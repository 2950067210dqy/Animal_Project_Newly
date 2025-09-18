"""
PeriodicTimer 可复用类（可注入任务）- 支持多进程版本
- interval_ms: 间隔（毫秒）
- max_duration_ms: 最大运行时长（毫秒），None 表示无限制
- task: 每次触发时要执行的可调用对象，可以接收 0 或 1 个参数(elapsed_ms)
- run_in_thread: 若 True，则把 task 提交到 ThreadPoolExecutor 执行（避免阻塞主逻辑）
- task_done_callback: 当任务完成时的回调，签名为 callback(result, elapsed_ms)
- run_immediately: start 时是否立即执行一次 task
"""

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional, Callable, Any
from loguru import logger


class PeriodicTimer:
    """
    支持多进程的周期性定时器类
    """

    def __init__(
        self,
        interval_ms: int,
        max_duration_ms: Optional[int] = None,
        task: Optional[Callable[..., Any]] = None,
        run_in_thread: bool = False,
        task_done_callback: Optional[Callable[[Any, int], None]] = None,
        run_immediately: bool = False,
        max_workers: int =None
    ):
        self.interval_ms = int(interval_ms)
        self.max_duration_ms = None if max_duration_ms is None else int(max_duration_ms)
        self._task = task
        self.run_in_thread = bool(run_in_thread)
        self._task_done_callback = task_done_callback
        self.run_immediately = bool(run_immediately)

        # 线程控制
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始为非暂停状态

        # 时间记录
        self._start_time = 0
        self._paused_duration = 0
        self._pause_start_time = 0

        # 线程池（如果需要）
        self._executor: Optional[ThreadPoolExecutor] = None
        if self.run_in_thread:
            self._executor = ThreadPoolExecutor(max_workers=max_workers)

        # 回调列表（支持多个监听器）
        self._finished_callbacks = []
        self._task_finished_callbacks = []

        # 锁保护状态
        self._lock = threading.Lock()

    def add_finished_callback(self, callback: Callable[[int], None]):
        """添加定时器结束回调"""
        self._finished_callbacks.append(callback)

    def add_task_finished_callback(self, callback: Callable[[Any, int], None]):
        """添加任务完成回调"""
        self._task_finished_callbacks.append(callback)

    def set_task(self, task: Callable[..., Any]):
        """设置/替换任务函数"""
        with self._lock:
            self._task = task

    def start(self):
        """启动定时器"""
        if self._timer_thread and self._timer_thread.is_alive():
            logger.warning("Timer is already running")
            return

        # 重置状态
        self._stop_event.clear()
        self._pause_event.set()
        self._start_time = time.time()
        self._paused_duration = 0

        # 启动定时器线程
        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

        logger.info(f"PeriodicTimer started with interval {self.interval_ms}ms")

    def stop(self):
        """停止定时器"""
        if not self._timer_thread or not self._timer_thread.is_alive():
            return

        # 设置停止标志
        self._stop_event.set()
        self._pause_event.set()  # 确保不会卡在暂停状态

        # 等待线程结束
        if self._timer_thread:
            self._timer_thread.join(timeout=1.0)

        # 关闭线程池
        if self._executor:
            self._executor.shutdown(wait=False)

        # 触发结束回调
        elapsed = self.get_elapsed_ms()
        self._trigger_finished_callbacks(elapsed)

        logger.info(f"PeriodicTimer stopped after {elapsed}ms")

    def pause(self):
        """暂停定时器"""
        if not self._timer_thread or not self._timer_thread.is_alive():
            return

        with self._lock:
            if not self._pause_event.is_set():
                return  # 已经暂停

            self._pause_start_time = time.time()
            self._pause_event.clear()

        logger.info("PeriodicTimer paused")

    def resume(self):
        """恢复定时器"""
        if not self._timer_thread or not self._timer_thread.is_alive():
            return

        with self._lock:
            if self._pause_event.is_set():
                return  # 没有暂停

            # 累计暂停时间
            self._paused_duration += time.time() - self._pause_start_time
            self._pause_event.set()

        logger.info("PeriodicTimer resumed")

    def is_active(self) -> bool:
        """检查定时器是否活跃"""
        return (self._timer_thread and
                self._timer_thread.is_alive() and
                not self._stop_event.is_set() and
                self._pause_event.is_set())

    def is_paused(self) -> bool:
        """检查是否暂停"""
        return (self._timer_thread and
                self._timer_thread.is_alive() and
                not self._stop_event.is_set() and
                not self._pause_event.is_set())

    def get_elapsed_ms(self) -> int:
        """获取已运行时间（毫秒）"""
        if not self._start_time:
            return 0

        current_time = time.time()
        total_elapsed = current_time - self._start_time

        # 减去暂停时间
        paused_time = self._paused_duration
        if not self._pause_event.is_set() and self._pause_start_time:
            paused_time += current_time - self._pause_start_time

        elapsed = total_elapsed - paused_time
        return int(elapsed * 1000)

    def _timer_loop(self):
        """定时器主循环"""
        try:
            # 立即执行（如果需要）
            if self.run_immediately:
                self._execute_task()

            while not self._stop_event.is_set():
                # 等待间隔时间或停止信号
                if self._stop_event.wait(timeout=self.interval_ms / 1000.0):
                    break  # 收到停止信号

                # 等待恢复（如果暂停）
                self._pause_event.wait()

                # 再次检查停止信号
                if self._stop_event.is_set():
                    break

                # 执行任务
                self._execute_task()

                # 检查最大运行时间
                if self.max_duration_ms is not None:
                    elapsed = self.get_elapsed_ms()
                    if elapsed >= self.max_duration_ms:
                        logger.info(f"Max duration {self.max_duration_ms}ms reached")
                        break

        except Exception as e:
            logger.error(f"Timer loop error: {e}")
            traceback.print_exc()
        finally:
            # 确保线程池关闭
            if self._executor:
                self._executor.shutdown(wait=True)

    def _execute_task(self):
        """执行用户任务"""
        if not self._task:
            return

        elapsed = self.get_elapsed_ms()

        if self.run_in_thread and self._executor:
            # 在线程池中执行
            future = self._executor.submit(self._run_task_safe, elapsed)
            future.add_done_callback(lambda f: self._handle_task_result(f, elapsed))
        else:
            # 在当前线程执行
            result = self._run_task_safe(elapsed)
            self._trigger_task_finished_callbacks(result, elapsed)

    def _run_task_safe(self, elapsed_ms: int) -> Any:
        """安全执行用户任务"""
        try:
            # 尝试传递elapsed_ms参数
            try:
                return self._task(elapsed_ms)
            except TypeError:
                # 如果函数不接受参数，则不传递
                return self._task()
        except Exception as e:
            logger.error(f"Task execution error: {e}")
            traceback.print_exc()
            return None

    def _handle_task_result(self, future: Future, elapsed_ms: int):
        """处理线程池任务结果"""
        try:
            result = future.result()
        except Exception as e:
            logger.error(f"Task future error: {e}")
            result = None

        self._trigger_task_finished_callbacks(result, elapsed_ms)

    def _trigger_finished_callbacks(self, elapsed_ms: int):
        """触发定时器结束回调"""
        for callback in self._finished_callbacks:
            try:
                callback(elapsed_ms)
            except Exception as e:
                logger.error(f"Finished callback error: {e}")
                traceback.print_exc()

        # 也触发原来的task_done_callback
        if self._task_done_callback:
            try:
                self._task_done_callback(None, elapsed_ms)
            except Exception as e:
                logger.error(f"Task done callback error: {e}")
                traceback.print_exc()

    def _trigger_task_finished_callbacks(self, result: Any, elapsed_ms: int):
        """触发任务完成回调"""
        for callback in self._task_finished_callbacks:
            try:
                callback(result, elapsed_ms)
            except Exception as e:
                logger.error(f"Task finished callback error: {e}")
                traceback.print_exc()

        # 也触发原来的task_done_callback
        if self._task_done_callback:
            try:
                self._task_done_callback(result, elapsed_ms)
            except Exception as e:
                logger.error(f"Task done callback error: {e}")
                traceback.print_exc()

    def __del__(self):
        """析构函数，确保资源清理"""
        try:
            self.stop()
        except:
            pass


# 用法示例和测试代码
if __name__ == "__main__":
    import multiprocessing
    from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget
    from PyQt6.QtCore import QTimer as QtTimer

    def test_task(elapsed_ms=0):
        """测试任务函数"""
        import random
        data = random.randint(1, 100)
        print(f"Task executed at {elapsed_ms}ms, generated data: {data}")
        time.sleep(0.1)  # 模拟一些处理时间
        return data

    def task_done_callback(result, elapsed_ms):
        """任务完成回调"""
        print(f"Task completed: result={result}, elapsed={elapsed_ms}ms")

    def finished_callback(elapsed_ms):
        """定时器结束回调"""
        print(f"Timer finished after {elapsed_ms}ms")

    def subprocess_worker():
        """子进程工作函数"""
        print("子进程启动")

        # 在子进程中创建和使用定时器
        timer = PeriodicTimer(
            interval_ms=500,
            max_duration_ms=5000,
            task=test_task,
            run_in_thread=True,
            task_done_callback=task_done_callback,
            run_immediately=True
        )

        timer.add_finished_callback(finished_callback)
        timer.start()

        # 模拟一些其他工作
        time.sleep(2)
        print("子进程暂停定时器")
        timer.pause()

        time.sleep(1)
        print("子进程恢复定时器")
        timer.resume()

        # 等待定时器结束
        while timer.is_active() or timer.is_paused():
            time.sleep(0.1)

        print("子进程结束")

    class MainWindow(QMainWindow):
        """主窗口类，演示在GUI中使用定时器"""
        def __init__(self):
            super().__init__()
            self.timer = None
            self.init_ui()

        def init_ui(self):
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)

            self.status_label = QLabel("定时器状态: 未启动")
            self.elapsed_label = QLabel("运行时间: 0ms")
            self.result_label = QLabel("最新结果: 无")

            self.start_button = QPushButton("启动定时器")
            self.start_button.clicked.connect(self.start_timer)

            self.pause_button = QPushButton("暂停")
            self.pause_button.clicked.connect(self.pause_timer)

            self.resume_button = QPushButton("恢复")
            self.resume_button.clicked.connect(self.resume_timer)

            self.stop_button = QPushButton("停止")
            self.stop_button.clicked.connect(self.stop_timer)

            layout.addWidget(self.status_label)
            layout.addWidget(self.elapsed_label)
            layout.addWidget(self.result_label)
            layout.addWidget(self.start_button)
            layout.addWidget(self.pause_button)
            layout.addWidget(self.resume_button)
            layout.addWidget(self.stop_button)

            # GUI更新定时器
            self.gui_timer = QtTimer()
            self.gui_timer.timeout.connect(self.update_ui)
            self.gui_timer.start(100)

        def gui_task_callback(self, result, elapsed_ms):
            """GUI线程安全的任务回调"""
            self.result_label.setText(f"最新结果: {result} (at {elapsed_ms}ms)")

        def gui_finished_callback(self, elapsed_ms):
            """GUI线程安全的结束回调"""
            self.status_label.setText(f"定时器已结束，总运行时间: {elapsed_ms}ms")

        def start_timer(self):
            if self.timer and (self.timer.is_active() or self.timer.is_paused()):
                return

            self.timer = PeriodicTimer(
                interval_ms=1000,
                max_duration_ms=10000,
                task=test_task,
                run_in_thread=True,
                run_immediately=True
            )

            self.timer.add_task_finished_callback(self.gui_task_callback)
            self.timer.add_finished_callback(self.gui_finished_callback)
            self.timer.start()

        def pause_timer(self):
            if self.timer:
                self.timer.pause()

        def resume_timer(self):
            if self.timer:
                self.timer.resume()

        def stop_timer(self):
            if self.timer:
                self.timer.stop()

        def update_ui(self):
            if self.timer:
                if self.timer.is_active():
                    status = "运行中"
                elif self.timer.is_paused():
                    status = "已暂停"
                else:
                    status = "已停止"

                self.status_label.setText(f"定时器状态: {status}")
                self.elapsed_label.setText(f"运行时间: {self.timer.get_elapsed_ms()}ms")

    # 测试多进程
    print("=== 测试子进程中的定时器 ===")
    process = multiprocessing.Process(target=subprocess_worker)
    process.start()
    process.join()

    print("\n=== 测试GUI中的定时器 ===")
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()