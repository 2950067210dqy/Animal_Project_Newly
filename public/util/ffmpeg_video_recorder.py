import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import cv2
from PyQt6.QtCore import QThread
from loguru import logger


@dataclass
class _WriterState:
    writer: Any
    output_path: str
    partial_path: str
    backend: str
    frame_count: int = 0
    total_encode_ms: float = 0.0
    max_encode_ms: float = 0.0


class FFmpegVideoRecorderThread(QThread):
    """Non-blocking, low-resolution MP4 recorder using OpenCV's FFmpeg backend."""

    def __init__(
            self,
            fps: float = 10.0,
            width: int = 640,
            height: int = 360,
            codec: str = "mp4v",
            max_pending_frames: int = 8,
            stats_interval_seconds: float = 5.0,
            session_timestamp: float | None = None,
            diagnostic_callback: Callable[[str, str], None] | None = None,
            parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("deep_camera_ffmpeg_video_recorder")
        self.fps = max(float(fps), 0.1)
        self.width = self._even_dimension(width, 640)
        self.height = self._even_dimension(height, 360)
        self.output_size = (self.width, self.height)
        self.codec = str(codec or "mp4v")[:4]
        if len(self.codec) != 4:
            self.codec = "mp4v"
        self.max_pending_frames = max(int(max_pending_frames), 1)
        self.stats_interval_seconds = max(float(stats_interval_seconds), 1.0)
        self.session_timestamp = float(session_timestamp or time.time())
        self.session_text = datetime.fromtimestamp(self.session_timestamp).strftime(
            "%Y%m%d_%H%M%S_%f"
        )[:-3]
        self.diagnostic_callback = diagnostic_callback

        self._pending_by_cage = {}
        self._pending_order = deque()
        self._pending_lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._accepting = True
        self._last_submit_time_by_cage = {}
        self._writers: dict[int, _WriterState] = {}
        self._failed_cages = set()

        self.accepted_count = 0
        self.dropped_count = 0
        self.copy_count = 0
        self.total_copy_ms = 0.0
        self.max_copy_ms = 0.0
        self.encoded_count = 0
        self._encoded_since_log = 0
        self._encode_ms_since_log = 0.0
        self._last_stats_time = time.monotonic()

    @staticmethod
    def _even_dimension(value, default):
        try:
            result = max(int(float(value)), 2)
        except (TypeError, ValueError):
            result = int(default)
        return result if result % 2 == 0 else result - 1

    def submit_frame(self, cage_number: int, output_dir: str, timestamp: float, frame) -> bool:
        """Queue one sampled frame without ever waiting for the encoder."""
        if frame is None or not output_dir:
            return False

        cage_number = int(cage_number)
        timestamp = float(timestamp or time.time())
        with self._pending_lock:
            if not self._accepting:
                return False
            previous_timestamp = self._last_submit_time_by_cage.get(cage_number)
            if (
                    previous_timestamp is not None
                    and timestamp - previous_timestamp < (1.0 / self.fps) * 0.95
            ):
                return False
            self._last_submit_time_by_cage[cage_number] = timestamp

        copy_started = time.perf_counter()
        frame_copy = frame.copy()
        copy_ms = (time.perf_counter() - copy_started) * 1000.0

        with self._pending_lock:
            if not self._accepting:
                return False
            if cage_number in self._pending_by_cage:
                self._pending_by_cage[cage_number] = (
                    output_dir,
                    timestamp,
                    frame_copy,
                )
                self.dropped_count += 1
            else:
                if len(self._pending_by_cage) >= self.max_pending_frames:
                    dropped_cage = self._pending_order.popleft()
                    self._pending_by_cage.pop(dropped_cage, None)
                    self.dropped_count += 1
                self._pending_by_cage[cage_number] = (
                    output_dir,
                    timestamp,
                    frame_copy,
                )
                self._pending_order.append(cage_number)
            self.accepted_count += 1
            self.copy_count += 1
            self.total_copy_ms += copy_ms
            self.max_copy_ms = max(self.max_copy_ms, copy_ms)

        self._wake_event.set()
        return True

    def stop(self):
        with self._pending_lock:
            self._accepting = False
        self._stop_event.set()
        self._wake_event.set()

    def _pop_pending(self):
        with self._pending_lock:
            if not self._pending_order:
                return None
            cage_number = self._pending_order.popleft()
            item = self._pending_by_cage.pop(cage_number, None)
        if item is None:
            return None
        output_dir, timestamp, frame = item
        return cage_number, output_dir, timestamp, frame

    def _has_pending(self):
        with self._pending_lock:
            return bool(self._pending_order)

    def _open_writer(self, cage_number: int, output_dir: str) -> _WriterState | None:
        if cage_number in self._failed_cages:
            return None
        state = self._writers.get(cage_number)
        if state is not None:
            return state

        os.makedirs(output_dir, exist_ok=True)
        base_stem = f"capture_{self.session_text}_cage_{cage_number}"
        file_stem = base_stem
        segment_number = 1
        output_path = os.path.join(output_dir, f"{file_stem}.mp4")
        partial_path = os.path.join(output_dir, f"{file_stem}.partial.mp4")
        while os.path.exists(output_path) or os.path.exists(partial_path):
            segment_number += 1
            file_stem = f"{base_stem}_segment_{segment_number}"
            output_path = os.path.join(output_dir, f"{file_stem}.mp4")
            partial_path = os.path.join(output_dir, f"{file_stem}.partial.mp4")
        fourcc = cv2.VideoWriter_fourcc(*self.codec)
        writer = cv2.VideoWriter(
            partial_path,
            cv2.CAP_FFMPEG,
            fourcc,
            self.fps,
            self.output_size,
        )
        if not writer.isOpened():
            writer.release()
            self._failed_cages.add(cage_number)
            message = (
                "FFmpeg video writer open failed | "
                f"cage={cage_number}, codec={self.codec}, "
                f"fps={self.fps:.2f}, size={self.width}x{self.height}, "
                f"path={partial_path}"
            )
            logger.error(message)
            self._emit_diagnostic("video_recorder_open_failed", message)
            return None

        backend = writer.getBackendName()
        state = _WriterState(
            writer=writer,
            output_path=output_path,
            partial_path=partial_path,
            backend=backend,
        )
        self._writers[cage_number] = state
        message = (
            "FFmpeg video writer started | "
            f"cage={cage_number}, backend={backend}, codec={self.codec}, "
            f"fps={self.fps:.2f}, size={self.width}x{self.height}, "
            f"path={output_path}"
        )
        logger.info(message)
        self._emit_diagnostic("video_recorder_started", message)
        return state

    def _prepare_frame(self, frame):
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        source_h, source_w = frame.shape[:2]
        if (source_w, source_h) == self.output_size:
            return frame

        scale = min(self.width / source_w, self.height / source_h)
        resized_w = max(2, min(self.width, int(round(source_w * scale))))
        resized_h = max(2, min(self.height, int(round(source_h * scale))))
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        resized = cv2.resize(frame, (resized_w, resized_h), interpolation=interpolation)
        left = (self.width - resized_w) // 2
        right = self.width - resized_w - left
        top = (self.height - resized_h) // 2
        bottom = self.height - resized_h - top
        return cv2.copyMakeBorder(
            resized,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=(0, 0, 0),
        )

    def _write_frame(self, cage_number: int, output_dir: str, frame):
        state = self._open_writer(cage_number, output_dir)
        if state is None:
            return

        encode_started = time.perf_counter()
        prepared = self._prepare_frame(frame)
        state.writer.write(prepared)
        encode_ms = (time.perf_counter() - encode_started) * 1000.0
        state.frame_count += 1
        state.total_encode_ms += encode_ms
        state.max_encode_ms = max(state.max_encode_ms, encode_ms)
        self.encoded_count += 1
        self._encoded_since_log += 1
        self._encode_ms_since_log += encode_ms

    def _current_output_size_mb(self):
        size_bytes = 0
        for state in self._writers.values():
            try:
                if os.path.exists(state.partial_path):
                    size_bytes += os.path.getsize(state.partial_path)
            except OSError:
                pass
        return size_bytes / 1024.0 / 1024.0

    def _log_runtime(self, force=False):
        now = time.monotonic()
        elapsed = now - self._last_stats_time
        if not force and elapsed < self.stats_interval_seconds:
            return
        with self._pending_lock:
            pending_count = len(self._pending_by_cage)
            accepted_count = self.accepted_count
            dropped_count = self.dropped_count
            copy_count = self.copy_count
            total_copy_ms = self.total_copy_ms
            max_copy_ms = self.max_copy_ms
        interval_encoded = self._encoded_since_log
        encode_avg_ms = (
            self._encode_ms_since_log / interval_encoded
            if interval_encoded
            else 0.0
        )
        copy_avg_ms = total_copy_ms / copy_count if copy_count else 0.0
        message = (
            "deep camera video runtime | "
            f"target_fps_per_cage={self.fps:.2f}, "
            f"active_writers={len(self._writers)}, pending={pending_count}, "
            f"accepted={accepted_count}, encoded={self.encoded_count}, "
            f"dropped={dropped_count}, encode_avg_ms={encode_avg_ms:.2f}, "
            f"copy_avg_ms={copy_avg_ms:.2f}, copy_max_ms={max_copy_ms:.2f}, "
            f"current_size_mb={self._current_output_size_mb():.2f}"
        )
        logger.info(message)
        self._emit_diagnostic("video_recorder_runtime", message)
        self._encoded_since_log = 0
        self._encode_ms_since_log = 0.0
        self._last_stats_time = now

    def _close_writers(self):
        total_size_mb = 0.0
        for cage_number, state in list(self._writers.items()):
            try:
                state.writer.release()
                if os.path.exists(state.partial_path):
                    os.replace(state.partial_path, state.output_path)
                size_mb = (
                    os.path.getsize(state.output_path) / 1024.0 / 1024.0
                    if os.path.exists(state.output_path)
                    else 0.0
                )
                total_size_mb += size_mb
                duration_seconds = state.frame_count / self.fps
                estimated_10h_mb = (
                    size_mb * 36000.0 / duration_seconds
                    if duration_seconds > 0
                    else 0.0
                )
                encode_avg_ms = (
                    state.total_encode_ms / state.frame_count
                    if state.frame_count
                    else 0.0
                )
                message = (
                    "FFmpeg video writer finalized | "
                    f"cage={cage_number}, backend={state.backend}, "
                    f"frames={state.frame_count}, duration_s={duration_seconds:.1f}, "
                    f"size_mb={size_mb:.2f}, estimated_10h_mb={estimated_10h_mb:.1f}, "
                    f"encode_avg_ms={encode_avg_ms:.2f}, "
                    f"encode_max_ms={state.max_encode_ms:.2f}, "
                    f"path={state.output_path}"
                )
                logger.info(message)
                self._emit_diagnostic("video_recorder_finalized", message)
            except Exception as error:
                logger.exception(
                    f"finalize FFmpeg video failed cage={cage_number}: {error}"
                )
        self._writers.clear()
        logger.info(
            f"FFmpeg video recorder stopped | total_size_mb={total_size_mb:.2f}, "
            f"accepted={self.accepted_count}, encoded={self.encoded_count}, "
            f"dropped={self.dropped_count}"
        )

    def _emit_diagnostic(self, event: str, message: str):
        if self.diagnostic_callback is None:
            return
        try:
            self.diagnostic_callback(event, message)
        except Exception as error:
            logger.debug(f"video recorder diagnostic callback failed: {error}")

    def get_stats(self):
        with self._pending_lock:
            return {
                "accepted": self.accepted_count,
                "encoded": self.encoded_count,
                "dropped": self.dropped_count,
                "pending": len(self._pending_by_cage),
                "copy_avg_ms": (
                    self.total_copy_ms / self.copy_count
                    if self.copy_count
                    else 0.0
                ),
                "copy_max_ms": self.max_copy_ms,
            }

    def run(self):
        logger.info(
            "FFmpeg video recorder thread started | "
            f"fps={self.fps:.2f}, size={self.width}x{self.height}, "
            f"codec={self.codec}, max_pending={self.max_pending_frames}"
        )
        try:
            while not self._stop_event.is_set() or self._has_pending():
                item = self._pop_pending()
                if item is None:
                    self._log_runtime()
                    self._wake_event.wait(0.02)
                    self._wake_event.clear()
                    continue
                cage_number, output_dir, _timestamp, frame = item
                try:
                    self._write_frame(cage_number, output_dir, frame)
                except Exception as error:
                    logger.exception(
                        f"FFmpeg video frame write failed cage={cage_number}: {error}"
                    )
                self._log_runtime()
        finally:
            self._log_runtime(force=True)
            self._close_writers()
