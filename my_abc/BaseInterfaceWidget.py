from abc import ABC, abstractmethod
from enum import Enum

from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow

class BaseInterfaceType(Enum):
    WINDOW=0
    FRAME=1
    WIDGET = 1
class BaseInterfaceWidget(ABC):

    def __init__(self):
        self.type =None
        # 中间窗口
        self.frame_obj:BaseWidget|BaseWindow =None
        #  左侧窗口
        self.left_frame_obj: BaseWidget | BaseWindow = None
        #  右侧窗口
        self.right_frame_obj: BaseWidget | BaseWindow = None
        #  bottom窗口
        self.bottom_frame_obj: BaseWidget | BaseWindow = None
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