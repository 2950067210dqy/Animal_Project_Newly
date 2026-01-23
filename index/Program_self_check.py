#程序自检
from PyQt6.QtWidgets import QDialog, QDialogButtonBox


from public.component.Guide_tutorial_interface.Tutorial_Manager import TutorialManager
from public.config_class.App_Setting import AppSettings
from public.config_class.global_setting import global_setting
from public.entity.BaseDialog import BaseDialog
from public.entity.enum.Public_Enum import Tutorial_Type
from theme.ThemeQt6 import ThemedWindow, ThemedDialog
from ui.project_self_check import Ui_project_self_check_window
from ui.project_self_check_dialog import Ui_project_self_check_dialog
class Program_self_check_index(ThemedDialog):
    def __init__(self):
        super().__init__()
        self.buttonBox=None

        # 实例化ui
        self._init_ui()
        # 实例化自定义ui
        self._init_customize_ui()
        # 实例化功能
        self._init_function()
        # 加载qss样式表
        pass
    # 实例化ui
    def _init_ui(self):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        self.ui = Ui_project_self_check_dialog()
        self.ui.setupUi(self)
        # 设置窗口大小为屏幕大小
        self.setObjectName("Program_self_check_index")
        pass
    def _init_customize_ui(self):
        self.buttonBox = self.ui.buttonBox
        super()._init_customize_ui()
        pass
    def _init_function(self):
        pass
    def setup_tutorial(self):
        #实例化提示引导器 下面式实例化模板
        if self.tutorial:
            self.tutorial.end_tutorial()

        self.tutorial = TutorialManager(self, "Program_self_check_index", Tutorial_Type.ARROW_GUIDE, global_setting.get_setting("app_setting", AppSettings()))

        # 连接教程完成信号
        self.tutorial.tutorial_completed.connect(self.on_tutorial_completed)

        # 添加更详细的引导步骤


        self.tutorial.add_step(self.buttonBox.button(QDialogButtonBox.StandardButton.Ok),
                               "单击此按钮可进入主程序。\n系统会为进入主程序。")

        self.tutorial.add_step(self.buttonBox.button(QDialogButtonBox.StandardButton.Cancel),
                               "单击此按钮可退出主程序。\n系统会为退出主程序。")

        self.tutorial.add_step(self.help_button,
                               "单击此按钮可调出教程。\n系统会调出教程。")