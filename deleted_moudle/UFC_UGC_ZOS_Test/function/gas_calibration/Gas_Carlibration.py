import abc
import copy
import time

from PyQt6.QtCore import pyqtSignal

from Module.UFC_UGC_ZOS_Test.config_class.global_setting import global_setting
from Module.UFC_UGC_ZOS_Test.function.Send_Message.Send_Message import Send_Message
from Module.UFC_UGC_ZOS_Test.function.promise.AsyPromise import AsyPromise
from Module.UFC_UGC_ZOS_Test.util.number_util import number_util
from Module.UFC_UGC_ZOS_Test.util.time_util import time_util

# 前面测量的氧气值
last_oxygen_value = 0
# 前面测量的二氧化碳值
last_carbon_value = 0

#量程标定的前面测量的氧气值
last_span_oxygen_value = 0

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
        self.send_thread: Send_Message = Send_Message(update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,send_message=self.send_message)

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
        # resolve()
        # 1.ugc sample电磁阀关闭
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.emit(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 1.ugc sample电磁阀关闭")
        AsyPromise(self.send_thread.Send).then(
            # 2.校零气路（Zero气）电磁阀开
            lambda r: AsyPromise(self.solenoid_valve_of_zero_gas_open,port=port),resolve()
        ).catch(lambda e: print(e))
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
            lambda r: AsyPromise(self.cyclic_sampling_of_ugc_carbon_sensor_and_zos_oxygen_sensor, port=port),resolve()
        ).catch(lambda e: reject(e))
        pass
    # 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。
    def cyclic_sampling_of_ugc_carbon_sensor_and_zos_oxygen_sensor(self, resolve, reject, port):
        global last_carbon_value,last_oxygen_value
        #现在测量的氧气值
        now_oxygen_value = None
        #现在测量的二氧化碳值
        now_carbon_value = None

        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。")
        #小于阈值稳定
        while (now_oxygen_value is  None and now_carbon_value is  None) or(last_carbon_value is None and last_oxygen_value is None) or (
                now_oxygen_value-last_oxygen_value)>float(global_setting.get_setting("UFC_UGC_ZOS_config")['Calibration']['zero_calibration_oxygen_threshold'] and
                now_carbon_value - last_carbon_value) > float(global_setting.get_setting("UFC_UGC_ZOS_config")['Calibration']['zero_calibration_carbon_threshold']):
            # 循环开始
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
            carbon_data, carbon_message =self.send_thread.Send_no_promise()
            now_carbon_values = [item['value'] for item in carbon_data['data'] if "CO2" in item['desc']]
            last_carbon_value = copy.deepcopy(now_carbon_value)
            now_carbon_value =now_carbon_values[0] if  now_carbon_values else None
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
            oxygen_data,oxygen_message =  self.send_thread.Send_no_promise()
            now_oxygen_values = [item['value'] for item in oxygen_data['data'] if "氧传感器测量值" in item['desc']]
            last_oxygen_value = copy.deepcopy(now_oxygen_value)
            now_oxygen_value = now_oxygen_values[0] if now_oxygen_values else None
            self.update_status_main_signal_gui_update.emit(
                f"{time_util.get_format_from_time(time.time())} |  零点标定 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。3）现在氧气浓度（{now_oxygen_value}）之前氧气浓度（{last_oxygen_value}）|现在co2浓度（{now_carbon_value}）之前co2浓度（{last_carbon_value}）")
            pass
        #4.二氧化碳零点设置。
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00100000"),
            'slave_id': '3',
            'function_code': '6',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 4.二氧化碳零点设置")
        AsyPromise(self.send_thread.Send).then(
            # 5.氧浓传感器零点记录。
            lambda r: AsyPromise(self.zero_point_recording_of_oxygen_sensor, port=port),resolve()
        ).catch(lambda e: reject(e))
        pass
    # 5.氧浓传感器零点记录。
    def zero_point_recording_of_oxygen_sensor(self,resolve,reject,port):
        # 采集氧气
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("2"),
            'slave_id': '4',
            'function_code': '4',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message

        oxygen_data, oxygen_message = self.send_thread.Send_no_promise()
        now_oxygen_values = [item['value'] for item in oxygen_data['data'] if "氧传感器测量值" in item['desc']]
        now_oxygen_value = now_oxygen_values[0] if now_oxygen_values else None
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 5.氧浓传感器零点记录值{now_oxygen_value}")
        # 存储值----------------------------------------------------

        # 6.校零气路（Zero气）电磁阀关。
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00010000"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 6.校零气路（Zero气）电磁阀关")
        AsyPromise(self.send_thread.Send).then(
            # 7 ugc sample电磁阀打开。
            lambda r: AsyPromise(self.ugc_sample_open, port=port
                               ),resolve()
        ).catch(lambda e: reject(e))
        pass
    # 7 ugc sample电磁阀打开
    def ugc_sample_open(self,resolve,reject,port):
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0000FF00"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 7 ugc sample电磁阀打开")
        AsyPromise(self.send_thread.Send).then(
            # 7 ugc sample电磁阀打开。
            lambda r: resolve()
        ).catch(lambda e: reject(e))
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
        self.update_status_main_signal_gui_update.emit(f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 开始{'.' * 100}")
        # resolve()
        #1.ugc sample电磁阀关闭
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.emit(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |   SPan量程标定 1.ugc sample电磁阀关闭")
        AsyPromise(self.send_thread.Send).then(
            # 2.ugc span电磁阀打开。
            lambda r: AsyPromise(self.ugc_span_open,port=port),resolve()
        ).catch(lambda e: print(e))
        pass
    def ugc_span_open(self,resolve,reject,port):
        # 2.ugc span电磁阀打开。
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0002FF00"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |   SPan量程标定 2.ugc span电磁阀打开。")
        AsyPromise(self.send_thread.Send).then(
            # 3.循环采样zos氧浓度
            lambda r: AsyPromise(self.cyclic_sampling_of_zos_oxygen_sensor, port=port),resolve()
        ).catch(lambda e: print(e))
        pass
    def cyclic_sampling_of_zos_oxygen_sensor(self,resolve,reject,port):
        # 3.循环采样zos氧浓度
        global last_oxygen_value
        # 现在测量的氧气值
        now_oxygen_value = None


        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 3.循环采样zos氧浓度。")
        # 小于阈值稳定
        while (now_oxygen_value is None ) or (
                 last_oxygen_value is None) or (
                now_oxygen_value - last_oxygen_value) > float(
            global_setting.get_setting("UFC_UGC_ZOS_config")['Calibration']['span_calibration_oxygen_threshold']):
            # 循环开始
            self.send_message = {
                'port': port,
                'data': number_util.set_int_to_4_bytes_list("2"),
                'slave_id': '4',
                'function_code': '4',
                'timeout': 1
            }
            self.send_thread.send_message = self.send_message
            self.update_status_main_signal_gui_update.emit(
                f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 3.循环采样zos氧浓度。1)采样zos氧气浓度")
            oxygen_data, oxygen_message = self.send_thread.Send_no_promise()
            now_oxygen_values = [item['value'] for item in oxygen_data['data'] if "氧传感器测量值" in item['desc']]
            last_oxygen_value = copy.deepcopy(now_oxygen_value)
            now_oxygen_value = now_oxygen_values[0] if now_oxygen_values else None
            self.update_status_main_signal_gui_update.emit(
                f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 3.循环采样zos氧浓度。2）现在氧气浓度（{now_oxygen_value}）之前氧气浓度（{last_oxygen_value}）")
            pass
        # 5. 氧浓传感器span数值记录。
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("2"),
            'slave_id': '4',
            'function_code': '4',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message

        oxygen_data, oxygen_message = self.send_thread.Send_no_promise()
        now_oxygen_values = [item['value'] for item in oxygen_data['data'] if "氧传感器测量值" in item['desc']]
        now_oxygen_value = now_oxygen_values[0] if now_oxygen_values else None
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 5.氧浓传感器span数值记录。{now_oxygen_value}")
        # 存储值----------------------------------------------------

        # 6.ugc span电磁阀关闭。
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00020000"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 6.ugc span电磁阀关闭")
        AsyPromise(self.send_thread.Send).then(
            # 7 ugc sample电磁阀打开。
            lambda r: AsyPromise(self.ugc_sample_open, port=port
                                 ),resolve()
        ).catch(lambda e: reject(e))

    # 7 ugc sample电磁阀打开
    def ugc_sample_open(self, resolve, reject, port):
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0000FF00"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.emit(
            f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 7. ugc sample电磁阀打开")
        AsyPromise(self.send_thread.Send).then(
            # 7 ugc sample电磁阀打开。
            lambda r: resolve()
        ).catch(lambda e: reject(e))
        pass
    pass
