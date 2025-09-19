"""
PeriodicTimer 可复用类（可注入任务）
- interval_ms: 间隔（毫秒）
- max_duration_ms: 最大运行时长（毫秒），None 表示无限制
- task: 每次触发时要执行的可调用对象，可以接收 0 或 1 个参数(elapsed_ms)
- run_in_thread: 若 True，则把 task 提交到 QThreadPool 执行（避免阻塞 GUI）
- task_done_callback: 当任务（无论是在主线程还是在线程池中）完成时，会在主线程调用该回调，签名为 callback(result, elapsed_ms)（如果 task 返回结果则为 result，否则 None）
- run_immediately: start 时是否立即执行一次 task
"""

import sys
import traceback
from typing import Optional, Callable, Any
from PyQt6.QtCore import QObject, QTimer, QElapsedTimer, pyqtSignal, QRunnable, QThreadPool
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt6.QtCore import Qt


class _TaskRunnable(QRunnable):
    """用于在线程池中执行用户任务，并在完成后通过回调通知（在工作线程中）。"""

    def __init__(self, func: Callable[..., Any], elapsed_ms: int, done_callback: Optional[Callable[[Any, int], None]] = None):
        super().__init__()
        self.func = func
        self.elapsed_ms = elapsed_ms
        self.done_callback = done_callback
        self.setAutoDelete(True)

    def run(self):
        result = None
        try:
            try:
                result = self.func(self.elapsed_ms)
            except TypeError:
                result = self.func()
        except Exception:
            traceback.print_exc()
        # done_callback 期望在主线程调用；我们不能直接在工作线程安全调用 GUI，
        # 所以 done_callback 应该是线程安全的或将结果通过信号回到主线程。
        if self.done_callback:
            try:
                self.done_callback(result, self.elapsed_ms)
            except Exception:
                traceback.print_exc()


class PeriodicTimer(QObject):
    """
    可注入任务的周期性定时器。
    信号:
        finished(elapsed_ms)
        taskFinished(result, elapsed_ms)  # 任务完成（不保证在主线程，视 done_callback 实现）
    """
    finished = pyqtSignal(int)
    taskFinished = pyqtSignal(object, int)

    def __init__(
        self,
        interval_ms: int,
        max_duration_ms: Optional[int] = None,
        task: Optional[Callable[..., Any]] = None,
        run_in_thread: bool = False,
        task_done_callback: Optional[Callable[[Any, int], None]] = None,
        run_immediately: bool = False,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.interval_ms = int(interval_ms)
        self.max_duration_ms = None if max_duration_ms is None else int(max_duration_ms)
        self._task = task
        self.run_in_thread = bool(run_in_thread)
        self._task_done_callback = task_done_callback
        self.run_immediately = bool(run_immediately)

        self._timer = QTimer(self)
        self._timer.setInterval(self.interval_ms)
        self._timer.timeout.connect(self._on_timeout)

        self._elapsed_timer = QElapsedTimer()
        self._paused_elapsed_ms = 0
        self._is_paused = False

        self._pool = QThreadPool.globalInstance()

        # 将线程池任务完成通过信号回到主线程（如果用户使用 done callback）
        self.taskFinished.connect(self._on_task_finished)

    def set_task(self, task: Callable[..., Any]):
        """在运行前或运行时设置/替换任务 callable"""
        self._task = task

    def start(self):
        self._paused_elapsed_ms = 0
        self._is_paused = False
        self._elapsed_timer.restart()
        self._timer.start()
        if self.run_immediately:
            self._on_timeout()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self._is_paused = False
        elapsed = self.get_elapsed_ms()
        # 调用结束回调/信号
        self.finished.emit(elapsed)

    def pause(self):
        if not self._timer.isActive() or self._is_paused:
            return
        self._paused_elapsed_ms += self._elapsed_timer.elapsed()
        self._timer.stop()
        self._is_paused = True

    def resume(self):
        if not self._is_paused:
            return
        self._elapsed_timer.restart()
        self._timer.start()
        self._is_paused = False

    def is_active(self) -> bool:
        return self._timer.isActive() and not self._is_paused

    def get_elapsed_ms(self) -> int:
        if self._is_paused:
            return int(self._paused_elapsed_ms)
        else:
            return int(self._paused_elapsed_ms + (self._elapsed_timer.elapsed() if self._elapsed_timer.isValid() else 0))

    def _on_timeout(self):
        elapsed = self.get_elapsed_ms()

        if not self._task:
            # 无任务，仅用于计时
            pass
        else:
            if self.run_in_thread:
                # 在线程池中执行任务
                def done_cb(result, ems):
                    # 由工作线程调用，这里转发到主线程通过信号
                    self.taskFinished.emit(result, ems)

                runnable = _TaskRunnable(self._task, elapsed, done_cb)
                self._pool.start(runnable)
            else:
                # 在主线程直接执行（注意不要阻塞）
                result = None
                try:
                    try:
                        result = self._task(elapsed)
                    except TypeError:
                        result = self._task()
                except Exception:
                    traceback.print_exc()
                    result = None
                # 直接调用完成回调（若有），并发出信号
                if self._task_done_callback:
                    try:
                        self._task_done_callback(result, elapsed)
                    except Exception:
                        traceback.print_exc()
                self.taskFinished.emit(result, elapsed)

        # 再次检查 elapsed（任务可能耗时）
        elapsed = self.get_elapsed_ms()
        if self.max_duration_ms is not None and elapsed >= self.max_duration_ms:
            self.stop()

    def _on_task_finished(self, result: Any, elapsed_ms: int):
        """
        taskFinished 信号在主线程被调用，适合在这里调用用户传入的 task_done_callback（保证在主线程）
        """
        if self._task_done_callback:
            try:
                self._task_done_callback(result, elapsed_ms)
            except Exception:
                traceback.print_exc()