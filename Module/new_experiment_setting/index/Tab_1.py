# Module/new_experiment_setting/index/Tab_1.py
import json
import math
import time
import typing
import threading  # 新增

from PyQt6.QtGui import QDoubleValidator, QColor
from loguru import logger

from Module.new_experiment_setting.config.new_experiment_default_config import get_default_config
from Module.new_experiment_setting.ui.tab1_frame import Ui_tab1_frame
from public.component.Guide_tutorial_interface.Tutorial_Manager import TutorialManager
from public.component.dialog.custom.InfoDialog import InfoDialog
from public.config_class.App_Setting import AppSettings
from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from public.entity.enum.Public_Enum import AppState, Tutorial_Type
from public.entity.experiment_setting_entity import Experiment_setting_entity
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Modbus import Modbus_Type
from public.function.Modbus.COM_Scan import scan_serial_ports_with_id
from public.function.Modbus.Modbus import ModbusRTUMaster
from public.function.Modbus.New_Mod_Bus import ModbusRTUMasterNew
from theme.ThemeQt6 import ThemedWindow
from PyQt6 import QtGui, QtCore
from PyQt6.QtCore import QRect, Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QGroupBox, QLabel, QSlider, QRadioButton,
    QGridLayout, QButtonGroup, QComboBox, QPushButton, QMessageBox, QHBoxLayout,
    QLineEdit, QDoubleSpinBox, QListWidget, QListWidgetItem
)
from public.util.time_util import time_util

# ========== 常量定义 ==========

# 定义必需的笼子内模块
REQUIRED_MODULES = ['ENM', 'EM']

# 定义所有需要检测的笼子内模块
ALL_MODULES_TO_DETECT = {
    'ENM': 0x0B,  # 环境监测模块
    'EM': 0x0D,  # 食物管理模块
    'DWM': 0x0C,  # 饮水处理模块
    'WM': 0x0E,  # 称重模块
}


# ========== 线程相关 ==========

class read_queue_data_Thread(MyQThread):
    """读取队列数据的线程"""

    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.update_group_activation_signal: pyqtSignal = None

    def dosomething(self):
        if not self.queue.empty():
            try:
                message: ObjectQueueItem = self.queue.get()
            except Exception as e:
                logger.error(f"{self.name}发生错误{e}")
                return

            if message is not None and isinstance(message, ObjectQueueItem) and message.to == 'tab_1':
                logger.info(f"{self.name}_get_message: {message.title}")
                match message.title:
                    case 'group_response':
                        if self.update_group_activation_signal is not None:
                            data_to_emit = message.data

                            # 改进：直接处理字典数据
                            if isinstance(data_to_emit, dict):
                                # 字典格式，直接发送
                                logger.info(f"响应数据 (笼子{data_to_emit.get('group_id')}): {data_to_emit}")
                                self.update_group_activation_signal.emit(data_to_emit)
                            elif isinstance(data_to_emit, str):
                                # 字符串格式，解析后发送
                                logger.info(f"响应数据（字符串）: {data_to_emit}")
                                response_dict = self.parse_response_string(data_to_emit)
                                self.update_group_activation_signal.emit(response_dict)
                            else:
                                logger.error(f"未知数据类型: {type(data_to_emit)}")
                    case _:
                        pass
            else:
                if message:
                    self.queue.put(message)

    def parse_response_string(self, response_str):
        """从响应字符串中解析鼠笼号和模块信息"""
        try:
            if len(response_str) > 10:
                hex_parts = response_str.split('-')
                slave_id = None

                for part in hex_parts:
                    if len(part) >= 8 and all(c in '0123456789abcdefABCDEF' for c in part[:8]):
                        slave_id = int(part[0:2], 16)
                        break

                module_name = self.extract_module_name(response_str)

                return {
                    'group_id': slave_id // 16 if slave_id else 0,  # 从slave_id提取group_id
                    'slave_id': slave_id,
                    'module_name': module_name,
                    'raw_data': response_str
                }
            else:
                return {'group_id': 0, 'raw_data': response_str}

        except Exception as e:
            logger.error(f"解析响应字符串失败: {e}, 原数据: {response_str}")
            return {'group_id': 0, 'raw_data': response_str}

    def extract_module_name(self, response_str):
        """从响应字符串中提取模块名"""
        module_names = ['ZOS', 'UFC', 'UGC', 'ENM', 'EM', 'DWM', 'WM']
        for module_name in module_names:
            if module_name in response_str:
                return module_name
        return 'UNKNOWN'


read_queue_data_thread = read_queue_data_Thread(name="tab_1_read_queue_data_thread")


class Send_thread(MyQThread):
    """发送数据的线程"""

    def __init__(self, name=None, modbus=None, send_message=None):
        super().__init__(name)
        self.modbus = modbus
        self.send_message = send_message
        self.is_start = True
        self.group_id = None  # 保存笼子号

    def __del__(self):
        logger.debug(f"线程{self.name}被销毁!")

    def init_modBus(self):
        try:
            self.modbus = ModbusRTUMaster(
                port=self.send_message['port'],
                timeout=float(global_setting.get_setting('monitor_data')['Serial']['timeout']),
                origin="tab_1"
            )
        except Exception as e:
            logger.error(f"初始化Modbus失败: {e}")

    def set_send_message(self, send_message):
        self.send_message = send_message
        self.group_id = send_message.get('group_id')  # 提取笼子号

    def set_modbus(self, modbus):
        self.modbus = modbus

    def dosomething(self):
        if self.is_start:
            self.init_modBus()
            try:
                logger.info(f"发送报文 (笼子{self.group_id}): slave_id={self.send_message['slave_id']}, "
                            f"function_code={self.send_message['function_code']}")
                response, response_hex, send_state = self.modbus.send_command(
                    slave_id=self.send_message['slave_id'],
                    function_code=self.send_message['function_code'],
                    data_hex_list=self.send_message['data'],
                    is_parse_response=False
                )
                if send_state:
                    return_data, parser_message = self.modbus.parse_response(
                        response=response,
                        response_hex=response.hex(),
                        send_state=True,
                        slave_id=self.send_message['slave_id'],
                        function_code=self.send_message['function_code'],
                    )

                    # 构造响应数据，包含笼子号
                    message_struct = ObjectQueueItem(
                        to="tab_1",
                        data={
                            'parsed_data': parser_message,
                            'group_id': self.group_id,  # 添加笼子号
                            'slave_id': int(self.send_message['slave_id'], 16),
                            'module_name': self.extract_module_name(parser_message)
                        },
                        title='group_response',
                        origin='tab_1_send_thread'
                    )

                    global_setting.get_setting("send_message_queue").put(message_struct)
                    logger.info(f"笼子{self.group_id}响应成功")
                else:
                    logger.warning(f"笼子{self.group_id}发送失败，无响应")

                self.is_start = False
            except Exception as e:
                logger.error(f"笼子{self.group_id}异常: {e}")
            finally:
                self.is_start = False
            time.sleep(0.5)

    def extract_module_name(self, parser_message):
        """从解析的消息中提取模块名"""
        if isinstance(parser_message, str):
            for module in ['ZOS', 'UFC', 'UGC', 'ENM', 'EM', 'DWM', 'WM']:
                if module in parser_message:
                    return module
        return 'UNKNOWN'


# ========== 主窗口 ==========

class Tab_1(ThemedWindow):
    update_group_activation_signal = pyqtSignal(dict)

    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        """窗口显示事件"""
        logger.warning("tab1——show")
        if self.send_thread is not None and self.send_thread.isRunning():
            self.send_thread.resume()
        self._init_customize_ui()
        super().showEvent(a0)

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        """窗口隐藏事件"""
        logger.warning("tab1--hide")
        if self.send_thread is not None and self.send_thread.isRunning():
            self.send_thread.pause()
        super().hideEvent(a0)

    def setup_tutorial(self):
        """设置教程"""
        if self.tutorial:
            self.tutorial.end_tutorial()

        self.tutorial = TutorialManager(
            self, "experiment_setting", Tutorial_Type.ARROW_GUIDE,
            global_setting.get_setting("app_setting", AppSettings())
        )

        self.tutorial.tutorial_completed.connect(self.on_tutorial_completed)

        self.tutorial.add_step(
            self.port_combox,
            f"步骤1：选择正确的串口，这步非常的重要，不然无法联系到传感器。"
        )
        self.tutorial.add_step(
            self.cage_list_widget if hasattr(self,
                                             'cage_list_widget') and self.cage_list_widget else self.config_layout,
            f"步骤2：可以对相关传感器进行实验前的相关配置。"
        )
        self.tutorial.add_step(
            self.start_btn,
            f"步骤3：最后单击该按钮完成配置。"
        )
        self.tutorial.add_step(
            self.status_bar.tip_btn,
            f"Tips：如果还不会操作，可再次单击该按钮查看教程。"
        )

    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()

        if parent is not None:
            self.setParent(parent)
            self.setWindowFlags(QtCore.Qt.WindowType.Widget)

        # ==================== 线程安全相关 ====================
        self.response_lock = threading.Lock()  # 保护响应数据
        self.group_responses = {}  # {group_id: {module_name: response_data}}
        self.pending_requests = set()  # 追踪待处理的请求

        # ==================== 检测相关属性 ====================
        self.port_confirmed = False
        self.detection_in_progress = False
        self.detecting_groups = {}  # 追踪正在检测的笼子及其模块
        self.detection_timers = {}  # {group_id_module_name: timer}
        self.detection_timeout_timer = None  # 总检测超时计时器
        self.cage_modules_status = {}  # {group_id: {module_name: response_data}}

        # ==================== UI 组件 ====================
        self.port_combox = None
        self.cage_list_widget = None
        self.detection_status_label = None
        self.right_title = None
        self.vr_desc_text: QDoubleSpinBox = None
        self.experiment_setting: Experiment_setting_entity = None
        self.send_thread: Send_thread = None
        self.confirm_port_btn = None
        self.config_btn = None

        # ==================== 消息相关 ====================
        self.send_message = {
            'port': '',
            'data': '',
            'slave_id': 0,
            'function_code': 0,
            'timeout': 0,
            'group_id': None  # 笼子号
        }

        # ==================== 数据相关 ====================
        self.ports = []
        self.config = None
        self.config_layout: QVBoxLayout = None
        self.content_layout: QVBoxLayout = None
        self.start_btn: QPushButton = None
        self.groups_status = {}
        self.selected_group_num = None
        self.cage_enabled_status = {}  # {group_id: group_obj}

        # ==================== 防抖相关 ====================
        self.cage_selection_timer = QTimer()  # 防抖计时器
        self.cage_selection_timer.setSingleShot(True)
        self.cage_selection_timer.timeout.connect(self._on_cage_selected_debounced)
        self.pending_cage_selection = None  # 待处理的笼子选择
        self.last_warning_group_id = None  # 上次显示警告的笼子ID
        self.last_warning_time = 0  # 上次显示警告的时间

        # 初始化UI
        self._init_ui(parent, geometry, title)
        # 获取数据
        self._init_data()
        # 获取实验设置
        self.experiment_setting: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)
        # 初始化自定义UI
        self._init_customize_ui()
        # 初始化功能
        self._init_function()
        # 加载样式表
        self._init_style_sheet()
        # 设置教程
        self.setup_tutorial()
        # 只在没有parent时自动启动教程
        if parent is None:
            QTimer.singleShot(400, self.start_tutorial_if_exists)

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        """初始化UI"""
        if parent is not None:
            self.setParent(parent)
            if geometry is not None:
                self.setGeometry(geometry)

        self.ui = Ui_tab1_frame()
        self.ui.setupUi(self)
        self._retranslateUi()

    def _retranslateUi(self):
        """翻译UI文本（如果需要）"""
        pass

    def _init_customize_ui(self):
        """初始化自定义UI"""
        if self.experiment_setting is None:
            logger.warning("experiment_setting 为None，跳过部分初始化")
            self.init_port_combox()
            self.config = get_default_config()
        else:
            self.init_port_combox()
            self.config = get_default_config()
            QTimer.singleShot(100, self.init_cage_list)

        # 初始化右侧配置区域为默认显示
        self.init_config_ui()

        super()._init_customize_ui()

    def init_port_combox(self):
        """初始化端口下拉框"""
        self.port_combox: QComboBox = self.findChild(QComboBox, "tab_1_port_combox")
        if self.port_combox == None:
            logger.error("实例化端口下拉框失败！")
            return

        self.port_combox.clear()
        for port_obj in self.ports:
            self.port_combox.addItem(f"设备: {port_obj['device']} - {port_obj['description']}")

        if len(self.ports) != 0:
            self.send_message['port'] = self.ports[0]['device']
            global_setting.set_setting("port", self.send_message['port'])
            send_message_queue = global_setting.get_setting("send_message_queue")
            send_message_queue.put(ObjectQueueItem(
                origin='tab_1', to='main_monitor_data', title='set_port',
                data=self.send_message['port'],
                time=time_util.get_format_from_time(time.time())
            ))

            modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
            if modbus is None:
                modbus = ModbusRTUMasterNew(
                    self.send_message['port'], baudrate=115200,
                    timeout=float(global_setting.get_setting('monitor_data')['Serial']['timeout'])
                )
                global_setting.set_setting("modbus", modbus)
            else:
                modbus.close()
                modbus = ModbusRTUMasterNew(
                    self.send_message['port'], baudrate=115200,
                    timeout=float(global_setting.get_setting('monitor_data')['Serial']['timeout'])
                )
                global_setting.set_setting("modbus", modbus)

            logger.info(
                f"{time_util.get_format_from_time(time.time())}- 设备: {self.ports[0]['device']} "
                f"({self.ports[0]['description']}) - 默认已被选中"
            )

        self.port_combox.disconnect()
        self.port_combox.currentIndexChanged.connect(self.on_port_selection_changed)

    def on_port_selection_changed(self, index):
        """端口下拉框选择变化"""
        try:
            if index < 0 or index >= len(self.ports):
                logger.warning(f"无效的端口索引: {index}")
                return

            self.send_message['port'] = self.ports[index]['device']
            global_setting.set_setting("port", self.send_message['port'])
            send_message_queue = global_setting.get_setting("send_message_queue")
            send_message_queue.put(ObjectQueueItem(
                origin='tab_1', to='main_monitor_data', title='set_port',
                data=self.send_message['port'],
                time=time_util.get_format_from_time(time.time())
            ))

            modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
            if modbus is None:
                modbus = ModbusRTUMasterNew(
                    self.send_message['port'], baudrate=115200,
                    timeout=float(global_setting.get_setting('monitor_data')['Serial']['timeout'])
                )
                global_setting.set_setting("modbus", modbus)
            else:
                modbus.close()
                modbus = ModbusRTUMasterNew(
                    self.send_message['port'], baudrate=115200,
                    timeout=float(global_setting.get_setting('monitor_data')['Serial']['timeout'])
                )
                global_setting.set_setting("modbus", modbus)

            logger.info(
                f"{time_util.get_format_from_time(time.time())}- 设备: {self.ports[index]['device']} "
                f"({self.ports[index]['description']}) - 已被选中"
            )
        except Exception as e:
            logger.error(e)

    def init_config_ui(self):
        """初始化配置UI - 显示默认配置"""
        if self.experiment_setting is None:
            self.experiment_setting: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)

        self.config_layout: QVBoxLayout = self.findChild(QVBoxLayout, "content_layout")
        if self.config_layout is not None:
            self.remove_layout_items(self.config_layout)

            self.scroll_area = QScrollArea()
            self.scroll_area.setObjectName("content_layout_scroll_area")
            self.scroll_area.setWidgetResizable(True)

            self.scroll_area_content = QWidget()
            self.scroll_area_layout = QVBoxLayout(self.scroll_area_content)

            # 添加提示标签
            tip_label = QLabel("请先确认串口，然后选择要配置的鼠笼")
            tip_label.setStyleSheet("color: #666; font-style: italic;")
            self.scroll_area_layout.addWidget(tip_label)

            # 初始化基本配置
            self.init_basic_config(self.scroll_area_layout)

            # 如果有config，则显示所有模块的默认配置
            if self.config:
                for module_key, module_value in self.config.items():
                    if module_key == Modbus_Type.Modbus_Slave_Ids.ENM.value['name']:
                        self.init_enm_config_ui_default(module_key, module_value, self.scroll_area_layout)
                    elif module_key == Modbus_Type.Modbus_Slave_Ids.EM.value['name']:
                        self.init_em_config_ui_default(module_key, module_value, self.scroll_area_layout)

            # 添加伸缩空间
            self.scroll_area_layout.addStretch()

            self.scroll_area.setWidget(self.scroll_area_content)
            self.config_layout.addWidget(self.scroll_area)

    def _init_function(self):
        """初始化功能"""
        self.init_btn_func()
        self.update_group_activation_signal.connect(self.update_group_activation)

        global read_queue_data_thread
        read_queue_data_thread.update_group_activation_signal = self.update_group_activation_signal
        read_queue_data_thread.queue = global_setting.get_setting("send_message_queue")
        if read_queue_data_thread is not None and not read_queue_data_thread.isRunning():
            read_queue_data_thread.start()

    def init_btn_func(self):
        """初始化按钮功能"""
        refresh_port_btn: QPushButton = self.findChild(QPushButton, "tab_1_refresh_port_btn")
        if refresh_port_btn:
            refresh_port_btn.clicked.connect(self.refresh_port)

        # 确定串口按钮
        self.confirm_port_btn: QPushButton = self.findChild(QPushButton, "tab_1_confirm_port_btn")
        if self.confirm_port_btn:
            self.confirm_port_btn.clicked.connect(self.confirm_port)
            self.confirm_port_btn.setEnabled(True)

        # 配置按钮（初始禁用）
        self.config_btn: QPushButton = self.findChild(QPushButton, "config_btn")
        if self.config_btn:
            self.config_btn.clicked.connect(self.start_device_config)
            self.config_btn.setEnabled(False)

        self.start_btn: QPushButton = self.findChild(QPushButton, "start_btn")
        if self.start_btn:
            self.start_btn.clicked.connect(self.start_device_config)

    def confirm_port(self):
        """
        确认串口并开始检测
        流程：
        1. 检查是否选择了有效的串口
        2. 禁用串口选择
        3. 初始化笼子列表
        4. 开始检测笼子的所有模块
        """
        if self.port_combox is None:
            logger.error("串口下拉框未初始化")
            self.show_warning("错误", "串口下拉框未初始化")
            return

        selected_port = self.port_combox.currentText()

        if not selected_port or selected_port == "":
            logger.warning("请先选择一个有效的串口")
            self.show_warning("请选择串口", "请从下拉框中选择一个有效的串口")
            return

        # 记录选中的串口
        self.send_message['port'] = self.ports[self.port_combox.currentIndex()]['device']
        self.port_confirmed = True

        logger.info(f"已确认串口: {self.send_message['port']}")

        # 更新UI：禁用串口选择和"确定串口"按钮
        self.port_combox.setEnabled(False)
        if self.confirm_port_btn:
            self.confirm_port_btn.setEnabled(False)
            self.confirm_port_btn.setText("串口已确认")

        # 禁用配置按钮（检测完成后才启用）
        if self.config_btn:
            self.config_btn.setEnabled(False)
            self.config_btn.setText("检测中...")

        # 初始化笼子列表（从数据库读取已启用的笼子）
        self.init_cage_list()

        # 自动开始检测笼子的所有模块
        self.start_module_detection()

    def init_cage_list(self):
        """
        初始化鼠笼列表（已启用的笼子）
        改进：初始化为等待检测状态
        """
        if self.experiment_setting is None:
            logger.warning("experiment_setting 未初始化，跳过鼠笼列表初始化")
            return

        self.cage_list_widget = self.findChild(QListWidget, "cage_list_widget")
        self.detection_status_label = self.findChild(QLabel, "detection_status_label")
        self.right_title = self.findChild(QLabel, "right_title")
        self.config_layout = self.findChild(QVBoxLayout, "content_layout")

        if self.cage_list_widget is None:
            logger.error("cage_list_widget 未找到！")
            return

        self.cage_list_widget.clear()

        # ==================== 断开旧连接，避免重复触发 ====================
        try:
            self.cage_list_widget.itemClicked.disconnect()
        except TypeError:
            pass  # 如果没有连接过，会抛出异常，捕获即可

        # ==================== 使用防抖处理笼子选择 ====================
        self.cage_list_widget.itemClicked.connect(self._on_cage_clicked)

        # 清空之前的状态
        self.cage_enabled_status = {}
        self.groups_status = {}
        self.cage_modules_status = {}
        self.last_warning_group_id = None  # 重置上次警告的ID
        self.last_warning_time = 0  # 重置上次警告的时间

        # 清空响应队列
        with self.response_lock:
            self.group_responses.clear()
            self.pending_requests.clear()

        # 只获取已启用的分组
        if self.experiment_setting.groups:
            enabled_groups = [g for g in self.experiment_setting.groups if g.is_selected == 1]

            for group in enabled_groups:
                group_id = group.id

                # 初始化笼子状态
                self.groups_status[group_id] = {
                    'status': 'waiting_detection',  # 等待检测
                    'response_data': {},
                    'modules_status': {}
                }

                self.cage_modules_status[group_id] = {}

                # 获取该分组下的动物数量
                animal_count = 0
                if self.experiment_setting.animalGroupRecords:
                    animal_count = len([
                        record for record in self.experiment_setting.animalGroupRecords
                        if record.gid == group_id
                    ])

                # 显示已启用笼子的信息
                item_text = f"鼠笼 {group_id} - {group.name} ({animal_count}个动物) - 等待检测..."
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, group_id)
                item.setFlags(Qt.ItemFlag.NoItemFlags)  # 禁用选择
                item.setBackground(QColor(255, 255, 200))  # 黄色背景

                self.cage_list_widget.addItem(item)
                self.cage_enabled_status[group_id] = group

                logger.info(f"已启用笼子: ID={group_id}, Name={group.name}, Animals={animal_count}")
        else:
            logger.warning("没有找到任何已启用的分组")

        if self.detection_status_label:
            self.detection_status_label.setText(f"准备检测 {len(self.cage_enabled_status)} 个笼子...")

    def start_module_detection(self):
        """
        开始检测各鼠笼的所有模块状态
        流程：
        1. 检查是否有已启用的笼子
        2. 初始化每个笼子的模块追踪信息
        3. 逐个向笼子的每个模块发送检测报文（带延迟）
        4. 等待响应（最多N秒）
        5. 显示检测结果
        """
        if not self.cage_enabled_status or len(self.cage_enabled_status) == 0:
            logger.error("没有已启用的笼子，无法开始检测")
            if self.detection_status_label:
                self.detection_status_label.setText("没有已启用的笼子")
            return

        self.detection_in_progress = True
        logger.info(f"{'=' * 80}")
        logger.info(f"开始检测 {len(self.cage_enabled_status)} 个笼子的所有模块...")
        logger.info(f"{'=' * 80}")

        if self.detection_status_label:
            self.detection_status_label.setText(f"正在检测 {len(self.cage_enabled_status)} 个笼子...")

        # ==================== 初始化检测追踪信息 ====================
        self.detecting_groups = {}
        for group_id in self.cage_enabled_status.keys():
            self.detecting_groups[group_id] = {
                'modules_status': {},
                'total_modules': len(ALL_MODULES_TO_DETECT),
                'detected_modules': set(),
            }

            # 为每个模块初始化状态
            for module_name in ALL_MODULES_TO_DETECT.keys():
                self.detecting_groups[group_id]['modules_status'][module_name] = {
                    'status': 'waiting_response',
                    'response_received': False
                }

        # ==================== 逐个笼子发送检测报文 ====================
        for idx, group_id in enumerate(self.cage_enabled_status.keys()):
            # 为每个笼子的所有模块发送检测报文
            for module_idx, (module_name, module_addr) in enumerate(ALL_MODULES_TO_DETECT.items()):
                # 计算延迟：笼子间隔2秒，模块间隔500ms
                delay = (idx * 2000) + (module_idx * 500)

                logger.debug(
                    f"计划在 {delay}ms 后发送笼子 {group_id} 的 {module_name} 检测报文"
                )

                QTimer.singleShot(
                    delay,
                    lambda gid=group_id, mname=module_name, maddr=module_addr:
                    self.send_detection_to_single_module(gid, mname, maddr)
                )

        # ==================== 设置总超时 ====================
        if self.detection_timeout_timer:
            self.detection_timeout_timer.stop()

        self.detection_timeout_timer = QTimer()
        self.detection_timeout_timer.setSingleShot(True)
        self.detection_timeout_timer.timeout.connect(self.finalize_detection)
        self.detection_timeout_timer.start(40000)  # 40秒总超时

        logger.info("检测报文已排队，等待响应...")

    def send_detection_to_single_module(self, group_id, module_name, module_addr):
        """向单个笼子的单个模块发送检测报文"""
        try:
            if group_id not in self.cage_enabled_status:
                logger.warning(f"笼子 {group_id} 不在已启用列表中")
                return

            if group_id not in self.detecting_groups:
                logger.warning(f"笼子 {group_id} 不在检测追踪中")
                return

            module_info = self.detecting_groups[group_id]['modules_status'].get(module_name)
            if not module_info:
                logger.warning(f"笼子 {group_id} 的模块 {module_name} 不在追踪中")
                return

            # 如果已收到响应，跳过重复发送
            if module_info['response_received']:
                logger.debug(f"笼子 {group_id} 的模块 {module_name} 已收到响应，跳过")
                return

            # 清空该模块的旧响应
            with self.response_lock:
                response_key = f"{group_id}_{module_name}"
                if response_key in self.group_responses:
                    del self.group_responses[response_key]
                self.pending_requests.add(response_key)

            # 更新发送计数
            module_info['send_count'] += 1
            send_count = module_info['send_count']
            max_retries = module_info['max_retries']

            logger.info(
                f"向笼子 {group_id} 的模块 {module_name} 发送检测报文 "
                f"(第 {send_count}/{max_retries} 次)"
            )

            # ==================== 构造检测报文 ====================
            # slave_id = 笼子号*16 + 模块地址
            slave_id = group_id * 16 + module_addr

            self.send_message = {
                'port': self.send_message['port'],
                'slave_id': format(slave_id, '02X'),
                'function_code': '03',
                'data': ['00', '00', '00', '04'],
                'group_id': group_id,
                'module_name': module_name,
            }

            # 发送报文
            self.send_data()

            # ==================== 设置模块的超时检查 ====================
            response_key = f"{group_id}_{module_name}"

            if response_key in self.detection_timers and self.detection_timers[response_key]:
                self.detection_timers[response_key].stop()

            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(
                lambda: self.check_module_response_timeout(group_id, module_name)
            )
            timer.start(module_info['timeout'])
            self.detection_timers[response_key] = timer

        except Exception as e:
            logger.error(
                f"向笼子 {group_id} 的模块 {module_name} 发送检测报文出错: {e}",
                exc_info=True
            )

    def check_module_response_timeout(self, group_id, module_name):
        """检查单个模块是否超时"""
        try:
            if group_id not in self.detecting_groups:
                return

            module_info = self.detecting_groups[group_id]['modules_status'].get(module_name)
            if not module_info:
                return

            # 如果已收到响应，则跳过
            if module_info['response_received']:
                logger.debug(f"笼子 {group_id} 的模块 {module_name} 已收到响应")
                return

            # 检查响应队列中是否有该模块的响应
            response_key = f"{group_id}_{module_name}"
            with self.response_lock:
                if response_key in self.group_responses:
                    logger.debug(f"笼子 {group_id} 的模块 {module_name} 有待处理的响应")
                    return

                # 从待处理列表中移除
                self.pending_requests.discard(response_key)

            send_count = module_info['send_count']
            max_retries = module_info['max_retries']

            # 检查是否需要重试
            if send_count < max_retries:
                logger.warning(
                    f"笼子 {group_id} 的模块 {module_name} 响应超时，进行重试 "
                    f"({send_count + 1}/{max_retries})"
                )
                QTimer.singleShot(
                    300,
                    lambda: self.send_detection_to_single_module(
                        group_id, module_name, ALL_MODULES_TO_DETECT[module_name]
                    )
                )
            else:
                logger.error(
                    f"笼子 {group_id} 的模块 {module_name} 多次重试仍无响应，标记为失败"
                )
                module_info['status'] = 'no_response'

                # 检查是否所有笼子的所有模块都已完成（成功或失败）
                self.check_all_responses_received()

        except Exception as e:
            logger.error(
                f"检查模块 {group_id}_{module_name} 超时出错: {e}",
                exc_info=True
            )

    def update_group_activation(self, response_data):
        """
        处理笼子的模块检测响应
        改进：支持多模块检测，每个笼子可能有多个模块响应
        """
        try:
            logger.debug(f"处理响应数据: {response_data}")

            # ==================== 提取响应数据 ====================
            group_id = None
            module_name = None

            if isinstance(response_data, dict):
                if 'group_id' in response_data:
                    group_id = response_data['group_id']
                elif 'slave_id' in response_data:
                    slave_id_int = int(response_data['slave_id'], 16) if isinstance(response_data['slave_id'], str) else \
                    response_data['slave_id']
                    group_id = slave_id_int // 16

                module_name = response_data.get('module_name', 'UNKNOWN')

            if group_id is None or module_name is None:
                logger.warning(f"无法从响应中提取笼子号或模块名: {response_data}")
                return

            logger.info(f"收到笼子 {group_id} 的模块 {module_name} 的响应")

            # ==================== 验证笼子 ====================
            if group_id not in self.cage_enabled_status:
                logger.warning(f"笼子 {group_id} 不在已启用列表中")
                return

            if group_id not in self.detecting_groups:
                logger.warning(f"笼子 {group_id} 不在检测状态中")
                return

            # ==================== 验证模块 ====================
            module_info = self.detecting_groups[group_id]['modules_status'].get(module_name)
            if not module_info:
                logger.warning(f"笼子 {group_id} 的模块 {module_name} 不在追踪中")
                return

            # ==================== 存储响应 ====================
            response_key = f"{group_id}_{module_name}"
            with self.response_lock:
                self.group_responses[response_key] = response_data
                self.pending_requests.discard(response_key)

            # ==================== 更新模块状态 ====================
            module_info['response_received'] = True
            module_info['status'] = 'detected'

            # 停止该模块的超时计时器
            if response_key in self.detection_timers and self.detection_timers[response_key]:
                self.detection_timers[response_key].stop()
                del self.detection_timers[response_key]

            # ==================== 更新检测到的模块集合 ====================
            self.detecting_groups[group_id]['detected_modules'].add(module_name)

            # 初始化笼子的模块状态字典
            if group_id not in self.cage_modules_status:
                self.cage_modules_status[group_id] = {}

            self.cage_modules_status[group_id][module_name] = response_data

            logger.info(
                f"✓ 笼子 {group_id} 的模块 {module_name} 检测成功！ "
                f"已检测模块: {self.detecting_groups[group_id]['detected_modules']}"
            )

            # ==================== 更新UI ====================
            self.update_cage_ui_status(group_id, 'detecting')

            # ==================== 检查检测完成 ====================
            self.check_all_responses_received()

        except Exception as e:
            logger.error(f"处理响应出错: {e}", exc_info=True)

    def update_cage_ui_status(self, group_id, status):
        """更新UI中笼子的显示状态"""
        try:
            if not self.cage_list_widget:
                return

            for i in range(self.cage_list_widget.count()):
                item = self.cage_list_widget.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == group_id:
                    group = self.cage_enabled_status.get(group_id)
                    if not group:
                        return

                    # ==================== 获取动物数量 ====================
                    animal_count = 0
                    if self.experiment_setting and self.experiment_setting.animalGroupRecords:
                        animal_count = len([
                            record for record in self.experiment_setting.animalGroupRecords
                            if record.gid == group_id
                        ])

                    # ==================== 根据状态更新显示 ====================
                    if status == 'waiting_detection':
                        item.setText(
                            f"鼠笼 {group_id} - {group.name} ({animal_count}个动物) - 等待检测..."
                        )
                        item.setFlags(Qt.ItemFlag.NoItemFlags)
                        item.setBackground(QColor(255, 255, 200))  # 黄色

                    elif status == 'detecting':
                        # 正在检测中，显示已检测到的模块
                        detected_modules = self.detecting_groups[group_id]['detected_modules']
                        detected_str = ', '.join(sorted(detected_modules)) if detected_modules else '检测中...'

                        item.setText(
                            f"鼠笼 {group_id} - {group.name} ({animal_count}个动物) - 检测中 ({detected_str})"
                        )
                        item.setFlags(Qt.ItemFlag.NoItemFlags)
                        item.setBackground(QColor(255, 255, 200))  # 黄色

                    elif status == 'ready':
                        # 检测完成，所有必需模块都已就绪
                        detected_modules = self.cage_modules_status.get(group_id, {})
                        detected_str = ', '.join(sorted(detected_modules.keys())) if detected_modules else 'UNKNOWN'

                        item.setText(
                            f"鼠笼 {group_id} - {group.name} ({animal_count}个动物) - 可配置 ({detected_str})"
                        )
                        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                        item.setBackground(QColor(200, 255, 200))  # 绿色
                        self.groups_status[group_id]['status'] = 'ready'

                    elif status == 'incomplete':
                        # 缺少必需模块
                        detected_modules = self.detecting_groups[group_id]['detected_modules']
                        missing_modules = [m for m in REQUIRED_MODULES if m not in detected_modules]

                        item.setText(
                            f"鼠笼 {group_id} - {group.name} ({animal_count}个动物) - "
                            f"配置不完整 (缺: {', '.join(missing_modules)})"
                        )
                        item.setFlags(Qt.ItemFlag.NoItemFlags)
                        item.setBackground(QColor(255, 255, 200))  # 黄色
                        self.groups_status[group_id]['status'] = 'incomplete'

                    elif status == 'no_response':
                        item.setText(
                            f"鼠笼 {group_id} - {group.name} ({animal_count}个动物) - 无响应"
                        )
                        item.setFlags(Qt.ItemFlag.NoItemFlags)
                        item.setBackground(QColor(255, 200, 200))  # 红色
                        self.groups_status[group_id]['status'] = 'no_response'

                    break

        except Exception as e:
            logger.error(f"更新笼子UI状态出错: {e}", exc_info=True)

    def check_all_responses_received(self):
        """检查是否所有笼子的所有必需模块都已收到响应"""
        try:
            all_complete = True

            # ==================== 检查所有笼子的状态 ====================
            for group_id in self.cage_enabled_status.keys():
                if group_id not in self.detecting_groups:
                    all_complete = False
                    break

                detecting_info = self.detecting_groups[group_id]
                module_status = detecting_info['modules_status']

                # ==================== 检查是否有待处理请求 ====================
                with self.response_lock:
                    pending_for_group = [
                        key for key in self.pending_requests
                        if key.startswith(f"{group_id}_")
                    ]

                    if pending_for_group:
                        all_complete = False
                        break

                # ==================== 检查所有模块的完成状态 ====================
                all_modules_done = all(
                    module['response_received'] or module['status'] == 'no_response'
                    for module in module_status.values()
                )

                if not all_modules_done:
                    all_complete = False
                    break

            # ==================== 如果所有检测都完成，提前结束 ====================
            if all_complete and len(self.pending_requests) == 0:
                logger.info("所有模块的检测都已完成，结束检测流程")
                if self.detection_timeout_timer:
                    self.detection_timeout_timer.stop()
                self.finalize_detection()

        except Exception as e:
            logger.error(f"检查响应完成状态出错: {e}", exc_info=True)

    def finalize_detection(self):
        """
        检测完成，显示最终结果并启用配置按钮
        """
        try:
            # ==================== 停止所有计时器 ====================
            if self.detection_timeout_timer:
                self.detection_timeout_timer.stop()

            for timer_key in list(self.detection_timers.keys()):
                if self.detection_timers[timer_key]:
                    self.detection_timers[timer_key].stop()
                    del self.detection_timers[timer_key]

            self.detection_in_progress = False

            logger.info("=" * 100)
            logger.info("全部模块检测完成，汇总结果：")
            logger.info("=" * 100)

            available_count = 0
            unavailable_count = 0
            total_detected_info = []

            # ==================== 更新所有笼子的最终状态 ====================
            for group_id in list(self.cage_enabled_status.keys()):
                if group_id not in self.detecting_groups:
                    continue

                detecting_info = self.detecting_groups[group_id]
                detected_modules = detecting_info['detected_modules']

                # ==================== 检查是否有所有必需模块 ====================
                has_all_required = all(
                    module in detected_modules
                    for module in REQUIRED_MODULES
                )

                group = self.cage_enabled_status[group_id]

                # ==================== 更新笼子状态 ====================
                if has_all_required:
                    self.groups_status[group_id]['status'] = 'ready'
                    self.update_cage_ui_status(group_id, 'ready')
                    available_count += 1

                    status_msg = f"✓ 笼子 {group_id} ({group.name}): 检测到模块 {sorted(detected_modules)}"
                    total_detected_info.append(status_msg)
                    logger.info(status_msg)

                else:
                    self.groups_status[group_id]['status'] = 'incomplete'
                    self.update_cage_ui_status(group_id, 'incomplete')
                    unavailable_count += 1

                    missing = [m for m in REQUIRED_MODULES if m not in detected_modules]
                    status_msg = f"✗ 笼子 {group_id} ({group.name}): 缺少模块 {missing}, 检测到 {sorted(detected_modules)}"
                    total_detected_info.append(status_msg)
                    logger.warning(status_msg)

            # ==================== 更新检测状态标签 ====================
            if self.detection_status_label:
                if available_count > 0:
                    self.detection_status_label.setText(
                        f"✓ 检测完成！{available_count} 个笼子可配置，"
                        f"{unavailable_count} 个笼子模块不完整"
                    )
                else:
                    self.detection_status_label.setText(
                        f"✗ 检测完成！所有笼子模块检测都不完整，请检查硬件连接"
                    )

            # ==================== 启用或禁用配置按钮 ====================
            if self.config_btn:
                if available_count > 0:
                    self.config_btn.setEnabled(True)
                    self.config_btn.setText(f"配置笼子 ({available_count}个可用)")
                    logger.info(f"'配置' 按钮已启用")
                else:
                    self.config_btn.setEnabled(False)
                    self.config_btn.setText("没有可配置的笼子")
                    logger.info(f"'配置' 按钮保持禁用")

            logger.info("=" * 100)
            logger.info("检测流程完成")
            logger.info("=" * 100)

        except Exception as e:
            logger.error(f"最终化检测结果出错: {e}", exc_info=True)

    def show_warning(self, title: str, message: str):
        """显示警告对话框"""
        QMessageBox.warning(self, title, message)

    def show_success(self, title: str, message: str):
        """显示成功对话框"""
        QMessageBox.information(self, title, message)

    def start_device_config(self):
        """确定设备配置按钮"""
        reply = QMessageBox.question(
            self, '确定设备配置',
            "确定该设备配置？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            global_setting.set_setting("app_state", AppState.CONFIGURING)
            if self.main_gui is not None:
                self.main_gui.change_enable_component_app_state_signal.emit()

            vr_value = self.vr_desc_text.value()
            if vr_value:
                global_setting.set_setting("Vr", float(vr_value))

            send_message_queue = global_setting.get_setting("send_message_queue")
            send_message_queue.put(ObjectQueueItem(
                origin='tab_1', to='main_monitor_data', title='set_port',
                data=self.send_message['port'],
                time=time_util.get_format_from_time(time.time())
            ))

            self.close()
            msg_box = InfoDialog(
                title="确定设备配置", info="确定该设备配置成功!",
                icon=QMessageBox.Icon.Information
            )
            msg_box.exec()

            reply_start_experiment = QMessageBox.question(
                self, '开始实验',
                "是否直接开始实验？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply_start_experiment == QMessageBox.StandardButton.Yes:
                self.main_gui.start_experiment()

    def stop_experiment(self):
        """停止实验"""
        if self.main_gui is not None:
            self.main_gui.stop_experiment()

    def refresh_port(self):
        """重新获取端口"""
        self.ports = []
        self._init_data()
        self.init_port_combox()

    def _init_data(self):
        """获取相关数据"""
        self.ports = scan_serial_ports_with_id()

    def update_slider(self, address, mouse_cage_number, function_code, data_lists, slider: QSlider):
        """更新滑块"""
        value = slider.value()

        data_list = ['00', '00', '00', '00']
        if str(value) in data_lists:
            data_list = [hex_str[2:] for hex_str in data_lists[str(value)]['value']]

        self.send_message['data'] = data_list
        if mouse_cage_number == 0:
            self.send_message['slave_id'] = format(address, '02X')
        else:
            self.send_message['slave_id'] = format(address + mouse_cage_number * 16, '02X')
        self.send_message['function_code'] = format(function_code, '02X')
        self.send_message['group_id'] = mouse_cage_number  # 添加笼子号

        self.send_data()

    def update_slider_label(self, value, label):
        """更新滑块标签"""
        label.setText(f"当前值: {value}")

    def on_radio_button_clicked(self, button, address, mouse_cage_number, function_code, data_lists):
        """处理单选按钮点击"""
        btn_object_name: str = button.objectName()
        data_list = ['00', '00', '00', '00']

        if "on" in btn_object_name.lower():
            data_list = [hex_str[2:] for hex_str in data_lists["0"]['value']]
        elif "off" in btn_object_name.lower():
            data_list = [hex_str[2:] for hex_str in data_lists["1"]['value']]

        self.send_message['data'] = data_list
        if mouse_cage_number == 0:
            self.send_message['slave_id'] = format(address, '02X')
        else:
            self.send_message['slave_id'] = format(address + mouse_cage_number * 16, '02X')
        self.send_message['function_code'] = format(function_code, '02X')
        self.send_message['group_id'] = mouse_cage_number  # 添加笼子号

        self.send_data()

    def send_data(self):
        """发送数据"""
        state = global_setting.get_setting("app_state", AppState.INITIALIZED)
        if state is None or state != AppState.MONITORING:
            try:
                if self.send_thread is None:
                    logger.info("初始化串口")
                    self.send_thread = Send_thread(
                        name="tab_1_COM_Send_Thread",
                        modbus=None, send_message=self.send_message
                    )

                    self.send_thread.is_start = True
                    self.send_thread.start()
                    return

                logger.info("使用之前的串口实例化对象")
                self.send_thread.set_send_message(self.send_message)
                self.send_thread.is_start = True
            except Exception as e:
                logger.error(e)
        else:
            message_struct = ObjectQueueItem(
                to="main_monitor_data",
                data=self.send_message,
                origin='tab_1'
            )

            global_setting.get_setting("send_message_queue").put(message_struct)
            logger.debug(f"tab_1开始发送消息:{message_struct}")

    def _on_cage_clicked(self, item):
        """
        鼠笼列表项被点击时触发
        使用防抖延迟处理，避免多次点击导致多次警告
        """
        try:
            if not item:
                return

            group_id = item.data(Qt.ItemDataRole.UserRole)

            # ==================== 防抖：停止之前的计时器 ====================
            if self.cage_selection_timer.isActive():
                self.cage_selection_timer.stop()

            # ==================== 保存待处理的笼子选择，延迟处理 ====================
            self.pending_cage_selection = item
            self.cage_selection_timer.start(200)  # 200ms延迟

            logger.debug(f"鼠笼 {group_id} 点击事件已加入防抖队列")

        except Exception as e:
            logger.error(f"处理笼子点击出错: {e}", exc_info=True)

    def _on_cage_selected_debounced(self):
        """
        防抖处理笼子选择事件
        确保在用户停止点击后才处理，避免重复弹窗
        """
        try:
            if self.pending_cage_selection is None:
                return

            item = self.pending_cage_selection
            self.pending_cage_selection = None

            if not item:
                return

            group_id = item.data(Qt.ItemDataRole.UserRole)

            logger.debug(f"开始处理鼠笼 {group_id} 的选择")

            if group_id not in self.cage_enabled_status:
                logger.warning(f"笼子 {group_id} 不在已启用列表中")
                # 取消选中
                if self.cage_list_widget:
                    self.cage_list_widget.clearSelection()
                return

            status = self.groups_status.get(group_id, {}).get('status', 'unknown')

            logger.info(f"处理笼子选择：ID={group_id}, 状态={status}")

            # ==================== 检查是否可配置 ====================
            if status == 'ready':
                logger.info(f"笼子 {group_id} 可以配置")
                group = self.cage_enabled_status.get(group_id)

                if group and self.right_title:
                    detected_modules = list(self.cage_modules_status.get(group_id, {}).keys())
                    self.right_title.setText(
                        f"鼠笼 {group_id} - {group.name} 配置 ({', '.join(sorted(detected_modules))})"
                    )

                self.load_cage_config(group_id)
            else:
                # ==================== 改为日志记录和UI提示，不弹窗 ====================
                detected_modules = self.detecting_groups.get(group_id, {}).get('detected_modules', set())
                missing_modules = [m for m in REQUIRED_MODULES if m not in detected_modules]

                # 构造错误消息
                message_parts = [
                    f"笼子 {group_id} 缺少以下必需模块，无法配置：",
                    f"缺少的模块: {', '.join(missing_modules)}",
                    f"已检测到的模块: {', '.join(sorted(detected_modules)) if detected_modules else '无'}"
                ]
                error_message = "\n".join(message_parts)

                logger.warning(f"笼子 {group_id} 配置不完整\n{error_message}")

                # ==================== 使用状态栏提示而不是弹窗 ====================
                if self.detection_status_label:
                    self.detection_status_label.setText(
                        f"⚠ 笼子 {group_id} 配置不完整，缺少模块: {', '.join(missing_modules)}"
                    )

                # 取消选中
                if self.cage_list_widget:
                    self.cage_list_widget.clearSelection()

        except Exception as e:
            logger.error(f"防抖处理笼子选择出错: {e}", exc_info=True)
            if self.cage_list_widget:
                self.cage_list_widget.clearSelection()

    def load_cage_config(self, group_num):
        """加载指定鼠笼的配置界面"""
        try:
            self.content_layout: QVBoxLayout = self.findChild(QVBoxLayout, "content_layout")
            if self.content_layout is None:
                logger.error("content_layout 未找到！")
                return

            self.remove_layout_items(self.content_layout)

            self.init_basic_config(self.content_layout)

            response_data = self.groups_status[group_num]['response_data']

            for module_key, module_value in self.config.items():
                if module_key == Modbus_Type.Modbus_Slave_Ids.ENM.value['name']:
                    self.init_enm_config_ui_for_group(module_key, module_value, self.content_layout, group_num)
                elif module_key == Modbus_Type.Modbus_Slave_Ids.EM.value['name']:
                    self.init_em_config_ui_for_group(module_key, module_value, self.content_layout, group_num)
        except Exception as e:
            logger.error(f"加载笼子配置出错: {e}", exc_info=True)

    def remove_layout_items(self, layout):
        """清空布局中的所有控件"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def init_em_config_ui_default(self, module_key, module_value, scroll_area_layout):
        """初始化 EM 配置UI - 默认显示（不含具体鼠笼）"""
        group_box = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][0]['value'][0]['desc']}"
        )
        group_box.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box)

        grid_layout1 = QGridLayout()
        grid_layout1.setContentsMargins(10, 30, 10, 10)
        group_box.setLayout(grid_layout1)

        label = QLabel("选择鼠笼后将显示具体配置")
        label.setStyleSheet("color: #999;")

        radio_on = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['0']['desc']}"
        )
        radio_on.setObjectName("on")
        radio_on.setEnabled(False)
        radio_off = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['1']['desc']}"
        )
        radio_off.setObjectName("off")
        radio_off.setChecked(True)
        radio_off.setEnabled(False)

        grid_layout1.addWidget(label, 0, 0)
        grid_layout1.addWidget(radio_on, 0, 1)
        grid_layout1.addWidget(radio_off, 0, 2)

    def init_em_config_ui_for_group(self, module_key, module_value, scroll_area_layout, group_num):
        """初始化 EM 配置UI（针对特定鼠笼）"""
        group_box = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][0]['value'][0]['desc']}"
        )
        group_box.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box)

        grid_layout1 = QGridLayout()
        grid_layout1.setContentsMargins(10, 30, 10, 10)
        group_box.setLayout(grid_layout1)

        label = QLabel(f"鼠笼 {group_num}")

        radio_on = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['0']['desc']}"
        )
        radio_on.setObjectName("on")
        radio_off = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['1']['desc']}"
        )
        radio_off.setObjectName("off")
        radio_off.setChecked(True)

        button_group = QButtonGroup(grid_layout1)
        button_group.addButton(radio_on)
        button_group.addButton(radio_off)
        button_group.buttonClicked.connect(
            lambda button, address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][0]['function_code'],
                   data_lists=module_value['config'][0]['value'][0]['refer_value']:
            self.on_radio_button_clicked(button, address, mouse_cage_number, function_code, data_lists)
        )

        grid_layout1.addWidget(label, 0, 0)
        grid_layout1.addWidget(radio_on, 0, 1)
        grid_layout1.addWidget(radio_off, 0, 2)

    def init_enm_config_ui_default(self, module_key, module_value, scroll_area_layout):
        """初始化 ENM 配置UI - 默认显示（不含具体鼠笼）"""
        # 第1个 GroupBox
        group_box = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][0]['value'][0]['desc']}"
        )
        group_box.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box)

        grid_layout1 = QGridLayout()
        grid_layout1.setContentsMargins(10, 30, 10, 10)
        group_box.setLayout(grid_layout1)

        label = QLabel("选择鼠笼后将显示具体配置")
        label.setStyleSheet("color: #999;")

        radio_on = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['0']['desc']}"
        )
        radio_on.setObjectName("on")
        radio_on.setEnabled(False)
        radio_off = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['1']['desc']}"
        )
        radio_off.setObjectName("off")
        radio_off.setChecked(True)
        radio_off.setEnabled(False)

        grid_layout1.addWidget(label, 0, 0)
        grid_layout1.addWidget(radio_on, 0, 1)
        grid_layout1.addWidget(radio_off, 0, 2)

        # 第2个 GroupBox
        group_box2 = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][0]['value'][1]['desc']}"
        )
        group_box2.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box2)

        grid_layout2 = QGridLayout()
        grid_layout2.setContentsMargins(10, 30, 10, 10)
        group_box2.setLayout(grid_layout2)

        label = QLabel("选择鼠笼后将显示具体配置")
        label.setStyleSheet("color: #999;")

        radio_on = QRadioButton(
            f"{module_value['config'][0]['value'][1]['refer_value']['0']['desc']}"
        )
        radio_on.setObjectName("on")
        radio_on.setEnabled(False)
        radio_off = QRadioButton(
            f"{module_value['config'][0]['value'][1]['refer_value']['1']['desc']}"
        )
        radio_off.setObjectName("off")
        radio_off.setChecked(True)
        radio_off.setEnabled(False)

        grid_layout2.addWidget(label, 0, 0)
        grid_layout2.addWidget(radio_on, 0, 1)
        grid_layout2.addWidget(radio_off, 0, 2)

        # 第3个 GroupBox（滑块）
        group_box3 = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][1]['value'][0]['desc']}"
        )
        group_box3.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box3)

        grid_layout3 = QGridLayout()
        grid_layout3.setContentsMargins(10, 30, 10, 10)
        group_box3.setLayout(grid_layout3)

        label = QLabel("选择鼠笼后将显示具体配置")
        label.setStyleSheet("color: #999;")
        slider = QSlider()
        slider.setOrientation(Qt.Orientation.Horizontal)
        slider.setMinimum(1)
        slider.setMaximum(9)
        slider.setValue(1)
        slider.setEnabled(False)

        current_value_label = QLabel("当前值: 1")

        grid_layout3.addWidget(label, 0, 0)
        grid_layout3.addWidget(slider, 0, 1)
        grid_layout3.addWidget(current_value_label, 0, 2)

        # 第4个 GroupBox（滑块）
        group_box4 = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][1]['value'][1]['desc']}"
        )
        group_box4.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box4)

        grid_layout4 = QGridLayout()
        grid_layout4.setContentsMargins(10, 30, 10, 10)
        group_box4.setLayout(grid_layout4)

        label = QLabel("选择鼠笼后将显示具体配置")
        label.setStyleSheet("color: #999;")
        slider = QSlider()
        slider.setOrientation(Qt.Orientation.Horizontal)
        slider.setMinimum(1)
        slider.setMaximum(9)
        slider.setValue(1)
        slider.setEnabled(False)

        current_value_label = QLabel("当前值: 1")

        grid_layout4.addWidget(label, 0, 0)
        grid_layout4.addWidget(slider, 0, 1)
        grid_layout4.addWidget(current_value_label, 0, 2)

    def init_enm_config_ui_for_group(self, module_key, module_value, scroll_area_layout, group_num):
        """初始化 ENM 配置UI（针对特定鼠笼）"""
        # 第1个 GroupBox
        group_box = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][0]['value'][0]['desc']}"
        )
        group_box.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box)

        grid_layout1 = QGridLayout()
        grid_layout1.setContentsMargins(10, 30, 10, 10)
        group_box.setLayout(grid_layout1)

        label = QLabel(f"鼠笼 {group_num}")

        radio_on = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['0']['desc']}"
        )
        radio_on.setObjectName("on")
        radio_off = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['1']['desc']}"
        )
        radio_off.setObjectName("off")
        radio_off.setChecked(True)

        button_group = QButtonGroup(grid_layout1)
        button_group.addButton(radio_on)
        button_group.addButton(radio_off)
        button_group.buttonClicked.connect(
            lambda button, address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][0]['function_code'],
                   data_lists=module_value['config'][0]['value'][0]['refer_value']:
            self.on_radio_button_clicked(button, address, mouse_cage_number, function_code, data_lists)
        )

        grid_layout1.addWidget(label, 0, 0)
        grid_layout1.addWidget(radio_on, 0, 1)
        grid_layout1.addWidget(radio_off, 0, 2)

        # 第2个 GroupBox
        group_box2 = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][0]['value'][1]['desc']}"
        )
        group_box2.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box2)

        grid_layout2 = QGridLayout()
        grid_layout2.setContentsMargins(10, 30, 10, 10)
        group_box2.setLayout(grid_layout2)

        label = QLabel(f"鼠笼 {group_num}")

        radio_on = QRadioButton(
            f"{module_value['config'][0]['value'][1]['refer_value']['0']['desc']}"
        )
        radio_on.setObjectName("on")
        radio_off = QRadioButton(
            f"{module_value['config'][0]['value'][1]['refer_value']['1']['desc']}"
        )
        radio_off.setObjectName("off")
        radio_off.setChecked(True)

        button_group = QButtonGroup(grid_layout2)
        button_group.addButton(radio_on)
        button_group.addButton(radio_off)
        button_group.buttonClicked.connect(
            lambda button, address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][0]['function_code'],
                   data_lists=module_value['config'][0]['value'][1]['refer_value']:
            self.on_radio_button_clicked(button, address, mouse_cage_number, function_code, data_lists)
        )

        grid_layout2.addWidget(label, 0, 0)
        grid_layout2.addWidget(radio_on, 0, 1)
        grid_layout2.addWidget(radio_off, 0, 2)

        # 第3个 GroupBox（滑块）
        group_box3 = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][1]['value'][0]['desc']}"
        )
        group_box3.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box3)

        grid_layout3 = QGridLayout()
        grid_layout3.setContentsMargins(10, 30, 10, 10)
        group_box3.setLayout(grid_layout3)

        label = QLabel(f"鼠笼 {group_num}")
        slider = QSlider()
        slider.setOrientation(Qt.Orientation.Horizontal)
        slider.setMinimum(1)
        slider.setMaximum(9)
        slider.setValue(1)

        current_value_label = QLabel("当前值: 1")

        slider.valueChanged.connect(
            lambda value, label=current_value_label: self.update_slider_label(value, label)
        )
        slider.sliderReleased.connect(
            lambda address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][1]['function_code'],
                   data_lists=module_value['config'][1]['value'][0]['refer_value'], slider=slider
            : self.update_slider(address, mouse_cage_number, function_code, data_lists, slider)
        )

        grid_layout3.addWidget(label, 0, 0)
        grid_layout3.addWidget(slider, 0, 1)
        grid_layout3.addWidget(current_value_label, 0, 2)

        # 第4个 GroupBox（滑块）
        group_box4 = QGroupBox(
            f"{module_value['desc']}-{module_value['config'][1]['value'][1]['desc']}"
        )
        group_box4.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(group_box4)

        grid_layout4 = QGridLayout()
        grid_layout4.setContentsMargins(10, 30, 10, 10)
        group_box4.setLayout(grid_layout4)

        label = QLabel(f"鼠笼 {group_num}")
        slider = QSlider()
        slider.setOrientation(Qt.Orientation.Horizontal)
        slider.setMinimum(1)
        slider.setMaximum(9)
        slider.setValue(1)

        current_value_label = QLabel("当前值: 1")

        slider.valueChanged.connect(
            lambda value, label=current_value_label: self.update_slider_label(value, label)
        )
        slider.sliderReleased.connect(
            lambda address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][1]['function_code'],
                   data_lists=module_value['config'][1]['value'][1]['refer_value'], slider=slider
            : self.update_slider(address, mouse_cage_number, function_code, data_lists, slider)
        )

        grid_layout4.addWidget(label, 0, 0)
        grid_layout4.addWidget(slider, 0, 1)
        grid_layout4.addWidget(current_value_label, 0, 2)

    def init_basic_config(self, scroll_area_layout):
        """初始化基本配置"""
        basic_group_box = QGroupBox("基本配置")
        basic_group_box.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(basic_group_box)

        h_layout = QHBoxLayout()
        vr_desc_label = QLabel(
            "请输入Vr值（实际的标定气体，根据气瓶上的标识确定,单位:%,例如20.9%，请输入20.9）："
        )
        self.vr_desc_text = QDoubleSpinBox()
        self.vr_desc_text.setValue(global_setting.get_setting("Vr", 20.9))

        h_layout.addWidget(vr_desc_label)
        h_layout.addWidget(self.vr_desc_text)
        basic_group_box.setLayout(h_layout)