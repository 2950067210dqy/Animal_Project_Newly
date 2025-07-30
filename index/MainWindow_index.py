import importlib
import json
import os
from json import JSONDecodeError
from queue import Queue

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QLabel, QVBoxLayout, QToolBar
from loguru import logger

from my_abc.BaseInterfaceWidget import BaseInterfaceWidget, BaseInterfaceType
from my_abc.BaseModule import BaseModule
from public.config_class.global_setting import global_setting
from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow
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
        self.modules =[]
        # 正在显示的Widget
        self.active_widget:BaseWidget = None
        # 打开的窗口
        self.open_windows:[BaseWindow]=[]
        # 标题label
        self.title_label :QLabel = None
        # 内容layout
        self.content_layout :QVBoxLayout =None
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
        self.title_label = self.findChild(QLabel,"title_label")
        self.content_layout = self.findChild(QVBoxLayout,"content_layout")
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
        self.create_tool_bar()

        pass
    # 创建工具栏
    def create_tool_bar(self):
        # 创建 QToolBar
        toolbar = QToolBar("Toolbar")
        self.addToolBar(toolbar)
        # 创建动作（Action）
        action_one = QAction("窗口变换", self)
        action_one.triggered.connect(self.exchange_widget_and_window)
        action_two= QAction("更改主题颜色", self)
        action_two.triggered.connect(self.toggle_theme)
        # 将动作添加到工具栏
        toolbar.addAction(action_one)
        toolbar.addSeparator()
        toolbar.addAction(action_two)
        toolbar.addSeparator()
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
                    # module.interface_widget.frame_obj.setWindowTitle(module_title)
                    # # 如果是frame或widget就放入到centerwidget中，
                    # if module.interface_widget.type==BaseInterfaceType.FRAME or module.interface_widget.type==BaseInterfaceType.WIDGET:
                    #     module.interface_widget.frame_obj.resize(int(self.width() * 0.9), int(self.height() * 0.9))
                    #     module.interface_widget.frame_obj. setParent(self.centralWidget())
                    #     module.interface_widget.frame_obj.setVisible(False)
                    # else:
                    #     module.interface_widget.frame_obj.resize(int(self.width() * 0.7), int(self.height() * 0.7))
                    # 创建menu action
                    module.set_main_gui(main_gui=self)
                    action = QAction(module_title, self)
                    # 创建点击事件
                    action.triggered.connect( module.adjustGUIPolicy)
                    action.triggered.connect( module.interface_widget.frame_obj.show_frame)

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
            # 将正在显示的方式进行改变
            if self.active_widget is None and len(self.open_windows)!=0:
                # 将正在显示的方式进行改变
                for index in range(len(self.open_windows)):
                    if self.open_windows[index] is not None and module.interface_widget.frame_obj is self.open_windows[index]:
                        self.open_windows[index].close()

                        module.adjustGUIPolicy()
                        module.interface_widget.frame_obj.show_frame()
                        self.active_widget=module.interface_widget.frame_obj
                        break
            elif self.active_widget is not None and module.interface_widget.frame_obj is self.active_widget:
                # 从初始布局中移除 label

                self.active_widget.hide()
                self.title_label.setText("")
                self.content_layout.removeWidget(self.active_widget)
                self.active_widget.setParent(None)
                self.active_widget=None
                module.adjustGUIPolicy()
                module.interface_widget.frame_obj.show_frame()

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


