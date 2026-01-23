# Module/new_experiment_setting/index/main.py
from PyQt6.QtWidgets import QMainWindow

from Module.new_experiment_setting.index.Tab_1 import Tab_1
from my_abc.BaseInterfaceWidget import BaseInterfaceWidget
from my_abc.BaseModule import BaseModule
from my_abc.BaseService import BaseService
from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow
from public.entity.enum.Public_Enum import BaseInterfaceType, AppState


class Main_experiment_setting_service(BaseService):
    def __init__(self):
        pass

    def start(self, resolve, reject):
        resolve()

    def stop(self):
        pass


class Main_experiment_setting_widget(BaseInterfaceWidget):
    def __init__(self):
        super().__init__()
        self.type = self.get_type()
        self.frame_obj = self.create_middle_window()
        self.left_frame_obj = None
        self.right_frame_obj = None
        self.bottom_frame_obj = None

    def get_type(self):
        return BaseInterfaceType.WINDOW

    def create_middle_window(self) -> BaseWindow:
        return Tab_1()

    def create_left_window(self) -> BaseWindow:
        return None

    def create_right_window(self) -> BaseWindow:
        return None

    def create_bottom_window(self) -> BaseWindow:
        return None


class Main_experiment_setting(BaseModule):
    def __init__(self):
        super().__init__()
        self.interface_widget = self.get_interface_widget()
        self.name = self.get_name()
        self.title = self.get_title()
        self.menu_name = self.get_menu_name()
        self.service = self.create_service()
        self.app_state = self.get_app_state()

    def get_app_state(self) -> AppState:
        return AppState.APPLYING

    def get_name(self):
        return "New_main_New_Monitor_data"

    def get_title(self):
        return "串口配置"

    def get_menu_name(self):
        return {"id": 1, "text": "设备信息"}

    def create_service(self) -> BaseService:
        return Main_experiment_setting_service()

    def get_interface_widget(self) -> BaseInterfaceWidget:
        widget_builder = Main_experiment_setting_widget()
        widget_builder.module = self
        return widget_builder