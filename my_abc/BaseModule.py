# plugin_interface.py
import queue
from abc import abstractmethod, ABC

from PyQt6.QtWidgets import QVBoxLayout

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

    def set_main_gui(self,main_gui:BaseWindow=None) -> None:
        # 获取主界面变量
        self.main_gui=main_gui
        pass
    def adjustGUIPolicy(self):
        if self.interface_widget is None or self.interface_widget.type is None or self.interface_widget.frame_obj is None or self.main_gui is None:
            return
        # 根据type来确定相关策略
        if self.interface_widget.type == BaseInterfaceType.WIDGET or self.interface_widget.type == BaseInterfaceType.FRAME:
            # 如果之前有界面则移除该界面
            if self.main_gui.active_widget is not None:
                self.main_gui.active_widget.hide()
                self.main_gui.content_layout.removeWidget(self.main_gui.active_widget)
                self.main_gui.active_widget.setParent(None)
                self.main_gui.active_widget = None
            self.interface_widget.frame_obj.resize(int(self.main_gui.width() ), int(self.main_gui.height() ))
            self.main_gui.content_layout.addWidget(self.interface_widget.frame_obj)
            self.main_gui.title_label.setText(self.title)
            self.interface_widget.frame_obj.setVisible(False)
            self.interface_widget.frame_obj.set_main_gui(self.main_gui)
            # 将界面放入正在显示界面
            self.main_gui.active_widget=self.interface_widget.frame_obj
            pass
        else:
            self.interface_widget.frame_obj.setWindowTitle(self.title)
            self.interface_widget.frame_obj.set_main_gui(self.main_gui)
            self.interface_widget.frame_obj.resize(int(self.main_gui.width() * 0.7), int(self.main_gui.height() * 0.7))
            # 添加窗口
            if self.interface_widget.frame_obj not in self.main_gui.open_windows:
                self.main_gui.open_windows.append(self.interface_widget.frame_obj)
            pass
        pass