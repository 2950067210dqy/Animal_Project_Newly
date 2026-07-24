import importlib
import json
import os
import sqlite3
import threading
import time
from json import JSONDecodeError

from PyQt6.QtGui import QFont
from PyQt6 import QtCore
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMessageBox, QVBoxLayout, QToolBar, QTabWidget, QDialog, QMenu, QMenuBar, QWidget, \
    QApplication, QCheckBox
from loguru import logger

from PyQt6.QtCore import Qt
from Service import main_monitor_data, main_deep_camera, main_infrared_camera
from Service.UFC_UGC_ZOS_Service.function.gas_path_system.Gas_path_system import ZOS_gas_path_system, \
    UFC_gas_path_system, UGC_gas_path_system
from Service.UFC_UGC_ZOS_Service.index.UFC_UGC_ZOS_index import UFC_UGC_ZOS_index
from my_abc.BaseModule import BaseModule
from public.component.Guide_tutorial_interface.Tutorial_Manager import TutorialManager
from public.component.custom_status_bar import CustomStatusBar
from public.component.dialog.custom.calibration_detail_Dialog import CalibrationDialog
from public.component.dialog.custom.loading_dialog_seconds import AnimatedLoadingDialog
from public.component.mask.LoadingMask import LoadingContext
from public.config_class.App_Setting import AppSettings
from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from public.entity.enum.Public_Enum import BaseInterfaceType, AppState, Tutorial_Type
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Modbus.New_Mod_Bus import ModbusRTUMasterNew
from public.function.promise.AsyPromise import AsyPromise
from public.util.custom_data_file_util import custom_data_file_util
from public.util.time_util import time_util
from theme.ThemeQt6 import ThemedWindow
from ui.MainWindow import Ui_MainWindow
#logger = logger.bind(category="gui_logger")

class Start_experiment_thread(MyQThread):
    def __init__(self,name,window):
        super().__init__(name=name)
        self.window:MainWindow_Index = window
    def dosomething(self):
        self.window.start_experiment_handle()
        self.stop()
        pass
class Stop_experiment_thread(MyQThread):
    def __init__(self,name,window):
        super().__init__(name)
        self.window:MainWindow_Index = window
    def dosomething(self):
        self.window.stop_experiment_handle()
        self.stop()
class read_queue_data_Thread(MyQThread):
    def __init__(self, name,window=None):
        super().__init__(name)
        self.queue = None
        self.camera_list = None
        self.window:MainWindow_Index = window

        # 停止实验用到的 返回状态，当深度相机、红外相机、整体气路、UFC气路、ugc气路、zos气路、鼠笼内、存储数据都发过返回消息则关闭关闭实验窗口
        self.old_Stop_experiment_status_text_reTurn =None
        self.old_stop_status_counts = 0
        self.old_stop_status_max = 7
        pass

    def dosomething(self):
        if self.queue and  not self.queue.empty():
            try:
                message: ObjectQueueItem = self.queue.get()
            except Exception as e:
                logger.error(f"{self.name}发生错误{e}")
                return

            if message is not None and message.is_Empty():
                return
            if message is not None and isinstance(message, ObjectQueueItem) and message.to=='MainWindow_index':
                # logger.error(f"{self.name}_get_message:{message}")
                match message.title:
                    case "gap_system_running_state":
                        if message.data  and self.window:
                            #  更新气路运行消息
                            # 将运行信息放入status栏中
                            self.window.status_bar.update_tip(message.data)
                            if self.window.start_dialog is not None :
                                self.window.start_dialog.insert_data_signal.emit(f"{message.data} ")
                                # self.window.start_dialog.update_progress_value(1)
                            pass


                        pass
                    case "mouse_cage_inner_module_running_state":
                        #鼠笼环境内部模块运行情况
                        if message.data and self.window:
                            # 将运行信息放入status栏中
                            self.window.status_bar.update_tip(message.data)
                            pass
                    case "epoch_running_state":
                        # 一轮模块数据运行情况
                        if message.data and self.window:
                            # 将运行信息放入status栏中
                            self.window.status_bar.update_tip(message.data)
                            pass
                    case 'close_start_experiment_dialog':
                        if self.window is not None and self.window.start_dialog is not None:
                            self.window.start_dialog.update_progress_value(self.window.start_dialog.progress_max)
                        if self.window is not None:
                            # ★ 标记成功，取消备用超时计时器
                            self.window._gas_path_success = True
                            if self.window._gas_path_timeout_timer is not None:
                                self.window._gas_path_timeout_timer.stop()
                                self.window._gas_path_timeout_timer = None
                            # 显示3秒成功提示，之后恢复"正在监控数据"
                            self.window.show_temp_status_tip_signal.emit("气路启动成功！", "#00aa00", 3000)
                            QTimer.singleShot(3100,
                                              lambda: self.window.status_bar.update_status() if self.window else None)
                    case "stop_deep_camera_return" |"stop_infrared_camera_return"|"stop_gap_system_return"|"stop_ufc_gap_system_return"|"stop_ugc_gap_system_return"|"stop_zos_gap_system_return"|"stop_monitor_data_return"|"stop_show_info_except_status_counts":
                        if message.data and self.window:
                            #  更新气路运行消息
                            # 将运行信息放入status栏中
                            self.window.status_bar.update_tip(message.data)
                            if self.window.stop_dialog is not None:
                                self.window.stop_dialog.insert_data_signal.emit(f"{message.data} ")
                                # self.window.start_dialog.update_progress_value(1)
                            if message.title !="stop_show_info_except_status_counts":
                                #不为普通消息  且 当深度相机、红外相机、气路、鼠笼内、存储数据都发过返回消息则关闭关闭实验窗口
                                if self.old_Stop_experiment_status_text_reTurn is  None:
                                    self.old_Stop_experiment_status_text_reTurn = message.title
                                    self.old_stop_status_counts += 1
                                elif message.title !=self.old_Stop_experiment_status_text_reTurn:
                                    self.old_Stop_experiment_status_text_reTurn=message.title
                                    self.old_stop_status_counts += 1

                            if self.old_stop_status_counts >= self.old_stop_status_max:
                                # 停止完成，关闭停止实验窗口
                                self.old_Stop_experiment_status_text_reTurn = None
                                self.old_stop_status_counts =0

                                QTimer.singleShot(5000,self.close_stop_experiment_dialog)

                        pass
                    case 'close_stop_experiment_dialog':
                        # 停止完成，关闭停止实验窗口
                        self.close_stop_experiment_dialog()
                    case 'calibration_msg':
                        """
                        标定的消息
                        """
                        if self.window is not None:
                            self.window.cache_calibration_detail_log(message.data, has_time=True)
                    case 'set_start_zero_calibration_time':
                        """
                        设置开始校准零点
                        data为time
                        """
                        if self.window is not None:
                            self.window.calibration_detail_zero_start_time = message.data
                            self.window.calibration_detail_status_text = "零点标定"
                            if self.window.calibration_details_windows is not None:
                                self.window.calibration_details_windows.updateZeroStartTime(message.data, event_time=message.data)
                                self.window.calibration_details_windows.updateStatus("零点标定", event_time=message.data)

                    case 'set_stop_zero_calibration_time':
                        """
                        设置结束校准零点
                        data为time
                        """
                        if self.window is not None:
                            self.window.calibration_detail_zero_end_time = message.data
                            self.window.calibration_detail_status_text = "未标定"
                            if self.window.calibration_details_windows is not None:
                                self.window.calibration_details_windows.updateZeroEndTime(message.data, event_time=message.data)
                                self.window.calibration_details_windows.updateStatus("未标定", event_time=message.data)
                    case 'set_start_span_calibration_time':
                        """
                        设置开始校准span
                        data为time
                        """
                        if self.window is not None:
                            self.window.calibration_detail_span_start_time = message.data
                            self.window.calibration_detail_status_text = "量程标定"
                            if self.window.calibration_details_windows is not None:
                                self.window.calibration_details_windows.updateSpanStartTime(message.data, event_time=message.data)
                                self.window.calibration_details_windows.updateStatus("量程标定", event_time=message.data)
                    case 'set_stop_span_calibration_time':
                        """
                        设置结束校准span
                        data为time
                        """
                        if self.window is not None:
                            self.window.calibration_detail_span_end_time = message.data
                            self.window.calibration_detail_status_text = "未标定"
                            if self.window.calibration_details_windows is not None:
                                self.window.calibration_details_windows.updateSpanEndTime(message.data, event_time=message.data)
                                self.window.calibration_details_windows.updateStatus("未标定", event_time=message.data)
                    case 'set_start_air_calibration_time':
                        if self.window is not None:
                            self.window.calibration_detail_zero_start_time = message.data
                            self.window.calibration_detail_status_text = "Air空气校准"
                            if self.window.calibration_details_windows is not None:
                                self.window.calibration_details_windows.updateZeroStartTime(message.data, event_time=message.data)
                                self.window.calibration_details_windows.updateStatus("Air空气校准", event_time=message.data)
                    case 'set_stop_air_calibration_time':
                        if self.window is not None:
                            self.window.calibration_detail_zero_end_time = message.data
                            self.window.calibration_detail_status_text = "未标定"
                            if self.window.calibration_details_windows is not None:
                                self.window.calibration_details_windows.updateZeroEndTime(message.data, event_time=message.data)
                                self.window.calibration_details_windows.updateStatus("未标定", event_time=message.data)
                    case 'set_calibration_values':
                        """
                        设置校准窗口显示值
                        data:{"oxygen_value":0,"carbon_value":0,"oxygen_pressure_value":0}
                        """
                        if self.window is not None and self.window.calibration_details_windows is not None and message.data is not None:
                            self.window.calibration_details_windows.updateO2Current(message.data.get("oxygen_value", 0), event_time=message.time)
                            self.window.calibration_details_windows.updateCO2Current(
                                message.data.get("carbon_value", 0), event_time=message.time)
                            self.window.calibration_details_windows.updatePressureCurrent(
                                message.data.get("oxygen_pressure_value", 0), event_time=message.time)
                    case _:
                        pass

            else:
                # 把消息放回去
                self.queue.put(message)
    def close_stop_experiment_dialog(self):
        if self.window is not None and self.window.stop_dialog is not None:
            self.window.stop_dialog.update_progress_value(self.window.stop_dialog.progress_max)


class PeriodicExcelExportThread(threading.Thread):
    def __init__(self, db_path, export_file_path, callback=None):
        super().__init__(name="periodic_excel_export_thread", daemon=True)
        self.db_path = db_path
        self.export_file_path = export_file_path
        self.callback = callback

    @staticmethod
    def _create_snapshot(source_db_path, snapshot_db_path):
        source_conn = None
        snapshot_conn = None
        try:
            source_conn = sqlite3.connect(source_db_path, timeout=30.0)
            snapshot_conn = sqlite3.connect(snapshot_db_path, timeout=30.0)
            source_conn.backup(snapshot_conn)
        finally:
            if snapshot_conn is not None:
                snapshot_conn.close()
            if source_conn is not None:
                source_conn.close()

    def run(self):
        snapshot_db_path = f"{self.db_path}.{int(time.time() * 1000)}.snapshot.db"
        success = False
        message = ""
        try:
            if not os.path.exists(self.db_path):
                raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")

            export_dir = os.path.dirname(self.export_file_path)
            if export_dir:
                os.makedirs(export_dir, exist_ok=True)

            self._create_snapshot(self.db_path, snapshot_db_path)
            success = custom_data_file_util.export_data_to_csv(
                export_file_path=self.export_file_path,
                file_path=snapshot_db_path,
                show_success_message=False,
                use_atomic_replace=True
            )
            message = f"定时导出实验数据{'成功' if success else '失败'}: {os.path.basename(self.export_file_path)}"
        except Exception as e:
            message = f"定时导出实验数据失败: {e}"
            logger.error(message)
        finally:
            if os.path.exists(snapshot_db_path):
                try:
                    os.remove(snapshot_db_path)
                except OSError as remove_error:
                    logger.error(f"删除数据库快照失败: {remove_error}")

            if self.callback is not None:
                self.callback(success, message)


read_queue_data_thread = read_queue_data_Thread(name="MainWindow_index_read_queue_data_thread")
class MainWindow_Index(ThemedWindow):
    # 根据程序状态来改变是否可以点击的组件
    change_enable_component_app_state_signal = QtCore.pyqtSignal()
    # 设备配置页校准选择变化信号 (是否已选择, 是否校准)
    calibration_selection_changed_signal = QtCore.pyqtSignal(bool, str)
    # 显示校准详情dialog的信号
    show_calibration_window_signal = QtCore.pyqtSignal(dict)
    # 释放校准详情dialog的信号
    release_calibration_window_signal = QtCore.pyqtSignal()
    # 线程安全的状态栏提示信号
    update_status_tip_signal = QtCore.pyqtSignal(str)
    # 临时覆盖状态栏中间文字的信号 (message, color, duration_ms)
    show_temp_status_tip_signal = QtCore.pyqtSignal(str, str, int)
    def close_window_handle(self):
        """
        关闭窗口执行的事件
        :return:
        """
        state = global_setting.get_setting("app_state", None)
        # 如果在开始实验期间关闭窗口
        if state is not None and state ==AppState.MONITORING:
            # 停止实验
            self.stop_experiment()
        # 关闭所有串口

    def closeEvent(self, event):
        app_state = global_setting.get_setting("app_state", AppState.INITIALIZED)
        if len(self.open_windows)!=0:
            # 可选择使用 QMessageBox 来确认是否关闭
            if app_state == AppState.MONITORING:
                message="当前正在实验中，且还有其他子窗口未关闭,退出程序将停止实验，你确定要退出程序吗？"
            else:
                message ="当前还有其他子窗口未关闭，你确定要退出程序吗？"
            reply = QMessageBox.question(self, '关闭窗口',
                                         message,
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                for window in self.open_windows:
                    self.close_window_handle()
                    window.close()
                # 关闭所有窗口
                QApplication.closeAllWindows()
                event.accept()  # 关闭窗口
            else:
                event.ignore()  # 忽略关闭事件
        else:
            # 可选择使用 QMessageBox 来确认是否关闭
            if app_state == AppState.MONITORING:
                message = "当前正在实验中,退出程序将停止实验，你确定要退出程序吗？"
            else:
                message = "你确定要退出程序吗？"
            reply = QMessageBox.question(self, '关闭窗口',
                                         message,
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.close_window_handle()
                # 关闭所有窗口
                QApplication.closeAllWindows()
                event.accept()  # 关闭窗口
            else:
                event.ignore()  # 忽略关闭事件
        pass
    def setup_tutorial(self):
        #实例化提示引导器 下面式实例化模板
        if self.tutorial:
            self.tutorial.end_tutorial()

        self.tutorial = TutorialManager(self, "MainWindow_index", Tutorial_Type.ARROW_GUIDE, global_setting.get_setting("app_setting", AppSettings()))

        # 连接教程完成信号
        self.tutorial.tutorial_completed.connect(self.on_tutorial_completed)

        # 添加更详细的引导步骤
        actions = self.menuBar().actions()
        widgets = self.findChildren(QObject, "temp_deleted_widget")
        for action in actions:
            action:QAction
            menu:QMenu = action.menu()
            if menu:
                # 获取菜单栏中的按钮控件
                geometry = self.menuBar().actionGeometry(action)
                if not widgets:
                    widget =QWidget()
                    widget.setParent(self)
                    widget.setGeometry(geometry)
                    widget.setObjectName("temp_deleted_widget")

                    # 对 file_menu 进行操作
                    self.tutorial.add_step(widget,
                                           f"单击此按钮是{action.text()}\n{menu.toolTip()}")
                else:
                    widget =widgets.pop(0)
                    widget.show()
                    self.tutorial.add_step(widget,
                                           f"单击此按钮是{action.text()}\n{menu.toolTip()}")
        for tool_bar_action in self.tool_bar_actions:
            if isinstance(tool_bar_action['action'], QAction):
                self.tutorial.add_step(tool_bar_action['action'].associatedObjects()[1],
                                       f"单击此按钮是{tool_bar_action['text']}\n{tool_bar_action['tip']}")
            else:
                self.tutorial.add_step(tool_bar_action['action'],
                                       f"单击此是{tool_bar_action['text']}\n{tool_bar_action['tip']}")
        # 状态栏提示
        self.tutorial.add_step(self.status_bar.time_label,
                               f"显示当前时间。")
        self.tutorial.add_step(self.status_bar.app_status_label,
                               f"显示当前程序状态 。\n 1.INITIALIZED: 初始化状态\n 2.APPLYING: 应用实验状态\n 3.CONFIGURING: 设备配置状态\n 4.MONITORING: 开始监测数据状态")
        self.tutorial.add_step(self.status_bar.status_label,
                               f"显示当前实验状态。\n1.未开始实验。2.开始实验。3.暂停实验。4.停止实验")
        self.tutorial.add_step(self.status_bar.tip_label,
                               f"显示当前帮助消息。")
        self.tutorial.add_step(self.status_bar.setting_file_name_label,
                               f"显示当前实验设置文件路径。")

        self.tutorial.add_step(self.status_bar.progress_bar,
                               f"显示进度条。")
        #步骤提示
        widgets = self.findChildren(QObject, "temp_deleted_widget")
        for action in actions:
            action: QAction
            menu: QMenu = action.menu()
            if menu:
                # 获取菜单栏中的按钮控件
                geometry = self.menuBar().actionGeometry(action)
                if not widgets:
                    widget = QWidget()
                    widget.setParent(self)
                    widget.setGeometry(geometry)
                    widget.setObjectName("temp_deleted_widget")

                    # 对 file_menu 进行操作
                    self.tutorial.add_step(widget,
                                           f"不知道怎么操作？请跟着步骤指引\n1.单击{action.text()}菜单\n2.在单击打开或导入")
                else:
                    widget = widgets.pop(0)
                    widget.show()
                    self.tutorial.add_step(widget,
                                           f"不知道怎么操作？请跟着步骤指引\n1.单击{action.text()}菜单\n2.在单击打开或导入")
            break
        self.tutorial.add_step(self.status_bar.tip_btn,
                               f"Tips：\n如果还不会操作，可再次单击该按钮查看教程。")
    def __init__(self):
        super().__init__()
        # 开始实验dialog
        self.start_dialog:AnimatedLoadingDialog=None
        # 停止实验dialog
        self.stop_dialog:AnimatedLoadingDialog=None
        # ★ 新增：气路成功标志 & 备用超时计时器
        self._gas_path_success = False
        self._gas_path_timeout_timer = None
        #暂停实验标志位
        self.is_paused = False
        # 点击开始实验 接受数据和存储数据的线程
        self.store_thread_sub=None
        self.send_thread_sub=None
        self.read_queue_data_thread_sub=None
        self.add_message_thread_sub=None
        self.ufc_ugc_zos:UFC_UGC_ZOS_index=None
        self.ufc_ugc_zos_thread=None
        # 深度相机线程
        self.deep_camera_thread_sub_list=[]
        self.deep_camera_read_queue_data_thread_sub=None
        self.deep_camera_delete_file_thread_sub=None
        # 红外相机线程
        self.infrared_camera_thread_sub_list = []
        self.infrared_camera_read_queue_data_thread_sub = None
        self.infrared_camera_delete_file_thread_sub = None
        # tool——bar-action 工具栏的action [{'obj_name':'','name';",'action':QAction,'tip':''}]
        self.tool_bar_actions = []
        self.menu_bar_actions = []
        # 添加动态工具栏相关属性
        self.dynamic_tool_bar_actions = []
        self.dynamic_toolbar_separators = []
        self.static_toolbar_actions = []
        self.current_active_menu_id = None
        # 模块
        self.modules =[]
        # 正在显示的Widget
        self.active_module_widgets:[BaseModule]=[]
        # 打开的窗口
        self.open_windows:[BaseModule]=[]
        # 校准气路的窗口
        self.calibration_details_windows: CalibrationDialog = None
        self.calibration_detail_log_buffer = []
        self.calibration_detail_status_text = None
        self.calibration_detail_zero_start_time = None
        self.calibration_detail_zero_end_time = None
        self.calibration_detail_span_start_time = None
        self.calibration_detail_span_end_time = None
        # 工具栏
        self.toolbar = None
        #状态栏
        self.status_bar:CustomStatusBar = None
        # 内容layout
        self.content_layout :QVBoxLayout =None
        # tab_widget
        self.tab_widget :QTabWidget =None
        # 实例化ui
        self._init_ui()
        self.periodic_export_lock = threading.Lock()
        self.periodic_export_in_progress = False
        self.periodic_export_thread = None
        self.periodic_export_timer = QTimer(self)
        self.periodic_export_timer.setSingleShot(False)
        self.periodic_export_timer.setInterval(self._get_periodic_export_interval_ms())
        self.periodic_export_timer.timeout.connect(self.trigger_periodic_excel_export)
        # 实例化自定义ui
        self._init_customize_ui()
        # 实例化功能
        self._init_function()
        # 加载qss样式表
        self._init_custom_style_sheet()
        self._retranslateUi()
        # 实例化提示器
        self.setup_tutorial()
        # 自动启动提示教程 如果有提示页面的话
        QTimer.singleShot(400, self.start_tutorial_if_exists)
        pass
    # 实例化ui
    def _init_ui(self, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        # 设置窗口大小为屏幕大小
        self.setGeometry(global_setting.get_setting("screen"))
        self.setObjectName("mainWindow_Index")
        pass
    def _init_customize_ui(self):
        global read_queue_data_thread
        read_queue_data_thread.queue = global_setting.get_setting("queue",None)
        read_queue_data_thread.window=self
        read_queue_data_thread.start()
        self.content_layout = self.findChild(QVBoxLayout,"content_layout")
        self.tab_widget:QTabWidget = self.findChild(QTabWidget,"tab_widget")
        # 启用标签关闭按钮
        self.tab_widget.setTabsClosable(True)
        # 允许标签拖动重新排序
        self.tab_widget.setMovable(True)
        # 连接标签关闭信号
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        # 加载模块
        self.modules = self.load_modules()
        # 实例化菜单
        # [{id:0,text:"文件"},....]
        menu_name=global_setting.get_setting("configer")['menu']['menu_name']
        self.menu_name = None
        if menu_name is not None and menu_name != "":
            try:
                self.menu_name =  json.loads(menu_name)
            except JSONDecodeError  as e:
                logger.error(f"读取菜单json字符串解析错误：{e}")
                self.menu_name = None
            except Exception as e:
                logger.error(f"{e}")
                self.menu_name = None
            if self.menu_name is not None:
                # 创建菜单栏
                self.create_menu_bar()
                self.menuBar().setStyleSheet("""
                    QMenuBar{
                        font-size:15px;
                    }
                    QMenuBar::item {
                        font-size: 15px;
                        padding: 4px 10px;
                    }
                """)
            pass
        # 创建工具栏
        self.create_tool_bar()
        # 初始化自定义状态栏
        self.status_bar = CustomStatusBar(self)
        self.setStatusBar(self.status_bar)
        super()._init_customize_ui()
        pass
    def _init_function(self):
        # 改变组件是否被点击
        self.change_enable_component_app_state()
        # 连接信号
        self.change_enable_component_app_state_signal.connect(self.change_enable_component_app_state)
        self.show_calibration_window_signal.connect(self.show_calibration_windows)
        self.release_calibration_window_signal.connect(self.release_calibration_windows)
        # 新增连接
        self.update_status_tip_signal.connect(self.status_bar.update_tip)
        self.show_temp_status_tip_signal.connect(self.status_bar.show_temp_tip)
        pass
    # 创建工具栏
    def create_tool_bar(self):
        # 创建 QToolBar
        self.toolbar = QToolBar("Toolbar")

        # 设置工具栏样式为图标在左，文字在右
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar.setIconSize(QtCore.QSize(48, 48))
        self.toolbar.setMinimumHeight(70)

        self.addToolBar(self.toolbar)

        # 初始化动态内容相关列表
        self.dynamic_tool_bar_actions = []
        self.dynamic_toolbar_separators = []
        self.current_active_menu_id = None

        # ==================== 创建通用功能按钮 ====================
        # 定义工具栏按钮数据
        static_buttons = [
            {
                "name": "窗口变换",
                "short_name": "变换",
                "obj_name": "window_exchange",
                "type": "button",
                "icon": "⇄",  # 或使用图标文件: ":/icons/exchange.png"
                "callback": self.exchange_widget_and_window,
                "app_state": AppState.INITIALIZED,
                "tip": "单击此按钮会将打开的窗口变成内嵌抽屉页。",
                "disabled": False,
                "separator_before": False,
                "separator_after": True
            },
            {
                "name": "更改主题颜色",
                "short_name": "主题",
                "obj_name": "toggle_mode",
                "type": "button",
                "icon": "🌓",
                "callback": self.toggle_theme,
                "app_state": AppState.INITIALIZED,
                "tip": "单击此按钮会将程序的主题颜色变换黑色和白色",
                "disabled": False,
                "separator_before": False,
                "separator_after": True
            },

            {
                "name": "开始实验",
                "short_name": "开始",
                "obj_name": "start_experiment",
                "type": "button",
                "icon": "▶",
                "callback": self.start_experiment,
                "app_state": AppState.CONFIGURING,
                "tip": "单击此按钮会将开始实验，但是必须等待配置完成才能单击该按钮。",
                "disabled": False,
                "separator_before": False,
                "separator_after": False
            },
            {
                "name": "开始实验时校准气体",
                "short_name": "校准",
                "obj_name": "calibration_gas",
                "type": "button",
                "icon": "📏",
                "callback": self.calibration_gas_state_change,
                "app_state": AppState.INITIALIZED,
                "tip": "单击此按钮会将选择开始实验时是否校准气体。",
                "disabled": True,
                "separator_before": False,
                "separator_after": False
            },
            {
                "name": "暂停实验",
                "short_name": "暂停",
                "obj_name": "pause_experiment",
                "type": "button",
                "icon": "⏸",
                "callback": self.pause_experiment,
                "app_state": AppState.CONFIGURING,
                "tip": "单击此按钮会将暂停实验，必须在实验中才能单击该按钮。",
                "disabled": True,
                "separator_before": False,
                "separator_after": False
            },
            {
                "name": "停止实验",
                "short_name": "停止",
                "obj_name": "stop_experiment",
                "type": "button",
                "icon": "⏹",
                "callback": self.stop_experiment,
                "app_state": AppState.CONFIGURING,
                "tip": "单击此按钮会将停止实验，并将实验数据保存。",
                "disabled": True,
                "separator_before": False,
                "separator_after": True
            },
            {
                "name": "导出实验数据",
                "short_name": "导出",
                "obj_name": "export_experiment_datas",
                "type": "button",
                "icon": "💾",
                "callback": self.export_experiment_datas,
                "app_state": AppState.MONITORING,
                "tip": "单击此按钮会将将实验数据保存。",
                "disabled": True,
                "separator_before": False,
                "separator_after": True
            },
            {
                "name": "重置教程页",
                "short_name": "重置教程",
                "obj_name": "reset_guidance",
                "type": "button",
                "icon": "🔄",
                "callback": self.reset_guidance,
                "app_state": AppState.INITIALIZED,
                "tip": "单击此按钮会将重置教程。",
                "disabled": True,
                "separator_before": False,
                "separator_after": True
            }
        ]

        # 创建按钮，图标在前，文字在后
        for i, button_config in enumerate(static_buttons):
            if button_config["separator_before"]:
                self.toolbar.addSeparator()
            if button_config["type"] == "button":
                action = QAction(button_config["short_name"], self)
                action.setObjectName(button_config["obj_name"])
                action.setToolTip(button_config["tip"])
                action.triggered.connect(button_config["callback"])
                # 设置图标
                if button_config["icon"]:
                    action.setText(button_config["icon"] + " " + button_config["short_name"])

                if button_config["disabled"]:
                    action.setDisabled(True)

                self.tool_bar_actions.append({
                    "text": button_config["name"],
                    "obj_name": button_config["obj_name"],
                    "action": action,
                    "app_state": button_config["app_state"],
                    "tip": button_config["tip"]
                })

                self.toolbar.addAction(action)
                # 记录静态按钮（用于插入动态按钮时定位）
                if i == 0:
                    self.static_toolbar_actions.append(action)
            elif button_config["type"] == "checkbox":
                if button_config["icon"]:
                    checkBox = QCheckBox(button_config["icon"] + " " + button_config["name"])
                else:
                    checkBox = QCheckBox(button_config["name"])
                checkBox.setChecked(True)
                checkBox.stateChanged.connect(button_config["callback"])
                checkBox.setObjectName(button_config["obj_name"])
                if button_config["disabled"]:
                    checkBox.setDisabled(True)
                self.tool_bar_actions.append({
                    "text": button_config["name"],
                    "obj_name": button_config["obj_name"],
                    "action": checkBox,
                    "app_state": button_config["app_state"],
                    "tip": button_config["tip"]
                })

                self.toolbar.addWidget(checkBox)
            if button_config["separator_after"]:
                self.toolbar.addSeparator()


            # # 在某些按钮后添加分隔符
            # if button_config["obj_name"] in ["window_exchange", "toggle_mode", "stop_experiment",
            #                                  "export_experiment_datas", "reset_guidance"]:
            #     self.toolbar.addSeparator()

        self.initialize_toolbar_visibility()

    def initialize_toolbar_visibility(self):
        """初始化工具栏可见性 - 根据当前菜单配置"""
        if self.menu_name and len(self.menu_name) > 0:
            first_menu = self.menu_name[0]
            hide_common_tools = first_menu.get('hide_common_tools', False)

            if hide_common_tools:
                self.hide_common_tools()
            else:
                self.show_common_tools()
        else:
            self.show_common_tools()
    # 创建文本图标的方法
    def create_text_icon(self, text, size=18):
        """创建文本图标"""
        from PyQt6.QtGui import QPixmap, QPainter, QFont, QIcon, QColor
        from PyQt6.QtCore import Qt

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 设置字体
        font = QFont()
        font.setPixelSize(size - 2)  # emoji 稍小一点
        painter.setFont(font)

        # 设置文字颜色
        painter.setPen(QColor("#333333"))

        # 绘制文本
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()

        return QIcon(pixmap)

    def create_menu_bar(self):
        """创建菜单栏 - 触发工具栏切换"""
        for menu_dict in self.menu_name:
            # 创建菜单动作
            action = QAction(menu_dict['text'], self)
            action.setObjectName(f"menu_{menu_dict['id']}")
            action.setToolTip(menu_dict.get('tip', ""))

            # 连接到工具栏切换方法
            action.triggered.connect(lambda checked, menu_id=menu_dict['id']: self.switch_toolbar_content(menu_id))

            # 添加到菜单栏
            self.menuBar().addAction(action)

            # 从菜单配置中获取 required_app_state，转换为枚举
            required_state_str = menu_dict.get('required_app_state', 'INITIALIZED')
            try:
                required_app_state = AppState[required_state_str]
            except KeyError:
                required_app_state = AppState.INITIALIZED

            # 存储菜单动作信息
            self.menu_bar_actions.append({
                "name": menu_dict['text'],
                "obj_name": f"menu_{menu_dict['id']}",
                "action": action,
                "menu_id": menu_dict['id'],
                "app_state": required_app_state  # 使用正确的状态
            })

    def switch_toolbar_content(self, menu_id):
        """根据菜单ID切换工具栏内容"""
        # 清除当前工具栏的动态内容
        self.clear_dynamic_toolbar_content()

        # 记录当前激活的菜单
        self.current_active_menu_id = menu_id

        # 为所有模块设置 main_gui
        for module in self.modules:
            if module.main_gui is None:
                module.set_main_gui(main_gui=self)
        # 找到对应的菜单配置
        current_menu_config = None
        for menu_dict in self.menu_name:
            if menu_dict.get('id') == menu_id:
                current_menu_config = menu_dict
                break

        # 检查是否需要隐藏通用工具
        hide_common_tools = current_menu_config.get('hide_common_tools', False) if current_menu_config else False

        # 控制通用工具的显示/隐藏
        if hide_common_tools:
            self.hide_common_tools()
        else:
            self.show_common_tools()

        if menu_id == 1:
            global_setting.set_setting("device_config_calibration_selected", False)
            global_setting.set_setting("startup_calibration_mode", "none")
            global_setting.set_setting("is_auto_calibration", False)
            global_setting.set_setting("air_modules_all_valid", False)
            self.calibration_selection_changed_signal.emit(
                False,
                global_setting.get_setting("startup_calibration_mode", "none")
            )

        # 找到属于这个菜单的所有模块
        menu_modules = []
        for module in self.modules:
            module: BaseModule
            module_menu_name = module.menu_name
            if (module_menu_name is not None and
                    "id" in module_menu_name and
                    module_menu_name["id"] == menu_id):
                menu_modules.append(module)

        # 按模块顺序和标题排序
        menu_modules.sort(key=lambda x: (getattr(x, "toolbar_order", 999), x.title))

        # 确定插入位置
        insert_position = self.get_dynamic_content_insert_position(hide_common_tools)

        # 为每个模块创建工具栏按钮
        for module in menu_modules:
            module.set_main_gui(main_gui=self)
            if hasattr(module, "refresh_display_text"):
                module.refresh_display_text()
            name = module.title
            obj_name = f"dynamic_{module.name}"

            # 图标映射表
            MODULE_ICON_MAP = {
                "新建实验": "🧪",
                "打开实验文件": "📂",
                "设置设备": "🔧",
                "校准": "🎯",
                "设备配置": "🖥️",
                "老鼠轨迹监测": "🐭",
                "相机监控": "📷",
                "红外相机": "📷",
                "视频图像": "📹",
                "深度相机对应鼠笼配置": "🧭",
                "红外相机对应鼠笼配置": "🌡",
                "硬件配置": "🗂️",
                "用户界面": "👤",
                "数据监控": "📊",
                "串口调试":"🔌",
                "坐标标定":"📍"
            }

            # 根据模块名匹配图标
            icon_char = None
            for key, icon in MODULE_ICON_MAP.items():
                if key in name:
                    icon_char = icon
                    break

            # 用 QToolButton 替代 QAction
            from PyQt6.QtWidgets import QToolButton
            btn = QToolButton()
            btn.setObjectName(obj_name)
            btn.setToolTip(name)
            btn.clicked.connect(module.click_method)
            if obj_name == "dynamic_New_main_experiment_calibration":
                btn.setEnabled(
                    bool(global_setting.get_setting("air_modules_all_valid", False))
                    or bool(global_setting.get_setting("allow_test_calibration_without_air_validation", False))
                )

            # # 文字竖排
            # btn.setText("\n".join(name))
            btn.setText(name)

            # 图标在上，文字在下
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

            # 图标：优先模块自带，其次映射表，最后首字
            if hasattr(module, 'icon') and module.icon:
                from PyQt6.QtGui import QIcon
                btn.setIcon(QIcon(module.icon))
            elif icon_char:
                btn.setIcon(self.create_text_icon(icon_char, size=28))
            else:
                btn.setIcon(self.create_text_icon(name[0] if name else "●", size=28))
            btn.setIconSize(QtCore.QSize(28, 28))

            # 字体
            font = QFont()
            font.setPixelSize(12)
            btn.setFont(font)

            # 固定宽度
            btn.setFixedWidth(190 if len(name) >= 8 else 150)

            # 样式
            btn.setStyleSheet("""
                            QToolButton {
                                border: none;
                                padding: 0px 2px;
                                background: transparent;
                            }
                            QToolButton:hover {
                                background: rgba(128,128,128,0.15);
                                border-radius: 6px;
                            }
                            QToolButton:pressed {
                                background: rgba(128,128,128,0.3);
                                border-radius: 6px;
                            }
                        """)

            self.dynamic_tool_bar_actions.append({
                "name": name,
                "obj_name": obj_name,
                "action": btn,  # 存btn
                "app_state": module.app_state,
                "menu_id": menu_id
            })

            # 用insertWidget/addWidget
            if insert_position:
                self.toolbar.insertWidget(insert_position, btn)
            else:
                self.toolbar.addWidget(btn)

        # 添加分隔符（只有在显示通用工具且有动态内容时才添加）
        if menu_modules and not hide_common_tools and self.static_toolbar_actions:
            separator = self.toolbar.insertSeparator(self.static_toolbar_actions[0])
            self.dynamic_toolbar_separators.append(separator)

        # 更新菜单栏按钮的激活状态
        self.update_menu_bar_active_state(menu_id)
        self.change_enable_component_app_state()

    def clear_dynamic_toolbar_content(self):
        """清除工具栏中的动态内容"""
        from PyQt6.QtWidgets import QToolButton
        for action_dict in self.dynamic_tool_bar_actions:
            widget_or_action = action_dict["action"]
            if isinstance(widget_or_action, QAction):
                self.toolbar.removeAction(widget_or_action)
            else:
                # QToolButton 直接隐藏并销毁
                widget_or_action.hide()
                widget_or_action.deleteLater()

        for separator in self.dynamic_toolbar_separators:
            self.toolbar.removeAction(separator)

        self.dynamic_tool_bar_actions.clear()
        self.dynamic_toolbar_separators.clear()
        self.show_common_tools()

    def hide_common_tools(self):
        """隐藏通用工具按钮"""
        # 隐藏所有工具栏中的 action
        for action in self.toolbar.actions():
            if not action.isSeparator():
                action.setVisible(False)
            elif action not in self.dynamic_toolbar_separators:
                # 隐藏非动态分隔符
                action.setVisible(False)

        # 同时隐藏通过 addWidget 添加的 checkbox 等 widget
        for i in range(self.toolbar.layout().count()):
            widget = self.toolbar.layout().itemAt(i).widget()
            if widget is not None and isinstance(widget, QCheckBox):
                widget.setVisible(False)


    def show_common_tools(self):
        """显示通用工具按钮"""
        # 显示所有 action
        for action in self.toolbar.actions():
            if not action.isSeparator():
                action.setVisible(True)
            elif action not in self.dynamic_toolbar_separators:
                action.setVisible(True)

        # 显示通过 addWidget 添加的 checkbox 等 widget
        for i in range(self.toolbar.layout().count()):
            widget = self.toolbar.layout().itemAt(i).widget()
            if widget is not None and isinstance(widget, QCheckBox):
                widget.setVisible(True)


    def get_dynamic_content_insert_position(self, hide_common_tools):
        """获取动态内容插入位置"""
        if hide_common_tools:
            # 如果隐藏通用工具，插入到工具栏开始位置（第一个动作）
            actions = self.toolbar.actions()
            return actions[0] if actions else None
        else:
            # 如果显示通用工具，插入到第一个静态按钮之前
            if self.static_toolbar_actions:
                return self.static_toolbar_actions[0]
            return None

    def update_menu_bar_active_state(self, active_menu_id):
        """更新菜单栏按钮的激活状态"""
        for action_dict in self.menu_bar_actions:
            action = action_dict["action"]
            menu_id = action_dict.get("menu_id")

            if menu_id == active_menu_id:
                # 设置为激活状态（可以通过样式表来显示不同的外观）
                action.setCheckable(True)
                action.setChecked(True)
            else:
                action.setCheckable(True)
                action.setChecked(False)

    def _retranslateUi(self, **kwargs):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate(self.objectName(), global_setting.get_setting("configer")["window"]["title"]))
    pass
    def load_modules(self):
        # 动态加载模块
        modules = []
        module_dir = 'Module'  # 插件目录
        # 递归遍历指定目录
        for dirpath, dirnames, filenames in os.walk(module_dir):
            for filename in filenames:
                if filename.endswith('.py'):
                    module_name = filename[:-3]  # 去掉 .py 后缀
                    if module_name.startswith("main"):
                        file_path = os.path.join(dirpath, filename)
                        # 动态加载模块
                        spec = importlib.util.spec_from_file_location(module_name, file_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)  # 装载module
                        # 查找到实现 BasePlugin 的类
                        for name, obj in module.__dict__.items():
                            if name == "BaseModule":
                                # 抽象类跳过
                                continue
                            if (
                                isinstance(obj, type)
                                and issubclass(obj, BaseModule)
                                and not obj.__dict__.get("__module_loader_skip__", False)
                            ):
                                modules.append(obj())
        return modules
        pass

    def exchange_widget_and_window(self):
        """widget和window相互转换"""
        # 将module的显示方式改变
        for module in self.modules:
            if module.interface_widget.type == BaseInterfaceType.WIDGET or module.interface_widget.type == BaseInterfaceType.FRAME:
                module.interface_widget.type = BaseInterfaceType.WINDOW

            else:
                module.interface_widget.type = BaseInterfaceType.WIDGET
        new_open_windows = []
        new_active_module_widgets = []
        # 将正在显示的方式进行改变
        if self.open_windows is not None and len(self.open_windows) != 0:
            # 窗口-》frame
            # 将正在显示的方式进行改变
            index = 0
            last_module = None
            while index < len(self.open_windows) or len(self.open_windows) == 1:
                if index >= len(self.open_windows):
                    index = 0
                module = self.open_windows[index]
                if last_module is module:
                    break
                last_module = module
                module.close()
                if module not in self.active_module_widgets:
                    new_active_module_widgets.append(module)
                index += 1
        if self.active_module_widgets is not None and len(self.active_module_widgets) != 0:
            # 从初始布局中移除 label
            # frame-》窗口
            index = 0
            last_module = None
            while index < len(self.active_module_widgets) or len(self.active_module_widgets) == 1:
                if index >= len(self.active_module_widgets):
                    index = 0
                module = self.active_module_widgets[index]
                if last_module is module:
                    break
                last_module = module
                module.setParent(None)
                module.hide()
                if module not in self.open_windows:
                    new_open_windows.append(module)
                index += 1
        # 删除所有标签页和widgets
        while self.tab_widget.count() > 0:  # 直到没有标签页
            self.tab_widget.removeTab(0)  # 删除第一个标签页
        self.open_windows.extend(new_open_windows)
        self.active_module_widgets.extend(new_active_module_widgets)
        for module in self.open_windows:
            module.adjustGUIPolicy()
            module.interface_widget.setMinimumSize(0, 0)
            module.interface_widget.show()
        for module in self.active_module_widgets:
            module.adjustGUIPolicy()
            module.interface_widget.setMinimumSize()
            module.interface_widget.show()

    # 切换白天黑夜主题功能
    def toggle_theme(self):
        # 根据当前主题变换主题
        new_theme = "dark" if global_setting.get_setting("theme_manager").current_theme == "light" else "light"
        # 将新主题关键字赋值回去
        global_setting.set_setting('style', new_theme)
        global_setting.get_setting("theme_manager").current_theme = new_theme
        # 更改样式
        self.setStyleSheet(global_setting.get_setting("theme_manager").get_style_sheet())
        pass

    def start_update_gui(self, resolve, reject):
        # 更新main_gui组件显示
        self.change_enable_component_app_state_signal.emit()
        self.status_bar.update_status()
        self.status_bar.update_tip(f"开启实验监测成功！")
        for action_dict in self.tool_bar_actions:
            if action_dict["obj_name"] == "start_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(True)
            if action_dict["obj_name"] == "stop_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(False)
            if action_dict["obj_name"] == "pause_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(False)
        self.setEnabled(True)
        resolve()

    def _get_experiment_root_path(self):
        experiment_setting_file = global_setting.get_setting("experiment_setting_file", None)
        if experiment_setting_file is None or not os.path.exists(experiment_setting_file):
            return None

        file_name = os.path.basename(experiment_setting_file)
        file_name_without_extension = os.path.splitext(file_name)[0]
        return os.getcwd() + global_setting.get_setting('monitor_data')['STORAGE']['fold_path'] + os.path.join(
            global_setting.get_setting('monitor_data')['STORAGE']['sub_fold_path'],
            f"{file_name_without_extension}_{time_util.get_format_file_from_time(global_setting.get_setting('start_experiment_time', time.time()))}"
        )

    def _get_experiment_db_path(self):
        experiment_root_path = self._get_experiment_root_path()
        if experiment_root_path is None:
            return None
        return os.path.join(experiment_root_path, "data", "data.db")

    def _get_experiment_excel_path(self):
        experiment_root_path = self._get_experiment_root_path()
        if experiment_root_path is None:
            return None
        return f"{experiment_root_path}.xlsx"

    def _get_periodic_export_interval_ms(self):
        export_config = global_setting.get_setting("monitor_data", {}).get("EXPORT", {})
        interval_minutes_raw = export_config.get("periodic_xlsx_interval_minutes", 30)
        try:
            interval_minutes = float(interval_minutes_raw)
        except (TypeError, ValueError):
            logger.warning(f"定时导出xlsx配置无效，使用默认值30分钟: {interval_minutes_raw}")
            interval_minutes = 30.0

        if interval_minutes <= 0:
            return 0
        return int(interval_minutes * 60 * 1000)

    def _start_periodic_export_timer(self):
        interval_ms = self._get_periodic_export_interval_ms()
        if self.periodic_export_timer.isActive():
            self.periodic_export_timer.stop()
        if interval_ms <= 0:
            logger.info("定时导出xlsx已关闭：EXPORT.periodic_xlsx_interval_minutes <= 0")
            return
        self.periodic_export_timer.setInterval(interval_ms)
        self.periodic_export_timer.start()
        logger.info(f"定时导出xlsx已启动，周期: {interval_ms / 60000:.2f} 分钟")

    def _stop_periodic_export_timer(self):
        if self.periodic_export_timer.isActive():
            self.periodic_export_timer.stop()
            logger.info("定时导出xlsx已停止")

    def _is_periodic_export_running(self):
        with self.periodic_export_lock:
            return self.periodic_export_in_progress

    def _on_periodic_export_finished(self, success, message):
        with self.periodic_export_lock:
            self.periodic_export_in_progress = False
            self.periodic_export_thread = None

        if success:
            logger.info(message)
        else:
            logger.error(message)
            self.update_status_tip_signal.emit(message)

    def trigger_periodic_excel_export(self):
        if global_setting.get_setting("app_state", AppState.INITIALIZED) != AppState.MONITORING:
            return

        db_path = self._get_experiment_db_path()
        export_file_path = self._get_experiment_excel_path()
        if db_path is None or export_file_path is None:
            logger.warning("定时导出xlsx跳过：实验路径尚未准备好")
            return
        if not os.path.exists(db_path):
            logger.warning(f"定时导出xlsx跳过：数据库不存在 {db_path}")
            return

        with self.periodic_export_lock:
            if self.periodic_export_in_progress:
                logger.warning("上一次定时导出xlsx尚未完成，跳过本轮导出")
                return
            self.periodic_export_in_progress = True

        logger.info(f"开始定时导出xlsx: {export_file_path}")
        self.periodic_export_thread = PeriodicExcelExportThread(
            db_path=db_path,
            export_file_path=export_file_path,
            callback=self._on_periodic_export_finished
        )
        self.periodic_export_thread.start()

    def start_experiment(self):

        # ★ 重置上一次实验残留的临时提示状态，确保从绿色开始
        self.status_bar._temp_tip_active = False
        self.old_Stop_experiment_status_text_reTurn = None
        self.old_stop_status_counts = 0
        self._gas_path_success = False
        if self._gas_path_timeout_timer is not None:
            self._gas_path_timeout_timer.stop()
            self._gas_path_timeout_timer = None

        self.setEnabled(False)
        self.status_bar.update_tip(f"正在开启实验监测...")
        port = global_setting.get_setting("port")
        if port is None or port == "":
            reply = QMessageBox.question(self, '注意',
                                         "未设置串口，请去实验配置配置串口!",
                                         QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.No)
            self.setEnabled(True)
            return
        modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
        if modbus is None:
            modbus = ModbusRTUMasterNew(port, baudrate=115200, timeout=float(
                global_setting.get_setting('monitor_data')['Serial']['timeout']), )
            global_setting.set_setting("modbus", modbus)
        else:
            modbus.close()
            modbus = ModbusRTUMasterNew(port, baudrate=115200, timeout=float(
                global_setting.get_setting('monitor_data')['Serial']['timeout']), )
            global_setting.set_setting("modbus", modbus)
        # 开始实验
        global_setting.set_setting("app_state", AppState.MONITORING)
        global_setting.set_setting("start_experiment_time", time.time())
        global_setting.set_setting("pause_experiment_time", [])
        global_setting.set_setting("relieve_pause_experiment_time", [])
        self._start_periodic_export_timer()
        # self.start_thread = Start_experiment_thread(name="start_thread",window=self)
        # self.start_thread.start()

        send_message_queue = global_setting.get_setting("send_message_queue")

        send_message_queue.put(ObjectQueueItem(origin='MainWindow_Index', to='main_monitor_data', title='start',
                                               data={
                                                   'start_experiment_time': global_setting.get_setting(
                                                       "start_experiment_time"),
                                                   'pause_experiment_time': global_setting.get_setting(
                                                       "pause_experiment_time"),
                                                   'relieve_pause_experiment_time': global_setting.get_setting(
                                                       "relieve_pause_experiment_time")
                                               },
                                               time=time_util.get_format_from_time(time.time())))
        message_structs = [

            ObjectQueueItem(origin='MainWindow_Index', to='main_infrared_camera', title='start',
                            data={
                                'start_experiment_time': global_setting.get_setting("start_experiment_time"),
                                'pause_experiment_time': global_setting.get_setting("pause_experiment_time"),
                                'relieve_pause_experiment_time': global_setting.get_setting(
                                    "relieve_pause_experiment_time")
                            },
                            time=time_util.get_format_from_time(time.time())),
            ObjectQueueItem(origin='MainWindow_Index', to='main_deep_camera', title='start',
                            data={
                                'start_experiment_time': global_setting.get_setting("start_experiment_time"),
                                'pause_experiment_time': global_setting.get_setting("pause_experiment_time"),
                                'relieve_pause_experiment_time': global_setting.get_setting(
                                    "relieve_pause_experiment_time")
                            },
                            time=time_util.get_format_from_time(time.time())),
        ]
        for message_struct in message_structs:
            queue = global_setting.get_setting("queue")
            queue.put(message_struct)
        AsyPromise(self.start_update_gui).then(
            lambda _: AsyPromise(self.show_open_dialog).then(
                lambda _: AsyPromise(self.start_open_window).then(

                ).catch(lambda e: logger.error(f"{e}"))
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))
        # AsyPromise(self.start_open_window).then().catch(lambda e: logger.error(f"{e}"))
        pass

    def show_open_dialog(self, resolve, reject):
        start_wait_times = float(global_setting.get_setting('configer')['dialog_timeout']['timeout']) + float(
            global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['wait_time']) + float(
            global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['start_read_pressure_all_time']) / float(
            global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['start_read_pressure_delay']) * 2 * 8 + 20

        if self.start_dialog is None:
            self.start_dialog = AnimatedLoadingDialog(countdown_seconds=start_wait_times, title="开始实验",
                                                      message="正在启动气路...")
        else:
            self.start_dialog.reset_progress()
            self.start_dialog.clear_list_data()
            self.start_dialog.deleteLater()
            self.start_dialog = None
            self.start_dialog = AnimatedLoadingDialog(
                countdown_seconds=start_wait_times,
                title="开始实验", message="正在启动气路...")

        startup_calibration_mode = global_setting.get_setting('startup_calibration_mode', None)
        if startup_calibration_mode == "air_co2":
            startup_calibration_mode = "air"
        if startup_calibration_mode not in {"none", "air", "full"}:
            startup_calibration_mode = "full" if global_setting.get_setting('is_auto_calibration', False) else "none"

        if startup_calibration_mode == "air":
            calibration_config = global_setting.get_setting('UFC_UGC_ZOS_config', {}).get('Calibration', {})
            try:
                start_wait_times += max(float(calibration_config.get('startup_air_calibration_wait_time', 1800)), 0)
            except Exception:
                start_wait_times += 1800
            try:
                start_wait_times += max(float(calibration_config.get('startup_air_calibration_max_timeout', 2700)), 0)
            except Exception:
                start_wait_times += 2700
            if self.start_dialog is not None:
                self.start_dialog.countdown_seconds = start_wait_times
                self.start_dialog.current_seconds = start_wait_times

        if startup_calibration_mode in {"air", "full"}:
            self.init__calibration_windows()
            self.start_dialog.insert_calibration_dialog(self.calibration_details_windows)

        self.start_dialog.timeout_signal.connect(self._on_start_experiment_timeout)  # 新增
        result = self.start_dialog.exec()
        self.release_calibration_windows()

        if result == QDialog.DialogCode.Accepted:
            if self.start_dialog is not None and self.start_dialog.force_entered:
                self.show_temp_status_tip_signal.emit("后台正在启动气路，请稍候...", "#ff8800", 0)
                self._gas_path_success = False
                remaining_ms = int((start_wait_times - 60) * 1000)
                if self._gas_path_timeout_timer is not None:
                    self._gas_path_timeout_timer.stop()
                self._gas_path_timeout_timer = QTimer(self)
                self._gas_path_timeout_timer.setSingleShot(True)
                self._gas_path_timeout_timer.timeout.connect(self._on_gas_path_final_timeout)
                self._gas_path_timeout_timer.start(max(remaining_ms, 1000))
            resolve()
        else:
            # ★ 先 reject 解除当前 Promise 链，再延迟调用 stop_experiment
            #    避免 reject() 与 stop_experiment 内部的异步链互相干扰
            logger.warning("start_dialog returned Rejected, skip auto stop_experiment")
            self.show_temp_status_tip_signal.emit("启动弹窗已关闭，实验保持当前运行状态", "#ff8800", 5000)
            resolve()
        pass

    def _on_start_experiment_timeout(self):
        """dialog内部倒计时结束触发（已由force_entered接管，此处留空）"""
        pass

    def _on_gas_path_final_timeout(self):
        """备用计时器到期：force_entered后气路仍未成功，仅显示红色提示，不停止"""
        if not self._gas_path_success:
            self.show_temp_status_tip_signal.emit("气路初始化失败", "#cc0000", 0)
    def cache_calibration_detail_log(self, message, has_time=True):
        self.calibration_detail_log_buffer.append((message, has_time))
        if len(self.calibration_detail_log_buffer) > 1000:
            self.calibration_detail_log_buffer = self.calibration_detail_log_buffer[-1000:]
        if self.calibration_details_windows is not None:
            self.calibration_details_windows.addLog(message, has_time=has_time)

    def restore_calibration_detail_window_state(self):
        if self.calibration_details_windows is None:
            return
        for message, has_time in self.calibration_detail_log_buffer:
            self.calibration_details_windows.addLog(message, has_time=has_time)
        if self.calibration_detail_zero_start_time is not None:
            self.calibration_details_windows.updateZeroStartTime(self.calibration_detail_zero_start_time, log_event=False)
        if self.calibration_detail_zero_end_time is not None:
            self.calibration_details_windows.updateZeroEndTime(self.calibration_detail_zero_end_time, log_event=False)
        if self.calibration_detail_span_start_time is not None:
            self.calibration_details_windows.updateSpanStartTime(self.calibration_detail_span_start_time, log_event=False)
        if self.calibration_detail_span_end_time is not None:
            self.calibration_details_windows.updateSpanEndTime(self.calibration_detail_span_end_time, log_event=False)
        if self.calibration_detail_status_text is not None:
            self.calibration_details_windows.updateStatus(self.calibration_detail_status_text, log_event=False)

    def init__calibration_windows(self):
        #初始化标定窗口
        if self.calibration_details_windows is None:
            self.calibration_details_windows = CalibrationDialog(main_gui=self)
            self.calibration_details_windows.log_history = []
            self.calibration_details_windows.log_sequence = 0
            self.calibration_details_windows.log_list.clear()
            self.calibration_details_windows.updateO2Span(global_setting.get_setting('span_standard_oxygen_value',0), log_event=False)
            self.calibration_details_windows.updateCO2Span(global_setting.get_setting('span_standard_carbon_value',0), log_event=False)
            self.calibration_details_windows.updatePressureSpan(float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['pressure_steady_default']), log_event=False)
            self.restore_calibration_detail_window_state()
    def show_calibration_windows(self,data):
        self.init__calibration_windows()
        if data:
            match data.get("type",''):
                case "zero_calibration"|"all_calibration":
                    self.calibration_details_windows.updateStatus("零点标定", log_event=False)
                    self.calibration_details_windows.updateZeroStartTime(data.get("time"), log_event=False)
                    pass
                case "span_calibration":
                    self.calibration_details_windows.updateStatus("量程标定", log_event=False)
                    self.calibration_details_windows.updateSpanStartTime(data.get("time"), log_event=False)
                    pass
                case _:
                    pass

        self.calibration_details_windows.show()
    def release_calibration_windows(self):
        # 释放标定窗口
        if self.calibration_details_windows is not None:
            self.calibration_details_windows.hide()
            self.calibration_details_windows.close()
            self.calibration_details_windows.deleteLater()
            self.calibration_details_windows = None

    #   延遲打開窗口
    def start_open_window(self, resolve, reject):
        QTimer.singleShot(1 * 1000, self.open_monitor_data_window)
        resolve()

    def open_monitor_data_window(self):
        """
        打開監控數據界面
        :return:
        """
        # 打開窗口
        for module in self.modules:
            module: BaseModule
            if module.name == "Main_New_Monitor_data":
                module.click_method()
                return

    def pause_experiment(self):
        # 在with语句中自动管理加载遮罩
        with LoadingContext(self, "正在暂停...", "animated") as mask:
            self.setEnabled(False)
            try:
                if self.ufc_ugc_zos is not None and not self.ufc_ugc_zos.ispause:
                    self.ufc_ugc_zos.pause()
                else:
                    self.ufc_ugc_zos.resume()
                if self.ufc_ugc_zos_thread is not None and not self.ufc_ugc_zos_thread.isPaused():
                    self.ufc_ugc_zos.disabled_auto_btn_handle()
            except Exception as e:
                logger.error(f"暂停实验监测ufc_ugc_zos错误，原因：{e}")
            try:
                if self.store_thread_sub is not None and not self.store_thread_sub.isPaused():
                    self.store_thread_sub.pause()
                else:
                    self.store_thread_sub.resume()
            except Exception as e:
                logger.error(f"暂停实验监测store_thread_sub错误，原因：{e}")
                self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            try:
                if self.add_message_thread_sub is not None and not self.add_message_thread_sub.isPaused():
                    self.add_message_thread_sub.pause()
                else:
                    self.add_message_thread_sub.resume()
            except Exception as e:
                logger.error(f"暂停实验监测add_message_thread_sub错误，原因：{e}")
                self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            try:
                if self.send_thread_sub is not None and not self.send_thread_sub.isPaused():
                    self.send_thread_sub.pause()
                else:
                    self.send_thread_sub.resume()
            except Exception as e:
                logger.error(f"暂停实验监测send_thread_sub错误，原因：{e}")
                self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            try:
                if self.read_queue_data_thread_sub is not None and not self.read_queue_data_thread_sub.isPaused():
                    self.read_queue_data_thread_sub.pause()
                else:
                    self.read_queue_data_thread_sub.resume()
            except Exception as e:
                logger.error(f"暂停实验监测read_queue_data_thread_sub错误，原因：{e}")
                self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            # 所有红外相机线程停止
            for camera_struct_l in self.infrared_camera_thread_sub_list:
                if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                    try:
                        if camera_struct_l['camera'] is not None and not camera_struct_l['camera'].isPaused():
                            camera_struct_l['camera'].pause()
                        else:
                            camera_struct_l['camera'].resume()
                    except Exception as e:
                        logger.error(f"暂停实验监测infrared_camera_thread_sub_list错误，原因：{e}")
                        self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            try:
                if self.infrared_camera_delete_file_thread_sub is not None and not self.infrared_camera_delete_file_thread_sub.isPaused():
                    self.infrared_camera_delete_file_thread_sub.pause()
                else:
                    self.infrared_camera_delete_file_thread_sub.resume()
            except Exception as e:
                logger.error(f"暂停实验监测infrared_camera_delete_file_thread_sub错误，原因：{e}")
                self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            try:
                if self.infrared_camera_read_queue_data_thread_sub is not None and not self.infrared_camera_read_queue_data_thread_sub.isPaused():
                    self.infrared_camera_read_queue_data_thread_sub.pause()
                else:
                    self.infrared_camera_read_queue_data_thread_sub.resume()
            except Exception as e:
                logger.error(f"暂停实验监测infrared_camera_read_queue_data_thread_sub错误，原因：{e}")
                self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            # 所有深度相机线程停止
            for camera_struct_l in self.deep_camera_thread_sub_list:
                if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                    try:
                        if camera_struct_l['camera'] is not None and not camera_struct_l['camera'].isPaused():
                            camera_struct_l['camera'].pause()
                        else:
                            camera_struct_l['camera'].resume()
                    except Exception as e:
                        logger.error(f"暂停实验监测deep_camera_thread_sub_list错误，原因：{e}")
                        self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
                if len(camera_struct_l) != 0 and 'img_process' in camera_struct_l:
                    try:
                        if camera_struct_l['img_process'] is not None and not camera_struct_l['img_process'].isPaused():
                            camera_struct_l['img_process'].pause()
                        else:
                            camera_struct_l['img_process'].resume()
                    except Exception as e:
                        logger.error(f"暂停实验监测deep_camera_thread_sub_list_img_process错误，原因：{e}")
                        self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            try:
                if self.deep_camera_delete_file_thread_sub is not None and not self.deep_camera_delete_file_thread_sub.isPaused():
                    self.deep_camera_delete_file_thread_sub.pause()
                else:
                    self.deep_camera_delete_file_thread_sub.resume()
            except Exception as e:
                logger.error(f"暂停实验监测deep_camera_delete_file_thread_sub错误，原因：{e}")
                self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            try:
                if self.deep_camera_read_queue_data_thread_sub is not None and not self.deep_camera_read_queue_data_thread_sub.isPaused():
                    self.deep_camera_read_queue_data_thread_sub.pause()
                else:
                    self.deep_camera_read_queue_data_thread_sub.resume()
            except Exception as e:
                logger.error(f"暂停实验监测deep_camera_read_queue_data_thread_sub错误，原因：{e}")
                self.status_bar.update_tip(f"暂停实验监测错误，原因：{e}")
            pass

            self.is_paused = not self.is_paused
            if self.is_paused:
                pause_experiment_time = global_setting.get_setting("pause_experiment_time", [])
                pause_experiment_time.append(time.time())
                global_setting.set_setting("pause_experiment_time", pause_experiment_time)
                self.status_bar.update_tip(f"暂停实验监测成功！")
            else:
                relieve_pause_experiment_time = global_setting.get_setting("relieve_pause_experiment_time", [])
                relieve_pause_experiment_time.append(time.time())
                global_setting.set_setting("relieve_pause_experiment_time", relieve_pause_experiment_time)
                self.status_bar.update_tip(f"解除暂停实验监测成功！")
            self.status_bar.update_status(is_paused=self.is_paused)

            for action_dict in self.tool_bar_actions:
                if action_dict["obj_name"] == "pause_experiment":
                    action_dict["action"]: QAction
                    if self.is_paused:
                        action_dict["name"] = "解除暂停实验"
                    else:
                        action_dict["name"] = "暂停实验"
                    action_dict["action"].setToolTip(action_dict["name"])
                    action_dict["action"].setText(action_dict["name"])
            self.setEnabled(True)
        pass

    def stop_experiment(self):
        if global_setting.get_setting("app_state", AppState.INITIALIZED) != AppState.MONITORING:
            return

            # ★ 停止实验时清掉所有临时提示，状态栏恢复正常
        self.status_bar._temp_tip_active = False
        self.old_Stop_experiment_status_text_reTurn = None
        self.old_stop_status_counts = 0
        if self._gas_path_timeout_timer is not None:
            self._gas_path_timeout_timer.stop()
            self._gas_path_timeout_timer = None
        self._stop_periodic_export_timer()

        self.setEnabled(False)
        self.status_bar.update_tip(f"正在关闭实验监测...")
        # self.stop_experiment_thread = Stop_experiment_thread(name="stop_experiment_thread",window=self)
        # self.stop_experiment_thread.start()
        global_setting.set_setting("stop_experiment_time", time.time())
        send_message_queue = global_setting.get_setting("send_message_queue")
        send_message_queue.put(ObjectQueueItem(origin='MainWindow_Index', to='main_monitor_data', title='stop',
                                               data={
                                                   'stop_experiment_time': global_setting.get_setting(
                                                       "stop_experiment_time"),
                                               },
                                               time=time_util.get_format_from_time(time.time())))
        message_structs = [
            ObjectQueueItem(origin='MainWindow_Index', to='main_deep_camera', title='stop', data={
                'stop_experiment_time': global_setting.get_setting("stop_experiment_time"),
            },
                            time=time_util.get_format_from_time(time.time())),
            ObjectQueueItem(origin='MainWindow_Index', to='main_infrared_camera', title='stop', data={
                'stop_experiment_time': global_setting.get_setting("stop_experiment_time"),
            },
                            time=time_util.get_format_from_time(time.time())),

        ]
        for message_struct in message_structs:
            queue = global_setting.get_setting("queue")
            queue.put(message_struct)

        QTimer.singleShot(0, self.start_stop_cleanup_async)
        self.show_stop_dialog_sync()
        self.stop_update_gui_sync()

    def start_stop_cleanup_async(self):
        AsyPromise(self.close_monitor_data_window).then(
            lambda _: AsyPromise(self.stop_store_info_Qtimer)
        ).catch(lambda e: logger.error(f"{e}"))

    def stop_update_gui_sync(self):
        logger.error("stop_update_gui")
        global_setting.set_setting("app_state", AppState.CONFIGURING)

        # 更新main_gui组件显示
        self.change_enable_component_app_state_signal.emit()
        self.status_bar.update_status()
        self.status_bar.update_tip(f"关闭实验监测成功！")
        for action_dict in self.tool_bar_actions:
            if action_dict["obj_name"] == "start_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(False)
            if action_dict["obj_name"] == "stop_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(True)

        self.setEnabled(True)

    def stop_update_gui(self, resolve, reject):
        self.stop_update_gui_sync()
        resolve()
        pass

    def show_stop_dialog_sync(self):
        stop_wait_times = float(global_setting.get_setting('configer')['dialog_timeout']['timeout']) + float(
            global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['wait_time']) + 30
        if self.stop_dialog is None:
            self.stop_dialog = AnimatedLoadingDialog(countdown_seconds=stop_wait_times, title="停止实验",
                                                     message="正在停止实验...")
        else:
            self.stop_dialog.reset_progress()
            self.stop_dialog.clear_list_data()
            self.stop_dialog.deleteLater()
            self.stop_dialog = AnimatedLoadingDialog(
                countdown_seconds=stop_wait_times,
                title="停止实验", message="正在停止实验...")

        # self.start_dialog.set_progress_range(0, ZOS_gas_path_system.process_nums+UFC_gas_path_system.process_nums+UGC_gas_path_system.process_nums)
        self.stop_dialog.exec()

    def show_stop_dialog(self, resolve, reject):
        self.show_stop_dialog_sync()
        resolve()

    def stop_store_info_Qtimer(self, resolve, reject):
        QTimer.singleShot(100, self.stop_store_info)
        resolve()

    def stop_store_info(self):
        if self._is_periodic_export_running():
            if self.stop_dialog is not None:
                self.stop_dialog.insert_data_signal.emit("等待定时导出完成.... ")
            QTimer.singleShot(1000, self.stop_store_info)
            return

        # 停止实验 将文件夹的数据合并成一个数据文件
        folder_path_data = self._get_experiment_root_path()
        if folder_path_data is not None and os.path.exists(folder_path_data):
            if self.stop_dialog is not None:
                self.stop_dialog.insert_data_signal.emit(f"正在导出数据.... ")
            custom_data_file_util.save_folder_contents_as_custom_file(folder_path_data)

    def _finalize_mouse_trajectory_views(self) -> bool:
        trajectory_views = []
        seen_widget_ids = set()
        for widget in QApplication.allWidgets():
            stop_trajectory = getattr(widget, "stop_trajectory_thread", None)
            if not callable(stop_trajectory) or id(widget) in seen_widget_ids:
                continue
            seen_widget_ids.add(id(widget))
            trajectory_views.append((widget, stop_trajectory))

        all_finalized = True
        for widget, stop_trajectory in trajectory_views:
            try:
                logger.info(
                    f"finalizing mouse trajectory before experiment archive: "
                    f"widget={type(widget).__name__}"
                )
                if stop_trajectory() is False:
                    all_finalized = False
            except RuntimeError as error:
                logger.warning(
                    f"mouse trajectory widget was already destroyed during finalization: {error}"
                )
            except Exception as error:
                all_finalized = False
                logger.exception(f"mouse trajectory finalization failed: {error}")

        return all_finalized

    def close_monitor_data_window_sync(self):
        """
        关闭監控數據界面
        :return:
        """
        # 关闭窗口
        if not self._finalize_mouse_trajectory_views():
            raise RuntimeError(
                "mouse trajectory finalization did not finish; experiment archive was not started"
            )

        for module in self.modules:
            module: BaseModule
            if module.name == "Main_New_Monitor_data":
                try:
                    module.close()
                except RuntimeError as e:
                    logger.warning(f"关闭监控数据窗口时窗口对象已销毁，跳过关闭：{e}")
                return
        return

    def close_monitor_data_window(self, resolve, reject):
        try:
            self.close_monitor_data_window_sync()
        except Exception as error:
            reject(error)
            return
        resolve()

    def export_experiment_datas(self):
        """
        导出实验数据按钮函数
        :return:
        """

        def stop_store_info_Qtimer():
            # 读取实验设置文件路径
            experiment_setting_file = global_setting.get_setting("experiment_setting_file", None)
            if experiment_setting_file is not None and os.path.exists(experiment_setting_file):
                # 获取文件所在的文件夹路径
                folder_path = os.path.dirname(experiment_setting_file)
                # 获取文件名称
                file_name = os.path.basename(experiment_setting_file)
                # 不带扩展名的文件名称
                file_name_without_extension = os.path.splitext(file_name)[0]
                # 获取文件的扩展名
                file_name_extension = os.path.splitext(file_name)[1]
                # 定义文件夹路径
                folder_path_data = os.getcwd() + global_setting.get_setting('monitor_data')['STORAGE'][
                    'fold_path'] + os.path.join(
                    global_setting.get_setting('monitor_data')['STORAGE']['sub_fold_path'],
                    f"{file_name_without_extension}_{time_util.get_format_file_from_time(global_setting.get_setting('start_experiment_time', time.time()))}")
                custom_data_file_util.export_data_to_csv(export_file_path=None,
                                                         file_name=os.path.basename(folder_path_data))
                # custom_data_file_util.save_folder_contents_as_custom_file(folder_path_data,is_delete_original_data_file=False)

        QTimer.singleShot(1000, stop_store_info_Qtimer)

    def close_tab(self, index):
        """关闭标签页"""
        self.tab_widget.widget(index).hide()
        self.tab_widget.removeTab(index)

    def _set_module_interface_enabled(self, module: BaseModule, enabled: bool):
        if module is None or module.interface_widget is None:
            return

        widgets = [
            module.interface_widget.frame_obj,
            module.interface_widget.left_frame_obj,
            module.interface_widget.right_frame_obj,
            module.interface_widget.bottom_frame_obj,
        ]
        for widget in widgets:
            if widget is None:
                continue
            try:
                widget.setEnabled(enabled)
            except RuntimeError as e:
                logger.warning(f"同步页面控件可用状态时跳过已销毁窗口：{e}")

    def sync_module_interface_enabled_state(self):
        current_app_state = global_setting.get_setting("app_state", AppState.INITIALIZED)
        handled_modules = set()

        for module in list(self.active_module_widgets) + list(self.open_windows):
            if module is None:
                continue
            module_key = id(module)
            if module_key in handled_modules:
                continue
            handled_modules.add(module_key)
            module_enabled = True if module.app_state is None else module.app_state <= current_app_state
            self._set_module_interface_enabled(module, module_enabled)

    def change_enable_component_app_state(self):
        # 更新程序状态值
        self.status_bar.update_app_state()
        current_app_state = global_setting.get_setting("app_state", AppState.INITIALIZED)
        # 根据程序状态来改变是否可以点击的组件'
        # 设置是否可以点击 menu_bar
        for menu_bar_action in self.menu_bar_actions:
            if menu_bar_action["app_state"] > current_app_state:
                menu_bar_action["action"].setEnabled(False)
            else:
                menu_bar_action["action"].setEnabled(True)
                # 特殊情况
                if current_app_state == AppState.MONITORING \
                        and menu_bar_action['obj_name'] in ["Main_New_experiment", "Main_New_experiment_open"]:
                    menu_bar_action["action"].setEnabled(False)
        # 设置是否可以点击 tool_bar
        for tool_bar_action in self.tool_bar_actions:
            if tool_bar_action["app_state"] > current_app_state:
                tool_bar_action["action"].setEnabled(False)
            else:
                tool_bar_action["action"].setEnabled(True)
            # 特殊按钮需要特殊配置
            obj_name = tool_bar_action["obj_name"]
            if obj_name in ["stop_experiment", "pause_experiment"]:
                tool_bar_action["action"].setEnabled(current_app_state == AppState.MONITORING)
            elif obj_name in ["toggle_mode", "window_exchange"]:
                tool_bar_action["action"].setEnabled(False)

        # 设置是否可以点击 dynamic tool_bar
        for dynamic_action in self.dynamic_tool_bar_actions:
            if dynamic_action["app_state"] > current_app_state:
                dynamic_action["action"].setEnabled(False)
            else:
                dynamic_action["action"].setEnabled(True)

            if dynamic_action["obj_name"] == "dynamic_New_main_experiment_calibration":
                dynamic_action["action"].setEnabled(
                    bool(global_setting.get_setting("air_modules_all_valid", False))
                    or bool(global_setting.get_setting("allow_test_calibration_without_air_validation", False))
                )

        self.sync_module_interface_enabled_state()

        pass

    def reset_guidance(self):
        """重置教程"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "这将重置所有页面的首次访问状态，下次进入各个页面时会再次显示引导教程。\n\n确定要继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 重置程序首次运行状态
            self.tutorial.settings_manager.settings["first_run"] = True
            self.tutorial.settings_manager.settings["tutorial_completed"] = False

            # 获取所有以 "first_visit_" 开头的设置项并重置为 True
            keys_to_reset = []
            for key in self.tutorial.settings_manager.settings.keys():
                if key.startswith("first_visit_"):
                    keys_to_reset.append(key)

            # 重置所有页面的首次访问状态
            for key in keys_to_reset:
                self.tutorial.settings_manager.settings[key] = True

            # 也可以直接重置特定页面（如果已知页面名称）
            page_names = ["main_page", "project_page", "settings_page", "help_page"]  # 可根据实际页面名称调整
            for page_name in page_names:
                self.tutorial.settings_manager.settings[f"first_visit_{page_name}"] = True

            self.tutorial.settings_manager.save_settings()

            # 显示重置的页面信息
            reset_pages = [key.replace("first_visit_", "") for key in keys_to_reset]
            if reset_pages:
                pages_info = "、".join(reset_pages)
                message = f"所有状态已重置。\n\n已重置的页面: {pages_info}\n\n重新进入这些页面时将显示引导教程。"
            else:
                message = "首次运行状态已重置。\n重新启动程序或进入页面时将显示引导教程。"

            QMessageBox.information(
                self,
                "重置完成",
                message
            )

            self.status_bar.update_tip("✅ 所有页面的首次访问状态已重置")
# 监听是否自动校准气路模块的框选
    def calibration_gas_state_change(self, state=None):
        current_mode = global_setting.get_setting("startup_calibration_mode", None)
        if current_mode not in {"none", "air", "full"}:
            current_mode = "full" if global_setting.get_setting("is_auto_calibration", False) else "none"

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("启动前校准模式")
        msg_box.setText("请选择开始实验前的校准模式：")

        air_button = msg_box.addButton("Air 空气校准后开启实验", QMessageBox.ButtonRole.ActionRole)
        full_button = msg_box.addButton("调零+调span后开启实验", QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton({
            "air": air_button,
            "full": full_button
        }.get(current_mode, air_button))
        msg_box.exec()

        clicked_button = msg_box.clickedButton()
        mode = None
        if clicked_button == air_button:
            mode = "air"
        elif clicked_button == full_button:
            mode = "full"

        if mode is None:
            return

        global_setting.set_setting("startup_calibration_mode", mode)
        global_setting.set_setting("is_auto_calibration", mode == "full")
        global_setting.set_setting("device_config_calibration_selected", True)

        send_message_queue = global_setting.get_setting("send_message_queue")
        if send_message_queue is not None:
            send_message_queue.put(
                ObjectQueueItem(
                    origin='MainWindow_Index',
                    to='main_monitor_data',
                    title='set_experiment_basic_config',
                    data={
                        "startup_calibration_mode": mode,
                        "is_auto_calibration": mode == "full"
                    },
                    time=time_util.get_format_from_time(time.time())
                )
            )

        self.calibration_selection_changed_signal.emit(True, mode)
        return
        is_checked = bool(state)  # 直接转为布尔值
        # 是否自动校准气体给其他进程同步设置
        global_setting.set_setting("is_auto_calibration", is_checked)
        send_message_queue = global_setting.get_setting("send_message_queue")
        send_message_queue.put(
            ObjectQueueItem(origin='MainWindow_Index', to='main_monitor_data', title='set_experiment_basic_config',
                            data={"is_auto_calibration": is_checked},
                            time=time_util.get_format_from_time(time.time())))


def _patched_calibration_gas_state_change(self, state=None):
    current_mode = global_setting.get_setting("startup_calibration_mode", None)
    if current_mode == "air_co2":
        current_mode = "air"
    if current_mode not in {"none", "air", "full"}:
        current_mode = "full" if global_setting.get_setting("is_auto_calibration", False) else "none"

    msg_box = QMessageBox(self)
    msg_box.setIcon(QMessageBox.Icon.Question)
    msg_box.setWindowTitle("启动前校准模式")
    msg_box.setText("请选择开始实验前的校准模式：")

    air_button = msg_box.addButton("Air空气校准O2后开启实验", QMessageBox.ButtonRole.ActionRole)
    air_co2_button = msg_box.addButton("Air空气校准CO2后开启实验", QMessageBox.ButtonRole.ActionRole)
    full_button = msg_box.addButton("调零+调span后开启实验", QMessageBox.ButtonRole.ActionRole)
    msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    msg_box.setDefaultButton({
        "air": air_button,
        "air_co2": air_co2_button,
        "full": full_button,
    }.get(current_mode, air_button))
    msg_box.exec()

    clicked_button = msg_box.clickedButton()
    mode = None
    if clicked_button == air_button:
        mode = "air"
    elif clicked_button == air_co2_button:
        mode = "air_co2"
    elif clicked_button == full_button:
        mode = "full"

    if mode is None:
        return

    global_setting.set_setting("startup_calibration_mode", mode)
    global_setting.set_setting("is_auto_calibration", mode != "none")
    global_setting.set_setting("device_config_calibration_selected", True)

    send_message_queue = global_setting.get_setting("send_message_queue")
    if send_message_queue is not None:
        send_message_queue.put(
            ObjectQueueItem(
                origin='MainWindow_Index',
                to='main_monitor_data',
                title='set_experiment_basic_config',
                data={
                    "startup_calibration_mode": mode,
                    "is_auto_calibration": mode != "none",
                },
                time=time_util.get_format_from_time(time.time()),
            )
        )

    self.calibration_selection_changed_signal.emit(True, mode)


MainWindow_Index.calibration_gas_state_change = _patched_calibration_gas_state_change


def _patched_calibration_gas_state_change_v2(self, state=None):
    current_mode = global_setting.get_setting("startup_calibration_mode", None)
    if current_mode == "air_co2":
        current_mode = "air"
    if current_mode not in {"none", "air", "full"}:
        current_mode = "full" if global_setting.get_setting("is_auto_calibration", False) else "none"

    msg_box = QMessageBox(self)
    msg_box.setIcon(QMessageBox.Icon.Question)
    msg_box.setWindowTitle("启动前校准模式")
    msg_box.setText("请选择开始实验前的校准模式：")

    air_button = msg_box.addButton("Air空气校准后开启实验", QMessageBox.ButtonRole.ActionRole)
    full_button = msg_box.addButton("调零+调span后开启实验", QMessageBox.ButtonRole.ActionRole)
    msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    msg_box.setDefaultButton({
        "air": air_button,
        "full": full_button,
    }.get(current_mode, air_button))
    msg_box.exec()

    clicked_button = msg_box.clickedButton()
    mode = None
    if clicked_button == air_button:
        mode = "air"
    elif clicked_button == full_button:
        mode = "full"

    if mode is None:
        return

    global_setting.set_setting("startup_calibration_mode", mode)
    global_setting.set_setting("is_auto_calibration", mode != "none")
    global_setting.set_setting("device_config_calibration_selected", True)

    send_message_queue = global_setting.get_setting("send_message_queue")
    if send_message_queue is not None:
        send_message_queue.put(
            ObjectQueueItem(
                origin='MainWindow_Index',
                to='main_monitor_data',
                title='set_experiment_basic_config',
                data={
                    "startup_calibration_mode": mode,
                    "is_auto_calibration": mode != "none",
                },
                time=time_util.get_format_from_time(time.time()),
            )
        )

    self.calibration_selection_changed_signal.emit(True, mode)


MainWindow_Index.calibration_gas_state_change = _patched_calibration_gas_state_change_v2
