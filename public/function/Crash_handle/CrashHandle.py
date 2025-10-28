import sys
import traceback
from datetime import datetime
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, pyqtSignal, QObject
import signal
import os
from loguru import logger


class CrashHandler(QObject):
    crash_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setup_logging()
        self.setup_exception_handling()
        self.setup_signal_handling()

    def setup_logging(self):
        """设置loguru日志记录"""
        # 移除默认的控制台日志

        # 专门的崩溃日志文件
        logger.add(
            "./log/crash/crash_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="ERROR",
            rotation="1 day",
            retention="90 days",  # 崩溃日志保留更久
            encoding="utf-8",
            filter=lambda record: record["level"].name in ["ERROR", "CRITICAL"]
        )

        logger.info("CrashHandler initialized")

    def setup_exception_handling(self):
        """设置异常处理"""
        # Python异常处理
        sys.excepthook = self.handle_exception

        # Qt异常处理
        if hasattr(sys, '_excepthook'):
            sys._excepthook = sys.excepthook

    def setup_signal_handling(self):
        """设置信号处理"""
        # 处理SIGTERM, SIGINT等信号
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        # Windows下的特殊处理
        if os.name == 'nt':
            try:
                signal.signal(signal.SIGBREAK, self.handle_signal)
            except AttributeError:
                pass

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """处理Python异常"""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        # 使用loguru记录异常
        logger.exception(f"Unhandled exception occurred: {exc_value}")

        # 发送信号
        self.crash_signal.emit(error_msg)

        # 保存详细的崩溃信息
        self.save_crash_dump(error_msg, exc_type, exc_value)

    def handle_signal(self, signum, frame):
        """处理系统信号"""
        signal_names = {
            signal.SIGTERM: "SIGTERM",
            signal.SIGINT: "SIGINT"
        }

        signal_name = signal_names.get(signum, f"Signal {signum}")
        error_msg = f"Application received {signal_name}"

        logger.warning(f"Received signal: {signal_name}")
        self.crash_signal.emit(error_msg)

        # 清理并退出
        QApplication.quit()

    def save_crash_dump(self, error_msg, exc_type=None, exc_value=None):
        """保存详细的崩溃转储"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"/crash_dumps/crash_dump_{timestamp}.txt"

        try:
            # 确保目录存在
            os.makedirs("crash_dumps", exist_ok=True)

            with open(os.getcwd()+filename, 'w', encoding='utf-8') as f:
                f.write(f"Crash Time: {datetime.now()}\n")
                f.write(f"Python Version: {sys.version}\n")
                f.write(f"Platform: {sys.platform}\n")
                if exc_type:
                    f.write(f"Exception Type: {exc_type.__name__}\n")
                if exc_value:
                    f.write(f"Exception Value: {exc_value}\n")
                f.write("-" * 50 + "\n")
                f.write(error_msg)

            logger.info(f"Crash dump saved to: {filename}")

        except Exception as e:
            logger.error(f"Failed to save crash dump: {e}")