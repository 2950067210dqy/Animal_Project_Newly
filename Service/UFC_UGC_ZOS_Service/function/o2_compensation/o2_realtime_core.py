import json
import threading
from copy import deepcopy
from pathlib import Path

import numpy as np


VALID_CHANNELS = ["REF"] + [f"M{i}" for i in range(1, 9)]

DEFAULT_SMOOTHING_PARAMS = {
    "zos_temp_window": 3,
    "humidity_window": 5,
    "pressure_window": 5,
    "humidity_clip_min": 45,
    "humidity_clip_max": 85,
    "pressure_clip_min": 85,
    "pressure_clip_max": 110,
}

LEGACY_O2_UPPER_LIMIT = 23.0
LEGACY_O2_LOWER_LIMIT = 10.0
LEGACY_FILTER_WINDOW = 15


def get_default_config():
    config = {
        "version": "1.0",
        "target_o2": 20.93,
        "calibration_info": {
            "calibration_date": "",
            "calibration_points": 0,
            "note": "default config",
        },
        "smoothing_params": deepcopy(DEFAULT_SMOOTHING_PARAMS),
        "channels": {},
    }
    for channel in VALID_CHANNELS:
        config["channels"][channel] = {
            "coef_moist": 1.0,
            "coef_zos_t": 0.0,
            "coef_rh": 0.0,
            "coef_p": 0.0,
            "intercept": 0.0,
        }
    return config


def get_default_config_path():
    return Path(__file__).resolve().parents[4] / "config" / "calib_config.json"


def calc_dry_o2(o2_wet, temp_celsius, rh_percent, press_kpa):
    sat_vapor_pressure = 0.61094 * np.exp(17.625 * temp_celsius / (temp_celsius + 243.04))
    actual_vapor_pressure = sat_vapor_pressure * rh_percent / 100.0
    dry_pressure = max(press_kpa - actual_vapor_pressure, 1e-6)
    return float(o2_wet * (press_kpa / dry_pressure))


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        result = float(value)
        if np.isnan(result) or np.isinf(result):
            return default
        return result
    except Exception:
        return default


class RealtimeO2Compensator:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path or get_default_config_path())
        self.channels = VALID_CHANNELS.copy()
        self.config_mode = "calibrated"
        self.target = 20.93
        self.base_channel = "REF"
        self.config = get_default_config()
        self.coefs = {}
        self.legacy_models = {}
        self.last_valid = {channel: None for channel in self.channels}
        self.last_compensated = {channel: self.target for channel in self.channels}
        self.last_ref_deviation = 0.0
        self.filter_cache = {channel: [] for channel in self.channels}
        self.legacy_last_valid_value_cache = {channel: self.target for channel in self.channels}
        self._config_mtime_ns = None
        self.reload_config(force=True)

    def _get_config_mtime_ns(self):
        try:
            return self.config_path.stat().st_mtime_ns
        except OSError:
            return None

    def ensure_latest(self):
        self.reload_config(force=False)

    def reload_config(self, force=False):
        current_mtime_ns = self._get_config_mtime_ns()
        if not force and self._config_mtime_ns == current_mtime_ns:
            return

        config = self._load_config()
        if "target_o2" in config and "channels" in config:
            self._load_calibrated_config(config)
        else:
            self._load_legacy_config(config)
        self._config_mtime_ns = current_mtime_ns

    def _load_config(self):
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return get_default_config()

    def _load_calibrated_config(self, config):
        self.config_mode = "calibrated"
        self.config = config
        self.target = _safe_float(config.get("target_o2"), 20.93)
        self.coefs = {}
        for channel in self.channels:
            channel_config = config.get("channels", {}).get(channel, {})
            self.coefs[channel] = {
                "coef_moist": _safe_float(channel_config.get("coef_moist"), 1.0),
                "coef_zos_t": _safe_float(channel_config.get("coef_zos_t"), 0.0),
                "coef_rh": _safe_float(channel_config.get("coef_rh"), 0.0),
                "coef_p": _safe_float(channel_config.get("coef_p"), 0.0),
                "intercept": _safe_float(channel_config.get("intercept"), 0.0),
            }
        for channel in self.channels:
            self.last_compensated.setdefault(channel, self.target)
        self.legacy_last_valid_value_cache = {channel: self.target for channel in self.channels}
        self.filter_cache = {channel: [] for channel in self.channels}

    def _load_legacy_config(self, config):
        self.config_mode = "legacy"
        self.config = config
        self.target = _safe_float(config.get("TARGET_O2"), 20.93)
        self.base_channel = config.get("BASE_CHANNEL", "REF")
        self.legacy_models = {}
        for channel in self.channels:
            channel_config = config.get(channel, {})
            self.legacy_models[channel] = {
                "K": _safe_float(channel_config.get("K"), 1.0),
                "B": _safe_float(channel_config.get("B"), 0.0),
            }
        self.filter_cache = {channel: [] for channel in self.channels}
        self.legacy_last_valid_value_cache = {channel: self.target for channel in self.channels}

    def _is_valid_realtime_value(self, field, value):
        if value is None:
            return False
        if field == "zos_temp":
            return 10 <= value <= 50
        if field == "gas_pressure":
            return 85 <= value <= 110
        if field == "o2_percent":
            return 18 <= value <= 23
        if field == "sht_rh":
            return 20 <= value <= 95
        return True

    def _filter_legacy_value(self, channel, value):
        cache = self.filter_cache[channel]
        cache.append(value)
        if len(cache) > LEGACY_FILTER_WINDOW:
            cache.pop(0)
        return float(np.mean(cache))

    def _compensate_legacy(self, channel, gas_pressure, o2_raw_pct, temp_cage, rh_cage):
        channel_model = self.legacy_models.get(channel, {"K": 1.0, "B": 0.0})
        dry_o2 = calc_dry_o2(o2_raw_pct, temp_cage, rh_cage, gas_pressure)
        calibrated_o2 = dry_o2 * channel_model["K"] + channel_model["B"]
        if channel == self.base_channel:
            final_o2 = self.target
        else:
            final_o2 = calibrated_o2

        filtered_value = self._filter_legacy_value(channel, final_o2)
        if LEGACY_O2_LOWER_LIMIT <= filtered_value <= LEGACY_O2_UPPER_LIMIT:
            self.legacy_last_valid_value_cache[channel] = filtered_value
            return round(filtered_value, 3)
        return round(self.legacy_last_valid_value_cache[channel], 3)

    def _compensate_calibrated(self, channel, zos_temp, gas_pressure, o2_percent, sht_rh):
        current = {
            "zos_temp": _safe_float(zos_temp),
            "gas_pressure": _safe_float(gas_pressure),
            "o2_percent": _safe_float(o2_percent),
            "sht_rh": _safe_float(sht_rh),
        }

        if all(self._is_valid_realtime_value(key, value) for key, value in current.items()):
            self.last_valid[channel] = current.copy()
        elif self.last_valid[channel] is not None:
            current = self.last_valid[channel].copy()
        else:
            return round(self.last_compensated.get(channel, self.target), 4)

        physical_dry = calc_dry_o2(
            current["o2_percent"],
            current["zos_temp"],
            current["sht_rh"],
            current["gas_pressure"],
        )

        coef = self.coefs.get(channel, {
            "coef_moist": 1.0,
            "coef_zos_t": 0.0,
            "coef_rh": 0.0,
            "coef_p": 0.0,
            "intercept": 0.0,
        })
        model_pred = (
            coef["coef_moist"] * current["o2_percent"]
            + coef["coef_zos_t"] * current["zos_temp"]
            + coef["coef_rh"] * current["sht_rh"]
            + coef["coef_p"] * current["gas_pressure"]
            + coef["intercept"]
        )
        compensated = physical_dry - (model_pred - self.target)

        if channel == "REF":
            self.last_ref_deviation = compensated - self.target
            final_value = self.target
        else:
            final_value = compensated - self.last_ref_deviation

        self.last_compensated[channel] = final_value
        return round(final_value, 4)

    def compensate(self, channel, o2_partial, zos_temp, gas_pressure, o2_percent, sht_temp, sht_rh):
        del o2_partial
        del sht_temp

        if channel not in self.channels:
            return round(self.target, 4)

        self.ensure_latest()
        if self.config_mode == "legacy":
            gas_pressure_value = _safe_float(gas_pressure)
            o2_percent_value = _safe_float(o2_percent)
            zos_temp_value = _safe_float(zos_temp)
            sht_rh_value = _safe_float(sht_rh)
            if None in (gas_pressure_value, o2_percent_value, zos_temp_value, sht_rh_value):
                return round(self.legacy_last_valid_value_cache.get(channel, self.target), 3)
            return self._compensate_legacy(
                channel,
                gas_pressure_value,
                o2_percent_value,
                zos_temp_value,
                sht_rh_value,
            )

        return self._compensate_calibrated(
            channel,
            zos_temp,
            gas_pressure,
            o2_percent,
            sht_rh,
        )

    def set_target(self, new_target):
        target = _safe_float(new_target)
        if target is None:
            return
        self.target = target


_COMPENSATOR_LOCK = threading.Lock()
_COMPENSATOR = None
_CALIBRATION_HANDLER_LOCK = threading.Lock()
_CALIBRATION_HANDLER = None


def get_realtime_o2_compensator():
    global _COMPENSATOR
    with _COMPENSATOR_LOCK:
        if _COMPENSATOR is None:
            _COMPENSATOR = RealtimeO2Compensator()
        else:
            _COMPENSATOR.ensure_latest()
        return _COMPENSATOR


def reload_o2_compensation_config():
    compensator = get_realtime_o2_compensator()
    compensator.reload_config(force=True)
    return True


def get_o2_calibration_handler(target_points=None):
    global _CALIBRATION_HANDLER
    with _CALIBRATION_HANDLER_LOCK:
        if target_points is not None:
            target_points = int(target_points)

        if (
            _CALIBRATION_HANDLER is None
            or (target_points is not None and _CALIBRATION_HANDLER.target_points != target_points)
        ):
            from .calibration_handler import CalibrationHandler

            _CALIBRATION_HANDLER = CalibrationHandler(
                target_points=target_points or 120,
                config_path=get_default_config_path(),
            )
        return _CALIBRATION_HANDLER


def start_new_o2_calibration(target_points=120):
    handler = get_o2_calibration_handler(target_points=target_points)
    return handler.start_new_calibration()


def append_o2_calibration_data(channel, o2_partial, zos_temp, gas_pressure, o2_percent, sht_temp, sht_rh):
    handler = get_o2_calibration_handler()
    success = handler.add_data(
        channel=channel,
        o2_partial=o2_partial,
        zos_temp=zos_temp,
        gas_pressure=gas_pressure,
        o2_percent=o2_percent,
        sht_temp=sht_temp,
        sht_rh=sht_rh,
    )
    if success:
        reload_o2_compensation_config()
    return success


def get_o2_calibration_status():
    handler = get_o2_calibration_handler()
    return handler.get_status()


def calculate_o2_compensated(
        channel_id,
        o2_partial_press,
        temp_sensor,
        gas_total_press,
        o2_raw_pct,
        temp_cage,
        rh_cage
):
    if channel_id not in VALID_CHANNELS:
        return -1

    compensator = get_realtime_o2_compensator()
    return compensator.compensate(
        channel=channel_id,
        o2_partial=o2_partial_press,
        zos_temp=temp_sensor,
        gas_pressure=gas_total_press,
        o2_percent=o2_raw_pct,
        sht_temp=temp_cage,
        sht_rh=rh_cage,
    )
