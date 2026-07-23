import struct
import time
from multiprocessing import shared_memory
from typing import Any

import numpy as np


META_STRUCT = struct.Struct("<qqdiiiii")


class SharedVideoFrameStore:
    def __init__(
        self,
        prefix: str = "animal_project_video",
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

        try:
            meta_shm = shared_memory.SharedMemory(name=meta_name, create=True, size=META_STRUCT.size)
            meta_shm.buf[: META_STRUCT.size] = META_STRUCT.pack(0, 0, 0.0, 0, 0, self.channels, 0, 0)
        except FileExistsError:
            meta_shm = shared_memory.SharedMemory(name=meta_name, create=False)

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

        try:
            frame_shm = shared_memory.SharedMemory(name=frame_name, create=False)
            meta_shm = shared_memory.SharedMemory(name=meta_name, create=False)
        except FileNotFoundError:
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
        current_seq = META_STRUCT.unpack(meta_shm.buf[: META_STRUCT.size])[0]
        start_seq = current_seq + 1 if current_seq % 2 == 0 else current_seq + 2

        meta_shm.buf[: META_STRUCT.size] = META_STRUCT.pack(start_seq, frame_id, timestamp, 0, 0, channels, 0, 0)
        frame_shm.buf[:frame_bytes] = array.reshape(-1).tobytes()
        meta_shm.buf[: META_STRUCT.size] = META_STRUCT.pack(
            start_seq + 1,
            frame_id,
            timestamp,
            height,
            width,
            channels,
            frame_bytes,
            1,
        )

    def read_frame(self, stream_name: str, cage_number: int, *, retries: int = 3) -> dict[str, Any] | None:
        shm_pair = self._get_or_open_reader_pair(stream_name, cage_number)
        if shm_pair is None:
            return None

        frame_shm, meta_shm = shm_pair
        for _ in range(max(retries, 1)):
            seq_1, frame_id, timestamp, height, width, channels, frame_bytes, valid = META_STRUCT.unpack(
                meta_shm.buf[: META_STRUCT.size]
            )
            if valid != 1 or seq_1 % 2 == 1 or frame_bytes <= 0 or height <= 0 or width <= 0:
                return None

            raw = bytes(frame_shm.buf[:frame_bytes])
            seq_2 = META_STRUCT.unpack(meta_shm.buf[: META_STRUCT.size])[0]
            if seq_1 != seq_2 or seq_2 % 2 == 1:
                continue

            frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, channels))
            return {
                "cage_number": int(cage_number),
                "frame_id": int(frame_id),
                "timestamp": float(timestamp),
                "frame": frame,
            }
        return None

    def clear_frame(self, stream_name: str, cage_number: int) -> None:
        shm_pair = self._get_or_create_writer_pair(stream_name, cage_number)
        _frame_shm, meta_shm = shm_pair
        current_seq = META_STRUCT.unpack(meta_shm.buf[: META_STRUCT.size])[0]
        start_seq = current_seq + 1 if current_seq % 2 == 0 else current_seq + 2
        meta_shm.buf[: META_STRUCT.size] = META_STRUCT.pack(start_seq + 1, 0, 0.0, 0, 0, self.channels, 0, 0)

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
