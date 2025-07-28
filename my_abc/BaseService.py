from abc import ABC, abstractmethod


class BaseService(ABC):
    @abstractmethod
    def start(self):
        """启动服务"""
        pass

    @abstractmethod
    def stop(self):
        """停止服务"""
        pass