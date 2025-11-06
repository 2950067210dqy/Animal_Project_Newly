import os
import threading
import time
import typing
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from loguru import logger


from Module.UFC_UGC_ZOS_Test.config_class.global_setting import global_setting
from Module.UFC_UGC_ZOS_Test.config_class.ini_parser import ini_parser
from Module.UFC_UGC_ZOS_Test.entity.MyQThread import MyQThread
from Module.UFC_UGC_ZOS_Test.function.Timer.ProcederTimer import PeriodicTimer
from Module.UFC_UGC_ZOS_Test.function.gas_calibration.Gas_Carlibration import Zero_Carlibration, Range_Carlibration
from Module.UFC_UGC_ZOS_Test.function.gas_path_system.Gas_path_system import UFC_gas_path_system, UGC_gas_path_system, \
    ZOS_gas_path_system
from Module.UFC_UGC_ZOS_Test.function.gas_state_check.Gas_State_Check import UFC_Gas_State_Check
from Module.UFC_UGC_ZOS_Test.function.modbus.New_Mod_Bus import ModbusRTUMasterNew
from Module.UFC_UGC_ZOS_Test.function.promise.AsyPromise import AsyPromise
from Module.UFC_UGC_ZOS_Test.ui.UFC_UGC_ZOS_window import Ui_UFC_UGC_ZOS_window






from Module.UFC_UGC_ZOS_Test.function.modbus.COM_Scan import scan_serial_ports_with_id
from Module.UFC_UGC_ZOS_Test.util.time_util import time_util
from public.entity.queue.ObjectQueue import ObjectQueue
from public.entity.queue.ObjectQueueItem import ObjectQueueItem

from theme.ThemeQt6 import ThemedWindow
from PyQt6 import QtGui, QtCore
from PyQt6.QtCore import QRect, pyqtSignal, pyqtBoundSignal
from PyQt6.QtWidgets import QComboBox, QListWidget, QPushButton, QLabel
# 过滤日志

report_logger = logger.bind(category="report_logger")
read_queue_data_Thread_Lock = threading.Lock()
auto_wait_event = threading.Event()
class SimpleLRU:
    """去除report.log的重复项"""
    def __init__(self, cap=1000):
        self.cap = cap
        self.od = OrderedDict()

    def add(self, key):
        if key in self.od:
            self.od.move_to_end(key)
            return False
        self.od[key] = True
        if len(self.od) > self.cap:
            self.od.popitem(last=False)
        return True
"""去除report.log的重复项"""
_lru = SimpleLRU(cap=500)
def log_once_lru(message):
    if not _lru.add(message):
        return
    # report_logger.info(message)
    logger.info(message)
class auto_run_Thread(MyQThread,QtCore.QObject):
    #開始回調信號
    start_finish_signal:pyqtBoundSignal=pyqtSignal()
    #運行回調信號
    run_finish_signal:pyqtBoundSignal = pyqtSignal()
    #標定回調信號
    carlibration_finish_signal:pyqtBoundSignal = pyqtSignal()
    #狀態檢測回調信號
    check_finish_signal:pyqtBoundSignal = pyqtSignal()
    def __init__(self,name,start_signal,run_signal,carlibration_signal,gas_state_check_signal,auto_finish_signal):
        super().__init__(name=name)
        # 開始信號
        self.start_signal =start_signal
        # 運行信號
        self.run_signal = run_signal
        # 标定信號
        self.carlibration_signal = carlibration_signal
        # 量程标定信號

        # 状态检测信號
        self.gas_state_check_signal =gas_state_check_signal

        #自動運行結束信號
        self.auto_finish_signal = auto_finish_signal

        self.before_start_flag =True
        self.start_finish_flag =False
        self.run_finish_flag =False
        self.carlibration_finish_flag =False
        self.check_finish_flag =False

        self.start_finish_signal.connect(self.start_finish)
        self.run_finish_signal.connect(self.run_finish)
        self.carlibration_finish_signal.connect(self.carlibration_finish)
        self.check_finish_signal.connect(self.check_finish)

    def start_finish(self):
        self.start_finish_flag=True
        pass
    def run_finish(self):
        self.run_finish_flag=True
    def carlibration_finish(self):
        self.carlibration_finish_flag=True
    def check_finish(self):
        self.check_finish_flag=True

    def dosomething(self):
        if self.before_start_flag:
            self.start_signal.emit()
            self.before_start_flag=False
        if self.start_finish_flag:
            self.start_finish_flag = False
            global auto_wait_event
            auto_wait_event.wait()
            self.run_signal.emit()

        if self.run_finish_flag:
            self.carlibration_signal.emit()
            self.run_finish_flag=False
        if self.carlibration_finish_flag:
            self.gas_state_check_signal.emit()
            self.carlibration_finish_flag=False
        if self.check_finish_flag:
            self.auto_finish_signal.emit()
            self.check_finish_flag=False
            self.stop()

        pass
class read_queue_data_Thread(MyQThread):
    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.update_status_main_signal_gui_update: pyqtSignal(str) = None
        pass

    def dosomething(self):
        if not self.queue.empty():
            try:
                message: ObjectQueueItem = self.queue.get()
            except Exception as e:
                logger.error(f"{self.name}发生错误{e}")
                return
            # message 结构{'to'发往哪个线程，'data'数据，‘from'从哪来}

            if message is not None and isinstance(message, ObjectQueueItem) and message.to== 'UFC_UGC_ZOS_index':
                # logger.error(f"{self.name}_get_message:{message}")
                match message.title:
                    case '':
                        if self.update_status_main_signal_gui_update is not None:
                            with read_queue_data_Thread_Lock:
                                self.update_status_main_signal_gui_update.emit(message.data)
                            pass
                    case _:
                        pass


            else:
                # 把消息放回去
                self.queue.put(message)

        pass


read_queue_data_thread = read_queue_data_Thread(name="UFC_UGC_ZOS_index_read_queue_data_thread")

class Monitor_start_state_Thread(MyQThread):
    def __init__(self, name,UFC_gas_path_system_obj=None,UGC_gas_path_system_obj=None,ZOS_gas_path_system_obj=None,update_start_state_signal=None):
        # UFC气路系统
        self.UFC_gas_path_system_obj: UFC_gas_path_system = UFC_gas_path_system_obj
        # UGC气路系统
        self.UGC_gas_path_system_obj: UGC_gas_path_system = UGC_gas_path_system_obj
        # ZOS气路系统
        self.ZOS_gas_path_system_obj: ZOS_gas_path_system = ZOS_gas_path_system_obj
        self.update_start_state_signal:pyqtSignal = update_start_state_signal

        super().__init__(name)
    def dosomething(self):
        # print(self.UFC_gas_path_system_obj.ufc_start_time_state,self.ZOS_gas_path_system_obj.zos_start_status)
        if self.UFC_gas_path_system_obj.ufc_start_time_state and self.ZOS_gas_path_system_obj.zos_start_status:
            self.update_start_state_signal.emit()
        time.sleep(1)

        pass


class UFC_UGC_ZOS_index(ThemedWindow):
    update_status_main_signal_gui_update = pyqtSignal(str)

    #更新开始状态的信号
    update_start_state_signal:pyqtBoundSignal=pyqtSignal()

    # 開始信號
    start_signal:pyqtBoundSignal =pyqtSignal()
    #運行信號
    run_signal:pyqtBoundSignal =pyqtSignal()
    # 标定信號
    carlibration_signal:pyqtBoundSignal =pyqtSignal()
    #自動運行結束信號
    auto_finish_signal:pyqtBoundSignal =pyqtSignal()

    # 状态检测信號
    gas_state_check_signal =pyqtSignal()
    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        # 加载qss样式表
        logger.warning("UFC_UGC_ZOS_index——show")

        # 实例化自定义ui
        self._init_customize_ui()
        super().showEvent(a0)
    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.warning("UFC_UGC_ZOS_index--hide")

        super().hideEvent(a0)
    def closeEvent(self, event):
        logger.warning("UFC_UGC_ZOS_index--close")
        self.disabled_auto_btn_handle()
        super().closeEvent(event)
    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()


        # 发送的数据结构
        self.send_message = {
            'port': '',
            'data': '',
            'slave_id': 0,
            'function_code': 0,
            'timeout': 0
        }
        # 下拉框数据列表
        self.ports = []
        #状态显示label
        self.state_label:QLabel = None
        # 重新获取端口按钮
        self.refresh_port_btn: QPushButton=None

        #自动按钮
        self.auto_btn:QPushButton=None
        #解除自动按钮
        self.disabled_auto_btn: QPushButton=None
        #开始按钮
        self.start_btn: QPushButton=None
        #运行按钮
        self.run_btn :  QPushButton=None
        #停止按钮
        self. stop_btn: QPushButton=None
        #打开日志文件夹按钮
        self.open_log_btn: QPushButton=None

        #UFC气路系统
        self.UFC_gas_path_system_obj:UFC_gas_path_system =None
        #UGC气路系统
        self.UGC_gas_path_system_obj:UGC_gas_path_system =None
        #ZOS气路系统
        self.ZOS_gas_path_system_obj:ZOS_gas_path_system =None
        #零点标定
        self.Zero_carlibration_obj:Zero_Carlibration =None
        #量程标定
        self.Range_carlibration_obj:Range_Carlibration =None
        #UFC状态检测
        self.UFC_gas_state_check_obj:UFC_Gas_State_Check=None

        #ZOS预热定时器
        self.zos_start_timer :PeriodicTimer=None
        self.ufc_start_timer :PeriodicTimer=None
        self.calibration_start_timer :PeriodicTimer=None
        self.gas_state_check_timer:PeriodicTimer=None
        #监测开始状态的线程
        self.monitor_start_state_Thread:MyQThread = None
        #自動運行按鈕綫程
        self.auto_run_thread:auto_run_Thread=None
        # 实例化ui
        self._init_ui(parent, geometry, title)
        # 获得相关数据
        self._init_data()
        # 实例化自定义ui
        self._init_customize_ui()
        # 实例化功能
        self._init_function()
        # 加载qss样式表
        self._init_style_sheet()
        pass


    # 获得相关数据
    def _init_data(self):
        # 获得端口下拉框数据
        self.ports = scan_serial_ports_with_id()


        #保存状态栏信息的日志
        # logger.remove()
        logger.add(
            "./"+"Module/UFC_UGC_ZOS_Test/"+"log/report_data/report_{time:YYYY-MM-DD}.log",
            rotation="00:00",  # 日志文件转存
            retention="30 days",  # 多长时间之后清理
            enqueue=True,
            format="{time:YYYY.MM.DD HH:mm:ss} {message}",
            filter=lambda record: record["extra"].get("category") == "report_logger"
        )
        #读取config ini文件
        # 加载配置 如果ini文件在最外层要去除module+
        config_file_path =os.getcwd() + "./"+"Module/UFC_UGC_ZOS_Test/"+"config/UFC_UGC_ZOS_Test.ini"
        # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
        configer = ini_parser(config_file_path).read()
        if (len(configer) != 0):
            logger.info("UFC_UGC_ZOS_config配置文件读取成功。")
        else:
            logger.error("UFC_UGC_ZOS_config配置文件读取失败。")
        global_setting.set_setting("UFC_UGC_ZOS_config", configer)
        q = ObjectQueue()  # 创建 Queue 消息传递
        send_message_q = ObjectQueue()  # 发送查询报文的消息传递单独一个通道
        global_setting.set_setting("queue", q)
        global_setting.set_setting("send_message_queue", send_message_q)
        # 串口的线程锁 确保同时只能一个线程访问资源
        serial_lock = threading.Lock()
        global_setting.set_setting("serial_lock", serial_lock)

        pass
    # 实例化ui
    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        # 有父窗口添加父窗口
        if parent != None and geometry != None:
            self.setParent(parent)
            self.setGeometry(geometry)
        else:
            pass

        self.ui = Ui_UFC_UGC_ZOS_window()

        self.ui.setupUi(self)

        self._retranslateUi()

        pass

    # 实例化自定义ui
    def _init_customize_ui(self):
        # 实例化下拉框
        self.init_port_combox()
        self.state_label=self.findChild(QLabel, "state_label")
        self.state_label.setText("未启动")
        self.state_label.setStyleSheet("QLabel { color:red; }")

        # logger.error(self.config)

        pass

    # 实例化端口下拉框
    def init_port_combox(self):
        port_combox: QComboBox = self.findChild(QComboBox, "port_combox")
        if port_combox == None:
            logger.error("实例化端口下拉框失败！")
            return
        port_combox.clear()
        for port_obj in self.ports:
            port_combox.addItem(f"- 设备: {port_obj['device']}" + f" #{port_obj['description']}")
            pass
        if len(self.ports) != 0:
            # 默认下拉项
            self.send_message['port'] = self.ports[0]['device']
            global_setting.set_setting("port", self.send_message['port'])
            modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
            if modbus is None:
                modbus = ModbusRTUMasterNew(self.send_message['port'], baudrate=115200, timeout=float(
                    0.5), )
                global_setting.set_setting("modbus", modbus)
            else:
                modbus.close()
                modbus = ModbusRTUMasterNew(self.send_message['port'], baudrate=115200, timeout=float(
                    0.5), )
                global_setting.set_setting("modbus", modbus)
            self.send_response_text(
                f"{time_util.get_format_from_time(time.time())} | 设备: {self.ports[0]['device']}" + f" #{self.ports[0]['description']}" + "  默认已被选中!")
        port_combox.disconnect()
        port_combox.currentIndexChanged.connect(self.selectionchange)
    #端口下拉框选择事件
    def selectionchange(self, index):
        try:
            self.send_message['port'] = self.ports[index]['device']
            global_setting.set_setting("port", self.send_message['port'])
            modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
            if modbus is None:
                modbus = ModbusRTUMasterNew(self.send_message['port'], baudrate=115200, timeout=float(
                   0.5), )
                global_setting.set_setting("modbus", modbus)
            else:
                modbus.close()
                modbus = ModbusRTUMasterNew(self.send_message['port'], baudrate=115200, timeout=float(
                    0.5), )
                global_setting.set_setting("modbus", modbus)
            self.send_response_text(
                f"{time_util.get_format_from_time(time.time())} | 设备: {self.ports[index]['device']}" + f" #{self.ports[index]['description']}" + "  已被选中!")
        except Exception as e:
            logger.error(e)
        pass
    # 往响应栏添加信息
    def send_response_text(self, text):
        # 往状态栏发消息
        response_text: QListWidget = self.findChild(QListWidget, "responselist")
        if response_text == None:
            logger.error("response_text状态栏未找到！")
            return
        #去重复项日志
        log_once_lru(text)
        response_text.addItem(text)
        self.sort_qlistwidget_by_time(response_text=response_text)
        if self.main_gui is not None:
            self.main_gui.status_bar.update_tip(text)
        # 滑动滚动条到最底下
        scroll_bar = response_text.verticalScrollBar()
        if scroll_bar != None:
            scroll_bar.setValue(scroll_bar.maximum())
        pass
    #响应栏内容根据时间来排序
    def sort_qlistwidget_by_time(self,response_text:QListWidget):
        items = []
        for idx in range(response_text.count()):
            it = response_text.item(idx)
            text = it.text()
            dt = self.parse_time_from_item(text)
            items.append((dt, idx, text))  # idx 为次要键，确保稳定排序

        items.sort(key=lambda x: (x[0], x[1]))

        response_text.clear()
        for _, _, text in items:

            response_text.addItem(text)

    # QListWidget中的item为字符串"2025-09-04 23:21:54:123 - xxxxxx",解析前面的时间
    def parse_time_from_item(self,text):
        # 假设格式: "2025-09-04 23:21:54:123 - xxxxxx"
        # 提取前面的时间部分
        time_part = text.split("|")[0].strip()  # "2025-09-04 23:21:54:123"
        # 解析为 datetime
        try:
            dt = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError as e:
            logger.error(e)
            # 如果没有毫秒，退回简单解析
            dt = datetime.strptime(time_part, "%Y-%m-%d %H:%M:%S")
        return dt
    # 实例化功能
    def _init_function(self):
        # 将更新status信号绑定更新status界面函数
        self.update_status_main_signal_gui_update.connect(self.send_response_text)
        self.update_start_state_signal.connect(self.update_start_state)

        self.start_signal.connect(self.start_btn_handle)
        self.run_signal.connect(self.run_btn_handle)
        self.carlibration_signal.connect(self.calibration_handle)
        self.gas_state_check_signal.connect(self.gas_state_check_handle)
        self.auto_finish_signal.connect(lambda :self.disabled_auto_btn.setEnabled(True))

        #实例化气路
        self.UFC_gas_path_system_obj:UFC_gas_path_system = UFC_gas_path_system()
        self.UGC_gas_path_system_obj:UGC_gas_path_system = UGC_gas_path_system()
        self.ZOS_gas_path_system_obj:ZOS_gas_path_system = ZOS_gas_path_system()
        self.UFC_gas_path_system_obj.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.UGC_gas_path_system_obj.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.ZOS_gas_path_system_obj.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update

        # 实例化标定
        self.Zero_carlibration_obj:Zero_Carlibration = Zero_Carlibration()
        self.Zero_carlibration_obj.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        self.Range_carlibration_obj:Range_Carlibration = Range_Carlibration()
        self.Range_carlibration_obj.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update

        #实例化状态检测
        self.UFC_gas_state_check_obj=UFC_Gas_State_Check()
        self.UFC_gas_state_check_obj.update_status_main_signal_gui_update=self.update_status_main_signal_gui_update
        # 实例化按钮信号槽绑定
        self.init_btn_func()
        # 实例化信号

        global read_queue_data_thread
        read_queue_data_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        read_queue_data_thread.queue = global_setting.get_setting("send_message_queue")
        if read_queue_data_thread is not None and not read_queue_data_thread.isRunning():
            read_queue_data_thread.start()
            pass
        pass

    # 实例化按钮信号槽绑定
    def init_btn_func(self):
        # 重新获取端口按钮
        self.refresh_port_btn: QPushButton = self.findChild(QPushButton, "refresh_port_btn")
        self.refresh_port_btn.clicked.connect(self.refresh_port)
        #开始按钮
        self.start_btn: QPushButton = self.findChild(QPushButton, "start_btn")
        self.start_btn.clicked.connect(self.start_btn_handle)
        #运行按钮
        self.run_btn: QPushButton = self.findChild(QPushButton, "run_btn")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.run_btn_handle)
        #停止按钮
        self.stop_btn: QPushButton = self.findChild(QPushButton, "stop_btn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_btn_handle)

        #自动按钮
        self.auto_btn: QPushButton = self.findChild(QPushButton, "auto_btn")
        self.auto_btn.clicked.connect(self.auto_btn_handle)
        #解除自动按钮
        self.disabled_auto_btn: QPushButton = self.findChild(QPushButton, "disabled_auto_btn")
        self.disabled_auto_btn.clicked.connect(self.disabled_auto_btn_handle)
        self.disabled_auto_btn.setEnabled(False)

        #打开日志文件夹
        self.open_log_btn: QPushButton = self.findChild(QPushButton, "open_log_btn")
        self.open_log_btn.clicked.connect(self.open_log)
        pass

    def open_log(self):
        """打开日志文件夹"""
        # 获取当前工作目录
        current_directory = Path.cwd()
        open_direct = Path.joinpath(current_directory,
                                    "./"+"Module/UFC_UGC_ZOS_Test/"+"log/report_data/")
        open_direct.mkdir(parents=True, exist_ok=True)
        os.startfile(open_direct)  # 替换为你要打开的文件夹路径
    # 重新获取端口
    def refresh_port(self):
        self.ports = []
        self._init_data()
        self.init_port_combox()
    def auto_finish_handle(self):
        pass
    def update_start_state(self):
        self.monitor_start_state_Thread.stop()
        self.close_timers()
        self.stop_btn.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.state_label.setText("已启动")
        self.state_label.setStyleSheet("QLabel { color:blue; }")
        #預熱完之後取消自動運行的阻塞
        global auto_wait_event
        auto_wait_event.set()
        auto_wait_event.clear()
    #启动按钮事件 启动气路
    def start_btn_handle(self):
        self.start_btn.setEnabled(False)
        self.state_label.setText("正在启动...")
        self.state_label.setStyleSheet("QLabel { color:black; }")
        p= AsyPromise(self.ZOS_gas_path_system_obj.start).then(
            AsyPromise(
                self.UFC_gas_path_system_obj.start,
            ).then(
                AsyPromise(self.UGC_gas_path_system_obj.start,).then(
                    AsyPromise(self.set_start_timers)
                ).catch(lambda e:logger.error(f"{e}"))
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))

        #等开始状态都结束
        if self.monitor_start_state_Thread is  None:
            self.monitor_start_state_Thread = Monitor_start_state_Thread(name="Monitor_start_state_Thread",UFC_gas_path_system_obj=self.UFC_gas_path_system_obj,UGC_gas_path_system_obj=self.UGC_gas_path_system_obj,ZOS_gas_path_system_obj=self.ZOS_gas_path_system_obj,update_start_state_signal=self.update_start_state_signal)
        self.monitor_start_state_Thread.start()

        #開始結束回調
        if self.auto_run_thread is not None and self.auto_run_thread.isRunning():
            self.auto_run_thread.start_finish_signal.emit()


        return p

        pass

    #运行按钮事件 运行气路
    def run_btn_handle(self):
        self.state_label.setText("正在运行...")
        self.state_label.setStyleSheet("QLabel { color:green; }")
        p=AsyPromise(self.UFC_gas_path_system_obj.run).then(
            lambda v: AsyPromise(
                self.UGC_gas_path_system_obj.run,
            ).then(
                lambda v2: AsyPromise(self.ZOS_gas_path_system_obj.run)
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))
        self.run_btn.setEnabled(False)
        # 運行結束回調
        if self.auto_run_thread is not None and self.auto_run_thread.isRunning():
            self.auto_run_thread.run_finish_signal.emit()
        return p
        pass
    #停止按钮事件 停止气路
    def stop_btn_handle(self):
        self.state_label.setText("正在停止")
        self.state_label.setStyleSheet("QLabel { color:black; }")
        if  self.monitor_start_state_Thread is not None :
            self.monitor_start_state_Thread.stop()
        self.close_timers()
        p=AsyPromise(self.UGC_gas_path_system_obj.stop).then(
            lambda v: AsyPromise(
                self.UFC_gas_path_system_obj.stop,
            ).then(
                lambda v2: AsyPromise(self.ZOS_gas_path_system_obj.stop)
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))
        self.state_label.setText("未启动")
        self.state_label.setStyleSheet("QLabel { color:red; }")
        self.start_btn.setEnabled(True)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        return p
        pass

    def calibration_handle(self):
        #标定主函数 启动timer
        self.set_calibration_start_timer()
        # 標定結束回調
        if self.auto_run_thread is not None and self.auto_run_thread.isRunning():
            self.auto_run_thread.carlibration_finish_signal.emit()
        pass
    #标定执行函数
    def carlibation(self):
        p=AsyPromise(self.Zero_carlibration_obj.calibrate).then(
            lambda v: AsyPromise(
                self.Range_carlibration_obj.calibrate
            ).then(

            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))

        return p
        pass
    #状态检测timer
    def gas_state_check_handle(self):
        self.set_gas_state_check_timer()
        # 狀態結束回調
        if self.auto_run_thread is not None and self.auto_run_thread.isRunning():
            self.auto_run_thread.check_finish_signal.emit()
        pass
    #状态检测执行函数
    def gas_state_check(self):

        p= AsyPromise(self.UFC_gas_state_check_obj.state_check).then(
        ).catch(lambda e: logger.error(f"{e}"))

        return p
        pass

    #自动执行按钮事件
    def auto_btn_handle(self):
        self.auto_btn.setEnabled(False)
        if self.auto_run_thread is None:
            self.auto_run_thread = auto_run_Thread(name="auto_run_thread",
                                                   start_signal=self.start_signal,
                                                   run_signal=self.run_signal,
                                                   carlibration_signal=self.carlibration_signal,
                                                   gas_state_check_signal=self.gas_state_check_signal,
                                                   auto_finish_signal=self.auto_finish_signal,
                                                   )
        self.auto_run_thread.start()
        pass
    #解除自动执行按钮事件
    def disabled_auto_btn_handle(self):
        if self.auto_run_thread is not None:
            self.auto_run_thread.stop()
        self.disabled_auto_btn.setEnabled(False)
        self.stop_btn_handle().then(
            self.auto_btn.setEnabled(True)
        )
        pass
    #设置启动阶段的定时器
    def set_start_timers(self,resolve, reject):
        self.set_zos_start_timer()
        self.set_ufc_start_timer()
        resolve()
    def close_timers(self):
        # 关闭timers
        # 关闭窗口时确保停止定时器
        if self.zos_start_timer is not None and (self.zos_start_timer.is_active() or self.zos_start_timer._is_paused):
            self.zos_start_timer.stop()
        if self.ufc_start_timer is not None and (self.ufc_start_timer.is_active() or self.ufc_start_timer._is_paused):
            self.ufc_start_timer.stop()
        if self.calibration_start_timer is not None and (self.calibration_start_timer.is_active() or self.calibration_start_timer._is_paused):
            self.calibration_start_timer.stop()
        if self.gas_state_check_timer is not None and (self.gas_state_check_timer.is_active() or self.gas_state_check_timer._is_paused):
            self.gas_state_check_timer.stop()
        pass
    #设置状态检测计时器
    def set_gas_state_check_timer(self):
        # logger.error(f"1:{float(global_setting.get_setting('UFC_UGC_ZOS_config')['Gas_State_Check']['start_time_delay']) * 1000}")
        self.gas_state_check_timer= PeriodicTimer(
                interval_ms=float(global_setting.get_setting('UFC_UGC_ZOS_config')['Gas_State_Check']['start_time_delay']) * 1000,
                max_duration_ms=None,
                task=None,  # 先不传，后面用 set_task 注入
                run_in_thread=True,  # 若你的任务耗时，设为 True

                run_immediately=True
            )
        self.gas_state_check_timer.set_task(self.gas_state_check)
        self.gas_state_check_timer.start()
        pass
    # 设置标定计时器
    def set_calibration_start_timer(self):
        self.calibration_start_timer =  PeriodicTimer(
                interval_ms=float(global_setting.get_setting('UFC_UGC_ZOS_config')['Calibration']['start_time_delay']) * 1000,
                max_duration_ms=None,
                task=None,  # 先不传，后面用 set_task 注入
                run_in_thread=True,  # 若你的任务耗时，设为 True

                run_immediately=True
            )
        self.calibration_start_timer.set_task(self.carlibation)
        self.calibration_start_timer.start()
    # 设置zos预热定时器
    def set_zos_start_timer(self):
            # 构造 PeriodicTimer（2秒间隔，20分钟上限）

            self.zos_start_timer = PeriodicTimer(
                interval_ms=float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['start_time_delay']) * 1000,
                max_duration_ms=float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['start_time']) * 1000,
                task=None,  # 先不传，后面用 set_task 注入
                run_in_thread=True,  # 若你的任务耗时，设为 True

                run_immediately=True
            )
            self.zos_start_timer.set_task(self.ZOS_gas_path_system_obj.zos_start_timer_task)
            self.zos_start_timer.start()
    #设置UFC 等待流量控制器自动配置及运行 定时器
    def  set_ufc_start_timer(self):
        try:
            self.ufc_start_timer = PeriodicTimer(
                interval_ms=float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['start_wait_time_delay']) * 1000,
                max_duration_ms=float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['start_wait_time']) * 1000,
                task=None,  # 先不传，后面用 set_task 注入
                run_in_thread=True,  # 若你的任务耗时，设为 True

                run_immediately=True
            )
        except Exception as e:
            logger.error(e)
        self.ufc_start_timer.finished.connect(self.UFC_gas_path_system_obj.check_ufc_start_time_state)
        self.ufc_start_timer.set_task(self.UFC_gas_path_system_obj.ufc_start_timer_task)
        self.ufc_start_timer.start()








