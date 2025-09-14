import abc
import time

from PyQt6.QtCore import pyqtSignal
from loguru import logger

from Service.UFC_UGC_ZOS_Service.function.Send_Message.Send_Message import Send_Message
from public.config_class.global_setting import global_setting

from public.function.promise.AsyPromise import AsyPromise
from public.util.number_util import number_util
from public.util.time_util import time_util

logger = logger.bind(category="monitor_data_logger")
class Gas_Carlibration:
    """
    气路标定 零点标定和量程标定的父类
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
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 开始{'.' * 100}")
        resolve()
        # # 1.ugc sample电磁阀关闭
        # port = global_setting.get_setting("port", None)
        # if port is None:
        #     self.update_status_main_signal_gui_update.emit(
        #         f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
        #     reject()
        # self.send_message = {
        #     'port': port,
        #     'data': number_util.set_int_to_4_bytes_list("0"),
        #     'slave_id': '3',
        #     'function_code': '5',
        #     'timeout': 1
        # }
        #
        # self.send_thread.send_message = self.send_message
        # self.update_status_main_signal_gui_update.emit(
        #     f"{time_util.get_format_from_time(time.time())} |  零点标定 1.ugc sample电磁阀关闭")
        # AsyPromise(self.send_thread.Send).then(
        #     # 2.校零气路（Zero气）电磁阀开
        #     lambda r: AsyPromise(self.solenoid_valve_of_zero_gas_open,port=port, r=r)
        # ).catch(lambda e: print(e))
        pass
    #2.校零气路（Zero气）电磁阀开
    def solenoid_valve_of_zero_gas_open(self,resolve,reject,port):
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0001FF00"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 2.校零气路（Zero气）电磁阀开")
        AsyPromise(self.send_thread.Send).then(
            # 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。
            lambda r: AsyPromise(self.cyclic_sampling_of_ugc_carbon_sensor_and_zos_oxygen_sensor, port=port, r=r)
        ).catch(lambda e: reject(e))
        pass
    # 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。
    def cyclic_sampling_of_ugc_carbon_sensor_and_zos_oxygen_sensor(self,resolve,reject,port):
        #前面测量的氧气值
        last_oxygen_value = 0
        #前面测量的二氧化碳值
        last_carbon_value = 0
        #现在测量的氧气值
        now_oxygen_value = None
        #现在测量的二氧化碳值
        now_carbon_value = None

        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。")
        #小于阈值稳定
        while (now_oxygen_value is  None and now_carbon_value is  None) or (
                now_oxygen_value-last_oxygen_value)>float(global_setting.get_setting("UFC_UGC_ZOS_config")['Calibration']['zero_calibration_oxygen_threshold'] and
                now_carbon_value - last_carbon_value) > float(global_setting.get_setting("UFC_UGC_ZOS_config")['Calibration']['zero_calibration_carbon_threshold']):
            AsyPromise(lambda :self.get_carbon_value(port=port,now_oxygen_value=now_oxygen_value,now_carbon_value=now_carbon_value))

            pass
        #4.二氧化碳零点设置。
        AsyPromise()
        pass
    # 3.1采样ugc二氧化碳传感器浓度。
    def get_carbon_value(self,resolve,reject,port, now_oxygen_value,now_carbon_value):
        # 采集二氧化碳
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("8"),
            'slave_id': '3',
            'function_code': '4',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。1）采集二氧化碳浓度")
        AsyPromise(self.send_thread.Send).then(
            # 3.2采样zos氧浓度
            lambda r: AsyPromise(self.cyclic_sampling_of_ugc_carbon_sensor_and_zos_oxygen_sensor, port=port, carbon_value_Text=r, now_oxygen_value=now_oxygen_value,now_carbon_value=now_carbon_value)
        ).catch(lambda e: reject(e))
        pass
    # 3.2采样zos氧浓度。
    def get_oxygen_value(self,resolve,reject,port,carbon_value_Text ,now_oxygen_value,now_carbon_value):
        # 采集氧气
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("2"),
            'slave_id': '4',
            'function_code': '4',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。2）采集氧气浓度")
        AsyPromise(self.send_thread.Send).then(
            # 3.3获得两个值。
            lambda r: AsyPromise(self.get_value_of_carbon_oxgen, port=port,
                                 carbon_value_Text=carbon_value_Text,oxygen_value_Text=r ,now_oxygen_value=now_oxygen_value,now_carbon_value=now_carbon_value)
        ).catch(lambda e: reject(e))
        pass
    # 3.3获得两个值
    def get_value_of_carbon_oxgen(self,resolve,reject,port,carbon_value_Text,oxygen_value_Text, now_oxygen_value,now_carbon_value):
        now_carbon_value=1
        now_oxygen_value=1
        resolve({'carbon':carbon_value_Text,'oxygen':oxygen_value_Text})
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