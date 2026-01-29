import threading
import traceback

from PyQt6.QtCore import QThread, QMutex, QWaitCondition
from loguru import logger

#logger = logger.bind(category="gui_logger")
class MyQThread(QThread):
    def __init__(self, name):
        super().__init__()
        super().setObjectName(name)
        self.name = name
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self._running = False
        self._paused = False
        self._stop_requested = False  # 新增明确的停止标志

    def run(self):
        logger.warning(f"{self.name} thread {threading.get_ident()} has been started！")
        self._running = True
        self._stop_requested = False

        try:
            self.before_Runing_work()

            while not self._stop_requested and not self.isInterruptionRequested():
                # 检查是否需要暂停
                self.mutex.lock()
                while self._paused and not self._stop_requested and not self.isInterruptionRequested():
                    # 使用带超时的等待，定期检查停止状态
                    if not self.condition.wait(self.mutex, 500):  # 500ms超时
                        # 超时后重新检查状态
                        pass
                self.mutex.unlock()

                # 双重检查
                if self._stop_requested or self.isInterruptionRequested():
                    break

                # 执行工作
                if not self._paused:
                    try:
                        self.dosomething()
                    except Exception as e:
                        error_msg=[f"{self.name} dosomething error: {e}"]
                        # 1. 获取错误的类型和值
                        error_type = type(e).__name__
                        error_value = str(e)
                        error_msg.append(f"Error Type: {error_type}")
                        error_msg.append(f"Error Value: {error_value}")
                        if hasattr(e, '__traceback__') and e.__traceback__:
                            error_msg.append("Traceback:")
                            tb_lines = traceback.format_tb(e.__traceback__)
                            error_msg.extend(tb_lines)
                            error_msg.append(f"{error_type}: {error_value}")
                        else:
                            error_msg.append("No traceback available")
                        error_msg.append(f"{self.name} dosomething error: {e}")
                        logger.error("\n".join(error_msg))
                        break
                else:
                    # 如果暂停了，短暂休眠
                    self.msleep(10)

        except Exception as e:
            logger.error(f"{self.name} run() exception: {e}")
        finally:
            self._running = False
            logger.warning(f"{self.name} thread run() ended")

    def stop(self):
        logger.warning(f"{self.name} thread stop() called")
        self.mutex.lock()
        try:
            self._stop_requested = True
            self._running = False
            self._paused = False
            self.condition.wakeAll()
        finally:
            self.mutex.unlock()

    def pause(self):
        # 只有线程真正运行时才允许暂停
        if not self.isRunning():
            logger.warning(f"{self.name} thread is not running, pause ignored")
            return

        if not self._stop_requested:
            self.mutex.lock()
            self._paused = True
            self.mutex.unlock()
            logger.warning(f"{self.name} thread has been paused！")

    def resume(self):
        # 只有线程真正运行时才允许恢复
        if not self.isRunning():
            logger.warning(f"{self.name} thread is not running, resume ignored")
            return

    def deleteLater(self):
        """更安全的删除方法"""
        logger.warning(f"开始删除线程 {self.name}")

        try:
            # 1. 设置停止标志
            self.stop()

            # 2. 请求中断
            self.requestInterruption()

            # 3. 强制唤醒多次
            for _ in range(5):
                self.mutex.lock()
                self.condition.wakeAll()
                self.mutex.unlock()
                QThread.msleep(20)

            # 4. 退出事件循环
            self.quit()

            # 5. 等待线程结束
            wait_count = 0
            while self.isRunning() and wait_count < 50:  # 最多等待5秒 (50 * 100ms)
                QThread.msleep(100)
                wait_count += 1

                # 每秒再次唤醒一次
                if wait_count % 10 == 0:
                    self.mutex.lock()
                    self.condition.wakeAll()
                    self.mutex.unlock()

            if self.isRunning():
                logger.warning(f"{self.name}线程等待超时，强制终止")
                # self.terminate()
                self.wait(1000)
            else:
                logger.warning(f"{self.name}线程正常结束")

        except Exception as e:
            logger.error(f"{self.name}删除线程异常: {e}")
            try:
                # self.terminate()
                self.wait(1000)
            except Exception as e2:
                logger.error(f"{self.name}强制终止失败: {e2}")

    def isStart(self):
        return self._running and not self._stop_requested

    def isPaused(self):
        return self._paused and self._running and not self._stop_requested

    def move_work_to_thread(self, work):
        self.dosomething = work

    def before_Runing_work(self):
        pass

    def dosomething(self):
        pass

    def __del__(self):
        logger.debug(f"线程{self.name}被销毁!")
class MyThread(threading.Thread):

    def __init__(self, name):
        super().__init__()
        self.name = name
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self._running = False
        self._paused = False

    def isRunning(self):  # 添加的函数，与QThread保持一致
        """检查线程是否正在运行"""
        return self._running and self.is_alive()
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
    def move_work_to_thread(self,work):
        self.dosomething=work
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
