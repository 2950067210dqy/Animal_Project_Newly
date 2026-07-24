import struct
import time
from multiprocessing import shared_memory
from typing import Any

import numpy as np


# seq, camera_session_id, frame_sequence, capture_monotonic_ns,
# capture_wall_time, height, width, channels, frame_bytes, valid
META_STRUCT = struct.Struct("<qqqqdiiiii")


class SharedVideoFrameStore:
    def __init__(
        self,
        prefix: str = "animal_project_video_v2",
        *,
        max_width: int = 1280,
        max_height: int = 720,
        channels: int = 3,
    ):
        self.prefix = prefix
        self.max_width = max_width
        self.max_height = max_height
        self.channels = channels
        self.max_frame_bytes = max_width * max_height * channels
        self._writer_shm: dict[tuple[str, int], tuple[shared_memory.SharedMemory, shared_memory.SharedMemory]] = {}
        self._reader_shm: dict[tuple[str, int], tuple[shared_memory.SharedMemory, shared_memory.SharedMemory]] = {}

    def _frame_name(self, stream_name: str, cage_number: int) -> str:
        return f"{self.prefix}_{stream_name}_frame_{int(cage_number)}"

    def _meta_name(self, stream_name: str, cage_number: int) -> str:
        return f"{self.prefix}_{stream_name}_meta_{int(cage_number)}"

    def _get_or_create_writer_pair(
        self, stream_name: str, cage_number: int
    ) -> tuple[shared_memory.SharedMemory, shared_memory.SharedMemory]:
        key = (stream_name, int(cage_number))
        cached = self._writer_shm.get(key)
        if cached is not None:
            return cached

        frame_name = self._frame_name(stream_name, cage_number)
        meta_name = self._meta_name(stream_name, cage_number)

        try:
            frame_shm = shared_memory.SharedMemory(name=frame_name, create=True, size=self.max_frame_bytes)
        except FileExistsError:
            frame_shm = shared_memory.SharedMemory(name=frame_name, create=False)
            if frame_shm.size < self.max_frame_bytes:
                frame_shm.close()
                raise RuntimeError(
                    f"shared frame segment is too small: name={frame_name}, "
                    f"size={frame_shm.size}, required={self.max_frame_bytes}"
                )

        try:
            meta_shm = shared_memory.SharedMemory(name=meta_name, create=True, size=META_STRUCT.size)
            meta_shm.buf[: META_STRUCT.size] = META_STRUCT.pack(
                0,
                0,
                0,
                0,
                0.0,
                0,
                0,
                self.channels,
                0,
                0,
            )
        except FileExistsError:
            meta_shm = shared_memory.SharedMemory(name=meta_name, create=False)
            if meta_shm.size < META_STRUCT.size:
                frame_shm.close()
                meta_shm.close()
                raise RuntimeError(
                    f"shared metadata segment is too small: name={meta_name}, "
                    f"size={meta_shm.size}, required={META_STRUCT.size}"
                )

        self._writer_shm[key] = (frame_shm, meta_shm)
        return frame_shm, meta_shm

    def _get_or_open_reader_pair(
        self, stream_name: str, cage_number: int
    ) -> tuple[shared_memory.SharedMemory, shared_memory.SharedMemory] | None:
        key = (stream_name, int(cage_number))
        cached = self._reader_shm.get(key)
        if cached is not None:
            return cached

        frame_name = self._frame_name(stream_name, cage_number)
        meta_name = self._meta_name(stream_name, cage_number)

        frame_shm = None
        try:
            frame_shm = shared_memory.SharedMemory(name=frame_name, create=False)
            meta_shm = shared_memory.SharedMemory(name=meta_name, create=False)
        except FileNotFoundError:
            if frame_shm is not None:
                frame_shm.close()
            return None

        self._reader_shm[key] = (frame_shm, meta_shm)
        return frame_shm, meta_shm

    def write_frame(
        self,
        stream_name: str,
        cage_number: int,
        frame: np.ndarray,
        *,
        frame_id: int,
        timestamp: float | None = None,
        camera_session_id: int = 0,
        capture_monotonic_ns: int | None = None,
    ) -> None:
        if frame is None:
            return

        array = np.ascontiguousarray(frame)
        if array.ndim != 3:
            raise ValueError(f"shared frame expects 3-D array, got shape={array.shape}")

        height, width, channels = array.shape
        if channels != self.channels:
            raise ValueError(f"shared frame expects channels={self.channels}, got {channels}")

        frame_bytes = int(array.nbytes)
        if frame_bytes > self.max_frame_bytes:
            raise ValueError(
                f"shared frame bytes overflow: frame_bytes={frame_bytes}, max_frame_bytes={self.max_frame_bytes}"
            )

        frame_shm, meta_shm = self._get_or_create_writer_pair(stream_name, cage_number)
        timestamp = float(time.time() if timestamp is None else timestamp)
        capture_monotonic_ns = int(
            time.monotonic_ns() if capture_monotonic_ns is None else capture_monotonic_ns
        )
        camera_session_id = int(camera_session_id)
        frame_id = int(frame_id)
        current_seq = META_STRUCT.unpack(meta_shm.buf[: META_STRUCT.size])[0]
        start_seq = current_seq + 1 if current_seq % 2 == 0 else current_seq + 2

        meta_shm.buf[: META_STRUCT.size] = META_STRUCT.pack(
            start_seq,
            camera_session_id,
            frame_id,
            capture_monotonic_ns,
            timestamp,
            0,
            0,
            channels,
            0,
            0,
        )
        frame_shm.buf[:frame_bytes] = array.reshape(-1).tobytes()
        meta_shm.buf[: META_STRUCT.size] = META_STRUCT.pack(
            start_seq + 1,
            camera_session_id,
            frame_id,
            capture_monotonic_ns,
            timestamp,
            height,
            width,
            channels,
            frame_bytes,
            1,
        )

    def read_frame(
        self,
        stream_name: str,
        cage_number: int,
        *,
        retries: int = 3,
        max_age_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        shm_pair = self._get_or_open_reader_pair(stream_name, cage_number)
        if shm_pair is None:
            return None

        frame_shm, meta_shm = shm_pair
        for _ in range(max(retries, 1)):
            (
                seq_1,
                camera_session_id,
                frame_sequence,
                capture_monotonic_ns,
                capture_wall_time,
                height,
                width,
                channels,
                frame_bytes,
                valid,
            ) = META_STRUCT.unpack(meta_shm.buf[: META_STRUCT.size])
            if seq_1 % 2 == 1:
                continue
            if valid != 1 or frame_bytes <= 0 or height <= 0 or width <= 0:
                return None
            expected_frame_bytes = int(height) * int(width) * int(channels)
            if (
                channels != self.channels
                or height > self.max_height
                or width > self.max_width
                or frame_bytes != expected_frame_bytes
                or frame_bytes > self.max_frame_bytes
            ):
                return None
            if (
                max_age_seconds is not None
                and max_age_seconds > 0
                and capture_monotonic_ns > 0
                and time.monotonic_ns() - capture_monotonic_ns
                > int(max_age_seconds * 1_000_000_000)
            ):
                return None

            raw = bytes(frame_shm.buf[:frame_bytes])
            seq_2 = META_STRUCT.unpack(meta_shm.buf[: META_STRUCT.size])[0]
            if seq_1 != seq_2 or seq_2 % 2 == 1:
                continue

            frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, channels))
            return {
                "cage_number": int(cage_number),
                "camera_session_id": int(camera_session_id),
                "frame_sequence": int(frame_sequence),
                "frame_id": int(frame_sequence),
                "capture_monotonic_ns": int(capture_monotonic_ns),
                "capture_wall_time": float(capture_wall_time),
                "timestamp": float(capture_wall_time),
                "frame": frame,
            }
        return None

    def clear_frame(self, stream_name: str, cage_number: int) -> None:
        shm_pair = self._get_or_create_writer_pair(stream_name, cage_number)
        _frame_shm, meta_shm = shm_pair
        current_seq = META_STRUCT.unpack(meta_shm.buf[: META_STRUCT.size])[0]
        start_seq = current_seq + 1 if current_seq % 2 == 0 else current_seq + 2
        meta_shm.buf[: META_STRUCT.size] = META_STRUCT.pack(
            start_seq + 1,
            0,
            0,
            0,
            0.0,
            0,
            0,
            self.channels,
            0,
            0,
        )

    def close_reader(self) -> None:
        for frame_shm, meta_shm in self._reader_shm.values():
            try:
                frame_shm.close()
            except Exception:
                pass
            try:
                meta_shm.close()
            except Exception:
                pass
        self._reader_shm.clear()

    def close_writer(self) -> None:
        for frame_shm, meta_shm in self._writer_shm.values():
            try:
                frame_shm.close()
            except Exception:
                pass
            try:
                meta_shm.close()
            except Exception:
                pass
        self._writer_shm.clear()


shared_video_frame_store = SharedVideoFrameStore()
