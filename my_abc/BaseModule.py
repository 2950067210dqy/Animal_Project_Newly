# plugin_interface.py
from abc import abstractmethod, ABC

from my_abc import BaseInterfaceWidget
from my_abc.BaseService import BaseService


class BaseModule(ABC):
    @abstractmethod
    def get_name(self):
        """返回插件名称"""
        pass

    @abstractmethod
    def create_service(self) -> BaseService:
        """创建并返回插件的相关服务"""
        pass

    @abstractmethod
    def get_interface_widget(self) -> BaseInterfaceWidget:
        """返回自定义界面构建器"""
        pass