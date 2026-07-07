import json
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


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


def get_default_config_path():
    return Path(__file__).resolve().parents[4] / "config" / "calib_config.json"


class CalibrationHandler:
    def __init__(self, target_points=120, config_path=None):
        self.channels = VALID_CHANNELS.copy()
        self.target_points = int(target_points)
        self.config_path = Path(config_path or get_default_config_path())
        self.data = {channel: [] for channel in self.channels}
        self.calibrated = False
        self.is_active = False
        self.lock = threading.Lock()

    def start_new_calibration(self):
        with self.lock:
            self.data = {channel: [] for channel in self.channels}
            self.calibrated = False
            self.is_active = True
        return True

    def add_data(self, channel, o2_partial, zos_temp, gas_pressure, o2_percent, env_temp, env_rh):
        del o2_partial
        del zos_temp

        with self.lock:
            if channel not in self.channels:
                return False
            if self.calibrated:
                return True
            if not self.is_active:
                return False

            point = {
                "zos_temp": float(env_temp),
                "gas_pressure": float(gas_pressure),
                "o2_percent": float(o2_percent),
                "sht_rh": float(env_rh),
            }
            self.data[channel].append(point)

            if all(len(self.data[item]) >= self.target_points for item in self.channels):
                success = self._perform_calibration()
                if success:
                    self.calibrated = True
                    self.is_active = False
                return success
            return False

    def _perform_calibration(self):
        try:
            coefficient_items = []
            for channel in self.channels:
                channel_frame = self._build_channel_frame(self.data[channel][:self.target_points])
                features = channel_frame[["o2_percent", "T_smooth", "RH_smooth", "P_smooth"]].values
                labels = channel_frame["dry_o2"].values
                model = LinearRegression()
                model.fit(features, labels)
                coefficient_items.append({
                    "channel": channel,
                    "coef_moist": round(float(model.coef_[0]), 6),
                    "coef_zos_t": round(float(model.coef_[1]), 6),
                    "coef_rh": round(float(model.coef_[2]), 6),
                    "coef_p": round(float(model.coef_[3]), 6),
                    "intercept": round(float(model.intercept_), 6),
                })
            self._write_config(coefficient_items)
            return True
        except Exception:
            return False

    def _build_channel_frame(self, points):
        frame = pd.DataFrame(points)
        for field in ["o2_percent", "gas_pressure", "zos_temp", "sht_rh"]:
            frame[field] = frame[field].replace(0, np.nan).ffill().bfill().astype(float)

        frame["T_smooth"] = frame["zos_temp"].rolling(
            window=DEFAULT_SMOOTHING_PARAMS["zos_temp_window"],
            center=True,
            min_periods=1,
        ).median().ffill().bfill()

        frame["RH_smooth"] = frame["sht_rh"].rolling(
            window=DEFAULT_SMOOTHING_PARAMS["humidity_window"],
            center=True,
            min_periods=2,
        ).median()
        frame["RH_smooth"] = frame["RH_smooth"].clip(
            lower=DEFAULT_SMOOTHING_PARAMS["humidity_clip_min"],
            upper=DEFAULT_SMOOTHING_PARAMS["humidity_clip_max"],
        ).ffill().bfill()

        frame["P_smooth"] = frame["gas_pressure"].clip(
            lower=DEFAULT_SMOOTHING_PARAMS["pressure_clip_min"],
            upper=DEFAULT_SMOOTHING_PARAMS["pressure_clip_max"],
        )
        frame["P_smooth"] = frame["P_smooth"].rolling(
            window=DEFAULT_SMOOTHING_PARAMS["pressure_window"],
            center=True,
            min_periods=1,
        ).median().ffill().bfill()

        frame["dry_o2"] = frame.apply(
            lambda row: self._calculate_dry_o2(
                row["o2_percent"],
                row["P_smooth"],
                row["T_smooth"],
                row["RH_smooth"],
            ),
            axis=1,
        )
        return frame

    def _calculate_dry_o2(self, moist_o2, gas_pressure, zos_temp, sht_rh):
        if pd.isna(gas_pressure) or gas_pressure <= 0 or pd.isna(zos_temp) or pd.isna(sht_rh):
            return np.nan
        sat_vapor_pressure = 0.61094 * np.exp(17.625 * zos_temp / (zos_temp + 243.04))
        actual_vapor_pressure = (sht_rh / 100.0) * sat_vapor_pressure
        if actual_vapor_pressure >= gas_pressure * 0.99:
            actual_vapor_pressure = gas_pressure * 0.99
        return moist_o2 * (gas_pressure / (gas_pressure - actual_vapor_pressure))

    def _write_config(self, coefficient_items):
        config = {
            "version": "1.0",
            "target_o2": 20.93,
            "calibration_info": {
                "calibration_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "calibration_points": self.target_points,
                "note": "上位机实时标定完成",
            },
            "smoothing_params": DEFAULT_SMOOTHING_PARAMS.copy(),
            "channels": {},
        }

        for item in coefficient_items:
            config["channels"][item["channel"]] = {
                "coef_moist": item["coef_moist"],
                "coef_zos_t": item["coef_zos_t"],
                "coef_rh": item["coef_rh"],
                "coef_p": item["coef_p"],
                "intercept": item["intercept"],
            }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def get_status(self):
        with self.lock:
            current_counts = {channel: len(self.data[channel]) for channel in self.channels}
            return {
                "is_active": self.is_active,
                "calibrated": self.calibrated,
                "current_counts": current_counts,
                "all_ready": all(count >= self.target_points for count in current_counts.values()),
                "target_points": self.target_points,
                "config_path": str(self.config_path),
            }
