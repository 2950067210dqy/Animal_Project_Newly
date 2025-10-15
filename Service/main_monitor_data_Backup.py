import copy
import json
import multiprocessing
import os
import queue
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime

from PyQt6.QtCore import QThread, QTimer, QCoreApplication
from PyQt6.QtWidgets import QApplication
from loguru import logger

from Service.UFC_UGC_ZOS_Service.index.UFC_UGC_ZOS_index import UFC_UGC_ZOS_index

from public.config_class import global_load
from public.config_class.global_setting import global_setting

from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.MyQThread import MyQThread, MyThread
from public.entity.experiment_setting_entity import Experiment_setting_entity
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Modbus.Modbus import ModbusRTUMaster
from public.function.Modbus.Modbus_Type import Modbus_Slave_Type, Modbus_Slave_Send_Messages_Senior_Data, Others_Tables
from public.function.Modbus.New_Mod_Bus import ModbusRTUMasterNew
from public.util.number_util import number_util
from public.util.time_util import time_util

# 全局变量
# 实现主线程发一整轮消息，当从线程响应完全部的消息后，主线程在发一整轮消息
MESSAGE_BATCH_SIZE = 0
total_messages_processed = 1
lock = threading.Lock()
batch_complete_event = threading.Event()
#等待气路启动之后在一起运行发送
wait_UFC_UGC_ZOS_start_event = threading.Event()
global_setting.set_setting("wait_UFC_UGC_ZOS_start_event",wait_UFC_UGC_ZOS_start_event)
#使用端口
port_use=None
# 存储数据锁
store_Q_lock = threading.Lock()
store_Q = queue.Queue()
#  放进全局变量中
global_setting.set_setting("store_Q_lock",store_Q_lock)
global_setting.set_setting("store_Q",store_Q)
# 过滤日志
#logger = logger.bind(category="deep_camera_logger")

class read_queue_data_Thread(MyQThread):
    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.send_thread: Send_thread = None
        pass

    def stop(self):
        if self.send_thread is not None and self.send_thread.isRunning():
            self.send_thread.stop()
        super().stop()
    def dosomething(self):
        if not self.queue.empty():
            # logger.error(f"{self.queue.qsize()}")
            message:ObjectQueueItem = self.queue.get()
            # logger.error(f"{self.name}_get_message:{message}|")
            if message is not None and message.is_Empty():
                return
            if message is not None and isinstance(message, ObjectQueueItem) and message.to == 'main_monitor_data':
                # logger.error(f"{self.name}_get_message:{message}")
                match message.title:
                    case '':
                        if self.send_thread is not None and self.send_thread.isRunning():
                            # 发送优先级高的报文
                            self.send_thread.add_message(message=message.data, urgent=True, origin=message.origin)
                            pass
                    case 'set_port':
                        global port_use
                        port_use=message.data
                        global_setting.set_setting("port", port_use)
                        modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
                        if modbus is None:
                            modbus = ModbusRTUMasterNew(port_use, baudrate=115200, timeout=float(
                                global_setting.get_setting('monitor_data')['Serial']['timeout']), )
                            global_setting.set_setting("modbus", modbus)
                        else:
                            modbus.close()
                            modbus = ModbusRTUMasterNew(port_use, baudrate=115200, timeout=float(
                                global_setting.get_setting('monitor_data')['Serial']['timeout']), )
                            global_setting.set_setting("modbus", modbus)
                    case 'start':
                        data = message.data
                        if data is not None:
                            global_setting.set_setting("start_experiment_time", data.get("start_experiment_time",time.time()))
                            global_setting.set_setting("pause_experiment_time", data.get("pause_experiment_time",[]))
                            global_setting.set_setting("relieve_pause_experiment_time", data.get("relieve_pause_experiment_time",[]))
                        start()
                    case 'pause':
                        pause()
                    case 'stop':
                        stop()
                    case 'experiment_setting':
                        data = message.data
                        if data is not None:
                            # 将实验设置存入全局变量
                            global_setting.set_setting("experiment_setting", data.get("experiment_setting", None))
                            global_setting.set_setting("experiment_setting_file",
                                                       data.get("experiment_setting_file", ""))

                        pass
                    case _:
                        pass




            else:
                # 把消息放回去
                self.queue.put(message)

        pass


read_queue_data_thread = read_queue_data_Thread(name="main_monitor_data_read_queue_data_thread")



class Store_Thread(MyQThread):
    """
    存储请求线程发来的数据到sqlite中
    """

    def __init__(self, name):
        self.handle = None
        super().__init__(name)

    def dosomething(self):
        global store_Q, store_Q_lock
        # 队列中有数据在存储 且接收数据线程存活 才存数据
        if not store_Q.empty():
            try:
                # 加锁
                with store_Q_lock:
                    data = store_Q.get()  # 修改全局变量
                # 解锁会在with块结束后自动处理
            except queue.Empty:
                logger.error(f"数据队列Q为空，获取数据失败！")
            logger.info(f"存储数据线程开始存储数据: {data}")
            # 存储到文件里
            self.store_to_data_base(data)
        time.sleep(float(global_setting.get_setting('monitor_data')['STORAGE']['delay']))
        pass

    def store_to_data_base(self, data):
        try:
            # 存储到数据库中
            # if self.handle is not None:
            #     self.handle.stop()
            if self.handle is None:

                self.handle = Monitor_Datas_Handle()  # # 创建数据库

            self.handle.insert_data(data)
        except Exception as e:
            logger.error(f"{self.name}错误：{e}")
        pass

    def stop(self):
        if self.handle is not None:
            self.handle.stop()
            self.handle=None
        super().stop()


class Send_thread(MyQThread):
    """
    请求数据线程
    """

    def __init__(self, name=None, modbus=None,
                 ):
        super().__init__(name)

        self.modbus: ModbusRTUMasterNew= global_setting.get_setting("modbus", None)
        # 正常队列和紧急队列 紧急队列的消息立即处理
        self.normal_queue = queue.Queue()
        self.priority_queue = queue.Queue()
        self.lock = threading.Lock()
        self.normal_queue_lock = threading.Lock()
        self.priority_queue_lock = threading.Lock()
        self.normal_queue_empty=False
        self.priority_queue_empty=False
        pass

#!
    def add_message(self, message, urgent=False, origin=""):
        # origin 为源头
        if urgent:
            with self.priority_queue_lock:
                self.priority_queue.put({'origin': origin, 'message': message})
        else:
            with self.normal_queue_lock:
                self.normal_queue.put(message)


    def stop(self):
        if self.modbus is not None:
            self.modbus.close()
        super().stop()

    def set_modbus(self, modbus):
        self.modbus = modbus

    def run(self):
        logger.warning(f"{self.name} thread has been started！")
        self._running=True

        global lock, total_messages_processed, store_Q, store_Q_lock
        global MESSAGE_BATCH_SIZE
        while self._running:
            self.mutex.lock()
            if self._paused:
                self.condition.wait(self.mutex)  # 等待条件变量
            self.mutex.unlock()
            self.priority_queue_empty = False
            self.normal_queue_empty=False
            send_message =None
            try:
                # logger.info(self.send_messages)

                # 优先检查紧急队列
                try:
                    with self.priority_queue_lock:
                        message = self.priority_queue.get_nowait()
                    send_message = message['message']

                    logger.debug(f"{self.name}接收到查询报文。正在发送查询报文：{send_message}")
                    response, response_hex, send_state, return_data= self.modbus.send_command(
                        slave_id=send_message['slave_id'],
                        function_code=send_message['function_code'],
                        data_hex_list=send_message['data'],

                        is_parse_response=False
                    )
                    # 响应报文是正确的，即发送状态时正确的 进行解析响应报文

                    if send_state:
                        return_data, parser_message = self.modbus.parse_response(response=response,
                                                                                 response_hex=response.hex(),
                                                                                 send_state=True,
                                                                                 slave_id=
                                                                                 send_message['slave_id'],
                                                                                 function_code=
                                                                                 send_message['function_code'], )

                        # 把返回数据返回给源头
                        message_struct = ObjectQueueItem(to=message['origin'],
                                                         data=parser_message,
                                                         origin='main_monitor_data')

                        global_setting.get_setting("send_message_queue").put(message_struct)
                        logger.debug(f"main_monitor_data将响应报文的解析数据返回源头：{message_struct}")
                        pass
                except queue.Empty:
                    self.priority_queue_empty=True
                    pass
                send_message=None
                # 处理普通消息
                try:
                    #!
                    with self.normal_queue_lock:
                        send_message = self.normal_queue.get(timeout=0.1)

                    response, response_hex, send_state,return_data = self.modbus.send_command(
                        slave_id=send_message['slave_id'],
                        function_code=send_message['function_code'],
                        data_hex_list=send_message['data'],
                        is_parse_response=False
                    )
                    # 响应报文是正确的，即发送状态时正确的 进行解析响应报文
                    if send_state:
                        return_data, parser_message = self.modbus.parse_response(response=response,
                                                                                 response_hex=response.hex(),
                                                                                 send_state=True,
                                                                                 slave_id=
                                                                                 send_message['slave_id'],
                                                                                 function_code=
                                                                                 send_message['function_code'], )

                        return_data['time']= datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        # 加锁
                        with store_Q_lock:
                            # 放入队列给存储线程进行存储
                            store_Q.put(return_data)  # 修改全局变量
                        # logger.info(f"{total_messages_processed}|{return_data}")
                        pass

                except queue.Empty:
                    self.normal_queue_empty=True
                    break
            except Exception as e:
                logger.error(e)
            finally:
                if self.normal_queue_empty:
                    continue
                if send_message is not None:
                    logger.info(f"响应报文{total_messages_processed}/{MESSAGE_BATCH_SIZE}响应结束{'-' * 100}")
                    with lock:
                        if total_messages_processed % MESSAGE_BATCH_SIZE == 0:
                            barrier: threading.Barrier = global_setting.get_setting("barrier")
                            if barrier is not None:
                                logger.debug(f"barrier_鼠笼内部传感器 run one batch done ! ")
                                barrier.wait()
                            total_messages_processed = 1
                            MESSAGE_BATCH_SIZE = 0
                            batch_complete_event.set()  # 通知主线程当前批次完成
                            batch_complete_event.clear()  # 重置事件
                        else:
                            total_messages_processed += 1
                else:
                    #如果遇到未知错误，则跳过这条报文
                    logger.error(f"响应报文{total_messages_processed}/{MESSAGE_BATCH_SIZE}响应遇到未知错误，直接跳过这条报文并结束{'-' * 100}")
                    with lock:

                        if MESSAGE_BATCH_SIZE == 0 or total_messages_processed % MESSAGE_BATCH_SIZE == 0:
                            barrier: threading.Barrier = global_setting.get_setting("barrier")
                            if barrier is not None:
                                logger.debug(f"barrier_鼠笼内部传感器 run one batch done ! ")
                                barrier.wait()
                            total_messages_processed = 1
                            MESSAGE_BATCH_SIZE = 0
                            batch_complete_event.set()  # 通知主线程当前批次完成
                            batch_complete_event.clear()  # 重置事件
                        else:
                            total_messages_processed += 1

            time.sleep(float(global_setting.get_setting('monitor_data')['SEND']['delay']))






class Add_message_thread(MyQThread):
    def __init__(self,name,send_thread, port):
        super().__init__(name=name)
        self.send_thread = send_thread
        self.port=port
        self.experiment_setting:Experiment_setting_entity = global_setting.get_setting("experiment_setting",None)
        pass
    def run(self):
        logger.warning(f"{self.name} thread has been started！")
        self._running=True
        # 发送消息
        global MESSAGE_BATCH_SIZE
        self.experiment_setting = global_setting.get_setting("experiment_setting", None)
        # 等待气路启动
        wait_UFC_UGC_ZOS_start_event.wait()
        while self._running:
            self.mutex.lock()
            if self._paused:
                self.condition.wait(self.mutex)  # 等待条件变量
            self.mutex.unlock()

            send_messages = []
            # # 公共传感器数据的send_messages  现在只发传感器数值查询报文DEBUGGER
            # for data_type in Modbus_Slave_Type.Not_Each_Mouse_Cage_Message_Senior_Data.value:
            #     """debugger专用 需要哪个模块的数据监控就放进去"""
            #     if data_type in [
            #         Modbus_Slave_Send_Messages_Senior_Data.UFC,
            #         Modbus_Slave_Send_Messages_Senior_Data.UGC,
            #         Modbus_Slave_Send_Messages_Senior_Data.ZOS
            #     ]:
            #         # 所有消息
            #         for message_struct in data_type.value['send_messages']:
            #             message_temp = message_struct.message
            #             message_temp['port'] =  self.port
            #             self.send_thread.add_message(message=message_temp, urgent=False)
            #             send_messages.append(message_temp)
            #             MESSAGE_BATCH_SIZE += 1
            # 每个笼子里的传感器的send_messages
            for data_type in Modbus_Slave_Type.Each_Mouse_Cage_Message_Senior_Data.value:
                """debugger专用 需要哪个模块的数据监控就放进去"""
                if data_type in [
                                Modbus_Slave_Send_Messages_Senior_Data.ENM,
                                  Modbus_Slave_Send_Messages_Senior_Data.EM,
                                  Modbus_Slave_Send_Messages_Senior_Data.DWM,
                                  Modbus_Slave_Send_Messages_Senior_Data.WM
                ]:
                    if self.experiment_setting  is not None:
                        for mouse_cage in range(1,len(self.experiment_setting.groups)+1):
                            # 所有消息

                            for message_struct in data_type.value['send_messages']:
                                message_temp = copy.deepcopy(message_struct.message)
                                message_temp['port'] =  self.port

                                message_temp['slave_id'] =copy.copy(format(int(message_temp['slave_id'], 16)+16*mouse_cage, '02X'))
                                self.send_thread.add_message(message=message_temp, urgent=False)
                                send_messages.append(message_temp)
                                MESSAGE_BATCH_SIZE += 1
                            """测试专用 只拿一个笼子鼠笼1里的数据 DEBUGGER"""
                            break
                    else:
                        logger.error(f"响应报文的打包获取Add_message_thread遇到self.experiment_setting is None 错误")
                pass
            #     # 等待从线程处理完当前批次
            logger.info(f"数据请求报文：一共{len(send_messages)}条报文！")
            # print(f"send_messages:{send_messages}")
            batch_complete_event.wait()

            logger.info(f"从线程已处理完上批消息，主线程继续发送下一批\n")

def copy_experiment_setting_file():
    #将实验配置存储到该实验的文件夹中去
    # 将实验设置存入全局变量
    experiment_setting_file=global_setting.get_setting("experiment_setting_file", None)
    if experiment_setting_file is not None and  os.path.exists(experiment_setting_file):
        # 获取文件所在的文件夹路径
        folder_path = os.path.dirname(experiment_setting_file)
        # 获取文件名称
        file_name = os.path.basename(experiment_setting_file)
        # 不带扩展名的文件名称
        file_name_without_extension = os.path.splitext(file_name)[0]
        #获取文件的扩展名
        file_name_extension = os.path.splitext(file_name)[1]
        # 定义文件夹路径
        folder_path_copy = os.getcwd() + global_setting.get_setting('monitor_data')['STORAGE']['fold_path'] + os.path.join(
            global_setting.get_setting('monitor_data')['STORAGE']['sub_fold_path'],f"{file_name_without_extension}_{time_util.get_format_file_from_time(global_setting.get_setting('start_experiment_time',time.time()))}","experiment_setting")

        # 创建文件夹（如果不存在）
        os.makedirs(folder_path_copy, exist_ok=True)

        source_file = experiment_setting_file
        destination_file=os.path.join(folder_path_copy,f"experiment_setting{file_name_extension}")
        # 复制文件并保留元数据
        shutil.copy2(source_file, destination_file)
        pass
    pass
# 线程
ufc_ugc_zos:UFC_UGC_ZOS_index=None
ufc_ugc_zos_thread =None
# 存储线程
store_thread:Store_Thread = None
# 发送报文线程
send_thread :Send_thread= None
add_message_thread:Add_message_thread = None
#一轮模块发送报文结束
def barrier_action():
    end_time = time.time()
    start_time = global_setting.get_setting("start_time_messages_sent_epoch_for_running", time.time())

    logger.warning(f"{'-'*100}|结束时间：{time_util.get_format_from_time(end_time)}|开始时间：{time_util.get_format_from_time(start_time)}|用时：{time_util.format_timedelta(a= datetime.fromtimestamp(end_time),b= datetime.fromtimestamp(start_time),signed=True,zero_pad=True)}|一轮传感器发送报文结束|期间一共发送{ global_setting.get_setting('messages_sent_epoch_for_running', 0)}条报文。")

    handle = Monitor_Datas_Handle()  # # 创建数据库操作器
    results, columns=handle.query_data_in_line_with_epoch_data(start_time,end_time)
    handle.stop()
    logger.critical(f"{results}")
    mouse_cage_number,_,_= number_util.extract_numbers_with_patterns(string_list=columns+[f"{results.get('UFC_monitor_data__mouse_cage')}"])
    mouse_cage_number=int(mouse_cage_number) if mouse_cage_number else 1
    store_Datas =[]
    # store_Datas.append({'desc':'序号','value':None})
    store_Datas.append({'desc':'鼠笼号','value':mouse_cage_number})
    store_Datas.append({'desc': '氧浓度0点校准值',
                        'value': results.get('ZeroCalibration_data__oxygen_calibration_zero_value') if results.get(
                            'ZeroCalibration_data__oxygen_calibration_zero_value') else None})
    store_Datas.append({'desc': '氧浓传感器span数值',
                        'value': results.get('SpanCalibration_data__oxygen_calibration_span_value') if results.get(
                            'SpanCalibration_data__oxygen_calibration_span_value') else None})
    store_Datas.append({'desc': 'ufc_流量计测量值(sccm)', 'value': results.get('UFC_monitor_data__flow_num')})
    store_Datas.append({'desc': 'ufc_参考气路流量计测量值(sccm)', 'value': results.get('UFC_monitor_data__reference_flow_num')})
    store_Datas.append({'desc': 'ugc_流量计1', 'value': results.get('UGC_monitor_data__flow_num_1')})
    store_Datas.append({'desc': 'CO2(%)', 'value': results.get('UGC_monitor_data__CO2_num')})
    store_Datas.append({'desc': '氧气传感器测量值(%)', 'value': results.get('ZOS_monitor_data__oxygen_num')})
    store_Datas.append(
        {'desc': '温度测量值(°C)', 'value': results.get(f'ENM_monitor_data_cage_{mouse_cage_number}__temperature_num')})
    store_Datas.append(
        {'desc': '湿度测量值(%RH)', 'value': results.get(f'ENM_monitor_data_cage_{mouse_cage_number}__humidity_num')})
    store_Datas.append(
        {'desc': '噪声测量值(dB)', 'value': results.get(f'ENM_monitor_data_cage_{mouse_cage_number}__noise_num')})
    store_Datas.append({'desc': '大气压测量值(KPa)',
                        'value': results.get(f'ENM_monitor_data_cage_{mouse_cage_number}__barometer_num')})
    store_Datas.append({'desc': '当前计量周期内跑轮圈数测量值',
                        'value': results.get(f'ENM_monitor_data_cage_{mouse_cage_number}__running_wheel_num')})
    store_Datas.append(
        {'desc': '饮水重量测量值(g)', 'value': results.get(f'DWM_monitor_data_cage_{mouse_cage_number}__weight_num') })
    store_Datas.append(
        {'desc': '食物重量测量值(g)', 'value':results.get(f'EM_monitor_data_cage_{mouse_cage_number}__weight_num')  })
    store_Datas.append(
        {'desc': '称重重量测量值(g)', 'value': results.get(f'WM_monitor_data_cage_{mouse_cage_number}__weight_num')})
    store_Datas.append({'desc':'轮次开始时间','value':datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]})
    store_Datas.append({'desc':'轮次结束时间','value':datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]})
    # store_Datas.append({'desc':'获取时间','value':datetime.now().fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')})
    # 装载数据
    # 存储值----------------------------------------------------
    # 去数据库里查询 所有的在这个时间段的数据
    return_data_struct = {}
    return_data_struct['module_name'] = 'Epoch'
    return_data_struct['table_name'] = next(iter(Others_Tables.Epoch_Data.value.keys()))
    return_data_struct['mouse_cage_number'] = 0
    return_data_struct['data'] = store_Datas
    return_data_struct['slave_id'] = 0
    return_data_struct['time']=datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    return_data_struct['function_code'] = 0
    #  取出全局存储queue
    lock = global_setting.get_setting("store_Q_lock", threading.Lock())
    storeQ = global_setting.get_setting("store_Q", queue.Queue())
    # 加锁
    with lock:
        # 放入队列给存储线程进行存储 这个存储线程时main_monitor_data的存储线程
        storeQ.put(return_data_struct)  # 修改全局变量
    global_setting.set_setting("start_time_messages_sent_epoch_for_running", end_time+0.1)
    global_setting.set_setting("messages_sent_epoch_for_running",
                               0)
def main(q,send_message_q):

    # logger.remove(0)
    # 加载日志配置
    # logger.add(
    #     "./log/monitor_data/monitor_{time:YYYY-MM-DD}.log",
    #     rotation="00:00",
    #     retention="30 days",
    #     enqueue=True,
    #     format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}",
    #
    # )
    logger.info(f"{'-' * 30}monitor_data_start{'-' * 30}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")
    app = QCoreApplication(sys.argv)
    # 设置全局变量
    global_load.load_global_setting_without_Qt()
    global_setting.set_setting("queue", q)
    global_setting.set_setting("send_message_queue", send_message_q)
    #设置线程屏障，等待4个线程
    # barrier专门用于多个线程需要在某个点同步等待的场景。每个线程执行完自己的工作后调用
    # barrier.wait()，当所有线程都到达这个同步点时，它们会同时继续执行下一轮循环。
    barrier = threading.Barrier(4,action=barrier_action)
    global_setting.set_setting("barrier", barrier)
    #每轮运行发送报文数量 总的 在气路启动后和一轮结束后会重新赋值0
    global_setting.set_setting("messages_sent_epoch_for_running",0)
    #每轮运行开始的时间 在气路启动后和一轮结束后会重新赋值
    global_setting.set_setting("start_time_messages_sent_epoch_for_running",time.time())
    global read_queue_data_thread

    read_queue_data_thread.queue = send_message_q

    read_queue_data_thread.start()
    # return store_thread,send_thread,read_queue_data_thread,add_message_thread,ufc_ugc_zos,ufc_ugc_zos_thread
    # 系统退出
    return app.exec()
def start():
    logger.info(f"{'-' * 30}monitor_data_run{'-' * 30}")
    global MESSAGE_BATCH_SIZE, total_messages_processed
    MESSAGE_BATCH_SIZE = 0
    total_messages_processed = 1
    # UFC_UGC_ZOS
    global ufc_ugc_zos_thread, ufc_ugc_zos,store_thread,send_thread,add_message_thread
    ufc_ugc_zos_thread = None
    ufc_ugc_zos = None
    try:
        # ufc_ugc_zos = UFC_UGC_ZOS_index()
        # ufc_ugc_zos.auto_btn_handle()
        ufc_ugc_zos_thread= UFC_UGC_ZOS_index()
        ufc_ugc_zos_thread.start()

    except Exception as ex:
        print(ex)
        logger.error(f"<UNK>{ex}")

    # 存储线程
    store_thread = Store_Thread(name="monitor_data_store_message")
    store_thread.start()

    # 发送报文线程
    send_thread = Send_thread(name="monitor_data_send_message")
    send_thread.start()
    read_queue_data_thread.send_thread = send_thread

    global port_use
    add_message_thread = Add_message_thread("monitor_data_add_message", send_thread, port_use)
    add_message_thread.start()

    # 将实验配置存储到该实验的文件夹中去
    copy_experiment_setting_file()
def restart(q,send_message_q):
    main(q,send_message_q)
    start()
def pause():
    logger.info(f"{'-' * 30}monitor_data_pause{'-' * 30}")
    pass

def stop():
    logger.info(f"{'-' * 30}monitor_data_stop{'-' * 30}")
    global ufc_ugc_zos_thread, ufc_ugc_zos,store_thread,send_thread,add_message_thread
    try:
        logger.error("stop_ufc_ugc_zos")

        if ufc_ugc_zos_thread is not None:
            ufc_ugc_zos_thread.stop()

    except Exception as e:
        logger.error(f"关闭实验监测ufc_ugc_zos错误，原因：{e}")
    pass
    try:
        logger.error("stop_store_thread")
        if store_thread is not None and store_thread.isRunning():
            store_thread.stop()
    except Exception as e:
        logger.error(f"关闭实验监测store_thread错误，原因：{e}")
    try:
        logger.error("stop_add_message_thread")
        if add_message_thread is not None and add_message_thread.isRunning():
            add_message_thread.stop()
    except Exception as e:
        logger.error(f"关闭实验监测add_message_thread错误，原因：{e}")

    try:
        logger.error("stop_send_thread")
        if send_thread is not None and send_thread.isRunning():
            send_thread.stop()
    except Exception as e:
        logger.error(f"关闭实验监测send_thread错误，原因：{e}")
if __name__ == "__main__":
    q = multiprocessing.Queue()
    send_message_q = multiprocessing.Queue()
    main("COM5",q,send_message_q)
