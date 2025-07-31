import time
import typing

from PyQt6.QtGui import QAction
from loguru import logger

from Module.experiment_setting.config.experiment_default_config import get_default_config

from Module.experiment_setting.ui.tab7 import Ui_tab7_frame
from Module.experiment_setting.ui.tab7_window import Ui_tab7_window
from Service import main_monitor_data
from my_abc.BaseInterfaceWidget import BaseInterfaceType
from public.config_class.global_setting import global_setting
from public.entity.BaseWindow import BaseWindow

from public.entity.MyQThread import MyQThread
from public.function.Modbus import Modbus_Type

from public.function.Modbus.COM_Scan import scan_serial_ports_with_id
from public.function.Modbus.Modbus import ModbusRTUMaster
from theme.ThemeQt6 import ThemedWidget, ThemedWindow
from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QScrollArea, QGroupBox, QLabel, QSlider, QRadioButton, \
    QGridLayout, QButtonGroup, QComboBox, QListWidget, QPushButton

from theme.ThemeQt6 import ThemedWidget

from util.time_util import time_util


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
                'to'] == 'tab_7':
                logger.error(f"{self.name}_get_message:{message}")
                if 'data' in message:
                    if self.update_status_main_signal_gui_update is not None:
                        self.update_status_main_signal_gui_update.emit(message['data'])
                    pass
            else:
                # 把消息放回去
                self.queue.put(message)

        pass


read_queue_data_thread = read_queue_data_Thread(name="tab_7_read_queue_data_thread")

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
                    origin="tab_7"
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
                    message_struct = {'to': "tab_7", 'data': parser_message, 'from': 'tab_7_send_thread'}
                    global_setting.get_setting("send_message_queue").put(message_struct)
                    logger.debug(f"tab_7_send_thread将响应报文的解析数据返回源头：{message_struct}")
                    pass
                self.is_start = False
            except Exception as e:
                logger.error(e)
            finally:
                self.is_start = False
            time.sleep(1)
        pass

    pass


class Tab_7(ThemedWindow):
    update_status_main_signal_gui_update = pyqtSignal(str)

    def closeEvent(self, event):
        # 关闭事件
        if self.main_gui is not None:

            for index in range(len(self.main_gui.open_windows)):
                if self.main_gui.open_windows[index] is self:
                    del self.main_gui.open_windows[index]
                    break
                index+=1
        pass
    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        # 加载qss样式表
        logger.warning("tab7——show")
        if self.send_thread is not None and self.send_thread.isRunning():
            self.send_thread.resume()

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.warning("tab7--hide")
        # 主界面的当前页面为None
        self.main_gui.activate_widget = None
        if self.send_thread is not None and self.send_thread.isRunning():
            self.send_thread.pause()
    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()

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
        # 配置json对象
        self.config = None
        # 配置layout
        self.config_layout:QVBoxLayout = None
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

        # 实例化ui

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        # 有父窗口添加父窗口
        if parent != None and geometry != None:
            self.setParent(parent)
            self.setGeometry(geometry)
        else:
            pass

        self.ui = Ui_tab7_window()

        self.ui.setupUi(self)

        self._retranslateUi()
        pass

    # 实例化自定义ui
    def _init_customize_ui(self):
        # 实例化下拉框
        self.init_port_combox()
        # 读取默认config json
        self.config = get_default_config()
        # logger.error(self.config)
        self.init_config_ui()
        pass

    # 实例化下拉框
    def init_port_combox(self):
        port_combox: QComboBox = self.findChild(QComboBox, "tab_7_port_combox")
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

    def selectionchange(self, index):
        try:
            self.send_message['port'] = self.ports[index]['device']
            global_setting.set_setting("port", self.send_message['port'])

            self.send_response_text(
                f"{time_util.get_format_from_time(time.time())}- 设备: {self.ports[index]['device']}" + f" #{self.ports[index]['description']}" + "  已被选中!")
        except Exception as e:
            logger.error(e)
        pass
    def send_response_text(self, text):
        # 往状态栏发消息
        response_text: QListWidget = self.findChild(QListWidget, "tab_7_responselist")
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
    def remove_layout_items(self, layout):
        # 遍历并移除布局中的所有项目
        while layout.count():
            item = layout.takeAt(0)  # 取出第一个项目
            if item is not None:
                widget = item.widget()  # 获取该项目的 widget，如果有
                if widget is not None:
                    widget.deleteLater()  # 删除 widget 的创建/显示
                else:
                    # 如果是其他布局，则递归调用
                    sub_layout = item.layout()
                    if sub_layout is not None:
                        self.remove_layout_items(sub_layout)  # 递归清空子布局
    def init_config_ui(self):
        #添加config ——ui

        # 找到layout
        self.config_layout :QVBoxLayout= self.findChild(QVBoxLayout,"content_layout")
        if self.config_layout is not None:
            # 清除所有子组件
            self.remove_layout_items(self.config_layout)
            # 添加scroll_area
            # 添加滚动区域
            self.scroll_area = QScrollArea()
            self.scroll_area.setObjectName("content_layout_scroll_area")
            self.scroll_area.setWidgetResizable(True)  # 使滚动区域填充空间
            # 创建一个容器部件，用于在滚动区域中放置内容
            self.scroll_area_content = QWidget()
            self.scroll_area_layout = QVBoxLayout(self.scroll_area_content)


            # 添加每个模块
            for module_key, module_value in self.config.items():
                if module_key  ==Modbus_Type.Modbus_Slave_Ids.UFC.value['name']:
                    pass
                elif module_key  ==Modbus_Type.Modbus_Slave_Ids.UGC.value['name']:
                    pass
                elif module_key  ==Modbus_Type.Modbus_Slave_Ids.ZOS.value['name']:
                    pass
                elif module_key  ==Modbus_Type.Modbus_Slave_Ids.ENM.value['name']:
                    self.init_enm_config_ui( module_key, module_value,self.scroll_area_layout)
                    pass
                elif module_key  ==Modbus_Type.Modbus_Slave_Ids.DWM.value['name']:

                    pass
                elif module_key  ==Modbus_Type.Modbus_Slave_Ids.EM.value['name']:
                    self.init_em_config_ui(module_key, module_value, self.scroll_area_layout)
                    pass
                elif module_key  ==Modbus_Type.Modbus_Slave_Ids.WM.value['name']:

                    pass
                pass
            pass
            # 将容器部件设置为滚动区域的主部件
            self.scroll_area.setWidget(self.scroll_area_content)
            self.config_layout.addWidget(self.scroll_area)
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
        refresh_port_btn: QPushButton = self.findChild(QPushButton, "tab_7_refresh_port_btn")

        refresh_port_btn.clicked.connect(self.refresh_port)
        # 开始实验按钮
        self.start_btn: QPushButton = self.findChild(QPushButton, "start_btn")
        self.start_btn.clicked.connect(self.start_experiment)
        # 停止实验按钮
        self.stop_btn: QPushButton = self.findChild(QPushButton, "stop_btn")
        self.stop_btn.clicked.connect(self.stop_experiment)
        self.stop_btn.setEnabled(False)
        pass

    def start_experiment(self):
        if self.main_gui is not None:
            self.main_gui.start_experiment()
            pass

    def stop_experiment(self):
        if self.main_gui is not None:
            self.main_gui.stop_experiment()
    # 重新获取端口
    def refresh_port(self):
        self.ports = []
        self._init_data()
        self.init_port_combox()

    # 获得相关数据
    def _init_data(self):
        # 获得下拉框数据
        self.ports = scan_serial_ports_with_id()
        pass
    def update_slider(self, address,mouse_cage_number,function_code,data_lists,slider:QSlider):
        value = slider.value()

        data_list = ['00', '00', '00', '00']
        if str(value) in data_lists:
            data_list=[hex_str[2:] for hex_str in data_lists[str(value)]['value']]
        self.send_message['data'] = data_list
        if mouse_cage_number ==0:
            self.send_message['slave_id'] = format(address, '02X')
        else:
            self.send_message['slave_id'] = format(address+mouse_cage_number*16, '02X')
        self.send_message['function_code'] = format(function_code, '02X')

        self.send_data()

    def update_slider_label(self,value,label):
        label.setText(f"当前值: {value}")  # 更新当前值标签的文本
        # 更新label
        pass
    def on_radio_button_clicked(self, button,address,mouse_cage_number,function_code,data_lists):
        btn_object_name:str = button.objectName()
        """处理按钮点击事件"""
        data_list = ['00','00','00','00']
        if "on" in btn_object_name.lower():
            data_list=[hex_str[2:] for hex_str in data_lists["0"]['value']]
        elif "off" in btn_object_name.lower():
            data_list = [hex_str[2:] for hex_str in data_lists["1"]['value']]
        self.send_message['data'] = data_list
        if mouse_cage_number ==0:
            self.send_message['slave_id'] = format(address, '02X')
        else:
            self.send_message['slave_id'] = format(address+mouse_cage_number*16, '02X')
        self.send_message['function_code'] = format(function_code, '02X')

        self.send_data()


    def send_data(self):
        state = global_setting.get_setting("experiment")
        # 根据是否已经实验来发送到自己还是main_monitor_data
        if state is None or not state:
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

    def init_em_config_ui(self, module_key, module_value, scroll_area_layout):
        # 创建 GroupBox
        group_box = QGroupBox(f"{module_value['desc']}-{module_value['config'][0]['value'][0]['desc']}")
        group_box.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box)

        # 创建第一个 GridLayout
        grid_layout1 = QGridLayout()
        grid_layout1.setContentsMargins(10, 30, 10, 10)
        group_box.setLayout(grid_layout1)

        # 添加鼠笼和 radio buttons
        for i in range(4):  # 行
            for j in range(2):  # 列
                index = i * 2 + j + 1  # 计算鼠笼编号
                label = QLabel(f"鼠笼 {index}")

                radio_on = QRadioButton(f"{module_value['config'][0]['value'][0]['refer_value']['0']['desc']}")
                radio_on.setObjectName("on")
                radio_off = QRadioButton(f"{module_value['config'][0]['value'][0]['refer_value']['1']['desc']}")
                radio_off.setObjectName("off")
                radio_off.setChecked(True)
                # 创建一个 ButtonGroup
                button_group = QButtonGroup(grid_layout1)  # 绑定到主窗口以便于管理
                # 添加到 ButtonGroup 中
                button_group.addButton(radio_on)
                button_group.addButton(radio_off)
                # 连接信号
                button_group.buttonClicked.connect(
                    lambda button, address=module_value['address'], mouse_cage_number=index,
                           function_code=module_value['config'][0]['function_code'],
                           data_lists=module_value['config'][0]['value'][0]['refer_value']:
                    self.on_radio_button_clicked(button, address, mouse_cage_number, function_code, data_lists))
                # 这里的3代表组件数量  label  radio_on radio_off 3个
                grid_layout1.addWidget(label, i, j * 3)  # 标签在 (i, j * 3)
                grid_layout1.addWidget(radio_on, i, j * 3 + 1)  # ON 按钮在 (i, j * 3 + 1)
                grid_layout1.addWidget(radio_off, i, j * 3 + 2)  # OFF 按钮在 (i, j * 3 + 2)
        pass
    def init_enm_config_ui(self, module_key, module_value,scroll_area_layout):
        # 创建 GroupBox
        group_box = QGroupBox(f"{module_value['desc']}-{module_value['config'][0]['value'][0]['desc']}")
        group_box.setContentsMargins(10,10,10,10)
        scroll_area_layout.addWidget(group_box)

        # 创建第一个 GridLayout
        grid_layout1 = QGridLayout()
        grid_layout1.setContentsMargins(10,30,10,10)
        group_box.setLayout(grid_layout1)

        # 添加鼠笼和 radio buttons
        for i in range(4):  # 行
            for j in range(2):  # 列
                index = i * 2 + j + 1  # 计算鼠笼编号
                label = QLabel(f"鼠笼 {index}")

                radio_on = QRadioButton(f"{module_value['config'][0]['value'][0]['refer_value']['0']['desc']}")
                radio_on.setObjectName("on")
                radio_off = QRadioButton(f"{module_value['config'][0]['value'][0]['refer_value']['1']['desc']}")
                radio_off.setObjectName("off")
                radio_off.setChecked(True)
                # 创建一个 ButtonGroup
                button_group = QButtonGroup(grid_layout1)  # 绑定到主窗口以便于管理
                # 添加到 ButtonGroup 中
                button_group.addButton(radio_on)
                button_group.addButton(radio_off)
                # 连接信号
                button_group.buttonClicked.connect(lambda button,address=module_value['address'],mouse_cage_number=index,function_code=module_value['config'][0]['function_code'],data_lists=module_value['config'][0]['value'][0]['refer_value']:
                                                   self.on_radio_button_clicked(button,address,mouse_cage_number,function_code,data_lists))
                # 这里的3代表组件数量  label  radio_on radio_off 3个
                grid_layout1.addWidget(label, i, j * 3)  # 标签在 (i, j * 3)
                grid_layout1.addWidget(radio_on, i, j * 3 + 1)  # ON 按钮在 (i, j * 3 + 1)
                grid_layout1.addWidget(radio_off, i, j * 3 + 2)  # OFF 按钮在 (i, j * 3 + 2)

        # 创建第2个 GridLayout
        group_box2 = QGroupBox(f"{module_value['desc']}-{module_value['config'][0]['value'][1]['desc']}")
        group_box2.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box2)
        grid_layout2 = QGridLayout()
        grid_layout2.setContentsMargins(10,30, 10, 10)
        group_box2.setLayout(grid_layout2)

        # 添加鼠笼和 radio buttons
        for i in range(4):  # 行
            for j in range(2):  # 列
                index = i * 2 + j + 1  # 计算鼠笼编号
                label = QLabel(f"鼠笼 {index}")

                radio_on = QRadioButton(f"{module_value['config'][0]['value'][1]['refer_value']['0']['desc']}")
                radio_on.setObjectName("on")
                radio_off = QRadioButton(f"{module_value['config'][0]['value'][1]['refer_value']['1']['desc']}")
                radio_off.setObjectName("off")
                radio_off.setChecked(True)
                # 创建一个 ButtonGroup
                button_group = QButtonGroup(grid_layout2)  # 绑定到主窗口以便于管理
                # 添加到 ButtonGroup 中
                button_group.addButton(radio_on)
                button_group.addButton(radio_off)
                button_group.buttonClicked.connect(
                    lambda button, address=module_value['address'], mouse_cage_number=index,
                           function_code=module_value['config'][0]['function_code'],
                           data_lists=module_value['config'][0]['value'][1]['refer_value']:
                    self.on_radio_button_clicked(button, address, mouse_cage_number, function_code, data_lists))
                grid_layout2.addWidget(label, i, j * 3)  # 标签在 (i, j * 3)
                grid_layout2.addWidget(radio_on, i, j * 3 + 1)  # ON 按钮在 (i, j * 3 + 1)
                grid_layout2.addWidget(radio_off, i, j * 3 + 2)  # OFF 按钮在 (i, j * 3 + 2)

        # 创建第3个 GridLayout
        group_box3 = QGroupBox(f"{module_value['desc']}-{module_value['config'][1]['value'][0]['desc']}")
        group_box3.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box3)
        # 创建第二个 GridLayout
        grid_layout3 = QGridLayout()
        grid_layout3.setContentsMargins(10, 30, 10, 10)
        group_box3.setLayout(grid_layout3)

        # 添加鼠笼和 sliders
        for i in range(4):  # 行
            for j in range(2):  # 列
                index = i * 2 + j + 1  # 计算鼠笼编号
                label = QLabel(f"鼠笼 {index}")
                slider = QSlider()  # 创建滑块
                slider.setOrientation(Qt.Orientation.Horizontal)  # 设置为横向
                slider.setMinimum(1)  # 最小值
                slider.setMaximum(9)  # 最大值
                slider.setValue(1)  # 默认值

                # 创建一个 label 来显示当前值
                current_value_label = QLabel("当前值: 1")

                # 连接滑块的值变化信号到更新标签的槽
                slider.valueChanged.connect(lambda value, label=current_value_label:self.update_slider_label(value, label))
                slider.sliderReleased.connect(lambda address=module_value['address'],mouse_cage_number=index,function_code=module_value['config'][1]['function_code'],data_lists=module_value['config'][1]['value'][0]['refer_value'], slider=slider
                                            : self.update_slider(address,mouse_cage_number,function_code,data_lists,slider))

                # 添加到布局中
                grid_layout3.addWidget(label, i, j * 3)  # 标签在 (i, j * 3)
                grid_layout3.addWidget(slider, i, j * 3 + 1)  # 滑块在 (i, j * 3 + 1)
                grid_layout3.addWidget(current_value_label, i, j * 3 + 2)  # 当前值标签在 (i, j * 3 + 2)
        # 创建第4个 GridLayout
        group_box4 = QGroupBox(f"{module_value['desc']}-{module_value['config'][1]['value'][1]['desc']}")
        group_box4.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box4)
        grid_layout4 = QGridLayout()
        grid_layout4.setContentsMargins(10, 30, 10, 10)
        group_box4.setLayout(grid_layout4)

        # 添加鼠笼和 sliders
        for i in range(4):  # 行
            for j in range(2):  # 列
                index = i * 2 + j + 1  # 计算鼠笼编号
                label = QLabel(f"鼠笼 {index}")
                slider = QSlider()  # 创建滑块
                slider.setOrientation(Qt.Orientation.Horizontal)  # 设置为横向
                slider.setMinimum(1)  # 最小值
                slider.setMaximum(9)  # 最大值
                slider.setValue(1)  # 默认值

                # 创建一个 label 来显示当前值
                current_value_label = QLabel("当前值: 1")

                # 连接滑块的值变化信号到更新标签的槽
                slider.valueChanged.connect(
                    lambda value, label=current_value_label: self.update_slider_label(value, label))
                slider.sliderReleased.connect(lambda address=module_value['address'], mouse_cage_number=index,
                                                     function_code=module_value['config'][1]['function_code'],
                                                     data_lists=module_value['config'][1]['value'][1]['refer_value'],
                                                     slider=slider
                                              : self.update_slider(address, mouse_cage_number, function_code,
                                                                   data_lists, slider))

                # 添加到布局中
                grid_layout4.addWidget(label, i, j * 3)  # 标签在 (i, j * 3)
                grid_layout4.addWidget(slider, i, j * 3 + 1)  # 滑块在 (i, j * 3 + 1)
                grid_layout4.addWidget(current_value_label, i, j * 3 + 2)  # 当前值标签在 (i, j * 3 + 2)
        pass


