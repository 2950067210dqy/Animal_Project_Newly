import abc
import time
import re

from PyQt6.QtCore import pyqtSignal


from loguru import logger

from Module.UFC_UGC_ZOS_Test.config_class.global_setting import global_setting
from Module.UFC_UGC_ZOS_Test.function.Send_Message.Send_Message import Send_Message
from Module.UFC_UGC_ZOS_Test.function.promise.AsyPromise import AsyPromise
from Module.UFC_UGC_ZOS_Test.util.number_util import number_util
from Module.UFC_UGC_ZOS_Test.util.time_util import time_util


class Gas_State_Check:
    """
    气路状态检测
    """

    def __init__(self):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: pyqtSignal(str) = None

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
    def state_check(self,resolve,reject):
        """
        UFC 状态检测
        :return:
        """
        self.update_status_main_signal_gui_update.emit(f"{time_util.get_format_from_time(time.time())} | UFC 状态检测 开始{'-'*50}")
        # resolve()
        #1.端口输出状态是否正确，确认与程序逻辑是否一致，否则报错
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.emit(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("C"),
            'slave_id': '2',
            'function_code': '1',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  UFC 状态检测 1.端口输出状态是否正确，确认与程序逻辑是否一致，否则报错")
        data,message = self.send_thread.Send_no_promise()
        # print(f"{data},{message}")
        # print(f"原来的设置：{setting_mouse_cages},{setting_mouse_cages_2byte_str}")
        setting_mouse_cages = global_setting.get_setting("mouse_cages", [0, 1, 2, 3, 4, 5, 6, 7])
        setting_mouse_cages_2byte_str = global_setting.get_setting("mouse_cages_2byte_str", "11111111")
        state_datas = [item for item in data['data'] if '鼠笼' in item['desc']]
        is_Error =False
        # 方法1：提取所有整数
        data_mouse_cages=[]
        for state_data in state_datas:
            integers = int(re.findall(r'\d+', state_data))
            data_mouse_cages.append(integers)
            if integers-1 not  in setting_mouse_cages:
                is_Error = True
        # 报错
        if is_Error:
            self.update_status_main_signal_gui_update.emit(
                f"{time_util.get_format_from_time(time.time())} |  UFC 状态检测 1.端口输出状态与程序逻辑不一致|端口响应状态：{data_mouse_cages}|软件设置的端口状态：{setting_mouse_cages}")


        # 2.读取流量控制器状态，判断所运行的鼠笼的是否正常
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("8"),
            'slave_id': '2',
            'function_code': '2',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  UFC 状态检测 2.读取流量控制器状态，判断所运行的鼠笼的是否正常")
        flow_data, flow_message = self.send_thread.Send_no_promise()

        resolve()

        pass

