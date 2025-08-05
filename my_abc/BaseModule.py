# plugin_interface.py
import queue
from abc import abstractmethod, ABC

from PyQt6.QtWidgets import QVBoxLayout, QWidget, QScrollArea

from index.Content_index import content_index
from my_abc import BaseInterfaceWidget
from my_abc.BaseInterfaceWidget import BaseInterfaceType
from my_abc.BaseService import BaseService
from public.entity.BaseWindow import BaseWindow


class BaseModule(ABC):

    def __init__(self):
        self.interface_widget:BaseInterfaceWidget =None
        self.name =None
        self.title=None
        self.menu_name=None
        self.service:BaseService =None
        self.main_gui:BaseWindow =None
        pass

    @abstractmethod
    def get_menu_name(self):
        """返回组件所属菜单{id:,text:} 在./config/gui_config.ini文件查看"""
        pass
    @abstractmethod
    def get_name(self):
        """返回组件名称"""
        pass
    @abstractmethod
    def get_title(self):
        """获取组件title"""
        pass
    @abstractmethod
    def create_service(self) -> BaseService:
        """创建并返回组件的相关服务"""
        pass

    @abstractmethod
    def get_interface_widget(self) -> BaseInterfaceWidget:
        """返回自定义界面构建器"""
        pass
    def close(self):
        """关闭所有窗口 若有"""
        if self.interface_widget is not None:
            self.interface_widget.close()
    def show(self):
        """显示页面"""
        if self.interface_widget is not None:
            self.interface_widget.show()
    def hide(self):
        """隐藏页面"""
        if self.interface_widget is not None:
            self.interface_widget.hide()
    def setParent(self, parent):
        """设置父界面"""
        if self.interface_widget is not None:
            self.interface_widget.setParent(parent)
    def set_main_gui(self,main_gui:BaseWindow=None) -> None:
        # 获取主界面变量
        self.main_gui=main_gui
        pass
    def adjustGUIPolicy(self):
        if self.interface_widget is None or self.interface_widget.type is None or self.interface_widget.frame_obj is None or self.main_gui is None:
            return
        # 设置父界面给所有子界面
        if self.interface_widget.frame_obj is not None:
            self.interface_widget.frame_obj.set_main_gui(self.main_gui)
        if self.interface_widget.left_frame_obj is not None:
            self.interface_widget.left_frame_obj.set_main_gui(self.main_gui)
        if self.interface_widget.right_frame_obj is not None:
            self.interface_widget.right_frame_obj.set_main_gui(self.main_gui)
        if self.interface_widget.bottom_frame_obj is not None:
            self.interface_widget.bottom_frame_obj.set_main_gui(self.main_gui)

        # 根据type来确定相关策略
        if self.interface_widget.type == BaseInterfaceType.WIDGET or self.interface_widget.type == BaseInterfaceType.FRAME:

            if self not in self.main_gui.active_module_widgets:
                tab_content = QWidget()
                tab_content.setObjectName(f"tab_content_{self.menu_name['text']}_{self.name}")
                tab_layout = QVBoxLayout(tab_content)
                tab_layout.setObjectName(f"tab_content_{self.menu_name['text']}_{self.name}_layout")
                # 创建一个 QScrollArea
                scroll_area = QScrollArea(tab_content)
                scroll_area.setObjectName(f"scroll_tab_{self.menu_name['text']}_{self.name}")
                scroll_area.setWidgetResizable(True)  # 使内容小部件可以调整大小

                # 创建一个内容小部件并填充内容

                tab_frame = content_index()
                content_layout =tab_frame.findChild(QVBoxLayout,"content_layout")
                left_layout = tab_frame.findChild(QVBoxLayout,"left_layout")
                right_layout = tab_frame.findChild(QVBoxLayout,"right_layout")
                bottom_layout = tab_frame.findChild(QVBoxLayout,"bottom_layout")
                middle_layout = tab_frame.findChild(QVBoxLayout,"middle_layout")
                content_layout.addWidget(self.interface_widget.frame_obj)
                left_layout.addWidget(self.interface_widget.left_frame_obj)
                right_layout.addWidget(self.interface_widget.right_frame_obj)
                bottom_layout.addWidget(self.interface_widget.bottom_frame_obj)
                if self.interface_widget.frame_obj is not None:
                    self.interface_widget.frame_obj.resize(int(middle_layout.geometry().width()),
                                                           int(middle_layout.geometry().height()))
                if self.interface_widget.left_frame_obj is not None:
                    self.interface_widget.left_frame_obj.resize(
                        int(left_layout.geometry().width()),
                        int(left_layout.geometry().height()))
                if self.interface_widget.right_frame_obj is not None:
                    self.interface_widget.right_frame_obj.resize(int(right_layout.geometry().width()),
                                                                 int(right_layout.geometry().height()))
                if self.interface_widget.bottom_frame_obj is not None:
                    self.interface_widget.bottom_frame_obj.resize(int(bottom_layout.geometry().width()),
                                                                  int(bottom_layout.geometry().height()))
                content_widget = QWidget()
                content_widget.setObjectName(f"scroll_tab_content_widget_{self.menu_name['text']}_{self.name}")

                content_layout = QVBoxLayout(content_widget)
                content_layout.setObjectName(f"scroll_tab_{self.menu_name['text']}_{self.name}_content_widget_layout")
                content_layout.addWidget(tab_frame)

                # 将内容小部件添加到 QScrollArea
                scroll_area.setWidget(content_widget)
                # 将 scroll_area 添加进去
                tab_layout.addWidget(scroll_area)
                tab_content.setLayout(tab_layout)
                self.main_gui.tab_widget.addTab(tab_content,self.title)

                # 将界面放入正在显示界面
                self.main_gui.active_module_widgets.append(self)
            pass
        else:
            if self not in self.main_gui.open_windows:
                flag = 10
                # ，每部分layout占多少
                h_stretch = {'left':1,'middle':3,'right':1}
                v_stretch = {'top':3,'bottom':1}
                h_all = h_stretch['left']+h_stretch['middle']+h_stretch['right']
                v_all = v_stretch['top']+v_stretch['bottom']
                h_each = self.main_gui.centralWidget().geometry().width()//h_all
                v_each = self.main_gui.centralWidget().geometry().height()//v_all
                if self.interface_widget.frame_obj is not None:
                    self.interface_widget.frame_obj.setWindowTitle(self.title+'content')
                    self.interface_widget.frame_obj.setGeometry(h_each*(h_stretch['left']-1),
                                                                self.main_gui.centralWidget().geometry().top() + self.main_gui.toolbar.geometry().height() + flag,
                                                                h_each*(h_stretch['middle']),
                                                                v_each*(v_stretch['top'])- self.main_gui.toolbar.geometry().height() - flag,)
                if self.interface_widget.left_frame_obj is not None:
                    self.interface_widget.left_frame_obj.setWindowTitle(self.title+'left')
                    self.interface_widget.left_frame_obj.setGeometry(
                        0,
                        self.main_gui.centralWidget().geometry().top() + self.main_gui.toolbar.geometry().height() + flag,
                        h_each * (h_stretch['middle']),
                        v_each * (v_stretch['top']) - self.main_gui.toolbar.geometry().height() - flag,

                    )
                if self.interface_widget.right_frame_obj is not None:
                    self.interface_widget.right_frame_obj.setWindowTitle(self.title+'right')
                    self.interface_widget.right_frame_obj.setGeometry(
                        h_each * (h_stretch['middle'] - 1),
                        self.main_gui.centralWidget().geometry().top() + self.main_gui.toolbar.geometry().height() + flag,
                        h_each * (h_stretch['middle']),
                        v_each * (v_stretch['top']) - self.main_gui.toolbar.geometry().height() - flag,
                    )
                if self.interface_widget.bottom_frame_obj is not None:
                    self.interface_widget.bottom_frame_obj.setWindowTitle(self.title+'bottom')
                    self.interface_widget.bottom_frame_obj.setGeometry(
                        0,
                        self.main_gui.centralWidget().geometry().top() + self.main_gui.toolbar.geometry().height() + flag +v_each * (v_stretch['top']-1),
                        self.main_gui.centralWidget().width(),
                        v_each * (v_stretch['bottom']) - self.main_gui.toolbar.geometry().height() - flag,

                    )


                # 添加窗口
                self.main_gui.open_windows.append(self)

            pass

        pass

