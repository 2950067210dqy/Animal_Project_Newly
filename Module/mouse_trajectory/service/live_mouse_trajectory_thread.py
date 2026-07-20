import json
import time
from pathlib import Path
from typing import Any

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
    run_yolo_single,
    save_csv,
    save_plots,
    solve_mouse_location,
    stabilize_trajectory_rows,
)
from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread


def _serialize_detection_box(mouse_box: DetectionBox | None) -> dict[str, Any] | None:
    if mouse_box is None:
        return None
    return {
        "xyxy": [float(value) for value in mouse_box.xyxy],
        "conf": float(mouse_box.conf),
        "cls": float(mouse_box.cls),
    }


def _serialize_corners(corners: BoxCorners | None) -> dict[str, Any] | None:
    if corners is None:
        return None
    return {
        "corners": [dict(point) for point in corners.corners],
        "conf": float(corners.conf),
        "source": corners.source,
    }


class MouseTrajectoryThread(MyQThread):
    trajectory_ready = pyqtSignal(dict)

    def __init__(self):
        super().__init__(name="mouse_trajectory_thread")
        self.pending_frames: dict[int, dict[str, Any]] = {}
        self.last_processed_frame_ids: dict[int, int] = {}
        self.fixed_corners_by_cage: dict[int, BoxCorners] = {}
        self.previous_corners_by_cage: dict[int, list[dict[str, Any]]] = {}
        self.trajectory_rows: dict[int, list[dict[str, Any]]] = {}
        self.shift_logs: dict[int, list[dict[str, Any]]] = {}
        self.latest_plot_paths: dict[int, dict[str, str]] = {}
        self.last_output_flush_by_cage: dict[int, float] = {}

        self.reference_image_path = DEFAULT_REFERENCE_IMAGE_PATH
        self.grid_json_path = DEFAULT_GRID_JSON_PATH
        self.registration_json_path = DEFAULT_IMAGE_REGISTRATION_JSON_PATH
        self.instrument_area_json_path = DEFAULT_INSTRUMENT_AREA_JSON_PATH
        self.box_model_path = DEFAULT_BOX_MODEL_PATH
        self.mouse_model_path = DEFAULT_MOUSE_MODEL_PATH

        self.conf_box = 0.4
        self.conf_mouse = 0.4
        self.imgsz = 640
        self.shift_threshold_px = 10.0
        self.output_flush_interval_seconds = 3.0

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

    def before_Runing_work(self):
        self._prepare_runtime()

    def submit_frame(self, cage_number: int, frame_payload: dict[str, Any]):
        if not frame_payload or frame_payload.get("frame") is None:
            return
        self.pending_frames[int(cage_number)] = frame_payload

    def submit_frames(self, cage_frame_map: dict[int, dict[str, Any]]):
        for cage_number, frame_payload in cage_frame_map.items():
            self.submit_frame(cage_number, frame_payload)

    def dosomething(self):
        self._cleanup_history_outputs_if_needed()
        if not self.pending_frames:
            time.sleep(0.03)
            return

        cage_number = next(iter(self.pending_frames.keys()))
        frame_payload = self.pending_frames.pop(cage_number)
        self._process_frame(cage_number, frame_payload)

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

    def _process_frame(self, cage_number: int, frame_payload: dict[str, Any]):
        if self.solver is None or self.box_model is None or self.mouse_model is None or self.ref_corners is None:
            return

        source_frame = frame_payload.get("frame")
        if source_frame is None:
            return

        frame_id = int(frame_payload.get("frame_id", 0) or 0)
        if frame_id > 0 and self.last_processed_frame_ids.get(cage_number) == frame_id:
            return
        if frame_id > 0:
            self.last_processed_frame_ids[cage_number] = frame_id

        timestamp = float(frame_payload.get("timestamp", time.time()) or time.time())
        frame_name = str(frame_payload.get("frame_name") or f"{timestamp:.6f}".replace(".", "_") + ".bmp")
        image_file = Path(frame_name)

        rows = self.trajectory_rows.setdefault(cage_number, [])
        shift_log = self.shift_logs.setdefault(cage_number, [])
        frame_index = len(rows) + 1

        corners: BoxCorners | None = None
        mouse_box: DetectionBox | None = None
        solved: dict[str, Any] | None = None
        corner_shift: float | None = None
        status = "ok"

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
                    status = "no_box_corners"
            else:
                corner_shift = 0.0

            registration_mean_error = None
            registration_max_error = None
            registration_source = ""
            h_test_to_ref = None

            if corners is not None:
                h_temp = CAL.get_perspective_transform(corners.corners, self.ref_corners.corners)
                if h_temp:
                    h_test_to_ref = h_temp
                    registration_source = "dynamic_box"

            if h_test_to_ref is None and self.static_registration:
                h_test_to_ref = self.static_registration.get("H_test_to_ref")
                registration_mean_error = self.static_registration.get("meanError")
                registration_max_error = self.static_registration.get("maxError")
                registration_source = "image_registration_json"
                if status in ("no_previous_mask", "registration_failed"):
                    status = "ok"

            if h_test_to_ref is None:
                status = "registration_failed"
            else:
                mouse_result = run_yolo_single(self.mouse_model, source_frame, self.imgsz, self.conf_mouse)
                mouse_box = best_box_from_result(mouse_result)
                if mouse_box is None:
                    status = "no_mouse"
                else:
                    self.solver.registration = {
                        "H_test_to_ref": h_test_to_ref,
                        "meanError": registration_mean_error,
                        "maxError": registration_max_error,
                        "source": registration_source,
                    }
                    solved = solve_mouse_location(self.solver, mouse_box, image_file.name)
                    if solved is not None:
                        solved["registrationSource"] = registration_source
                    if solved is None:
                        status = "solve_failed"

            row = build_row(frame_index, image_file, status, corners, mouse_box, solved, corner_shift)
        except Exception as error:
            logger.error(f"mouse trajectory process frame failed cage={cage_number} file={image_file.name}: {error}")
            row = {
                "frameIndex": frame_index,
                "frameName": image_file.name,
                "status": "error",
                "error": str(error),
            }
            status = "error"

        rows.append(row)
        stabilize_trajectory_rows(rows)

        plot_paths = self._maybe_flush_outputs(
            cage_number=cage_number,
            image_file=image_file,
            rows=rows,
            shift_log=shift_log,
            timestamp=timestamp,
        )

        self.trajectory_ready.emit(
            {
                "cage_number": cage_number,
                "frame_name": image_file.name,
                "frame_id": frame_id,
                "status": status,
                "plot_paths": plot_paths,
                "mouse_box": _serialize_detection_box(mouse_box),
                "corners": _serialize_corners(corners),
                "solved": dict(solved) if solved else None,
            }
        )

    def _save_outputs(
        self,
        cage_number: int,
        image_file: Path,
        export_dir: Path,
        rows: list[dict[str, Any]],
        shift_log: list[dict[str, Any]],
    ) -> dict[str, str]:
        export_dir.mkdir(parents=True, exist_ok=True)
        plots_dir = get_cage_plots_dir(cage_number)
        data_dir = get_cage_data_dir(cage_number)
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
        }

        save_csv(data_dir / "trajectory.csv", rows)
        (data_dir / "trajectory.json").write_text(
            json.dumps({"metadata": metadata, "frames": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "box_shift_log.json").write_text(
            json.dumps({"thresholdPx": self.shift_threshold_px, "events": shift_log}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if self.instrument_polygon_phys:
            (data_dir / "instrument_area.json").write_text(
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

        save_plots(plots_dir, rows, self.instrument_polygon_phys)

        return {
            "xy_trajectory": str(plots_dir / "xy_trajectory.png"),
            "height_trajectory": str(plots_dir / "height_trajectory.png"),
            "occupancy_heatmap": str(plots_dir / "occupancy_heatmap.png"),
        }

    def _build_plot_paths(self, cage_number: int) -> dict[str, str]:
        plots_dir = get_cage_plots_dir(cage_number)
        return {
            "xy_trajectory": str(plots_dir / "xy_trajectory.png"),
            "height_trajectory": str(plots_dir / "height_trajectory.png"),
            "occupancy_heatmap": str(plots_dir / "occupancy_heatmap.png"),
        }

    def _maybe_flush_outputs(
        self,
        cage_number: int,
        image_file: Path,
        rows: list[dict[str, Any]],
        shift_log: list[dict[str, Any]],
        timestamp: float,
    ) -> dict[str, str]:
        last_flush_time = self.last_output_flush_by_cage.get(cage_number, 0.0)
        expected_plot_paths = self._build_plot_paths(cage_number)
        should_flush = (
            cage_number not in self.latest_plot_paths
            or len(rows) <= 1
            or (timestamp - last_flush_time) >= self.output_flush_interval_seconds
        )
        if not should_flush:
            return self.latest_plot_paths.get(cage_number, expected_plot_paths)

        plot_paths = self._save_outputs(
            cage_number=cage_number,
            image_file=image_file,
            export_dir=get_cage_export_dir(cage_number),
            rows=rows,
            shift_log=shift_log,
        )
        self.latest_plot_paths[cage_number] = plot_paths
        self.last_output_flush_by_cage[cage_number] = timestamp
        return plot_paths

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
        (data_dir / "fixed_box_corners.json").write_text(
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
        try:
            camera_config = global_setting.get_setting("camera_config")
            return float(camera_config["DELETE"]["interval_seconds"])
        except Exception:
            return 1800.0

    def _cleanup_history_outputs_if_needed(self):
        current_time = time.time()
        if current_time - self.last_cleanup_time < self._get_cleanup_interval_seconds():
            return

        try:
            if not EXPORT_DIR.exists():
                self.last_cleanup_time = current_time
                return

            deleted_count = 0
            for cage_dir in EXPORT_DIR.glob("cage_*"):
                history_dir = cage_dir / "annotated" / "history"
                if not history_dir.exists():
                    continue
                for file_path in history_dir.iterdir():
                    if not file_path.is_file():
                        continue
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception as error:
                        logger.error(f"delete mouse trajectory history file failed: {file_path}, reason: {error}")

            logger.info(f"mouse_trajectory cleanup finished, deleted_history_files={deleted_count}")
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
