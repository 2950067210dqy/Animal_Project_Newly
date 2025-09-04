import abc
import time

from PyQt6.QtCore import pyqtSignal
from loguru import logger

from Module.UFC_UGC_ZOS_Test.util.time_util import time_util


class Gas_Carlibration:
    """
    气路标定 零点标定和量程标定的父类
    """

    def __init__(self):
        #更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update:pyqtSignal(str) = None
        # 发送报文线程
        self.send_thread = None
        # 发送的数据结构
        self.send_message = {
            'port': '',
            'data': '',
            'slave_id': 0,
            'function_code': 0,
            'timeout': 0
        }
        pass
    def send_data(self):
        # 发送数据
        try:
            if self.send_thread is None:
                return
                # 发送
            logger.info("未初始化串口对象,使用之前串口实例化对象")
            self.send_thread.set_send_message(self.send_message)
            self.send_thread.is_start = True
        except Exception as e:
            logger.error(e)
    @abc.abstractmethod
    def calibrate(self,resolve,reject):
        """
        标定
        :return:
        """
        pass

class Zero_Carlibration(Gas_Carlibration):
    """
    零点标定
    """
    def __init__(self):
        super().__init__()
    def calibrate(self,resolve,reject):
        """零点标定"""
        self.update_status_main_signal_gui_update.emit(f"{time_util.get_format_from_time(time.time())} | Zero Carlibration")
        resolve()
        pass
class Range_Carlibration(Gas_Carlibration):
    """
    量程标定
    """
    def __init__(self):
        super().__init__()
        pass
    def calibrate(self,resolve,reject):
        """量程标定"""
        self.update_status_main_signal_gui_update.emit(f"{time_util.get_format_from_time(time.time())} | Range Carlibration")
        resolve()
        pass