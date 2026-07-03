import copy
import time

from blinker.base import _PNamespaceSignal
from loguru import logger

from Service.UFC_UGC_ZOS_Service.function.Send_Message.Send_Message import Send_Message
from public.config_class.global_setting import global_setting
from public.entity.enum.Public_Enum import GapSystem_Running_Type
from public.function.promise.AsyPromise import AsyPromise
from public.util.number_util import number_util
from public.util.time_util import time_util


class Startup_Air_Calibration:
    def __init__(self, title=GapSystem_Running_Type.STARTUP_AIR_CALIBRATION):
        self.title = title
        self.name = "运行前 Air 空气校准"
        self.update_status_main_signal_gui_update: _PNamespaceSignal = None
        self.send_message = {
            'port': '',
            'data': '',
            'slave_id': 0,
            'function_code': 0,
            'timeout': 0
        }
        self.send_thread = Send_Message(
            update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,
            send_message=self.send_message,
            update_status_main_signal_gui_update_type=title
        )
        self.current_calibration_values = {
            'oxygen_value': None,
            'carbon_value': None,
            'oxygen_pressure_value': None,
        }
        self.calibration_handler = None
        self.previous_valid_snapshots = {}

    def update(self):
        self.send_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update

    def _send_text(self, text):
        if self.update_status_main_signal_gui_update is not None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | {text}",
                title=self.title
            )

    def _send_state(self, state_type, value):
        if self.update_status_main_signal_gui_update is not None:
            self.update_status_main_signal_gui_update.send(
                {'type': state_type, 'value': value},
                title=self.title
            )

    def push_calibration_values_to_ui(self, oxygen_value=None, oxygen_pressure_value=None):
        if oxygen_value is not None:
            self.current_calibration_values['oxygen_value'] = oxygen_value
        if oxygen_pressure_value is not None:
            self.current_calibration_values['oxygen_pressure_value'] = oxygen_pressure_value

        if self.update_status_main_signal_gui_update is not None:
            self.update_status_main_signal_gui_update.send(
                {
                    'type': 'set_calibration_values',
                    'value': copy.deepcopy(self.current_calibration_values)
                },
                title=self.title
            )

    @staticmethod
    def _is_zero_value(value):
        try:
            return float(value) == 0.0
        except (TypeError, ValueError):
            return False

    def _normalize_snapshot_with_previous(self, channel, snapshot):
        if snapshot is None:
            return None

        fields = (
            "o2_partial",
            "zos_temp",
            "gas_pressure",
            "o2_percent",
            "sht_temp",
            "sht_rh",
        )
        previous_snapshot = self.previous_valid_snapshots.get(channel)
        normalized_snapshot = dict(snapshot)

        for field in fields:
            current_value = normalized_snapshot.get(field)
            if not self._is_zero_value(current_value):
                continue

            previous_value = previous_snapshot.get(field) if previous_snapshot else None
            if previous_value not in (None, 0, 0.0):
                normalized_snapshot[field] = previous_value
                logger.warning(
                    f"{self.name}：通道 {channel} 的 {field} 返回0，已使用前值覆盖：{previous_value}"
                )

        merged_snapshot = dict(previous_snapshot) if previous_snapshot else {}
        for field in fields:
            current_value = normalized_snapshot.get(field)
            if not self._is_zero_value(current_value):
                merged_snapshot[field] = current_value
        if merged_snapshot:
            self.previous_valid_snapshots[channel] = merged_snapshot

        return normalized_snapshot

    @staticmethod
    def _normalize_startup_wait_seconds():
        calibration_config = global_setting.get_setting("UFC_UGC_ZOS_config", {}).get("Calibration", {})
        try:
            wait_seconds = int(float(calibration_config.get("startup_air_calibration_wait_time", 1800)))
        except Exception:
            wait_seconds = 1800
        return max(wait_seconds, 0)

    @staticmethod
    def _normalize_sample_interval():
        calibration_config = global_setting.get_setting("UFC_UGC_ZOS_config", {}).get("Calibration", {})
        try:
            sample_interval = float(calibration_config.get('calibration_sample_interval', 1))
        except Exception:
            sample_interval = 1.0
        return max(sample_interval, 0.5)

    @staticmethod
    def _normalize_target_points():
        calibration_config = global_setting.get_setting("UFC_UGC_ZOS_config", {}).get("Calibration", {})
        try:
            target_points = int(float(calibration_config.get('startup_air_calibration_target_points', 120)))
        except Exception:
            target_points = 120
        return max(target_points, 1)

    @staticmethod
    def _normalize_run_timeout(target_points, sample_interval):
        calibration_config = global_setting.get_setting("UFC_UGC_ZOS_config", {}).get("Calibration", {})
        default_timeout = max(int(target_points * sample_interval * 3), 300)
        try:
            max_timeout = int(float(calibration_config.get('startup_air_calibration_max_timeout', default_timeout)))
        except Exception:
            max_timeout = default_timeout
        return max(max_timeout, default_timeout)

    @staticmethod
    def _normalize_oxygen_percent(value):
        value = float(value)
        if value > 100:
            value = value / 100
        return value

    @staticmethod
    def _extract_data_value(data_items, keyword):
        for item in data_items or []:
            desc = str(item.get("desc", ""))
            if keyword in desc:
                return item.get("value")
        return None

    @staticmethod
    def _channel_to_handler_name(channel):
        if int(channel) == 8:
            return "REF"
        return f"M{int(channel) + 1}"

    @staticmethod
    def _channel_to_display_name(channel):
        if int(channel) == 8:
            return "参考气"
        return f"{int(channel) + 1}号鼠笼"

    def _get_port(self):
        return global_setting.get_setting("port", None)

    def _get_active_channels(self):
        return list(range(9))

    def _build_calibration_handler(self):
        try:
            from Service.UFC_UGC_ZOS_Service.function.o2_compensation.calibration_handler import CalibrationHandler
        except Exception as e:
            raise RuntimeError(f"加载 CalibrationHandler 失败: {e}")

        self.calibration_handler = CalibrationHandler(target_points=self._normalize_target_points())
        self.calibration_handler.start_new_calibration()
        self.previous_valid_snapshots = {}

    def _read_zos_channel_snapshot(self, channel):
        port = self._get_port()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"00{int(channel):02X}000E"),
            'slave_id': '4',
            'function_code': '4',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        result_data, _ = self.send_thread.Send_no_promise()
        if not result_data or 'data' not in result_data:
            return None

        data_items = result_data.get('data', [])
        o2_partial = self._extract_data_value(data_items, "氧分压")
        zos_temp = self._extract_data_value(data_items, "ZOS温度测量值")
        gas_pressure = self._extract_data_value(data_items, "气体压力")
        o2_percent = self._extract_data_value(data_items, "氧浓度")
        sht_temp = self._extract_data_value(data_items, "ZOS温度2测量值")
        sht_rh = self._extract_data_value(data_items, "ZOS湿度测量值")

        if None in [o2_partial, zos_temp, gas_pressure, o2_percent, sht_temp, sht_rh]:
            return None

        o2_percent = self._normalize_oxygen_percent(o2_percent)
        return {
            "o2_partial": float(o2_partial),
            "zos_temp": float(zos_temp),
            "gas_pressure": float(gas_pressure),
            "o2_percent": float(o2_percent),
            "sht_temp": float(sht_temp),
            "sht_rh": float(sht_rh),
        }

    def start(self, resolve, reject):
        port = self._get_port()
        if port is None:
            reject("未选择串口，无法执行运行前 Air 空气校准")
            return

        start_time_text = time_util.get_format_from_time(time.time())
        self._send_state('set_start_air_calibration_time', start_time_text)
        self._send_text(f"{self.name}开始：发送 ZOS Air 校准开始指令")
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0009FF00"),
            'slave_id': '4',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda _: resolve()
        ).catch(lambda e: reject(e))

    def wait_air_calibration_prepare(self, resolve, reject):
        wait_seconds = self._normalize_startup_wait_seconds()
        if wait_seconds == 0:
            self._send_text(f"{self.name}等待阶段已跳过")
            resolve()
            return

        for second in range(wait_seconds):
            if second == 0 or (second + 1) % 5 == 0 or second == wait_seconds - 1:
                self._send_text(
                    f"{self.name}等待稳定：当前等待 {second + 1}/{wait_seconds} 秒"
                )
            time.sleep(1)
        resolve()

    def run(self, resolve, reject):
        port = self._get_port()
        if port is None:
            reject("未选择串口，无法执行运行前 Air 空气校准")
            return

        active_channels = self._get_active_channels()
        if len(active_channels) == 0:
            reject("未配置 mouse_cages，无法执行运行前 Air 空气校准")
            return

        try:
            self._build_calibration_handler()
        except Exception as e:
            reject(str(e))
            return

        sample_interval = self._normalize_sample_interval()
        target_points = self._normalize_target_points()
        max_timeout = self._normalize_run_timeout(target_points, sample_interval)
        last_progress_log_time = 0.0
        start_time = time.time()

        self._send_text(
            f"{self.name}开始采集 9 路氧浓度信息并执行 CalibrationHandler 判定，目标点数 {target_points}"
        )

        while True:
            elapsed_time = time.time() - start_time
            if elapsed_time > max_timeout:
                reject(f"{self.name}超时，已运行 {int(elapsed_time)} 秒")
                return

            for channel in active_channels:
                snapshot = self._read_zos_channel_snapshot(channel)
                if snapshot is None:
                    logger.warning(f"{self.name}读取 {self._channel_to_display_name(channel)} 数据失败")
                    continue
                snapshot = self._normalize_snapshot_with_previous(channel, snapshot)

                self.push_calibration_values_to_ui(
                    oxygen_value=snapshot["o2_percent"],
                    oxygen_pressure_value=snapshot["gas_pressure"]
                )
                try:
                    finished = self.calibration_handler.add_data(
                        self._channel_to_handler_name(channel),
                        snapshot["o2_partial"],
                        snapshot["zos_temp"],
                        snapshot["gas_pressure"],
                        snapshot["o2_percent"],
                        snapshot["sht_temp"],
                        snapshot["sht_rh"]
                    )
                except Exception as e:
                    reject(f"{self.name}执行 CalibrationHandler 失败: {e}")
                    return

                if finished:
                    self._send_text(f"{self.name}判定完成，CalibrationHandler 已输出补偿系数")
                    resolve()
                    return

            current_time = time.time()
            if current_time - last_progress_log_time >= 5:
                status = self.calibration_handler.get_status()
                counts = status.get("current_counts", {})
                progress_parts = [
                    f"REF={counts.get('REF', 0)}/{target_points}"
                ]
                for idx in range(1, 9):
                    channel_name = f"M{idx}"
                    progress_parts.append(
                        f"{channel_name}={counts.get(channel_name, 0)}/{target_points}"
                    )
                self._send_text(
                    f"{self.name}采集中：{'，'.join(progress_parts)}，已运行 {int(elapsed_time)}/{int(max_timeout)} 秒"
                )
                last_progress_log_time = current_time

            time.sleep(sample_interval)

    def stop(self, resolve, reject):
        port = self._get_port()
        if port is None:
            reject("未选择串口，无法执行运行前 Air 空气校准")
            return

        self._send_text(f"{self.name}结束：发送 ZOS Air 校准结束指令")
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00090000"),
            'slave_id': '4',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda _: self._finish_stop(resolve)
        ).catch(lambda e: reject(e))

    def _finish_stop(self, resolve):
        stop_time_text = time_util.get_format_from_time(time.time())
        self._send_state('set_stop_air_calibration_time', stop_time_text)
        resolve()
