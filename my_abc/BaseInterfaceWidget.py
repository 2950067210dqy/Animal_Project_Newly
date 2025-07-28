from abc import ABC, abstractmethod

from PyQt6.QtWidgets import QWidget, QMainWindow


class BaseInterfaceBuilder(ABC):
    @abstractmethod
    def create_widget(self) -> QWidget:
        """创建并返回自定义的界面部件WIDGET"""
        pass

    @abstractmethod
    def create_window(self) -> QMainWindow:
        """创建并返回自定义的界面部件WINDOW"""
        pass