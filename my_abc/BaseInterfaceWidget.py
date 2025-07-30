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
        self.frame_obj:BaseWidget|BaseWindow =None

    @abstractmethod
    def get_type(self)->int:
        """获得类型BaseInterfaceType"""
        pass

    @abstractmethod
    def create_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件WINDOW"""
        pass
