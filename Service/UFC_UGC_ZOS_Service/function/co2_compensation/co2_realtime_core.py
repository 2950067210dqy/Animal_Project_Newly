import json
import math
from pathlib import Path

import pandas as pd


def get_default_config_path():
    return Path(__file__).resolve().parents[4] / "config" / "co2_calib_config.json"


class CO2RealtimeCompensator:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path or get_default_config_path())
        self.channels = ["REF"] + [f"M{i}" for i in range(1, 9)]
        self.last_valid = {ch: None for ch in self.channels}
        self._config_mtime = None
        self.config = {"channels": {}}
        self.coefs = {}
        self.reload_config(force=True)

    def reload_config(self, force=False):
        try:
            current_mtime = self.config_path.stat().st_mtime
        except OSError:
            current_mtime = None

        if not force and current_mtime == self._config_mtime:
            return

        self._config_mtime = current_mtime
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception:
            self.config = {"channels": {}}

        self.coefs = {}
        for channel, data in self.config.get("channels", {}).items():
            self.coefs[channel] = {
                "coef_k": float(data.get("coef_k", 1.0)),
                "coef_b": float(data.get("coef_b", 0.0)),
            }

    def compensate(self, channel, co2_std):
        self.reload_config()

        if channel not in self.channels:
            return float("nan")

        value = float(co2_std)
        if pd.isna(value) or value < 0 or value > 10000:
            if self.last_valid[channel] is None:
                return float("nan")
            value = self.last_valid[channel]
        else:
            self.last_valid[channel] = value

        if channel == "REF":
            return round(value, 2)

        coef = self.coefs.get(channel)
        if coef is None:
            return float("nan")

        compensated = coef["coef_k"] * value + coef["coef_b"]
        if math.isnan(compensated):
            return float("nan")
        if compensated < 0:
            compensated = 0.0
        return round(compensated, 2)
