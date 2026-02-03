# Module/new_experiment_setting/index/Tab_1.py
import json
import math
import time
import typing
import threading
from functools import partial
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
from PyQt6 import QtGui, QtCore, QtWidgets
from PyQt6.QtCore import QRect, Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QGroupBox, QLabel, QSlider, QRadioButton,
    QGridLayout, QButtonGroup, QComboBox, QPushButton, QMessageBox, QHBoxLayout,
    QLineEdit, QDoubleSpinBox, QListWidget, QListWidgetItem, QCheckBox
)
from public.util.time_util import time_util


# ========== 线程相关 ==========
class read_queue_data_Thread(MyQThread):
    """读取队列数据的线程"""

    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.Each_Mouse_Cage_detect_finished_signal: pyqtSignal = None
        self.Not_Each_Mouse_Cage_detect_finished_signal: pyqtSignal = None

    def dosomething(self):
        if not self.queue.empty():
            try:
                message: ObjectQueueItem = self.queue.get()
            except Exception as e:
                logger.error(f"{self.name}发生错误{e}")
                return

            if message is not None and isinstance(message,
                                                  ObjectQueueItem) and message.to == 'New_main_experiment_setting':
                logger.info(f"{self.name}_get_message: {message.title}")
                match message.title:
                    case "Each_Mouse_Cage_detect_finished":
                        if self.Each_Mouse_Cage_detect_finished_signal is not None:
                            self.Each_Mouse_Cage_detect_finished_signal.emit(message.data)
                    case "Not_Each_Mouse_Cage_detect_finished":
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

    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()

        # ==================== 配置管理相关 ====================
        self.current_cage_config = {}
        self.user_config_dir = Path.home() / ".mouse_experiment_config" / "cage_configs"
        self.user_config_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"配置文件保存位置: {self.user_config_dir}")

        # ==================== 线程安全相关 ====================
        self.response_lock = threading.Lock()
        self.send_thread: Send_thread = None

        # ==================== 新增：气路检测同步 ====================
        self.air_module_detection_lock = threading.Lock()
        self.air_modules_detected = set()  # 已检测的气路模块
        self.air_modules_valid = {}  # 气路模块有效性状态
        self.required_air_modules = {'UFC', 'UGC', 'ZOS'}
        self.air_detection_complete = False  # 气路检测是否完成
        self.air_detection_complete_event = threading.Event()  # 用于等待气路检测完成

        # ==================== 检测相关属性 ====================
        self.port_confirmed = False
        self.detection_in_progress = False
        self.cage_list_to_detect = []
        self.current_detecting_index = 0
        self.cage_detection_timers = {}  # 笼子检测超时计时器
        self._completed_cages = set()

        # ==================== UI 组件 ====================
        self.port_combox = None
        self.cage_list_widget = None
        self.detection_status_label = None
        self.right_title = None
        self.vr_desc_text: QDoubleSpinBox = None
        self.experiment_setting: Experiment_setting_entity = None
        self.span_oxygen_desc_text: QDoubleSpinBox = None
        self.span_carbon_desc_text: QDoubleSpinBox = None
        self.calibration_checkbox = None
        self.confirm_port_btn = None
        self.config_btn = None
        self.config_layout: QVBoxLayout = None
        self.content_layout: QVBoxLayout = None
        self.start_btn: QPushButton = None
        self.module_status_labels = {}  # 气路模块状态标签 {UFC, UGC, ZOS}
        self.group_box = None
        self.config_scroll_area = None
        self.basic_config_layout = None
        self.module_detection_layout = None

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
        self.cage_enabled_status = {}

        # ========== 初始化顺序 ==========
        if parent is not None:
            self.setParent(parent)
            self.setWindowFlags(QtCore.Qt.WindowType.Widget)

        self._init_ui(parent, geometry, title)
        self._cache_ui_components()
        self._init_data()
        self.experiment_setting: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)
        self.config = get_default_config()
        self._init_customize_ui()
        self._init_function()
        self._init_style_sheet()
        self.setup_tutorial()

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
        """缓存所有 UI 组件"""
        try:
            self.cage_list_widget = getattr(self.ui, 'cage_list_widget', None) or self.findChild(QListWidget,
                                                                                                 "cage_list_widget")
            self.config_scroll_area = getattr(self.ui, 'config_scroll_area', None) or self.findChild(QScrollArea,
                                                                                                     "config_scroll_area")

            if self.config_scroll_area:
                widget = self.config_scroll_area.widget()
                if widget:
                    self.content_layout = widget.layout()

            self.basic_config_layout = getattr(self.ui, 'basic_config_layout', None) or self.findChild(QVBoxLayout,
                                                                                                       "basic_config_layout")
            self.module_detection_layout = getattr(self.ui, 'module_detection_layout', None) or self.findChild(
                QVBoxLayout, "module_detection_layout")
            self.port_combox = getattr(self.ui, 'tab_1_port_combox', None) or self.findChild(QComboBox,
                                                                                             "tab_1_port_combox")
            self.confirm_port_btn = getattr(self.ui, 'tab_1_confirm_port_btn', None) or self.findChild(QPushButton,
                                                                                                       "tab_1_confirm_port_btn")
            self.start_btn = getattr(self.ui, 'start_btn', None) or self.findChild(QPushButton, "start_btn")

            self.right_title = self.findChild(QLabel, "right_title_label")
            self.detection_status_label = self.findChild(QLabel, "detection_status_label")
            self.config_btn = self.findChild(QPushButton, "config_btn")

            logger.info("✓ 所有UI组件已缓存")

        except Exception as e:
            logger.error(f"缓存UI组件失败: {e}", exc_info=True)

    def _init_data(self):
        """获得相关数据"""
        self.ports = scan_serial_ports_with_id()

    def _init_customize_ui(self):
        """初始化自定义UI"""
        if self.experiment_setting is None:
            self.experiment_setting = global_setting.get_setting("experiment_setting", None)

        self.init_port_combox()
        self.config = get_default_config()
        self.init_module_detection_display()
        QTimer.singleShot(200, self.init_cage_list)
        self.init_config_ui()
        super()._init_customize_ui()

    def init_module_detection_display(self):
        """初始化气路模块检测显示区域 - 固定显示 UFC, UGC, ZOS"""
        if self.module_detection_layout is None:
            logger.error("module_detection_layout 未找到！")
            return

        self.remove_layout_items(self.module_detection_layout)
        self.module_detection_layout.setSpacing(15)
        self.module_detection_layout.setContentsMargins(10, 10, 10, 10)

        self.module_status_labels = {}

        modules_to_detect = [
            {'name': 'UFC', 'key': 'UFC'},
            {'name': 'UGC', 'key': 'UGC'},
            {'name': 'ZOS', 'key': 'ZOS'},
        ]

        for module_info in modules_to_detect:
            module_name = module_info['name']
            module_key = module_info['key']

            h_layout = QtWidgets.QHBoxLayout()
            h_layout.setSpacing(15)
            h_layout.setContentsMargins(5, 5, 5, 5)

            name_label = QtWidgets.QLabel(f"{module_name}:")
            name_label.setMinimumWidth(45)
            name_label.setMaximumWidth(45)
            name_label.setMinimumHeight(30)
            name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            name_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    font-size: 12px;
                    color: #333;
                }
            """)

            status_label = QtWidgets.QLabel("待检测")
            status_label.setMinimumWidth(80)
            status_label.setMinimumHeight(30)
            status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            status_label.setWordWrap(False)
            status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #999;
                    padding: 5px 8px;
                    background-color: #f5f5f5;
                    border-radius: 3px;
                }
            """)

            h_layout.addWidget(name_label)
            h_layout.addWidget(status_label)
            h_layout.addStretch()

            self.module_detection_layout.addLayout(h_layout)
            self.module_status_labels[module_key] = status_label

    def _init_function(self):
        """初始化功能"""
        self.init_btn_func()

        self.Each_Mouse_Cage_detect_finished_signal.connect(self.each_Mouse_Cage_detect_update_state)
        self.Not_Each_Mouse_Cage_detect_finished_signal.connect(self.not_each_Mouse_Cage_detect_update_state)

        global read_queue_data_thread

        if read_queue_data_thread is not None:
            if not read_queue_data_thread.isRunning():
                read_queue_data_thread.queue = global_setting.get_setting("send_message_queue")
                read_queue_data_thread.Each_Mouse_Cage_detect_finished_signal = self.Each_Mouse_Cage_detect_finished_signal
                read_queue_data_thread.Not_Each_Mouse_Cage_detect_finished_signal = self.Not_Each_Mouse_Cage_detect_finished_signal
                read_queue_data_thread.update_group_activation_signal = self.update_group_activation_signal
                read_queue_data_thread.start()

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

        try:
            self.port_combox.disconnect()
        except:
            pass
        self.port_combox.currentIndexChanged.connect(self.on_port_selection_changed)

    def init_cage_list(self):
        """初始化鼠笼列表（已启用的笼子）"""
        if self.experiment_setting is None:
            self.experiment_setting = global_setting.get_setting("experiment_setting", None)

        if self.experiment_setting is None:
            logger.error("experiment_setting 仍未加载，无法初始化笼子列表")
            return

        if self.cage_list_widget is None:
            logger.error("cage_list_widget 为 None")
            return

        self.cage_list_widget.clear()
        self.cage_enabled_status.clear()

        try:
            self.cage_list_widget.itemClicked.disconnect()
        except TypeError:
            pass
        self.cage_list_widget.itemClicked.connect(self._on_cage_clicked)

        if self.experiment_setting.groups:
            enabled_groups = [g for g in self.experiment_setting.groups if g.is_selected == 1]

            for group in enabled_groups:
                group_id = group.id
                item_text = f"鼠笼 {group_id} - 待检测"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, group_id)
                item.setFlags(Qt.ItemFlag.NoItemFlags)

                self.cage_list_widget.addItem(item)
                self.cage_enabled_status[group_id] = group

    def init_config_ui(self):
        """初始化配置UI - 显示默认配置"""
        if self.experiment_setting is None:
            self.experiment_setting: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)

        if self.content_layout is None:
            logger.error("content_layout 未找到！")
            return

        self.remove_layout_items(self.content_layout)

        tip_label = QLabel("请先确认串口，然后选择要配置的鼠笼")
        tip_label.setStyleSheet("color: #666; font-style: italic;")
        self.content_layout.addWidget(tip_label)

        self.init_basic_config(self.content_layout)

        if self.config:
            for module_key, module_value in self.config.items():
                if module_key == Modbus_Type.Modbus_Slave_Ids.ENM.value['name']:
                    self.init_enm_config_ui_default(module_key, module_value, self.content_layout)
                elif module_key == Modbus_Type.Modbus_Slave_Ids.EM.value['name']:
                    self.init_em_config_ui_default(module_key, module_value, self.content_layout)

        self.content_layout.addStretch()

    def init_basic_config(self, scroll_area_layout):
        """设置基础设置"""
        self.group_box = QGroupBox(f"基本配置")
        self.group_box.setStyleSheet("""
        QGroupBox {
            font-size:17px;
            font-weight:bolder;
        }
        """)
        self.group_box.setContentsMargins(10, 10, 10, 10)
        scroll_area_layout.addWidget(self.group_box)
        main_layout = QVBoxLayout()
        hT_layout = QHBoxLayout()

        self.calibration_checkbox = QCheckBox("启动时校准气路值")
        self.calibration_checkbox.setStyleSheet("""
                QCheckBox {
                    margin-top:17px;
                    font-weight:bold;
                }
                """)
        self.calibration_checkbox.stateChanged.connect(self.calibration_gas_state_change)
        self.calibration_checkbox.setChecked(global_setting.get_setting("is_auto_calibration", True))
        hT_layout.addWidget(self.calibration_checkbox)
        main_layout.addLayout(hT_layout)

        h0_layout = QHBoxLayout()
        span_oxygen_desc_label = QLabel("span校准的标准气体的氧浓度数值（单位:%,例如20.9%，请输入20.9）：")
        span_oxygen_desc_label.setStyleSheet("""
                      QLabel {
                          font-weight:bold;
                      }
                      """)
        self.span_oxygen_desc_text = QDoubleSpinBox()
        self.span_oxygen_desc_text.setValue(global_setting.get_setting("span_standard_oxygen_value", 20.9))

        h0_layout.addWidget(span_oxygen_desc_label)
        h0_layout.addWidget(self.span_oxygen_desc_text)
        main_layout.addLayout(h0_layout)

        h1_layout = QHBoxLayout()
        span_carbon_desc_label = QLabel("span校准的标准气体的CO2浓度数值（单位:%,例如0.03%，请输入0.03）：")
        span_carbon_desc_label.setStyleSheet("""
                              QLabel {
                                  font-weight:bold;
                              }
                              """)
        self.span_carbon_desc_text = QDoubleSpinBox()
        self.span_carbon_desc_text.setValue(global_setting.get_setting("span_standard_carbon_value", 0.03))

        h1_layout.addWidget(span_carbon_desc_label)
        h1_layout.addWidget(self.span_carbon_desc_text)
        main_layout.addLayout(h1_layout)

        h_layout = QHBoxLayout()
        vr_desc_label = QLabel("请输入Vr值[已弃用]（实际的标定气体，根据气瓶上的标识确定,单位:%,例如20.9%，请输入20.9）：")
        vr_desc_label.setStyleSheet("""
                              QLabel {
                                  font-weight:bold;
                              }
                              """)
        self.vr_desc_text = QDoubleSpinBox()
        self.vr_desc_text.setValue(global_setting.get_setting("Vr", 20.9))

        h_layout.addWidget(vr_desc_label)
        h_layout.addWidget(self.vr_desc_text)
        main_layout.addLayout(h_layout)

        self.group_box.setLayout(main_layout)

    def calibration_gas_state_change(self, state):
        """校准气体状态变化处理"""
        is_checked = bool(state)
        if self.main_gui is not None:
            for tool_bar_action in self.main_gui.tool_bar_actions:
                if tool_bar_action['obj_name'] in ["calibration_gas"]:
                    tool_bar_action["action"].setChecked(is_checked)
                    break
        global_setting.set_setting("is_auto_calibration", is_checked)
        send_message_queue = global_setting.get_setting("send_message_queue")
        send_message_queue.put(
            ObjectQueueItem(origin='tab_7', to='main_monitor_data', title='set_experiment_basic_config',
                            data={"is_auto_calibration": is_checked},
                            time=time_util.get_format_from_time(time.time())))

    def init_btn_func(self):
        """初始化按钮功能"""
        refresh_port_btn: QPushButton = self.findChild(QPushButton, "tab_1_refresh_port_btn")
        if refresh_port_btn:
            refresh_port_btn.clicked.connect(self.refresh_port)

        if self.confirm_port_btn:
            self.confirm_port_btn.clicked.connect(self.confirm_port)
            self.confirm_port_btn.setEnabled(True)

        self.config_btn: QPushButton = self.findChild(QPushButton, "config_btn")
        if self.config_btn:
            self.config_btn.clicked.connect(self.start_device_config)
            self.config_btn.setEnabled(False)

        if self.start_btn:
            self.start_btn.clicked.connect(self.start_device_config)

    # ==========配置UI创建==========
    def init_em_config_ui_default(self, module_key, module_value, scroll_area_layout):
        """初始化 EM 配置UI - 默认显示（不含具体鼠笼）"""
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

    def init_em_config_ui_for_group(self, module_key, module_value, scroll_area_layout, group_num, saved_config=None):
        """初始化 EM 配置UI（针对特定鼠笼）"""
        if saved_config is None:
            saved_config = {}

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

        label = QLabel(f"鼠笼 {group_num}")

        radio_on = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['0']['desc']}"
        )
        radio_on.setObjectName("on")
        radio_off = QRadioButton(
            f"{module_value['config'][0]['value'][0]['refer_value']['1']['desc']}"
        )
        radio_off.setObjectName("off")

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
        """初始化 ENM 配置UI（针对特定鼠笼）"""
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
    def changeEvent(self, event: QEvent):
        """窗口状态改变事件"""
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                if self.calibration_checkbox is not None:
                    self.calibration_checkbox.setChecked(global_setting.get_setting('is_auto_calibration', True))

        super().changeEvent(event)

    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        """窗口显示事件 - 仅更新必要的UI，不重置检测状态"""
        logger.warning("tab1——show")

        # ==================== 只更新校准复选框，不重置整个UI ====================
        if self.calibration_checkbox is not None:
            self.calibration_checkbox.setChecked(global_setting.get_setting('is_auto_calibration', True))

        # ==================== 只在首次显示时初始化 ====================
        if not hasattr(self, '_first_show_done'):
            self._init_customize_ui()
            self._first_show_done = True
        else:
            pass

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
        只有笼内模块检测通过的笼子才能被选中进行配置
        """
        try:
            if not item:
                return

            group_id = item.data(Qt.ItemDataRole.UserRole)

            mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})

            if group_id not in mouse_cage_detect_dict:
                logger.warning(f"笼子 {group_id} 未在检测字典中")
                return

            cage_data = mouse_cage_detect_dict[group_id]
            cage_is_valid = cage_data.get('cage_is_valid', False)

            if not cage_is_valid:
                logger.warning(f"笼子 {group_id} 笼内模块检测未通过，不能配置")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                return

            logger.info(f"✓ 笼子 {group_id} 笼内模块检测通过，允许配置")
            self.load_cage_config(group_id)

            if self.right_title:
                group = self.cage_enabled_status.get(group_id)
                if group:
                    self.right_title.setText(f"配置: 鼠笼 {group_id} - {group.name}")

        except Exception as e:
            logger.error(f"处理笼子点击出错: {e}", exc_info=True)

    # ==========检测流程==========
    def confirm_port(self):
        """确认串口并开始检测"""
        logger.critical("=" * 80)
        logger.critical("开始确认串口并初始化检测流程")
        logger.critical("=" * 80)

        if not self.port_combox or self.port_combox.currentIndex() < 0:
            self.show_warning("错误", "请先选择有效的串口")
            return

        if self.experiment_setting is None:
            self.experiment_setting = global_setting.get_setting("experiment_setting", None)
            if self.experiment_setting is None:
                self.show_warning("错误", "实验设置未加载，请稍候...")
                return

        self.send_message['port'] = self.ports[self.port_combox.currentIndex()]['device']
        self.port_confirmed = True

        # ==================== 禁用按钮 ====================
        self.port_combox.setEnabled(False)
        if self.confirm_port_btn:
            self.confirm_port_btn.setEnabled(False)
            self.confirm_port_btn.setText("串口已确认")

        refresh_port_btn = self.findChild(QPushButton, "tab_1_refresh_port_btn")
        if refresh_port_btn:
            refresh_port_btn.setEnabled(False)

        if self.config_btn:
            self.config_btn.setEnabled(False)

        # ==================== 重置气路模块检测状态 ====================
        with self.air_module_detection_lock:
            self.air_modules_detected.clear()
            self.air_modules_valid.clear()
            self.air_detection_complete = False
            self.air_detection_complete_event.clear()

        # ==================== 重置气路模块显示为检测中 ====================
        for module_key in self.module_status_labels:
            status_label = self.module_status_labels[module_key]
            status_label.setText("检测中...")


        # ==================== 初始化笼内检测状态 ====================
        self._completed_cages = set()
        self.cage_list_to_detect = list(self.cage_enabled_status.keys())
        self.current_detecting_index = 0

        # 初始化全局检测字典
        mouse_cage_detect_dict = {}
        for cage_id in self.cage_enabled_status.keys():
            mouse_cage_detect_dict[cage_id] = {
                'cage_modules': {},
                'air_modules': {},
                'cage_is_valid': False,
                'update_time': time_util.get_format_from_time(time.time())
            }
        global_setting.set_setting("mouse_cage_detect_state_dict", mouse_cage_detect_dict)

        # ==================== ✨ 改动：直接开始检测第一个笼子（包括气路） ====================
        if self.detection_status_label:
            self.detection_status_label.setText("开始检测笼内模块和气路...")

        logger.info("✓ 准备开始检测第一个笼子的所有模块（包括气路）")

        # 直接启动笼内检测（会包括气路检测）
        self.detection_in_progress = True
        self._detect_next_cage()

    def _start_cage_detection(self):
        """开始笼内模块检测流程"""
        logger.critical("=" * 80)
        logger.critical("第2步：开始检测笼内模块")
        logger.critical("=" * 80)

        if not self.cage_list_to_detect:
            logger.error("没有笼子可检测")
            if self.detection_status_label:
                self.detection_status_label.setText("错误：没有笼子可检测")
            return

        self.detection_in_progress = True

        if self.detection_status_label:
            self.detection_status_label.setText(
                f"第2步：检测笼内模块（共 {len(self.cage_list_to_detect)} 个笼子）..."
            )

        self._detect_next_cage()

    def _detect_next_cage(self):
        """检测下一个笼子"""
        try:
            # 检查是否全部完成
            if self.current_detecting_index >= len(self.cage_list_to_detect):
                self._cleanup_all_timers()
                self.detection_in_progress = False

                logger.critical(
                    f"\n{'=' * 80}\n"
                    f"所有笼子检测完成\n"
                    f"  完成的笼子: {sorted(self._completed_cages)}\n"
                    f"{'=' * 80}\n"
                )

                if self.detection_status_label:
                    self.detection_status_label.setText("✓ 检测完成！请选择笼子进行配置")

                if self.config_btn:
                    self.config_btn.setEnabled(True)

                return

            cage_number = self.cage_list_to_detect[self.current_detecting_index]
            self.current_detecting_index += 1

            current_position = self.current_detecting_index
            total_cages = len(self.cage_list_to_detect)

            logger.critical(
                f"\n{'─' * 80}\n"
                f"开始检测笼子: {cage_number} ({current_position}/{total_cages})\n"
                f"{'─' * 80}\n"
            )

            # 更新列表显示为检测中
            self._update_cage_detecting(cage_number)

            if self.detection_status_label:
                self.detection_status_label.setText(
                    f"正在检测笼 {cage_number} 的所有模块 ({current_position}/{total_cages})..."
                )

            # ==================== 检测笼内模块 + 气路模块 ====================
            send_message_queue = global_setting.get_setting("send_message_queue", None)
            if send_message_queue:
                # 1. 先检测笼子内的模块（ENM, EM, DWM, WM）
                send_message_queue.put(
                    ObjectQueueItem(
                        origin="New_main_experiment_setting",
                        to="main_monitor_data",
                        title="start_all_modules_detection",
                        data={'gids': [cage_number]},
                        time=time_util.get_format_from_time(time.time())
                    )
                )
                logger.info(f"✓ 已发送笼 {cage_number} 的模块检测命令")

                # ✨ 只在第一个笼子检测气路模块（参考气路）
                # 但要等待笼内模块检测完全完成后再发送！
                if self.current_detecting_index == 1 and not self.air_detection_complete:
                    logger.info(f"✓ 对笼 {cage_number} 进行参考气路检测（仅第一个笼子检测）")
                    # 延迟发送气路检测，等待笼内模块检测开始处理
                    QTimer.singleShot(500, lambda: self._send_air_module_detection(send_message_queue))

            # 设置超时（15秒 - 增加时间以容纳气路检测）
            self._set_cage_detection_timeout(cage_number, timeout_seconds=15)

        except Exception as e:
            logger.error(f"检测下一个笼子时出错: {e}", exc_info=True)
            self.detection_in_progress = False

    def _send_air_module_detection(self, send_message_queue):
        """发送气路模块检测请求"""
        try:
            if not self.air_detection_complete:
                send_message_queue.put(
                    ObjectQueueItem(
                        origin="New_main_experiment_setting",
                        to="main_monitor_data",
                        title="read_reference_air_module",
                        data={'port': self.send_message['port']},
                        time=time_util.get_format_from_time(time.time())
                    )
                )
                logger.info(f"✓ 参考气路检测请求已发送（延迟发送以避免串口冲突）")
        except Exception as e:
            logger.error(f"发送气路检测请求失败: {e}", exc_info=True)

    def _set_cage_detection_timeout(self, cage_number, timeout_seconds=10):
        """为单个笼子设置检测超时"""
        if cage_number in self.cage_detection_timers:
            self.cage_detection_timers[cage_number].stop()

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._on_cage_detection_timeout(cage_number))
        timer.start(timeout_seconds * 1500)

        self.cage_detection_timers[cage_number] = timer
        logger.debug(f"✓ 笼 {cage_number} 的 {timeout_seconds}秒检测超时已设置")

    def _on_cage_detection_timeout(self, cage_number):
        """笼子检测超时处理"""
        try:
            if cage_number in self.cage_detection_timers:
                self.cage_detection_timers.pop(cage_number)

            if cage_number in self._completed_cages:
                logger.warning(f"笼 {cage_number} 已处理过，跳过超时处理")
                return

            logger.warning(f"笼 {cage_number} 检测超时（15秒），强制结束该笼子的检测")

            self._completed_cages.add(cage_number)
            self._update_cage_detection_complete(cage_number)

            # 推进到下一个笼子
            QTimer.singleShot(300, self._detect_next_cage)

        except Exception as e:
            logger.error(f"处理笼 {cage_number} 超时时出错: {e}", exc_info=True)

    def _update_cage_detecting(self, cage_number):
        """更新笼子为检测中状态"""
        try:
            cage_list_widget = self._get_cage_list_widget()
            if not cage_list_widget:
                return

            for i in range(cage_list_widget.count()):
                item = cage_list_widget.item(i)
                if not item or item.data(Qt.ItemDataRole.UserRole) != cage_number:
                    continue

                item_text = f"鼠笼 {cage_number} - 检测中..."
                item.setText(item_text)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setBackground(QtGui.QColor(255, 255, 240))
                item.setForeground(QtGui.QColor(184, 134, 11))

                cage_list_widget.viewport().update()
                break

        except Exception as e:
            logger.error(f"更新笼 {cage_number} 为检测中状态失败: {e}", exc_info=True)

    def _cleanup_all_timers(self):
        """清理所有计时器"""
        for cage_num in list(self.cage_detection_timers.keys()):
            timer = self.cage_detection_timers.pop(cage_num)
            if timer and timer.isActive():
                timer.stop()

    # ==========状态更新==========
    def each_Mouse_Cage_detect_update_state(self, state_data):
        """
        更新鼠笼内模块检测状态
        逻辑：
        1. 接收笼内模块检测结果（ENM, EM, DWM, WM）
        2. 记录模块有效性
        3. 判断笼子是否完整（收到4个模块且全部有效）
        4. 完整则立即结束该笼子检测，推进到下一个笼子
        5. 实时更新笼子列表显示
        """
        try:
            logger.critical(
                f"\n{'=' * 80}\n"
                f"笼内模块检测结果:\n"
                f"{state_data}\n"
                f"{'=' * 80}\n"
            )

            mouse_cage_number = state_data.get('mouse_cage_number')
            module_name = state_data.get('module_name', 'UNKNOWN')
            data_field = state_data.get('data', [])

            if mouse_cage_number is None:
                logger.error("缺少 mouse_cage_number 信息")
                return

            # ==================== 判断模块是否有效 ====================
            module_is_valid = bool(data_field) and len(data_field) > 0

            if module_is_valid and isinstance(data_field, list):
                for item in data_field:
                    if isinstance(item, dict) and 'value' in item:
                        value_str = str(item['value'])
                        if 'Time OUT' in value_str or '未获取到响应数据' in value_str:
                            module_is_valid = False
                            break

            logger.critical(
                f"笼 {mouse_cage_number} 模块 {module_name}: "
                f"{'✓ 有效' if module_is_valid else '✗ 无效'}"
            )

            # ==================== 更新全局检测字典 ====================
            mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})

            if mouse_cage_number not in mouse_cage_detect_dict:
                mouse_cage_detect_dict[mouse_cage_number] = {
                    'cage_modules': {},
                    'air_modules': {},
                    'cage_is_valid': False,
                    'update_time': time_util.get_format_from_time(time.time())
                }

            # 记录模块状态
            mouse_cage_detect_dict[mouse_cage_number]['cage_modules'][module_name] = module_is_valid
            mouse_cage_detect_dict[mouse_cage_number]['update_time'] = time_util.get_format_from_time(time.time())

            cage_modules = mouse_cage_detect_dict[mouse_cage_number]['cage_modules']
            required_modules = {'ENM', 'EM', 'DWM', 'WM'}

            # ==================== 检查笼子是否完整 ====================
            all_received = required_modules.issubset(set(cage_modules.keys()))
            all_valid = all(cage_modules.values()) if cage_modules else False
            cage_is_valid = all_received and all_valid

            mouse_cage_detect_dict[mouse_cage_number]['cage_is_valid'] = cage_is_valid

            logger.critical(
                f"笼 {mouse_cage_number} 笼内模块统计:\n"
                f"  已收到: {list(cage_modules.keys())}\n"
                f"  缺少: {required_modules - set(cage_modules.keys())}\n"
                f"  有效性: {dict([(k, v) for k, v in cage_modules.items()])}\n"
                f"  判定: {'完整' if all_received else '不完整'} - {'有效' if all_valid else '无效'}"
            )

            global_setting.set_setting("mouse_cage_detect_state_dict", mouse_cage_detect_dict)

            # ==================== 实时更新UI ====================
            self._update_cage_list_display(mouse_cage_number, mouse_cage_detect_dict[mouse_cage_number])

            # ==================== 笼子完整则立即结束检测 ====================
            if all_received:
                self._on_cage_complete(mouse_cage_number, cage_is_valid)

        except Exception as e:
            logger.error(f"更新笼内模块状态时出错: {e}", exc_info=True)

    def _on_cage_complete(self, cage_number, cage_is_valid):
        """笼子完成检测（所有4个模块已收到）"""
        try:
            logger.critical(
                f"\n{'=' * 80}\n"
                f"笼 {cage_number} 已完成检测\n"
                f"检测结果: {'通过' if cage_is_valid else '失败'}\n"
                f"立即停止该笼子的检测\n"
                f"{'=' * 80}\n"
            )

            # 停止该笼子的超时计时器
            if cage_number in self.cage_detection_timers:
                timer = self.cage_detection_timers.pop(cage_number)
                if timer.isActive():
                    timer.stop()
                logger.info(f"✓ 笼 {cage_number} 的检测超时计时器已停止")

            # 避免重复处理
            if cage_number in self._completed_cages:
                logger.warning(f"笼 {cage_number} 已处理过，跳过")
                return

            self._completed_cages.add(cage_number)

            # 更新UI为最终状态
            self._update_cage_detection_complete(cage_number)

            # 延迟后推进到下一个笼子
            logger.info(f"笼 {cage_number} 处理完成，300ms后推进到下一个笼子")
            QTimer.singleShot(300, self._detect_next_cage)

        except Exception as e:
            logger.error(f"处理笼 {cage_number} 完成时出错: {e}", exc_info=True)

    def not_each_Mouse_Cage_detect_update_state(self, state_data):
        """更新气路模块检测状态 - 实时更新（收到一个就立即显示）"""
        try:
            logger.critical(
                f"\n{'=' * 80}\n"
                f"气路模块检测结果:\n"
                f"{state_data}\n"
                f"{'=' * 80}\n"
            )

            module_name = state_data.get('module_name', 'UNKNOWN')
            data_field = state_data.get('data', [])

            # ==================== 判断气路模块是否有效 ====================
            module_is_valid = self._check_module_valid(data_field)

            logger.critical(
                f"气路模块 {module_name}: "
                f"{'✓ 有效' if module_is_valid else '✗ 无效'}"
            )

            # ==================== 线程安全地更新气路检测状态 ====================
            with self.air_module_detection_lock:
                self.air_modules_detected.add(module_name)
                self.air_modules_valid[module_name] = module_is_valid

                logger.critical(
                    f"气路模块检测进度: {len(self.air_modules_detected)}/{len(self.required_air_modules)}\n"
                    f"已检测: {sorted(self.air_modules_detected)}\n"
                    f"缺少: {sorted(self.required_air_modules - self.air_modules_detected)}\n"
                    f"有效性: {self.air_modules_valid}"
                )

                # ✨ 改动：检查是否所有模块都检测完成
                all_detected = self.required_air_modules.issubset(self.air_modules_detected)
                if all_detected:
                    self.air_detection_complete = True
                    logger.critical(
                        f"\n{'=' * 80}\n"
                        f"气路模块检测全部完成\n"
                        f"检测结果: {self.air_modules_valid}\n"
                        f"{'=' * 80}\n"
                    )
                    self.air_detection_complete_event.set()

            # ==================== 实时更新UI - 收到一个就立即更新 ====================
            QTimer.singleShot(
                0,
                partial(self._update_air_module_status_ui, module_name, module_is_valid)
            )

        except Exception as e:
            logger.error(f"更新气路模块状态时出错: {e}", exc_info=True)

    def _check_module_valid(self, data_field):
        """检查模块是否有效"""
        try:
            if not data_field or len(data_field) == 0:
                return False

            if not isinstance(data_field, list):
                return False

            for item in data_field:
                if isinstance(item, dict) and 'value' in item:
                    value_str = str(item['value']).lower()
                    if 'time out' in value_str or '未获取到响应数据' in value_str:
                        return False

            return True
        except Exception as e:
            logger.error(f"检查模块有效性失败: {e}")
            return False

    def _update_air_module_status_ui(self, module_name, module_is_valid):
        """实时更新气路模块UI - 收到一个就立即显示"""
        try:
            if module_name not in self.module_status_labels:
                logger.error(
                    f"气路模块 {module_name} 不在 module_status_labels 中!!!\n"
                    f"已有的气路模块: {list(self.module_status_labels.keys())}"
                )
                return

            status_label = self.module_status_labels[module_name]

            # ==================== 根据检测结果立即更新 ====================
            if module_is_valid:
                status_label.setText("✓ 检测通过")
                style = """
                    QLabel {
                        font-size: 11px;
                        color: #fff;
                        padding: 5px 8px;
                        background-color: #00AA00;
                        border-radius: 3px;
                        font-weight: bold;
                    }
                """
                logger.critical(f"✅ 气路模块 {module_name} 已更新为通过状态")
            else:
                status_label.setText("✗ 检测失败")
                style = """
                    QLabel {
                        font-size: 11px;
                        color: #fff;
                        padding: 5px 8px;
                        background-color: #CC0000;
                        border-radius: 3px;
                        font-weight: bold;
                    }
                """
                logger.critical(f"气路模块 {module_name} 已更新为失败状态")

            status_label.setStyleSheet(style)
            status_label.update()

        except Exception as e:
            logger.error(f"更新气路模块 {module_name} UI 失败: {e}", exc_info=True)

    def _update_cage_list_display(self, cage_number, cage_data):
        """实时更新笼子列表显示 - 每收到一个模块就更新"""
        try:
            cage_list_widget = self._get_cage_list_widget()
            if not cage_list_widget:
                return

            for i in range(cage_list_widget.count()):
                item = cage_list_widget.item(i)
                if not item or item.data(Qt.ItemDataRole.UserRole) != cage_number:
                    continue

                cage_modules = cage_data.get('cage_modules', {})
                cage_is_valid = cage_data.get('cage_is_valid', False)
                air_modules = cage_data.get('air_modules', {})

                required_cage_modules = {'ENM', 'EM', 'DWM', 'WM'}
                received_count = len(cage_modules)
                missing_modules = required_cage_modules - set(cage_modules.keys())
                failed_modules = [name for name, status in cage_modules.items() if not status]

                group = self.cage_enabled_status.get(cage_number)
                group_name = f"[{group.name}]" if group else ""

                logger.debug(
                    f"笼 {cage_number} 实时显示:\n"
                    f"  已收到: {list(cage_modules.keys())}\n"
                    f"  缺少: {list(missing_modules)}\n"
                    f"  有效: {cage_is_valid}\n"
                    f"  进度: {received_count}/4"
                )

                if cage_is_valid and received_count >= 4:
                    # 检测通过
                    status_text = "✓ 检测完成（可配置）"
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    item.setBackground(QtGui.QColor(240, 255, 240))
                    item.setForeground(QtGui.QColor(34, 139, 34))

                elif received_count > 0:
                    # 检测中
                    modules_str = ", ".join(sorted(cage_modules.keys()))
                    status_text = f"检测中... ({received_count}/4 模块: {modules_str})"
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    item.setBackground(QtGui.QColor(255, 255, 240))
                    item.setForeground(QtGui.QColor(184, 134, 11))

                else:
                    # 等待中
                    status_text = "检测中..."
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    item.setBackground(QtGui.QColor(255, 255, 240))
                    item.setForeground(QtGui.QColor(184, 134, 11))

                item_text = f"鼠笼 {cage_number} {group_name} - {status_text}"
                item.setText(item_text)

                cage_list_widget.viewport().update()
                cage_list_widget.repaint()

                logger.debug(f"✓ 笼 {cage_number} 列表显示已更新")
                break

        except Exception as e:
            logger.error(f"更新笼 {cage_number} 列表显示失败: {e}", exc_info=True)

    def _update_cage_detection_complete(self, cage_number):
        """更新笼子UI为最终检测完成状态"""
        try:
            cage_list_widget = self._get_cage_list_widget()
            if not cage_list_widget:
                return

            for i in range(cage_list_widget.count()):
                item = cage_list_widget.item(i)
                if not item or item.data(Qt.ItemDataRole.UserRole) != cage_number:
                    continue

                group = self.cage_enabled_status.get(cage_number)
                if not group:
                    break

                mouse_cage_detect_dict = global_setting.get_setting("mouse_cage_detect_state_dict", {})
                cage_data = mouse_cage_detect_dict.get(cage_number, {})

                cage_modules = cage_data.get('cage_modules', {})
                cage_is_valid = cage_data.get('cage_is_valid', False)

                group_name = f"[{group.name}]" if group else ""

                if cage_is_valid and len(cage_modules) >= 4:
                    status_text = "✓ 检测完成（可配置）"
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    item.setBackground(QtGui.QColor(240, 255, 240))
                    item.setForeground(QtGui.QColor(34, 139, 34))
                    logger.critical(f"笼 {cage_number} 最终状态：通过")

                else:
                    failed_modules = [name for name, status in cage_modules.items() if not status]
                    failed_str = ", ".join(sorted(failed_modules)) if failed_modules else "未收到任何模块"
                    status_text = f"✗ 检测异常 - {failed_str}"
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    item.setBackground(QtGui.QColor(255, 240, 245))
                    item.setForeground(QtGui.QColor(220, 20, 60))
                    logger.error(f"笼 {cage_number} 最终状态：失败 - {status_text}")

                item_text = f"鼠笼 {cage_number} {group_name} - {status_text}"
                item.setText(item_text)

                cage_list_widget.viewport().update()
                cage_list_widget.repaint()
                break

        except Exception as e:
            logger.error(f"更新笼 {cage_number} 最终状态失败: {e}", exc_info=True)

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
                logger.debug(f"笼子 {cage_id} 配置文件不存在，使用默认配置")
                return {}

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            logger.info(f"✓ 笼子 {cage_id} 配置已从本地加载")
            return config_data
        except Exception as e:
            logger.error(f"加载笼子 {cage_id} 配置失败: {e}")
            return {}

    def load_cage_config(self, group_num):
        """加载指定鼠笼的配置界面"""
        try:
            if self.content_layout is None:
                logger.error("content_layout 未找到！")
                return

            self.remove_layout_items(self.content_layout)

            self.init_basic_config(self.content_layout)

            saved_config = self._load_cage_config_from_json(group_num)
            self.current_cage_config = saved_config.copy()

            if saved_config:
                logger.info(f"✓ 已加载笼子 {group_num} 的本地保存配置")
            else:
                logger.info(f"笼子 {group_num} 首次配置，将创建新配置文件")

            for module_key, module_value in self.config.items():
                if module_key == Modbus_Type.Modbus_Slave_Ids.ENM.value['name']:
                    module_config = saved_config.get('ENM', {})
                    self.init_enm_config_ui_for_group(module_key, module_value, self.content_layout, group_num,
                                                      module_config)
                elif module_key == Modbus_Type.Modbus_Slave_Ids.EM.value['name']:
                    module_config = saved_config.get('EM', {})
                    self.init_em_config_ui_for_group(module_key, module_value, self.content_layout, group_num,
                                                     module_config)

            self.content_layout.addStretch()

        except Exception as e:
            logger.error(f"加载笼子配置出错: {e}", exc_info=True)

    def on_radio_button_clicked(self, button, address, mouse_cage_number, function_code, data_lists, config_key=''):
        """处理按钮点击事件"""
        btn_object_name: str = button.objectName()
        data_list = ['00', '00', '00', '00']

        if "on" in btn_object_name.lower():
            data_list = [hex_str[2:] for hex_str in data_lists["0"]['value']]
            state_value = 'on'
        elif "off" in btn_object_name.lower():
            data_list = [hex_str[2:] for hex_str in data_lists["1"]['value']]
            state_value = 'off'

        if config_key:
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
            self._save_cage_config_to_json(mouse_cage_number, self.current_cage_config)

        self.send_message['data'] = data_list
        if mouse_cage_number == 0:
            self.send_message['slave_id'] = format(address, '02X')
        else:
            self.send_message['slave_id'] = format(address + mouse_cage_number * 16, '02X')
        self.send_message['function_code'] = format(function_code, '02X')

        self.send_data()

    def update_slider(self, address, mouse_cage_number, function_code, data_lists, slider: QSlider, config_key=''):
        """更新滑块值"""
        value = slider.value()
        data_list = ['00', '00', '00', '00']

        if str(value) in data_lists:
            data_list = [hex_str[2:] for hex_str in data_lists[str(value)]['value']]

        if config_key:
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
            self._save_cage_config_to_json(mouse_cage_number, self.current_cage_config)

        self.send_message['data'] = data_list
        if mouse_cage_number == 0:
            self.send_message['slave_id'] = format(address, '02X')
        else:
            self.send_message['slave_id'] = format(address + mouse_cage_number * 16, '02X')
        self.send_message['function_code'] = format(function_code, '02X')

        self.send_data()
        logger.info(f"✓ 笼子 {mouse_cage_number} 滑块配置已保存: {config_key}={value}")

    def update_slider_label(self, value, label):
        """更新滑块标签"""
        label.setText(f"当前值: {value}")

    # ==========数据通信==========
    def send_data(self):
        """发送数据"""
        state = global_setting.get_setting("app_state", AppState.INITIALIZED)
        if state is None or state != AppState.MONITORING:
            try:
                if self.send_thread is None:
                    logger.info("初始化串口")
                    self.send_thread = Send_thread(name="tab_3_COM_Send_Thread",
                                                   modbus=None, send_message=self.send_message)
                    self.send_thread.is_start = True
                    self.send_thread.start()
                    return
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
    def refresh_port(self):
        """重新获取端口"""
        self.ports = []
        self._init_data()
        self.init_port_combox()

    def start_device_config(self):
        """开始设备配置"""
        reply = QMessageBox.question(self, '确定设备配置',
                                     "确定该设备配置？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            global_setting.set_setting("app_state", AppState.CONFIGURING)
            if self.main_gui is not None:
                self.main_gui.change_enable_component_app_state_signal.emit()

            send_message_queue = global_setting.get_setting("send_message_queue")
            send_message_queue.put(ObjectQueueItem(origin='tab_7', to='main_monitor_data', title='set_port',
                                                   data=self.send_message['port'],
                                                   time=time_util.get_format_from_time(time.time())))
            basic_experiment_config = {}
            vr_value = self.vr_desc_text.value()
            if vr_value:
                basic_experiment_config['vr_desc'] = float(vr_value)
                global_setting.set_setting("Vr", float(vr_value))

            span_oxygen_value = self.span_oxygen_desc_text.value()
            if span_oxygen_value:
                basic_experiment_config["span_standard_oxygen_value"] = float(span_oxygen_value)
                global_setting.set_setting("span_standard_oxygen_value", float(span_oxygen_value))

            span_carbon_value = self.span_carbon_desc_text.value()
            if span_carbon_value:
                basic_experiment_config["span_standard_carbon_value"] = float(span_carbon_value)
                global_setting.set_setting("span_standard_carbon_value", float(span_carbon_value))

            send_message_queue.put(
                ObjectQueueItem(origin='tab_7', to='main_monitor_data', title='set_experiment_basic_config',
                                data=basic_experiment_config,
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
        """停止实验"""
        if self.main_gui is not None:
            self.main_gui.stop_experiment()

    # ==========工具函数==========
    def _get_cage_list_widget(self):
        """安全获取 cage_list_widget"""
        try:
            if self.cage_list_widget is None:
                self.cage_list_widget = self.findChild(QListWidget, "cage_list_widget")
                if self.cage_list_widget is None:
                    logger.error("无法找到 cage_list_widget")
                    return None

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