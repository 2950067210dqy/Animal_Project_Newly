import abc
import re
import time

from blinker.base import _PNamespaceSignal
from loguru import logger

from Service.UFC_UGC_ZOS_Service.function.Send_Message.Send_Message import Send_Message
from public.config_class.global_setting import global_setting
from public.util.number_util import number_util
from public.util.time_util import time_util

#logger = logger.bind(category="deep_camera_logger")
class Gas_State_Check:
    """
    气路状态检测
    """

    def __init__(self):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: _PNamespaceSignal = None

        # 发送的数据结构
        self.send_message = {
            'port': '',
            'data': '',
            'slave_id': 0,
            'function_code': 0,
            'timeout': 0
        }
        # 发送报文线程
        self.send_thread: Send_Message = Send_Message(
            update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,
            send_message=self.send_message)
    def update(self):
        self.send_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
    @abc.abstractmethod
    def state_check(self,resolve,reject):
        """
        状态检测
        :return:
        """
        pass
class UFC_Gas_State_Check(Gas_State_Check):
    """
    UFC 状态检测
    """
    def __init__(self):
        super().__init__()
        pass

    def state_check(self, resolve, reject):
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 开始"
        )

        port = global_setting.get_setting("port", None)
        if port is None:
            msg = f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！"
            self.update_status_main_signal_gui_update.send(msg)
            reject(msg)
            return

        # ============================================================
        # 1. 读端口输出状态（软检测）
        # 新协议写了 02 01 00 00 00 0C，但当前设备实际可能不响应
        # 所以：能读就解析，读不到只记日志，不作为失败条件
        # ============================================================
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0000000C"),
            'slave_id': '2',
            'function_code': '1',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 1. 读端口输出状态"
        )

        data, message = self.send_thread.Send_no_promise()

        pump_state = None
        machine_state = None

        if not data or 'data' not in data:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 1 跳过：设备未响应 | {message}"
            )
        else:
            coil_data = data.get('data', [])

            for item in coil_data:
                desc = str(item.get('desc', ''))
                value = item.get('value', None)

                if '气泵' in desc:
                    pump_state = value
                elif '机器状态' in desc or 'UFC状态' in desc or '运行状态' in desc:
                    machine_state = value

            # 兼容旧解析器没有 desc 的情况
            if pump_state is None and len(coil_data) > 2:
                pump_state = coil_data[2].get('value', None)
            if machine_state is None and len(coil_data) > 3:
                machine_state = coil_data[3].get('value', None)

            if pump_state != 1:
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 1.1 气泵状态异常：{pump_state}"
                )
            if machine_state != 1:
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 1.2 机器运行状态异常：{machine_state}"
                )

        # ============================================================
        # 2. 读流量控制器状态（主检测）
        # 02 02 00 00 00 09
        # D0 = 参考气
        # D1~D8 = 流量传感器1~8
        # ============================================================
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00000009"),
            'slave_id': '2',
            'function_code': '2',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 2. 读流量控制器状态"
        )

        flow_data, flow_message = self.send_thread.Send_no_promise()
        if not flow_data or 'data' not in flow_data:
            msg = f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 2 无响应（警告）：{flow_message}"
            self.update_status_main_signal_gui_update.send(msg)
            logger.warning(msg)
            resolve()
            return

        flow_coils = flow_data.get('data', [])
        ref_flow = None
        cage_flow_state_map = {}

        # 优先按 desc 解析
        for item in flow_coils:
            desc = str(item.get('desc', ''))
            value = item.get('value', None)

            if '参考气' in desc:
                ref_flow = value
            elif '流量传感器' in desc:
                nums = re.findall(r'\d+', desc)
                if nums:
                    cage_no = int(nums[0])  # 1~8
                    cage_flow_state_map[cage_no] = value

        # 如果解析器没给 desc，退回索引解析
        if ref_flow is None and len(flow_coils) > 0:
            ref_flow = flow_coils[0].get('value', None)

        if not cage_flow_state_map and len(flow_coils) >= 9:
            for i, coil in enumerate(flow_coils[1:9], start=1):
                cage_flow_state_map[i] = coil.get('value', None)

        if ref_flow != 1:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 2.1 参考气流量传感器异常：{ref_flow}"
            )

        setting_mouse_cages = global_setting.get_setting("mouse_cages", [])

        abnormal_cages = []
        unknown_cages = []

        for cage_no in setting_mouse_cages:
            # 如果 mouse_cages 存的是 0~7，请改成 cage_no = cage_no + 1
            if cage_no not in cage_flow_state_map:
                unknown_cages.append(cage_no)
            elif cage_flow_state_map[cage_no] != 1:
                abnormal_cages.append(cage_no)

        if abnormal_cages:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 2.2 选中鼠笼流量传感器异常：{abnormal_cages}"
            )

        if unknown_cages:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 2.3 未解析到的鼠笼流量传感器：{unknown_cages}"
            )

        resolve()