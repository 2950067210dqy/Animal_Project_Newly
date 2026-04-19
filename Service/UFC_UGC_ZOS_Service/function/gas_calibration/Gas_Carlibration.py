import abc
import copy
import queue
import threading
import time
from datetime import datetime
from enum import Enum

from blinker.base import _PNamespaceSignal
from loguru import logger

from Service.UFC_UGC_ZOS_Service.function.Send_Message.Send_Message import Send_Message


from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from public.entity.enum.Public_Enum import GapSystem_Running_Type
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Modbus.Modbus_Type import Others_Tables
from public.function.Monitor_data_storage.DataStorage import store_data_with_result

from public.function.promise.AsyPromise import AsyPromise
from public.util.number_util import number_util
from public.util.time_util import time_util
# 前面测量的氧气值
last_oxygen_value = 0
# 前面测量的ZOS气压值
last_pressure_value = 0
# 前面测量的二氧化碳值
last_carbon_value = 0
#logger = logger.bind(category="deep_camera_logger")
# 气路校准类型
class Gas_Carlibration_Type(Enum):
    # 校0
    ZERO = 0
    #校span
    SPAN = 1
    def __lt__(self, other):
        if other is None:
            return False
        return self.value < other.value

    def __le__(self, other):
        if other is None:
            return False
        return self.value <= other.value

    def __gt__(self, other):
        if other is None:
            return False
        return self.value > other.value

    def __ge__(self, other):
        if other is None:
            return False
        return self.value >= other.value
    def __eq__(self, other):
        if other is None:
            return False
        return self.value == other.value
    def __ne__(self, other):
        if other is None:
            return False
        return self.value != other.value
class Gas_Carlibration:
    """
    气路标定 零点标定和量程标定的父类
    """

    def __init__(self,title=GapSystem_Running_Type.DEFAULT,type =Gas_Carlibration_Type.ZERO):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: _PNamespaceSignal = None
        #校0还是校span
        self.type =type
        match self.type:
            case Gas_Carlibration_Type.ZERO:
                self.name="零点标定"
            case Gas_Carlibration_Type.SPAN:
                self.name="SPan量程标定"
            case _:
                self.name="默认标定"
        # 是否  停止标定
        self.is_STOP = False
        # 发送的数据结构
        self.send_message = {
            'port': '',
            'data': '',
            'slave_id': 0,
            'function_code': 0,
            'timeout': 0
        }
        # 发送报文线程
        self.send_thread: Send_Message = Send_Message(update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,send_message=self.send_message,update_status_main_signal_gui_update_type=title)
    def update(self):
        self.send_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.is_STOP = self.is_STOP
    @abc.abstractmethod
    def calibrate(self,resolve,reject):
        """
        标定
        :return:
        """
        pass
    """start   start"""
    # 简化的阀门控制函数
    def open_ugc_zero_or_span_valve(self, resolve, reject, port):
        """打开 UGC Zero/Span 气电磁阀"""
        if self.is_STOP:
            reject("stopped")
            return

        match self.type:
            case Gas_Carlibration_Type.ZERO:
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"00010000"),
                    'slave_id': '3',
                    'function_code': '5',
                    'timeout': 1
                }
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | {self.name}标定： 1. 打开ugc调零阀门")
            case Gas_Carlibration_Type.SPAN:
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"00020000"),
                    'slave_id': '3',
                    'function_code': '5',
                    'timeout': 1
                }
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | {self.name}标定： 1. 打开ugc SPan阀门")
            case _:
                reject("默认标定")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: resolve()
        ).catch(lambda e: reject(e))
    def close_ugc_zero_or_span_valve(self, resolve, reject, port):
        """关闭 UGC Zero/Span 气电磁阀"""
        if self.is_STOP:
            reject("stopped")
            return

        match self.type:
            case Gas_Carlibration_Type.ZERO:
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"0001FF00"),
                    'slave_id': '3',
                    'function_code': '5',
                    'timeout': 1
                }
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | {self.name}标定： 2. 关闭ugc 校0阀门")
            case Gas_Carlibration_Type.SPAN:
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"0002FF00"),
                    'slave_id': '3',
                    'function_code': '5',
                    'timeout': 1
                }
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | {self.name}标定： 2. 关闭ugc SPan阀门")
            case _:
                reject("默认标定")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: resolve()
        ).catch(lambda e: reject(e))
    """start   end"""


    def finish_calibration(self, resolve, reject):
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  {self.name}标定 5. 标定完成", title=self.title)
        # 标定完成通知
        send_message_queue = global_setting.get_setting("send_message_queue")
        match self.type:
            case Gas_Carlibration_Type.SPAN:
                # 给界面进程发送消息
                send_message_queue.put(ObjectQueueItem(origin='Gas_Carlibration', to='monitor_data_new_index',
                                               title='range_calibration_finish',
                                               data=None,
                                               time=time_util.get_format_from_time(time.time())))
                # 发送完成标定消息
                self.update_status_main_signal_gui_update.send(
                    {'type': 'set_stop_span_calibration_time',
                     'value': f'{time_util.get_format_from_time(time.time())}'}, title=self.title
                )
            case Gas_Carlibration_Type.ZERO:
                send_message_queue.put(ObjectQueueItem(origin='Gas_Carlibration', to='monitor_data_new_index',
                                                       title='zero_calibration_finish',
                                                       data=None,
                                                       time=time_util.get_format_from_time(time.time())))
                # 发送完成标定消息
                self.update_status_main_signal_gui_update.send(
                    {'type': 'set_stop_zero_calibration_time',
                     'value': f'{time_util.get_format_from_time(time.time())}'}, title=self.title
                )
            case _:
                pass
        resolve()

    def stop_finish_calibration(self, resolve, reject):
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |   {self.name} 停止标定完成", title=self.title)
        # # 停止标定完成通知
        send_message_queue = global_setting.get_setting("send_message_queue")
        match self.type:
            case Gas_Carlibration_Type.SPAN:
                send_message_queue.put(ObjectQueueItem(origin='Gas_Carlibration', to='monitor_data_new_index',
                                                       title='stop_range_calibration_finish',
                                                       data=None,
                                                       time=time_util.get_format_from_time(time.time())))
                # 发送完成标定消息
                self.update_status_main_signal_gui_update.send(
                    {'type': 'set_stop_span_calibration_time',
                     'value': f'{time_util.get_format_from_time(time.time())}'}, title=self.title
                )
            case Gas_Carlibration_Type.ZERO:
                send_message_queue.put(ObjectQueueItem(origin='Gas_Carlibration', to='monitor_data_new_index',
                                                       title='stop_zero_calibration_finish',
                                                       data=None,
                                                       time=time_util.get_format_from_time(time.time())))
                # 发送完成标定消息
                self.update_status_main_signal_gui_update.send(
                    {'type': 'set_stop_zero_calibration_time',
                     'value': f'{time_util.get_format_from_time(time.time())}'}, title=self.title
                )
            case _:
                pass

        resolve()
    """exit  end"""
class Zero_Carlibration(Gas_Carlibration,MyQThread):
    """
    零点标定
    """
    def __init__(self):
        self.title = GapSystem_Running_Type.ZERO_CALIBRATION
        self.port=None
        Gas_Carlibration.__init__(self, title=self.title,type =Gas_Carlibration_Type.ZERO)

        mouse_cages = global_setting.get_setting("mouse_cages", [])
        num_cages = len(mouse_cages) + 1
        timeout_ms = 300000 + (num_cages * 20000)

        MyQThread.__init__(self, name='Zero_Carlibration_thread', deletion_timeout_ms=timeout_ms)
    def dosomething(self):
        # 新版流程：直接打开 Zero 阀门并开始采样 CO2
        AsyPromise(self.open_ugc_zero_or_span_valve, port=self.port).then(
            lambda r: AsyPromise(self.cyclic_sampling_of_ugc_co2_sensor, port=self.port).then(
                lambda r2: self.stop()
            ).catch(lambda e: self.stop())
        ).catch(lambda e: self.stop())
        pass
    def calibrate(self,resolve,reject):
        """零点标定"""
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  零点标定 开始{'.' * 100}",title=self.title )
        # 发送开始标定消息
        self.update_status_main_signal_gui_update.send(
            {'type': 'set_start_zero_calibration_time', 'value': f'{time_util.get_format_from_time(time.time())}'},
            title=self.title
        )
        self.is_STOP = False
        self.port = global_setting.get_setting("port", None)
        if self.port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！",title=self.title )
            reject()
            return
        if self.is_STOP:
            reject()
            return


        AsyPromise(self.open_ugc_zero_or_span_valve, port=self.port).then(
            lambda _: AsyPromise(self.cyclic_sampling_of_ugc_co2_sensor, port=self.port).then(
                lambda _: resolve()
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))
        pass
    def stop_calibrate(self,resolve,reject):
        """
        取消零点标定（发送零点设置指令 + 关闭阀门，让设备退出标定模式）
        :param resolve:
        :param reject:
        :return:
        """
        self.is_STOP=True
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  停止零点标定", title=self.title)
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 停止失败，未选择串口！", title=self.title)
            reject()
            return

        # 发送零点设置指令，让设备退出标定模式
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00100000"),
            'slave_id': '3',
            'function_code': '6',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | 停止零点标定：发送零点设置指令", title=self.title)

        # 发送指令 -> 关闭阀门 -> 完成
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.close_ugc_zero_or_span_valve, port=port).then(
                lambda r2: AsyPromise(self.stop_finish_calibration).then(lambda r3: resolve()).catch(lambda e: reject(e))
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))

    def cyclic_sampling_of_ugc_co2_sensor(self, resolve, reject, port):
        """
        UGC 零点标定 CO2 采样（逐笼完成）
        按用户开启的笼子顺序，逐个笼子读取并等待稳定后再进入下一个
        """
        if self.is_STOP:
            reject("stopped")
            return

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC零点标定：开始逐笼采样 CO2浓度",
            title=self.title
        )

        config = global_setting.get_setting("UFC_UGC_ZOS_config")
        threshold = float(config['Calibration']['zero_calibration_carbon_threshold'])
        total_timeout = float(config['Calibration']['zero_calibration_circular_times'])
        stable_required_count = 15  # 连续15秒稳定

        # 获取用户开启的笼子列表
        mouse_cages = global_setting.get_setting("mouse_cages", [])
        # 转换为路号（笼子号-1），并添加参考气路8
        routes_to_calibrate = [cage - 1 for cage in mouse_cages] + [8]

        # 逐个路完成标定
        for route_x in routes_to_calibrate:
            if self.is_STOP:
                reject("stopped")
                return

            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | UGC零点标定：开始标定路{route_x}",
                title=self.title
            )

            # 该路的状态
            last_value = None
            current_value = None
            stable_count = 0
            start_time = time.time()

            # 循环读取该路直到稳定
            while True:
                if self.is_STOP:
                    reject("stopped")
                    return

                # 检查该路超时
                if time.time() - start_time > total_timeout:
                    self.update_status_main_signal_gui_update.send(
                        f"{time_util.get_format_from_time(time.time())} | UGC零点标定：路{route_x}超时失败",
                        title=self.title)
                    reject(f"route {route_x} timeout")
                    return

                # 读取该路的 CO2 浓度
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"{route_x:04X}0005"),
                    'slave_id': '3',
                    'function_code': '4',
                    'timeout': 1
                }
                self.send_thread.send_message = self.send_message
                carbon_data, carbon_message = self.send_thread.Send_no_promise()

                if not carbon_data or 'data' not in carbon_data:
                    time.sleep(1)
                    continue

                now_carbon_values = [
                    item.get('value')
                    for item in carbon_data.get('data', [])
                    if "CO2" in str(item.get('desc', ''))
                ]
                last_value = current_value
                current_value = now_carbon_values[0] if now_carbon_values else None

                # 判断稳定性
                is_stable = False
                if current_value is not None and last_value is not None:
                    change = abs(current_value - last_value)
                    in_range = 0 <= current_value <= 50
                    is_stable = (change < threshold) and in_range

                if is_stable:
                    stable_count += 1
                else:
                    stable_count = 0

                # 立即发送该路的数据给UI显示
                self.update_status_main_signal_gui_update.send(
                    {'type': 'set_calibration_values',
                     'value': {
                         'carbon_value': current_value,
                     }
                     }, title=self.title
                )

                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | UGC零点标定：路{route_x} CO2={current_value}%, 稳定计数={stable_count}/{stable_required_count}",
                    title=self.title
                )

                # 该路稳定15秒后完成
                if stable_count >= stable_required_count:
                    self.update_status_main_signal_gui_update.send(
                        f"{time_util.get_format_from_time(time.time())} | UGC零点标定：路{route_x}已稳定，完成",
                        title=self.title
                    )
                    break

                time.sleep(1)

        # 所有路都完成后，发送全局零点设置指令
        if self.is_STOP:
            reject("stopped")
            return

        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00100000"),
            'slave_id': '3',
            'function_code': '6',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC零点标定：发送全局 CO2 零点设置指令",
            title=self.title
        )

        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.close_ugc_zero_or_span_valve, port=port).then(
                lambda r2: resolve()
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))


class Range_Carlibration(Gas_Carlibration,MyQThread):
    """
    量程标定
    """
    def __init__(self):
        self.title = GapSystem_Running_Type.RANGE_CALIBRATION
        Gas_Carlibration.__init__(self,title=self.title,type =Gas_Carlibration_Type.SPAN)

        mouse_cages = global_setting.get_setting("mouse_cages", [])
        num_cages = len(mouse_cages) + 1
        timeout_ms = 300000 + (num_cages * 20000)

        MyQThread.__init__(self, name='Range_Carlibration_thread', deletion_timeout_ms=timeout_ms)
        self.port =None
        pass
    def dosomething(self):
        # 新版流程：直接打开 Span 阀门并开始采样 CO2
        AsyPromise(self.open_ugc_zero_or_span_valve, port=self.port).then(
            lambda r: AsyPromise(self.cyclic_sampling_of_ugc_co2_for_span, port=self.port).then(
                lambda r2: self.stop()
            ).catch(lambda e: self.stop())
        ).catch(lambda e: self.stop())
        pass
    def calibrate(self,resolve,reject):
        """量程标定"""
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} |  SPan量程标定 开始{'.' * 100}",title=self.title )
        # 发送开始标定消息
        self.update_status_main_signal_gui_update.send(
            {'type':'set_start_span_calibration_time','value':f'{time_util.get_format_from_time(time.time())}'},title=self.title
        )

        self.is_STOP=False
        self.port = global_setting.get_setting("port", None)
        if self.port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！",title=self.title )
            reject()
            return
        if self.is_STOP:
            reject()
            return

        # 不使用线程，直接执行标定流程
        AsyPromise(self.open_ugc_zero_or_span_valve, port=self.port).then(
            lambda _: AsyPromise(self.cyclic_sampling_of_ugc_co2_for_span, port=self.port).then(
                lambda _: resolve()
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))
        pass
    def stop_calibrate(self,resolve,reject):
        """
        取消量程标定（发送量程设置指令 + 关闭阀门，让设备退出标定模式）
        :param resolve:
        :param reject:
        :return:
        """
        self.is_STOP=True
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} |  停止SPan量程标定", title=self.title)
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 停止失败，未选择串口！", title=self.title)
            reject()
            return

        # 发送量程设置指令，让设备退出标定模式
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00110000"),
            'slave_id': '3',
            'function_code': '6',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | 停止量程标定：发送量程设置指令", title=self.title)

        # 发送指令 -> 关闭阀门 -> 完成
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.close_ugc_zero_or_span_valve, port=port).then(
                lambda r2: AsyPromise(self.stop_finish_calibration).then(lambda r3: resolve()).catch(lambda e: reject(e))
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))

    def cyclic_sampling_of_ugc_co2_for_span(self,resolve,reject,port):
        """
        UGC span 标定 CO2 采样（逐笼完成）
        按用户开启的笼子顺序，逐个笼子读取并等待稳定后再进入下一个
        稳定条件：连续15秒内数据变化 < 15ppm，且值在标准气浓度±25ppm范围内
        """
        if self.is_STOP:
            reject("stopped")
            return

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC span标定：开始逐笼采样 CO2浓度",
            title=self.title
        )

        config = global_setting.get_setting("UFC_UGC_ZOS_config")
        threshold = float(config['Calibration']['span_calibration_carbon_threshold'])
        standard_gas_concentration = float(config['Calibration'].get('standard_gas_concentration', 300))
        # 标准气浓度单位转换：配置文件是ppm，需要转换为%（除以10000）
        standard_gas_concentration_percent = standard_gas_concentration / 10000.0  # 300ppm = 0.03%
        stable_required_count = 15  # 连续15秒稳定
        max_wait_time = 30  # 每个笼子最大等待30秒

        # 获取用户开启的笼子列表
        mouse_cages = global_setting.get_setting("mouse_cages", [])
        # 转换为路号（笼子号-1），并添加参考气路8
        routes_to_calibrate = [cage - 1 for cage in mouse_cages] + [8]

        # 逐个路完成标定
        for route_x in routes_to_calibrate:
            if self.is_STOP:
                reject("stopped")
                return

            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | UGC span标定：开始标定路{route_x}",
                title=self.title
            )

            # 该路的状态
            last_value = None
            current_value = None
            stable_count = 0
            route_start_time = time.time()  # 记录该路开始时间

            # 循环读取该路直到稳定
            while True:
                if self.is_STOP:
                    reject("stopped")
                    return

                # 检查该路是否超时
                elapsed_time = time.time() - route_start_time
                if elapsed_time > max_wait_time:
                    self.update_status_main_signal_gui_update.send(
                        f"{time_util.get_format_from_time(time.time())} | UGC span标定：路{route_x}超时（{max_wait_time}秒），跳过进入下一路",
                        title=self.title
                    )
                    break

                # 读取该路的 CO2 浓度
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"000{route_x:X}0005"),
                    'slave_id': '3',
                    'function_code': '4',
                    'timeout': 1
                }
                self.send_thread.send_message = self.send_message
                carbon_data, carbon_message = self.send_thread.Send_no_promise()

                if not carbon_data or 'data' not in carbon_data:
                    time.sleep(1)
                    continue

                now_carbon_values = [
                    item.get('value')
                    for item in carbon_data.get('data', [])
                    if "CO2" in str(item.get('desc', ''))
                ]
                last_value = current_value
                current_value = now_carbon_values[0] if now_carbon_values else None

                # 判断稳定性（变化 < 15ppm，且值在合理范围内）
                is_stable = False
                if current_value is not None and last_value is not None:
                    change = abs(current_value - last_value)
                    threshold_percent = threshold / 10000.0  # 15ppm -> 0.0015%
                    # 范围：标准气浓度 ± 200ppm（考虑实际测量偏差）
                    lower_bound = standard_gas_concentration_percent - (200 / 10000.0)
                    upper_bound = standard_gas_concentration_percent + (200 / 10000.0)
                    in_range = lower_bound <= current_value <= upper_bound
                    is_stable = (change < threshold_percent) and in_range

                if is_stable:
                    stable_count += 1
                else:
                    stable_count = 0

                # 立即发送该路的数据给UI显示
                self.update_status_main_signal_gui_update.send(
                    {'type': 'set_calibration_values',
                     'value': {
                         'carbon_value': current_value,
                     }
                     }, title=self.title
                )

                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | UGC span标定：路{route_x} CO2={current_value}%, 稳定计数={stable_count}/{stable_required_count}",
                    title=self.title
                )

                # 该路稳定，进入下一路
                if stable_count >= stable_required_count:
                    self.update_status_main_signal_gui_update.send(
                        f"{time_util.get_format_from_time(time.time())} | UGC span标定：路{route_x}已稳定",
                        title=self.title
                    )
                    break

                time.sleep(1)

        if self.is_STOP:
            reject("stopped")
            return

        # 发送一次全局 CO2 span 设置指令
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00110000"),
            'slave_id': '3',
            'function_code': '6',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC span标定：发送全局 CO2 span 设置指令",title=self.title)

        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.close_ugc_zero_or_span_valve, port=port).then(
                lambda r2: resolve()
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))

    pass


class ZOS_Zero_Calibration(Gas_Carlibration, MyQThread):
    """
    ZOS 零点标定（独立流程，不与 UGC 耦合）
    """
    def __init__(self):
        self.title = GapSystem_Running_Type.ZERO_CALIBRATION
        self.port = None
        Gas_Carlibration.__init__(self, title=self.title, type=Gas_Carlibration_Type.ZERO)

        mouse_cages = global_setting.get_setting("mouse_cages", [])
        num_cages = len(mouse_cages)
        timeout_ms = 300000 + (num_cages * 20000)

        MyQThread.__init__(self, name='ZOS_Zero_Calibration_thread', deletion_timeout_ms=timeout_ms)

    def dosomething(self):
        # ZOS 调零独立流程
        AsyPromise(self.start_zos_zero_calibration, port=self.port).then(
            lambda r: self.stop()
        ).catch(lambda e: self.stop())

    def calibrate(self, resolve, reject):
        """ZOS 零点标定"""
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS 零点标定开始",
            title=self.title)
        self.update_status_main_signal_gui_update.send(
            {'type': 'set_start_zero_calibration_time',
             'value': f'{time_util.get_format_from_time(time.time())}'},
            title=self.title
        )
        self.is_STOP = False
        self.port = global_setting.get_setting("port", None)
        if self.port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！",
                title=self.title)
            reject()
            return

        # 直接执行标定流程，不启动线程
        AsyPromise(self.start_zos_zero_calibration, port=self.port).then(
            lambda r: resolve()
        ).catch(lambda e: reject(e))

    def start_zos_zero_calibration(self, resolve, reject, port):
        """发送 ZOS 调零开始指令：04 05 00 09 FF 00"""
        if self.is_STOP:
            reject("stop")
            return
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0009FF00"),
            'slave_id': '4',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS 零点标定：发送调零开始指令",
            title=self.title)
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.cyclic_sampling_zos_oxygen, port=port).then(
                lambda r2: resolve()
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))

    def cyclic_sampling_zos_oxygen(self, resolve, reject, port):
        """循环读取 ZOS 所有通道氧气浓度，所有通道稳定15秒后结束

        ZOS 协议：逐通道读取，每个通道单独发送 04 04 00 0X 00 0A 指令
        """
        if self.is_STOP:
            reject()
            return

        # 获取用户开启的笼子列表，转换为通道号
        mouse_cages = global_setting.get_setting("mouse_cages", [])
        channels_to_calibrate = mouse_cages  # ZOS 通道号与笼子号一致

        # 如果没有配置通道，直接保存默认值并完成标定
        if not channels_to_calibrate:
            logger.warning("ZOS 零点标定：未配置任何通道，使用默认值完成标定")
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | ZOS 零点标定：未配置通道，使用默认值完成",
                title=self.title)
            self.save_zero_data(0.0, 0.0)

            # 发送 ZOS 调零结束指令
            self.send_message = {
                'port': port,
                'data': number_util.set_int_to_4_bytes_list("00090000"),
                'slave_id': '4',
                'function_code': '5',
                'timeout': 1
            }
            self.send_thread.send_message = self.send_message
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | ZOS 零点标定：发送调零结束指令",
                title=self.title)
            AsyPromise(self.send_thread.Send).then(
                lambda r: AsyPromise(self.finish_calibration).then(lambda r2: resolve()).catch(lambda e: reject(e))
            ).catch(lambda e: reject(e))
            return

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS 零点标定：循环采样所有通道氧气浓度",
            title=self.title)

        start_time = time.time()
        total_timeout = 300  # 5分钟总超时
        threshold = float(global_setting.get_setting("UFC_UGC_ZOS_config")['Calibration'].get(
            'zero_calibration_oxygen_threshold', 0.1))

        # 每个通道独立状态：{last_value, current_value, stable_since}
        channel_states = {ch: {'last_value': None, 'current_value': None, 'stable_since': None}
                         for ch in channels_to_calibrate}

        # 压力值（所有通道共享，从第一个通道读取）
        pressure_value = None

        while True:
            if self.is_STOP:
                reject()
                return

            # 检查总超时
            elapsed = time.time() - start_time
            if elapsed > total_timeout:
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | ZOS 零点标定：超时失败，未能在{total_timeout}秒内所有通道达到稳定",
                    title=self.title)
                reject(f"timeout after {total_timeout}s without all channels stable")
                return

            # 逐通道读取氧气浓度
            for ch in channels_to_calibrate:
                if self.is_STOP:
                    reject()
                    return

                # 为每个通道单独发送读取指令：04 04 00 0X 00 0A
                # X 是通道号
                data_hex = f"00{ch:02X}000A"

                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(data_hex),
                    'slave_id': '4',
                    'function_code': '4',
                    'timeout': 1
                }
                self.send_thread.send_message = self.send_message
                oxygen_data, oxygen_message = self.send_thread.Send_no_promise()

                # 检查数据有效性
                if not oxygen_data or 'data' not in oxygen_data:
                    logger.warning(f"ZOS零点标定：通道{ch}读取失败，跳过本次采样")
                    time.sleep(1)
                    continue

                # 解析该通道的氧气浓度和压力
                oxygen_items = [item['value'] for item in oxygen_data['data'] if "氧浓度(%)" in item['desc']]
                pressure_items = [item['value'] for item in oxygen_data['data'] if "气体压力" in item['desc']]

                # 更新该通道状态
                state = channel_states[ch]
                state['last_value'] = state['current_value']
                state['current_value'] = oxygen_items[0] if oxygen_items else None

                # 更新压力值（从第一个通道获取）
                if ch == channels_to_calibrate[0] and pressure_items:
                    pressure_value = pressure_items[0]

                # 检查该通道稳定性
                if (state['current_value'] is not None and
                    state['last_value'] is not None and
                    abs(state['current_value'] - state['last_value']) <= threshold):

                    if state['stable_since'] is None:
                        state['stable_since'] = time.time()
                else:
                    state['stable_since'] = None

                # 立即发送该通道的数据给UI显示
                self.update_status_main_signal_gui_update.send(
                    {'type': 'set_calibration_values',
                     'value': {
                                'oxygen_value': state['current_value'],
                                'oxygen_pressure_value': pressure_value,
                                }
                     }, title=self.title
                )

            # 检查是否所有通道都稳定
            all_stable = True
            min_stable_duration = float('inf')

            for ch in channels_to_calibrate:
                state = channel_states[ch]
                if state['stable_since'] is None:
                    all_stable = False
                    min_stable_duration = 0
                    break
                else:
                    stable_duration = time.time() - state['stable_since']
                    min_stable_duration = min(min_stable_duration, stable_duration)

            # 状态更新
            channel_status = ", ".join([
                f"通道{ch}={channel_states[ch]['current_value']}%(稳定{int(time.time() - channel_states[ch]['stable_since'])}s)" if channel_states[ch]['stable_since']
                else f"通道{ch}={channel_states[ch]['current_value']}%(不稳定)"
                for ch in channels_to_calibrate
            ])
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | ZOS 零点标定：{channel_status}，压力={pressure_value}kPa，已循环{int(elapsed)}秒",
                title=self.title)

            # 所有通道都稳定15秒后结束
            if all_stable and min_stable_duration >= 15:
                break

            time.sleep(1)

        if self.is_STOP:
            reject()
            return

        # 保存零点数据（使用基准通道 - 第一个通道的值）
        base_channel = channels_to_calibrate[0]
        base_channel_value = channel_states[base_channel]['current_value']
        logger.info(f"ZOS 零点标定：使用通道{base_channel}作为基准通道，值={base_channel_value}%")
        self.save_zero_data(base_channel_value, pressure_value)

        # 发送 ZOS 调零结束指令：04 05 00 09 00 00
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00090000"),
            'slave_id': '4',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS 零点标定：发送调零结束指令",
            title=self.title)
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.finish_calibration).then(lambda r2: resolve()).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))

    def save_zero_data(self, oxygen_value, pressure_value):
        """保存 ZOS 零点标定数据"""
        return_data_struct = {}
        return_data_struct['module_name'] = 'ZOS_ZeroCalibration'
        return_data_struct['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        return_data_struct['table_name'] = next(iter(Others_Tables.Zero_Carlibration_Data.value.keys()))
        return_data_struct['mouse_cage_number'] = -1

        if oxygen_value is not None:
            global_setting.set_setting("Vzero", oxygen_value)
            return_data_struct['data'] = [
                {'desc': 'ZOS氧浓度0点校准值', 'value': oxygen_value},
                {'desc': 'ZOS压力0点校准值', 'value': pressure_value}
            ]
        else:
            return_data_struct['data'] = [{'desc': 'ZOS氧浓度0点校准值', 'value': None}]

        return_data_struct['slave_id'] = 0
        return_data_struct['function_code'] = 0
        result = store_data_with_result(return_data_struct, need_result=True, timeout=5)
        if result and result.success:
            logger.info(f"ZOS零点数据存储成功，ID: {result.item_id}")
        else:
            logger.error(f"ZOS零点数据存储失败: {result.error if result else '未知错误'}")

    def stop_calibrate(self, resolve, reject):
        """停止 ZOS 零点标定"""
        self.is_STOP = True
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | 停止 ZOS 零点标定",
            title=self.title)
        port = global_setting.get_setting("port", None)
        if port is None:
            reject()
            return
        # 发送调零结束指令
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00090000"),
            'slave_id': '4',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.stop_finish_calibration).then(lambda r2: resolve()).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))


class ZOS_Span_Calibration(Gas_Carlibration, MyQThread):
    """
    ZOS span 标定（独立流程，不与 UGC 耦合）
    """
    def __init__(self):
        self.title = GapSystem_Running_Type.RANGE_CALIBRATION
        self.port = None
        Gas_Carlibration.__init__(self, title=self.title, type=Gas_Carlibration_Type.SPAN)

        mouse_cages = global_setting.get_setting("mouse_cages", [])
        num_cages = len(mouse_cages)
        timeout_ms = 300000 + (num_cages * 20000)

        MyQThread.__init__(self, name='ZOS_Span_Calibration_thread', deletion_timeout_ms=timeout_ms)

    def dosomething(self):
        # 新版流程：ZOS 调 span 独立流程
        AsyPromise(self.start_zos_span_calibration, port=self.port).then(
            lambda r: self.stop()
        ).catch(lambda e: self.stop())

    def calibrate(self, resolve, reject):
        """ZOS span 标定"""
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS span 标定开始",
            title=self.title)
        self.update_status_main_signal_gui_update.send(
            {'type': 'set_start_span_calibration_time',
             'value': f'{time_util.get_format_from_time(time.time())}'},
            title=self.title
        )
        self.is_STOP = False
        self.port = global_setting.get_setting("port", None)
        if self.port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！",
                title=self.title)
            reject()
            return

        # 直接执行标定流程，不启动线程
        AsyPromise(self.start_zos_span_calibration, port=self.port).then(
            lambda r: resolve()
        ).catch(lambda e: reject(e))

    def start_zos_span_calibration(self, resolve, reject, port):
        """发送 ZOS 调 span 开始指令：04 05 00 0A FF 00"""
        if self.is_STOP:
            reject("stop")
            return
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("000AFF00"),
            'slave_id': '4',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS span 标定：发送调 span 开始指令",
            title=self.title)
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.cyclic_sampling_zos_oxygen_for_span, port=port).then(
                lambda r2: resolve()
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))

    def cyclic_sampling_zos_oxygen_for_span(self, resolve, reject, port):
        """ZOS span 标定 氧气采样（逐笼完成）
        按用户开启的笼子顺序，逐个笼子读取并等待稳定后再进入下一个

        ZOS 协议：逐通道读取，每个通道单独发送 04 04 00 0X 00 0A 指令
        """
        if self.is_STOP:
            reject()
            return

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS span 标定：开始逐笼采样氧气浓度",
            title=self.title
        )

        config = global_setting.get_setting("UFC_UGC_ZOS_config")
        threshold = float(config['Calibration'].get('span_calibration_oxygen_threshold', 0.1))
        stable_required_count = 15  # 连续15秒稳定
        max_wait_time = 60  # 每个通道最大等待60秒

        # 获取用户开启的笼子列表，转换为通道号
        mouse_cages = global_setting.get_setting("mouse_cages", [])
        channels_to_calibrate = mouse_cages  # ZOS 通道号与笼子号一致

        # 压力值（所有通道共享）
        pressure_value = None

        # 逐个通道完成标定
        for ch in channels_to_calibrate:
            if self.is_STOP:
                reject()
                return

            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | ZOS span 标定：开始标定通道{ch}",
                title=self.title
            )

            # 该通道的状态
            last_value = None
            current_value = None
            stable_count = 0
            channel_start_time = time.time()  # 记录该通道开始时间

            # 循环读取该通道直到稳定
            while True:
                if self.is_STOP:
                    reject()
                    return

                # 检查该通道是否超时
                elapsed_time = time.time() - channel_start_time
                if elapsed_time > max_wait_time:
                    self.update_status_main_signal_gui_update.send(
                        f"{time_util.get_format_from_time(time.time())} | ZOS span 标定：通道{ch}超时（{max_wait_time}秒），跳过进入下一通道",
                        title=self.title
                    )
                    break

                # 为该通道发送读取指令：04 04 00 0X 00 0A
                data_hex = f"00{ch:02X}000A"

                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(data_hex),
                    'slave_id': '4',
                    'function_code': '4',
                    'timeout': 1
                }
                self.send_thread.send_message = self.send_message
                oxygen_data, _ = self.send_thread.Send_no_promise()

                if not oxygen_data or 'data' not in oxygen_data:
                    time.sleep(1)
                    continue

                # 解析该通道的氧气浓度和压力
                oxygen_items = [
                    item.get('value')
                    for item in oxygen_data.get('data', [])
                    if "氧气浓度(%)" in str(item.get('desc', '')) or "氧浓度(%)" in str(item.get('desc', ''))
                ]
                pressure_items = [
                    item.get('value')
                    for item in oxygen_data.get('data', [])
                    if "气压力" in str(item.get('desc', '')) or "气体压力" in str(item.get('desc', ''))
                ]

                last_value = current_value
                current_value = oxygen_items[0] if oxygen_items else None

                # 更新压力值
                if pressure_items:
                    pressure_value = pressure_items[0]

                # 判断稳定性
                is_stable = False
                if current_value is not None and last_value is not None:
                    change = abs(current_value - last_value)
                    is_stable = change <= threshold

                if is_stable:
                    stable_count += 1
                else:
                    stable_count = 0

                # 立即发送该通道的数据给UI显示
                self.update_status_main_signal_gui_update.send(
                    {'type': 'set_calibration_values',
                     'value': {
                         'oxygen_value': current_value,
                         'oxygen_pressure_value': pressure_value,
                     }
                     }, title=self.title
                )

                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | ZOS span 标定：通道{ch} O2={current_value}%, 压力={pressure_value}kPa, 稳定计数={stable_count}/{stable_required_count}",
                    title=self.title
                )

                # 该通道稳定，进入下一通道
                if stable_count >= stable_required_count:
                    self.update_status_main_signal_gui_update.send(
                        f"{time_util.get_format_from_time(time.time())} | ZOS span 标定：通道{ch}已稳定",
                        title=self.title
                    )
                    break

                time.sleep(1)

        if self.is_STOP:
            reject()
            return

        # 保存 span 数据并计算 K 值（使用最后一个通道的值）
        base_channel = channels_to_calibrate[-1]
        base_channel_value = current_value  # 使用最后一个通道的 current_value
        logger.info(f"ZOS span 标定：使用通道{base_channel}作为基准通道，值={base_channel_value}%")
        self.save_span_data(base_channel_value, pressure_value)

        # 发送 ZOS 调 span 结束指令：04 05 00 0A 00 00
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("000A0000"),
            'slave_id': '4',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS span 标定：发送调 span 结束指令",
            title=self.title)
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.finish_calibration).then(lambda r2: resolve()).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))

    def save_span_data(self, oxygen_value, pressure_value):
        """保存 ZOS span 标定数据并计算 K 值"""
        return_data_struct = {}
        return_data_struct['module_name'] = 'ZOS_SpanCalibration'
        return_data_struct['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        return_data_struct['table_name'] = next(iter(Others_Tables.SPan_Carlibration_Data.value.keys()))
        return_data_struct['mouse_cage_number'] = -1

        if oxygen_value is not None:
            # 计算 K 值：K = (Vs - Vzero) / (Vr - Vzero)
            K = (oxygen_value - global_setting.get_setting("Vzero", 0)) / (
                        global_setting.get_setting("Vr", 20.9) - global_setting.get_setting("Vzero", 0))
            logger.warning(
                f"ZOS span 标定 K 值：{K}, Vs={oxygen_value}, Vr={global_setting.get_setting('Vr', 20.9)}, Vzero={global_setting.get_setting('Vzero', 0)}")
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | ZOS span 标定 K 值：{K}",
                title=self.title)
            global_setting.set_setting("K", K)
            return_data_struct['data'] = [
                {'desc': 'ZOS氧浓传感器span数值', 'value': oxygen_value},
                {'desc': 'ZOS压力span数值', 'value': pressure_value},
                {'desc': 'K值', 'value': K}
            ]
        else:
            return_data_struct['data'] = [{'desc': 'ZOS氧浓传感器span数值', 'value': None}]

        return_data_struct['slave_id'] = 0
        return_data_struct['function_code'] = 0
        result = store_data_with_result(return_data_struct, need_result=True, timeout=5)
        if result and result.success:
            logger.info(f"ZOS span 数据存储成功，ID: {result.item_id}")
        else:
            logger.error(f"ZOS span 数据存储失败: {result.error if result else '未知错误'}")

    def stop_calibrate(self, resolve, reject):
        """停止 ZOS span 标定"""
        self.is_STOP = True
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | 停止 ZOS span 标定",
            title=self.title)
        port = global_setting.get_setting("port", None)
        if port is None:
            reject()
            return
        # 发送调 span 结束指令
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("000A0000"),
            'slave_id': '4',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.stop_finish_calibration).then(lambda r2: resolve()).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))
