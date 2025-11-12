import importlib
import json
import os
import time
from json import JSONDecodeError
from PyQt6 import QtCore
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMessageBox, QVBoxLayout, QToolBar, QTabWidget, QDialog, QMenu, QMenuBar, QWidget, \
    QApplication
from loguru import logger


from Service import main_monitor_data, main_deep_camera, main_infrared_camera
from Service.UFC_UGC_ZOS_Service.function.gas_path_system.Gas_path_system import ZOS_gas_path_system, \
    UFC_gas_path_system, UGC_gas_path_system
from Service.UFC_UGC_ZOS_Service.index.UFC_UGC_ZOS_index import UFC_UGC_ZOS_index
from my_abc.BaseModule import BaseModule
from public.component.Guide_tutorial_interface.Tutorial_Manager import TutorialManager
from public.component.custom_status_bar import CustomStatusBar
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

        # 停止实验用到的 返回状态，当深度相机、红外相机、气路、鼠笼内、存储数据都发过返回消息则关闭关闭实验窗口
        self.old_Stop_experiment_status_text_reTurn =None
        self.old_stop_status_counts = 0
        self.old_stop_status_max = 5
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
                        #启动气路完成，关闭开始实验窗口
                        if self.window is not None and self.window.start_dialog is not None :

                            self.window.start_dialog.update_progress_value(self.window.start_dialog.progress_max)
                    case "stop_deep_camera_return" |"stop_infrared_camera_return"|"stop_gap_system_return"|"stop_monitor_data_return"|"stop_store_data_return":
                        if message.data and self.window:
                            #  更新气路运行消息
                            # 将运行信息放入status栏中
                            self.window.status_bar.update_tip(message.data)
                            if self.window.stop_dialog is not None:
                                self.window.stop_dialog.insert_data_signal.emit(f"{message.data} ")
                                # self.window.start_dialog.update_progress_value(1)
                            pass

                            if self.old_Stop_experiment_status_text_reTurn is not None and message.title !=self.old_Stop_experiment_status_text_reTurn:
                                self.old_Stop_experiment_status_text_reTurn=message.title
                                self.old_stop_status_counts += 1
                            else:
                                self.old_Stop_experiment_status_text_reTurn = message.title
                            if self.old_stop_status_counts >= self.old_stop_status_max:
                                # 停止完成，关闭停止实验窗口
                                self.old_Stop_experiment_status_text_reTurn = None
                                self.old_stop_status_counts =0

                                QTimer.singleShot(3000,self.close_stop_experiment_dialog)

                        pass
                    case 'close_stop_experiment_dialog':
                        # 停止完成，关闭停止实验窗口
                        self.close_stop_experiment_dialog()
                    case _:
                        pass

            else:
                # 把消息放回去
                self.queue.put(message)
    def close_stop_experiment_dialog(self):
        if self.window is not None and self.window.stop_dialog is not None:
            self.window.stop_dialog.update_progress_value(self.window.stop_dialog.progress_max)
read_queue_data_thread = read_queue_data_Thread(name="MainWindow_index_read_queue_data_thread")
class MainWindow_Index(ThemedWindow):
    # 根据程序状态来改变是否可以点击的组件
    change_enable_component_app_state_signal = QtCore.pyqtSignal()

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
            self.tutorial.add_step(tool_bar_action['action'].associatedObjects()[1],
                               f"单击此按钮是{tool_bar_action['name']}\n{tool_bar_action['tip']}")
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
        # 模块
        self.modules =[]
        # 正在显示的Widget
        self.active_module_widgets:[BaseModule]=[]
        # 打开的窗口
        self.open_windows:[BaseModule]=[]
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
                logger.error(e)
                self.menu_name = None
            if self.menu_name is not None:
                # 创建菜单栏
                self.create_menu_bar()
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
        pass
    # 创建工具栏
    def create_tool_bar(self):
        # 创建 QToolBar
        self.toolbar = QToolBar("Toolbar")
        self.addToolBar(self.toolbar)
        # 创建动作（Action）
        name ="窗口变换"
        obj_name ="window_exchange"
        action_one = QAction(name, self)
        action_one.setObjectName(obj_name)
        action_one.setToolTip(name)
        action_one.triggered.connect(self.exchange_widget_and_window)
        self.tool_bar_actions.append({"name":name,"obj_name":obj_name,"action":action_one,"app_state":AppState.INITIALIZED,'tip':"单击此按钮会将打开的窗口变成内嵌抽屉页。"})
        name = "更改主题颜色"
        obj_name = "toggle_mode"
        action_two= QAction(name, self)
        action_two.setObjectName(obj_name)
        action_two.setToolTip(name)
        action_two.triggered.connect(self.toggle_theme)
        self.tool_bar_actions.append({"name":name,"obj_name":obj_name,"action":action_two,"app_state":AppState.INITIALIZED,'tip':"单击此按钮会将程序的主题颜色变换黑色和白色"})
        name = "开始实验"
        obj_name = "start_experiment"
        action_three = QAction(name, self)
        action_three.setObjectName(obj_name)
        action_three.setToolTip(name)
        action_three.triggered.connect(self.start_experiment)
        self.tool_bar_actions.append({"name": name,"obj_name":obj_name, "action": action_three,"app_state":AppState.CONFIGURING,'tip':"单击此按钮会将开始实验，但是必须等待配置完成才能单击该按钮。"})
        name = "暂停实验"
        obj_name = "pause_experiment"
        action_four = QAction(name, self)
        action_four.setObjectName(obj_name)
        action_four.setToolTip(name)
        action_four.setDisabled(True)
        action_four.triggered.connect(self.pause_experiment)
        self.tool_bar_actions.append({"name": name,"obj_name":obj_name, "action": action_four,"app_state":AppState.CONFIGURING,'tip':"单击此按钮会将暂停实验，必须在实验中才能单击该按钮。"})

        name = "停止实验"
        obj_name = "stop_experiment"
        action_five = QAction(name, self)
        action_five.setObjectName(obj_name)
        action_five.setToolTip(name)
        action_five.triggered.connect(self.stop_experiment)
        action_five.setDisabled(True)
        self.tool_bar_actions.append({"name": name,"obj_name":obj_name, "action": action_five,"app_state":AppState.CONFIGURING,'tip':"单击此按钮会将停止实验，并将实验数据保存。"})

        name = "导出实验数据"
        obj_name = "export_experiment_datas"
        action_six = QAction(name, self)
        action_six.setObjectName(obj_name)
        action_six.setToolTip(name)
        action_six.triggered.connect(self.export_experiment_datas)
        action_six.setDisabled(True)
        self.tool_bar_actions.append(
            {"name": name, "obj_name": obj_name, "action": action_six, "app_state": AppState.MONITORING,
             'tip': "单击此按钮会将将实验数据保存。"})

        name = "重置教程页"
        obj_name = "reset_guidance"
        action_final = QAction(name, self)
        action_final.setObjectName(obj_name)
        action_final.setToolTip(name)
        action_final.triggered.connect(self.reset_guidance)
        action_final.setDisabled(True)
        self.tool_bar_actions.append(
            {"name": name, "obj_name": obj_name, "action": action_final, "app_state": AppState.INITIALIZED,
             'tip': "单击此按钮会将重置教程。"})

        # 将动作添加到工具栏
        self.toolbar.addAction(action_one)
        self.toolbar.addSeparator()
        self.toolbar.addAction(action_two)
        self.toolbar.addSeparator()
        self.toolbar.addAction(action_three)
        self.toolbar.addAction(action_four)
        self.toolbar.addAction(action_five)
        self.toolbar.addSeparator()
        self.toolbar.addAction(action_six)
        self.toolbar.addSeparator()
        self.toolbar.addAction(action_final)
        self.toolbar.addSeparator()
    def create_menu_bar(self):
    # 创建菜单
        for menu_dict in self.menu_name:
            # 创建文件菜单
            menu = self.menuBar().addMenu(menu_dict['text'])
            menu.setToolTip(menu_dict.get('tip',""))
            # 从module加载组件...
            for module in self.modules:
                module:BaseModule
                module_menu_name = module.menu_name
                module_title = module.title
                if module_menu_name is not None and module_menu_name != "" and "id" in module_menu_name and "id" in menu_dict and menu_dict["id"] == module_menu_name["id"]:
                    # 创建menu action
                    module.set_main_gui(main_gui=self)
                    action = QAction(module_title, self)
                    action.setObjectName(f"{module.name}")
                    # 创建点击事件
                    # action.triggered.connect(module.start_service)
                    action.triggered.connect(module.click_method)
                    # action.triggered.connect( module.adjustGUIPolicy)
                    # action.triggered.connect( module.interface_widget.show)
                    self.menu_bar_actions.append(
                        {"name": module_title, "obj_name": f"{module.name}", "action": action, "app_state": module.app_state})
                    # 将操作添加到文件菜单
                    menu.addAction(action)
                    menu.addSeparator()  # 添加分隔线
        pass
    def _retranslateUi(self, **kwargs):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate(self.objectName(),global_setting.get_setting("configer")["window"]["title"]))
    pass
    def load_modules(self):
        #动态加载模块
        modules = []
        module_dir = 'Module'  # 插件目录
        # 递归遍历指定目录
        for dirpath, dirnames, filenames in os.walk(module_dir):
            for filename in filenames:
                if filename.endswith('.py'):
                    module_name = filename[:-3]# 去掉 .py 后缀
                    if module_name.startswith("main"):
                        file_path = os.path.join(dirpath, filename)
                        # 动态加载模块
                        spec = importlib.util.spec_from_file_location(module_name, file_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)#装载module
                        # 查找到实现 BasePlugin 的类
                        for name, obj in module.__dict__.items():
                            if name =="BaseModule":
                                # 抽象类跳过
                                continue
                            if isinstance(obj, type) and issubclass(obj, BaseModule):
                                modules.append(obj())
        return modules
        pass
    def exchange_widget_and_window(self):
        """widget和window相互转换"""
        # 将module的显示方式改变
        for module in self.modules:
            if module.interface_widget.type == BaseInterfaceType.WIDGET or module.interface_widget.type == BaseInterfaceType.FRAME:
                module.interface_widget.type=BaseInterfaceType.WINDOW

            else:
                module.interface_widget.type=BaseInterfaceType.WIDGET
        new_open_windows = []
        new_active_module_widgets=[]
        # 将正在显示的方式进行改变
        if self.open_windows is not None and len(self.open_windows)!=0:
            #窗口-》frame
            # 将正在显示的方式进行改变
            index = 0
            last_module=None
            while index<len(self.open_windows) or len(self.open_windows)==1:
                if index>=len(self.open_windows):
                    index=0
                module = self.open_windows[index]
                if last_module is module:
                    break
                last_module = module
                module.close()
                if module not in self.active_module_widgets:
                    new_active_module_widgets.append(module)
                index+=1
        if self.active_module_widgets is not None and len(self.active_module_widgets)!=0:
            # 从初始布局中移除 label
            # frame-》窗口
            index = 0
            last_module = None
            while index<len(self.active_module_widgets) or len(self.active_module_widgets)==1:
                if index>=len(self.active_module_widgets):
                    index=0
                module = self.active_module_widgets[index]
                if last_module is module:
                    break
                last_module = module
                module.setParent(None)
                module.hide()
                if module not in self.open_windows:
                    new_open_windows.append(module)
                index+=1
        # 删除所有标签页和widgets
        while self.tab_widget.count() > 0:  # 直到没有标签页
            self.tab_widget.removeTab(0)  # 删除第一个标签页
        self.open_windows.extend(new_open_windows)
        self.active_module_widgets.extend(new_active_module_widgets)
        for module in self.open_windows:
            module.adjustGUIPolicy()
            module.interface_widget.setMinimumSize(0,0)
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
    def start_update_gui(self,resolve,reject):
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
                # action_dict["action"].setDisabled(False)
        self.setEnabled(True)
        resolve()
        #   延遲打開窗口
    def start_open_window(self,resolve,reject):
        QTimer.singleShot(1 * 1000, self.open_monitor_data_window)
        resolve()

    def start_experiment(self):

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
        # self.start_thread = Start_experiment_thread(name="start_thread",window=self)
        # self.start_thread.start()

        send_message_queue = global_setting.get_setting("send_message_queue")
        send_message_queue.put(ObjectQueueItem(origin='MainWindow_Index', to='main_monitor_data', title='start',
                                               data={
                                                   'start_experiment_time':global_setting.get_setting("start_experiment_time"),
                                                    'pause_experiment_time':global_setting.get_setting("pause_experiment_time"),
                                                   'relieve_pause_experiment_time':global_setting.get_setting("relieve_pause_experiment_time")
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
            queue=global_setting.get_setting("queue")
            queue.put(           message_struct)
        AsyPromise(self.start_update_gui).then(
            AsyPromise(self.show_open_dialog).then(
                AsyPromise(self.start_open_window).then().catch(lambda e: logger.error(e))
            ).catch(lambda e: logger.error(e))
        ).catch(lambda e: logger.error(e))
        pass
    def show_open_dialog(self,resolve,reject):
        if self.start_dialog is None:
            self.start_dialog = AnimatedLoadingDialog(countdown_seconds=float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['wait_time'])+15,title="开始实验",message="正在启动气路...")
        else:
            self.start_dialog.reset_progress()
            self.start_dialog.clear_list_data()
            self.start_dialog.deleteLater()
            self.start_dialog = AnimatedLoadingDialog(
                countdown_seconds=float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['wait_time'])+15,
                title="开始实验", message="正在启动气路...")

        # self.start_dialog.set_progress_range(0, ZOS_gas_path_system.process_nums+UFC_gas_path_system.process_nums+UGC_gas_path_system.process_nums)
        result = self.start_dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            resolve()
        else:
            self.stop_experiment()
            reject()
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
                pause_experiment_time=global_setting.get_setting("pause_experiment_time",[])
                pause_experiment_time.append(time.time())
                global_setting.set_setting("pause_experiment_time",pause_experiment_time )
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
                        action_dict["name"]="解除暂停实验"
                    else:
                        action_dict["name"] = "暂停实验"
                    action_dict["action"].setToolTip(action_dict["name"])
                    action_dict["action"].setText(action_dict["name"])
            self.setEnabled(True)
        pass
    def stop_experiment(self):

        self.setEnabled(False)
        self.status_bar.update_tip(f"正在关闭实验监测...")
        # self.stop_experiment_thread = Stop_experiment_thread(name="stop_experiment_thread",window=self)
        # self.stop_experiment_thread.start()

        send_message_queue = global_setting.get_setting("send_message_queue")
        send_message_queue.put( ObjectQueueItem(origin='MainWindow_Index', to='main_monitor_data', title='stop',
                        time=time_util.get_format_from_time(time.time())))
        message_structs = [
            ObjectQueueItem(origin='MainWindow_Index', to='main_deep_camera', title='stop',
                            time=time_util.get_format_from_time(time.time())),
            ObjectQueueItem(origin='MainWindow_Index', to='main_infrared_camera', title='stop',
                            time=time_util.get_format_from_time(time.time())),

        ]
        for message_struct in message_structs:
            queue = global_setting.get_setting("queue")
            queue.put(message_struct)
        self.stop_store_info_Qtimer()
        AsyPromise(self.show_stop_dialog).then(
                AsyPromise(self.stop_update_gui).then(


            ).catch(lambda e: logger.error(e))
        ).catch(
            lambda e:logger.error(e)
        )

        # self.stop_store_info()
        pass
    def stop_update_gui(self,resolve,reject):
        logger.error("stop_update_gui")
        global_setting.set_setting("app_state", AppState.CONFIGURING)
        global_setting.set_setting("stop_experiment_time", time.time())



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

        pass

    def show_stop_dialog(self,resolve,reject):
        if self.stop_dialog is None:
            self.stop_dialog = AnimatedLoadingDialog(countdown_seconds=float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['wait_time'])+15,title="停止实验",message="正在停止实验...")
        else:
            self.stop_dialog.reset_progress()
            self.stop_dialog.clear_list_data()
            self.stop_dialog.deleteLater()
            self.stop_dialog = AnimatedLoadingDialog(
                countdown_seconds=float(global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['wait_time'])+15,
                title="停止实验",message="正在停止实验...")

        # self.start_dialog.set_progress_range(0, ZOS_gas_path_system.process_nums+UFC_gas_path_system.process_nums+UGC_gas_path_system.process_nums)
        result = self.stop_dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            resolve()
        else:
            resolve()
    def stop_store_info_Qtimer(self):
        QTimer.singleShot(100, self.stop_store_info)

    def stop_store_info(self):

        # 停止实验 将文件夹的数据合并成一个数据文件
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
            custom_data_file_util.save_folder_contents_as_custom_file(folder_path_data)
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
                custom_data_file_util.export_data_to_csv(export_file_path=None, file_name=os.path.basename(folder_path_data))
                # custom_data_file_util.save_folder_contents_as_custom_file(folder_path_data,is_delete_original_data_file=False)

        QTimer.singleShot(1000, stop_store_info_Qtimer)
    def close_tab(self, index):
        """关闭标签页"""
        self.tab_widget.widget(index).hide()
        self.tab_widget.removeTab(index)
    def change_enable_component_app_state(self):
        # 更新程序状态值
        self.status_bar.update_app_state()
        #根据程序状态来改变是否可以点击的组件'
        #设置是否可以点击 menu_bar
        for menu_bar_action in self.menu_bar_actions:
            if menu_bar_action["app_state"] > global_setting.get_setting("app_state",AppState.INITIALIZED):
                menu_bar_action["action"].setEnabled(False)
            else:
                menu_bar_action["action"].setEnabled(True)
                #特殊情况
                if global_setting.get_setting("app_state",AppState.INITIALIZED) == AppState.MONITORING \
                    and menu_bar_action['obj_name'] in ["Main_New_experiment", "Main_New_experiment_open"]:
                    menu_bar_action["action"].setEnabled(False)
        # 设置是否可以点击 tool_bar
        for tool_bar_action in self.tool_bar_actions:
            if tool_bar_action["app_state"] > global_setting.get_setting("app_state",AppState.INITIALIZED):
                tool_bar_action["action"].setEnabled(False)
            else:
                tool_bar_action["action"].setEnabled(True)
            # 特殊按钮需要特殊配置
            if tool_bar_action['obj_name'] in ["stop_experiment", "pause_experiment","toggle_mode","window_exchange"]:
                tool_bar_action["action"].setEnabled(False)
        pass


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