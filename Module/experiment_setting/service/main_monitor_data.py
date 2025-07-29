import multiprocessing
import os
import queue
import threading
import time

from PyQt6.QtCore import pyqtSignal
from loguru import logger


from public.config_class.global_setting import global_setting

from public.config_class.ini_parser import ini_parser
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.MyQThread import MyQThread
from public.function.Modbus.Modbus import ModbusRTUMaster
from public.function.Modbus.Modbus_Type import Modbus_Slave_Type

# 全局变量
# 实现主线程发一整轮消息，当从线程响应完全部的消息后，主线程在发一整轮消息
MESSAGE_BATCH_SIZE = 0
total_messages_processed = 1
lock = threading.Lock()
batch_complete_event = threading.Event()

# 存储数据锁
store_Q_lock = threading.Lock()
store_Q = queue.Queue()


class read_queue_data_Thread(MyQThread):
    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.send_thread: Send_thread = None
        pass

    def dosomething(self):
        if not self.queue.empty():
            message = self.queue.get()
            # message 结构{'to'发往哪个线程，'data'数据,'from'从哪发的}
            if message is not None and isinstance(message, dict) and len(message) > 0 and 'to' in message and message[
                'to'] == 'main_monitor_data':
                logger.error(f"{self.name}_get_message:{message}")
                if 'data' in message:
                    if self.send_thread is not None and self.send_thread.isRunning():
                        # 发送优先级高的报文
                        self.send_thread.add_message(message=message['data'], urgent=True, origin=message['from'])
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
            if self.handle is not None:
                self.handle.stop()
            self.handle = Monitor_Datas_Handle()  # # 创建数据库
            self.handle.insert_data(data)
        except Exception as e:
            logger.error(f"{self.name}错误：{e}")
        pass

    def stop(self):
        if self.handle is not None:
            self.handle.stop()
        super().stop()


class Send_thread(MyQThread):
    """
    请求数据线程
    """

    def __init__(self, name=None, modbus=None,
                 ):
        super().__init__(name)

        self.modbus: ModbusRTUMaster = modbus
        # 正常队列和紧急队列 紧急队列的消息立即处理
        self.normal_queue = queue.Queue()
        self.priority_queue = queue.Queue()
        self.lock = threading.Lock()

        pass

    def add_message(self, message, urgent=False, origin=""):
        # origin 为源头
        if urgent:
            self.priority_queue.put({'origin': origin, 'message': message})
        else:
            self.normal_queue.put(message)

    def init_modBus(self, port, origin=None):
        try:

            self.modbus = ModbusRTUMaster(port=port, timeout=float(
                global_setting.get_setting('monitor_data')['Serial']['timeout']),
                                          origin=origin
                                          )
        except Exception as e:
            logger.error(f"{self.name},实例化modbus错误：{e}")
            pass
        pass
    def stop(self):
        if self.modbus is not None:
            self.modbus.close()
        super().stop()

    def set_modbus(self, modbus):
        self.modbus = modbus

    def run(self):
        logger.warning(f"{self.name} thread has been started！")
        global lock, total_messages_processed, store_Q, store_Q_lock
        global MESSAGE_BATCH_SIZE
        while self._running:
            self.mutex.lock()
            if self._paused:
                self.condition.wait(self.mutex)  # 等待条件变量
            self.mutex.unlock()
            send_message =None
            try:
                # logger.info(self.send_messages)

                # 优先检查紧急队列
                try:
                    message = self.priority_queue.get_nowait()
                    send_message = message['message']
                    self.init_modBus(port=send_message['port'], origin=message['origin'])
                    logger.debug(f"{self.name}接收到查询报文。正在发送查询报文：{send_message}")
                    response, response_hex, send_state = self.modbus.send_command(
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
                        message_struct = {'to': message['origin'], 'data': parser_message, 'from': 'main_monitor_data'}
                        global_setting.get_setting("send_message_queue").put(message_struct)
                        logger.debug(f"main_monitor_data将响应报文的解析数据返回源头：{message_struct}")
                        pass
                except queue.Empty:
                    pass
                send_message=None
                # 处理普通消息
                try:

                    send_message = self.normal_queue.get(timeout=0.1)
                    self.init_modBus(port=send_message['port'])
                    response, response_hex, send_state = self.modbus.send_command(
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
                        # 加锁
                        with store_Q_lock:
                            # 放入队列给存储线程进行存储
                            store_Q.put(return_data)  # 修改全局变量
                        # logger.info(f"{total_messages_processed}|{return_data}")
                        pass

                except queue.Empty:
                    break
            except Exception as e:
                logger.error(e)
            finally:
                if send_message is not None:
                    logger.info(f"响应报文{total_messages_processed}/{MESSAGE_BATCH_SIZE}响应结束{'-' * 100}")
                    with lock:
                        if total_messages_processed % MESSAGE_BATCH_SIZE == 0:

                            total_messages_processed = 1
                            MESSAGE_BATCH_SIZE = 0
                            batch_complete_event.set()  # 通知主线程当前批次完成
                        else:
                            total_messages_processed += 1
            time.sleep(float(global_setting.get_setting('monitor_data')['SEND']['delay']))






class Add_message_thread(MyQThread):
    def __init__(self,name,send_thread, port):
        super().__init__(name=name)
        self.send_thread = send_thread
        self.port=port
        pass
    def run(self):
        logger.warning(f"{self.name} thread has been started！")
        # 发送消息
        global MESSAGE_BATCH_SIZE

        while self._running:
            self.mutex.lock()
            if self._paused:
                self.condition.wait(self.mutex)  # 等待条件变量
            self.mutex.unlock()

            send_messages = []
            # 公共传感器数据的send_messages  现在只发传感器数值查询报文DEBUGGER
            for data_type in Modbus_Slave_Type.Not_Each_Mouse_Cage_Message_Senior_Data.value:
                # 所有消息
                for message_struct in data_type.value['send_messages']:
                    message_temp = message_struct.message
                    message_temp['port'] =  self.port
                    self.send_thread.add_message(message=message_temp, urgent=False)
                    send_messages.append(message_temp)
                    MESSAGE_BATCH_SIZE += 1
            # 每个笼子里的传感器的send_messages
            for data_type in Modbus_Slave_Type.Each_Mouse_Cage_Message_Senior_Data.value:
                for mouse_cage in data_type.value['send_messages']:
                    # 所有消息
                    for message_struct in mouse_cage:
                        message_temp = message_struct.message
                        message_temp['port'] =  self.port
                        self.send_thread.add_message(message=message_temp, urgent=False)
                        send_messages.append(message_temp)
                        MESSAGE_BATCH_SIZE += 1
                    # 测试专用 只拿一个笼子鼠笼1里的数据 DEBUGGER
                    # break
                pass
                # 等待从线程处理完当前批次
            logger.info(f"数据请求报文：一共{len(send_messages)}条报文！")
            # print(f"send_messages:{send_messages}")
            batch_complete_event.wait()
            batch_complete_event.clear()  # 重置事件
            logger.info(f"从线程已处理完上批消息，主线程继续发送下一批\n")

def main(port,q,send_message_q):
    # logger.remove(0)
    logger.add(
        "./log/monitor_data/monitor_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}"
    )
    logger.info(f"{'-' * 30}monitor_data_start{'-' * 30}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")

    # 读取共享信息线程
    # q = global_setting.get_setting("queue")
    # send_message_q = global_setting.get_setting("send_message_queue")
    global read_queue_data_thread
    read_queue_data_thread.queue = send_message_q



    # 存储线程
    store_thread = Store_Thread(name="monitor_data_store_message")
    store_thread.start()

    # 发送报文线程
    send_thread = Send_thread(name="monitor_data_send_message")
    send_thread.start()

    read_queue_data_thread.send_thread = send_thread
    read_queue_data_thread.start()

    add_message_thread=Add_message_thread("monitor_data_add_message",send_thread, port)
    add_message_thread.start()

    return store_thread,send_thread,read_queue_data_thread,add_message_thread



if __name__ == "__main__":
    q = multiprocessing.Queue()
    send_message_q = multiprocessing.Queue()
    main("COM5",q,send_message_q)
