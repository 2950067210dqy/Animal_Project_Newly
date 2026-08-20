"""Stable public API for replaceable oxygen compensation implementations.

The oxygen algorithm files are supplied independently and may be replaced by
another compatible implementation.  This module keeps the host application's
contract stable and applies project-wide safety rules at the boundary.
"""

from __future__ import annotations

import configparser
import math
from pathlib import Path
from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover - logging must never break the API
    import logging

    logger = logging.getLogger(__name__)

from . import o2_realtime_core as _core


_WARNED_MISSING_REFERENCE: set[str] = set()
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_POINTS_CONFIG = _PROJECT_ROOT / "config" / "UFC_UGC_ZOS_Test.ini"


def _configured_target_points() -> int:
    """Read the shared calibration count instead of trusting vendor defaults."""
    parser = configparser.ConfigParser()
    try:
        parser.read(_POINTS_CONFIG, encoding="utf-8")
        value = parser.getint("Calibration", "startup_air_calibration_target_points", fallback=120)
        return max(1, value)
    except (OSError, ValueError, configparser.Error) as exc:
        logger.warning(
            f"Unable to read O2 calibration point count from {_POINTS_CONFIG}: {exc}; using 120"
        )
        return 120


def _valid_channels() -> set[str]:
    return set(getattr(_core, "VALID_CHANNELS", ["REF"] + [f"M{i}" for i in range(1, 9)]))


def _has_reference_sample(compensator: Any) -> bool:
    checker = getattr(compensator, "has_valid_reference_sample", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception as exc:
            logger.warning(f"O2 reference sample check failed: {exc}")
            return False

    # Older supplier implementations expose only the buffer.
    buffer = getattr(compensator, "dry_ref_buffer", None)
    if buffer is None:
        return False
    try:
        return any(math.isfinite(float(value)) for value in buffer)
    except (TypeError, ValueError, OverflowError):
        return False


def get_realtime_o2_compensator():
    return _core.get_realtime_o2_compensator()


def has_valid_reference_dry_oxygen_sample() -> bool:
    """Return True only when a real REF dry-oxygen sample is available."""
    return _has_reference_sample(get_realtime_o2_compensator())


def reload_o2_compensation_config():
    return _core.reload_o2_compensation_config()


def get_o2_calibration_handler(target_points: int | None = None):
    points = _configured_target_points() if target_points is None else int(target_points)
    return _core.get_o2_calibration_handler(target_points=points)


def start_new_o2_calibration(target_points: int | None = None):
    points = _configured_target_points() if target_points is None else int(target_points)
    return _core.start_new_o2_calibration(target_points=points)


def append_o2_calibration_data(channel, o2_partial, zos_temp, gas_pressure, o2_percent, zos_rh):
    return _core.append_o2_calibration_data(
        channel, o2_partial, zos_temp, gas_pressure, o2_percent, zos_rh
    )


def get_o2_calibration_status():
    return _core.get_o2_calibration_status()


def calculate_o2_compensated(
    channel_id,
    o2_partial_press,
    zos_temp,
    gas_total_press,
    o2_raw_pct,
    zos_rh,
):
    """Call the replaceable implementation behind the stable host contract."""
    if channel_id not in _valid_channels():
        return -1

    if channel_id != "REF" and not has_valid_reference_dry_oxygen_sample():
        if channel_id not in _WARNED_MISSING_REFERENCE:
            logger.warning(f"O2 compensation skipped for {channel_id}: no valid REF sample")
            _WARNED_MISSING_REFERENCE.add(channel_id)
        return -1

    try:
        result = _core.calculate_o2_compensated(
            channel_id,
            o2_partial_press,
            zos_temp,
            gas_total_press,
            o2_raw_pct,
            zos_rh,
        )
        numeric_result = float(result)
        if not math.isfinite(numeric_result):
            return -1
        return numeric_result
    except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        logger.warning(f"O2 compensation rejected {channel_id} sample: {exc}")
        return -1


__all__ = [
    "append_o2_calibration_data",
    "calculate_o2_compensated",
    "get_o2_calibration_handler",
    "get_o2_calibration_status",
    "get_realtime_o2_compensator",
    "has_valid_reference_dry_oxygen_sample",
    "reload_o2_compensation_config",
    "start_new_o2_calibration",
]
