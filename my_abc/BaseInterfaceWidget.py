from abc import ABC, abstractmethod
from enum import Enum

from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow

class BaseInterfaceType(Enum):
    WINDOW=0
    FRAME=1
    WIDGET = 1
class Frame_state(Enum):
    Default = 0
    Opening = 1
    Closed = 2

class BaseInterfaceWidget(ABC):

    def __init__(self):
        self.type =None
        # 中间窗口
        self.frame_obj:BaseWindow =None
        # 窗口状态
        self.frame_obj_state=Frame_state.Default
        #  左侧窗口
        self.left_frame_obj:  BaseWindow = None
        self.left_frame_obj_state=Frame_state.Default
        #  右侧窗口
        self.right_frame_obj: BaseWindow = None
        self.right_frame_obj_state=Frame_state.Default
        #  bottom窗口
        self.bottom_frame_obj: BaseWindow = None
        self.bottom_frame_obj_state=Frame_state.Default
    @abstractmethod
    def get_type(self)->int:
        """获得类型BaseInterfaceType"""
        pass

    @abstractmethod
    def create_middle_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件middle WINDOW"""
        pass

    @abstractmethod
    def create_left_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件left WINDOW"""
        pass
    @abstractmethod
    def create_right_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件right WINDOW"""
        pass

    @abstractmethod
    def create_bottom_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件bottom WINDOW"""
        pass

    def close(self):
        """关闭所有窗口 若有"""
        if self.frame_obj is not None:
            self.frame_obj.close()
        if self.left_frame_obj is not None:
            self.left_frame_obj.close()
        if self.right_frame_obj is not None:
            self.right_frame_obj.close()
        if self.bottom_frame_obj is not None:
            self.bottom_frame_obj.close()
    def show(self):
        """显示页面"""
        if self.frame_obj is not None:
            self.frame_obj.show_frame()
        if self.left_frame_obj is not None:
            self.left_frame_obj.show_frame()
        if self.right_frame_obj is not None:
            self.right_frame_obj.show_frame()
        if self.bottom_frame_obj is not None:
            self.bottom_frame_obj.show_frame()
    def hide(self):
        """隐藏页面"""
        if self.frame_obj is not None:
            self.frame_obj.hide()
        if self.left_frame_obj is not None:
            self.left_frame_obj.hide()
        if self.right_frame_obj is not None:
            self.right_frame_obj.hide()
        if self.bottom_frame_obj is not None:
            self.bottom_frame_obj.hide()
    def setParent(self, parent):
        """设置父界面"""
        if self.frame_obj is not None:
            self.frame_obj.setParent(parent)
        if self.left_frame_obj is not None:
            self.left_frame_obj.setParent(parent)
        if self.right_frame_obj is not None:
            self.right_frame_obj.setParent(parent)
        if self.bottom_frame_obj is not None:
            self.bottom_frame_obj.setParent(parent)
