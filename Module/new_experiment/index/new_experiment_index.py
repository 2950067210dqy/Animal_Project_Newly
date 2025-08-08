import typing

from PyQt6 import QtGui
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QDockWidget, QMainWindow

from Module.new_experiment.ui.animal_window import AnimalWindow
from Module.new_experiment.ui.content_window import ContentWindow
from Module.new_experiment.ui.group_window import GroupWindow
from Module.new_experiment.ui.new_experiment import Ui_new_experiment_window
from theme.ThemeQt6 import ThemedWindow


class New_experiment_index(ThemedWindow):


    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        # 加载qss样式表
        super().showEvent(a0)
    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:


        super().hideEvent(a0)
    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        # 布局
        self.left_dock_widget:QDockWidget=None
        self.left_dock_widget_content:GroupWindow=None
        self.right_dock_widget:QDockWidget=None
        self.right_dock_widget_content: AnimalWindow = None
        self.center_widget_content:ContentWindow=None
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

        self.ui = Ui_new_experiment_window()

        self.ui.setupUi(self)

        self._retranslateUi()

        pass
    def _init_customize_ui(self) -> None:
        self.left_dock_widget: QDockWidget = self.findChild(QDockWidget, "left_dock_widget")
        self.right_dock_widget: QDockWidget =self.findChild(QDockWidget, "right_dock_widget")

        self.left_dock_widget_content:GroupWindow = GroupWindow()
        self.right_dock_widget_content:AnimalWindow = AnimalWindow()

        self.center_widget_content:ContentWindow=ContentWindow()
        if self.left_dock_widget != None:
            self.left_dock_widget.setWidget(self.left_dock_widget_content)
        if self.right_dock_widget != None:
            self.right_dock_widget.setWidget(self.right_dock_widget_content)
        self.setCentralWidget(self.center_widget_content)
        # self.center_widget_content.setParent(self.centralWidget())
