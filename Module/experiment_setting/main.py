from PyQt6.QtWidgets import QMainWindow

from Module.experiment_setting.index.tab_7 import Tab_7
from my_abc.BaseInterfaceWidget import BaseInterfaceWidget
from my_abc.BaseModule import BaseModule
from my_abc.BaseService import BaseService
from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow


class Main_experiment_setting_service(BaseService):
    # 组件服务
    def __init__(self):
        pass
    def start(self):
        pass
    def stop(self):
        pass

class Main_experiment_setting_widget(BaseInterfaceWidget):
    # 组件自定义界面
    def __init__(self):
        self.type = self.get_type()
        if self.type == 0:
            self.frame_obj = self.create_window()
        else:
            self.frame_obj = self.create_widget()
        pass
    def get_type(self):
        """获得类型 0是BaseWindow 1是BaseWidget"""
        return 0
    def create_window(self) -> BaseWindow:
        tab_window = Tab_7()
        return tab_window
    def create_widget(self) -> BaseWidget:
        pass




class Main_experiment_setting(BaseModule):
    def __init__(self):
        self.interface_widget=self.get_interface_widget()
        self.name = self.get_name()
        self.title = self.get_title()
        self.menu_name = self.get_menu_name()
        self.service= self.create_service()

        pass
    def get_name(self):
        """返回组件名称"""
        return "Main_experiment_setting"
        pass
    def get_title(self):
        """获取组件title"""
        return "实验配置"
    def get_menu_name(self):
        """返回组件所属菜单{id:,text:} 在./config/gui_config.ini文件查看"""
        return {"id":0,"text":"文件"}
        pass

    def create_service(self) -> BaseService:
        """创建并返回组件的相关服务"""
        return Main_experiment_setting_service()
        pass

    def get_interface_widget(self) -> BaseInterfaceWidget:
        """返回自定义界面构建器"""
        widget_builder =Main_experiment_setting_widget()
        widget_builder.module = self  # 可以通过引用将组件功能传递给界面构建器
        return widget_builder
        pass