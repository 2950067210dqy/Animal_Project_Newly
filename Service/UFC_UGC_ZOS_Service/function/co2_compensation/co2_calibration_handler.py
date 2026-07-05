import json
from datetime import datetime
from pathlib import Path
import threading

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


VALID_CHANNELS = ["REF"] + [f"M{i}" for i in range(1, 9)]


def get_default_config_path():
    return Path(__file__).resolve().parents[4] / "config" / "co2_calib_config.json"


class CO2CalibrationHandler:
    def __init__(self, target_points=120, config_path=None):
        self.channels = VALID_CHANNELS.copy()
        self.target_points = int(target_points)
        self.config_path = Path(config_path or get_default_config_path())
        self.data = {ch: [] for ch in self.channels}
        self.calibrated = False
        self.is_active = False
        self.lock = threading.Lock()

    def start_new_calibration(self):
        with self.lock:
            self.data = {ch: [] for ch in self.channels}
            self.calibrated = False
            self.is_active = True
        return True

    def add_data(self, channel, co2_std):
        with self.lock:
            if channel not in self.channels:
                return False
            if self.calibrated:
                return True
            if not self.is_active:
                return False

            self.data[channel].append({"co2_std": float(co2_std)})

            all_ready = all(len(self.data[ch]) >= self.target_points for ch in self.channels)
            if not all_ready:
                return False

            success = self._perform_calibration()
            if success:
                self.calibrated = True
                self.is_active = False
            return success

    def _perform_calibration(self):
        try:
            ref_df = pd.DataFrame(self.data["REF"][: self.target_points])
            ref_df["co2_smooth"] = (
                ref_df["co2_std"]
                .rolling(window=11, center=True, min_periods=5)
                .mean()
                .ffill()
                .bfill()
            )

            coefficient_items = []
            for channel in self.channels:
                if channel == "REF":
                    coefficient_items.append(
                        {
                            "channel": "REF",
                            "coef_k": 1.0,
                            "coef_b": 0.0,
                        }
                    )
                    continue

                channel_df = pd.DataFrame(self.data[channel][: self.target_points])
                channel_df["co2_std"] = channel_df["co2_std"].replace(0, np.nan).ffill().bfill()

                sample_count = min(len(channel_df), len(ref_df))
                model = LinearRegression()
                x_values = channel_df[["co2_std"]].iloc[:sample_count].values
                y_values = ref_df["co2_smooth"].iloc[:sample_count].values
                model.fit(x_values, y_values)

                coef_k = max(0.95, min(1.05, float(model.coef_[0])))
                coef_b = float(y_values.mean() - coef_k * x_values.mean())
                coefficient_items.append(
                    {
                        "channel": channel,
                        "coef_k": round(coef_k, 6),
                        "coef_b": round(coef_b, 4),
                    }
                )

            self._write_config(coefficient_items)
            return True
        except Exception:
            return False

    def _write_config(self, coefficient_items):
        config = {
            "version": "2.0",
            "sensor_model": "GS5T",
            "calibration_info": {
                "calibration_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "calibration_points": self.target_points,
                "method": "Air_Consistency_Alignment_SingleVar",
            },
            "channels": {},
        }

        for item in coefficient_items:
            config["channels"][item["channel"]] = {
                "coef_k": item["coef_k"],
                "coef_b": item["coef_b"],
            }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def get_status(self):
        with self.lock:
            counts = {channel: len(self.data[channel]) for channel in self.channels}
            return {
                "is_active": self.is_active,
                "calibrated": self.calibrated,
                "current_counts": counts,
                "target_points": self.target_points,
                "all_ready": all(count >= self.target_points for count in counts.values()),
                "config_path": str(self.config_path),
            }
