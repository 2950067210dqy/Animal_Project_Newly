import math
import typing

from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QLabel

from Module.new_monitor_data.ui.Table_select_columns_paging_bottom import Table_select_columns_paging_bottom
from public.component.dock_widget.DraggableWindow import DemoDraggableDockWidget
from theme.ThemeQt6 import ThemedWindow


class MonitorDataWindows(ThemedWindow):
    def resizeEvent(self, a0: typing.Optional[QtGui.QResizeEvent]):
        self.setMinimumSize(0, 0)
    def __init__(self):
        super().__init__()
        # 存放创建的 dock 引用
        self.centerWidget = QWidget()
        self.setCentralWidget(self.centerWidget)
        self.dock_widget=DemoDraggableDockWidget(parent=self.centerWidget)
        self._docks_widget = []



    def clear_existing_docks(self):
        self.dock_widget.remove_all()
        for d in self._docks_widget:
            d.hide()
            d.deleteLater()
        self._docks_widget = []



    def create_tiled_docks(self,n=8,gids=[]):
        self.clear_existing_docks()

        for gid in gids:
            widget = Table_select_columns_paging_bottom(gid=gid)
            # ！！！！！！！！！！！！！！！！！！！！！！！！！！临时添加！！！！！！！！！！！！！！！！！！
            widget.on_replace_headers([1])

            self._docks_widget.append(widget)
        self.dock_widget.addFrames(self._docks_widget)

