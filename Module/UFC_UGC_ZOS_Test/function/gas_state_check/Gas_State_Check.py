import abc
import time

from PyQt6.QtCore import pyqtSignal


from loguru import logger

from Module.UFC_UGC_ZOS_Test.util.time_util import time_util


class Gas_State_Check:
    """
    气路状态检测
    """
    def __init__(self):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: pyqtSignal(str) = None
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
        self.update_status_main_signal_gui_update.emit(f"{time_util.get_format_from_time(time.time())} | UFC Gas State Check")
        resolve()
        pass