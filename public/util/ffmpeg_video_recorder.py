import os
import shutil
import subprocess
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import cv2
from loguru import logger

from public.entity.MyQThread import MyQThread


@dataclass(frozen=True)
class FFmpegVideoRecorderConfig:
    ffmpeg_path: str = ""
    output_dir_name: str = "video"
    fps: float = 10.0
    width: int = 480
    height: int = 270
    bitrate_kbps: int = 100
    maxrate_kbps: int = 120
    bufsize_kbps: int = 240
    preset: str = "ultrafast"
    encoder_threads: int = 1
    stats_interval_seconds: float = 5.0


@dataclass
class _WriterState:
    cage_number: int
    output_path: str
    stderr_path: str
    process: subprocess.Popen
    stderr_handle: Any
    started_monotonic: float
    next_frame_due: float
    last_frame: Any = None
    last_frame_timestamp: float = 0.0
    encoded_frames: int = 0
    write_seconds: float = 0.0


def find_ffmpeg_executable(configured_path: str = "") -> str:
    configured_path = str(configured_path or "").strip().strip('"')
    if configured_path and os.path.isfile(configured_path):
        return os.path.abspath(configured_path)

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return os.path.abspath(system_ffmpeg)

    try:
        import imageio_ffmpeg

        bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled_ffmpeg and os.path.isfile(bundled_ffmpeg):
            return os.path.abspath(bundled_ffmpeg)
    except Exception:
        pass
    return ""


class FFmpegVideoRecorderThread(MyQThread):
    def __init__(
        self,
        config: FFmpegVideoRecorderConfig,
        session_timestamp: float | None = None,
        diagnostic_callback: Callable[[str, str], None] | None = None,
    ):
        super().__init__(name="deep_camera_ffmpeg_video_recorder")
        self.config = config
        self.ffmpeg_executable = find_ffmpeg_executable(config.ffmpeg_path)
        self.session_timestamp = float(session_timestamp or time.time())
        self.diagnostic_callback = diagnostic_callback

        self.fps = max(float(config.fps), 0.1)
        self.width = max(2, int(config.width) // 2 * 2)
        self.height = max(2, int(config.height) // 2 * 2)
        self.bitrate_kbps = max(1, int(config.bitrate_kbps))
        self.maxrate_kbps = max(self.bitrate_kbps, int(config.maxrate_kbps))
        self.bufsize_kbps = max(self.maxrate_kbps, int(config.bufsize_kbps))
        self.encoder_threads = max(1, int(config.encoder_threads))
        self.stats_interval_seconds = max(float(config.stats_interval_seconds), 1.0)
        self.output_dir_name = str(config.output_dir_name or "video").strip("/\\") or "video"

        self.pending_lock = threading.Lock()
        self.pending_frames: dict[int, tuple[str, Any, float]] = {}
        self.writer_states: dict[int, _WriterState] = {}
        self.disabled_cages: set[int] = set()
        self.submitted_frames = defaultdict(int)
        self.replaced_frames = defaultdict(int)
        self.last_stats_time = time.monotonic()
        self.accepting_frames = bool(self.ffmpeg_executable)

    @property
    def available(self):
        return bool(self.ffmpeg_executable)

    def _emit_diagnostic(self, event: str, message: str):
        if self.diagnostic_callback is not None:
            try:
                self.diagnostic_callback(event, message)
            except Exception as error:
                logger.debug(f"video recorder diagnostic callback failed: {error}")

    def submit_frame(self, cage_number: int, cage_path: str, frame, timestamp: float):
        if not self.accepting_frames or frame is None:
            return False

        cage_number = int(cage_number)
        if cage_number in self.disabled_cages:
            return False

        with self.pending_lock:
            if cage_number in self.pending_frames:
                self.replaced_frames[cage_number] += 1
            # capture.read() returns a new array. Keeping that reference avoids a
            # full-resolution copy in the camera and trajectory path.
            self.pending_frames[cage_number] = (str(cage_path), frame, float(timestamp))
            self.submitted_frames[cage_number] += 1
        return True

    def stop(self):
        self.accepting_frames = False
        super().stop()

    def run(self):
        self._running = True
        self._stop_requested = False
        self._paused = False
        expected_mb_10h = self.bitrate_kbps * 1000 * 10 * 60 * 60 / 8 / 1_000_000
        logger.info(
            f"FFmpeg video recorder started: ffmpeg={self.ffmpeg_executable}, "
            f"size={self.width}x{self.height}, fps={self.fps:g}, "
            f"bitrate={self.bitrate_kbps}kbps, estimated_10h={expected_mb_10h:.1f}MB/cage"
        )
        self._emit_diagnostic(
            "video_record_started",
            f"ffmpeg={self.ffmpeg_executable}, size={self.width}x{self.height}, "
            f"fps={self.fps:g}, bitrate_kbps={self.bitrate_kbps}, "
            f"estimated_10h_mb_per_cage={expected_mb_10h:.1f}",
        )
        try:
            while self._running and not self.isInterruptionRequested():
                self.dosomething()
        finally:
            self.accepting_frames = False
            self._close_all_writers()
            self._running = False
            logger.info("FFmpeg video recorder thread released")

    def dosomething(self):
        self._consume_latest_frames()
        now = time.monotonic()
        frame_interval = 1.0 / self.fps

        for cage_number, state in list(self.writer_states.items()):
            if state.last_frame is None or now < state.next_frame_due:
                continue
            try:
                frame = cv2.resize(
                    state.last_frame,
                    (self.width, self.height),
                    interpolation=cv2.INTER_AREA,
                )
                if not frame.flags.c_contiguous:
                    frame = frame.copy(order="C")
                write_started = time.perf_counter()
                state.process.stdin.write(frame.tobytes())
                state.write_seconds += time.perf_counter() - write_started
                state.encoded_frames += 1
                state.next_frame_due += frame_interval
                if state.next_frame_due < now - frame_interval:
                    state.next_frame_due = now + frame_interval
            except Exception as error:
                logger.error(
                    f"FFmpeg video write failed: cage={cage_number}, "
                    f"output={state.output_path}, reason={error}"
                )
                self._emit_diagnostic(
                    "video_record_failed",
                    f"cage={cage_number}, output={state.output_path}, reason={error}",
                )
                self.disabled_cages.add(cage_number)
                self._close_writer(cage_number, terminate=True)

        if now - self.last_stats_time >= self.stats_interval_seconds:
            self._log_runtime_stats(now)
            self.last_stats_time = now
        time.sleep(0.002)

    def _consume_latest_frames(self):
        with self.pending_lock:
            pending = self.pending_frames
            self.pending_frames = {}

        for cage_number, (cage_path, frame, timestamp) in pending.items():
            state = self.writer_states.get(cage_number)
            if state is None:
                state = self._open_writer(cage_number, cage_path)
                if state is None:
                    self.disabled_cages.add(cage_number)
                    continue
                self.writer_states[cage_number] = state
            state.last_frame = frame
            state.last_frame_timestamp = timestamp

    def _open_writer(self, cage_number: int, cage_path: str):
        video_dir = Path(cage_path) / self.output_dir_name
        video_dir.mkdir(parents=True, exist_ok=True)
        session_name = datetime.fromtimestamp(self.session_timestamp).strftime("%Y_%m_%d_%H_%M_%S_%f")[:-3]
        output_path = str(video_dir / f"video_{session_name}_cage{cage_number}.mp4")
        stderr_path = str(video_dir / f"video_{session_name}_cage{cage_number}.ffmpeg.log")
        stderr_handle = open(stderr_path, "ab", buffering=0)

        command = [
            self.ffmpeg_executable,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s:v",
            f"{self.width}x{self.height}",
            "-r",
            f"{self.fps:g}",
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            str(self.config.preset or "ultrafast"),
            "-tune",
            "zerolatency",
            "-b:v",
            f"{self.bitrate_kbps}k",
            "-maxrate",
            f"{self.maxrate_kbps}k",
            "-bufsize",
            f"{self.bufsize_kbps}k",
            "-g",
            str(max(1, int(round(self.fps * 10)))),
            "-threads",
            str(self.encoder_threads),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+frag_keyframe+empty_moov+default_base_moof",
            "-y",
            output_path,
        ]
        creation_flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        )
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                bufsize=0,
                creationflags=creation_flags,
            )
        except Exception as error:
            stderr_handle.close()
            logger.error(f"FFmpeg process start failed: cage={cage_number}, reason={error}")
            self._emit_diagnostic(
                "video_record_failed",
                f"cage={cage_number}, process_start_failed={error}",
            )
            return None

        logger.info(f"FFmpeg video output opened: cage={cage_number}, path={output_path}")
        self._emit_diagnostic(
            "video_output_opened",
            f"cage={cage_number}, path={output_path}",
        )
        now = time.monotonic()
        return _WriterState(
            cage_number=cage_number,
            output_path=output_path,
            stderr_path=stderr_path,
            process=process,
            stderr_handle=stderr_handle,
            started_monotonic=now,
            next_frame_due=now,
        )

    def _log_runtime_stats(self, now: float):
        with self.pending_lock:
            pending_count = len(self.pending_frames)
        for cage_number, state in self.writer_states.items():
            elapsed = max(now - state.started_monotonic, 0.001)
            file_size_mb = self._file_size_mb(state.output_path)
            average_write_ms = (
                state.write_seconds * 1000 / state.encoded_frames
                if state.encoded_frames
                else 0.0
            )
            message = (
                f"cage={cage_number}, encoded_fps={state.encoded_frames / elapsed:.2f}, "
                f"encoded_frames={state.encoded_frames}, "
                f"submitted_frames={self.submitted_frames[cage_number]}, "
                f"replaced_frames={self.replaced_frames[cage_number]}, "
                f"write_avg_ms={average_write_ms:.2f}, pending_cages={pending_count}, "
                f"file_size_mb={file_size_mb:.2f}, output={state.output_path}"
            )
            logger.debug(f"FFmpeg video runtime: {message}")
            self._emit_diagnostic("video_record_runtime", message)

    def _close_writer(self, cage_number: int, terminate=False):
        state = self.writer_states.pop(cage_number, None)
        if state is None:
            return
        try:
            if state.process.stdin is not None and not state.process.stdin.closed:
                state.process.stdin.close()
        except Exception:
            pass
        if terminate and state.process.poll() is None:
            try:
                state.process.terminate()
            except Exception:
                pass
        try:
            state.process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            try:
                state.process.kill()
                state.process.wait(timeout=1.0)
            except Exception:
                pass
        try:
            state.stderr_handle.close()
        except Exception:
            pass
        self._log_final_state(state)

    def _close_all_writers(self):
        states = list(self.writer_states.values())
        self.writer_states = {}
        for state in states:
            try:
                if state.process.stdin is not None and not state.process.stdin.closed:
                    state.process.stdin.close()
            except Exception:
                pass

        deadline = time.monotonic() + 5.0
        for state in states:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                state.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    state.process.terminate()
                    state.process.wait(timeout=1.0)
                except Exception:
                    try:
                        state.process.kill()
                    except Exception:
                        pass
            try:
                state.stderr_handle.close()
            except Exception:
                pass
            self._log_final_state(state)

    def _log_final_state(self, state: _WriterState):
        elapsed = max(time.monotonic() - state.started_monotonic, 0.001)
        file_size_mb = self._file_size_mb(state.output_path)
        message = (
            f"cage={state.cage_number}, duration_seconds={elapsed:.1f}, "
            f"encoded_frames={state.encoded_frames}, file_size_mb={file_size_mb:.2f}, "
            f"output={state.output_path}, ffmpeg_log={state.stderr_path}"
        )
        logger.info(f"FFmpeg video finalized: {message}")
        self._emit_diagnostic("video_record_finalized", message)

    @staticmethod
    def _file_size_mb(path: str):
        try:
            return os.path.getsize(path) / 1_000_000
        except OSError:
            return 0.0
