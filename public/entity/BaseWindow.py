import typing

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import QRect, Qt, QSize
from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLayout, \
    QScrollArea, QSizePolicy
from loguru import logger


class BaseWindow(QMainWindow):
    def resizeEvent(self, a0 :typing.Optional[QtGui.QResizeEvent]):
        # 获取新的大小
        new_size:QSize = a0.size()

        old_size:QSize = a0.oldSize()
        # logger.error(f"resizeEvent:{new_size}|{old_size}")


        self.centralWidget().resize(new_size.width(),new_size.height())
        self.centralWidget().updateGeometry()
        # 直接下一级的子控件
        children = self.centralWidget().findChildren(QWidget)  # 获取所有子 QWidget
        direct_children = [child for child in children if child.parent() == self.centralWidget()]
        for child in direct_children:
            child.resize(new_size.width(), new_size.height())
            child.updateGeometry()
        # 更新scroll_area
        scroll_areas = self.findChildren(QScrollArea)
        for scroll_area in scroll_areas:
            scroll_area.updateGeometry()
        # 设置最小size 以免变形
        self.setMinimumSize(self.calculate_minimum_suggested_size())

        super().resizeEvent(a0)

    def calculate_minimum_suggested_size(self):
        max_width = 0
        max_height = 0
        # 使用 findChildren 查找所有的布局
        layouts = self.findChildren(QVBoxLayout) + self.findChildren(QHBoxLayout)+self.findChildren(QGridLayout)+self.findChildren(QFormLayout)
        for layout in layouts:
            if layout.parent() !=self.centralWidget():
                size = layout.sizeHint()
                max_width = max(max_width, size.width())
                max_height = max(max_height, size.height())
        return QSize(max_width, max_height)
    def __init__(self):
        super().__init__(flags=Qt.WindowType.Window)

    def _init_ui(self):
        # 实例化ui
        pass

    def _init_customize_ui(self):
        # 实例化自定义ui
        pass

    def _init_function(self):
        # 实例化功能
        pass

    def _init_style_sheet(self):
        # 加载qss样式表
        pass
    def _init_custom_style_sheet(self):
        # 加载自定义qss样式表
        pass

    # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码 应该是可以统一将文字改为其他语言
    def _retranslateUi(self, **kwargs):
        _translate = QtCore.QCoreApplication.translate

    # 添加子UI组件
    def set_child(self, child: QMainWindow, geometry: QRect, visible: bool = True):
        # 添加子组件
        child.setParent(self)
        # 添加子组件位置
        child.setGeometry(geometry)
        # 添加子组件可见性
        child.setVisible(visible)
        pass

    def get_ancestor(self, ancestor_obj_name):
        # 获取当前对象的祖先对象
        ancestor = self
        while ancestor is not None and ancestor.objectName() != ancestor_obj_name:
            ancestor = ancestor.parent()
        if ancestor == self:
            logger.info(f"{self.objectName()}没有祖先组件")
        elif ancestor is None:
            logger.info(f"{self.objectName()}未找到祖先{ancestor_obj_name}")
        else:
            logger.info(f"{self.objectName()}找到祖先{ancestor_obj_name}")
        self.ancestor = ancestor

    # 显示窗口
    def show_frame(self):
        self.show()
        pass