from __future__ import annotations

import configparser
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median
from typing import Iterable, Mapping, Optional, Sequence

try:
    from loguru import logger
except ImportError:  # Allows the postprocessor to run in lightweight export tools.
    import logging

    logger = logging.getLogger(__name__)


CAGE_HEADER = "鼠笼号"
WEIGHT_HEADER = "称重重量测量值(g)"
TIME_HEADER = "获取时间"
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "monitor_datas_config.ini"
)


@dataclass(frozen=True)
class WeightPostprocessConfig:
    enabled: bool = True
    event_window_points: int = 15
    minimum_group_points: int = 5
    minimum_body_weight_g: float = 5.0
    maximum_body_weight_g: float = 80.0
    initial_weight_match_ratio: float = 0.20
    initial_weight_match_min_g: float = 2.0
    event_outlier_ratio: float = 0.05
    event_outlier_min_g: float = 1.0
    first_event_match_ratio: float = 0.05
    first_event_match_min_g: float = 1.0
    weight_change_period_hours: float = 24.0
    weight_change_ratio_per_period: float = 0.05
    weight_change_min_g: float = 1.0
    decimal_places: int = 3
    output_suffix: str = "_称重拟合"


@dataclass(frozen=True)
class WeightPostprocessResult:
    success: bool
    output_path: Optional[str] = None
    processed_sheets: int = 0
    processed_cages: int = 0
    skipped_cages: int = 0
    warnings: tuple[str, ...] = ()
    error: str = ""

    @property
    def summary(self) -> str:
        if not self.success:
            return self.error or "称重后处理失败"
        if self.output_path is None:
            return self.warnings[0] if self.warnings else "称重后处理未启用"
        return (
            f"称重拟合完成：{self.processed_sheets} 个工作表，"
            f"{self.processed_cages} 个笼子"
            + (f"，{self.skipped_cages} 个笼子保留原值" if self.skipped_cages else "")
        )


@dataclass(frozen=True)
class _WeightEvent:
    position: int
    weight: float
    timestamp: Optional[float]


@dataclass(frozen=True)
class _BaselineMatch:
    baseline: float
    first_high_index: int


def load_weight_postprocess_config(
        config_path: Optional[os.PathLike | str] = None,
) -> WeightPostprocessConfig:
    parser = configparser.ConfigParser(interpolation=None)
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    if path.is_file():
        parser.read(path, encoding="utf-8-sig")

    section = "WEIGHT_POSTPROCESS"
    get = lambda key, fallback: parser.get(section, key, fallback=fallback)
    get_int = lambda key, fallback: parser.getint(section, key, fallback=fallback)
    get_float = lambda key, fallback: parser.getfloat(section, key, fallback=fallback)
    get_bool = lambda key, fallback: parser.getboolean(section, key, fallback=fallback)

    config = WeightPostprocessConfig(
        enabled=get_bool("enabled", True),
        event_window_points=max(2, get_int("event_window_points", 15)),
        minimum_group_points=max(1, get_int("minimum_group_points", 5)),
        minimum_body_weight_g=max(0.0, get_float("minimum_body_weight_g", 5.0)),
        maximum_body_weight_g=max(0.0, get_float("maximum_body_weight_g", 80.0)),
        initial_weight_match_ratio=max(
            0.0, get_float("initial_weight_match_ratio", 0.20)
        ),
        initial_weight_match_min_g=max(
            0.0, get_float("initial_weight_match_min_g", 2.0)
        ),
        event_outlier_ratio=max(0.0, get_float("event_outlier_ratio", 0.05)),
        event_outlier_min_g=max(0.0, get_float("event_outlier_min_g", 1.0)),
        first_event_match_ratio=max(
            0.0, get_float("first_event_match_ratio", 0.05)
        ),
        first_event_match_min_g=max(
            0.0, get_float("first_event_match_min_g", 1.0)
        ),
        weight_change_period_hours=max(
            0.1, get_float("weight_change_period_hours", 24.0)
        ),
        weight_change_ratio_per_period=max(
            0.0, get_float("weight_change_ratio_per_period", 0.05)
        ),
        weight_change_min_g=max(0.0, get_float("weight_change_min_g", 1.0)),
        decimal_places=max(0, get_int("decimal_places", 3)),
        output_suffix=get("output_suffix", "_称重拟合").strip() or "_称重拟合",
    )
    if config.maximum_body_weight_g <= config.minimum_body_weight_g:
        raise ValueError("maximum_body_weight_g must be greater than minimum_body_weight_g")
    if config.minimum_group_points * 2 > config.event_window_points:
        raise ValueError("minimum_group_points cannot exceed half of event_window_points")
    return config


def _to_finite_float(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"none", "null", "nan"}:
            return None
        value = stripped
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _to_timestamp(value) -> Optional[float]:
    """Convert Excel/SQLite time values to seconds for time-window fitting."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).timestamp()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.timestamp()
    return _to_finite_float(value)


def _tolerance(reference: float, ratio: float, minimum_g: float) -> float:
    return max(minimum_g, abs(reference) * ratio)


def _time_adjusted_tolerance(
        reference_weight: float,
        previous_timestamp: Optional[float],
        current_timestamp: Optional[float],
        config: WeightPostprocessConfig,
) -> float:
    """Allow gradual biological change only when elapsed time supports it."""
    if previous_timestamp is None or current_timestamp is None:
        return config.weight_change_min_g
    elapsed_seconds = max(0.0, current_timestamp - previous_timestamp)
    elapsed_periods = elapsed_seconds / (config.weight_change_period_hours * 3600.0)
    return _tolerance(
        reference_weight,
        config.weight_change_ratio_per_period * elapsed_periods,
        config.weight_change_min_g,
    )


def _robust_group_level(
        group: Sequence[tuple[int, float]],
        config: WeightPostprocessConfig,
) -> Optional[float]:
    values = [value for _, value in group]
    center = float(median(values))
    tolerance = _tolerance(
        center,
        config.event_outlier_ratio,
        config.event_outlier_min_g,
    )
    inliers = [value for value in values if abs(value - center) <= tolerance]
    if len(inliers) < config.minimum_group_points:
        return None
    return float(mean(inliers))


def _find_initial_baseline(
        values: Sequence[Optional[float]],
        initial_weight: float,
        config: WeightPostprocessConfig,
) -> Optional[_BaselineMatch]:
    """Use the first valid 15-point low/high split that agrees with manual weight."""
    valid_buffer: list[tuple[int, float]] = []
    initial_tolerance = _tolerance(
        initial_weight,
        config.initial_weight_match_ratio,
        config.initial_weight_match_min_g,
    )
    for index, value in enumerate(values):
        if value is None:
            continue
        valid_buffer.append((index, value))
        if len(valid_buffer) > config.event_window_points:
            valid_buffer.pop(0)
        if len(valid_buffer) < config.event_window_points:
            continue

        ranked = sorted(valid_buffer, key=lambda item: item[1])
        candidates: list[tuple[float, float, int]] = []
        minimum_split = config.minimum_group_points
        maximum_split = config.event_window_points - config.minimum_group_points
        for split in range(minimum_split, maximum_split + 1):
            low_group = ranked[:split]
            high_group = ranked[split:]
            low_level = _robust_group_level(low_group, config)
            high_level = _robust_group_level(high_group, config)
            if low_level is None or high_level is None:
                continue
            candidate_weight = high_level - low_level
            if not (
                    config.minimum_body_weight_g
                    <= candidate_weight
                    <= config.maximum_body_weight_g
            ):
                continue
            low_position = float(median(position for position, _ in low_group))
            high_position = float(median(position for position, _ in high_group))
            if high_position <= low_position:
                continue
            candidates.append(
                (
                    abs(candidate_weight - initial_weight),
                    low_level,
                    min(position for position, _ in high_group),
                )
            )

        if candidates:
            difference, baseline, first_high_index = min(candidates, key=lambda item: item[0])
            if difference <= initial_tolerance:
                return _BaselineMatch(baseline, first_high_index)
    return None


def _event_window(
        values: Sequence[Optional[float]],
        start: int,
        baseline: float,
        config: WeightPostprocessConfig,
) -> tuple[list[tuple[int, float]], int]:
    """Read one event from valid samples; gaps do not count as data points."""
    window: list[tuple[int, float]] = []
    cursor = start
    while cursor < len(values) and len(window) < config.event_window_points:
        value = values[cursor]
        if value is not None:
            window.append((cursor, value - baseline))
        cursor += 1
    return window, cursor


def _event_weight(
        window: Sequence[tuple[int, float]],
        config: WeightPostprocessConfig,
) -> Optional[float]:
    high_values = [
        value
        for _, value in window
        if config.minimum_body_weight_g <= value <= config.maximum_body_weight_g
    ]
    if len(high_values) < config.minimum_group_points:
        return None

    center = float(median(high_values))
    point_tolerance = _tolerance(
        center,
        config.event_outlier_ratio,
        config.event_outlier_min_g,
    )
    inliers = [value for value in high_values if abs(value - center) <= point_tolerance]
    if len(inliers) < config.minimum_group_points:
        return None
    return float(median(inliers))


def _confirm_weight_events(
        values: Sequence[Optional[float]],
        initial_weight: float,
        baseline_match: _BaselineMatch,
        config: WeightPostprocessConfig,
        timestamps: Optional[Sequence[float]] = None,
) -> list[_WeightEvent]:
    events: list[_WeightEvent] = []
    last_weight = initial_weight
    last_event_timestamp: Optional[float] = None
    index = baseline_match.first_high_index
    waiting_for_empty_return = False

    while index < len(values):
        value = values[index]
        if value is None:
            index += 1
            continue
        candidate_weight = value - baseline_match.baseline

        if waiting_for_empty_return:
            if candidate_weight < config.minimum_body_weight_g:
                waiting_for_empty_return = False
            index += 1
            continue
        if not (
                config.minimum_body_weight_g
                <= candidate_weight
                <= config.maximum_body_weight_g
        ):
            index += 1
            continue

        window, cursor = _event_window(values, index, baseline_match.baseline, config)
        event_weight = _event_weight(window, config)
        if event_weight is not None:
            event_position = window[-1][0]
            event_timestamp = (
                timestamps[event_position]
                if timestamps is not None and event_position < len(timestamps)
                else None
            )
            if not events:
                accepted = abs(event_weight - initial_weight) <= _tolerance(
                    initial_weight,
                    config.first_event_match_ratio,
                    config.first_event_match_min_g,
                )
            else:
                accepted = abs(event_weight - last_weight) <= _time_adjusted_tolerance(
                    last_weight,
                    last_event_timestamp,
                    event_timestamp,
                    config,
                )
            if accepted:
                events.append(_WeightEvent(event_position, event_weight, event_timestamp))
                last_weight = event_weight
                last_event_timestamp = event_timestamp

        # One high segment may create only one fitted event. A return to the
        # empty-scale range is required before another segment can be accepted.
        waiting_for_empty_return = not any(
            candidate < config.minimum_body_weight_g for _, candidate in window
        )
        index = max(cursor, index + 1)
    return events


def fit_weight_series(
        values: Iterable,
        config: Optional[WeightPostprocessConfig] = None,
        timestamps: Optional[Iterable] = None,
        initial_weight: Optional[float] = None,
) -> tuple[list[Optional[float]], int]:
    """Fit one cage with a fixed empty-scale baseline and event-level updates."""
    config = config or WeightPostprocessConfig()
    numeric_values = [_to_finite_float(value) for value in values]
    numeric_timestamps: Optional[list[float]] = None
    if timestamps is not None:
        timestamp_values = [_to_timestamp(value) for value in timestamps]
        if len(timestamp_values) == len(numeric_values) and all(
                value is not None for value in timestamp_values
        ):
            numeric_timestamps = [float(value) for value in timestamp_values]
    initial_weight_value = _to_finite_float(initial_weight)
    if initial_weight_value is None or not (
            config.minimum_body_weight_g
            <= initial_weight_value
            <= config.maximum_body_weight_g
    ):
        return [None] * len(numeric_values), 0

    baseline_match = _find_initial_baseline(numeric_values, initial_weight_value, config)
    if baseline_match is None:
        fitted_initial = round(initial_weight_value, config.decimal_places)
        return [fitted_initial] * len(numeric_values), 0

    events = _confirm_weight_events(
        numeric_values,
        initial_weight_value,
        baseline_match,
        config,
        numeric_timestamps,
    )
    fitted: list[Optional[float]] = []
    event_index = 0
    active_weight = initial_weight_value
    for index in range(len(numeric_values)):
        while event_index < len(events) and events[event_index].position <= index:
            active_weight = events[event_index].weight
            event_index += 1
        fitted.append(round(active_weight, config.decimal_places))
    return fitted, len(events)


def _fill_existing_numeric(values: Sequence) -> list[Optional[float]]:
    numeric = [_to_finite_float(value) for value in values]
    valid_indexes = [index for index, value in enumerate(numeric) if value is not None]
    if not valid_indexes:
        return numeric

    first_value = numeric[valid_indexes[0]]
    active_value = first_value
    result: list[Optional[float]] = []
    for value in numeric:
        if value is not None:
            active_value = value
        result.append(active_value)
    return result


def _default_output_path(raw_excel_path: Path, suffix: str) -> Path:
    return raw_excel_path.with_name(f"{raw_excel_path.stem}{suffix}{raw_excel_path.suffix}")


def _initial_weight_for_cage(
        initial_weights: Optional[Mapping],
        cage_name: str,
        config: WeightPostprocessConfig,
) -> Optional[float]:
    if not initial_weights:
        return None
    normalized_cage_name = str(cage_name).strip()
    for key, value in initial_weights.items():
        if str(key).strip() != normalized_cage_name:
            continue
        numeric_value = _to_finite_float(value)
        if numeric_value is not None and (
                config.minimum_body_weight_g
                <= numeric_value
                <= config.maximum_body_weight_g
        ):
            return numeric_value
        return None
    return None


def create_fitted_workbook(
        raw_excel_path: os.PathLike | str,
        output_path: Optional[os.PathLike | str] = None,
        config_path: Optional[os.PathLike | str] = None,
        initial_weights: Optional[Mapping] = None,
) -> WeightPostprocessResult:
    raw_path = Path(raw_excel_path).resolve()
    temp_path: Optional[Path] = None
    try:
        config = load_weight_postprocess_config(config_path)
        if not config.enabled:
            return WeightPostprocessResult(success=True)
        if not raw_path.is_file():
            raise FileNotFoundError(f"原始 Excel 不存在: {raw_path}")

        fitted_path = (
            Path(output_path).resolve()
            if output_path is not None
            else _default_output_path(raw_path, config.output_suffix)
        )
        if fitted_path == raw_path:
            raise ValueError("拟合结果不能覆盖原始 Excel")

        from openpyxl import load_workbook

        workbook = load_workbook(raw_path)
        matched_sheets = 0
        processed_sheets = 0
        processed_cage_names: set[str] = set()
        skipped_cage_names: set[str] = set()
        warnings: list[str] = []

        for worksheet in workbook.worksheets:
            headers = {
                str(cell.value).strip(): cell.column
                for cell in worksheet[1]
                if cell.value is not None
            }
            cage_column = headers.get(CAGE_HEADER)
            weight_column = headers.get(WEIGHT_HEADER)
            if cage_column is None or weight_column is None:
                continue
            matched_sheets += 1
            time_column = headers.get(TIME_HEADER)

            grouped_rows: dict[str, list[int]] = {}
            for row_number in range(2, worksheet.max_row + 1):
                cage_value = worksheet.cell(row_number, cage_column).value
                if cage_value is None or str(cage_value).strip() == "":
                    continue
                grouped_rows.setdefault(str(cage_value).strip(), []).append(row_number)

            sheet_processed = False
            for cage_name, row_numbers in grouped_rows.items():
                records = [
                    (
                        row_number,
                        worksheet.cell(row_number, weight_column).value,
                        _to_timestamp(
                            worksheet.cell(row_number, time_column).value
                        ) if time_column is not None else None,
                    )
                    for row_number in row_numbers
                ]
                has_complete_timestamps = (
                    time_column is not None
                    and bool(records)
                    and all(record[2] is not None for record in records)
                )
                if has_complete_timestamps:
                    records.sort(key=lambda record: float(record[2]))
                ordered_rows = [record[0] for record in records]
                raw_values = [record[1] for record in records]
                timestamps = (
                    [float(record[2]) for record in records]
                    if has_complete_timestamps
                    else None
                )
                numeric_count = sum(_to_finite_float(value) is not None for value in raw_values)
                initial_weight = _initial_weight_for_cage(
                    initial_weights,
                    cage_name,
                    config,
                )
                if numeric_count == 0:
                    for row_number in ordered_rows:
                        cell = worksheet.cell(row_number, weight_column)
                        cell.value = (
                            None
                            if initial_weight is None
                            else round(initial_weight, config.decimal_places)
                        )
                    if initial_weight is not None:
                        processed_cage_names.add(cage_name)
                        sheet_processed = True
                        warnings.append(
                            f"{worksheet.title}/{cage_name}: 无有效称重事件，使用实验前体重"
                        )
                    continue

                fitted_values, event_count = fit_weight_series(
                    raw_values,
                    config,
                    timestamps=timestamps,
                    initial_weight=initial_weight,
                )
                if event_count == 0:
                    if initial_weight is not None:
                        processed_cage_names.add(cage_name)
                        warnings.append(
                            f"{worksheet.title}/{cage_name}: 未找到有效称重事件，使用实验前体重"
                        )
                    else:
                        fitted_values = _fill_existing_numeric(raw_values)
                        skipped_cage_names.add(cage_name)
                        warnings.append(
                            f"{worksheet.title}/{cage_name}: 未提供实验前体重或未建立空秤基线，保留并补齐原始数值"
                        )
                else:
                    processed_cage_names.add(cage_name)

                for row_number, fitted_value in zip(ordered_rows, fitted_values):
                    worksheet.cell(row_number, weight_column).value = (
                        None
                        if fitted_value is None
                        else round(float(fitted_value), config.decimal_places)
                    )
                sheet_processed = True

            if sheet_processed:
                processed_sheets += 1

        if matched_sheets == 0:
            raise ValueError(f"Excel 中未找到 {CAGE_HEADER} 和 {WEIGHT_HEADER} 数据列")
        if processed_sheets == 0:
            workbook.close()
            return WeightPostprocessResult(
                success=True,
                warnings=("未检测到有效称重数据，未生成称重拟合 Excel",),
            )

        fitted_path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(
            prefix=f".{fitted_path.stem}.",
            suffix=fitted_path.suffix or ".xlsx",
            dir=fitted_path.parent,
        )
        os.close(handle)
        temp_path = Path(temp_name)
        workbook.save(temp_path)
        workbook.close()
        os.replace(temp_path, fitted_path)
        temp_path = None

        for warning in warnings:
            logger.warning(f"weight postprocess: {warning}")
        result = WeightPostprocessResult(
            success=True,
            output_path=str(fitted_path),
            processed_sheets=processed_sheets,
            processed_cages=len(processed_cage_names),
            skipped_cages=len(skipped_cage_names - processed_cage_names),
            warnings=tuple(warnings),
        )
        logger.info(f"{result.summary}: {fitted_path}")
        return result
    except Exception as error:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        logger.exception(f"称重后处理失败，原始 Excel 保持不变: {error}")
        return WeightPostprocessResult(success=False, error=str(error))
