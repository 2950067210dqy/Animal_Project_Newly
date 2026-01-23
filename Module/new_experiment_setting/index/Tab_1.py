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



# ========== 线程相关 ==========

class read_queue_data_Thread(MyQThread):
    """读取队列数据的线程"""

    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.Each_Mouse_Cage_detect_finished_signal: pyqtSignal = None

    def dosomething(self):
        if not self.queue.empty():
            try:
                message: ObjectQueueItem = self.queue.get()
            except Exception as e:
                logger.error(f"{self.name}发生错误{e}")
                return

            if message is not None and isinstance(message, ObjectQueueItem) and message.to == 'New_main_experiment_setting':
                logger.info(f"{self.name}_get_message: {message.title}")
                match message.title:
                    case "Each_Mouse_Cage_detect_finished":
                        """
                        鼠笼内模块解析
                        """
                        if self.Each_Mouse_Cage_detect_finished_signal is not None:
                            self.Each_Mouse_Cage_detect_finished_signal.emit(message.data)
                        # logger.info(f"{self.name}_get_message_datas,{message.data}")
                    case _:
                        pass
            else:
                if message:
                    self.queue.put(message)



read_queue_data_thread = read_queue_data_Thread(name="new_experiment_setting_tab_1_read_queue_data_thread")


# ========== 主窗口 ==========

class Tab_1(ThemedWindow):
    update_group_activation_signal = pyqtSignal(dict)
    Each_Mouse_Cage_detect_finished_signal = pyqtSignal(dict)
    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        """窗口显示事件"""
        logger.warning("tab1——show")

        self._init_customize_ui()
        super().showEvent(a0)

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        """窗口隐藏事件"""
        logger.warning("tab1--hide")

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
                origin='New_main_experiment_setting', to='main_monitor_data', title='set_port',
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
                origin='New_main_experiment_setting', to='main_monitor_data', title='set_port',
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
        self.Each_Mouse_Cage_detect_finished_signal.connect(self.each_Mouse_Cage_detect_update_state)
        global read_queue_data_thread
        read_queue_data_thread.update_group_activation_signal = self.update_group_activation_signal
        read_queue_data_thread.queue = global_setting.get_setting("send_message_queue")
        if read_queue_data_thread is not None and not read_queue_data_thread.isRunning():
            read_queue_data_thread.Each_Mouse_Cage_detect_finished_signal = self.Each_Mouse_Cage_detect_finished_signal
            read_queue_data_thread.start()
    def each_Mouse_Cage_detect_update_state(self,state_data):
        logger.critical(f"TAB1_get_message_datas,{state_data}")
        pass
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
        send_message_queue = global_setting.get_setting("send_message_queue", None)
        if send_message_queue:
            send_message_queue.put(
                ObjectQueueItem(origin="New_main_experiment_setting", to="main_monitor_data", title="start_all_modules_detection",

                                time=time_util.get_format_from_time(time.time())))








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
                missing_modules = []

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