import abc
import typing

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import QRect, Qt, QSize
from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLayout, \
    QScrollArea, QSizePolicy, QMessageBox, QTabWidget, QGroupBox, QTableWidget
from loguru import logger


class BaseWindow(QMainWindow):

    def closeEvent(self, event):
        # 关闭事件
        if self.main_gui is not None:

            for index in range(len(self.main_gui.open_windows)):
                if self.main_gui.open_windows[index] is self:
                    del self.main_gui.open_windows[index]
                    break
                index += 1

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
        # # 更新scroll_area
        # scroll_areas = self.findChildren(QScrollArea)
        # for scroll_area in scroll_areas:
        #     scroll_area:QScrollArea
        #     if scroll_area.widget() is not None:
        #
        #         # scroll_area.widget().setFixedSize(int(new_size.width()*0.95), int(new_size.height()*0.95))
        #         scroll_area.widget().updateGeometry()
        #     scroll_area.updateGeometry()
        # 更新tab——widget
        # tab_widget = self.findChildren(QTabWidget)
        # if tab_widget is not None and len(tab_widget) > 0:
        #     for tab in tab_widget:
        #         tab:QTabWidget
        #         tab.resize(new_size.width(), new_size.height())
        #         tab.updateGeometry()
        #         # 找到每一个tab里的widget
        #         for index in range(tab.count()):
        #             widget = tab.widget(index)  # 获取选项卡中的 QWidget
        #             widget.resize(new_size.width(), new_size.height())
        #             widget.updateGeometry()
        #         pass
        #     pass
        #更新groupbox
        # groupboxes = self.findChildren(QGroupBox)
        # if groupboxes is not None and len(groupboxes) > 0:
        #     for groupbox in groupboxes:
        #         groupbox:QGroupBox
        #         groupbox.resize(new_size.width(), new_size.height())
        #         groupbox.updateGeometry()
        # 更新tableWidget
        # tableWidgets = self.findChildren(QTableWidget)
        # if tableWidgets is not None and len(tableWidgets) > 0:
        #     for tableWidget in tableWidgets:
        #         tableWidget:QTableWidget
        #         tableWidget.resize(new_size.width(), new_size.height())
        #         tableWidget.updateGeometry()
        # 设置最小size 以免变形
        self.setMinimumSize(self.calculate_minimum_suggested_size())

        super().resizeEvent(a0)

    def calculate_minimum_suggested_size(self):
        # 限制最小尺寸
        max_width = 0
        max_height = 0
        # 使用 findChildren 查找所有的布局
        layouts = self.findChildren(QVBoxLayout) + self.findChildren(QHBoxLayout)+self.findChildren(QGridLayout)+self.findChildren(QFormLayout)
        for layout in layouts:
            if layout is not None:
                if layout.parent() !=self.centralWidget():
                    size = layout.sizeHint()
                    max_width = max(max_width, size.width())
                    max_height = max(max_height, size.height())
        return QSize(max_width+10, max_height+10)
    def __init__(self):
        super().__init__(flags=Qt.WindowType.Window)
        self.main_gui:BaseWindow=None

    @abc.abstractmethod
    def _init_ui(self):
        # 实例化ui
        pass

    @abc.abstractmethod
    def _init_customize_ui(self):
        # 实例化自定义ui
        pass

    @abc.abstractmethod
    def _init_function(self):
        # 实例化功能
        pass

    @abc.abstractmethod
    def _init_style_sheet(self):
        # 加载qss样式表
        pass

    @abc.abstractmethod
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
    # 设置主窗口变量
    def set_main_gui(self,main_gui):
        self.main_gui = main_gui
