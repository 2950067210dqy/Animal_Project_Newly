import json
import shutil
import threading
import time
import traceback
from collections import deque
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
from PyQt6.QtCore import pyqtSignal
from loguru import logger
from ultralytics import YOLO

from Module.mouse_trajectory.paths import (
    DEFAULT_BOX_MODEL_PATH,
    DEFAULT_GRID_JSON_PATH,
    DEFAULT_IMAGE_REGISTRATION_JSON_PATH,
    DEFAULT_INSTRUMENT_AREA_JSON_PATH,
    DEFAULT_MOUSE_MODEL_PATH,
    DEFAULT_REFERENCE_IMAGE_PATH,
    EXPORT_DIR,
    get_cage_annotated_history_dir,
    get_cage_annotated_latest_dir,
    get_cage_data_dir,
    get_cage_export_dir,
    get_cage_plots_dir,
)
from Module.mouse_trajectory.service.auto_mouse_trajectory import (
    CAL,
    BoxCorners,
    DetectionBox,
    HeadlessCalibration,
    best_box_from_result,
    build_row,
    extract_box_corners,
    map_topdown_polygon_to_physical,
    mean_corner_distance,
    parse_grid_json,
    parse_image_registration_json,
    parse_topdown_instrument_polygons,
    render_annotation_image,
    run_yolo_batch,
    run_yolo_single,
    save_csv,
    save_plots,
    solve_mouse_location,
    stabilize_trajectory_rows,
)
from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread


_OUTPUT_WRITE_LOCK = threading.RLock()
from public.util.time_util import time_util


def _serialize_detection_box(mouse_box: DetectionBox | None) -> dict[str, Any] | None:
    if mouse_box is None:
        return None
    return {
        "xyxy": [float(value) for value in mouse_box.xyxy],
        "conf": float(mouse_box.conf),
        "cls": float(mouse_box.cls),
    }


def _serialize_corners(corners: BoxCorners | None) -> list[dict[str, Any]] | None:
    if corners is None:
        return None
    return [{"x": float(point["x"]), "y": float(point["y"])} for point in corners.corners]


class MouseTrajectoryThread(MyQThread):
    trajectory_ready = pyqtSignal(dict)

    def __init__(self):
        super().__init__(name="mouse_trajectory_thread")
        self.pending_frames: deque[tuple[int, dict[str, Any]]] = deque()
        self.pending_frame_keys: set[tuple[int, int]] = set()
        self.pending_file_keys: set[tuple[int, str]] = set()
        self.processed_file_keys: set[tuple[int, str]] = set()
        self.pending_lock = threading.RLock()
        self.inflight_frame_counts_by_cage: dict[int, int] = {}
        self.inflight_since_by_cage: dict[int, float] = {}
        self.stale_inflight_logged_by_cage: set[int] = set()
        self.last_claimed_frame_versions: dict[int, tuple[int, int]] = {}
        self.last_processed_frame_versions: dict[int, tuple[int, int]] = {}
        self.fixed_corners_by_cage: dict[int, BoxCorners] = {}
        self.previous_corners_by_cage: dict[int, list[dict[str, Any]]] = {}
        self.trajectory_rows: dict[int, list[dict[str, Any]]] = {}
        self.shift_logs: dict[int, list[dict[str, Any]]] = {}
        self.latest_plot_paths: dict[int, dict[str, str]] = {}
        self.latest_plot_title_by_cage: dict[int, str] = {}
        self.last_output_flush_by_cage: dict[int, float] = {}
        self.first_timestamp_by_cage: dict[int, float] = {}
        self.last_plotted_window_by_cage: dict[int, int] = {}
        self.processed_frame_count = 0
        self.processed_frame_count_by_cage: dict[int, int] = {}
        self.dropped_frame_count_by_cage: dict[int, int] = {}
        self.total_dropped_frame_count = 0
        self.processing_started_at = time.time()
        self.processing_started_at_by_cage: dict[int, float] = {}
        self.accepting_frames = True
        self.finish_after_drain = False
        self.final_outputs_done = False
        self.mouse_annotated_jpg_quality = 75
        self.annotated_save_interval_seconds = 1.0
        self.annotated_output_size = (64, 24)
        self.last_annotated_schedule_by_cage: dict[int, float] = {}
        self.last_annotated_save_by_cage: dict[int, float] = {}
        self.latest_annotated_path_by_cage: dict[int, Path] = {}
        self.annotated_history_retention_seconds = 300.0
        self.annotated_history_cleanup_interval_seconds = 60.0

        self.reference_image_path = DEFAULT_REFERENCE_IMAGE_PATH
        self.grid_json_path = DEFAULT_GRID_JSON_PATH
        self.registration_json_path = DEFAULT_IMAGE_REGISTRATION_JSON_PATH
        self.instrument_area_json_path = DEFAULT_INSTRUMENT_AREA_JSON_PATH
        self.box_model_path = DEFAULT_BOX_MODEL_PATH
        self.mouse_model_path = DEFAULT_MOUSE_MODEL_PATH

        self.conf_box = 0.4
        self.conf_mouse = 0.4
        self.imgsz = 640
        self.batch_size = 8
        self.shift_threshold_px = 10.0
        self.output_flush_interval_seconds = 10.0
        self.plot_window_seconds = 60.0
        self.max_pending_frames_per_cage = 1
        self.max_total_pending_frames = 8
        self.inflight_watchdog_seconds = 5.0
        self.yolo_fps_ema = 0.0
        self.processing_fps_ema = 0.0
        self.yolo_fps_safety_factor = 0.85
        self.async_job_lock = threading.RLock()
        self.async_jobs: dict[tuple[Any, ...], Future] = {}
        self.output_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="mouse_trajectory_output",
        )
        self.preview_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="mouse_trajectory_preview",
        )
        self.async_executors_shutdown = False
        self.finalize_lock = threading.Lock()

        self.solver: HeadlessCalibration | None = None
        self.static_registration: dict[str, Any] | None = None
        self.instrument_polygon_img = None
        self.instrument_polygon_phys = None
        self.box_model: YOLO | None = None
        self.mouse_model: YOLO | None = None
        self.ref_corners: BoxCorners | None = None
        self.last_cleanup_time = time.time()

    @staticmethod
    def _build_model(model_path: Path | str, task: str) -> YOLO:
        return YOLO(str(model_path), task=task)

    @staticmethod
    def _frame_version(frame_payload: dict[str, Any]) -> tuple[int, int]:
        frame_sequence = int(
            frame_payload.get("frame_sequence", frame_payload.get("frame_id", 0)) or 0
        )
        camera_session_id = int(frame_payload.get("camera_session_id", 0) or 0)
        if camera_session_id > 0:
            return camera_session_id, frame_sequence
        timestamp = float(frame_payload.get("timestamp", 0.0) or 0.0)
        return int(timestamp * 1_000_000_000), frame_sequence

    @staticmethod
    def _is_stale_frame_version(
        frame_version: tuple[int, int],
        previous_version: tuple[int, int] | None,
    ) -> bool:
        return (
            previous_version is not None
            and frame_version[0] == previous_version[0]
            and frame_version[1] <= previous_version[1]
        )

    def before_Runing_work(self):
        self._load_runtime_config()
        self._prepare_runtime()

    def submit_frame(self, cage_number: int, frame_payload: dict[str, Any]) -> bool:
        if not self.accepting_frames or not frame_payload:
            return False
        has_frame = frame_payload.get("frame") is not None
        has_file = bool(frame_payload.get("file_path") or frame_payload.get("image_path"))
        if not has_frame and not has_file:
            return False
        cage_number = int(cage_number)
        frame_id = int(frame_payload.get("frame_id", 0) or 0)
        frame_version = self._frame_version(frame_payload)
        frame_key = (cage_number, frame_id)
        file_key = self._payload_file_key(cage_number, frame_payload)
        with self.pending_lock:
            if frame_id > 0 and self._is_stale_frame_version(
                frame_version,
                self.last_claimed_frame_versions.get(cage_number),
            ):
                return False
            if file_key is not None and (
                file_key in self.pending_file_keys or file_key in self.processed_file_keys
            ):
                return False

            active_for_cage = (
                self._pending_count_locked(cage_number)
                + self.inflight_frame_counts_by_cage.get(cage_number, 0)
            )
            if active_for_cage >= 1:
                inflight_since = self.inflight_since_by_cage.get(cage_number)
                if (
                    inflight_since is not None
                    and time.time() - inflight_since >= self.inflight_watchdog_seconds
                    and cage_number not in self.stale_inflight_logged_by_cage
                ):
                    logger.error(
                        f"mouse trajectory cage={cage_number} has been in-flight for "
                        f"{time.time() - inflight_since:.2f}s"
                    )
                    self.stale_inflight_logged_by_cage.add(cage_number)
                self._record_dropped_frame_locked(cage_number)
                return False

            while (
                self.max_pending_frames_per_cage > 0
                and self._pending_count_locked(cage_number) >= self.max_pending_frames_per_cage
            ):
                if not self._drop_oldest_pending_locked(cage_number):
                    break
            while (
                self.max_total_pending_frames > 0
                and len(self.pending_frames) >= self.max_total_pending_frames
            ):
                if not self._drop_oldest_pending_locked():
                    break
            self.pending_frames.append((cage_number, dict(frame_payload)))
            if frame_id > 0:
                self.pending_frame_keys.add(frame_key)
                self.last_claimed_frame_versions[cage_number] = frame_version
            if file_key is not None:
                self.pending_file_keys.add(file_key)
        return True

    def submit_frames(self, cage_frame_map: dict[int, dict[str, Any]]):
        sorted_items = sorted(
            cage_frame_map.items(),
            key=lambda item: self._frame_sort_key(int(item[0]), item[1]),
        )
        for cage_number, frame_payload in sorted_items:
            self.submit_frame(cage_number, frame_payload)

    @staticmethod
    def _normalize_file_key(file_path_text: str) -> str:
        try:
            return str(Path(file_path_text).resolve()).lower()
        except OSError:
            return str(Path(file_path_text).absolute()).lower()

    def _payload_file_key(self, cage_number: int, frame_payload: dict[str, Any]) -> tuple[int, str] | None:
        file_path = frame_payload.get("file_path") or frame_payload.get("image_path")
        if not file_path:
            return None
        return int(cage_number), self._normalize_file_key(str(file_path))

    def _mark_payload_processed(self, cage_number: int, frame_payload: dict[str, Any]):
        file_key = self._payload_file_key(cage_number, frame_payload)
        if file_key is None:
            return
        with self.pending_lock:
            self.pending_file_keys.discard(file_key)
            self.processed_file_keys.add(file_key)

    def _pending_count_locked(self, cage_number: int | None = None) -> int:
        if cage_number is None:
            return len(self.pending_frames)
        return sum(1 for pending_cage, _ in self.pending_frames if int(pending_cage) == int(cage_number))

    def _drop_oldest_pending_locked(self, cage_number: int | None = None) -> bool:
        target_index = None
        for index, (pending_cage, _frame_payload) in enumerate(self.pending_frames):
            if cage_number is None or int(pending_cage) == int(cage_number):
                target_index = index
                break
        if target_index is None:
            return False

        pending_items = list(self.pending_frames)
        dropped_cage, dropped_payload = pending_items.pop(target_index)
        self.pending_frames = deque(pending_items)

        dropped_cage = int(dropped_cage)
        frame_id = int(dropped_payload.get("frame_id", 0) or 0)
        if frame_id > 0:
            self.pending_frame_keys.discard((dropped_cage, frame_id))
        file_key = self._payload_file_key(dropped_cage, dropped_payload)
        if file_key is not None:
            self.pending_file_keys.discard(file_key)
        self._record_dropped_frame_locked(dropped_cage)
        return True

    def _record_dropped_frame_locked(self, cage_number: int):
        cage_number = int(cage_number)
        self.dropped_frame_count_by_cage[cage_number] = (
            self.dropped_frame_count_by_cage.get(cage_number, 0) + 1
        )
        self.total_dropped_frame_count += 1

    def _mark_inflight_locked(self, cage_number: int):
        cage_number = int(cage_number)
        self.inflight_frame_counts_by_cage[cage_number] = self.inflight_frame_counts_by_cage.get(cage_number, 0) + 1
        self.inflight_since_by_cage.setdefault(cage_number, time.time())

    def _mark_inflight_finished(self, cage_number: int):
        cage_number = int(cage_number)
        with self.pending_lock:
            current_count = self.inflight_frame_counts_by_cage.get(cage_number, 0)
            if current_count <= 1:
                self.inflight_frame_counts_by_cage.pop(cage_number, None)
                self.inflight_since_by_cage.pop(cage_number, None)
                self.stale_inflight_logged_by_cage.discard(cage_number)
            else:
                self.inflight_frame_counts_by_cage[cage_number] = current_count - 1

    @staticmethod
    def _load_payload_frame(frame_payload: dict[str, Any]):
        frame = frame_payload.get("frame")
        if frame is not None:
            return frame

        file_path = frame_payload.get("file_path") or frame_payload.get("image_path")
        if not file_path:
            return None

        image = cv2.imread(str(file_path))
        if image is None:
            logger.warning(f"mouse trajectory local image read failed: {file_path}")
        return image

    def dosomething(self):
        frame_items: list[tuple[int, dict[str, Any]]] = []
        try:
            self._schedule_history_cleanup_if_needed()
            frame_items = self._pop_pending_frames(self.batch_size)
            if not frame_items:
                if self.finish_after_drain:
                    self.finalize_outputs()
                    super().stop()
                    return
                time.sleep(0.03)
                return

            batch_start = time.perf_counter()
            self._process_frame_batch(frame_items)
            self._record_processing_fps(
                len(frame_items),
                time.perf_counter() - batch_start,
            )
        except Exception as error:
            logger.error(
                f"mouse trajectory batch processing failed: {error} | "
                f"{traceback.format_exc()}"
            )
        finally:
            for cage_number, _frame_payload in frame_items:
                self._mark_inflight_finished(cage_number)

    def request_finish_after_drain(self):
        self.accepting_frames = False
        self.finish_after_drain = True

    def stop(self):
        self.accepting_frames = False
        self._shutdown_async_executors(wait=False, cancel_pending=True)
        super().stop()

    def finalize_outputs(self):
        with self.finalize_lock:
            if self.final_outputs_done:
                return
            try:
                self._wait_for_async_outputs()
                self._flush_all_outputs(final=True)
                self.final_outputs_done = True
            except Exception as error:
                logger.error(f"mouse trajectory final flush failed: {error}")
            finally:
                self._shutdown_async_executors(wait=True, cancel_pending=False)

    def _load_runtime_config(self):
        try:
            camera_config = global_setting.get_setting("camera_config")
            trajectory_config = {}
            if camera_config and "MOUSE_TRAJECTORY" in camera_config:
                trajectory_config = camera_config["MOUSE_TRAJECTORY"]
            self.imgsz = int(float(trajectory_config.get("yolo_imgsz", self.imgsz) or self.imgsz))
            self.batch_size = max(
                int(float(trajectory_config.get("yolo_batch_size", self.batch_size) or self.batch_size)),
                1,
            )
            self.output_flush_interval_seconds = float(
                trajectory_config.get("data_flush_interval_seconds", self.output_flush_interval_seconds)
                or self.output_flush_interval_seconds
            )
            self.plot_window_seconds = float(
                trajectory_config.get("plot_window_seconds", self.plot_window_seconds) or self.plot_window_seconds
            )
            self.max_pending_frames_per_cage = 1
            self.max_total_pending_frames = 8
            self.annotated_save_interval_seconds = max(
                float(
                    trajectory_config.get(
                        "annotated_save_interval_seconds",
                        self.annotated_save_interval_seconds,
                    )
                    or self.annotated_save_interval_seconds
                ),
                0.0,
            )
            self.annotated_output_size = (64, 24)
            self.mouse_annotated_jpg_quality = max(
                1,
                min(
                    100,
                    int(
                        float(
                            trajectory_config.get(
                                "annotated_jpg_quality",
                                self.mouse_annotated_jpg_quality,
                            )
                            or self.mouse_annotated_jpg_quality
                        )
                    ),
                ),
            )
            self.annotated_history_retention_seconds = float(
                trajectory_config.get(
                    "annotated_history_retention_seconds",
                    self.annotated_history_retention_seconds,
                )
                or self.annotated_history_retention_seconds
            )
            self.annotated_history_cleanup_interval_seconds = float(
                trajectory_config.get(
                    "annotated_history_cleanup_interval_seconds",
                    self.annotated_history_cleanup_interval_seconds,
                )
                or self.annotated_history_cleanup_interval_seconds
            )
        except Exception as error:
            logger.warning(f"load mouse trajectory runtime config failed, use defaults: {error}")

    def _pop_pending_frame(self) -> tuple[int, dict[str, Any]] | None:
        frame_items = self._pop_pending_frames(1)
        if not frame_items:
            return None
        return frame_items[0]

    @staticmethod
    def _frame_sort_key(cage_number: int, frame_payload: dict[str, Any]) -> tuple[float, int, str, int]:
        timestamp = float(frame_payload.get("timestamp", 0.0) or 0.0)
        frame_id = int(frame_payload.get("frame_id", 0) or 0)
        frame_name = str(frame_payload.get("frame_key") or frame_payload.get("frame_name") or "")
        if not frame_name:
            file_path = frame_payload.get("file_path") or frame_payload.get("image_path")
            if file_path:
                frame_name = Path(str(file_path)).name
        return timestamp, frame_id, frame_name, int(cage_number)

    def _pop_pending_frames(self, max_items: int) -> list[tuple[int, dict[str, Any]]]:
        max_items = max(int(max_items), 1)
        frame_items: list[tuple[int, dict[str, Any]]] = []
        with self.pending_lock:
            if not self.pending_frames:
                return frame_items

            sorted_pending = sorted(
                self.pending_frames,
                key=lambda item: self._frame_sort_key(int(item[0]), item[1]),
            )
            selected_items = sorted_pending[:max_items]
            remaining_items = sorted_pending[max_items:]

            for cage_number, frame_payload in selected_items:
                cage_number = int(cage_number)
                frame_id = int(frame_payload.get("frame_id", 0) or 0)
                if frame_id > 0:
                    self.pending_frame_keys.discard((cage_number, frame_id))
                file_key = self._payload_file_key(cage_number, frame_payload)
                if file_key is not None:
                    self.pending_file_keys.discard(file_key)
                self._mark_inflight_locked(cage_number)
                frame_items.append((cage_number, frame_payload))

            self.pending_frames = deque(remaining_items)
        if frame_items:
            frame_ids = [int(frame_payload.get("frame_id", 0) or 0) for _, frame_payload in frame_items]
            cage_numbers = [int(cage_number) for cage_number, _ in frame_items]
            timestamps = [
                float(frame_payload.get("timestamp", 0.0) or 0.0)
                for _, frame_payload in frame_items
            ]
            logger.debug(
                "mouse trajectory pop ordered batch: "
                f"count={len(frame_items)}, cages={cage_numbers}, "
                f"frame_ids={frame_ids}, timestamps={timestamps}, pending={self._pending_count()}"
            )
        return frame_items

    def _pending_count(self, cage_number: int | None = None) -> int:
        with self.pending_lock:
            return self._pending_count_locked(cage_number)

    def get_pending_count(self, cage_number: int | None = None) -> int:
        with self.pending_lock:
            pending_count = self._pending_count_locked(cage_number)
            if cage_number is None:
                inflight_count = sum(self.inflight_frame_counts_by_cage.values())
            else:
                inflight_count = self.inflight_frame_counts_by_cage.get(int(cage_number), 0)
            return pending_count + inflight_count

    def _submit_async_job(
        self,
        job_key: tuple[Any, ...],
        executor: ThreadPoolExecutor,
        callback,
        *args,
        **kwargs,
    ) -> bool:
        with self.async_job_lock:
            if self.async_executors_shutdown:
                return False
            existing = self.async_jobs.get(job_key)
            if existing is not None and not existing.done():
                return False

            future = executor.submit(callback, *args, **kwargs)
            self.async_jobs[job_key] = future

        def _job_done(done_future: Future):
            try:
                done_future.result()
            except CancelledError:
                pass
            except Exception as error:
                logger.error(f"mouse trajectory async output failed key={job_key}: {error}")
            finally:
                with self.async_job_lock:
                    if self.async_jobs.get(job_key) is done_future:
                        self.async_jobs.pop(job_key, None)

        future.add_done_callback(_job_done)
        return True

    def _wait_for_async_outputs(self):
        while True:
            with self.async_job_lock:
                pending_futures = [
                    future for future in self.async_jobs.values() if not future.done()
                ]
            if not pending_futures:
                return
            for future in pending_futures:
                try:
                    future.result()
                except Exception:
                    pass

    def _get_async_queue_sizes(self) -> dict[str, int]:
        with self.async_job_lock:
            active_keys = [
                job_key
                for job_key, future in self.async_jobs.items()
                if not future.done()
            ]
        return {
            "recordQueueSize": sum(
                1 for job_key in active_keys if job_key and job_key[0] == "data_flush"
            ),
            "previewQueueSize": sum(
                1 for job_key in active_keys if job_key and job_key[0] == "preview"
            ),
            "plotQueueSize": sum(
                1 for job_key in active_keys if job_key and job_key[0] == "window_plot"
            ),
        }

    def _shutdown_async_executors(self, *, wait: bool, cancel_pending: bool):
        with self.async_job_lock:
            if self.async_executors_shutdown:
                return
            self.async_executors_shutdown = True

        shutdown_kwargs = {"wait": wait}
        if cancel_pending:
            shutdown_kwargs["cancel_futures"] = True
        try:
            self.preview_executor.shutdown(**shutdown_kwargs)
        except TypeError:
            self.preview_executor.shutdown(wait=wait)
        try:
            self.output_executor.shutdown(**shutdown_kwargs)
        except TypeError:
            self.output_executor.shutdown(wait=wait)

    def _schedule_history_cleanup_if_needed(self):
        current_time = time.time()
        if current_time - self.last_cleanup_time < self._get_cleanup_interval_seconds():
            return
        self._submit_async_job(
            ("history_cleanup",),
            self.output_executor,
            self._cleanup_history_outputs_if_needed,
        )

    def _prepare_runtime(self):
        for required_path in (
            self.reference_image_path,
            self.grid_json_path,
            self.box_model_path,
            self.mouse_model_path,
        ):
            if required_path is None or not Path(required_path).exists():
                raise FileNotFoundError(f"mouse trajectory required file missing: {required_path}")

        grid_data, image_meta = parse_grid_json(Path(self.grid_json_path))
        self.solver = HeadlessCalibration(grid_data, image_meta)
        self.static_registration = parse_image_registration_json(self.registration_json_path)

        instrument_outer_img, self.instrument_polygon_img = parse_topdown_instrument_polygons(self.instrument_area_json_path)
        self.instrument_polygon_phys = map_topdown_polygon_to_physical(
            instrument_outer_img,
            self.instrument_polygon_img,
        )

        logger.info(f"loading mouse trajectory box model: {self.box_model_path}")
        self.box_model = self._build_model(self.box_model_path, task="segment")
        logger.info(f"loading mouse trajectory mouse model: {self.mouse_model_path}")
        self.mouse_model = self._build_model(self.mouse_model_path, task="detect")

        ref_result = run_yolo_single(
            self.box_model,
            Path(self.reference_image_path),
            self.imgsz,
            self.conf_box,
        )
        self.ref_corners = extract_box_corners(ref_result)
        if self.ref_corners is None:
            raise RuntimeError(f"could not detect reference box corners from {self.reference_image_path}")

    def _write_jpg_atomic(self, output_path: Path, image: Any) -> bool:
        ok, encoded = cv2.imencode(
            ".jpg",
            image,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(self.mouse_annotated_jpg_quality)],
        )
        if not ok:
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(
            f"{output_path.name}.{time.time_ns()}_{threading.get_ident()}.tmp"
        )
        with _OUTPUT_WRITE_LOCK:
            try:
                temp_path.write_bytes(encoded.tobytes())
                temp_path.replace(output_path)
            finally:
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except OSError:
                    pass
        return True

    @staticmethod
    def _write_text_atomic(output_path: Path, text: str, *, encoding: str = "utf-8"):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(
            f"{output_path.name}.{time.time_ns()}_{threading.get_ident()}.tmp"
        )
        with _OUTPUT_WRITE_LOCK:
            try:
                temp_path.write_text(text, encoding=encoding)
                temp_path.replace(output_path)
            finally:
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _save_csv_atomic(output_path: Path, rows: list[dict[str, Any]]):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(
            f"{output_path.name}.{time.time_ns()}_{threading.get_ident()}.tmp"
        )
        with _OUTPUT_WRITE_LOCK:
            try:
                save_csv(temp_path, rows)
                temp_path.replace(output_path)
            finally:
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except OSError:
                    pass

    def _build_processed_color_source_path(self, cage_number: int, timestamp: float) -> Path | None:
        try:
            camera_config = global_setting.get_setting("camera_config") or {}
            storage_config = camera_config.get("STORAGE", {}) if isinstance(camera_config, dict) else {}
            deep_config = camera_config.get("DEEP_CAMERA", {}) if isinstance(camera_config, dict) else {}

            fold_path = str(storage_config.get("fold_path", "./data/") or "./data/")
            base_dir = Path(fold_path)
            if not base_dir.is_absolute():
                base_dir = Path.cwd() / base_dir

            deep_path = str(deep_config.get("path", "deep_camera/") or "deep_camera/").strip("/\\")
            cage_prefix = str(deep_config.get("mouse_cage_prefix", "mouse_cage_") or "mouse_cage_")
            color_dir = str(deep_config.get("color_dir", "color") or "color").strip("/\\")
            file_name = f"{time_util.get_format_file_from_time(timestamp)}.jpg"
            return base_dir / deep_path / f"{cage_prefix}{int(cage_number)}" / color_dir / file_name
        except Exception as error:
            logger.debug(f"build processed color source path failed cage={cage_number}: {error}")
            return None

    def _delete_processed_color_source(self, source_path: Path | None, history_path: Path | None):
        # Color images are the chronological input for trajectory backfill.
        # Keep them here so unfinished windows can be processed later in order.
        return

    def _save_mouse_detection_images(
        self,
        cage_number: int,
        frame_id: int,
        timestamp: float,
        image_source: Path | Any,
        corners: BoxCorners | None,
        mouse_box: DetectionBox | None,
        solved: dict[str, Any] | None,
        status: str,
    ) -> tuple[Path | None, Path | None]:
        try:
            last_save_time = self.last_annotated_save_by_cage.get(cage_number, 0.0)
            if (
                self.annotated_save_interval_seconds > 0
                and timestamp - last_save_time < self.annotated_save_interval_seconds
            ):
                return self.latest_annotated_path_by_cage.get(cage_number), None

            image = render_annotation_image(image_source, corners, mouse_box, solved, status)
            if image is None:
                return None, None
            target_w, target_h = self.annotated_output_size
            if image.shape[1] != target_w or image.shape[0] != target_h:
                interpolation = cv2.INTER_AREA if image.shape[1] > target_w or image.shape[0] > target_h else cv2.INTER_LINEAR
                image = cv2.resize(image, (target_w, target_h), interpolation=interpolation)

            latest_dir = get_cage_annotated_latest_dir(cage_number)
            latest_path = latest_dir / "mouse_detection_latest.jpg"
            saved_latest = self._write_jpg_atomic(latest_path, image)

            history_dir = get_cage_annotated_history_dir(cage_number)
            timestamp_text = datetime.fromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            frame_id_text = f"{int(frame_id):08d}" if int(frame_id) > 0 else str(time.time_ns())
            prefix = "mouse_detected" if mouse_box is not None else "mouse_none"
            history_path = history_dir / f"{prefix}_{timestamp_text}_f{frame_id_text}.jpg"
            saved_history = self._write_jpg_atomic(history_path, image)
            if saved_latest:
                self.latest_annotated_path_by_cage[cage_number] = latest_path
            if saved_latest or saved_history:
                self.last_annotated_save_by_cage[cage_number] = timestamp

            return (
                latest_path if saved_latest else None,
                history_path if saved_history else None,
            )
        except Exception as error:
            logger.error(f"save mouse detection image failed cage={cage_number}: {error}")
            return None, None

    def _schedule_mouse_detection_images(
        self,
        cage_number: int,
        frame_id: int,
        timestamp: float,
        image_source: Path | Any,
        corners: BoxCorners | None,
        mouse_box: DetectionBox | None,
        solved: dict[str, Any] | None,
        status: str,
    ) -> tuple[Path | None, Path | None]:
        last_schedule_time = self.last_annotated_schedule_by_cage.get(cage_number, 0.0)
        if (
            self.annotated_save_interval_seconds > 0
            and timestamp - last_schedule_time < self.annotated_save_interval_seconds
        ):
            return self.latest_annotated_path_by_cage.get(cage_number), None

        submitted = self._submit_async_job(
            ("preview", int(cage_number)),
            self.preview_executor,
            self._save_mouse_detection_images,
            cage_number,
            frame_id,
            timestamp,
            image_source,
            corners,
            mouse_box,
            solved,
            status,
        )
        if submitted:
            self.last_annotated_schedule_by_cage[cage_number] = timestamp
        return self.latest_annotated_path_by_cage.get(cage_number), None

    def _process_frame_batch(self, frame_items: list[tuple[int, dict[str, Any]]]):
        if self.solver is None or self.box_model is None or self.mouse_model is None or self.ref_corners is None:
            return

        prepared_items: list[dict[str, Any]] = []
        mouse_sources: list[Any] = []
        mouse_source_indexes: list[int] = []

        for cage_number, frame_payload in frame_items:
            source_frame = self._load_payload_frame(frame_payload)
            if source_frame is None:
                self._mark_payload_processed(cage_number, frame_payload)
                continue

            frame_id = int(frame_payload.get("frame_id", 0) or 0)
            timestamp = float(frame_payload.get("timestamp", time.time()) or time.time())
            frame_version = self._frame_version(frame_payload)
            if frame_id > 0 and self._is_stale_frame_version(
                frame_version,
                self.last_processed_frame_versions.get(cage_number),
            ):
                self._mark_payload_processed(cage_number, frame_payload)
                continue
            if frame_id > 0:
                self.last_processed_frame_versions[cage_number] = frame_version

            processing_start_timestamp = time.time()
            processing_start_monotonic_ns = time.monotonic_ns()
            source_file_path = frame_payload.get("file_path") or frame_payload.get("image_path")
            frame_name = str(
                frame_payload.get("frame_name")
                or (Path(str(source_file_path)).name if source_file_path else "")
                or f"{timestamp:.6f}".replace(".", "_") + ".jpg"
            )
            image_file = Path(frame_name)
            window_index, window_start, window_end = self._get_window_info(cage_number, timestamp)

            rows = self.trajectory_rows.setdefault(cage_number, [])
            shift_log = self.shift_logs.setdefault(cage_number, [])
            frame_index = len(rows) + 1

            item = {
                "cage_number": cage_number,
                "source_frame": source_frame,
                "frame_id": frame_id,
                "timestamp": timestamp,
                "processing_start_timestamp": processing_start_timestamp,
                "processing_start_monotonic_ns": processing_start_monotonic_ns,
                "yolo_start_timestamp": None,
                "yolo_end_timestamp": None,
                "yolo_start_monotonic_ns": None,
                "yolo_end_monotonic_ns": None,
                "image_file": image_file,
                "window_index": window_index,
                "window_start": window_start,
                "window_end": window_end,
                "rows": rows,
                "shift_log": shift_log,
                "frame_index": frame_index,
                "corners": None,
                "corner_shift": None,
                "registration_mean_error": None,
                "registration_max_error": None,
                "registration_source": "",
                "h_test_to_ref": None,
                "status": "ok",
                "error": None,
                "mouse_result": None,
                "frame_payload": dict(frame_payload),
                "source_file_path": str(source_file_path or ""),
                "color_source_path": None,
            }

            try:
                corners = self.fixed_corners_by_cage.get(cage_number)
                if corners is None:
                    corners = self._load_fixed_corners_json(cage_number)
                if corners is None:
                    corners = self._detect_and_cache_fixed_corners(
                        cage_number=cage_number,
                        image_file=image_file,
                        frame_index=frame_index,
                        shift_log=shift_log,
                        source_frame=source_frame,
                    )
                    if corners is None:
                        item["status"] = "no_box_corners"
                else:
                    item["corner_shift"] = 0.0

                item["corners"] = corners
                h_test_to_ref = None
                registration_source = ""

                if corners is not None:
                    h_temp = CAL.get_perspective_transform(corners.corners, self.ref_corners.corners)
                    if h_temp:
                        h_test_to_ref = h_temp
                        registration_source = "dynamic_box"

                if h_test_to_ref is None and self.static_registration:
                    h_test_to_ref = self.static_registration.get("H_test_to_ref")
                    item["registration_mean_error"] = self.static_registration.get("meanError")
                    item["registration_max_error"] = self.static_registration.get("maxError")
                    registration_source = "image_registration_json"
                    if item["status"] in ("no_previous_mask", "registration_failed"):
                        item["status"] = "ok"

                item["h_test_to_ref"] = h_test_to_ref
                item["registration_source"] = registration_source
                if h_test_to_ref is None:
                    item["status"] = "registration_failed"
                else:
                    mouse_source_indexes.append(len(prepared_items))
                    mouse_sources.append(source_frame)
            except Exception as error:
                logger.error(f"mouse trajectory prepare frame failed cage={cage_number} file={image_file.name}: {error}")
                item["status"] = "error"
                item["error"] = str(error)

            prepared_items.append(item)

        if mouse_sources:
            yolo_start_timestamp = time.time()
            yolo_start_monotonic_ns = time.monotonic_ns()
            for source_index in mouse_source_indexes:
                prepared_items[source_index]["yolo_start_timestamp"] = yolo_start_timestamp
                prepared_items[source_index]["yolo_start_monotonic_ns"] = yolo_start_monotonic_ns
                prepared_items[source_index]["yolo_batch_size"] = len(mouse_sources)
            try:
                predict_start = time.perf_counter()
                mouse_results = run_yolo_batch(
                    self.mouse_model,
                    mouse_sources,
                    self.imgsz,
                    self.conf_mouse,
                    self.batch_size,
                )
                self._record_yolo_fps(len(mouse_sources), time.perf_counter() - predict_start)
                for source_index, mouse_result in zip(mouse_source_indexes, mouse_results):
                    prepared_items[source_index]["mouse_result"] = mouse_result
                if len(mouse_results) < len(mouse_source_indexes):
                    for source_index in mouse_source_indexes[len(mouse_results) :]:
                        prepared_items[source_index]["status"] = "error"
                        prepared_items[source_index]["error"] = "YOLO returned fewer batch results than input frames"
            except Exception as error:
                logger.warning(
                    f"mouse trajectory batch predict failed count={len(mouse_sources)}, "
                    f"fallback to single: {error}"
                )
                fallback_start = time.perf_counter()
                fallback_count = 0
                for source_index, mouse_source in zip(mouse_source_indexes, mouse_sources):
                    try:
                        prepared_items[source_index]["mouse_result"] = run_yolo_single(
                            self.mouse_model,
                            mouse_source,
                            self.imgsz,
                            self.conf_mouse,
                        )
                        fallback_count += 1
                    except Exception as single_error:
                        logger.error(
                            f"mouse trajectory single fallback failed "
                            f"cage={prepared_items[source_index].get('cage_number')} "
                            f"frame_id={prepared_items[source_index].get('frame_id')}: {single_error}"
                        )
                        prepared_items[source_index]["status"] = "error"
                        prepared_items[source_index]["error"] = str(single_error)
                self._record_yolo_fps(fallback_count, time.perf_counter() - fallback_start)
            finally:
                yolo_end_timestamp = time.time()
                yolo_end_monotonic_ns = time.monotonic_ns()
                for source_index in mouse_source_indexes:
                    prepared_items[source_index]["yolo_end_timestamp"] = yolo_end_timestamp
                    prepared_items[source_index]["yolo_end_monotonic_ns"] = yolo_end_monotonic_ns

        for item in prepared_items:
            self._finish_prepared_frame(item)

    def _record_yolo_fps(self, frame_count: int, elapsed_seconds: float):
        frame_count = int(frame_count)
        if frame_count <= 0 or elapsed_seconds <= 0:
            return
        instant_fps = frame_count / max(float(elapsed_seconds), 1e-6)
        if self.yolo_fps_ema <= 0:
            self.yolo_fps_ema = instant_fps
        else:
            self.yolo_fps_ema = self.yolo_fps_ema * 0.8 + instant_fps * 0.2

    def _record_processing_fps(self, frame_count: int, elapsed_seconds: float):
        frame_count = int(frame_count)
        if frame_count <= 0 or elapsed_seconds <= 0:
            return
        instant_fps = frame_count / max(float(elapsed_seconds), 1e-6)
        if self.processing_fps_ema <= 0:
            self.processing_fps_ema = instant_fps
        else:
            self.processing_fps_ema = (
                self.processing_fps_ema * 0.8 + instant_fps * 0.2
            )

    def get_recommended_submit_fps(self, active_cage_count: int, target_fps: float = 10.0) -> float:
        active_cage_count = max(int(active_cage_count), 1)
        target_fps = max(float(target_fps), 0.1)
        measured_total_fps = float(self.processing_fps_ema)
        if measured_total_fps <= 0:
            measured_total_fps = float(self.yolo_fps_ema)
        if measured_total_fps <= 0 and self.processed_frame_count > 0:
            elapsed = max(time.time() - self.processing_started_at, 0.001)
            measured_total_fps = self.processed_frame_count / elapsed
        if measured_total_fps <= 0:
            return target_fps

        usable_total_fps = measured_total_fps * float(self.yolo_fps_safety_factor)
        pending_pressure = 0.0
        if self.max_total_pending_frames > 0:
            pending_pressure = self._pending_count() / max(float(self.max_total_pending_frames), 1.0)
        if pending_pressure >= 0.75:
            usable_total_fps *= 0.5
        elif pending_pressure >= 0.5:
            usable_total_fps *= 0.75

        return max(0.1, min(target_fps, usable_total_fps / active_cage_count))

    def _finish_prepared_frame(self, item: dict[str, Any]):
        cage_number = int(item["cage_number"])
        frame_id = int(item["frame_id"])
        timestamp = float(item["timestamp"])
        image_file = item["image_file"]
        window_index = int(item["window_index"])
        window_start = float(item["window_start"])
        window_end = float(item["window_end"])
        rows = item["rows"]
        shift_log = item["shift_log"]
        frame_index = int(item["frame_index"])
        corners = item["corners"]
        corner_shift = item["corner_shift"]
        status = str(item["status"])
        mouse_box: DetectionBox | None = None
        solved: dict[str, Any] | None = None

        try:
            if item.get("error"):
                row = {
                    "frameIndex": frame_index,
                    "frameName": image_file.name,
                    "status": "error",
                    "error": str(item["error"]),
                }
                status = "error"
            else:
                mouse_result = item.get("mouse_result")
                if item.get("h_test_to_ref") is not None and mouse_result is not None:
                    mouse_box = best_box_from_result(mouse_result)
                    if mouse_box is None:
                        status = "no_mouse"
                    else:
                        self.solver.registration = {
                            "H_test_to_ref": item.get("h_test_to_ref"),
                            "meanError": item.get("registration_mean_error"),
                            "maxError": item.get("registration_max_error"),
                            "source": item.get("registration_source", ""),
                        }
                        solved = solve_mouse_location(self.solver, mouse_box, image_file.name)
                        if solved is not None:
                            solved["registrationSource"] = item.get("registration_source", "")
                        if solved is None:
                            status = "solve_failed"

                row = build_row(frame_index, image_file, status, corners, mouse_box, solved, corner_shift)
        except Exception as error:
            logger.error(f"mouse trajectory finish frame failed cage={cage_number} file={image_file.name}: {error}")
            row = {
                "frameIndex": frame_index,
                "frameName": image_file.name,
                "status": "error",
                "error": str(error),
            }
            status = "error"

        row["timestamp"] = timestamp
        row["datetime"] = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        row["frameId"] = frame_id
        frame_payload = item.get("frame_payload", {})
        row["cameraSessionId"] = int(frame_payload.get("camera_session_id", 0) or 0)
        row["frameSequence"] = int(
            frame_payload.get("frame_sequence", frame_id) or frame_id
        )
        submit_timestamp = float(
            frame_payload.get("submit_timestamp", timestamp) or timestamp
        )
        processing_start_timestamp = float(
            item.get("processing_start_timestamp", submit_timestamp) or submit_timestamp
        )
        yolo_start_timestamp = item.get("yolo_start_timestamp")
        yolo_end_timestamp = item.get("yolo_end_timestamp")
        capture_monotonic_ns = int(frame_payload.get("capture_monotonic_ns", 0) or 0)
        submit_monotonic_ns = int(frame_payload.get("submit_monotonic_ns", 0) or 0)
        processing_start_monotonic_ns = int(
            item.get("processing_start_monotonic_ns", 0) or 0
        )
        yolo_start_monotonic_ns = item.get("yolo_start_monotonic_ns")
        yolo_end_monotonic_ns = item.get("yolo_end_monotonic_ns")
        frame_age_reference = (
            float(yolo_start_timestamp)
            if yolo_start_timestamp is not None
            else processing_start_timestamp
        )
        row["captureTimestamp"] = timestamp
        row["submitTimestamp"] = submit_timestamp
        row["processingStartTimestamp"] = processing_start_timestamp
        row["yoloStartTimestamp"] = yolo_start_timestamp
        row["yoloEndTimestamp"] = yolo_end_timestamp
        row["captureMonotonicNs"] = capture_monotonic_ns or None
        row["submitMonotonicNs"] = submit_monotonic_ns or None
        row["processingStartMonotonicNs"] = processing_start_monotonic_ns or None
        row["yoloStartMonotonicNs"] = yolo_start_monotonic_ns
        row["yoloEndMonotonicNs"] = yolo_end_monotonic_ns
        row["frameAgeMs"] = (
            max(
                (int(yolo_start_monotonic_ns) - capture_monotonic_ns) / 1_000_000.0,
                0.0,
            )
            if capture_monotonic_ns > 0 and yolo_start_monotonic_ns is not None
            else max((frame_age_reference - timestamp) * 1000.0, 0.0)
        )
        row["queueWaitMs"] = (
            max(
                (processing_start_monotonic_ns - submit_monotonic_ns) / 1_000_000.0,
                0.0,
            )
            if submit_monotonic_ns > 0 and processing_start_monotonic_ns > 0
            else max((processing_start_timestamp - submit_timestamp) * 1000.0, 0.0)
        )
        row["inferenceLatencyMs"] = (
            max(
                (int(yolo_end_monotonic_ns) - int(yolo_start_monotonic_ns))
                / 1_000_000.0,
                0.0,
            )
            if yolo_start_monotonic_ns is not None and yolo_end_monotonic_ns is not None
            else (
                max(
                    (float(yolo_end_timestamp) - float(yolo_start_timestamp)) * 1000.0,
                    0.0,
                )
                if yolo_start_timestamp is not None and yolo_end_timestamp is not None
                else None
            )
        )
        row["yoloBatchSize"] = int(item.get("yolo_batch_size", 0) or 0)
        row["windowIndex"] = window_index
        row["windowStart"] = self._format_timestamp(window_start)
        row["windowEnd"] = self._format_timestamp(window_end)
        row["effectiveSubmitFps"] = item.get("frame_payload", {}).get("effective_submit_fps")
        row["effectiveYoloFps"] = self.yolo_fps_ema if self.yolo_fps_ema > 0 else None
        row["effectiveProcessingFps"] = (
            self.processing_fps_ema if self.processing_fps_ema > 0 else None
        )
        row["droppedFramesForCage"] = self.dropped_frame_count_by_cage.get(cage_number, 0)
        row["pendingFramesForCage"] = self._pending_count(cage_number)
        row["activeFramesForCage"] = self.get_pending_count(cage_number)
        row.update(self._get_async_queue_sizes())
        processed_count_for_cage = self.processed_frame_count_by_cage.get(cage_number, 0) + 1
        capture_duration = max(
            timestamp - self.first_timestamp_by_cage.get(cage_number, timestamp),
            0.0,
        )
        row["effectiveCageFps"] = (
            (processed_count_for_cage - 1) / capture_duration
            if processed_count_for_cage > 1 and capture_duration > 0
            else None
        )
        rows.append(row)
        self.processed_frame_count += 1
        self.processing_started_at_by_cage.setdefault(cage_number, time.time())
        self.processed_frame_count_by_cage[cage_number] = processed_count_for_cage
        stabilize_trajectory_rows([row])

        plot_paths = self._maybe_flush_outputs(
            cage_number=cage_number,
            image_file=image_file,
            rows=rows,
            shift_log=shift_log,
            timestamp=timestamp,
        )
        mouse_annotated_path, mouse_annotated_history_path = self._schedule_mouse_detection_images(
            cage_number=cage_number,
            frame_id=frame_id,
            timestamp=timestamp,
            image_source=item.get("source_frame"),
            corners=corners,
            mouse_box=mouse_box,
            solved=solved,
            status=status,
        )
        self._delete_processed_color_source(
            item.get("color_source_path"),
            mouse_annotated_history_path,
        )
        async_queue_sizes = self._get_async_queue_sizes()

        self.trajectory_ready.emit(
            {
                "cage_number": cage_number,
                "frame_name": image_file.name,
                "frame_id": frame_id,
                "status": status,
                "plot_paths": plot_paths,
                "plot_title": self.latest_plot_title_by_cage.get(
                    cage_number,
                    self._build_processing_title(cage_number, window_start, window_end),
                ),
                "pending_frames": self._pending_count(cage_number),
                "processed_frames": self.processed_frame_count,
                "processed_frames_for_cage": self.processed_frame_count_by_cage.get(cage_number, 0),
                "dropped_frames_for_cage": self.dropped_frame_count_by_cage.get(cage_number, 0),
                "total_dropped_frames": self.total_dropped_frame_count,
                "effective_yolo_fps": self.yolo_fps_ema,
                "effective_processing_fps": self.processing_fps_ema,
                "record_queue_size": async_queue_sizes["recordQueueSize"],
                "preview_queue_size": async_queue_sizes["previewQueueSize"],
                "plot_queue_size": async_queue_sizes["plotQueueSize"],
                "estimated_remaining_seconds": self._estimate_remaining_seconds(cage_number),
                "mouse_box": _serialize_detection_box(mouse_box),
                "corners": _serialize_corners(corners),
                "solved": solved,
                "mouse_annotated_path": str(mouse_annotated_path) if mouse_annotated_path else "",
                "mouse_annotated_history_path": str(mouse_annotated_history_path) if mouse_annotated_history_path else "",
            }
        )

    @staticmethod
    def _format_timestamp(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _parse_timestamp_text(timestamp_text: str) -> float | None:
        try:
            return datetime.strptime(timestamp_text, "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            return None

    def _get_window_info(self, cage_number: int, timestamp: float) -> tuple[int, float, float]:
        first_timestamp = self.first_timestamp_by_cage.setdefault(cage_number, timestamp)
        window_seconds = max(float(self.plot_window_seconds), 1.0)
        window_index = int(max(timestamp - first_timestamp, 0.0) // window_seconds)
        window_start = first_timestamp + window_index * window_seconds
        window_end = window_start + window_seconds
        return window_index, window_start, window_end

    def _build_processing_title(self, cage_number: int, window_start: float, window_end: float) -> str:
        return (
            f"轨迹绘制中 | 鼠笼{cage_number} | "
            f"{self._format_timestamp(window_start)} - {self._format_timestamp(window_end)}"
        )

    def _estimate_remaining_seconds(self, cage_number: int | None = None) -> float | None:
        if cage_number is None:
            elapsed = max(time.time() - self.processing_started_at, 0.001)
            processed_count = self.processed_frame_count
        else:
            elapsed = max(time.time() - self.processing_started_at_by_cage.get(cage_number, self.processing_started_at), 0.001)
            processed_count = self.processed_frame_count_by_cage.get(cage_number, 0)
        speed = processed_count / elapsed
        if speed <= 0:
            return None
        return self._pending_count(cage_number) / speed

    @staticmethod
    def _build_plot_paths_from_dir(plots_dir: Path) -> dict[str, str]:
        return {
            "xy_trajectory": str(plots_dir / "xy_trajectory.png"),
            "height_trajectory": str(plots_dir / "height_trajectory.png"),
            "occupancy_heatmap": str(plots_dir / "occupancy_heatmap.png"),
        }

    @staticmethod
    def _build_latest_plot_paths(cage_number: int) -> dict[str, str]:
        plots_dir = get_cage_plots_dir(cage_number)
        return {
            "xy_trajectory": str(plots_dir / "latest_xy_trajectory.png"),
            "height_trajectory": str(plots_dir / "latest_height_trajectory.png"),
            "occupancy_heatmap": str(plots_dir / "latest_occupancy_heatmap.png"),
        }

    def _publish_latest_plot_paths(self, cage_number: int, source_plot_paths: dict[str, str]) -> dict[str, str]:
        latest_plot_paths = self._build_latest_plot_paths(cage_number)
        for plot_key, source_path_text in source_plot_paths.items():
            source_path = Path(str(source_path_text))
            target_path = Path(latest_plot_paths.get(plot_key, ""))
            if not source_path.exists() or not target_path:
                continue
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = target_path.with_name(
                    f"{target_path.name}.{time.time_ns()}_{threading.get_ident()}.tmp"
                )
                with _OUTPUT_WRITE_LOCK:
                    try:
                        shutil.copyfile(source_path, temp_path)
                        temp_path.replace(target_path)
                    finally:
                        try:
                            if temp_path.exists():
                                temp_path.unlink()
                        except OSError:
                            pass
            except Exception as error:
                logger.error(
                    f"publish latest mouse trajectory plot failed: cage={cage_number}, "
                    f"key={plot_key}, source={source_path}, target={target_path}, reason={error}"
                )
        return latest_plot_paths

    def _save_outputs(
        self,
        cage_number: int,
        image_file: Path,
        export_dir: Path,
        rows: list[dict[str, Any]],
        shift_log: list[dict[str, Any]],
        *,
        plots_dir: Path | None = None,
        save_plot_files: bool = True,
    ) -> dict[str, str]:
        export_dir.mkdir(parents=True, exist_ok=True)
        if plots_dir is None:
            plots_dir = get_cage_plots_dir(cage_number)
        plots_dir.mkdir(parents=True, exist_ok=True)
        data_dir = get_cage_data_dir(cage_number)
        data_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_legacy_flat_files(export_dir)

        metadata = {
            "cageNumber": cage_number,
            "referenceImage": str(self.reference_image_path) if self.reference_image_path else "",
            "gridJson": str(self.grid_json_path) if self.grid_json_path else "",
            "boxWeight": str(self.box_model_path) if self.box_model_path else "",
            "mouseWeight": str(self.mouse_model_path) if self.mouse_model_path else "",
            "instrumentAreaJson": str(self.instrument_area_json_path) if self.instrument_area_json_path else "",
            "imageRegistrationJson": str(self.registration_json_path) if self.registration_json_path else "",
            "imageRegistration": self.static_registration,
            "frameCount": len(rows),
            "okCount": sum(1 for row in rows if row.get("status") == "ok"),
            "effectiveYoloFps": self.yolo_fps_ema,
            "effectiveProcessingFps": self.processing_fps_ema,
            "droppedFramesForCage": self.dropped_frame_count_by_cage.get(cage_number, 0),
            "totalDroppedFrames": self.total_dropped_frame_count,
            "maxPendingFramesPerCage": self.max_pending_frames_per_cage,
            "maxTotalPendingFrames": self.max_total_pending_frames,
            "annotatedOutputSize": list(self.annotated_output_size),
            **self._get_async_queue_sizes(),
        }

        self._save_csv_atomic(data_dir / "trajectory.csv", rows)
        self._write_text_atomic(
            data_dir / "trajectory.json",
            json.dumps({"metadata": metadata, "frames": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_text_atomic(
            data_dir / "box_shift_log.json",
            json.dumps({"thresholdPx": self.shift_threshold_px, "events": shift_log}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if self.instrument_polygon_phys:
            self._write_text_atomic(
                data_dir / "instrument_area.json",
                json.dumps(
                    {
                        "source": str(self.instrument_area_json_path) if self.instrument_area_json_path else "",
                        "imagePolygon": self.instrument_polygon_img,
                        "physicalPolygon": self.instrument_polygon_phys,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        if save_plot_files:
            save_plots(plots_dir, rows, self.instrument_polygon_phys)

        return self._build_plot_paths_from_dir(plots_dir)

    def _build_plot_paths(self, cage_number: int) -> dict[str, str]:
        plots_dir = get_cage_plots_dir(cage_number)
        return self._build_plot_paths_from_dir(plots_dir)

    def _get_window_plots_dir(self, cage_number: int, window_index: int, window_start: float, window_end: float) -> Path:
        start_text = datetime.fromtimestamp(window_start).strftime("%Y%m%d_%H%M%S")
        end_text = datetime.fromtimestamp(window_end).strftime("%H%M%S")
        plots_dir = get_cage_plots_dir(cage_number) / "windows" / f"window_{window_index:05d}_{start_text}_{end_text}"
        plots_dir.mkdir(parents=True, exist_ok=True)
        return plots_dir

    def _window_rows(self, rows: list[dict[str, Any]], window_index: int) -> list[dict[str, Any]]:
        return [row for row in rows if int(row.get("windowIndex", -1) or -1) == int(window_index)]

    def _save_window_plot(
        self,
        cage_number: int,
        image_file: Path,
        rows: list[dict[str, Any]],
        shift_log: list[dict[str, Any]],
        window_index: int,
        *,
        mark_final: bool = True,
    ) -> dict[str, str] | None:
        window_rows = self._window_rows(rows, window_index)
        if not window_rows:
            return None
        first_row = window_rows[0]
        window_start_text = str(first_row.get("windowStart", ""))
        window_end_text = str(first_row.get("windowEnd", ""))
        window_start = float(first_row.get("timestamp", time.time()) or time.time())
        parsed_window_start = self._parse_timestamp_text(window_start_text)
        if parsed_window_start is not None:
            window_start = parsed_window_start
        window_end = window_start + max(float(self.plot_window_seconds), 1.0)
        plots_dir = self._get_window_plots_dir(cage_number, window_index, window_start, window_end)
        plot_rows = [dict(row, frameIndex=index) for index, row in enumerate(window_rows, 1)]
        save_plots(plots_dir, plot_rows, self.instrument_polygon_phys)
        window_plot_paths = self._build_plot_paths_from_dir(plots_dir)
        plot_paths = self._publish_latest_plot_paths(cage_number, window_plot_paths)
        logger.info(
            f"mouse trajectory window plot saved: cage={cage_number}, "
            f"window={window_index}, final={mark_final}, dir={plots_dir}, latest={plot_paths}"
        )
        title_suffix = "轨迹区间" if mark_final else "轨迹区间生成中"
        title = f"{window_start_text} - {window_end_text} | {title_suffix}"
        self.latest_plot_paths[cage_number] = plot_paths
        self.latest_plot_title_by_cage[cage_number] = title
        if mark_final:
            self.last_plotted_window_by_cage[cage_number] = window_index
        return plot_paths

    def _save_total_plot(
        self,
        cage_number: int,
        image_file: Path,
        rows: list[dict[str, Any]],
        shift_log: list[dict[str, Any]],
    ) -> dict[str, str]:
        plots_dir = get_cage_plots_dir(cage_number) / "total"
        plot_paths = self._save_outputs(
            cage_number=cage_number,
            image_file=image_file,
            export_dir=get_cage_export_dir(cage_number),
            rows=rows,
            shift_log=shift_log,
            plots_dir=plots_dir,
            save_plot_files=True,
        )
        plot_paths = self._publish_latest_plot_paths(cage_number, plot_paths)
        first_time = rows[0].get("datetime", "") if rows else ""
        last_time = rows[-1].get("datetime", "") if rows else ""
        self.latest_plot_paths[cage_number] = plot_paths
        logger.info(
            f"mouse trajectory total plot saved: cage={cage_number}, "
            f"dir={plots_dir}"
        )
        self.latest_plot_title_by_cage[cage_number] = f"{first_time} - {last_time} | 完整轨迹"
        return plot_paths

    def _maybe_flush_outputs(
        self,
        cage_number: int,
        image_file: Path,
        rows: list[dict[str, Any]],
        shift_log: list[dict[str, Any]],
        timestamp: float,
    ) -> dict[str, str]:
        last_flush_time = self.last_output_flush_by_cage.get(cage_number, 0.0)
        latest_plot_paths = self.latest_plot_paths.get(cage_number, {})

        current_window_index = int(rows[-1].get("windowIndex", 0) or 0) if rows else 0
        last_plotted_window = self.last_plotted_window_by_cage.get(cage_number, -1)
        if current_window_index > last_plotted_window:
            window_index = last_plotted_window + 1
            if window_index < current_window_index:
                rows_snapshot = [dict(row) for row in rows]
                shift_log_snapshot = [dict(event) for event in shift_log]
                self._submit_async_job(
                    ("window_plot", int(cage_number)),
                    self.output_executor,
                    self._save_window_plot,
                    cage_number,
                    image_file,
                    rows_snapshot,
                    shift_log_snapshot,
                    window_index,
                )

        should_flush_data = len(rows) <= 1 or (timestamp - last_flush_time) >= self.output_flush_interval_seconds
        if should_flush_data:
            rows_snapshot = [dict(row) for row in rows]
            shift_log_snapshot = [dict(event) for event in shift_log]
            submitted = self._submit_async_job(
                ("data_flush", int(cage_number)),
                self.output_executor,
                self._save_outputs,
                cage_number,
                image_file,
                get_cage_export_dir(cage_number),
                rows_snapshot,
                shift_log_snapshot,
                save_plot_files=False,
            )
            if submitted:
                self.last_output_flush_by_cage[cage_number] = timestamp

        return latest_plot_paths

    def _flush_all_outputs(self, final: bool = False):
        for cage_number, rows in list(self.trajectory_rows.items()):
            if not rows:
                continue
            image_file = Path(str(rows[-1].get("frameName", "trajectory_frame")))
            shift_log = self.shift_logs.setdefault(cage_number, [])
            self._save_outputs(
                cage_number=cage_number,
                image_file=image_file,
                export_dir=get_cage_export_dir(cage_number),
                rows=rows,
                shift_log=shift_log,
                save_plot_files=False,
            )
            if final:
                current_window_index = int(rows[-1].get("windowIndex", 0) or 0)
                last_plotted_window = self.last_plotted_window_by_cage.get(cage_number, -1)
                for window_index in range(last_plotted_window + 1, current_window_index + 1):
                    self._save_window_plot(
                        cage_number=cage_number,
                        image_file=image_file,
                        rows=rows,
                        shift_log=shift_log,
                        window_index=window_index,
                    )
                plot_paths = self._save_total_plot(
                    cage_number=cage_number,
                    image_file=image_file,
                    rows=rows,
                    shift_log=shift_log,
                )
                self.trajectory_ready.emit(
                    {
                        "cage_number": cage_number,
                        "frame_name": image_file.name,
                        "frame_id": int(rows[-1].get("frameIndex", 0) or 0),
                        "status": "final_done",
                        "plot_paths": plot_paths,
                        "plot_title": self.latest_plot_title_by_cage.get(cage_number, "完整轨迹"),
                        "pending_frames": self._pending_count(cage_number),
                        "processed_frames": self.processed_frame_count,
                        "processed_frames_for_cage": self.processed_frame_count_by_cage.get(cage_number, 0),
                        "dropped_frames_for_cage": self.dropped_frame_count_by_cage.get(cage_number, 0),
                        "total_dropped_frames": self.total_dropped_frame_count,
                        "effective_yolo_fps": self.yolo_fps_ema,
                        "effective_processing_fps": self.processing_fps_ema,
                        "record_queue_size": self._get_async_queue_sizes()["recordQueueSize"],
                        "preview_queue_size": self._get_async_queue_sizes()["previewQueueSize"],
                        "plot_queue_size": self._get_async_queue_sizes()["plotQueueSize"],
                        "estimated_remaining_seconds": self._estimate_remaining_seconds(cage_number),
                        "mouse_box": None,
                        "corners": self.fixed_corners_by_cage.get(cage_number).corners if cage_number in self.fixed_corners_by_cage else None,
                        "solved": None,
                    }
                )

    def _detect_and_cache_fixed_corners(
        self,
        cage_number: int,
        image_file: Path,
        frame_index: int,
        shift_log: list[dict[str, Any]],
        source_frame: Any = None,
    ) -> BoxCorners | None:
        box_source = image_file if source_frame is None else source_frame
        box_result = run_yolo_single(self.box_model, box_source, self.imgsz, self.conf_box)
        corners = extract_box_corners(box_result)
        previous_corners = self.previous_corners_by_cage.get(cage_number, list(self.ref_corners.corners))

        if corners is None:
            if previous_corners is None:
                return None
            corners = BoxCorners(
                [dict(point) for point in previous_corners],
                0.0,
                "previous_mask",
            )
        else:
            if previous_corners is not None:
                corner_shift = mean_corner_distance(corners.corners, previous_corners)
                if corner_shift > self.shift_threshold_px:
                    shift_log.append(
                        {
                            "frameIndex": frame_index,
                            "frameName": image_file.name,
                            "meanShiftPx": corner_shift,
                            "thresholdPx": self.shift_threshold_px,
                            "corners": [[point["x"], point["y"]] for point in corners.corners],
                        }
                    )

        fixed_corners = BoxCorners(
            [dict(point) for point in corners.corners],
            corners.conf,
            f"fixed_{corners.source}_json",
        )
        self.fixed_corners_by_cage[cage_number] = fixed_corners
        self.previous_corners_by_cage[cage_number] = [dict(point) for point in corners.corners]
        self._save_fixed_corners_json(cage_number, image_file, fixed_corners)
        return fixed_corners

    def _save_fixed_corners_json(self, cage_number: int, image_file: Path, corners: BoxCorners):
        data_dir = get_cage_data_dir(cage_number)
        self._write_text_atomic(
            data_dir / "fixed_box_corners.json",
            json.dumps(
                {
                    "schemaVersion": 2,
                    "cageNumber": cage_number,
                    "frameName": image_file.name,
                    "sourceImage": str(image_file),
                    "source": corners.source,
                    "confidence": corners.conf,
                    "corners": corners.corners,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load_fixed_corners_json(self, cage_number: int) -> BoxCorners | None:
        json_path = get_cage_data_dir(cage_number) / "fixed_box_corners.json"
        if not json_path.exists():
            return None

        try:
            json_data = json.loads(json_path.read_text(encoding="utf-8"))
            schema_version = int(json_data.get("schemaVersion", 1) or 1)
            source = str(json_data.get("source", "fixed_box_json") or "fixed_box_json")
            # Legacy cache files were generated from mask->minAreaRect and should be re-detected.
            if schema_version < 2 or source == "fixed_box_json":
                return None
            corners = BoxCorners(
                [dict(point) for point in json_data.get("corners", [])],
                float(json_data.get("confidence", 0.0) or 0.0),
                source,
            )
            if len(corners.corners) != 4:
                return None
            self.fixed_corners_by_cage[cage_number] = corners
            return corners
        except Exception as error:
            logger.error(f"load fixed box corners failed cage={cage_number}: {error}")
            return None

    def _get_cleanup_interval_seconds(self) -> float:
        return max(float(self.annotated_history_cleanup_interval_seconds), 1.0)

    def _cleanup_history_outputs_if_needed(self):
        current_time = time.time()
        if current_time - self.last_cleanup_time < self._get_cleanup_interval_seconds():
            return

        try:
            if not EXPORT_DIR.exists():
                self.last_cleanup_time = current_time
                return

            retention_seconds = float(self.annotated_history_retention_seconds)
            if retention_seconds <= 0:
                self.last_cleanup_time = current_time
                return

            cutoff_time = current_time - retention_seconds
            deleted_count = 0
            for cage_dir in EXPORT_DIR.glob("cage_*"):
                history_dir = cage_dir / "annotated" / "history"
                if not history_dir.exists():
                    continue
                for file_path in history_dir.iterdir():
                    if not file_path.is_file():
                        continue
                    if file_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                        continue
                    try:
                        if file_path.stat().st_mtime >= cutoff_time:
                            continue
                        file_path.unlink()
                        deleted_count += 1
                    except Exception as error:
                        logger.error(f"delete mouse trajectory history file failed: {file_path}, reason: {error}")

            if deleted_count:
                logger.info(
                    f"mouse_trajectory cleanup finished, "
                    f"retention_seconds={retention_seconds}, deleted_history_files={deleted_count}"
                )
        finally:
            self.last_cleanup_time = current_time

    @staticmethod
    def _cleanup_legacy_flat_files(export_dir: Path):
        legacy_file_names = [
            "annotated_latest.png",
            "box_shift_log.json",
            "fixed_box_corners.json",
            "height_trajectory.png",
            "instrument_area.json",
            "occupancy_heatmap.png",
            "trajectory.csv",
            "trajectory.json",
            "trajectory_latest.csv",
            "trajectory_latest.json",
            "trajectory_latest.png",
            "xy_trajectory.png",
        ]
        for file_name in legacy_file_names:
            file_path = export_dir / file_name
            if not file_path.exists():
                continue
            try:
                file_path.unlink()
            except Exception as error:
                logger.error(f"delete legacy mouse trajectory file failed: {file_path}, reason: {error}")

        legacy_annotated_dir = export_dir / "annotated"
        if legacy_annotated_dir.exists():
            for file_path in legacy_annotated_dir.iterdir():
                if not file_path.is_file():
                    continue
                try:
                    file_path.unlink()
                except Exception as error:
                    logger.error(f"delete legacy mouse trajectory annotated file failed: {file_path}, reason: {error}")
