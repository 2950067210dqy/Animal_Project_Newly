import importlib
import json
import os
from json import JSONDecodeError

from PyQt6 import QtWidgets, QtCore
from loguru import logger


from config_class.global_setting import global_setting
from my_abc.BaseModule import BaseModule
from theme.ThemeQt6 import ThemedWidget, ThemedWindow
from ui.MainWindow import Ui_MainWindow
from util.json_util import json_util


class MainWindow_Index(ThemedWindow):
    def __init__(self):
        super().__init__()
        self.modules =[]
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
        # 加载模块
        self.modules = self.load_modules()
        # 实例化菜单
        # [{id:0,text:"文件"},....]
        menu_name=global_setting.get_setting("gui_config")['menu']['menu_name']
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
                self.create_menu_bar()
            pass
        pass

    def create_menu_bar(self):
    # 创建菜单
        for menu_dict in self.menu_name:
            # 创建文件菜单
            menu = self.menuBar().addMenu(menu_dict['text'])
        pass
    def _retranslateUi(self, **kwargs):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate(self.objectName(),global_setting.get_setting("gui_config")["window"]["title"]))
    pass

    def load_modules(self):
        #动态加载模块
        modules = []
        module_dir = 'Module'  # 插件目录
        for filename in os.listdir(module_dir):
            if filename.endswith('.py'):
                module_name = filename[:-3]  # 去掉 .py 后缀
                file_path = os.path.join(module_dir, filename)

                # 动态加载模块
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # 查找到实现 BasePlugin 的类
                for name, obj in module.__dict__.items():
                    if isinstance(obj, type) and issubclass(obj, BaseModule):
                        modules.append(obj())

        return modules

        pass