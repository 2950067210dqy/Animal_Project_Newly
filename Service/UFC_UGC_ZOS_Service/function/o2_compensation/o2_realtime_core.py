import json
from pathlib import Path

import numpy as np


# 加载校准配置
def load_config():
    config_path = Path(__file__).resolve().parents[4] / "config" / "calib_config.json"
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()
TARGET_O2 = CFG["TARGET_O2"]
BASE_CHANNEL = CFG["BASE_CHANNEL"]  # M2为基线
VALID_CHANNELS = ["REF", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]

# 异常值阈值
O2_UPPER_LIMIT = 23.0
O2_LOWER_LIMIT = 10.0
FILTER_WINDOW = 15

# 全局缓存
FILTER_CACHE = {ch: [] for ch in VALID_CHANNELS}
LAST_VALID_VALUE_CACHE = {ch: TARGET_O2 for ch in VALID_CHANNELS}


# ============================
def calc_dry_o2(o2_wet, temp, rh, press_hpa):
    """干基氧温湿度/气压补偿公式，和离线版完全一致"""
    sat_vp = 0.61094 * np.exp(17.625 * temp / (temp + 243.04))
    actual_vp = sat_vp * rh / 100.0
    dry_press = np.clip(press_hpa - actual_vp, 1.0, 1000)
    dry_o2 = o2_wet * (press_hpa / dry_press)
    return dry_o2


def real_time_filter(channel, value):
    """实时滑动滤波，和离线版rolling窗口逻辑100%一致"""
    cache = FILTER_CACHE[channel]
    cache.append(value)
    if len(cache) > FILTER_WINDOW:
        cache.pop(0)
    return float(np.mean(cache))


# ============================
def calculate_o2_compensated(
        channel_id,
        o2_partial_press,
        temp_sensor,
        gas_total_press,
        o2_raw_pct,
        temp_cage,
        rh_cage
):
    # 1. 校验通道有效性
    if channel_id not in VALID_CHANNELS:
        return -1

    # 2. 读取该通道的校准系数
    K = CFG[channel_id]["K"]
    B = CFG[channel_id]["B"]

    # 3.计算
    dry_o2 = calc_dry_o2(o2_raw_pct, temp_cage, rh_cage, gas_total_press)
    calib_o2 = dry_o2 * K + B
    if channel_id == BASE_CHANNEL:
        final_o2 = TARGET_O2
    else:
        final_o2 = calib_o2

    final_o2_filtered = real_time_filter(channel_id, final_o2)

    if final_o2_filtered > O2_UPPER_LIMIT or final_o2_filtered < O2_LOWER_LIMIT:
        final_o2_valid = LAST_VALID_VALUE_CACHE[channel_id]
    else:
        final_o2_valid = final_o2_filtered
        LAST_VALID_VALUE_CACHE[channel_id] = final_o2_valid

    return round(final_o2_valid, 3)
