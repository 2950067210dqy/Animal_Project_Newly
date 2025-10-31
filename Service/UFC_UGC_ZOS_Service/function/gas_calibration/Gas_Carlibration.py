import abc
import copy
import queue
import threading
import time
from datetime import datetime

from blinker.base import _PNamespaceSignal
from loguru import logger

from Service.UFC_UGC_ZOS_Service.function.Send_Message.Send_Message import Send_Message

from public.config_class.global_setting import global_setting
from public.function.Modbus.Modbus_Type import Others_Tables
from public.function.Monitor_data_storage.DataStorage import store_data_with_result

from public.function.promise.AsyPromise import AsyPromise
from public.util.number_util import number_util
from public.util.time_util import time_util
# 前面测量的氧气值
last_oxygen_value = 0
# 前面测量的二氧化碳值
last_carbon_value = 0
#logger = logger.bind(category="deep_camera_logger")
class Gas_Carlibration:
    """
    气路标定 零点标定和量程标定的父类
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
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 开始{'.' * 100}")
        # resolve()
        # 1.ugc sample电磁阀关闭
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
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
        self.update_status_main_signal_gui_update.send(
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
        self.update_status_main_signal_gui_update.send(
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

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。")
        start_time = time.time()
        end_time = None
        #小于阈值稳定0 或者 至少循环60秒
        while (
                (
                        (now_oxygen_value is  None and now_carbon_value is  None) or
                        (last_carbon_value is None and last_oxygen_value is None) or

                        (
                                abs(now_oxygen_value - last_oxygen_value) > float(
                            global_setting.get_setting("UFC_UGC_ZOS_config")['Calibration'][
                                'zero_calibration_oxygen_threshold'])
                                or
                                abs(now_carbon_value - last_carbon_value) > float(
                            global_setting.get_setting("UFC_UGC_ZOS_config")['Calibration'][
                                'zero_calibration_carbon_threshold'])
                        )
                        or
                        (
                                now_carbon_value != 0 or now_oxygen_value != 0
                        )


                ) and
                (
                      end_time is None or int(end_time - start_time) <= float(
                  global_setting.get_setting('UFC_UGC_ZOS_config')['Calibration']['circular_times'])
                )
        ):
            # 循环开始
            self.send_message = {
                'port': port,
                'data': number_util.set_int_to_4_bytes_list("8"),
                'slave_id': '3',
                'function_code': '4',
                'timeout': 1
            }
            self.send_thread.send_message = self.send_message
            self.update_status_main_signal_gui_update.send(
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
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} |  零点标定 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。2）采集氧气浓度")
            oxygen_data,oxygen_message =  self.send_thread.Send_no_promise()
            now_oxygen_values = [item['value'] for item in oxygen_data['data'] if "氧气传感器测量值" in item['desc']]
            last_oxygen_value = copy.deepcopy(now_oxygen_value)
            now_oxygen_value = now_oxygen_values[0] if now_oxygen_values else None
            end_time = time.time()
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} |  零点标定 3.循环采样ugc二氧化碳传感器浓度和zos氧浓度。3）现在氧气浓度（{now_oxygen_value}）之前氧气浓度（{last_oxygen_value}）|现在co2浓度（{now_carbon_value}）之前co2浓度（{last_carbon_value}），已经循环{time_util.format_timedelta(a=datetime.fromtimestamp(end_time),b=datetime.fromtimestamp(start_time),zero_pad=True,signed=True)}/{float(global_setting.get_setting('UFC_UGC_ZOS_config')['Calibration']['circular_times'])}秒")
            time.sleep(1)
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
        self.update_status_main_signal_gui_update.send(
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
        now_oxygen_values = [item['value'] for item in oxygen_data['data'] if "氧气传感器测量值" in item['desc']]
        now_oxygen_value = now_oxygen_values[0] if now_oxygen_values else None
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 5.氧浓传感器零点记录值{now_oxygen_value}")
        # 存储值----------------------------------------------------
        return_data_struct={}
        return_data_struct['module_name']='ZeroCalibration'
        return_data_struct['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        return_data_struct['table_name'] = next(iter(Others_Tables.Zero_Carlibration_Data.value.keys()))
        return_data_struct['mouse_cage_number']=-1
        # 添加Vzero参数到全局变量 方便氧传感器的值校准

        if now_oxygen_value is None:
            return_data_struct['data'] =oxygen_data['data']+ [{'desc': '氧浓度0点校准值', 'value': now_oxygen_value}]
        else:
            global_setting.set_setting("Vzero", now_oxygen_value)
            return_data_struct['data']=[{'desc':'氧浓度0点校准值','value':now_oxygen_value}]
        return_data_struct['slave_id']=0
        return_data_struct['function_code']=0
        result = store_data_with_result(return_data_struct, need_result=True, timeout=5)
        if result and result.success:
            logger.info(f"数据存储成功，ID: {result.item_id}")
        else:
            logger.error(f"数据存储失败: {result.error if result else '未知错误'}")
        # 6.校零气路（Zero气）电磁阀关。
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00010000"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.send(
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
        self.update_status_main_signal_gui_update.send(
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
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 开始{'.' * 100}")
        # resolve()
        #1.ugc sample电磁阀关闭
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
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
        self.update_status_main_signal_gui_update.send(
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
        self.update_status_main_signal_gui_update.send(
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


        self.update_status_main_signal_gui_update.send(
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
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 3.循环采样zos氧浓度。1)采样zos氧气浓度")
            oxygen_data, oxygen_message = self.send_thread.Send_no_promise()
            now_oxygen_values = [item['value'] for item in oxygen_data['data'] if "氧气传感器测量值" in item['desc']]
            last_oxygen_value = copy.deepcopy(now_oxygen_value)
            now_oxygen_value = now_oxygen_values[0] if now_oxygen_values else None
            self.update_status_main_signal_gui_update.send(
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
        now_oxygen_values = [item['value'] for item in oxygen_data['data'] if "氧气传感器测量值" in item['desc']]
        now_oxygen_value = now_oxygen_values[0] if now_oxygen_values else None
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 5.氧浓传感器span数值记录。{now_oxygen_value}")
        # 存储值----------------------------------------------------
        return_data_struct = {}
        return_data_struct['module_name'] = 'SpanCalibration'
        return_data_struct['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        return_data_struct['table_name'] = next(iter(Others_Tables.SPan_Carlibration_Data.value.keys()))
        return_data_struct['mouse_cage_number'] = -1
        # 添加K参数到全局变量 方便氧传感器的值校准 Vr默认是20.9%
        #K=（Vs-Vzero）/（Vr-Vzero）
        if now_oxygen_value is not None:
            K =(now_oxygen_value-global_setting.get_setting("Vzero",0))/(global_setting.get_setting("Vr",20.9)-global_setting.get_setting("Vzero",0))
            logger.warning(f"量程标定的K值为：{K}")
            global_setting.set_setting("K",K )
            return_data_struct['data'] = [{'desc': '氧浓传感器span数值', 'value': now_oxygen_value}]
        else:
            return_data_struct['data'] =oxygen_data['data']+ [{'desc': '氧浓传感器span数值', 'value': now_oxygen_value}]
        return_data_struct['slave_id'] = 0
        return_data_struct['function_code'] = 0
        result = store_data_with_result(return_data_struct, need_result=True, timeout=5)
        if result and result.success:
            logger.info(f"数据存储成功，ID: {result.item_id}")
        else:
            logger.error(f"数据存储失败: {result.error if result else '未知错误'}")
        # 6.ugc span电磁阀关闭。
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00020000"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.send(
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
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 7. ugc sample电磁阀打开")
        AsyPromise(self.send_thread.Send).then(
            # 7 ugc sample电磁阀打开。
            lambda r: resolve()
        ).catch(lambda e: reject(e))
        pass
    pass
