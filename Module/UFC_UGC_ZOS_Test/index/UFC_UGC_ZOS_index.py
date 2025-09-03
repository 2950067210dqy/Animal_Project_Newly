import math
import time
import typing

from loguru import logger

from Module.UFC_UGC_ZOS_Test.ui.UFC_UGC_ZOS_window import Ui_UFC_UGC_ZOS_window


from public.config_class.global_setting import global_setting

from public.entity.MyQThread import MyQThread
from public.entity.enum.Public_Enum import AppState
from public.entity.experiment_setting_entity import Experiment_setting_entity


from Module.UFC_UGC_ZOS_Test.function.modbus.COM_Scan import scan_serial_ports_with_id
from Module.UFC_UGC_ZOS_Test.function.modbus.Modbus import ModbusRTUMaster
from theme.ThemeQt6 import ThemedWindow
from PyQt6 import QtGui
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import  QComboBox, QListWidget, QPushButton

from public.util.time_util import time_util


class read_queue_data_Thread(MyQThread):
    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.update_status_main_signal_gui_update: pyqtSignal(str) = None
        pass

    def dosomething(self):
        if not self.queue.empty():
            message = self.queue.get()
            # message 结构{'to'发往哪个线程，'data'数据，‘from'从哪来}

            if message is not None and isinstance(message, dict) and len(message) > 0 and 'to' in message and message[
                'to'] == 'UFC_UGC_ZOS_index':
                logger.error(f"{self.name}_get_message:{message}")
                if 'data' in message:
                    if self.update_status_main_signal_gui_update is not None:
                        self.update_status_main_signal_gui_update.emit(message['data'])
                    pass
            else:
                # 把消息放回去
                self.queue.put(message)

        pass


read_queue_data_thread = read_queue_data_Thread(name="UFC_UGC_ZOS_index_read_queue_data_thread")

class Send_thread(MyQThread):
    # 线程信号

    def __init__(self, name=None,  modbus=None, send_message=None):
        super().__init__(name)

        self.modbus = modbus
        self.send_message = send_message
        self.is_start = True
        pass

    def __del__(self):
        logger.debug(f"线程{self.name}被销毁!")

    def init_modBus(self):
        try:

                self.modbus = ModbusRTUMaster(
                    port=self.send_message['port'],
                    timeout=float(
                        global_setting.get_setting('monitor_data')['Serial']['timeout']),
                    origin="UFC_UGC_ZOS_index"
                                              )
        except:
            pass
        pass

    def set_send_message(self, send_message):
        self.send_message = send_message

    def set_modbus(self, modbus):
        self.modbus = modbus

    def dosomething(self):
        if self.is_start:
            self.init_modBus()
            try:
                logger.info(self.send_message)
                response, response_hex, send_state = self.modbus.send_command(
                    slave_id=self.send_message['slave_id'],
                    function_code=self.send_message['function_code'],
                    data_hex_list=self.send_message['data']
                    ,is_parse_response=False
                )
                # 响应报文是正确的，即发送状态时正确的 进行解析响应报文
                if send_state:
                    return_data, parser_message = self.modbus.parse_response(response=response,
                                                                             response_hex=response.hex(),
                                                                             send_state=True,
                                                                             slave_id=
                                                                             self.send_message['slave_id'],
                                                                             function_code=
                                                                             self.send_message['function_code'], )

                    # 把返回数据返回给源头
                    message_struct = {'to': "UFC_UGC_ZOS_index", 'data': parser_message, 'from': 'UFC_UGC_ZOS_index_send_thread'}
                    global_setting.get_setting("send_message_queue").put(message_struct)
                    logger.debug(f"UFC_UGC_ZOS_index_send_thread将响应报文的解析数据返回源头：{message_struct}")
                    pass
                self.is_start = False
            except Exception as e:
                logger.error(e)
            finally:
                self.is_start = False
            time.sleep(1)
        pass

    pass


class UFC_UGC_ZOS_index(ThemedWindow):
    update_status_main_signal_gui_update = pyqtSignal(str)


    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        # 加载qss样式表
        logger.warning("UFC_UGC_ZOS_index——show")
        if self.send_thread is not None and self.send_thread.isRunning():
            self.send_thread.resume()
        # 实例化自定义ui
        self._init_customize_ui()
        super().showEvent(a0)
    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.warning("UFC_UGC_ZOS_index--hide")
        if self.send_thread is not None and self.send_thread.isRunning():
            self.send_thread.pause()
        super().hideEvent(a0)
    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        self.experiment_setting: Experiment_setting_entity =None
        # 发送报文线程
        self.send_thread:Send_thread = None
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
        # 重新获取端口按钮
        self.refresh_port_btn: QPushButton=None
        #手动按钮
        self.manual_btn:QPushButton=None
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
            self.send_response_text(
                f"{time_util.get_format_from_time(time.time())}- 设备: {self.ports[0]['device']}" + f" #{self.ports[0]['description']}" + "  默认已被选中!")
        port_combox.disconnect()
        port_combox.currentIndexChanged.connect(self.selectionchange)
    #端口下拉框选择事件
    def selectionchange(self, index):
        try:
            self.send_message['port'] = self.ports[index]['device']
            global_setting.set_setting("port", self.send_message['port'])

            self.send_response_text(
                f"{time_util.get_format_from_time(time.time())}- 设备: {self.ports[index]['device']}" + f" #{self.ports[index]['description']}" + "  已被选中!")
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
        response_text.addItem(text)
        if self.main_gui is not None:
            self.main_gui.status_bar.update_tip(text)
        # 滑动滚动条到最底下
        scroll_bar = response_text.verticalScrollBar()
        if scroll_bar != None:
            scroll_bar.setValue(scroll_bar.maximum())
        pass


    # 实例化功能
    def _init_function(self):
        # 实例化按钮信号槽绑定
        self.init_btn_func()
        # 实例化信号
        # 将更新status信号绑定更新status界面函数
        self.update_status_main_signal_gui_update.connect(self.send_response_text)
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
        self.run_btn.clicked.connect(self.run_btn_handle)
        #停止按钮
        self.stop_btn: QPushButton = self.findChild(QPushButton, "stop_btn")
        self.stop_btn.clicked.connect(self.stop_btn_handle)
        #手动按钮
        self.manual_btn: QPushButton = self.findChild(QPushButton, "manual_btn")
        self.manual_btn.clicked.connect(self.manual_btn_handle)
        #自动按钮
        self.auto_btn: QPushButton = self.findChild(QPushButton, "auto_btn")
        self.auto_btn.clicked.connect(self.auto_btn_handle)
        #解除自动按钮
        self.disabled_auto_btn: QPushButton = self.findChild(QPushButton, "disabled_auto_btn")
        self.disabled_auto_btn.clicked.connect(self.disabled_auto_btn_handle)

        pass


    # 重新获取端口
    def refresh_port(self):
        self.ports = []
        self._init_data()
        self.init_port_combox()

    #启动按钮事件 启动气路
    def start_btn_handle(self):
        pass
    #运行按钮事件 运行气路
    def run_btn_handle(self):
        pass
    #停止按钮事件 停止气路
    def stop_btn_handle(self):
        pass

    #手动执行一次事件
    def manual_btn_handle(self):
        pass
    #自动执行按钮事件
    def auto_btn_handle(self):
        pass
    #解除自动执行按钮事件
    def disabled_auto_btn_handle(self):
        pass





    def send_data(self):
        state = global_setting.get_setting("app_state",AppState.INITIALIZED)
        # 根据是否已经实验来发送到自己还是main_monitor_data
        if state is None or state !=AppState.MONITORING:
            # 发送数据
            try:
                if self.send_thread is None:
                    logger.info("初始化串口")
                    self.send_thread = None
                    self.send_thread = Send_thread(name="tab_3_COM_Send_Thread",
                                                   modbus=None, send_message=self.send_message)

                    self.send_thread.is_start = True
                    self.send_thread.start()

                    return
                    # 发送
                logger.info("未初始化串口对象,使用之前串口实例化对象")
                self.send_thread.set_send_message(self.send_message)
                self.send_thread.is_start = True
            except Exception as e:
                logger.error(e)
        else:
            message = {'to': 'main_monitor_data', 'data': self.send_message, 'from': 'tab_7'}
            global_setting.get_setting("send_message_queue").put(message)
            logger.debug(f"tab_7开始发送消息:{message}")


