import threading

from PyQt6.QtCore import QThread, QMutex, QWaitCondition
from loguru import logger


class MyQThread(QThread):

    def __init__(self, name):
        super().__init__()
        super().setObjectName(name)
        if name is None:
            self.name =""
        else:
            self.name = name
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self._running = False
        self._paused = False
    def isStart(self):
        return self._running
    def isPaused(self):
        return self._paused and self._running
    def run(self):
        logger.warning(f"{self.name} thread {threading.get_ident()} has been started！")
        self._running = True
        self.before_Runing_work()
        while self._running:
            self.mutex.lock()
            if self._paused:
                self.condition.wait(self.mutex)  # 等待条件变量
            self.mutex.unlock()

            # 执行一些工作（替代为你需要的任务）
            self.dosomething()
    def before_Runing_work(self):
        #执行前的一些工作
        pass
    def dosomething(self):
        # 执行一些工作（替代为你需要的任务）
        pass

    def pause(self):
        # 暂停线程
        self.mutex.lock()
        self._paused = True
        self.mutex.unlock()
        logger.warning(f"{self.name} thread {threading.get_ident()} has been paused！")

    def resume(self):
        self.mutex.lock()
        self._paused = False
        self.condition.wakeAll()  # 唤醒线程
        self.mutex.unlock()
        logger.warning(f"{self.name} thread {threading.get_ident()} has been resumed！")

    def stop(self):
        logger.warning(f"{self.name} thread {threading.get_ident()} has been stopped！")
        self.mutex.lock()
        self._running = False
        self._paused = False  # 确保在停止前取消暂停
        self.condition.wakeAll()  # 可能需要唤醒线程以便其能正常退出
        self.mutex.unlock()
        # self.terminate()

    def __del__(self):
        logger.debug(f"线程{self.name}被销毁!")
