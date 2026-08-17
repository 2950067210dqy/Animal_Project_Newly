from __future__ import annotations

import configparser
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable, Optional, Sequence

try:
    from loguru import logger
except ImportError:  # Allows the postprocessor to run in lightweight export tools.
    import logging

    logger = logging.getLogger(__name__)


CAGE_HEADER = "鼠笼号"
WEIGHT_HEADER = "称重重量测量值(g)"
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "monitor_datas_config.ini"
)


@dataclass(frozen=True)
class WeightPostprocessConfig:
    enabled: bool = True
    stable_points: int = 3
    stable_tolerance_g: float = 1.0
    minimum_body_weight_g: float = 5.0
    maximum_body_weight_g: float = 80.0
    outlier_ratio: float = 0.20
    reference_history: int = 3
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
class _Plateau:
    start: int
    end: int
    position: int
    level: float


@dataclass(frozen=True)
class _WeightEvent:
    position: int
    weight: float


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
        stable_points=max(2, get_int("stable_points", 3)),
        stable_tolerance_g=max(0.0, get_float("stable_tolerance_g", 1.0)),
        minimum_body_weight_g=max(0.0, get_float("minimum_body_weight_g", 5.0)),
        maximum_body_weight_g=max(0.0, get_float("maximum_body_weight_g", 80.0)),
        outlier_ratio=max(0.0, get_float("outlier_ratio", 0.20)),
        reference_history=max(1, get_int("reference_history", 3)),
        decimal_places=max(0, get_int("decimal_places", 3)),
        output_suffix=get("output_suffix", "_称重拟合").strip() or "_称重拟合",
    )
    if config.maximum_body_weight_g <= config.minimum_body_weight_g:
        raise ValueError("maximum_body_weight_g must be greater than minimum_body_weight_g")
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


def _find_stable_plateaus(
        values: Sequence[Optional[float]],
        config: WeightPostprocessConfig,
) -> list[_Plateau]:
    windows: list[_Plateau] = []
    width = config.stable_points
    for start in range(0, len(values) - width + 1):
        window = values[start:start + width]
        if any(value is None for value in window):
            continue
        numeric_window = [float(value) for value in window if value is not None]
        if max(numeric_window) - min(numeric_window) > config.stable_tolerance_g:
            continue
        windows.append(
            _Plateau(
                start=start,
                end=start + width - 1,
                position=start + width // 2,
                level=float(median(numeric_window)),
            )
        )

    if not windows:
        return []

    plateaus: list[_Plateau] = []
    group = [windows[0]]
    for window in windows[1:]:
        previous = group[-1]
        levels = [item.level for item in group]
        if (
                window.start <= previous.end + 1
                and abs(window.level - float(median(levels))) <= config.stable_tolerance_g
        ):
            group.append(window)
            continue
        plateaus.append(_merge_plateau_windows(group))
        group = [window]
    plateaus.append(_merge_plateau_windows(group))
    return plateaus


def _merge_plateau_windows(windows: Sequence[_Plateau]) -> _Plateau:
    start = windows[0].start
    end = windows[-1].end
    return _Plateau(
        start=start,
        end=end,
        position=(start + end) // 2,
        level=float(median([window.level for window in windows])),
    )


def _nearest_lower_plateau(
        plateaus: Sequence[_Plateau],
        upper_index: int,
        direction: int,
        config: WeightPostprocessConfig,
) -> Optional[_Plateau]:
    index = upper_index + direction
    while 0 <= index < len(plateaus):
        difference = plateaus[upper_index].level - plateaus[index].level
        if config.minimum_body_weight_g <= difference <= config.maximum_body_weight_g:
            return plateaus[index]
        index += direction
    return None


def _interpolated_baseline(
        upper: _Plateau,
        before: Optional[_Plateau],
        after: Optional[_Plateau],
) -> Optional[float]:
    if before is None:
        return after.level if after is not None else None
    if after is None:
        return before.level
    distance = after.position - before.position
    if distance <= 0:
        return float(median([before.level, after.level]))
    ratio = (upper.position - before.position) / distance
    return before.level + ((after.level - before.level) * ratio)


def _candidate_weight_events(
        plateaus: Sequence[_Plateau],
        config: WeightPostprocessConfig,
) -> list[_WeightEvent]:
    candidates: list[_WeightEvent] = []
    for index, upper in enumerate(plateaus):
        before = _nearest_lower_plateau(plateaus, index, -1, config)
        after = _nearest_lower_plateau(plateaus, index, 1, config)
        baseline = _interpolated_baseline(upper, before, after)
        if baseline is None:
            continue
        weight = upper.level - baseline
        if config.minimum_body_weight_g <= weight <= config.maximum_body_weight_g:
            candidates.append(_WeightEvent(upper.position, weight))
    return candidates


def _filter_weight_events(
        candidates: Sequence[_WeightEvent],
        config: WeightPostprocessConfig,
) -> list[_WeightEvent]:
    if not candidates:
        return []

    robust_candidates = list(candidates)
    if len(robust_candidates) >= config.reference_history:
        center = float(median([candidate.weight for candidate in robust_candidates]))
        tolerance = max(config.stable_tolerance_g, abs(center) * config.outlier_ratio)
        robust_candidates = [
            candidate for candidate in robust_candidates
            if abs(candidate.weight - center) <= tolerance
        ]

    accepted: list[_WeightEvent] = []
    for candidate in sorted(robust_candidates, key=lambda item: item.position):
        if len(accepted) < config.reference_history:
            accepted.append(candidate)
            continue
        history = accepted[-config.reference_history:]
        reference = float(median([item.weight for item in history]))
        tolerance = max(config.stable_tolerance_g, abs(reference) * config.outlier_ratio)
        if abs(candidate.weight - reference) <= tolerance:
            accepted.append(candidate)
    return accepted


def fit_weight_series(
        values: Iterable,
        config: Optional[WeightPostprocessConfig] = None,
) -> tuple[list[Optional[float]], int]:
    config = config or WeightPostprocessConfig()
    numeric_values = [_to_finite_float(value) for value in values]
    plateaus = _find_stable_plateaus(numeric_values, config)
    candidates = _candidate_weight_events(plateaus, config)
    events = _filter_weight_events(candidates, config)
    if not events:
        return [None] * len(numeric_values), 0

    fitted: list[Optional[float]] = []
    event_index = 0
    active_weight = events[0].weight
    for index in range(len(numeric_values)):
        while event_index + 1 < len(events) and events[event_index + 1].position <= index:
            event_index += 1
            active_weight = events[event_index].weight
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


def create_fitted_workbook(
        raw_excel_path: os.PathLike | str,
        output_path: Optional[os.PathLike | str] = None,
        config_path: Optional[os.PathLike | str] = None,
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

            grouped_rows: dict[str, list[int]] = {}
            for row_number in range(2, worksheet.max_row + 1):
                cage_value = worksheet.cell(row_number, cage_column).value
                if cage_value is None or str(cage_value).strip() == "":
                    continue
                grouped_rows.setdefault(str(cage_value).strip(), []).append(row_number)

            sheet_processed = False
            for cage_name, row_numbers in grouped_rows.items():
                raw_values = [
                    worksheet.cell(row_number, weight_column).value
                    for row_number in row_numbers
                ]
                numeric_count = sum(_to_finite_float(value) is not None for value in raw_values)
                if numeric_count == 0:
                    for row_number in row_numbers:
                        cell = worksheet.cell(row_number, weight_column)
                        if _to_finite_float(cell.value) is None:
                            cell.value = None
                    continue

                fitted_values, event_count = fit_weight_series(raw_values, config)
                if event_count == 0:
                    fitted_values = _fill_existing_numeric(raw_values)
                    skipped_cage_names.add(cage_name)
                    warnings.append(
                        f"{worksheet.title}/{cage_name}: 未找到完整的上下稳定平台，保留并补齐原始数值"
                    )
                else:
                    processed_cage_names.add(cage_name)

                for row_number, fitted_value in zip(row_numbers, fitted_values):
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
