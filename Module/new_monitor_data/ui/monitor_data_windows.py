import math
import typing

from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QLabel

from Module.new_monitor_data.ui.Table_select_columns_paging_bottom import Table_select_columns_paging_bottom
from public.component.dock_widget.DraggableWindow import DemoDraggableDockWidget
from theme.ThemeQt6 import ThemedWindow, ThemedWidget


class MonitorDataWindows(ThemedWindow):
    def resizeEvent(self, a0: typing.Optional[QtGui.QResizeEvent]):
        self.setMinimumSize(0, 0)
    def __init__(self):
        super().__init__()
        # 存放创建的 dock 引用
        self.centerWidget = ThemedWidget()
        self.setCentralWidget(self.centerWidget)
        self.dock_widget=DemoDraggableDockWidget(parent=self.centerWidget)
        self._docks_widget = []








