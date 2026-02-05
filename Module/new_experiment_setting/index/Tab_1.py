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
from PyQt6.QtCore import QRect, Qt, pyqtSignal, QTimer, QEvent, pyqtSlot
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QGroupBox, QLabel, QSlider, QRadioButton,
    QGridLayout, QButtonGroup, QComboBox, QPushButton, QMessageBox, QHBoxLayout,
    QLineEdit, QDoubleSpinBox, QListWidget, QListWidgetItem, QCheckBox, QApplication
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
    # ==================== 原有信号 ====================
    update_group_activation_signal = pyqtSignal(dict)
    Each_Mouse_Cage_detect_finished_signal = pyqtSignal(dict)
    Not_Each_Mouse_Cage_detect_finished_signal = pyqtSignal(dict)
    air_module_ui_update_signal = pyqtSignal(str, bool)

    # ==================== 新增：跨线程安全的信号 ====================
    signal_air_module_update = pyqtSignal(str, bool)  # (module_name, is_valid)
    signal_detection_status_update = pyqtSignal(str)  # (status_text)
    signal_force_ui_refresh = pyqtSignal()  # 强制UI刷新

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

        # ==================== 气路检测相关属性 ====================
        self.air_module_detection_lock = threading.RLock()
        self._air_detection_finished = False
        self._air_detection_final_result_cached = None
        self._air_ui_has_been_updated = False

        # 气路模块状态字典
        self.air_modules_completed = {}
        self.air_modules_detected = {}
        self.air_modules_valid = {}
        self.air_modules_to_detect = ['UFC', 'UGC', 'ZOS']
        self.required_air_modules = {'UFC', 'UGC', 'ZOS'}

        self.air_module_detection_results = {
            'UFC': {'detected': False, 'valid': False},
            'UGC': {'detected': False, 'valid': False},
            'ZOS': {'detected': False, 'valid': False}
        }

        # 气路检测完成事件
        self.air_detection_complete_event = threading.Event()
        self.air_detection_complete_event.clear()

        # ==================== 检测相关属性 ====================
        self.port_confirmed = False
        self.detection_in_progress = False
        self.cage_list_to_detect = []
        self.current_detecting_index = 0
        self.cage_detection_timers = {}
        self._completed_cages = {}

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
        self.module_status_labels = {}
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
        self._connect_air_module_signals()  # 连接信号槽
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

    # ==================== 新增：连接信号槽 ====================
    def _connect_air_module_signals(self):
        """
        连接气路检测相关的信号槽
        这确保所有UI更新都在主线程执行
        """
        try:
            # 气路模块UI更新 - 直接在主线程处理
            self.signal_air_module_update.connect(
                self._slot_on_air_module_ui_update,
                Qt.ConnectionType.QueuedConnection  # 排队方式，确保在主线程
            )

            # 检测状态更新
            self.signal_detection_status_update.connect(
                self._slot_on_detection_status_update,
                Qt.ConnectionType.QueuedConnection
            )

            # UI强制刷新
            self.signal_force_ui_refresh.connect(
                self._slot_on_force_ui_refresh,
                Qt.ConnectionType.QueuedConnection
            )

            logger.info("气路检测信号槽已连接")

        except Exception as e:
            logger.error(f"连接信号槽失败: {e}", exc_info=True)

    # ==================== 新增：槽函数 ====================
    @pyqtSlot(str, bool)
    def _slot_on_air_module_ui_update(self, module_name: str, is_valid: bool):
        """
        【主线程槽函数】更新气路模块UI
        这是唯一修改UI的地方，保证线程安全
        """
        try:
            logger.critical(f"[主线程槽函数] 准备更新 {module_name} UI: {'✓ 有效' if is_valid else '✗ 无效'}")

            if module_name not in self.module_status_labels:
                logger.warning(f"模块 {module_name} 在 UI 中不存在")
                return

            status_label = self.module_status_labels[module_name]

            # ==================== 更新UI文本和样式 ====================
            if is_valid:
                # 有效状态
                status_label.setText("有效")
                status_label.setStyleSheet("""
                    QLabel {
                        color: #27AE60;
                        font-weight: bold;
                        font-size: 12px;
                        background-color: #E8F8F5;
                        border: 1px solid #27AE60;
                        border-radius: 3px;
                        padding: 5px 8px;
                    }
                """)
                logger.info(f"{module_name} UI 已更新为【有效】")

            else:
                # 无效状态
                status_label.setText("无效")
                status_label.setStyleSheet("""
                    QLabel {
                        color: #E74C3C;
                        font-weight: bold;
                        font-size: 12px;
                        background-color: #FADBD8;
                        border: 1px solid #E74C3C;
                        border-radius: 3px;
                        padding: 5px 8px;
                    }
                """)
                logger.warning(f"{module_name} UI 已更新为【无效】")

            # ==================== 强制刷新控件 ====================
            status_label.update()
            status_label.repaint()  # 强制重绘

            # ==================== 处理事件队列 ====================
            QApplication.processEvents()  # 立即处理待处理事件

            logger.info(f"{module_name} UI 已重绘完成")

        except Exception as e:
            logger.error(f"更新 {module_name} UI 失败: {e}", exc_info=True)

    @pyqtSlot(str)
    def _slot_on_detection_status_update(self, status_text: str):
        """【主线程槽函数】更新检测状态"""
        try:
            if self.detection_status_label:
                self.detection_status_label.setText(status_text)
                self.detection_status_label.update()
                self.detection_status_label.repaint()

                logger.info(f"检测状态已更新: {status_text}")

                QApplication.processEvents()

        except Exception as e:
            logger.error(f"更新检测状态失败: {e}", exc_info=True)

    @pyqtSlot()
    def _slot_on_force_ui_refresh(self):
        """【主线程槽函数】强制刷新整个UI"""
        try:
            logger.info("执行UI强制刷新...")

            # 刷新所有模块标签
            for module_name, status_label in self.module_status_labels.items():
                status_label.update()
                status_label.repaint()

            # 刷新检测状态标签
            if self.detection_status_label:
                self.detection_status_label.update()
                self.detection_status_label.repaint()

            # 刷新整个Widget
            self.update()
            self.repaint()

            # 处理事件队列
            QApplication.processEvents()

            logger.info("UI 强制刷新完成")

        except Exception as e:
            logger.error(f"UI 刷新失败: {e}", exc_info=True)

    def _init_function(self):
        """初始化功能"""
        self.init_btn_func()

        self.Each_Mouse_Cage_detect_finished_signal.connect(
            self.each_Mouse_Cage_detect_update_state,
            Qt.ConnectionType.QueuedConnection
        )
        self.Not_Each_Mouse_Cage_detect_finished_signal.connect(
            self.not_each_Mouse_Cage_detect_update_state,
            Qt.ConnectionType.QueuedConnection
        )

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
        """窗口显示事件"""
        logger.warning("tab1——show")

        if self.calibration_checkbox is not None:
            self.calibration_checkbox.setChecked(global_setting.get_setting('is_auto_calibration', True))

        if not hasattr(self, '_first_show_done'):
            self._init_customize_ui()
            self._first_show_done = True

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

    # ========== 气路检测流程（修改版 - 改用信号槽） ==========
    def confirm_port(self):
        """
        确认串口并启动气路检测（修复版）
        """
        logger.critical("=" * 80)
        logger.critical("确认串口，启动气路模块检测")
        logger.critical("=" * 80)

        # ==================== 验证串口 ====================
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

        # ==================== 进程状态检查 ====================
        process_monitor = global_setting.get_setting("process_monitor", None)
        if process_monitor:
            p_response_comm_status = process_monitor.get_process_status("p_response_comm")
            if p_response_comm_status and p_response_comm_status == "UNRESPONSIVE":
                reply = QMessageBox.question(
                    self, "进程警告",
                    "p_response_comm 进程无响应，可能导致串口数据接收异常，是否继续？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return

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

        # ==================== 重置气路检测状态 ====================
        with self.air_module_detection_lock:
            if not self._air_detection_finished or not self._air_ui_has_been_updated:
                self.air_detection_complete_event.clear()
                self._air_detection_finished = False
                self._air_ui_has_been_updated = False
                self._air_detection_final_result_cached = None

                self.air_modules_completed.clear()
                self.air_modules_detected.clear()
                self.air_modules_valid.clear()

                for module_name in ['UFC', 'UGC', 'ZOS']:
                    self.air_modules_completed[module_name] = False
                    self.air_modules_detected[module_name] = False
                    self.air_modules_valid[module_name] = False

                logger.debug("[重置] 气路检测状态已重置")

        # ==================== 重置气路模块UI ====================
        for module_name in self.air_modules_to_detect:
            if module_name in self.module_status_labels:
                status_label = self.module_status_labels[module_name]
                status_label.setText("检测中...")
                status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #FF8C00;
                        padding: 5px 8px;
                        background-color: #FFE4B5;
                        border-radius: 3px;
                    }
                """)
                status_label.update()
                status_label.repaint()

        # ==================== 初始化笼内检测 - 类型统一为int ====================
        self._completed_cages.clear()
        self.cage_list_to_detect = [int(cage_id) for cage_id in self.cage_enabled_status.keys()]
        self.current_detecting_index = 0
        self.cage_detection_timers.clear()

        logger.debug(f"笼子列表已初始化: {self.cage_list_to_detect} (类型统一为int)")

        # 初始化所有笼子的完成状态
        for cage_id in self.cage_list_to_detect:
            cage_id_int = int(cage_id)
            self._completed_cages[cage_id_int] = False
            logger.debug(f"  初始化笼子状态: {cage_id_int} -> False")

        # ==================== 初始化全局检测字典 ====================
        mouse_cage_detect_dict = {}
        for cage_id in self.cage_list_to_detect:
            cage_id_int = int(cage_id)
            mouse_cage_detect_dict[cage_id_int] = {
                'cage_modules': {},
                'air_modules': {},
                'cage_is_valid': False,
                'update_time': time_util.get_format_from_time(time.time())
            }
        global_setting.set_setting("mouse_cage_detect_state_dict", mouse_cage_detect_dict)
        logger.debug(f"全局检测字典已初始化，共 {len(mouse_cage_detect_dict)} 个笼子")

        if self.detection_status_label:
            self.detection_status_label.setText("检测中...")

        self.detection_in_progress = True

        # ==================== 发送气路检测请求 ====================
        send_message_queue = global_setting.get_setting("send_message_queue", None)
        if not send_message_queue:
            logger.error("send_message_queue 未找到，无法发送报文")
            self.show_warning("错误", "消息队列未找到，请重启应用")
            return

        logger.info("=" * 80)
        logger.info(f"发送气路模块检测报文（UFC、UGC、ZOS）")
        logger.info("=" * 80)

        send_message_queue.put(ObjectQueueItem(
            origin="New_main_experiment_setting",
            to="main_monitor_data",
            title="detect_air_modules_only",
            data={
                'port': self.send_message['port'],
                'mouse_cage_index': None
            },
            time=time_util.get_format_from_time(time.time())
        ))

        logger.info(
            f"气路模块检测报文已发送 | "
            f"Port: {self.send_message['port']} | "
            f"Modules: {self.air_modules_to_detect}"
        )

        # ==================== 启动鼠笼检测（7秒延迟） ====================
        logger.info("✓ 气路检测请求已发送，7秒后启动笼内模块检测...")
        QTimer.singleShot(7000, self._detect_next_cage)

    def not_each_Mouse_Cage_detect_update_state(self, state_data):
        """
        更新气路模块检测状态（改用信号槽）

        当收到气路模块响应时，立即记录状态
        当3个模块全部收到时，立即强制结算气路检测
        """
        try:
            module_name = state_data.get('module_name', '')
            data_field = state_data.get('data', [])

            # ==================== 1. 判定有效性 ====================
            module_is_valid = bool(data_field) and len(data_field) > 0

            if module_is_valid and isinstance(data_field, list):
                for item in data_field:
                    if isinstance(item, dict):
                        value = item.get('value', '')
                        if 'Time OUT' in str(value) or '未获取到' in str(value):
                            module_is_valid = False
                            logger.warning(f"   [错误值] {value}")
                            break

            logger.critical(f"[判定] {module_name}: {'✓ 有效' if module_is_valid else '✗ 无效'}")

            # ==================== 2. 记录状态 ====================
            should_trigger_final = False

            with self.air_module_detection_lock:
                # 如果已结束则直接返回
                if self._air_detection_finished:
                    logger.debug(f"气路检测已结束，忽略 {module_name} 的回复")
                    return

                # 防御性检查：确保模块在字典中存在
                if module_name not in self.air_modules_completed:
                    logger.debug(f"{module_name} 字典项不存在，现在初始化")
                    self.air_modules_completed[module_name] = False
                    self.air_modules_detected[module_name] = False
                    self.air_modules_valid[module_name] = False

                # 如果已处理过则直接返回
                if self.air_modules_completed.get(module_name, False) is True:
                    logger.debug(f"{module_name} 已处理过")
                    return

                # ==================== 写入数据 ====================
                self.air_modules_completed[module_name] = True
                self.air_modules_detected[module_name] = True
                self.air_modules_valid[module_name] = module_is_valid

                # 计算字典中 Value 为 True 的数量
                received_count = sum(1 for v in self.air_modules_completed.values() if v)
                total_count = len(self.air_modules_to_detect)

                logger.critical(
                    f"[记录] {module_name} 已记录\n"
                    f"   状态: {'✓ 有效' if module_is_valid else '✗ 无效'}\n"
                    f"   进度: {received_count}/{total_count}"
                )

                # ==================== 检查是否全部齐了 ====================
                if received_count >= total_count:
                    logger.critical(
                        f"所有 {total_count} 个模块已齐，准备触发结算"
                    )
                    should_trigger_final = True

            # ==================== 3. 【关键】发射信号更新UI（而不是直接调用） ====================
            logger.info(f"发射信号: {module_name} -> {'有效' if module_is_valid else '无效'}")
            self.signal_air_module_update.emit(module_name, module_is_valid)

            # ==================== 4. 更新检测状态标签 ====================
            self.signal_detection_status_update.emit("检测中...")

            # ==================== 5. 强制刷新UI ====================
            self.signal_force_ui_refresh.emit()

            # ==================== 6. 如果全齐了，触发结算 ====================
            if should_trigger_final:
                logger.info("[全齐] 所有模块已到齐，立即触发结算...")
                QTimer.singleShot(100, self._process_air_detection_final_results)

        except Exception as e:
            logger.error(f"[处理异常] {e}", exc_info=True)

    def _process_air_detection_final_results(self):
        """
        气路检测的唯一终点 - 改用信号槽版本

        仅负责结算气路检测结果并更新UI
        不触发笼内检测，笼内检测由confirm_port()中的定时器控制
        """
        try:
            # ==================== 1. 锁内提前设置标志位（核心：优先防重复） ====================
            with self.air_module_detection_lock:
                # 第一时间检查：已完成/已有缓存/UI已更新，直接返回，不执行任何操作
                if self._air_detection_finished or self._air_detection_final_result_cached or self._air_ui_has_been_updated:
                    logger.debug(
                        f"[防重复] 检测已完成（finished={self._air_detection_finished}，cached={bool(self._air_detection_final_result_cached)}，ui_updated={self._air_ui_has_been_updated}），直接返回")
                    return

                # 提前标记为已完成（锁内），确保超时入口能立即检测到
                self._air_detection_finished = True
                self.air_detection_complete_event.set()

                logger.critical("[结算] 气路检测进入结算阶段...")

                # 锁内创建永久快照
                air_modules_valid_snapshot = dict(self.air_modules_valid)
                air_modules_completed_snapshot = dict(self.air_modules_completed)

                # 补全缺失的键
                for module_name in ['UFC', 'UGC', 'ZOS']:
                    if module_name not in air_modules_valid_snapshot:
                        air_modules_valid_snapshot[module_name] = False
                    if module_name not in air_modules_completed_snapshot:
                        air_modules_completed_snapshot[module_name] = False

            # ==================== 2. 检查是否已有正确UI更新，禁止重复修改 ====================
            if self._air_ui_has_been_updated:
                logger.debug("[防重复] UI已被正确更新，禁止二次修改")
                return

            # ==================== 3. 处理结果（仅执行一次） ====================
            completed_modules = [k for k, v in air_modules_completed_snapshot.items() if v]

            logger.critical(
                f"\n{'=' * 80}\n"
                f"[结算开始]\n"
                f"预期模块: {self.air_modules_to_detect}\n"
                f"已收到: {completed_modules}\n"
                f"真值表: {air_modules_valid_snapshot}\n"
            )

            final_valid_list = []
            final_invalid_list = []
            final_no_response_list = []

            for module_name in self.air_modules_to_detect:
                has_responded = air_modules_completed_snapshot.get(module_name, False)
                is_valid = air_modules_valid_snapshot.get(module_name, False)

                if not has_responded:
                    logger.warning(
                        f"✗ [未响应] 模块 {module_name} 最终未响应"
                    )
                    # 使用信号槽确保UI更新
                    self.signal_air_module_update.emit(module_name, False)
                    final_no_response_list.append(module_name)
                else:
                    logger.info(
                        f"✓ [已回复] 模块 {module_name} 已回复，状态: {'有效' if is_valid else '无效'}"
                    )
                    # 使用信号槽确保UI更新
                    self.signal_air_module_update.emit(module_name, is_valid)
                    if is_valid:
                        final_valid_list.append(module_name)
                    else:
                        final_invalid_list.append(module_name)

            # ==================== 强制UI刷新 ====================
            QTimer.singleShot(50, self.signal_force_ui_refresh.emit)

            self._air_detection_final_result_cached = {
                'valid': final_valid_list,
                'invalid': final_invalid_list,
                'no_response': final_no_response_list,
                'snapshot': air_modules_valid_snapshot,
                'completed': completed_modules
            }
            self._air_ui_has_been_updated = True  # 标记UI已正确更新，禁止所有后续入口修改

            logger.critical(
                f"\n{'=' * 80}\n"
                f"[气路检测完成]\n"
                f"有效模块: {final_valid_list}\n"
                f"无效模块: {final_invalid_list}\n"
                f"未响应: {final_no_response_list}\n"
                f"{'=' * 80}\n"
            )

            # ==================== 更新总体检测状态 ====================
            self.signal_detection_status_update.emit("✓ 气路检测完成")

        except Exception as e:
            logger.error(f"[结算异常] {e}", exc_info=True)
            # 异常时也要标记所有标志位，防止死锁
            with self.air_module_detection_lock:
                self._air_detection_finished = True
                self._air_ui_has_been_updated = True

    # ========== 笼内检测流程 ==========
    def _detect_next_cage(self):
        """
        检测笼内模块（修复版：完全分离索引推进逻辑）
        确保笼号正确传递给报文
        """
        try:
            # ==================== 1. 边界检查 ====================
            if self.current_detecting_index >= len(self.cage_list_to_detect):
                logger.critical(
                    f"\n{'=' * 80}\n"
                    f"[检测完成] 所有 {len(self.cage_list_to_detect)} 个笼子已检测完毕\n"
                    f"{'=' * 80}\n"
                )
                self._cleanup_all_timers()
                self.detection_in_progress = False

                if self.detection_status_label:
                    self.detection_status_label.setText("✓ 检测完成，可选择笼子进行配置")

                if self.config_btn:
                    self.config_btn.setEnabled(True)
                return

            # ==================== 2. 获取当前笼子（修复：确保类型一致） ====================
            cage_number = int(self.cage_list_to_detect[self.current_detecting_index])

            logger.critical(
                f"\n{'=' * 80}\n"
                f"[开始检测笼子] {cage_number}\n"
                f"索引: {self.current_detecting_index}/{len(self.cage_list_to_detect) - 1}\n"
                f"笼子列表: {self.cage_list_to_detect}\n"
                f"{'=' * 80}\n"
            )

            # ==================== 3. 防重复检测 ====================
            if self._completed_cages.get(cage_number, False) is True:
                logger.warning(f"笼子 {cage_number} 已处理完成，跳过")
                return

            # ==================== 4. 标记为检测中并更新UI ====================
            self._update_cage_detecting(cage_number)

            # ==================== 5. 发送检测报文 ====================
            send_message_queue = global_setting.get_setting("send_message_queue", None)

            if not send_message_queue:
                logger.error(f"send_message_queue 未找到")
                self._completed_cages[cage_number] = True
                return

            try:
                # 确保笼号正确传入
                detect_item = ObjectQueueItem(
                    origin="New_main_experiment_setting",
                    to="main_monitor_data",
                    title="detect_cage_modules_only",
                    data={
                        'gids': [cage_number],  # 单个笼子的笼号
                        'cage_index': cage_number  # 笼子索引（与gids一致）
                    },
                    time=time_util.get_format_from_time(time.time())
                )
                send_message_queue.put(detect_item)

                logger.critical(
                    f"笼子 {cage_number} 检测报文已发送\n"
                    f"报文内容: gids=[{cage_number}], cage_index={cage_number}"
                )

            except Exception as queue_error:
                logger.error(f"笼子 {cage_number} 检测报文发送异常: {queue_error}")
                self._completed_cages[cage_number] = True
                return

            # ==================== 6. 设置超时（15秒） ====================
            self._set_cage_detection_timeout(cage_number, timeout_seconds=15)

        except Exception as e:
            logger.error(f"笼内检测流程异常: {e}", exc_info=True)

    def _set_cage_detection_timeout(self, cage_number, timeout_seconds=10):
        """为单个笼子设置检测超时"""
        if cage_number in self.cage_detection_timers:
            self.cage_detection_timers[cage_number].stop()

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._on_cage_detection_timeout(cage_number))
        timer.start(timeout_seconds * 1000)

        self.cage_detection_timers[cage_number] = timer
        logger.debug(f"✓ 笼 {cage_number} 的 {timeout_seconds}秒检测超时已设置")

    def _on_cage_detection_timeout(self, cage_number):
        """笼子检测超时处理（修复版：确保索引稳定推进）"""
        try:
            cage_number_int = int(cage_number)

            # 清理该笼子的计时器
            if cage_number_int in self.cage_detection_timers:
                self.cage_detection_timers.pop(cage_number_int)

            # ==================== 防止重复处理 ====================
            if self._completed_cages.get(cage_number_int, False) is True:
                logger.warning(f"笼子 {cage_number_int} 已处理过，跳过超时处理")
                return

            logger.warning(
                f"\n{'=' * 80}\n"
                f"[超时] 笼子 {cage_number_int} 检测超时（15秒）\n"
                f"{'=' * 80}\n"
            )

            # ==================== 标记完成 ====================
            self._completed_cages[cage_number_int] = True
            self._update_cage_detection_complete(cage_number_int)

            # ==================== 【关键】推进索引到下一个笼子 ====================
            prev_index = self.current_detecting_index
            self.current_detecting_index += 1

            logger.critical(
                f"索引推进: {prev_index} → {self.current_detecting_index}\n"
                f"当前完成笼子: {cage_number_int}\n"
                f"下一个将检测: {self.cage_list_to_detect[self.current_detecting_index] if self.current_detecting_index < len(self.cage_list_to_detect) else '无'}\n"
            )

            # ==================== 触发下一个笼子检测 ====================
            QTimer.singleShot(300, self._detect_next_cage)

        except Exception as e:
            logger.error(f"处理笼子 {cage_number} 超时异常: {e}", exc_info=True)
            # 异常兜底
            try:
                self.current_detecting_index += 1
            except:
                pass
            QTimer.singleShot(300, self._detect_next_cage)

    def _update_cage_detecting(self, cage_number):
        """更新笼子为检测中状态"""
        try:
            cage_number_int = int(cage_number)
            cage_list_widget = self._get_cage_list_widget()
            if not cage_list_widget:
                return

            for i in range(cage_list_widget.count()):
                item = cage_list_widget.item(i)
                if not item:
                    continue

                item_cage_id = int(item.data(Qt.ItemDataRole.UserRole))
                if item_cage_id != cage_number_int:
                    continue

                item_text = f"鼠笼 {cage_number_int} - 检测中..."
                item.setText(item_text)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setBackground(QtGui.QColor(255, 255, 240))
                item.setForeground(QtGui.QColor(184, 134, 11))

                cage_list_widget.viewport().update()
                logger.debug(f"✓ 笼子 {cage_number_int} UI已更新为检测中")
                break

        except Exception as e:
            logger.error(f"更新笼子 {cage_number} 为检测中状态失败: {e}", exc_info=True)

    def _cleanup_all_timers(self):
        """清理所有计时器"""
        for cage_num in list(self.cage_detection_timers.keys()):
            timer = self.cage_detection_timers.pop(cage_num)
            if timer and timer.isActive():
                timer.stop()

    # ========== 状态更新回调 ==========

    def each_Mouse_Cage_detect_update_state(self, state_data):
        """
        更新鼠笼内模块检测状态
        """
        try:
            logger.critical(f"笼内模块检测结果:\n{state_data}\n")

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
                f"  有效性: {dict([(k, v) for k, v in cage_modules.items()])}\n"
                f"  判定: {'完整' if all_received else '不完整'} - {'有效' if all_valid else '无效'}"
            )

            global_setting.set_setting("mouse_cage_detect_state_dict", mouse_cage_detect_dict)

            # ==================== 实时更新UI ====================
            self._update_cage_list_display(mouse_cage_number, mouse_cage_detect_dict[mouse_cage_number])

            # ==================== 笼子完整则调用完成处理 ====================
            if all_received:
                self._on_cage_complete(mouse_cage_number, cage_is_valid)

        except Exception as e:
            logger.error(f"更新笼内模块状态时出错: {e}", exc_info=True)

    def _on_cage_complete(self, cage_number, cage_is_valid):
        """
        笼子检测完成处理
        """
        if threading.current_thread() != threading.main_thread():
            QTimer.singleShot(0, lambda: self._on_cage_complete(cage_number, cage_is_valid))
            return

        try:
            cage_number_int = int(cage_number)

            logger.critical(
                f"\n{'=' * 80}\n"
                f"笼子 {cage_number_int} 检测完成\n"
                f"有效性: {'✓ 通过' if cage_is_valid else '✗ 失败'}\n"
                f"{'=' * 80}\n"
            )

            # ==================== 1. 立即停止计时器 ====================
            if cage_number_int in self.cage_detection_timers:
                timer = self.cage_detection_timers.pop(cage_number_int)
                timer.stop()
                timer.deleteLater()
                logger.debug(f"笼子 {cage_number_int} 的超时计时器已停止")

            # ==================== 2. 防止重复进入 ====================
            if self._completed_cages.get(cage_number_int, False) is True:
                logger.warning(f"笼子 {cage_number_int} 已处理过，跳过")
                return

            self._completed_cages[cage_number_int] = True
            logger.debug(f"笼子 {cage_number_int} 标记为已完成")

            # ==================== 3. 更新UI ====================
            self._update_cage_detection_complete(cage_number_int)


        except Exception as e:
            logger.error(f"笼子 {cage_number} 完成处理异常: {e}", exc_info=True)

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
                    received_modules = list(cage_modules.keys())
                    failed_modules = [name for name, status in cage_modules.items() if not status]

                    if received_modules:
                        if failed_modules:
                            failed_str = ", ".join(sorted(failed_modules))
                            status_text = f"✗ 检测异常 - 失败模块: {failed_str}"
                        else:
                            received_str = ", ".join(sorted(received_modules))
                            missing = {'ENM', 'EM', 'DWM', 'WM'} - set(received_modules)
                            missing_str = ", ".join(sorted(missing))
                            status_text = f"检测不完整 - 已收到: {received_str}, 缺少: {missing_str}"
                    else:
                        status_text = f"✗ 检测失败 - 无响应"

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