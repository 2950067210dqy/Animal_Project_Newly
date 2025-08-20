#程序自检
from PyQt6.QtWidgets import QDialog
from theme.ThemeQt6 import ThemedWindow
from ui.project_self_check import Ui_project_self_check_window
from ui.project_self_check_dialog import Ui_project_self_check_dialog
class Program_self_check_index(QDialog):
    def __init__(self):
        super().__init__()
        # 实例化ui
        self._init_ui()
        # 实例化自定义ui
        self._init_customize_ui()
        # 实例化功能
        self._init_function()
        # 加载qss样式表
        pass
    # 实例化ui
    def _init_ui(self, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        self.ui = Ui_project_self_check_dialog()
        self.ui.setupUi(self)
        # 设置窗口大小为屏幕大小
        self.setObjectName("Program_self_check_index")
        pass
    def _init_customize_ui(self):
        pass
    def _init_function(self):
        pass