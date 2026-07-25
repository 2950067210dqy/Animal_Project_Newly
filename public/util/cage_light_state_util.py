import json
import os
import time
from pathlib import Path
from typing import Iterable, List

from loguru import logger

from public.util.time_util import time_util


CAGE_CONFIG_DIR = Path.home() / ".mouse_experiment_config" / "cage_configs"
LIGHT_MODULE = "EM"
LIGHT_CONFIG_KEY = "config_0"


def _normalize_cage_numbers(cage_numbers: Iterable) -> List[int]:
    cages = []
    if cage_numbers is None:
        return cages
    for cage_number in cage_numbers:
        try:
            cage_number = int(cage_number)
        except (TypeError, ValueError):
            continue
        if cage_number > 0 and cage_number not in cages:
            cages.append(cage_number)
    return cages


def _load_cage_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"load cage light config failed: path={path}, error={e}")
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp_path.replace(path)


def force_save_cage_lights_off(cage_numbers: Iterable) -> List[int]:
    """Synchronize local cage config so the setup UI opens with lamps off."""
    saved_cages = []
    for cage_number in _normalize_cage_numbers(cage_numbers):
        config_path = CAGE_CONFIG_DIR / f"cage_{cage_number}_config.json"
        config_data = _load_cage_config(config_path)

        config_data["timestamp"] = time_util.get_format_from_time(time.time())
        config_data["cage_id"] = cage_number

        light_module = config_data.setdefault(LIGHT_MODULE, {})
        if not isinstance(light_module, dict):
            light_module = {}
            config_data[LIGHT_MODULE] = light_module
        light_module[LIGHT_CONFIG_KEY] = "off"

        dwm_module = config_data.get("DWM")
        if isinstance(dwm_module, dict) and LIGHT_CONFIG_KEY in dwm_module:
            dwm_module[LIGHT_CONFIG_KEY] = "off"

        _atomic_write_json(config_path, config_data)
        saved_cages.append(cage_number)
        logger.info(f"shutdown light state saved: cage={cage_number}, path={config_path}")
    return saved_cages
