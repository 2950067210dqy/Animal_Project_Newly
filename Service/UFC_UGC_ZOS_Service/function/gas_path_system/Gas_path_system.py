import abc

import re

import time
from datetime import datetime
from threading import Event, Barrier

from blinker.base import _PNamespaceSignal
from loguru import logger


from Service.UFC_UGC_ZOS_Service.function.Send_Message.Send_Message import Send_Message

from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from public.function.Monitor_data_storage.DataStorage import store_data_with_result
from public.function.promise.AsyPromise import AsyPromise
from public.util.number_util import number_util
from public.util.time_util import time_util

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
        # ).catch(lambda e: logger.error(e))
        AsyPromise(self.ufc_start).then(
            self.stop()
        ).catch(lambda e:logger.error(e))
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
        # 4. 打开zos采样阀
        # 等待时间
        time.sleep(float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['start_wait_time_delay']) )

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
        ).catch(lambda e:logger.error(e))
    def finsh_start(self,resolve, reject):

        self.parent_class.ufc_start_time_state = True
        # logger.critical(f"ufc_finish_start:{self.parent_class.ufc_start_time_state}")
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
            lambda r:  resolve()
        )
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC 已关闭")
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
        #鼠笼list的index

        self.mouse_cage_index = 0
        #参考气路的值
        self.reference_gap_value = None
        super().__init__(name=name)
    def before_Runing_work(self):
        mouse_cages_inc: list = global_setting.get_setting("mouse_cages", None)
        if mouse_cages_inc is not None and len(mouse_cages_inc) > 0:
            # 从参考气开始

            self.mouse_cage_index = len(mouse_cages_inc) - 1
        else:

            # 从鼠笼1开始
            self.mouse_cage_index = 0
        pass
    def dosomething(self):

        mouse_cages_inc:list=global_setting.get_setting("mouse_cages",None)
        if mouse_cages_inc is not None and len(mouse_cages_inc) > 0:
            port = global_setting.get_setting("port", None)
            if port is None:
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
                AsyPromise(self.finsh_one_batch, port=None, mouse_cages_inc=mouse_cages_inc).then(

                ).catch(lambda e: logger.error(e))
                return
            # 从我们之前选择的运行鼠笼拿出来 每次循环访问一个
            AsyPromise(self.switch_mouse_cage_gas,port=port,mouse_cages_inc=mouse_cages_inc).then(

            ).catch(lambda e:logger.error(e))
            pass
        else:
            AsyPromise(self.finsh_one_batch,port=None, mouse_cages_inc=mouse_cages_inc).then(

            ).catch(lambda e:logger.error(e))



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
        mouse_cage_number_addr_single = mouse_cages_inc[self.mouse_cage_index]
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
            f"{time_util.get_format_from_time(time.time())} | {'-' * 500}")
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-运行 1. 切换{str(mouse_cage_number_addr_single + 1) + '号鼠笼' if mouse_cage_number_addr_single < 8 else str(mouse_cage_number_addr_single + 1) + '号鼠笼(参考气)'}")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            # 2. 关闭上个鼠笼的气路或者关闭参考气
            lambda r: AsyPromise(self.close_last_mouse_cage_gas, port=port, mouse_cages_inc=mouse_cages_inc).then(
                lambda r:resolve()
            ).catch(lambda e: logger.error(e))
        ).catch(lambda e: logger.error(e))
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
        mouse_cage_number_addr_single = mouse_cages_inc[self.mouse_cage_index-1 if self.mouse_cage_index!=0 else len(mouse_cages_inc)-1]
        #2.关闭上个鼠笼号，如果当前鼠笼号为0，则关闭参考气体
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UFC-运行 2. 关闭{str(mouse_cage_number_addr_single + 1)+'号鼠笼' if mouse_cage_number_addr_single!=8 else str(mouse_cage_number_addr_single + 1)+'号鼠笼(参考气)'}")
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
        ).catch(lambda e: logger.error(e))


        pass
    def read_flow_rate_value_circulation(self,resolve,reject,port,mouse_cages_inc):
        """
        循环读取流量值 （推荐每2秒读取一次）（原定为15秒）
        """
        time.sleep(0.01)
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
        # 参考气路
        if mouse_cages_inc[self.mouse_cage_index]+1 ==9:
            logger.error(f"---------------参考气路值：{result_data['data']}")

            self.reference_gap_value=result_data['data'][0]['value']
            # 获得参考气则直接进行下个鼠笼的UFC数据获取
            # 将鼠笼下标循环前移动
            self.mouse_cage_index = (self.mouse_cage_index + 1) % len(mouse_cages_inc)
            AsyPromise(self.switch_mouse_cage_gas, port=port, mouse_cages_inc=mouse_cages_inc).then(
                lambda r:resolve()
            ).catch(lambda e: logger.error(e))
            return
        #其他鼠笼气路
        else:

            result_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            result_data['data'].insert(0,{'desc':'鼠笼号','value':  mouse_cages_inc[self.mouse_cage_index]+1})
            result_data['data'].append( {'desc':'参考气路流量计测量值(sccm)','value':self.reference_gap_value})
            logger.error(f"---------------鼠笼气路值：{result_data['data']}")
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
        ).catch(lambda e: logger.error(e))

    def finsh_one_batch(self,resolve,reject,port,mouse_cages_inc):
        """
        完成一轮次后做的事情
        :param resolve:
        :param reject:
        :param port:
        :param mouse_cages_inc:
        :return:
        """
        barrier: Barrier = global_setting.get_setting("barrier")
        if barrier is not None:
            logger.debug(f"barrier_UFC run one batch done ! ")
            barrier.wait()
        # 将鼠笼下标循环前移动
        self.mouse_cage_index = (self.mouse_cage_index + 1) % len(mouse_cages_inc)
        resolve()
class UFC_gas_path_system(Gas_path_system):
    """
    UFC 气路系统
    """
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
        global_setting.set_setting("mouse_cages",[0,1,2,3,4,5,6,7,8])
        # global_setting.set_setting("mouse_cages_2byte_str",data)
        global_setting.set_setting("mouse_cages_2byte_str", "111111111")

        self.ufc_gas_path_system_start_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.ufc_gas_path_system_start_thread.start()
        resolve()

    def ufc_start_timer_task(self,elapsed_ms):
        #ufc 气泵及设定鼠笼流量控制器开启 此过程需1分钟，等待流量控制器自动配置及运行

        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | {'-'*100}")

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

        AsyPromise(self.circular_running).then(lambda r:resolve(r)).catch(lambda e:logger.error(e))


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
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            return
        #3.循环读取CO2浓度
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list(f"00000008"),
            'slave_id': '3',
            'function_code': '4',
            'timeout': 1
        }
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | {'-' * 500}")
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC-运行 2. 循环读取CO2浓度")
        self.send_thread.send_message = self.send_message
        result_data, message = self.send_thread.Send_no_promise()
        result_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        result = store_data_with_result(result_data, need_result=True, timeout=5)
        if result and result.success:
            logger.info(f"数据存储成功，ID: {result.item_id}")
        else:
            logger.error(f"数据存储失败: {result.error if result else '未知错误'}")
        time.sleep(float(global_setting.get_setting('UFC_UGC_ZOS_config')['UGC']['run_time_delay']))
        barrier: Barrier = global_setting.get_setting("barrier")
        if barrier is not None:
            logger.debug(f"barrier_UGC run one batch done ! ")
            barrier.wait()
        pass
class UGC_gas_path_system(Gas_path_system):
    """
    UGC 气路系统
    """

    def __init__(self):
        super().__init__()
        # 运行线程
        self.ugc_gas_path_system_run_thread = UGC_gas_path_system_run_thread(
            name="UGC_gas_path_system_run_thread",
            update_status_main_signal_gui_update=self.update_status_main_signal_gui_update,

        )
        pass
    """start start"""
    def start(self,resolve,reject):
        """
        启动气路
        :return:
        """
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | UGC 正在启动{'.'*100}")

        # 1.读取系统状态
        port = global_setting.get_setting("port", None)
        if port is None:
            self.update_status_main_signal_gui_update.send(
                f"{time_util.get_format_from_time(time.time())} | 启动失败，未选择串口！")
            reject()
        self.send_message = {
            'port': port,
            'data': number_util.set_int_to_4_bytes_list("0004ff00"),
            'slave_id': '3',
            'function_code': '5',
            'timeout': 1
        }

        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            lambda r: resolve(r)
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
            # lambda r: AsyPromise(self.close_mouse_cage_valve,port=port),resolve()
            # 2.循环读取CO2浓度
            lambda r: AsyPromise(self.circular_running),resolve()
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
    #         lambda r: AsyPromise(self.circular_running),resolve()
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
            lambda r:self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | UGC 已停止{'.' * 100}"), resolve()
        ).catch(lambda e: reject(e))
        pass

    pass
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
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | {'-' * 500}")
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS-运行 1. 循环读取氧浓度")
        self.send_thread.send_message = self.send_message
        AsyPromise(self.send_thread.Send).then(
            # 2.传感器故障检测 如果在非调零状态下，氧浓度异常，小于某一个阈值（如1%），检查传感器状态
            lambda r:AsyPromise(self.check_senior_state,port=port,r=r)
        ).catch(lambda e: logger.error(e))
        time.sleep(float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['run_time_delay']))
        barrier: Barrier = global_setting.get_setting("barrier")
        if barrier is not None:
            logger.debug(f"barrier_ZOS run one batch done ! ")
            barrier.wait()
        pass
    def check_senior_state(self,resolve,reject,port,r):
        #存储值
        result_data = r['data']
        result_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        if len(result_data['data'])>0:
            oxygen_value = [data_struct['value']  for data_struct in result_data['data'] if data_struct['desc']=='氧传感器测量值(%)']
            if len(oxygen_value)>0:
                oxygen_value = oxygen_value[0]
                # 氧浓度V应校准为（V-Vzero）* K
                oxygen_value =round((oxygen_value-global_setting.get_setting("Vzero",0))*global_setting.get_setting("K",1),3)
                for i in range(len(result_data)):
                    if result_data['data'][i]['desc']=='氧传感器测量值(%)':
                        logger.warning(f"'氧传感器测量值(%)经过校准后得:{oxygen_value}")
                        result_data['data'][i]['value'] = oxygen_value
                        break
        # logger.critical(f"{'-'*500}|{result_data}")
        result = store_data_with_result(result_data, need_result=True, timeout=5)
        if result and result.success:
            logger.info(f"数据存储成功，ID: {result.item_id}")
        else:
            logger.error(f"数据存储失败: {result.error if result else '未知错误'}")
        """2.传感器故障监测"""
        m = re.search(r"氧传感器测量值\(%\)\s*:\s*([0-9]+(?:\.[0-9]+)?)", r['message'])
        if m:
            value_str = m.group(1)
            value = float(value_str)
            #如果在非调零状态下，氧浓度异常，小于某一个阈值（如1%），检查传感器状态
            if value <float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['threshold']):
                # 3.循环读取CO2浓度
                self.send_message = {
                    'port': port,
                    'data': number_util.set_int_to_4_bytes_list(f"00000002"),
                    'slave_id': '4',
                    'function_code': '2',
                    'timeout': 1
                }
                self.update_status_main_signal_gui_update.send(
                    f"{time_util.get_format_from_time(time.time())} | ZOS-运行 2. 氧浓度({value}%)异常，小于阈值（{float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['threshold'])}%），检查传感器状态")
                self.send_thread.send_message = self.send_message
                self.send_thread.Send_no_promise()
        resolve()

        pass

class ZOS_gas_path_system(Gas_path_system):
    """
    ZOS 气路系统
    """

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
    """start start"""
    def judge_zos_start_status(self,resolve,reject,r):

        if "ZOS状态状态：运行" in r['message']:
            self.zos_start_status = True
        else:
            self.zos_start_status = False
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | ZOS 启动状态:{'运行' if self.zos_start_status else '停止（预热）'}{r}{'-'*100}-end.")

        resolve()
    def start(self,resolve,reject):
        """
        启动气路
        :return:
        """
        time.sleep(0.01)
        self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | ZOS 正在启动{'.'*100}")
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
        AsyPromise(self.send_thread.Send).then(
           lambda r:AsyPromise(self.judge_zos_start_status,r=r)
        ).catch(lambda e:reject(e))

        pass

    def zos_start_timer_task(self,elapsed_ms):
        #zos启动之后需要预热
        self.update_status_main_signal_gui_update.send(
            f"{time_util.get_format_from_time(time.time())} | {'-'*100}")

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
        resolve()
        pass

    pass