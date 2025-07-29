from abc import ABC, abstractmethod

from public.entity.BaseWidget import BaseWidget
from public.entity.BaseWindow import BaseWindow


class BaseInterfaceWidget(ABC):
    @abstractmethod
    def get_type(self)->int:
        """获得类型 0是BaseWindow 1是BaseWidget"""
        pass
    @abstractmethod
    def create_widget(self) -> BaseWidget:
        """创建并返回自定义的界面部件WIDGET"""
        pass
    @abstractmethod
    def create_window(self) -> BaseWindow:
        """创建并返回自定义的界面部件WINDOW"""
        pass
