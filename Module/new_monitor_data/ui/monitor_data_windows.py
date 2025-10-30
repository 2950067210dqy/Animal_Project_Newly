import copy
import math
import typing
from enum import Enum

from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QLabel, QHBoxLayout, QButtonGroup, QRadioButton

from Module.new_monitor_data.ui.Table_select_columns_paging_bottom import Table_select_columns_paging_bottom
from public.component.dock_widget.DraggableWindow import DemoDraggableDockWidget
from public.entity.BaseFrame import BaseFrame
from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow
from theme.ThemeQt6 import ThemedWindow, ThemedWidget

class Show_Type(Enum):
    ALL = 0
    EACH = 1

    def __lt__(self, other):
        if other is None:
            return False
        return self.value < other.value

    def __le__(self, other):
        if other is None:
            return False
        return self.value <= other.value

    def __gt__(self, other):
        if other is None:
            return False
        return self.value > other.value

    def __ge__(self, other):
        if other is None:
            return False
        return self.value >= other.value

    def __eq__(self, other):
        if other is None:
            return False
        return self.value == other.value

    def __ne__(self, other):
        if other is None:
            return False
        return self.value != other.value
class MonitorDataWindows(ThemedWidget):
    def resizeEvent(self, a0: typing.Optional[QtGui.QResizeEvent]):
        self.setMinimumSize(0, 0)
    def __init__(self):
        super().__init__()
        self.gids = []
        self.n = 0
        # 默认看总表
        self.default_show = Show_Type.ALL
        # 当前看
        self.current_show = copy.deepcopy(self.default_show)
        self.show_radio_data = [
            {"text": "总表查看", "value": Show_Type.ALL},
            {"text": "分表查看", "value":  Show_Type.EACH}
        ]

        self.main_layout = QVBoxLayout()
        self.top_layout = QHBoxLayout()
        self.button_group = QButtonGroup()
        self.show_radios = []
        for i, data in enumerate(self.show_radio_data):
            radio = QRadioButton(data["text"])
            if i ==0:
                radio.setStyleSheet("""
                QRadioButton{
                    margin-left:15px;
                }
                """)
            radio.setProperty("value", data["value"])  # 存储数据值
            # 设置默认选择
            if data["value"]==self.default_show:
                radio.setChecked(True)
            self.show_radios.append(radio)
            self.button_group.addButton(radio, i)
            self.top_layout.addWidget(radio)
        self.top_layout.addStretch(7)
        # 连接信号
        self.button_group.buttonClicked.connect(self.on_show_selection_changed)

        self.content_layout = QVBoxLayout()
        self.content_widget=DemoDraggableDockWidget()
        self.content_layout.addWidget(self.content_widget)

        self.main_layout.addLayout(self.top_layout,stretch=0)
        self.main_layout.addLayout(self.content_layout,stretch=9)
        self.setLayout(self.main_layout)
        # 存放创建的 dock 引用
        self._docks_widget = []
    def clear_existing_docks(self):
        self.content_widget.remove_all()
        for d in self._docks_widget:
            d:BaseWindow|BaseWidget|BaseFrame
            # 把悬浮出去的窗口也关闭
            d.get_ancestor()
            if hasattr(d.ancestor,"detached_window"):
                if d.ancestor.detached_window is not None:
                    d.ancestor.detached_window.close()
            d.ancestor.hide()
            d.ancestor.deleteLater()
            if d is not None:
                d.hide()
                d.deleteLater()
        self._docks_widget = []

    def create_tiled_docks(self, n=8, gids=[]):
        if n !=0:
            self.n=n
        if len(gids)>0:
            self.gids = gids
        self.clear_existing_docks()
        if self.current_show == Show_Type.EACH:
            for gid in gids:
                widget = Table_select_columns_paging_bottom(gid=gid)
                widget.setWindowTitle(f"通道/鼠笼 {gid} {'(参考气)' if gid==0 else ''}")
                # ！！！！！！！！！！！！！！！！！！！！！！！！！！临时添加！！！！！！！！！！！！！！！！！！
                widget.on_replace_headers([1])

                self._docks_widget.append(widget)
            self.content_widget.addFrames(self._docks_widget)
        else:
            widget = Table_select_columns_paging_bottom(gid=-1)
            widget.setWindowTitle(f"通道/鼠笼 总表")
            # ！！！！！！！！！！！！！！！！！！！！！！！！！！临时添加！！！！！！！！！！！！！！！！！！
            widget.on_replace_headers([1])
            self._docks_widget.append(widget)
            self.content_widget.addFrames(self._docks_widget)

    def on_show_selection_changed(self, button):
        # 获取自定义数据值
        self.setRadiosEnable(enable=False)
        value = button.property("value")
        if self.current_show != value:
            self.current_show =value
            if self.current_show == Show_Type.EACH:
                self.create_tiled_docks(n=self.n, gids=self.gids)
            else:
                self.create_tiled_docks()
        QTimer.singleShot(3000, lambda: self.setRadiosEnable(enable=True))
    def setRadiosEnable(self,enable = True):
        for radios in self.show_radios:
            radios.setEnabled(enable)


