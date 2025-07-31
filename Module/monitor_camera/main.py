from PyQt6.QtWidgets import QMainWindow

from Module.monitor_camera.index.tab_4 import Tab_4
from Module.monitor_data.index.tab_2 import Tab_2
from my_abc.BaseInterfaceWidget import BaseInterfaceWidget, BaseInterfaceType
from my_abc.BaseModule import BaseModule
from my_abc.BaseService import BaseService
from public.entity.BaseWindow import BaseWindow


class Main_Monitor_camera_service(BaseService):
    # 组件服务
    def __init__(self):
        pass
    def start(self):
        pass
    def stop(self):
        pass

class Main_Monitor_camera_widget(BaseInterfaceWidget):
    # 组件自定义界面
    def __init__(self):
        super().__init__()
        self.type = self.get_type()
        self.frame_obj = self.create_window()


    def get_type(self):
        """获得类型 """
        return BaseInterfaceType.WIDGET
    def create_window(self) -> BaseWindow:
        tab_window = Tab_4()
        return tab_window




class Main_Monitor_camera_Module(BaseModule):
    def __init__(self):
        super().__init__()
        self.interface_widget=self.get_interface_widget()
        self.name = self.get_name()
        self.title = self.get_title()
        self.menu_name = self.get_menu_name()
        self.service= self.create_service()

        pass
    def get_name(self):
        """返回组件名称"""
        return "Main_Monitor_camera"
        pass
    def get_title(self):
        """获取组件title"""
        return "相机监控"
    def get_menu_name(self):
        """返回组件所属菜单{id:,text:} 在./config/gui_config.ini文件查看"""
        return {"id":1,"text":"实验"}
        pass

    def create_service(self) -> BaseService:
        """创建并返回组件的相关服务"""
        return Main_Monitor_camera_service()
        pass

    def get_interface_widget(self) -> BaseInterfaceWidget:
        """返回自定义界面构建器"""
        widget_builder =Main_Monitor_camera_widget()
        widget_builder.module = self  # 可以通过引用将组件功能传递给界面构建器
        return widget_builder
        pass

