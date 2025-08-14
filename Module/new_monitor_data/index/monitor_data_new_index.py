import typing

from PyQt6 import QtGui
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QDockWidget

from Module.new_monitor_data.ui.monitor_data_new import Ui_monitor_data_new
from theme.ThemeQt6 import ThemedWindow


class Monitor_data_new_index(ThemedWindow):




    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        self.left_top_dock_widget:QDockWidget = None
        self.left_bottom_dock_widget:QDockWidget = None
        self.right_dock_widget:QDockWidget = None
        # 实例化ui
        self._init_ui(parent, geometry, title)
        # 实例化自定义ui
        self._init_customize_ui()
        # 实例化功能
        self._init_function()
        # 加载qss样式表
        self._init_style_sheet()
        pass

        # 实例化ui

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        # 有父窗口添加父窗口
        if parent != None and geometry != None:
            self.setParent(parent)
            self.setGeometry(geometry)
        else:
            pass

        self.ui = Ui_monitor_data_new()

        self.ui.setupUi(self)

        self._retranslateUi()

        pass
    def _init_customize_ui(self) -> None:
        self.left_top_dock_widget = self.findChild(QDockWidget, "left_top_dock_widget")
        self.left_bottom_dock_widget = self.findChild(QDockWidget, "left_bottom_dock_widget")
        self.right_dock_widget = self.findChild(QDockWidget, "right_dock_widget")
        if self.left_bottom_dock_widget is not None:
            self.left_bottom_dock_widget.setMinimumSize(int(self.width() * 0.7), int(self.height() * 0.4))
        if self.left_top_dock_widget is not None:
            self.left_top_dock_widget.setMinimumSize(int(self.width() * 0.7), int(self.height() * 0.6))
        if self.right_dock_widget is not None:
            self.right_dock_widget.setMinimumSize(int(self.width() * 0.3), int(self.height()))
        pass
