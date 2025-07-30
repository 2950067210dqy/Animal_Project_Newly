from abc import ABC, abstractmethod

from my_abc.BaseInterfaceWidget import BaseInterfaceType


class BaseService(ABC):

    def __init__(self):
        pass
    @abstractmethod
    def start(self):
        """启动服务"""
        pass

    @abstractmethod
    def stop(self):
        """停止服务"""
        pass

