# Module/new_experiment_setting/index/Tab_1.py
import json
import math
import time
import typing
import threading
from pathlib import Path

from PyQt6.QtGui import QDoubleValidator, QColor
from loguru import logger

from Module.new_experiment_setting.config.new_experiment_default_config import get_default_config
from Module.new_experiment_setting.ui.tab1_frame import Ui_tab1_frame
from Service.main_monitor_data import Send_thread
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

# ========== 线程相关 ==========
class read_queue_data_Thread(MyQThread):
    """读取队列数据的线程"""

    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.Each_Mouse_Cage_detect_finished_signal: pyqtSignal = None
        self.Not_Each_Mouse_Cage_detect_finished_signal : pyqtSignal = None

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
                    case "Not_Each_Mouse_Cage_detect_finished":
                        """
                        气路模块解析
                        """
                        if self.Not_Each_Mouse_Cage_detect_finished_signal is not None:
                            self.Not_Each_Mouse_Cage_detect_finished_signal.emit(message.data)
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
    Not_Each_Mouse_Cage_detect_finished_signal = pyqtSignal(dict)

    # ==========初始化相关==========
    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        # ==================== 配置管理相关 ====================
        self.current_cage_config = {}  # 当前笼子的配置缓存
        # 获取用户主目录并创建配置文件夹
        self.user_config_dir = Path.home() / ".mouse_experiment_config" / "cage_configs"
        self.user_config_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"配置文件保存位置: {self.user_config_dir}")
        self.mouse_cage_modules_status = None
        self.reference_modules_status = None

        # ==================== 线程安全相关 ====================
        self.response_lock = threading.Lock()
        self.group_responses = {}
        self.pending_requests = set()
        # 发送报文线程
        self.send_thread: Send_thread = None
        # ==================== 检测相关属性 ====================
        self.port_confirmed = False
        self.detection_in_progress = False
        self.cage_list_to_detect = []  # 待检测的笼子列表
        self.current_detecting_index = 0  # 当前检测的笼子索引
        self.detection_timers = {}  # 单笼子超时计时器
        self.cage_modules_status = {}
        self._cage_list_initialized = False
        self._is_initializing = False
        # 初始化完成笼子集合和完成计时器字典
        self._completed_cages = set()
        self._detection_completion_timers = {}
        # ==================== UI 组件 ====================
        self.port_combox = None
        self.cage_list_widget = None
        self.detection_status_label = None
        self.right_title = None
        self.vr_desc_text: QDoubleSpinBox = None
        self.experiment_setting: Experiment_setting_entity = None

        self.confirm_port_btn = None
        self.config_btn = None
        self.config_layout: QVBoxLayout = None
        self.content_layout: QVBoxLayout = None
        self.start_btn: QPushButton = None

        # ==================== 数据相关 ====================
        self.send_message = {
            'port': '',
            'data': '',
            'slave_id': 0,
            'function_code': 0,
            'timeout': 0,
            'group_id': None
        }

        self.ports = []
        self.config = None
        self.groups_status = {}
        self.selected_group_num = None
        self.cage_enabled_status = {}

        # ==================== 防抖相关 ====================
        self.cage_selection_timer = QTimer()
        self.cage_selection_timer.setSingleShot(True)
        # self.cage_selection_timer.timeout.connect(self._on_cage_selected_debounced)
        self.pending_cage_selection = None
        self.last_warning_group_id = None
        self.last_warning_time = 0

        # ========== 正确的初始化顺序 ==========
        # 1. 设置父窗口
        if parent is not None:
            self.setParent(parent)
            self.setWindowFlags(QtCore.Qt.WindowType.Widget)

        # 2. 初始化UI（这会创建所有UI组件）
        self._init_ui(parent, geometry, title)

        # 3. 立即缓存UI组件（必须在setupUi之后）
        self._cache_ui_components()

        # 4. 获取数据
        self._init_data()

        # 5. 获取实验设置
        self.experiment_setting: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)

        # 6. 获取默认配置
        self.config = get_default_config()

        # 7. 初始化自定义UI
        self._init_customize_ui()

        # 8. 初始化功能
        self._init_function()

        # 9. 加载样式表
        self._init_style_sheet()

        # 10. 设置教程
        self.setup_tutorial()

        # 11. 只在没有parent时自动启动教程
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

    def _cache_ui_components(self):
        """缓存所有 UI 组件 - 必须在 setupUi 之后调用"""
        try:
            # 从UI对象直接获取（最优）
            if hasattr(self.ui, 'cage_list_widget'):
                self.cage_list_widget = self.ui.cage_list_widget
            else:
                self.cage_list_widget = self.findChild(QListWidget, "cage_list_widget")

            if hasattr(self.ui, 'config_scroll_area'):
                self.config_scroll_area = self.ui.config_scroll_area
            else:
                self.config_scroll_area = self.findChild(QScrollArea, "config_scroll_area")

            if hasattr(self.ui, 'content_layout'):
                self.content_layout = self.ui.content_layout
            else:
                # 从scroll area获取
                if self.config_scroll_area:
                    widget = self.config_scroll_area.widget()
                    if widget:
                        self.content_layout = widget.layout()

            if hasattr(self.ui, 'tab_1_port_combox'):
                self.port_combox = self.ui.tab_1_port_combox
            else:
                self.port_combox = self.findChild(QComboBox, "tab_1_port_combox")

            if hasattr(self.ui, 'tab_1_confirm_port_btn'):
                self.confirm_port_btn = self.ui.tab_1_confirm_port_btn
            else:
                self.confirm_port_btn = self.findChild(QPushButton, "tab_1_confirm_port_btn")

            if hasattr(self.ui, 'start_btn'):
                self.start_btn = self.ui.start_btn
            else:
                self.start_btn = self.findChild(QPushButton, "start_btn")

            # 通过 findChild 查找的组件
            self.right_title = self.findChild(QLabel, "right_title_label")
            self.detection_status_label = self.findChild(QLabel, "detection_status_label")
            self.config_btn = self.findChild(QPushButton, "config_btn")

            logger.info("✓ 所有UI组件已缓存")

        except Exception as e:
            logger.error(f"缓存UI组件失败: {e}", exc_info=True)

    # 获得相关数据
    def _init_data(self):
        # 获得下拉框数据
        self.ports = scan_serial_ports_with_id()
        pass

    def _init_customize_ui(self):
        """初始化自定义UI"""
        # 确保experiment_setting已被加载
        if self.experiment_setting is None:
            self.experiment_setting = global_setting.get_setting("experiment_setting", None)
            logger.warning(f"experiment_setting 状态: {self.experiment_setting is not None}")

        self.init_port_combox()
        self.config = get_default_config()

        # 延迟初始化，确保UI完全渲染
        QTimer.singleShot(200, self.init_cage_list)

        self.init_config_ui()
        super()._init_customize_ui()

    def _init_function(self):
        """初始化功能"""
        self.init_btn_func()

        # 连接信号到槽
        self.Each_Mouse_Cage_detect_finished_signal.connect(self.each_Mouse_Cage_detect_update_state)
        self.Not_Each_Mouse_Cage_detect_finished_signal.connect(self.not_each_Mouse_Cage_detect_update_state)

        # 配置全局读队列线程
        global read_queue_data_thread

        if read_queue_data_thread is not None:
            # 只设置一次，设置前检查线程是否已运行
            if not read_queue_data_thread.isRunning():
                # 设置队列
                read_queue_data_thread.queue = global_setting.get_setting("send_message_queue")

                # 设置两个信号
                read_queue_data_thread.Each_Mouse_Cage_detect_finished_signal = self.Each_Mouse_Cage_detect_finished_signal
                read_queue_data_thread.Not_Each_Mouse_Cage_detect_finished_signal = self.Not_Each_Mouse_Cage_detect_finished_signal

                # 设置其他必要属性
                read_queue_data_thread.update_group_activation_signal = self.update_group_activation_signal

                # 启动线程
                read_queue_data_thread.start()
            else:
                logger.warning("读队列线程已在运行，跳过启动")
        else:
            logger.error("read_queue_data_thread 为 None")


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

    # ==========UI初始化相关==========
    def init_port_combox(self):
        """初始化端口下拉框"""
        # 直接使用缓存的对象
        if self.port_combox is None:
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

    def init_cage_list(self):
        """初始化鼠笼列表（已启用的笼子）"""
        # ==================== 确保 experiment_setting 已加载 ====================
        if self.experiment_setting is None:
            self.experiment_setting = global_setting.get_setting("experiment_setting", None)
            logger.warning(f"experiment_setting 状态: {self.experiment_setting is not None}")

        # 如果仍为None，说明还没加载，直接返回
        if self.experiment_setting is None:
            logger.error("experiment_setting 仍未加载，无法初始化笼子列表")
            return

        if self.cage_list_widget is None:
            logger.error("cage_list_widget 为 None")
            return

        # 一次性清空所有状态
        self.cage_list_widget.clear()
        self.cage_enabled_status.clear()
        self.groups_status.clear()
        self.cage_modules_status.clear()
        # global_setting.set_setting("mouse_cage_detect_state_dict", {})


        try:
            self.cage_list_widget.itemClicked.disconnect()
        except TypeError:
            pass
        self.cage_list_widget.itemClicked.connect(self._on_cage_clicked)

        cage_added_count = 0
        if self.experiment_setting.groups:
            enabled_groups = [g for g in self.experiment_setting.groups if g.is_selected == 1]

            for group in enabled_groups:
                group_id = group.id

                # 初始化状态字典
                self.groups_status[group_id] = {
                    'status': 'waiting_detection',
                    'response_data': {},
                    'modules_status': {}
                }
                self.cage_modules_status[group_id] = {}

                # 获取动物数量
                animal_count = len([
                    r for r in (self.experiment_setting.animalGroupRecords or [])
                    if r.gid == group_id
                ])

                # 添加到列表
                item_text = f"鼠笼 {group_id} - {group.name} ({animal_count}个动物) - 待检测"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, group_id)
                item.setFlags(Qt.ItemFlag.NoItemFlags)

                self.cage_list_widget.addItem(item)
                self.cage_enabled_status[group_id] = group
                cage_added_count += 1

                # logger.info(f"已添加笼子: ID={group_id}, Name={group.name}")

         # 标记初始化完成
        self._cage_list_initialized = True
        # logger.critical(f"_cage_list_initialized 已设置为 True")
        # logger.info(f"笼子列表初始化完成: 添加 {cage_added_count} 个笼子")

    def init_config_ui(self):
        """初始化配置UI - 显示默认配置"""
        if self.experiment_setting is None:
            self.experiment_setting: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)
            # 直接使用缓存的对象
        if self.content_layout is None:
            logger.error("content_layout 未找到！")
            return

        self.remove_layout_items(self.content_layout)
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
            # self.scroll_area_layout.addStretch()

            self.scroll_area.setWidget(self.scroll_area_content)
            self.config_layout.addWidget(self.scroll_area, 1)

    def init_basic_config(self, scroll_area_layout):
        """初始化基本配置"""
        basic_group_box = QGroupBox("基本配置")
        basic_group_box.setContentsMargins(5, 5, 5, 5)
        basic_group_box.setMinimumHeight(80)
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

    def init_btn_func(self):
        """初始化按钮功能"""
        # 刷新端口按钮
        refresh_port_btn: QPushButton = self.findChild(QPushButton, "tab_1_refresh_port_btn")
        if refresh_port_btn:
            refresh_port_btn.clicked.connect(self.refresh_port)

        # 直接使用缓存的对象
        if self.confirm_port_btn:
            self.confirm_port_btn.clicked.connect(self.confirm_port)
            self.confirm_port_btn.setEnabled(True)

        # 配置按钮（初始禁用）
        self.config_btn: QPushButton = self.findChild(QPushButton, "config_btn")
        if self.config_btn:
            self.config_btn.clicked.connect(self.start_device_config)
            self.config_btn.setEnabled(False)

        # 直接使用缓存的对象
        if self.start_btn:
            self.start_btn.clicked.connect(self.start_device_config)


    # ==========配置UI创建==========
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

    def init_em_config_ui_for_group(self, module_key, module_value, scroll_area_layout, group_num, saved_config=None):
        """初始化 EM 配置UI（针对特定鼠笼）"""
        if saved_config is None:
            saved_config = {}

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

        # ==================== 新增：从保存的配置恢复状态 ====================
        saved_value = saved_config.get('config_0', 'off')
        if saved_value == 'on':
            radio_on.setChecked(True)
        else:
            radio_off.setChecked(True)

        button_group = QButtonGroup(grid_layout1)
        button_group.addButton(radio_on)
        button_group.addButton(radio_off)
        button_group.buttonClicked.connect(
            lambda button, address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][0]['function_code'],
                   data_lists=module_value['config'][0]['value'][0]['refer_value'],
                   config_key='EM_config_0':
            self.on_radio_button_clicked(button, address, mouse_cage_number, function_code, data_lists, config_key)
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
        group_box.setContentsMargins(5, 5, 5, 5)
        group_box.setMinimumHeight(70)
        group_box.setMaximumHeight(100)
        scroll_area_layout.addWidget(group_box)

        grid_layout1 = QGridLayout()
        grid_layout1.setContentsMargins(5, 10, 5, 5)
        grid_layout1.setSpacing(5)
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
    def init_enm_config_ui_for_group(self, module_key, module_value, scroll_area_layout, group_num, saved_config=None):
        """初始化 ENM 配置UI（针对特定鼠笼）- 支持配置加载"""
        if saved_config is None:
            saved_config = {}

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

        # ==================== 从保存的配置恢复状态 ====================
        saved_value = saved_config.get('config_0_value_0', 'off')
        if saved_value == 'on':
            radio_on.setChecked(True)
        else:
            radio_off.setChecked(True)

        button_group = QButtonGroup(grid_layout1)
        button_group.addButton(radio_on)
        button_group.addButton(radio_off)
        button_group.buttonClicked.connect(
            lambda button, address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][0]['function_code'],
                   data_lists=module_value['config'][0]['value'][0]['refer_value'],
                   config_key='ENM_config_0_value_0':
            self.on_radio_button_clicked(button, address, mouse_cage_number, function_code, data_lists, config_key)
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

        # ==================== 从保存的配置恢复状态 ====================
        saved_value = saved_config.get('config_0_value_1', 'off')
        if saved_value == 'on':
            radio_on.setChecked(True)
        else:
            radio_off.setChecked(True)

        button_group = QButtonGroup(grid_layout2)
        button_group.addButton(radio_on)
        button_group.addButton(radio_off)
        button_group.buttonClicked.connect(
            lambda button, address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][0]['function_code'],
                   data_lists=module_value['config'][0]['value'][1]['refer_value'],
                   config_key='ENM_config_0_value_1':
            self.on_radio_button_clicked(button, address, mouse_cage_number, function_code, data_lists, config_key)
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

        # ==================== 从保存的配置恢复滑块值 ====================
        saved_slider_value = saved_config.get('config_1_value_0', 1)
        try:
            slider.setValue(int(saved_slider_value))
        except (ValueError, TypeError):
            slider.setValue(1)

        current_value_label = QLabel(f"当前值: {slider.value()}")

        slider.valueChanged.connect(
            lambda value, label=current_value_label: self.update_slider_label(value, label)
        )
        slider.sliderReleased.connect(
            lambda address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][1]['function_code'],
                   data_lists=module_value['config'][1]['value'][0]['refer_value'],
                   slider=slider, config_key='ENM_config_1_value_0':
            self.update_slider(address, mouse_cage_number, function_code, data_lists, slider, config_key)
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

        # ==================== 从保存的配置恢复滑块值 ====================
        saved_slider_value = saved_config.get('config_1_value_1', 1)
        try:
            slider.setValue(int(saved_slider_value))
        except (ValueError, TypeError):
            slider.setValue(1)

        current_value_label = QLabel(f"当前值: {slider.value()}")

        slider.valueChanged.connect(
            lambda value, label=current_value_label: self.update_slider_label(value, label)
        )
        slider.sliderReleased.connect(
            lambda address=module_value['address'], mouse_cage_number=group_num,
                   function_code=module_value['config'][1]['function_code'],
                   data_lists=module_value['config'][1]['value'][1]['refer_value'],
                   slider=slider, config_key='ENM_config_1_value_1':
            self.update_slider(address, mouse_cage_number, function_code, data_lists, slider, config_key)
        )

        grid_layout4.addWidget(label, 0, 0)
        grid_layout4.addWidget(slider, 0, 1)
        grid_layout4.addWidget(current_value_label, 0, 2)



    # ==========事件处理==========
    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        """窗口显示事件"""
        logger.warning("tab1——show")

        self._init_customize_ui()
        super().showEvent(a0)

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        """窗口隐藏事件"""
        logger.warning("tab1--hide")

        super().hideEvent(a0)

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

            # logger.debug(f"鼠笼 {group_id} 点击事件已加入防抖队列")

        except Exception as e:
            logger.error(f"处理笼子点击出错: {e}", exc_info=True)

    def _on_cage_selected_debounced(self):
        """
        防抖处理笼子选择事件
        只有检测通过(overall_valid=True)的鼠笼才能被配置
        """
        try:
            if self.pending_cage_selection is None:
                return

            item = self.pending_cage_selection
            group_id = item.data(Qt.ItemDataRole.UserRole)

            # logger.info(f"处理笼子选择: {group_id}")

            # 获取检测状态
            mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})

            if group_id not in mouse_cage_detect_dict:
                logger.warning(f"笼子 {group_id} 未在检测字典中")
                self.show_warning("错误", "笼子还未进行检测，请稍候...")
                return

            cage_data = mouse_cage_detect_dict[group_id]

            # ==================== 获取预期模块列表 ====================
            expected_modules = self._get_expected_modules()
            expected_module_count = len(expected_modules)

            cage_modules = cage_data.get('cage_modules', {})
            air_modules = cage_data.get('air_modules', {})

            # 合并所有收到的模块
            received_modules = list(cage_modules.keys()) + list(air_modules.keys())
            received_module_count = len(received_modules)

            logger.info(f"笼子 {group_id} 检测统计:")
            logger.info(f"  已收到模块数: {received_module_count}")
            logger.info(f"  已收到: {received_modules}")

            # ==================== 检查是否所有模块都已检测 ====================
            # 动态判断是否收到了足够的模块
            min_required_modules = max(expected_module_count, 7)  # 至少需要7个模块
            all_modules_detected = received_module_count >= min_required_modules

            if not all_modules_detected:
                logger.warning(
                    f"笼子 {group_id} 还未完成所有模块的检测。"
                    f"已收到: {received_module_count}/{min_required_modules} 个模块"
                )
                self.show_warning(
                    "检测进行中",
                    f"笼子 {group_id} 的检测还未完成。\n\n"
                    f"已检测: {received_module_count} 个模块\n"
                    f"至少需要: {min_required_modules} 个模块\n\n"
                    f"请耐心等待检测完成。"
                )
                return

            # ==================== 所有模块都已检测，判断检测结果 ====================
            overall_valid = cage_data.get('overall_valid', False)

            # ==================== 检查是否可以进入配置 ====================
            if not overall_valid:
                # 收集失败的模块信息
                missing_modules = []
                failed_details = []

                cage_is_valid = cage_data.get('cage_is_valid', False)
                air_is_valid = cage_data.get('air_is_valid', False)

                # 收集失败的笼内模块
                if not cage_is_valid and cage_modules:
                    failed_cage_modules = [
                        name for name, status in cage_modules.items() if not status
                    ]
                    if failed_cage_modules:
                        missing_modules.extend(failed_cage_modules)
                        for module_name in failed_cage_modules:
                            failed_details.append(f"  • {module_name} (笼内模块) - ✗ 失败")

                # 收集失败的气路模块
                if not air_is_valid and air_modules:
                    failed_air_modules = [
                        name for name, status in air_modules.items() if not status
                    ]
                    if failed_air_modules:
                        missing_modules.extend(failed_air_modules)
                        for module_name in failed_air_modules:
                            failed_details.append(f"  • {module_name} (气路模块) - ✗ 失败")

                # 防止同一笼子频繁弹窗（5秒内只弹一次）
                current_time = time.time()
                if (self.last_warning_group_id != group_id or
                        current_time - self.last_warning_time > 5):
                    failed_info = "\n".join(failed_details) if failed_details else "未知模块失败"

                    self.show_warning(
                        "检测未通过",
                        f"笼子 {group_id} 检测异常\n\n"
                        f"已检测模块: {received_module_count}/{min_required_modules}\n\n"
                        f"失败的模块:\n{failed_info}\n\n"
                        f"请检查以上模块的连接状态，然后重新进行检测。"
                    )

                    self.last_warning_group_id = group_id
                    self.last_warning_time = current_time

                logger.warning(f"笼子 {group_id} 检测未通过，无法进入配置")
                return

            # ==================== 检测通过，进入配置 ====================
            # logger.info(f"✓ 笼子 {group_id} 所有 {received_module_count} 个模块检测通过，进入配置界面")

            self.selected_group_num = group_id
            self.load_cage_config(group_id)

            # 更新右侧标题
            if self.right_title:
                group = self.cage_enabled_status.get(group_id)
                if group:
                    self.right_title.setText(f"配置: 鼠笼 {group_id} - {group.name}")

            self.pending_cage_selection = None

        except Exception as e:
            logger.error(f"防抖处理笼子选择出错: {e}", exc_info=True)
            self.pending_cage_selection = None

    # ==========检测流程==========
    def confirm_port(self):
        """确认串口并开始检测"""
        if not self.port_combox or self.port_combox.currentIndex() < 0:
            self.show_warning("错误", "请先选择有效的串口")
            return

        # ==================== 关键：确保 experiment_setting 已加载 ====================
        if self.experiment_setting is None:
            self.experiment_setting = global_setting.get_setting("experiment_setting", None)
            if self.experiment_setting is None:
                self.show_warning("错误", "实验设置未加载，请稍候...")
                return

        self.send_message['port'] = self.ports[self.port_combox.currentIndex()]['device']
        self.port_confirmed = True

        # 禁用串口相关控件
        self.port_combox.setEnabled(False)
        if self.confirm_port_btn:
            self.confirm_port_btn.setEnabled(False)
            self.confirm_port_btn.setText("串口已确认")

        refresh_port_btn = self.findChild(QPushButton, "tab_1_refresh_port_btn")
        if refresh_port_btn:
            refresh_port_btn.setEnabled(False)

        if self.config_btn:
            self.config_btn.setEnabled(False)

        # 重置已完成笼子集合
        self._completed_cages = set()
        self._detection_completion_timers = {}

        # 先初始化列表，再开始检测
        self.init_cage_list()

        # 确保初始化完成后再开始检测
        if self._cage_list_initialized and self.cage_list_widget and self.cage_list_widget.count() > 0:
            # logger.info(f"开始检测 {self.cage_list_widget.count()} 个笼子...")
            QTimer.singleShot(50, self.start_module_detection)
        else:
            self.show_warning("初始化失败", f"没有找到已启用的笼子或初始化失败\n"
                                            f"cage_enabled_status: {len(self.cage_enabled_status)}\n"
                                            f"_cage_list_initialized: {self._cage_list_initialized}")
            logger.error(f"初始化失败: _cage_list_initialized={self._cage_list_initialized}, "
                         f"cage_enabled_status={self.cage_enabled_status}")

    def start_module_detection(self):
        """
        逐个笼子检测（串行）
        """
        if not self.cage_enabled_status or len(self.cage_enabled_status) == 0:
            logger.error("没有已启用的笼子，无法开始检测")
            if self.detection_status_label:
                self.detection_status_label.setText("错误：没有已启用的笼子")
            return

        self.detection_in_progress = True

        # 获取笼子ID列表
        self.cage_list_to_detect = list(self.cage_enabled_status.keys())
        self.current_detecting_index = 0

        if self.detection_status_label:
            self.detection_status_label.setText(
                f"检测中：正在检测 {len(self.cage_list_to_detect)} 个笼子..."
            )

        # logger.info(f"{'=' * 80}")
        # logger.info(f"开始逐个检测 {len(self.cage_list_to_detect)} 个笼子...")
        # logger.info(f"笼子顺序: {self.cage_list_to_detect}")
        # logger.info(f"{'=' * 80}")

        # 启动第一个笼子的检测
        self._detect_next_cage()

    def _detect_next_cage(self):
        """检测下一个笼子"""

        # ==================== 诊断信息 ====================
        logger.critical(
            f"[_detect_next_cage] 被调用\n"
            f"  current_detecting_index: {self.current_detecting_index}\n"
            f"  total_cages: {len(self.cage_list_to_detect)}\n"
            f"  detection_in_progress: {self.detection_in_progress}"
        )

        # ==================== 检查是否所有笼子都已检测 ====================
        if self.current_detecting_index >= len(self.cage_list_to_detect):
            # logger.critical(
            #     f"[完成] 所有 {len(self.cage_list_to_detect)} 个笼子已检测完成！"
            # )

            # 确保清理所有计时器
            self._cleanup_all_timers()

            # 更新全局状态
            self.detection_in_progress = False

            # 更新状态标签
            if self.detection_status_label:
                self.detection_status_label.setText("✓ 检测完成！请选择笼子进行配置")

            logger.critical("[检测流程] 正式结束")
            return

        # ==================== 检测被用户手动停止 ====================
        if not self.detection_in_progress:
            logger.warning(f"[中止] 用户已停止检测")
            self._cleanup_all_timers()
            return

        # ==================== 获取下一个笼子 ====================
        cage_number = self.cage_list_to_detect[self.current_detecting_index]
        self.current_detecting_index += 1

        total_cages = len(self.cage_list_to_detect)
        current_position = self.current_detecting_index

        # logger.info(f"\n{'─' * 80}")
        # logger.info(f"开始检测笼子 {cage_number} ({current_position}/{total_cages})")
        # logger.info(f"{'─' * 80}\n")

        # 更新UI为"检测中"
        self.update_cage_display_to_detecting(cage_number)

        # 发送检测命令
        send_message_queue = global_setting.get_setting("send_message_queue", None)
        if send_message_queue:
            send_message_queue.put(
                ObjectQueueItem(
                    origin="New_main_experiment_setting",
                    to="main_monitor_data",
                    title="start_all_modules_detection",
                    data={'gids': [cage_number]},
                    time=time_util.get_format_from_time(time.time())
                )
            )

        # 设置检测超时（10秒）
        self._set_cage_detection_timeout(cage_number)

    def _set_cage_detection_timeout(self, cage_number, timeout_seconds=10):
        """为单个笼子设置检测超时"""
        if cage_number in self.detection_timers:
            self.detection_timers[cage_number].stop()

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._on_cage_detection_timeout(cage_number))
        timer.start(timeout_seconds * 1000)

        self.detection_timers[cage_number] = timer
        # logger.info(f"笼子 {cage_number} 检测超时设置: {timeout_seconds}秒")

    def _on_cage_detection_timeout(self, cage_number):
        """
        检测超时处理 - 笼子检测10秒没有响应
        """
        logger.warning(f"[10秒超时] 笼子 {cage_number} 检测超时（10秒无响应）")

        # 清理该笼子的计时器
        if cage_number in self.detection_timers:
            timer = self.detection_timers.pop(cage_number)
            if timer.isActive():
                timer.stop()

        # 清理该笼子的3秒完成计时器
        if hasattr(self, '_detection_completion_timers'):
            if cage_number in self._detection_completion_timers:
                timer_data = self._detection_completion_timers.pop(cage_number, {})
                timer = timer_data.get('timer')
                if timer and timer.isActive():
                    timer.stop()

        # ==================== 标记为已完成 ====================
        if not hasattr(self, '_completed_cages'):
            self._completed_cages = set()

        if cage_number not in self._completed_cages:
            self._completed_cages.add(cage_number)
            logger.warning(f"笼 {cage_number} 超时，强制标记为已完成")

            # 更新UI为异常状态
            self._update_cage_detection_complete(cage_number)

        # ==================== 推进流程（即使是超时也要继续）====================
        # logger.info(f"笼 {cage_number} 超时完毕，推进到下一个笼子")
        QTimer.singleShot(300, self._detect_next_cage)

    def _cleanup_all_timers(self):
        """清理所有计时器"""
        # 清理检测超时计时器
        if self.detection_timers:
            count = 0
            for cage_num in list(self.detection_timers.keys()):
                timer = self.detection_timers.pop(cage_num, None)
                if timer and timer.isActive():
                    timer.stop()
                    count += 1
            if count > 0:
                # logger.info(f"  已停止 {count} 个超时计时器")
                pass

        # 清理完成检测计时器
        if hasattr(self, '_detection_completion_timers') and self._detection_completion_timers:
            count = 0
            for cage_num in list(self._detection_completion_timers.keys()):
                data = self._detection_completion_timers.pop(cage_num, {})
                timer = data.get('timer')
                if timer and timer.isActive():
                    timer.stop()
                    count += 1
            if count > 0:
                # logger.info(f"  已停止 {count} 个完成计时器")
                pass



    def _check_detection_complete(self, cage_number):
        """
        检查该笼子是否完成检测
        3秒内没有新模块到达则认为检测完成
        """
        try:
            mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})

            if cage_number not in mouse_cage_detect_dict:
                logger.warning(f"笼 {cage_number} 不在检测字典中")
                return

            cage_data = mouse_cage_detect_dict[cage_number]
            cage_modules = cage_data.get('cage_modules', {})
            air_modules = cage_data.get('air_modules', {})
            total_modules = len(cage_modules) + len(air_modules)

            # logger.critical(
            #     f"笼 {cage_number} 实时模块收集进度:\n"
            #     f"笼内模块: {list(cage_modules.keys())} (共{len(cage_modules)}个)\n"
            #     f"气路模块: {list(air_modules.keys())} (共{len(air_modules)}个)\n"
            #     f"总计: {total_modules} 个模块\n"
            #     f"检测结果: {'通过' if cage_data.get('overall_valid') else '✗ 异常'}"
            # )

            # ==================== 没有收到任何模块，不启动计时器 ====================
            if total_modules == 0:
                # logger.debug(f"笼 {cage_number} 还未收到任何模块，不启动计时器")
                return

            # ==================== 初始化计时器字典 ====================
            if not hasattr(self, '_detection_completion_timers'):
                self._detection_completion_timers = {}

            # ==================== 如果该笼子的计时器不存在，创建一个新的 ====================
            if cage_number not in self._detection_completion_timers:
                # logger.info(f"笼 {cage_number} 启动完成检测计时器（3秒等待期）")

                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(lambda: self._on_cage_detection_wait_timeout(cage_number))
                timer.start(3000)  # 3秒等待

                self._detection_completion_timers[cage_number] = {
                    'timer': timer,
                    'last_module_count': total_modules,
                    'last_update_time': time.time()
                }
            else:
                # ==================== 计时器已存在，检查是否有新模块到达 ====================
                timer_data = self._detection_completion_timers[cage_number]
                last_count = timer_data['last_module_count']

                if total_modules > last_count:
                    # 有新模块到达，重启计时器
                    logger.info(f"笼 {cage_number} 有新模块到达 ({last_count}→{total_modules})，重启计时器")
                    old_timer = timer_data['timer']
                    old_timer.stop()

                    timer = QTimer()
                    timer.setSingleShot(True)
                    timer.timeout.connect(lambda: self._on_cage_detection_wait_timeout(cage_number))
                    timer.start(3000)  # 再等3秒

                    self._detection_completion_timers[cage_number] = {
                        'timer': timer,
                        'last_module_count': total_modules,
                        'last_update_time': time.time()
                    }
                else:
                    # 没有新模块，继续等待
                    # logger.debug(
                    #     f"笼 {cage_number} 无新模块，继续等待（已等待 {time.time() - timer_data['last_update_time']:.1f}s）")
                    pass

        except Exception as e:
            logger.error(f"检查检测完成时出错: {e}", exc_info=True)

    def _on_cage_detection_wait_timeout(self, cage_number):
        """
        3秒等待超时，没有新模块到达，认为检测完成
        """
        try:
            if not hasattr(self, '_detection_completion_timers'):
                return

            if cage_number not in self._detection_completion_timers:
                logger.warning(f"笼 {cage_number} 的计时器已被清除")
                return

            # 清除该笼子的完成计时器
            del self._detection_completion_timers[cage_number]

            mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})

            if cage_number not in mouse_cage_detect_dict:
                logger.error(f"笼 {cage_number} 不在检测字典中")
                return

            cage_data = mouse_cage_detect_dict[cage_number]
            cage_modules = cage_data.get('cage_modules', {})
            air_modules = cage_data.get('air_modules', {})
            total_modules = len(cage_modules) + len(air_modules)

            # logger.critical(
            #     f"[3秒超时触发] 笼 {cage_number} 等待期满\n"
            #     f"  最终模块数: {total_modules}\n"
            #     f"  笼内: {list(cage_modules.keys())}\n"
            #     f"  气路: {list(air_modules.keys())}"
            # )

            # ==================== 防止重复处理 ====================
            if not hasattr(self, '_completed_cages'):
                self._completed_cages = set()

            if cage_number in self._completed_cages:
                logger.warning(f"笼 {cage_number} 已处理过，跳过")
                return

            self._completed_cages.add(cage_number)
            # logger.critical(f"[完成标记] 已完成笼子: {self._completed_cages}")

            # ==================== 更新UI为"检测完成"状态 ====================
            self._update_cage_detection_complete(cage_number)

            # ==================== 关键修复：无论什么状态，都推进到下一个笼子 ====================
            # 这样做是为了确保流程不会卡住
            # logger.info(f"笼 {cage_number} 检测完成，推进流程...")
            QTimer.singleShot(300, self._detect_next_cage)

        except Exception as e:
            logger.error(f"检测等待超时处理出错: {e}", exc_info=True)

    def _update_cage_detection_complete(self, cage_number):
        """
        更新笼子UI为"检测完成"状态
        """
        try:
            cage_list_widget = self._get_cage_list_widget()
            if not cage_list_widget:
                return

            # ========== 如果列表为空，重新初始化 ==========
            if cage_list_widget.count() == 0:
                logger.warning(f"列表为空，重新初始化...")
                self.init_cage_list()
                if cage_list_widget.count() == 0:
                    logger.error("重新初始化后列表仍为空")
                    return

            # 找到对应的笼子项
            for i in range(cage_list_widget.count()):
                item = cage_list_widget.item(i)
                if not item or item.data(Qt.ItemDataRole.UserRole) != cage_number:
                    continue

                group = self.cage_enabled_status.get(cage_number)
                if not group:
                    continue

                animal_count = 0
                if self.experiment_setting and self.experiment_setting.animalGroupRecords:
                    animal_count = len([
                        r for r in self.experiment_setting.animalGroupRecords
                        if r.gid == cage_number
                    ])

                # 获取检测数据
                mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})
                cage_data = mouse_cage_detect_dict.get(cage_number, {})
                overall_valid = cage_data.get('overall_valid', False)

                # 根据检测结果显示相应的状态
                if overall_valid:
                    status_text = "✓ 检测完成（可配置）"
                    # 使能该项，允许点击
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                else:
                    status_text = "✗ 检测异常（无法配置）"
                    # 禁用该项
                    item.setFlags(Qt.ItemFlag.NoItemFlags)

                item_text = f"鼠笼 {cage_number} - {group.name} ({animal_count}个动物) - {status_text}"
                item.setText(item_text)

                # logger.info(f"✓ 笼 {cage_number} UI 已更新为: {status_text}")
                cage_list_widget.viewport().update()
                cage_list_widget.repaint()
                break

        except Exception as e:
            logger.error(f"更新笼 {cage_number} 完成状态失败: {e}", exc_info=True)

    def _get_expected_modules(self):
        """获取所有预期需要检测的模块列表"""
        expected_modules = []

        try:
            if self.config:
                for module_key, module_value in self.config.items():
                    if isinstance(module_value, dict):
                        module_name = module_value.get('desc', module_key)
                        expected_modules.append(module_name)
                        logger.debug(f"添加预期模块: {module_name}")

            # logger.info(f"预期模块总数: {len(expected_modules)}, 列表: {expected_modules}")

        except Exception as e:
            logger.error(f"获取预期模块列表失败: {e}")
            # 如果配置读取失败，返回默认的最小模块数量要求
            expected_modules = ["默认模块"] * 7

        return expected_modules



    # ==========状态更新==========
    def each_Mouse_Cage_detect_update_state(self, state_data):
        """更新鼠笼内模块检测状态"""
        logger.critical(f"TAB1_each_Mouse_Cage_detect_update_state: {state_data}")

        mouse_cage_number = state_data.get('mouse_cage_number')
        response_state = state_data.get('response_state', False)
        module_name = state_data.get('module_name', 'UNKNOWN')

        if mouse_cage_number is None:
            logger.error(f"缺少 mouse_cage_number 信息")
            return

        # 获取或创建全局检测字典
        mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})

        # 初始化该鼠笼的检测数据（初始值应该为 False，表示还没开始检测）
        if mouse_cage_number not in mouse_cage_detect_dict:
            mouse_cage_detect_dict[mouse_cage_number] = {
                'cage_states': [],
                'air_states': [],
                'cage_modules': {},
                'air_modules': {},
                'cage_is_valid': False,
                'air_is_valid': False,
                'overall_valid': False,
                'update_time': time_util.get_format_from_time(time.time()),
                'first_detection_time': time.time()
            }

        # 将模块信息存储到 cage_modules 字典
        mouse_cage_detect_dict[mouse_cage_number]['cage_modules'][module_name] = response_state
        mouse_cage_detect_dict[mouse_cage_number]['cage_states'].append(response_state)
        mouse_cage_detect_dict[mouse_cage_number]['update_time'] = time_util.get_format_from_time(time.time())

        # 判断笼内所有模块是否都有效
        cage_modules = mouse_cage_detect_dict[mouse_cage_number]['cage_modules']
        cage_is_valid = len(cage_modules) > 0 and all(cage_modules.values())
        mouse_cage_detect_dict[mouse_cage_number]['cage_is_valid'] = cage_is_valid

        # 更新整体有效性（只有气路也完成检测时才判断整体有效）
        air_is_valid = mouse_cage_detect_dict[mouse_cage_number]['air_is_valid']
        overall_valid = cage_is_valid and air_is_valid and len(cage_modules) > 0
        mouse_cage_detect_dict[mouse_cage_number]['overall_valid'] = overall_valid

        # 保存到全局设置
        global_setting.set_setting("mouse_cage_detect_state_dict", mouse_cage_detect_dict)

        # logger.info(
        #     f"鼠笼 {mouse_cage_number} 笼内模块更新: "
        #     f"{module_name}={response_state}, "
        #     f"当前笼内模块: {cage_modules}, "
        #     f"笼内有效: {cage_is_valid}, "
        #     f"整体有效: {overall_valid}"
        # )

        # ==================== 更新UI ====================
        self.update_cage_display_to_detecting(mouse_cage_number)

        # 检查检测是否完成
        self._check_detection_complete(mouse_cage_number)

    def not_each_Mouse_Cage_detect_update_state(self, state_data):
        """更新气路模块检测状态"""
        logger.critical(f"TAB1_not_each_Mouse_Cage_detect_update_state: {state_data}")

        module_name = state_data.get('module_name', 'UNKNOWN')
        response_state = state_data.get('response_state', False)

        # 获取检测字典
        mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})

        # ==================== 确保cage_enabled_status不为空 ====================
        if not self.cage_enabled_status:
            logger.warning(f"cage_enabled_status 为空，正在初始化...")
            self.init_cage_list()

            if not self.cage_enabled_status:
                logger.error(f"cage_enabled_status 初始化失败，无法处理检测数据")
                return

        # 如果检测字典为空，先为所有已启用的笼子初始化
        if not mouse_cage_detect_dict:
            logger.info("检测字典为空，正在初始化所有已启用的笼子...")
            mouse_cage_detect_dict = {}

            for cage_number in self.cage_enabled_status.keys():
                mouse_cage_detect_dict[cage_number] = {
                    'cage_states': [],
                    'air_states': [],
                    'cage_modules': {},
                    'air_modules': {},
                    'cage_is_valid': False,  # ← 改为 False
                    'air_is_valid': False,  # ← 改为 False
                    'overall_valid': False,  # ← 改为 False
                    'update_time': time_util.get_format_from_time(time.time()),
                    'first_detection_time': time.time()
                }

            global_setting.set_setting("mouse_cage_detect_state_dict", mouse_cage_detect_dict)
            logger.info(f"已初始化 {len(mouse_cage_detect_dict)} 个笼子的检测状态")

        existing_cage_numbers = list(mouse_cage_detect_dict.keys())
        if not existing_cage_numbers:
            logger.warning("没有任何已初始化的笼子")
            return

        logger.info(f"气路模块 {module_name} 检测结果: {response_state}，将更新到笼子: {existing_cage_numbers}")

        # ==================== 为所有鼠笼更新该气路模块的状态 ====================
        for cage_number in existing_cage_numbers:
            cage_data = mouse_cage_detect_dict[cage_number]

            # 确保air_modules字典存在
            if 'air_modules' not in cage_data:
                cage_data['air_modules'] = {}

            # 将气路模块状态存储到 air_modules 字典
            cage_data['air_modules'][module_name] = response_state

            # 兼容旧代码：同时保存到 air_states 列表
            if 'air_states' not in cage_data:
                cage_data['air_states'] = []
            cage_data['air_states'].append(response_state)

            # 更新时间戳
            cage_data['update_time'] = time_util.get_format_from_time(time.time())

            # 判断所有气路模块是否都有效
            air_modules = cage_data['air_modules']
            air_is_valid = len(air_modules) > 0 and all(air_modules.values())
            cage_data['air_is_valid'] = air_is_valid

            # 更新整体有效性（两类模块都要检测完成）
            cage_is_valid = cage_data.get('cage_is_valid', False)
            cage_modules = cage_data.get('cage_modules', {})
            # 只有当两类模块都有数据时才判断overall_valid
            cage_data['overall_valid'] = (cage_is_valid and air_is_valid and
                                          len(cage_modules) > 0 and len(air_modules) > 0)

            # logger.info(
            #     f"鼠笼 {cage_number} 气路模块更新: "
            #     f"{module_name}={response_state}, "
            #     f"当前气路模块: {air_modules}, "
            #     f"气路有效: {air_is_valid}, "
            #     f"笼内模块: {len(cage_modules)} 个, "
            #     f"整体有效: {cage_data['overall_valid']}"
            # )

            # ==================== 更新该笼子的UI ====================
            self.update_cage_display_to_detecting(cage_number)

            # ==================== 检查该笼子是否完成检测 ====================
            self._check_detection_complete(cage_number)

        # 保存到全局设置
        global_setting.set_setting("mouse_cage_detect_state_dict", mouse_cage_detect_dict)

    def update_cage_ui_status(self, cage_number):
        """根据检测结果更新UI中鼠笼的状态和可点击性"""
        logger.info(f"update_cage_ui_status() 被调用，笼号: {cage_number}")

        cage_list_widget = self._get_cage_list_widget()

        if cage_list_widget is None:
            logger.error(f"cage_list_widget 为 None，无法更新鼠笼 {cage_number} 的UI")
            return

        # ========== 如果列表为空，重新初始化 ==========
        list_count = cage_list_widget.count()
        if list_count == 0:
            logger.warning(f"笼子列表为空，重新初始化...")
            self.init_cage_list()  # 重新初始化列表
            list_count = cage_list_widget.count()

            if list_count == 0:
                logger.error(f"重新初始化后列表仍为空，无法更新")
                return

        # ========== 检查状态字典 ==========
        if cage_number not in self.cage_enabled_status:
            logger.warning(f"笼号 {cage_number} 不在 cage_enabled_status 中")
            return

        if cage_number not in self.groups_status:
            logger.warning(f"笼号 {cage_number} 不在 groups_status 中")
            return

        try:
            # ==================== 找到对应的 ListWidgetItem ====================
            found_item = None

            for i in range(cage_list_widget.count()):
                item = cage_list_widget.item(i)
                if not item:
                    continue

                item_cage_number = item.data(Qt.ItemDataRole.UserRole)
                if item_cage_number == cage_number:
                    found_item = item
                    break

            if not found_item:
                logger.warning(f"未找到笼子 {cage_number} 对应的 ListWidgetItem")
                return

            # logger.info(f"✓ 找到匹配的笼子项: 笼号={cage_number}")

            # ==================== 获取分组和动物信息 ====================
            group = self.cage_enabled_status.get(cage_number)
            if not group:
                logger.warning(f"未找到鼠笼 {cage_number} 的分组信息")
                return

            animal_count = 0
            if self.experiment_setting and self.experiment_setting.animalGroupRecords:
                animal_count = len([
                    r for r in self.experiment_setting.animalGroupRecords
                    if r.gid == cage_number
                ])

            # ==================== 获取检测数据 ====================
            mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})
            cage_data = mouse_cage_detect_dict.get(cage_number, {})

            cage_modules = cage_data.get('cage_modules', {})
            air_modules = cage_data.get('air_modules', {})
            overall_valid = cage_data.get('overall_valid', False)

            cage_module_count = len(cage_modules)
            air_module_count = len(air_modules)
            total_module_count = cage_module_count + air_module_count

            logger.critical(
                f"\n{'=' * 80}\n"
                f"笼 {cage_number} 检测数据:\n"
                f"  笼内: {cage_modules}\n"
                f"  气路: {air_modules}\n"
                f"  总计: {total_module_count} 个模块\n"
                f"  结果: {'通过' if overall_valid else '异常'}\n"
                f"{'=' * 80}\n"
            )

            # ==================== 状态判断逻辑 ====================
            if total_module_count == 0:
                status_text = f"待检测"
                found_item.setFlags(Qt.ItemFlag.NoItemFlags)

            elif total_module_count > 0:
                status_text = f"检测中... ({total_module_count}个模块)"
                found_item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.groups_status[cage_number]['status'] = 'detecting'
                # logger.info(f"✓ 笼 {cage_number}: {status_text}")

            # ========== 更新UI ==========
            item_text = f"鼠笼 {cage_number} - {group.name} ({animal_count}个动物) - {status_text}"
            found_item.setText(item_text)

            # 强制刷新
            cage_list_widget.viewport().update()
            cage_list_widget.repaint()

            # logger.info(f"✓ UI 已更新: {status_text}")

        except Exception as e:
            logger.error(f"更新笼 {cage_number} UI 失败: {e}", exc_info=True)

    def update_cage_display_to_detecting(self, cage_number):
        """根据检测模块数量动态更新单个笼子的UI显示状态"""
        try:
            if not self.cage_list_widget:
                logger.warning(f"cage_list_widget 为空，无法更新笼 {cage_number}")
                return

            for i in range(self.cage_list_widget.count()):
                item = self.cage_list_widget.item(i)
                if not item or item.data(Qt.ItemDataRole.UserRole) != cage_number:
                    continue

                group = self.cage_enabled_status.get(cage_number)
                if not group:
                    logger.warning(f"笼 {cage_number} 未在 cage_enabled_status 中找到")
                    continue

                animal_count = 0
                if self.experiment_setting and self.experiment_setting.animalGroupRecords:
                    animal_count = len([
                        r for r in self.experiment_setting.animalGroupRecords
                        if r.gid == cage_number
                    ])

                # 获取检测状态
                mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})

                # ========== 处理字典为空或笼子数据不存在的情况 ==========
                if cage_number not in mouse_cage_detect_dict:
                    status_text = "检测中..."
                    # logger.info(f"笼 {cage_number} 检测字典为空，初始化为'检测中...'")
                else:
                    cage_data = mouse_cage_detect_dict[cage_number]

                    # 获取已检测的模块
                    cage_modules = cage_data.get('cage_modules', {})
                    air_modules = cage_data.get('air_modules', {})
                    received_module_count = len(cage_modules) + len(air_modules)

                    # 日志记录实时变化的值
                    logger.debug(
                        f"笼 {cage_number} - 笼内模块: {list(cage_modules.keys())} (count={len(cage_modules)})")
                    logger.debug(f"笼 {cage_number} - 气路模块: {list(air_modules.keys())} (count={len(air_modules)})")
                    logger.debug(f"笼 {cage_number} - 总模块数: {received_module_count}")

                    # 根据模块数量确定状态
                    if received_module_count == 0:
                        status_text = "检测中..."
                    elif received_module_count <= 7:
                        status_text = f"检测中..."
                    else:
                        status_text = f"检测异常"

                item_text = f"鼠笼 {cage_number} - {group.name} ({animal_count}个动物) - {status_text}"
                item.setText(item_text)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                # logger.info(f"✓ 已更新笼 {cage_number} 显示为: {status_text}")
                break

        except Exception as e:
            logger.error(f"更新笼 {cage_number} 检测状态失败: {e}", exc_info=True)

    # ==========配置管理==========
    def _get_cage_config_path(self, cage_id: int) -> Path:
        """获取笼子配置文件路径"""
        return self.user_config_dir / f"cage_{cage_id}_config.json"

    def _save_cage_config_to_json(self, cage_id: int, config_data: dict) -> bool:
        """保存笼子配置到用户本地JSON文件"""
        try:
            config_data['timestamp'] = time_util.get_format_from_time(time.time())
            config_data['cage_id'] = cage_id

            config_path = self._get_cage_config_path(cage_id)

            # 确保目录存在
            self.user_config_dir.mkdir(parents=True, exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            logger.info(f"✓ 笼子 {cage_id} 配置已保存到: {config_path}")
            return True
        except Exception as e:
            logger.error(f"保存笼子 {cage_id} 配置失败: {e}")
            return False

    def _load_cage_config_from_json(self, cage_id: int) -> dict:
        """从用户本地JSON文件加载笼子配置"""
        try:
            config_path = self._get_cage_config_path(cage_id)

            if not config_path.exists():
                logger.debug(f"笼子 {cage_id} 配置文件不存在，使用默认配置: {config_path}")
                return {}

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            logger.info(f"✓ 笼子 {cage_id} 配置已从本地加载: {config_path}")
            return config_data
        except Exception as e:
            logger.error(f"加载笼子 {cage_id} 配置失败: {e}")
            return {}

    def _delete_cage_config_file(self, cage_id: int) -> bool:
        """删除笼子本地配置文件"""
        try:
            config_path = self._get_cage_config_path(cage_id)
            if config_path.exists():
                config_path.unlink()
                logger.info(f"✓ 笼子 {cage_id} 本地配置文件已删除: {config_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除笼子 {cage_id} 配置失败: {e}")
            return False

    def load_cage_config(self, group_num):
        """加载指定鼠笼的配置界面"""
        try:
            if self.content_layout is None:
                logger.error("content_layout 未找到！")
                return

            self.remove_layout_items(self.content_layout)
            self.init_basic_config(self.content_layout)

            # ==================== 新增：从用户本地加载保存的配置 ====================
            saved_config = self._load_cage_config_from_json(group_num)
            self.current_cage_config = saved_config.copy()

            if saved_config:
                logger.info(f"✓ 已加载笼子 {group_num} 的本地保存配置")
            else:
                logger.info(f"笼子 {group_num} 首次配置，将创建新配置文件")

            response_data = self.groups_status[group_num]['response_data']

            for module_key, module_value in self.config.items():
                if module_key == Modbus_Type.Modbus_Slave_Ids.ENM.value['name']:
                    module_config = saved_config.get('ENM', {})
                    self.init_enm_config_ui_for_group(module_key, module_value, self.content_layout, group_num,
                                                      module_config)
                elif module_key == Modbus_Type.Modbus_Slave_Ids.EM.value['name']:
                    module_config = saved_config.get('EM', {})
                    self.init_em_config_ui_for_group(module_key, module_value, self.content_layout, group_num,
                                                     module_config)
        except Exception as e:
            logger.error(f"加载笼子配置出错: {e}", exc_info=True)

    def on_radio_button_clicked(self, button, address, mouse_cage_number, function_code, data_lists, config_key=''):
        """处理按钮点击事件 - 实时保存配置到本地"""
        btn_object_name: str = button.objectName()
        data_list = ['00', '00', '00', '00']

        if "on" in btn_object_name.lower():
            data_list = [hex_str[2:] for hex_str in data_lists["0"]['value']]
            state_value = 'on'
        elif "off" in btn_object_name.lower():
            data_list = [hex_str[2:] for hex_str in data_lists["1"]['value']]
            state_value = 'off'

        # ==================== 保存配置到内存和本地文件 ====================
        if config_key:
            # 获取模块类型
            if config_key.startswith('ENM_'):
                module_type = 'ENM'
                config_key_clean = config_key.replace('ENM_', '')
            elif config_key.startswith('EM_'):
                module_type = 'EM'
                config_key_clean = config_key.replace('EM_', '')
            else:
                module_type = 'UNKNOWN'
                config_key_clean = config_key

            if module_type not in self.current_cage_config:
                self.current_cage_config[module_type] = {}

            self.current_cage_config[module_type][config_key_clean] = state_value

            # 实时保存到用户本地文件
            self._save_cage_config_to_json(mouse_cage_number, self.current_cage_config)

        # ==================== 发送数据到硬件 ====================
        self.send_message['data'] = data_list
        if mouse_cage_number == 0:
            self.send_message['slave_id'] = format(address, '02X')
        else:
            self.send_message['slave_id'] = format(address + mouse_cage_number * 16, '02X')
        self.send_message['function_code'] = format(function_code, '02X')

        self.send_data()
        # logger.info(f"✓ 笼子 {mouse_cage_number} 配置已保存到本地并发送: {config_key}={state_value}")

    def update_slider(self, address, mouse_cage_number, function_code, data_lists, slider: QSlider, config_key=''):
        """更新滑块值 - 实时保存配置到本地"""
        value = slider.value()
        data_list = ['00', '00', '00', '00']

        if str(value) in data_lists:
            data_list = [hex_str[2:] for hex_str in data_lists[str(value)]['value']]

        # ==================== 保存配置到内存和本地文件 ====================
        if config_key:
            # 获取模块类型
            if config_key.startswith('ENM_'):
                module_type = 'ENM'
                config_key_clean = config_key.replace('ENM_', '')
            elif config_key.startswith('EM_'):
                module_type = 'EM'
                config_key_clean = config_key.replace('EM_', '')
            else:
                module_type = 'UNKNOWN'
                config_key_clean = config_key

            if module_type not in self.current_cage_config:
                self.current_cage_config[module_type] = {}

            self.current_cage_config[module_type][config_key_clean] = value

            # 实时保存到用户本地文件
            self._save_cage_config_to_json(mouse_cage_number, self.current_cage_config)

        # ==================== 发送数据到硬件 ====================
        self.send_message['data'] = data_list
        if mouse_cage_number == 0:
            self.send_message['slave_id'] = format(address, '02X')
        else:
            self.send_message['slave_id'] = format(address + mouse_cage_number * 16, '02X')
        self.send_message['function_code'] = format(function_code, '02X')

        self.send_data()
        logger.info(f"✓ 笼子 {mouse_cage_number} 滑块配置已保存到本地并发送: {config_key}={value}")
    def update_slider_label(self, value, label):
        label.setText(f"当前值: {value}")  # 更新当前值标签的文本
        # 更新label
        pass
    # ==========数据通信==========
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
                logger.error(f"{e}")
        else:
            message_struct = ObjectQueueItem(to="main_monitor_data",
                                             data=self.send_message,
                                             origin='Tab_1')

            global_setting.get_setting("send_message_queue").put(message_struct)
            logger.debug(f"Tab_1开始发送消息:{message_struct}")
    # ==========操作按钮==========
    # 重新获取端口
    def refresh_port(self):
        self.ports = []
        self._init_data()
        self.init_port_combox()

    def start_device_config(self):
        # 确定设备配置按钮
        reply = QMessageBox.question(self, '确定设备配置',
                                     "确定该设备配置？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            global_setting.set_setting("app_state", AppState.CONFIGURING)
            if self.main_gui is not None:
                self.main_gui.change_enable_component_app_state_signal.emit()
                pass
            # 设置vr值
            vr_value = self.vr_desc_text.value()
            if vr_value:
                global_setting.set_setting("Vr", float(vr_value))
            send_message_queue = global_setting.get_setting("send_message_queue")
            send_message_queue.put(ObjectQueueItem(origin='Tab_1', to='main_monitor_data', title='set_port',
                                                   data=self.send_message['port'],
                                                   time=time_util.get_format_from_time(time.time())))
            self.close()
            msg_box = InfoDialog(title="确定设备配置", info="确定该设备配置成功!",
                                 icon=QMessageBox.Icon.Information)
            msg_box.exec()

            reply_start_experiment = QMessageBox.question(self, '开始实验',
                                                          "是否直接开始实验？",
                                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                                          QMessageBox.StandardButton.No)
            if reply_start_experiment == QMessageBox.StandardButton.Yes:
                self.main_gui.start_experiment()

    def stop_experiment(self):
        if self.main_gui is not None:
            self.main_gui.stop_experiment()

    # ==========工具函数==========
    def _get_cage_list_widget(self):
        """安全获取 cage_list_widget"""
        try:
            # 方式1：检查引用是否为None
            if self.cage_list_widget is None:
                self.cage_list_widget = self.findChild(QListWidget, "cage_list_widget")
                if self.cage_list_widget is None:
                    logger.error("无法找到 cage_list_widget")
                    return None

            # 方式2：检查对象是否被销毁（通过检查objectName）
            if self.cage_list_widget.objectName() == "":
                logger.warning("cage_list_widget 可能已被销毁，重新查找...")
                self.cage_list_widget = self.findChild(QListWidget, "cage_list_widget")

            return self.cage_list_widget

        except (RuntimeError, AttributeError) as e:
            logger.error(f"获取 cage_list_widget 失败: {e}")
            self.cage_list_widget = None
            return None

    def remove_layout_items(self, layout):
        """清空布局中的所有控件"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def show_warning(self, title: str, message: str):
        """显示警告对话框"""
        QMessageBox.warning(self, title, message)

    def show_success(self, title: str, message: str):
        """显示成功对话框"""
        QMessageBox.information(self, title, message)