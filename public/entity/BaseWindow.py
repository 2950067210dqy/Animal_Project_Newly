import abc
import sys
import typing

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import QRect, Qt, QSize, QPoint, QEvent, QTimer, QObject
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLayout, \
    QScrollArea, QSizePolicy, QMessageBox, QTabWidget, QGroupBox, QTableWidget, QToolBar, QApplication, QDockWidget
from loguru import logger

from public.component.Window_Title_Bar import TitleBar
from public.component.custom_status_bar import CustomStatusBar
from public.config_class import App_Setting
from public.config_class.global_setting import global_setting
from public.entity.enum.Public_Enum import Frame_state
from wrapper.After_execution import after_execution


#logger = logger.bind(category="gui_logger")
class BaseWindow(QMainWindow):
    def changeEvent(self, event):
        # 监听状态变化事件
        if event.type() == QEvent.Type.WindowStateChange:
            if event.oldState() & Qt.WindowState.WindowMinimized:
                #窗口被最小化
                # print("最小化")
                event.ignore()
            elif event.oldState() & Qt.WindowState.WindowNoState:
                #窗口恢复到正常状态
                pass
            elif event.oldState() & Qt.WindowState.WindowMaximized:
                # 窗口被最大化
                pass

        # 一定要调用父类的 changeEvent 方法
        super().changeEvent(event)
    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        pass
    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        # 主界面的当前页面为None

        if self.main_gui is not None:
            index = 0
            while index < len(self.main_gui.active_module_widgets) :
                if index>=len(self.main_gui.active_module_widgets):
                    index=0
                # 更改每个module的每个窗口状态，当一个module的所有窗口的状态都为closed时就从openwindos移除掉这个module
                if self.main_gui.active_module_widgets[index].interface_widget.frame_obj is self:
                    self.main_gui.active_module_widgets[index].interface_widget.frame_obj_state = Frame_state.Closed
                if self.main_gui.active_module_widgets[index].interface_widget.left_frame_obj is self:
                    self.main_gui.active_module_widgets[index].interface_widget.left_frame_obj_state = Frame_state.Closed
                if self.main_gui.active_module_widgets[index].interface_widget.right_frame_obj is self:
                    self.main_gui.active_module_widgets[index].interface_widget.right_frame_obj_state = Frame_state.Closed
                if self.main_gui.active_module_widgets[index].interface_widget.bottom_frame_obj is self:
                    self.main_gui.active_module_widgets[index].interface_widget.bottom_frame_obj_state = Frame_state.Closed
                # 如果全部关闭则移除该module
                if self.main_gui.active_module_widgets[index].interface_widget.is_all_closed():
                    del self.main_gui.active_module_widgets[index]
                index += 1
    def closeEvent(self, event):
        # 关闭事件
        if self.main_gui is not None:


            index = 0
            while index<len(self.main_gui.open_windows) :
                if index>=len(self.main_gui.open_windows):
                    index=0
                # 更改每个module的每个窗口状态，当一个module的所有窗口的状态都为closed时就从openwindos移除掉这个module
                if self.main_gui.open_windows[index].interface_widget.frame_obj is self:
                    self.main_gui.open_windows[index].interface_widget.frame_obj_state = Frame_state.Closed
                if self.main_gui.open_windows[index].interface_widget.left_frame_obj is self:
                    self.main_gui.open_windows[index].interface_widget.left_frame_obj_state = Frame_state.Closed
                if self.main_gui.open_windows[index].interface_widget.right_frame_obj is self:
                    self.main_gui.open_windows[index].interface_widget.right_frame_obj_state = Frame_state.Closed
                if self.main_gui.open_windows[index].interface_widget.bottom_frame_obj is self:
                    self.main_gui.open_windows[index].interface_widget.bottom_frame_obj_state = Frame_state.Closed
                # 如果全部关闭则移除该module
                if self.main_gui.open_windows[index].interface_widget.is_all_closed():
                    del self.main_gui.open_windows[index]
                index+=1



    def resizeEvent(self, a0 :typing.Optional[QtGui.QResizeEvent]):
        # 获取新的大小
        new_size:QSize = a0.size()

        old_size:QSize = a0.oldSize()
        # logger.error(f"resizeEvent:{new_size}|{old_size}")

        if self.centralWidget() is not None:
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
        # self.setMinimumSize(self.calculate_minimum_suggested_size())

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

    # def mousePressEvent(self, event):
    #     """处理鼠标按下事件"""
    #     if event.button() == Qt.MouseButton.LeftButton:
    #         self.is_pressed = True
    #         self.start_pos = event.pos()
    #
    # def mouseMoveEvent(self, event):
    #     """处理鼠标移动事件"""
    #     if self.is_pressed:
    #         # 移动窗口
    #         self.move(self.pos() + event.pos() - self.start_pos)
    #
    # def mouseReleaseEvent(self, event):
    #     """处理鼠标释放事件"""
    #     if event.button() == Qt.MouseButton.LeftButton:
    #         if self.is_pressed:
    #             self.is_pressed = False

    def __init__(self):
        super().__init__()  # 隐藏系统标题栏
        # 主窗口 特指代MainWindow_index
        self.main_gui:BaseWindow=None
        # 状态栏
        self.status_bar=None
        # 设置窗口标志，
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        # 创建文件菜单


        # 用于记录鼠标状态
        self.is_pressed = False
        self.start_pos = QPoint()

        # 先初始化tutorial 提示指示器为None
        self.tutorial = None
        """
        如果需要添加页面指示帮助的话 请在子类的初始化函数末尾添加两句代码，
        # 实例化提示器
        self.setup_tutorial()
        # 自动启动提示教程 如果有提示页面的话
        QTimer.singleShot(400, self.start_tutorial_if_exists)
        """
    # 开始提示引导
    def start_tutorial_if_exists(self):
        if self.tutorial:
            settings:App_Setting = self.tutorial.settings_manager
            if settings and settings.is_first_visit(page_name=self.tutorial.page_name):
                self.tutorial.start_tutorial()
            else:
                widgets = self.findChildren(QObject, "temp_deleted_widget")
                for widget in widgets:
                    widget.hide()

    def setup_tutorial(self):
        #实例化提示引导器 下面式实例化模板
        # if self.tutorial:
        #     self.tutorial.end_tutorial()
        #
        # self.tutorial = TutorialManager(self, "main_page", Tutorial_Type.ARROW_GUIDE,global_setting.get_setting("app_setting", AppSettings()))
        #
        # # 连接教程完成信号
        # self.tutorial.tutorial_completed.connect(self.on_tutorial_completed)
        #
        # # 添加更详细的引导步骤
        # save_widgets = self.save_action.associatedObjects()
        # if save_widgets:
        #     self.tutorial.add_step(save_widgets[0],
        #                            "欢迎使用本应用！\n这是保存功能，可以保存您的工作进度和项目文件。\n建议定期保存以防数据丢失。")
        #
        # self.tutorial.add_step(self.start_btn,
        #                        "开始您的创作之旅\n点击此按钮可以启动新项目。\n系统会为您创建一个全新的工作环境。")
        #
        # self.tutorial.add_step(self.project_list,
        #                        "项目管理中心\n这里显示您的所有项目。\n您可以选择现有项目进行编辑，或查看项目详情。\n支持多项目并行开发。")
        #
        # self.tutorial.add_step(self.export_btn,
        #                        "数据导出功能\n使用此功能可以将项目数据导出为多种格式。\n支持 JSON、CSV、XML 等格式。")
        #
        # self.tutorial.add_step(self.text_editor,
        #                        "主编辑区域\n这是您的创作空间。\n支持富文本编辑、语法高亮、自动补全等功能。\n您可以在这里编写文档、代码或其他内容。")
        #
        # self.tutorial.add_step(self.restart_tutorial_btn,
        #                        "🎉 恭喜！教程完成！\n您已经了解了应用的主要功能。\n随时可以点击此按钮重新查看教程。\n\n开始您的创作之旅吧！")

        pass

    def on_tutorial_completed(self,page_name):
        """教程完成处理"""
        self.status_bar.update_tip(f"🎉 {page_name}教程已完成！感谢您的耐心学习。")
        widgets = self.findChildren(QObject, "temp_deleted_widget")
        for widget in widgets:
            widget.hide()
    def delete_widgets_by_name(self, object_name):
        """删除所有同名控件"""
        widgets = self.findChildren(QObject, object_name)

        for widget in widgets:
            try:
                # 从父控件中移除

                widget.setParent(None)

                # 释放资源
                widget.deleteLater()
                widget=None
            except Exception as e:
                logger.error(f"删除控件 {widget} 时出错: {e}")
    def restart_tutorial(self):
        """重新开始教程"""
        if self.tutorial:
            self.tutorial.clear()
            self.setup_tutorial()
            self.tutorial.start_tutorial()
        else:
            reply = QMessageBox.question(
                self,
                "注意",
                "当前页面暂无教程",
                QMessageBox.StandardButton.No
            )

    def reset_first_run_status(self):
        """重置首次运行状态（仅用于测试）"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "这将重置所有页面的首次访问状态，下次进入各个页面时会再次显示引导教程。\n\n确定要继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 重置程序首次运行状态
            self.settings.settings["first_run"] = True
            self.settings.settings["tutorial_completed"] = False

            # 获取所有以 "first_visit_" 开头的设置项并重置为 True
            keys_to_reset = []
            for key in self.settings.settings.keys():
                if key.startswith("first_visit_"):
                    keys_to_reset.append(key)

            # 重置所有页面的首次访问状态
            for key in keys_to_reset:
                self.settings.settings[key] = True

            # 也可以直接重置特定页面（如果已知页面名称）
            page_names = ["main_page", "project_page", "settings_page", "help_page"]  # 可根据实际页面名称调整
            for page_name in page_names:
                self.settings.settings[f"first_visit_{page_name}"] = True

            self.settings.save_settings()

            # 显示重置的页面信息
            reset_pages = [key.replace("first_visit_", "") for key in keys_to_reset]
            if reset_pages:
                pages_info = "、".join(reset_pages)
                message = f"所有状态已重置。\n\n已重置的页面: {pages_info}\n\n重新进入这些页面时将显示引导教程。"
            else:
                message = "首次运行状态已重置。\n重新启动程序或进入页面时将显示引导教程。"

            QMessageBox.information(
                self,
                "重置完成",
                message
            )

            self.statusBar().showMessage("✅ 所有页面的首次访问状态已重置", 3000)
    def insert_status_bar_button(self,self2):
        """
        对状态栏进行插入自定义按钮操作
        :return:
        """
        # 状态栏
        if self.status_bar is None:
            self.status_bar = CustomStatusBar(self,is_main=False)
            self.setStatusBar(self.status_bar)

            pass
        else:

            pass

    @abc.abstractmethod
    def _init_ui(self):
        # 实例化ui
        pass

    @after_execution(insert_status_bar_button)
    @abc.abstractmethod
    def _init_customize_ui(self):

        # 实例化自定义ui
        """
        ！！！！！！！！！！在子类的该函数末尾调用父类该函数 super()._init_customize_ui(),否则装饰器不会起作用
        :return:
        """
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


    # 为layout添加scroll_area 返回待scroll_area的layout
    @classmethod
    def add_scroll_area_if_not_exists(cls,layout):
        """
        检查指定的布局是否已经包含QScrollArea，如果没有则添加一个QScrollArea。

        :param layout: QVBoxLayout 要检索和添加滚动区域的布局
        :return: 返回滚动区域的内容布局以便添加小部件
        """
        if layout is None:
            return None
        for i in range(layout.count()):
            item_widget = layout.itemAt(i).widget()
            if isinstance(item_widget, QScrollArea):
                print("QScrollArea already exists. Not adding again.")
                return None  # 如果已经存在，返回 None

        # 创建 QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # 创建一个新的 QWidget 作为滚动区域的内容
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)

        # 将内容设置为滚动区域的内容
        scroll_area.setWidget(scroll_content)

        # 将 QScrollArea 添加到布局中
        layout.addWidget(scroll_area)

        return scroll_content_layout  # 返回内容布局

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

    def delete_central_widget(self):
        # 删除当前的 centralWidget
        widget = self.centralWidget()  # 获取当前的 centralWidget
        if widget:
            widget.setParent(None)  # 移除并删除 (也可以使用 deleteLater())
            self.setCentralWidget(None)  # 设置 centralWidget 为 None
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
