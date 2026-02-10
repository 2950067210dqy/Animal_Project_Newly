import abc

import re
import threading

import time
from datetime import datetime
from threading import Event, Barrier

from blinker.base import _PNamespaceSignal
from loguru import logger


from Service.UFC_UGC_ZOS_Service.function.Send_Message.Send_Message import Send_Message

from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from public.entity.barrier.ActionCompleteBarrier import ActionCompleteBarrier
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Monitor_data_storage.DataStorage import store_data_with_result
from public.function.promise.AsyPromise import AsyPromise
from public.util.number_util import number_util
from public.util.string_util import String_util
from public.util.time_util import time_util
# 等待ufc启动完
wait_UFC_start_finish_event = threading.Event()
# 等待ufc 停止完
wait_UFC_stop_finish_event = threading.Event()

import numpy as np
import os
import threading

# 全局O2模型缓存
_o2_model = None
_model_lock = threading.Lock()

# O2三点测量缓存
o2_measurement_cache = {}
o2_cache_lock = threading.Lock()


def get_o2_model():
    """改进版：增强错误处理"""
    global _o2_model
    if _o2_model is None:
        with _model_lock:
            if _o2_model is None:
                try:
                    import lightgbm as lgb
                    model_path = os.path.join(os.path.dirname(__file__), '..', '..', 'model', 'o2_steady_model.txt')

                    if not os.path.exists(model_path):
                        logger.critical(f"O2模型文件缺失: {model_path}")
                        logger.warning("将在无模型修正的情况下运行，精度将大幅下降")
                        return None

                    _o2_model = lgb.Booster(model_file=model_path)
                    logger.info(f"O2稳态模型加载成功: {model_path}")

                except ImportError:
                    logger.error("lightgbm库未安装，请执行: pip install lightgbm")
                except Exception as e:
                    logger.error(f"O2模型加载失败: {e}")

    return _o2_model


def predict_steady_o2(o2_5s, o2_10s, o2_15s):
    """
    基于三个时间点的氧气值进行稳态预测
    :param o2_5s: 第5秒的O2值（已校准和压力补偿）
    :param o2_10s: 第10秒的O2值（已校准和压力补偿）
    :param o2_15s: 第15秒的O2值（已校准和压力补偿）
    :return: 预测的稳态氧气值（%）
    """
    try:
        model = get_o2_model()
        if model is None:
            logger.warning("O2模型未加载，使用第15秒的值作为稳态值")
            return o2_15s

        # 构建三值输入：[[o2_5s, o2_10s, o2_15s]]
        X = np.array([[o2_5s, o2_10s, o2_15s]]).astype(np.float32)

        # 模型预测
        o2_steady = model.predict(X)[0]

        # 范围检查（确保在0-100%之间）
        if o2_steady < 0:
            o2_steady = 0
        elif o2_steady > 100:
            o2_steady = 100

        # 记录日志
        logger.info(f"O2稳态预测: [5s={o2_5s:.2f}%, 10s={o2_10s:.2f}%, 15s={o2_15s:.2f}%] → steady={o2_steady:.2f}%")

        return round(o2_steady, 6)

    except Exception as e:
        logger.error(f"O2稳态预测失败: {e}，使用第15秒的值")
        return o2_15s


class O2CorrectionManager:
    @staticmethod
    def calibrate_and_compensate(oxygen_raw, vzero=None, k=None, air_pressure=None):
        """增强版：明确气压来源"""
        try:
            if oxygen_raw is None:
                return None

            if vzero is None:
                vzero = global_setting.get_setting("Vzero", 0)
            if k is None:
                k = global_setting.get_setting("K", 1)
            if air_pressure is None:
                # 优先级：UGC测量 > 1104环境模块 > 标准大气压
                air_pressure = (
                        global_setting.get_setting("air_pressure") or
                        global_setting.get_setting("air_pressure_1104") or
                        None
                )

            # 第一步：校准
            oxygen_calibrated = round((oxygen_raw - vzero) * k, 6)

            # 第二步：气压补偿
            if air_pressure is not None:
                standard_atm = float(
                    global_setting.get_setting("UFC_UGC_ZOS_config")['PARAM']['standard_atmospheric_pressure'])
                o2_coeff = float(
                    global_setting.get_setting("UFC_UGC_ZOS_config")['PARAM']['oxygen_compensation_coefficient'])

                oxygen_value = (oxygen_calibrated / (1 + air_pressure / standard_atm)) * o2_coeff
                oxygen_value = round(oxygen_value, 6)

                # ✓ 记录日志，便于追溯
                logger.debug(f"O2补偿: raw={oxygen_raw} → calibrated={oxygen_calibrated} → "
                             f"compensated={oxygen_value} (air_pressure={air_pressure}kPa)")
            else:
                oxygen_value = oxygen_calibrated
                logger.warning("缺少气压数据，跳过补偿")

            return oxygen_value

        except Exception as e:
            logger.error(f"O2校准补偿失败: {e}")
            return oxygen_raw

    @staticmethod
    def predict_steady_o2_three_point(o2_5s, o2_10s, o2_15s):
        """
        基于三个时间点的O2值进行稳态预测
        :param o2_5s: 第5秒的O2值（已校准和补偿）
        :param o2_10s: 第10秒的O2值（已校准和补偿）
        :param o2_15s: 第15秒的O2值（已校准和补偿）
        :return: 预测的稳态O2值
        """
        try:
            model = get_o2_model()
            if model is None:
                logger.warning("O2模型未加载，使用第15秒的值作为稳态值")
                return o2_15s

            # 构建三值输入
            X = np.array([[o2_5s, o2_10s, o2_15s]]).astype(np.float32)
            o2_steady = model.predict(X)[0]

            # 范围检查
            o2_steady = max(0, min(100, o2_steady))

            logger.info(f"O2稳态预测: [5s={o2_5s:.2f}%, 10s={o2_10s:.2f}%, 15s={o2_15s:.2f}%] → steady={o2_steady:.2f}%")

            return round(o2_steady, 6)

        except Exception as e:
            logger.error(f"O2稳态预测失败: {e}，使用第15秒的值")
            return o2_15s

    @staticmethod
    def apply_model_correction(oxygen_value):
        """
        应用模型修正（当没有三点数据时使用）
        """
        try:
            model = get_o2_model()
            if model is None:
                return oxygen_value

            # 单点预测（作为降级方案）
            X = np.array([[oxygen_value]]).astype(np.float32)
            o2_corrected = model.predict(X)[0]

            o2_corrected = max(0, min(100, o2_corrected))
            logger.info(f"O2模型修正: {oxygen_value:.4f} → {o2_corrected:.4f}")
            return round(o2_corrected, 6)

        except Exception as e:
            logger.warning(f"O2模型修正失败，使用原值: {e}")
            return oxygen_value

logger = logger.bind(category="monitor_data_logger")
class Gas_path_system:
    """
    气路系统 三个气路模块的父类
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
        pass
    def update(self):
        self.send_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update


    @abc.abstractmethod
    def start(self,resolve,reject):
        """
        启动气路
        :return:
        """
        pass
    @abc.abstractmethod
    def run(self,resolve,reject):
        """
        气路运行
        :return:
        """
        pass
    @abc.abstractmethod
    def stop(self,resolve,reject):
        """
        停止气路
        :return:
        """
        pass
class UFC_gas_path_system_start_thread(MyQThread):
    """
    UFC 气路系统开启线程
    """
    def __init__(self,name,update_status_main_signal_gui_update,parent_class):
        #基类
        self.parent_class = parent_class
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: _PNamespaceSignal = update_status_main_signal_gui_update
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
        super().__init__(name=name)
    def before_Runing_work(self):
        pass
    def dosomething(self):
        # 1.设定运行鼠笼（默认8个鼠笼都运行）
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            return
        # mouse_cages_2byte_str: str = global_setting.get_setting("mouse_cages_2byte_str", "11111111")

        # self.send_message = {
        #     'port': port,
        #     'data': number_util.set_int_to_4_bytes_list(str(int(mouse_cages_2byte_str, 2))),
        #     'slave_id': '2',
        #     'function_code': '6',
        #     'timeout': 1
        # }
        # self.update_status_main_signal_gui_update.send(
        #     f"{time_util.get_format_from_time(time.time())} | UFC 启动-1.设定运行鼠笼")
        # self.send_thread.send_message = self.send_message
        # AsyPromise(self.send_thread.Send).then(
        #     # 2UFC启动
        #     lambda r: AsyPromise(self.ufc_start).then(
        #         self.stop()
        #     )
        # ).catch(lambda e: logger.error(f"{e}"))
        AsyPromise(self.ufc_start).then(
            self.stop()
        ).catch(lambda e: logger.error(f"{e}"))
        pass
        pass

    def ufc_start(self, resolve, reject):
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC 启动-2.UFC启动")
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        # 2 UFC 启动
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("000b00ff"),
            'slave_id': '2',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            # 3气泵和流量控制器开启
            lambda r: AsyPromise(self.gas_and_flow_rate_start)
        ).catch(lambda e: reject(e))
        pass

    def gas_and_flow_rate_start(self, resolve, reject):
        time.sleep(0.01)
        # 3气泵和流量控制器开启
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC 启动-3.气泵和流量控制器开启")
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("000a00ff"),
            'slave_id': '2',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r:AsyPromise(self.open_zos_valve).then(
                lambda r:resolve(r)
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))


        pass
        pass
    def open_zos_valve(self,resolve, reject):

        # 等待时间
        time_index = 0
        while time_index<float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['wait_time']):
            self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-启动 3.1 等待气泵和流量控制器开启，此过程需{time_index}/{float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['wait_time'])}秒，等待流量控制器自动配置及运行")
            time_index += 1
            time.sleep(1)
        # 4. 打开zos采样阀
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-启动 4.打开ZOS采样阀")
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("000900ff"),
            'slave_id': '2',
            'function_code': '5',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            AsyPromise(self.finsh_start).then(
                lambda r: resolve(r)
            ).catch(lambda e: reject(e))
        ).catch(lambda e: logger.error(f"{e}"))
    def finsh_start(self,resolve, reject):

        self.parent_class.ufc_start_time_state = True
        # logger.critical(f"ufc_finish_start:{self.parent_class.ufc_start_time_state}")
        # 释放 正在等待ufc启动的地方
        global wait_UFC_start_finish_event
        wait_UFC_start_finish_event.set()
        wait_UFC_start_finish_event.clear()
        resolve()
class UFC_gas_path_system_close_thread(MyQThread):
    """
    UFC 气路系统关闭线程
    """
    def __init__(self,name,update_status_main_signal_gui_update):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: _PNamespaceSignal = update_status_main_signal_gui_update
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
        super().__init__(name=name)
    def before_Runing_work(self):
        pass
    def dosomething(self):
        # 1.关闭正在运行的鼠笼
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            return
        mouse_cages_inc: list = global_setting.get_setting("mouse_cages", None)
        if mouse_cages_inc is not None and len(mouse_cages_inc) > 0:
            for addr in mouse_cages_inc:
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"000{addr}0000"),
                    'slave_id': '2',
                    'function_code': '5',
                    'timeout': 1
                }
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | UFC-停止 1.关闭{addr + 1}号鼠笼气路")
                self.send_thread.send_message = self.send_message
                AsyPromise(self.send_thread.Send).then()
                # self.send_thread.Send_no_promise()
            else:
                # 1.关闭参考气
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"00080000"),
                    'slave_id': '2',
                    'function_code': '5',
                    'timeout': 1
                }
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | UFC-停止 1.关闭参考气")
                self.send_thread.send_message = self.send_message
                AsyPromise(self.send_thread.Send).then(
                    lambda r: AsyPromise(self.close_ZOS_valve, port=port)
                )
        self.stop()
        pass
        pass
    def close_ZOS_valve(self,resolve,reject,port):
        """2.关闭zos采样阀门"""
        time.sleep(0.01)
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"00090000"),
            'slave_id': '2',
            'function_code': '5',
            'timeout': 1
        }
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-停止 2.关闭zos采样阀门")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.close_Gas_flow_rate_valve, port=port), resolve()
        )
    def close_Gas_flow_rate_valve(self,resolve,reject,port):
        """3.气泵及设定鼠笼流量控制器关闭"""
        time.sleep(0.01)
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"000A0000"),
            'slave_id': '2',
            'function_code': '5',
            'timeout': 1
        }
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-停止 3.气泵及设定鼠笼流量控制器关闭")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.close_UFC_valve, port=port), resolve()
        )
    def close_UFC_valve(self,resolve,reject,port):
        """4.UFC阀门关闭 让步骤3延迟1分钟在关闭"""
        time.sleep(float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['start_wait_time']))
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"000B0000"),
            'slave_id': '2',
            'function_code': '5',
            'timeout': 1
        }
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-停止 4.UFC阀门关闭")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            AsyPromise(self.finish_close).then(
                lambda r:resolve()
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))

    def finish_close(self,resolve,reject):
        # 释放 正在等待ufc启动的地方
        global wait_UFC_stop_finish_event
        wait_UFC_stop_finish_event.set()
        wait_UFC_stop_finish_event.clear()
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC 已关闭")
        # 返回响应
        queue = global_setting.get_setting("queue", None)
        if queue:
            queue.put(
                ObjectQueueItem(origin="Gas_path_system_ufc", to="MainWindow_index", title="stop_ufc_gap_system_return",
                                data=" UFC 已关闭",
                                time=time_util.get_format_from_time(time.time())))
        resolve()
class UFC_gas_path_system_run_thread(MyQThread):
    """
    UFC 气路系统运行线程
    """
    def __init__(self,name,update_status_main_signal_gui_update):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: _PNamespaceSignal = update_status_main_signal_gui_update
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

        super().__init__(name=name)
    def before_Runing_work(self):
        pass
    def dosomething(self):

        mouse_cages_inc:list=global_setting.get_setting("mouse_cages",None)
        if mouse_cages_inc is not None and len(mouse_cages_inc) > 0:
            port = global_setting.get_setting("port", None)
            if port is None:
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | UFC运行失败，未选择串口！")
                logger.error("UFC运行失败，未选择串口！")
                AsyPromise(self.finsh_one_batch, port=None, mouse_cages_inc=mouse_cages_inc).then(

                ).catch(lambda e: logger.error(f"{e}"))
                return
            # 从我们之前选择的运行鼠笼拿出来 每次循环访问一个
            AsyPromise(self.switch_mouse_cage_gas,port=port,mouse_cages_inc=mouse_cages_inc).then(

            ).catch(lambda e: logger.error(f"{e}"))
            pass
        else:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | UFC运行失败，未选择实例化实验设置的mouse_cages！")
            logger.error("UFC运行失败，未选择实例化实验设置的mouse_cages！")
            AsyPromise(self.finsh_one_batch,port=None, mouse_cages_inc=mouse_cages_inc).then(

            ).catch(lambda e: logger.error(f"{e}"))



        pass
    def switch_mouse_cage_gas(self,resolve,reject,port,mouse_cages_inc):
        """
        切换鼠笼气路
        :param resolve:
        :param reject:
        :param port:
        :param mouse_cages_inc:
        :return:
        """
        mouse_cage_index = global_setting.get_setting("cage_number_list_index",None)
        logger.critical(f"mouse_cages_inc:{mouse_cages_inc},mouse_cage_index:{mouse_cage_index}")
        if mouse_cage_index is not None:
            mouse_cage_number_addr_single = mouse_cages_inc[mouse_cage_index]-1
        else:
            # 下标为None 则为参考气
            mouse_cage_number_addr_single=8
        # 1 切换x号鼠笼

        time.sleep(0.01)
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"000{mouse_cage_number_addr_single}00ff"),
            'slave_id': '2',
            'function_code': '5',
            'timeout': 1
        }

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-运行 1. 切换{str(mouse_cage_number_addr_single ) + '号鼠笼' if mouse_cage_number_addr_single !=8 else global_setting.get_setting('configer')['mouse_cage']['reference'] + '(参考气)'}")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            # 2. 关闭上个鼠笼的气路或者关闭参考气
            lambda r: AsyPromise(self.close_last_mouse_cage_gas, port=port, mouse_cages_inc=mouse_cages_inc).then(
                lambda r:resolve()
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))
    def close_last_mouse_cage_gas(self,resolve,reject,port,mouse_cages_inc):
        """
         UFC-运行 2. 关闭上个鼠笼的气路或者关闭参考气
        如果i≠0，关闭i-1号，i++；
        如果i=0，关闭8号，i++
        :param resolve:
        :param reject:
        :param port:
        :return:
        """
        time.sleep(0.01)
        mouse_cage_index = global_setting.get_setting("cage_number_list_index", None)
        # 当前为参考气 则关闭最后一个鼠笼
        if mouse_cage_index is None :
            mouse_cage_number_addr_single = mouse_cages_inc[len(mouse_cages_inc) - 1 ]-1
        elif mouse_cage_index==0:
        #当前为鼠笼列表的第一个鼠笼 则关闭参考气
            mouse_cage_number_addr_single=8
        else:
            mouse_cage_number_addr_single=mouse_cages_inc[mouse_cage_index-1]-1
        #2.关闭上个鼠笼号，如果当前鼠笼号为0，则关闭参考气体
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-运行 2. 关闭{str(mouse_cage_number_addr_single )+'号鼠笼' if mouse_cage_number_addr_single!=8 else '参考气'}")


        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"000{mouse_cage_number_addr_single}0000"),
            'slave_id': '2',
            'function_code': '5',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        self.send_thread.Send_no_promise()
        # 3 循环读取流量值 （推荐每2秒读取一次）（原定为15秒）
        AsyPromise(self.read_flow_rate_value_circulation, port=port, mouse_cages_inc=mouse_cages_inc).then(
           lambda r:resolve()
        ).catch(lambda e: logger.error(f"{e}"))


        pass
    def read_flow_rate_value_circulation(self,resolve,reject,port,mouse_cages_inc):
        """
        循环读取流量值 （推荐每2秒读取一次）（原定为15秒）
        """
        time.sleep(18)
        # 让ugc开始运行
        wait_UFC_run_finish_event = global_setting.get_setting("wait_UFC_run_finish_event", None)
        if wait_UFC_run_finish_event:
            wait_UFC_run_finish_event.set()
            wait_UFC_run_finish_event.clear()
        mouse_cage_index = global_setting.get_setting("cage_number_list_index", None)

        # 3 循环读取流量值 （推荐每2秒读取一次）（原定为15秒） ！弃用
        index = 0
        # while (index< int(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['run_time'])):
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"00000006"),
            'slave_id': '2',
            'function_code': '4',
            'timeout': 1
        }
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-运行 3. 循环读取流量值（推荐每{int(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['run_time_delay'])}秒读取一次），当前{index}s/{int(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['run_time'])}s")
        self.send_thread.send_message = self.send_message
        result_data,message = self.send_thread.Send_no_promise()


        result_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        result_data['mouse_cage_number']= mouse_cages_inc[mouse_cage_index] if mouse_cage_index is not None else int(global_setting.get_setting('configer')['mouse_cage']['reference'])
        logger.error(f"---------------鼠笼气路值：{result_data}")
        result = store_data_with_result(result_data, need_result=True, timeout=5)
        if result and result.success:
            logger.info(f"数据存储成功，ID: {result.item_id}")
        else:
            logger.error(f"数据存储失败: {result.error if result else '未知错误'}")
        # index+=int(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['run_time_delay'])
        # time.sleep(float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['run_time_delay']))
#       #while end
#       #等待60秒 ！弃用
        AsyPromise(self.finsh_one_batch, port=port, mouse_cages_inc=mouse_cages_inc).then(
            lambda r: resolve()
        ).catch(lambda e: logger.error(f"{e}"))

    def finsh_one_batch(self,resolve,reject,port,mouse_cages_inc):
        """
        完成一轮次后做的事情
        :param resolve:
        :param reject:
        :param port:
        :param mouse_cages_inc:
        :return:
        """


        # # 让鼠笼内的传感器开始运行 要等待ufc ugc zos 都wait
        # ufc_ugc_zos_barrier=global_setting.get_setting("ufc_ugc_zos_barrier")
        # if ufc_ugc_zos_barrier is not None :
        #     logger.debug(f"ufc_ugc_zos_barrier_UFC run one batch done ! ")
        #     ufc_ugc_zos_barrier.wait()
        barrier = global_setting.get_setting("barrier")
        if barrier is not None:
            logger.debug(f"barrier_UFC run one batch done ! ")
            barrier.wait()

        resolve()
class UFC_gas_path_system(Gas_path_system):
    """
    UFC 气路系统
    """
    # UFC开始的操作数
    process_nums =3+1
    def __init__(self):
        super().__init__()

        #记录ufc等待的1分钟状态
        self.ufc_start_time_state = False
        #开启线程
        self.ufc_gas_path_system_start_thread = UFC_gas_path_system_start_thread(
            name="UFC_gas_path_system_start_thread",
            update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,
            parent_class=self

        )
        #运行线程
        self.ufc_gas_path_system_run_thread = UFC_gas_path_system_run_thread(
            name="UFC_gas_path_system_run_thread",
            update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,

        )
        #关闭线程
        self.ufc_gas_path_system_close_thread = UFC_gas_path_system_close_thread(
            name="UFC_gas_path_system_close_thread",
            update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,

        )
        pass
    def update(self):
        super().update()
        # 开启线程
        self.ufc_gas_path_system_start_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_start_thread.send_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_run_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_run_thread.send_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_close_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_close_thread.send_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update


    """start start"""
    def start(self,resolve,reject):
        """
        启动气路
        :return:
        """
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | UFC 开始启动{'.'*100}")

        # dlg = RunningCagesDialog(None, total_cages=8)
        # data = ""
        # if dlg.exec() == QDialog.DialogCode.Accepted:
        #     res = dlg.result_data
        #     if res['all_selected']:
        #         # 全部选择
        #         data = "11111111"
        #         pass
        #     else:
        #         for i in range(8):
        #             if i in res['selected_indices']:
        #                 data += "1"
        #             else:
        #                 data += "0"
        #         pass
        # global_setting.set_setting("mouse_cages", res['selected_indices'])
        experiment_settings = global_setting.get_setting("experiment_setting",None)

        gids = [group.id for group in experiment_settings.groups] if experiment_settings is not None else []
        global_setting.set_setting("mouse_cages",gids)
        # global_setting.set_setting("mouse_cages_2byte_str",data)
        global_setting.set_setting("mouse_cages_2byte_str", String_util.array_to_binary_string(gids))

        self.ufc_gas_path_system_start_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_start_thread.start()
        # 等待开始线程 把ufc启动完成
        global wait_UFC_start_finish_event
        wait_UFC_start_finish_event.wait()
        resolve()

    def ufc_start_timer_task(self,elapsed_ms):
        #ufc 气泵及设定鼠笼流量控制器开启 此过程需1分钟，等待流量控制器自动配置及运行



        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC 气泵及设定鼠笼流量控制器开启 此过程需{int(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['start_wait_time'])}s(当前{elapsed_ms//1000}s)，等待流量控制器自动配置及运行 .")

    def check_ufc_start_time_state(self):
        #定时器结束调用
        # logger.error("check_ufc_start_time_state")
        self.ufc_start_time_state =True

    """start end"""

    """run start"""
    def run(self,resolve,reject):
        """
        气路运行
        :return:
        """
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | UFC 开始运行{'.'*100}")

        AsyPromise(self.circular_running).then(lambda r:resolve(r)).catch(lambda e: logger.error(f"{e}"))


        pass
    def circular_running(self,resolve,reject):
        # 循环运行
        time.sleep(0.01)
        self.ufc_gas_path_system_run_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_run_thread.start()


        resolve()
        pass
    """run end"""
    def stop(self,resolve,reject):
        """
        停止气路
        :return:
        """
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | UFC 正在停止{'.'*100}")
        self.ufc_gas_path_system_run_thread.stop()

        self.ufc_gas_path_system_close_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_close_thread.start()
        # 等待开始线程 把ufc停止完成
        global wait_UFC_stop_finish_event
        wait_UFC_stop_finish_event.wait()
        resolve()
    pass


class UGC_gas_path_system_run_thread(MyQThread):
    """
    UGC 气路系统运行线程
    """

    def __init__(self, name, update_status_main_signal_gui_update):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: _PNamespaceSignal = update_status_main_signal_gui_update

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
        super().__init__(name=name)
    def before_Runing_work(self):
        pass
    def dosomething(self):
        wait_UFC_run_finish_event=global_setting.get_setting("wait_UFC_run_finish_event",None )
        if wait_UFC_run_finish_event:
            # 阻塞 等待ufc运行完在运行
            wait_UFC_run_finish_event.wait()
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            return
        #3.循环读取CO2浓度
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"00000005"),
            'slave_id': '3',
            'function_code': '4',
            'timeout': 1
        }
        mouse_cage_index = global_setting.get_setting("cage_number_list_index", None)
        mouse_cages_inc: list = global_setting.get_setting("mouse_cages", None)

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC-运行 2. 循环读取{'鼠笼'+str(mouse_cages_inc[mouse_cage_index]) if mouse_cage_index is not None else '参考气'}的CO2浓度")
        self.send_thread.send_message = self.send_message
        result_data, message = self.send_thread.Send_no_promise()
        logger.error(f"ugc:{result_data}")
        datas = result_data.get("data")
        # 数据不为TIME OUT 就进行补偿
        if datas and len(datas)>1 :
            co2 =None
            for data in datas:
                desc = data.get("desc")
                if desc and desc=="气压(KPa)":
                    # 获得气压的数据
                    air_pressure =float(data.get("value"))
                    global_setting.set_setting("air_pressure", air_pressure)

                elif desc and desc =="CO2(%)" :
                    # 获得co2的数据
                    co2 = data.get("value")


            # 进行压力补偿
            air_pressure=global_setting.get_setting("air_pressure", None)
            # 如果没有压力数据则补偿前后数据一样
            result_data["data"].append({"desc": "补偿前CO2(%)", "value": co2})
            if air_pressure is not None:
                # 当前co2数值/（1104测出来的气压值（没有就为标准大气压值）+当前读出大气压值） =co2补偿/标准大气压值 =》 co2补偿=（标准大气压值*当前co2数值）/（1104测出来的气压值（没有就为标准大气压值）+当前读出大气压值）
                co2_compensation=(float(global_setting.get_setting("UFC_UGC_ZOS_config")['PARAM']['standard_atmospheric_pressure'])*co2)/(global_setting.get_setting("air_pressure_1104",None) if global_setting.get_setting("air_pressure_1104",None) is not None else float(global_setting.get_setting("UFC_UGC_ZOS_config")['PARAM']['standard_atmospheric_pressure'])  +air_pressure)
                for i in range(len(result_data["data"])):
                    if result_data['data'][i]['desc']=="CO2(%)":
                        result_data['data'][i]['value'] = co2_compensation
                        break
                pass

        result_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        result_data['mouse_cage_number'] =mouse_cages_inc[mouse_cage_index] if mouse_cage_index is not  None else int(global_setting.get_setting('configer')['mouse_cage']['reference'])
        result = store_data_with_result(result_data, need_result=True, timeout=5)
        if result and result.success:
            logger.info(f"数据存储成功，ID: {result.item_id}")
        else:
            logger.error(f"数据存储失败: {result.error if result else '未知错误'}")
        time.sleep(float(global_setting.get_setting('UFC_UGC_ZOS_config')['UGC']['run_time_delay']))
        #通知zos 运行
        wait_UGC_run_finish_event=global_setting.get_setting("wait_UGC_run_finish_event",None )
        if wait_UGC_run_finish_event:
            wait_UGC_run_finish_event.set()
            wait_UGC_run_finish_event.clear()
        # # 让鼠笼内的传感器开始运行
        # ufc_ugc_zos_barrier = global_setting.get_setting("ufc_ugc_zos_barrier")
        # if ufc_ugc_zos_barrier is not None:
        #     logger.debug(f"ufc_ugc_zos_barrier_UGC run one batch done ! ")
        #     ufc_ugc_zos_barrier.wait()
        barrier = global_setting.get_setting("barrier")
        if barrier is not None:
            logger.debug(f"barrier_UGC run one batch done ! ")
            barrier.wait()
        pass
class UGC_gas_path_system(Gas_path_system):
    """
    UGC 气路系统
    """
    # UgC开始的操作数
    process_nums =1
    def __init__(self):
        super().__init__()
        # 运行线程
        self.ugc_gas_path_system_run_thread = UGC_gas_path_system_run_thread(
            name="UGC_gas_path_system_run_thread",
            update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,

        )
        pass
    def update(self):
        super().update()
        self.ugc_gas_path_system_run_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.ugc_gas_path_system_run_thread.send_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
    """start start"""
    def start(self,resolve,reject):
        """
        启动气路
        :return:
        """
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | UGC 正在启动")

        # 1.开泵抽气（正式开机）
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0004FF00"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC 正在启动-1.开泵抽气（正式开机）")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: resolve()
        ).catch(lambda e: reject(e))

        pass
        pass

    """start end"""
    """run start"""
    def run(self,resolve,reject):
        """
        气路运行
        :return:
        """
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | UGC 开始运行{'.'*100}")
        # 1.鼠笼气电磁阀开(sample 气)(开机默认打开)
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        # 修改命令反了 FF->00，11月1日改回，现和文档一致
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0000FF00"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC-运行 1.鼠笼气电磁阀开(sample 气)(开机默认打开)")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            # #2.鼠笼气电磁阀关(sample 气)
            # lambda r: AsyPromise(self.close_mouse_cage_valve,port=port)
            # 2.循环读取CO2浓度
            lambda r: AsyPromise(self.circular_running).then(lambda r1:resolve()
            ).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))
        pass
    # def close_mouse_cage_valve(self,resolve,reject,port):
    #     # 2.鼠笼气电磁阀关(sample 气)
    #     time.sleep(0.01)
    #     self.send_message = {
    #         'port': port,
    #         'data': number_util.set_int_to_4_bytes_list("00000000"),
    #         'slave_id': '3',
    #         'function_code': '5',
    #         'timeout': 1
    #     }
    #     self.update_status_main_signal_gui_update.send(
    #         f"{time_util.get_format_from_time(time.time())} | UGC-运行 2.鼠笼气电磁阀关(sample 气)(开机默认打开)")
    #     self.send_thread.send_message = self.send_message
    #     AsyPromise(self.send_thread.Send).then(
    #         # 3.循环读取CO2浓度
    #         lambda r: AsyPromise(self.circular_running)
    #     ).catch(lambda e: reject(e))
    #
    #     pass

    def circular_running(self, resolve, reject):
        # 3.循环读取CO2浓度
        time.sleep(0.01)
        self.ugc_gas_path_system_run_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.ugc_gas_path_system_run_thread.start()

        resolve()
        pass

    """run end"""
    def stop(self,resolve,reject):
        """
        停止气路
        :return:
        """
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | UGC 正在停止{'.'*100}")
        self.ugc_gas_path_system_run_thread.stop()

        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("00040000"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC-停止 1.停止UGC閥門")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            # 2.鼠笼气电磁阀关(sample 气)
            lambda r:AsyPromise(self.stop_finished).then(lambda r1:resolve()).catch(lambda e: reject(e))
        ).catch(lambda e: reject(e))
        pass

    pass
    def stop_finished(self,resolve,reject):
        #返回响应
        queue = global_setting.get_setting("queue", None)
        if queue:
            queue.put(
                ObjectQueueItem(origin="Gas_path_system_ugc", to="MainWindow_index", title="stop_ugc_gap_system_return",
                                data=" UGC 已停止",
                                time=time_util.get_format_from_time(time.time())))

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC 已停止{'.' * 100}")
        resolve()
class ZOS_gas_path_system_run_thread(MyQThread):
    """
    ZOS 气路系统运行线程
    """

    def __init__(self, name, update_status_main_signal_gui_update):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: _PNamespaceSignal = update_status_main_signal_gui_update

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
        super().__init__(name=name)
    def before_Runing_work(self):
        pass
    def dosomething(self):
        wait_UGC_run_finish_event = global_setting.get_setting("wait_UGC_run_finish_event", None)
        if wait_UGC_run_finish_event:
            # 阻塞 等待UGC运行完在运行
            wait_UGC_run_finish_event.wait()
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            return
        # 3.循环读取CO2浓度
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"00000002"),
            'slave_id': '4',
            'function_code': '4',
            'timeout': 1
        }
        mouse_cage_index = global_setting.get_setting("cage_number_list_index", None)
        mouse_cages_inc: list = global_setting.get_setting("mouse_cages", None)

        # 获取当前鼠笼号
        mouse_cage_number = mouse_cages_inc[mouse_cage_index] if mouse_cage_index is not None \
            else int(global_setting.get_setting('configer')['mouse_cage']['reference'])

        # 初始化O2采样缓存
        with o2_cache_lock:
            if mouse_cage_number not in o2_measurement_cache:
                o2_measurement_cache[mouse_cage_number] = {
                    'start_time': time.time(),
                    'o2_5s': None,
                    'o2_10s': None,
                    'o2_15s': None
                }
                logger.info(f"初始化鼠笼{mouse_cage_number}的O2采样缓存")

        # 启动三点采样流程
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS-运行 1. 鼠笼{mouse_cage_number}开始三点O2采样")

        # 链式调用三点采样（修正版）
        AsyPromise(self.read_o2_at_5s, port=port, mouse_cage_number=mouse_cage_number).then(
            lambda r: AsyPromise(self.read_o2_at_10s, port=port, mouse_cage_number=mouse_cage_number)
        ).then(
            lambda r: AsyPromise(self.read_o2_at_15s, port=port, mouse_cage_number=mouse_cage_number)
        ).then(
            lambda r: AsyPromise(self.predict_and_store_steady_o2,
                                 port=port, mouse_cage_number=mouse_cage_number)
        ).then(
            lambda r: AsyPromise(self.check_senior_state, port=port, r=r)
        ).then(
            lambda r: AsyPromise(self._update_cage_index_and_barrier,
                                 mouse_cage_index=mouse_cage_index,
                                 mouse_cages_inc=mouse_cages_inc)
        ).catch(lambda e: logger.error(f"ZOS三点采样流程失败: {e}"))

        time.sleep(float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['run_time_delay']))
        # self.update_status_main_signal_gui_update.send(
        #     f"{time_util.get_format_from_time(time.time())} | ZOS-运行 1. 循环读取{'鼠笼'+str(mouse_cages_inc[mouse_cage_index]) if mouse_cage_index is not None else '参考气'}的氧浓度")
        # self.send_thread.send_message = self.send_message
        # AsyPromise(self.send_thread.Send).then(
        #     # 2.传感器故障检测 如果在非调零状态下，氧浓度异常，小于某一个阈值（如1%），检查传感器状态
        #     lambda r:AsyPromise(self.check_senior_state,port=port,r=r)
        # ).catch(lambda e: logger.error(f"{e}"))
        # time.sleep(float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['run_time_delay']))
        # # # 让鼠笼内的传感器开始运行
        # # ufc_ugc_zos_barrier = global_setting.get_setting("ufc_ugc_zos_barrier")
        # # if ufc_ugc_zos_barrier is not None:
        # #     logger.debug(f"ufc_ugc_zos_barrier_ZOS run one batch done ! ")
        # #     ufc_ugc_zos_barrier.wait()
        # # 将鼠笼下标循环前移动
        #
        # mouse_cage_index = global_setting.get_setting("cage_number_list_index", None)
        # # logger.critical(f"zos run :mouse_cage_index before:{mouse_cage_index}")
        # mouse_cages_inc: list = global_setting.get_setting("mouse_cages", None)
        # if mouse_cage_index is not None:
        #     if mouse_cage_index == len(mouse_cages_inc) - 1:
        #         # 最后一个鼠笼 则下一个为参考气路
        #         mouse_cage_index = None
        #     else:
        #         mouse_cage_index = mouse_cage_index + 1
        #     pass
        # else:
        #     # 当前为参考气 则下一个为第一个鼠笼
        #     mouse_cage_index = 0
        #     pass
        # global_setting.set_setting("cage_number_list_index", mouse_cage_index)
        # # logger.critical(f"zos run :mouse_cage_index after:{mouse_cage_index}")
        # barrier = global_setting.get_setting("barrier")
        # if barrier is not None:
        #     logger.debug(f"barrier_ZOS run one batch done ! ")
        #     barrier.wait()
        # pass

    def check_senior_state(self, resolve, reject, port, r):
        """
        检查传感器状态，存储最终数据，并进行故障检测。
        去除冗余：直接使用缓存中的稳态值，不再重复进行单点修正。
        """
        try:
            # 1. 获取基本信息
            mouse_cage_index = global_setting.get_setting("cage_number_list_index", None)
            mouse_cages_inc: list = global_setting.get_setting("mouse_cages", None)

            # 确定当前鼠笼号
            current_cage_num = mouse_cages_inc[mouse_cage_index] if mouse_cage_index is not None else int(
                global_setting.get_setting('configer')['mouse_cage']['reference'])

            # 2. 获取最终的稳态O2值 (这是核心去冗余步骤)
            # 尝试获取基于5s/10s/15s计算出的稳态值
            final_o2_value = None

            with o2_cache_lock:
                cache_data = o2_measurement_cache.get(current_cage_num)
                if cache_data:
                    # 尝试重新快速计算稳态值 (开销极小)，确保使用的是三点模型结果
                    # 注意：这里假设 o2_5s 等在之前的步骤中已经经过了 calibrate_and_compensate
                    o2_5s = cache_data.get('o2_5s')
                    o2_10s = cache_data.get('o2_10s')
                    o2_15s = cache_data.get('o2_15s')

                    if o2_5s is not None and o2_10s is not None and o2_15s is not None:
                        final_o2_value = O2CorrectionManager.predict_steady_o2_three_point(o2_5s, o2_10s, o2_15s)
                        logger.info(f"check_senior_state 使用三点稳态值: {final_o2_value}")
                    elif o2_15s is not None:
                        # 如果数据不全，使用第15秒的值（它已经是校准过的）
                        final_o2_value = o2_15s
                        logger.warning(f"check_senior_state 数据不全，降级使用15s值: {final_o2_value}")

            # 如果缓存里完全没数据 (异常情况)，尝试从当前 r 包里提取并做单点修正
            if final_o2_value is None:
                logger.warning("缓存缺失，回退到单点修正模式")
                raw_data = r.get('data', {}).get('data', [])
                for item in raw_data:
                    if item.get('desc') == '氧气传感器测量值(%)':
                        raw_val = float(item.get('value', 0))
                        final_o2_value = O2CorrectionManager.calibrate_and_compensate(raw_val)
                        break

            # 3. 准备存储数据
            result_data = r.get('data', {})
            if not result_data:
                # 防止 r['data'] 为空的情况
                result_data = {'data': []}

            result_data['mouse_cage_number'] = current_cage_num
            result_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # 4. 更新数据包中的值为最终修正值
            updated = False
            if final_o2_value is not None:
                for item in result_data.get('data', []):
                    if item.get('desc') == '氧气传感器测量值(%)':
                        item['value'] = final_o2_value
                        updated = True
                        break

                # 如果原包里没有这个字段，手动添加（防止数据丢失）
                if not updated:
                    result_data.setdefault('data', []).append({
                        'desc': '氧气传感器测量值(%)',
                        'value': final_o2_value
                    })

            # 5. 存储数据
            logger.info(f"ZOS最终存储数据 (Cage {current_cage_num}): O2={final_o2_value}")
            result = store_data_with_result(result_data, need_result=True, timeout=5)
            if result and result.success:
                logger.info(f"数据存储成功，ID: {result.item_id}")
            else:
                logger.error(f"数据存储失败: {result.error if result else '未知错误'}")

            # 6. 传感器故障监测 (去除Regex解析，直接使用数值)
            if final_o2_value is not None:
                threshold = float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['threshold'])

                if final_o2_value < threshold:
                    logger.warning(f"ZOS-运行 异常: 氧浓度({final_o2_value}%) < 阈值({threshold}%)")

                    # 发送查询状态指令
                    self.send_message = {
                        'port': port,
                        'data': number_util.set_int_to_4_bytes_list(f"00000002"),
                        'slave_id': '4',
                        'function_code': '2',
                        'timeout': 1
                    }
                    self.update_status_main_signal_gui_update.send(
                        f"{time_util.get_format_from_time(time.time())} | ZOS-运行 2. 氧浓度({final_o2_value}%)异常，检查传感器状态")
                    self.send_thread.send_message = self.send_message
                    self.send_thread.Send_no_promise()

        except Exception as e:
            logger.error(f"check_senior_state 发生错误: {e}")

        finally:
            resolve()

    def read_o2_at_5s(self, resolve, reject, port, mouse_cage_number):
        """第5秒读取O2值"""
        try:
            with o2_cache_lock:
                start_time = o2_measurement_cache[mouse_cage_number]['start_time']

            # 计算需要等待的时间
            wait_time = 5 - (time.time() - start_time)
            if wait_time > 0:
                time.sleep(wait_time)

            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | ZOS 读取第5秒O2值")

            # 发送读取指令
            self.send_message = {
                'port': port,
                'data': number_util.set_int_to_4_bytes_list("00000002"),
                'slave_id': '4',
                'function_code': '4',
                'timeout': 1
            }
            self.send_thread.send_message = self.send_message

            AsyPromise(self.send_thread.Send).then(
                lambda r: self._extract_and_store_o2_value(r, '5s', mouse_cage_number, resolve, reject)
            ).catch(lambda e: reject(e))
        except Exception as e:
            logger.error(f"read_o2_at_5s异常: {e}")
            reject(e)

    def read_o2_at_10s(self, resolve, reject, port, mouse_cage_number):
        """第10秒读取O2值"""
        try:
            with o2_cache_lock:
                start_time = o2_measurement_cache[mouse_cage_number]['start_time']

            # 计算需要等待的时间
            wait_time = 10 - (time.time() - start_time)
            if wait_time > 0:
                time.sleep(wait_time)

            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | ZOS 读取第10秒O2值")

            # 发送读取指令
            self.send_message = {
                'port': port,
                'data': number_util.set_int_to_4_bytes_list("00000002"),
                'slave_id': '4',
                'function_code': '4',
                'timeout': 1
            }
            self.send_thread.send_message = self.send_message

            AsyPromise(self.send_thread.Send).then(
                lambda r: self._extract_and_store_o2_value(r, '10s', mouse_cage_number, resolve, reject)
            ).catch(lambda e: reject(e))
        except Exception as e:
            logger.error(f"read_o2_at_10s异常: {e}")
            reject(e)

    def read_o2_at_15s(self, resolve, reject, port, mouse_cage_number):
        """第15秒读取O2值"""
        try:
            with o2_cache_lock:
                start_time = o2_measurement_cache[mouse_cage_number]['start_time']

            # 计算需要等待的时间
            wait_time = 15 - (time.time() - start_time)
            if wait_time > 0:
                time.sleep(wait_time)

            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | ZOS 读取第15秒O2值")

            # 发送读取指令
            self.send_message = {
                'port': port,
                'data': number_util.set_int_to_4_bytes_list("00000002"),
                'slave_id': '4',
                'function_code': '4',
                'timeout': 1
            }
            self.send_thread.send_message = self.send_message

            AsyPromise(self.send_thread.Send).then(
                lambda r: self._extract_and_store_o2_value(r, '15s', mouse_cage_number, resolve, reject)
            ).catch(lambda e: reject(e))
        except Exception as e:
            logger.error(f"read_o2_at_15s异常: {e}")
            reject(e)

    def _extract_and_store_o2_value(self, response, time_point, mouse_cage_number, resolve, reject):
        """
        从响应中提取O2值，进行校准和压力补偿，存储到缓存
        :param response: 发送指令的响应
        :param time_point: 时间点标识 ('5s', '10s', '15s')
        :param mouse_cage_number: 鼠笼号
        """
        try:
            result_data = response.get('data', {})

            # 从响应数据中找到氧气传感器测量值
            o2_raw = None
            data_list = result_data.get('data', []) if isinstance(result_data, dict) else []

            for data_struct in data_list:
                if data_struct.get('desc') == '氧气传感器测量值(%)':
                    o2_raw = float(data_struct.get('value', 0))
                    break

            if o2_raw is None:
                logger.warning(f"未从{time_point}响应中找到O2值")
                reject(f"缺少{time_point}的O2值")
                return

            # 第一步：校准 = (raw - Vzero) * K
            Vzero = global_setting.get_setting("Vzero", 0)
            K = global_setting.get_setting("K", 1)
            o2_calibrated = round((o2_raw - Vzero) * K, 6)

            # 第二步：气压补偿
            air_pressure = global_setting.get_setting("air_pressure", None)
            if air_pressure is not None:
                standard_atm = float(
                    global_setting.get_setting("UFC_UGC_ZOS_config")['PARAM']['standard_atmospheric_pressure'])
                o2_compensation_coeff = float(
                    global_setting.get_setting("UFC_UGC_ZOS_config")['PARAM']['oxygen_compensation_coefficient'])

                o2_compensated = (o2_calibrated / (1 + air_pressure / standard_atm)) * o2_compensation_coeff
                o2_value = round(o2_compensated, 6)
            else:
                o2_value = o2_calibrated

            # 存储到缓存
            with o2_cache_lock:
                if mouse_cage_number in o2_measurement_cache:
                    o2_measurement_cache[mouse_cage_number][f'o2_{time_point}'] = o2_value
                    logger.info(
                        f"鼠笼{mouse_cage_number} {time_point}O2值: raw={o2_raw:.2f}, 校准={o2_calibrated:.2f}, 补偿={o2_value:.2f}")
            # 第二步：立即存储中间数据（持久化）
            intermediate_data = {
                'module_name': 'ZOS_Intermediate',
                'mouse_cage_number': mouse_cage_number,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'data': [
                    {'desc': f'氧气传感器测量值(%)_{time_point}_原始', 'value': o2_raw},
                    {'desc': f'氧气传感器测量值(%)_{time_point}_修正', 'value': o2_value}
                ]
            }
            store_data_with_result(intermediate_data, need_result=False, timeout=2)

            logger.info(
                f"鼠笼{mouse_cage_number} {time_point}O2值: raw={o2_raw:.2f} → corrected={o2_value:.2f}")
            resolve(response)
        except Exception as e:
            logger.error(f"提取{time_point}O2值失败: {e}")
            reject(e)

    def _update_cage_index_and_barrier(self, resolve, reject, mouse_cage_index, mouse_cages_inc):
        """更新鼠笼下标并等待barrier"""
        try:
            if mouse_cage_index is not None:
                if mouse_cage_index == len(mouse_cages_inc) - 1:
                    mouse_cage_index = None
                else:
                    mouse_cage_index = mouse_cage_index + 1
            else:
                mouse_cage_index = 0

            global_setting.set_setting("cage_number_list_index", mouse_cage_index)
            logger.debug(f"ZOS运行完成，下一轮鼠笼下标: {mouse_cage_index}")

            barrier = global_setting.get_setting("barrier")
            if barrier is not None:
                logger.debug(f"barrier_ZOS run one batch done!")
                barrier.wait()

            resolve()  # 必须调用 resolve
        except Exception as e:
            logger.error(f"更新鼠笼下标失败: {e}")
            reject(e)

    def predict_and_store_steady_o2(self, resolve, reject, port, mouse_cage_number):
        """预测稳态O2值并存储"""
        try:
            with o2_cache_lock:
                cache_data = o2_measurement_cache.get(mouse_cage_number)
                if cache_data is None:
                    logger.warning(f"缺少鼠笼{mouse_cage_number}的O2缓存")
                    resolve(None)
                    return

                o2_5s = cache_data.get('o2_5s')
                o2_10s = cache_data.get('o2_10s')
                o2_15s = cache_data.get('o2_15s')

            if o2_5s is not None and o2_10s is not None and o2_15s is not None:
                o2_steady = O2CorrectionManager.predict_steady_o2_three_point(
                    o2_5s, o2_10s, o2_15s)

                logger.info(f"鼠笼{mouse_cage_number}稳态O2: {o2_steady}%")

                result_data = {
                    'module_name': 'ZOS',
                    'mouse_cage_number': mouse_cage_number,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    'data': [
                        {'desc': '氧气传感器测量值(%)_5s', 'value': o2_5s},
                        {'desc': '氧气传感器测量值(%)_10s', 'value': o2_10s},
                        {'desc': '氧气传感器测量值(%)_15s', 'value': o2_15s},
                        {'desc': '氧气传感器测量值(%)_稳态', 'value': o2_steady}
                    ]
                }

                result = store_data_with_result(result_data, need_result=True, timeout=5)
                if result and result.success:
                    logger.info(f"稳态O2数据存储成功，ID: {result.item_id}")
                else:
                    logger.error(f"稳态O2数据存储失败: {result.error if result else '未知错误'}")
            else:
                logger.warning(f"缺少完整的O2三点数据: 5s={o2_5s}, 10s={o2_10s}, 15s={o2_15s}")

            resolve(None)  # 必须调用 resolve
        except Exception as e:
            logger.error(f"稳态O2预测失败: {e}")
            reject(e)

class ZOS_gas_path_system(Gas_path_system):
    """
    ZOS 气路系统
    """
    # UFC开始的操作数
    process_nums =2+2+2
    def __init__(self):
        super().__init__()
        # zos启动状态
        self.zos_start_status = False
        # 运行线程
        self.zos_gas_path_system_run_thread = ZOS_gas_path_system_run_thread(
            name="ZOS_gas_path_system_run_thread",
            update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,

        )
        pass
    def update(self):
        super().update()
        self.zos_gas_path_system_run_thread. update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.zos_gas_path_system_run_thread.send_thread.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
    """start start"""
    def judge_zos_start_status(self,resolve,reject,r):

        if "ZOS状态状态：运行" in r['message']:
            self.zos_start_status = True
        else:
            self.zos_start_status = False
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS 启动状态:{'运行' if self.zos_start_status else '停止（预热）'}{r}-end.")

        resolve()
    def start(self,resolve,reject):
        """
        启动气路
        :return:
        """
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | ZOS 正在启动")
        #1.读取系统状态
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("1"),
            'slave_id': '4',
            'function_code': '1',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | ZOS 正在启动 1.读取系统状态")
        AsyPromise(self.send_thread.Send).then(
                lambda r:AsyPromise(self.judge_zos_start_status,r=r).then(lambda r:resolve()
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e:reject(e))

        pass

    def zos_start_timer_task(self,elapsed_ms):
        #zos启动之后需要预热

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS 正在预热时间为{int(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['start_time'])}s(当前{elapsed_ms//1000}s)，循环判断zos状态是否完成，预热完成进入运行状态-start.")

        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("1"),
            'slave_id': '4',
            'function_code': '1',
            'timeout': 1
        }
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: AsyPromise(self.judge_zos_start_status, r=r)
        )
    """start end"""
    """run start"""
    def run(self,resolve,reject):
        """
        气路运行
        :return:
        """
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | ZOS 开始运行{'.'*100}")
        #1.循环读取氧浓度
        self.zos_gas_path_system_run_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.zos_gas_path_system_run_thread.start()

        resolve()
        pass
    """run end"""
    def stop(self,resolve,reject):
        """
        停止气路
        :return:
        """
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | ZOS 正在停止{'.'*100}")
        self.zos_gas_path_system_run_thread.stop()
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS 已停止{'.' * 100}")
        # 返回响应
        queue = global_setting.get_setting("queue", None)
        if queue:
            queue.put(
                ObjectQueueItem(origin="Gas_path_system", to="MainWindow_index", title="stop_gap_system_return",
                                data=" ZOS 已停止",
                                time=time_util.get_format_from_time(time.time())))
        resolve()
        pass

    pass