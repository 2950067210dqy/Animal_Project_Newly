import importlib
import json
import os
from json import JSONDecodeError
from queue import Queue

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QLabel, QVBoxLayout, QToolBar, QPushButton, QTabWidget
from loguru import logger

from Service import main_monitor_data, main_deep_camera, main_infrared_camera

from my_abc.BaseModule import BaseModule

from public.component.custom_status_bar import CustomStatusBar
from public.config_class.global_setting import global_setting
from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow
from public.entity.enum.Public_Enum import BaseInterfaceType
from theme.ThemeQt6 import ThemedWidget, ThemedWindow
from ui.MainWindow import Ui_MainWindow
from util.json_util import json_util


class MainWindow_Index(ThemedWindow):
    def closeEvent(self, event):
        if len(self.open_windows)!=0:
            # 可选择使用 QMessageBox 来确认是否关闭
            reply = QMessageBox.question(self, '关闭窗口',
                                         "当前还有其他子窗口未关闭，你确定要退出程序吗？",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                for window in self.open_windows:
                    window.close()
                event.accept()  # 关闭窗口
            else:
                event.ignore()  # 忽略关闭事件
        else:
            # 可选择使用 QMessageBox 来确认是否关闭
            reply = QMessageBox.question(self, '关闭窗口',
                                         "你确定要退出程序吗？",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()  # 关闭窗口
            else:
                event.ignore()  # 忽略关闭事件
        pass
    def __init__(self):
        super().__init__()
        # 点击开始实验 接受数据和存储数据的线程
        self.store_thread_sub=None
        self.send_thread_sub=None
        self.read_queue_data_thread_sub=None
        self.add_message_thread_sub=None
        # 深度相机线程
        # self.deep_camera_thread_sub_list = [camera_struct:dict,]
        #  camera_struct['id'] = num + 1
        #  camera_struct['camera'] = camera
        #  camera_struct['img_process'] = img_process
        self.deep_camera_thread_sub_list=[]
        self.deep_camera_read_queue_data_thread_sub=None
        self.deep_camera_delete_file_thread_sub=None
        # 红外相机线程
        # self.infrared_camera_thread_sub_list = [camera_struct:dict,]
        #  camera_struct['id'] = num + 1
        #  camera_struct['camera'] = camera
        self.infrared_camera_thread_sub_list = []
        self.infrared_camera_read_queue_data_thread_sub = None
        self.infrared_camera_delete_file_thread_sub = None
        # tool——bar-action 工具栏的action [{'obj_name':'','name';",'action':QAction}]
        self.tool_bar_actions = []
        # 模块
        self.modules =[]
        # 正在显示的Widget
        self.active_module_widgets:[BaseModule]=[]
        # 打开的窗口
        self.open_windows:[BaseModule]=[]
        # 工具栏
        self.toolbar = None
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
        self.status_bar = CustomStatusBar()
        self.setStatusBar(self.status_bar)
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
        self.tool_bar_actions.append({"name":name,"obj_name":obj_name,"action":action_one})


        name = "更改主题颜色"
        obj_name = "toggle_mode"
        action_two= QAction(name, self)
        action_two.setObjectName(obj_name)
        action_two.setToolTip(name)
        action_two.triggered.connect(self.toggle_theme)
        self.tool_bar_actions.append({"name":name,"obj_name":obj_name,"action":action_two})

        name = "开始实验"
        obj_name = "start_experiment"
        action_three = QAction(name, self)
        action_three.setObjectName(obj_name)
        action_three.setToolTip(name)
        action_three.triggered.connect(self.start_experiment)
        self.tool_bar_actions.append({"name": name,"obj_name":obj_name, "action": action_three})



        name = "停止实验"
        obj_name = "stop_experiment"
        action_four = QAction(name, self)
        action_four.setObjectName(obj_name)
        action_four.setToolTip(name)
        action_four.triggered.connect(self.stop_experiment)
        action_four.setDisabled(True)
        self.tool_bar_actions.append({"name": name,"obj_name":obj_name, "action": action_four})

        # 将动作添加到工具栏
        self.toolbar.addAction(action_one)
        self.toolbar.addSeparator()
        self.toolbar.addAction(action_two)
        self.toolbar.addSeparator()

        self.toolbar.addAction(action_three)
        self.toolbar.addAction(action_four)
        self.toolbar.addSeparator()
        pass
    def create_menu_bar(self):
    # 创建菜单
        for menu_dict in self.menu_name:
            # 创建文件菜单
            menu = self.menuBar().addMenu(menu_dict['text'])


            # 从module加载组件...
            for module in self.modules:
                module:BaseModule
                module_menu_name = module.menu_name
                module_title = module.title
                if module_menu_name is not None and module_menu_name != "" and "id" in module_menu_name and "id" in menu_dict and menu_dict["id"] == module_menu_name["id"]:

                    # 创建menu action
                    module.set_main_gui(main_gui=self)
                    action = QAction(module_title, self)
                    action.setToolTip(module_title)
                    # 创建点击事件
                    action.triggered.connect( module.adjustGUIPolicy)
                    action.triggered.connect( module.interface_widget.show)

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
                    if module_name=="main":
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
            module.interface_widget.show()
        for module in self.active_module_widgets:
            module.adjustGUIPolicy()
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

    def start_experiment(self):
        port = global_setting.get_setting("port")
        if port is None or port == "":
            reply = QMessageBox.question(self, '注意',
                                         "未设置串口，请去实验配置配置串口!",
                                         QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.No)
            return
        # 开始实验
        try:
            self.store_thread_sub, self.send_thread_sub, self.read_queue_data_thread_sub, self.add_message_thread_sub = main_monitor_data.main(
                port=port, q=global_setting.get_setting("queue"),
                send_message_q=global_setting.get_setting("send_message_queue"))

            self.deep_camera_thread_sub_list,self.deep_camera_read_queue_data_thread_sub,self.deep_camera_delete_file_thread_sub = main_deep_camera.main(q=global_setting.get_setting("queue"))
            self.infrared_camera_thread_sub_list,self.infrared_camera_read_queue_data_thread_sub,self.infrared_camera_delete_file_thread_sub = main_infrared_camera.main(q=global_setting.get_setting("queue"))



        except Exception as e:
            logger.error(f"开启实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"开启实验监测错误，原因：{e}")

        global_setting.set_setting("experiment", True)
        self.status_bar.update_status()
        self.status_bar.update_tip(f"开启实验监测成功！")
        for action_dict in self.tool_bar_actions:
            if action_dict["obj_name"] == "start_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(True)
            if action_dict["obj_name"] == "stop_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(False)
        for module in self.modules:
            if module.name == "Main_experiment_setting":
                module.interface_widget.frame_obj.start_btn.setEnabled(False)
                module.interface_widget.frame_obj.stop_btn.setEnabled(True)
                break
        pass

    def stop_experiment(self):

        try:
            if self.store_thread_sub is not None and self.store_thread_sub.isRunning():
                self.store_thread_sub.stop()
        except Exception as e:
            logger.error(f"关闭实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")
        try:
            if self.add_message_thread_sub is not None and self.add_message_thread_sub.isRunning():
                self.add_message_thread_sub.stop()
        except Exception as e:
            logger.error(f"关闭实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")
        try:
            if self.send_thread_sub is not None and self.send_thread_sub.isRunning():
                self.send_thread_sub.stop()
        except Exception as e:
            logger.error(f"关闭实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")
        try:
            if self.read_queue_data_thread_sub is not None and self.read_queue_data_thread_sub.isRunning():
                self.read_queue_data_thread_sub.stop()
        except Exception as e:
            logger.error(f"关闭实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")

        # 所有红外相机线程停止
        for camera_struct_l in self.infrared_camera_thread_sub_list:
            if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                try:
                    if camera_struct_l['camera'] is not None and camera_struct_l['camera'].isRunning():
                        camera_struct_l['camera'].stop()
                except Exception as e:
                    logger.error(f"关闭实验监测错误，原因：{e}")
                    self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")
        try:
            if self.infrared_camera_delete_file_thread_sub is not None and self.infrared_camera_delete_file_thread_sub.isRunning():
                self.infrared_camera_delete_file_thread_sub.stop()
        except Exception as e:
            logger.error(f"关闭实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")
        try:
            if self.infrared_camera_read_queue_data_thread_sub is not None and self.infrared_camera_read_queue_data_thread_sub.isRunning():
                self.infrared_camera_read_queue_data_thread_sub.stop()
        except Exception as e:
            logger.error(f"关闭实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")

        # 所有深度相机线程停止
        for camera_struct_l in self.deep_camera_thread_sub_list:
            if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                try:
                    if camera_struct_l['camera'] is not None and camera_struct_l['camera'].isRunning():
                        camera_struct_l['camera'].stop()
                except Exception as e:
                    logger.error(f"关闭实验监测错误，原因：{e}")
                    self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")
            if len(camera_struct_l) != 0 and 'img_process' in camera_struct_l:
                try:
                    if camera_struct_l['img_process'] is not None and camera_struct_l['img_process'].isRunning():
                        camera_struct_l['img_process'].stop()
                except Exception as e:
                    logger.error(f"关闭实验监测错误，原因：{e}")
                    self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")
        try:
            if self.deep_camera_delete_file_thread_sub is not None and self.deep_camera_delete_file_thread_sub.isRunning():
                self.deep_camera_delete_file_thread_sub.stop()
        except Exception as e:
            logger.error(f"关闭实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")
        try:
            if self.deep_camera_read_queue_data_thread_sub is not None and self.deep_camera_read_queue_data_thread_sub.isRunning():
                self.deep_camera_read_queue_data_thread_sub.stop()
        except Exception as e:
            logger.error(f"关闭实验监测错误，原因：{e}")
            self.status_bar.update_tip(f"关闭实验监测错误，原因：{e}")



        global_setting.set_setting("experiment", False)
        self.status_bar.update_status()
        self.status_bar.update_tip(f"关闭实验监测成功！")
        for action_dict in self.tool_bar_actions:
            if action_dict["obj_name"] == "start_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(False)
            if action_dict["obj_name"] == "stop_experiment":
                action_dict["action"]: QAction
                action_dict["action"].setDisabled(True)
        for module in self.modules:
            if module.name == "Main_experiment_setting":
                module.interface_widget.frame_obj.start_btn.setEnabled(True)
                module.interface_widget.frame_obj.stop_btn.setEnabled(False)
                break
        # 停止实验
        pass

    def close_tab(self, index):
        """关闭标签页"""
        self.tab_widget.widget(index).hide()
        self.tab_widget.removeTab(index)