import multiprocessing
import time
import threading
import json
import os
import traceback
import sys
from pathlib import Path
from queue import Queue, Empty

import psutil
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Callable, Any, Set, Union
from datetime import datetime, timedelta
from loguru import logger

from public.config_class.Exception_Info import ExceptionInfo
from public.config_class.Log_Config import LogConfig


def kill_process_tree(pid, including_parent=True):
    """
    确认子进程没有启动其他子进程，如果有，必须递归管理或用系统命令杀死整个进程树。
    用 psutil 库递归杀死进程树
    multiprocessing.Process.terminate() 只会终止对应的单个进程，如果该进程启动了其他进程，这些"子进程"不会被自动终止，因而可能会在任务管理器中残留。
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for child in children:
        child.terminate()
    gone, alive = psutil.wait_procs(children, timeout=5)
    for p in alive:
        p.kill()
    if including_parent:
        if psutil.pid_exists(pid):
            parent.terminate()
            parent.wait(5)

@dataclass
class ProcessMetrics:
    process_id: str  # 进程的唯一标识符
    pid: int  # 进程的 PID
    status: str  # 进程的当前状态(如 'RUNNING', 'CRASHED', 'COMPLETED' 等)
    cpu_percent: float  # 进程的 CPU 使用率(原始值,可能超过 100%)
    cpu_percent_normalized: float  # 进程的 CPU 使用率(标准化到单核的百分比)
    memory_mb: float  # 进程使用的内存(MB)
    start_time: datetime  # 进程启动的时间
    uptime: timedelta  # 进程运行的时长
    restart_count: int  # 进程重启的次数
    last_heartbeat: Optional[float] = None  # 最后一次收到的心跳时间(如果有心跳检测)
    exitcode: Optional[int] = None  # 进程的退出码(如果已退出)





class LoggerManager:
    """日志管理器"""

    def __init__(self):
        self.loggers: Dict[str, Any] = {}
        self.configs: Dict[str, LogConfig] = {}
        self.global_exception_queue = multiprocessing.Queue()
        self.logger_ids: Set[str] = set()  # 用于跟踪已创建的logger ID

    def create_logger_config(self,
                             process_id: str = "default",
                             log_dir: str = "./log",
                             log_level: str = "DEBUG",
                             rotation: str = "00:00",
                             retention: str = "30 days",
                             custom_format: str = None,
                             enqueue: bool = True,
                             backtrace: bool = True,
                             diagnose: bool = True,
                             enable_console: bool = True,
                             console_level: str = "DEBUG") -> LogConfig:
        """创建日志配置"""
        if custom_format is None:
            custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  | {process.name} | {thread.name} | {name}:{module}:{line} | {message} </level>"

        config = LogConfig(
            log_dir=log_dir,
            log_level=log_level,
            rotation=rotation,
            retention=retention,
            format=custom_format,
            enqueue=enqueue,
            backtrace=backtrace,
            diagnose=diagnose,
            enable_console=enable_console,
            console_level=console_level
        )

        self.configs[process_id] = config
        return config

    def setup_logger(self, process_id: str, config: LogConfig = None, remove_default: bool = True) -> Any:
        """为指定进程设置日志器"""
        if config is None:
            config = self.configs.get(process_id, self.create_logger_config(process_id))

        # 创建日志目录
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # 如果是第一次设置该logger,移除默认handler
        if remove_default and process_id not in self.logger_ids:
            logger.remove()
            self.logger_ids.add(process_id)

        # 添加文件handler
        log_file = log_dir / f"{process_id}_{'{time:YYYY-MM-DD}'}.log"
        handler_id = logger.add(
            str(log_file),
            rotation=config.rotation,
            retention=config.retention,
            level=config.log_level,
            format=config.format,
            enqueue=config.enqueue,
            backtrace=config.backtrace,
            diagnose=config.diagnose,
            filter=lambda record: record["extra"].get("logger_type", "default") == process_id
        )

        # 添加控制台handler（如果启用）
        console_handler_id = None
        if config.enable_console:
            console_handler_id = logger.add(
                sys.stdout,
                level=config.console_level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | {process.name} | {thread.name} | {name}:{module}:{line} | {message} </level>",
                backtrace=config.backtrace,
                diagnose=config.diagnose,
                filter=lambda record: record["extra"].get("logger_type", "default") == process_id
            )

        # 创建绑定的logger
        process_logger = logger.bind(logger_type=process_id)

        self.loggers[process_id] = {
            'logger': process_logger,
            'file_handler_id': handler_id,
            'console_handler_id': console_handler_id,
            'config': config
        }

        return process_logger

    def setup_main_process_logger(self, config: LogConfig = None) -> Any:
        """设置主进程日志器"""
        if config is None:
            config = self.create_logger_config(
                "main_process",
                log_dir="./log/main",
                log_level="DEBUG",
                custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | MAIN | {module}:{function}:{line} | {message} </level>",
                enable_console=True,
                console_level="DEBUG"
            )

        return self.setup_logger("main_process", config, remove_default=True)

    def setup_global_exception_logger(self, config: LogConfig = None) -> Any:
        if config is None:
            config = self.create_logger_config(
                "global_exceptions",
                log_dir="./log/exceptions",
                log_level="ERROR",
                custom_format=config.format,
                enable_console=True,
                console_level="ERROR"
            )

        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        exception_logger = logger.bind(logger_type="exception")

        # 异常日志文件
        exception_log_file = log_dir / f"exceptions_{'{time:YYYY-MM-DD}'}.log"

        exception_logger.add(
            str(exception_log_file),
            rotation=config.exception_log_rotation,
            retention=config.exception_log_retention,
            level="ERROR",
            format=config.format,
            enqueue=config.enqueue,
            backtrace=config.backtrace,
            diagnose=config.diagnose,
            filter=lambda record: record["extra"].get("logger_type") == "exception"
        )

        self.loggers["global_exceptions"] = exception_logger
        return exception_logger

    def get_logger(self, process_id: str) -> Any:
        """获取指定进程的日志器"""
        if process_id not in self.loggers:
            return self.setup_logger(process_id)
        return self.loggers[process_id]['logger']

    def remove_logger(self, process_id: str):
        """移除指定的日志器"""
        if process_id in self.loggers:
            logger_info = self.loggers[process_id]

            # 移除文件handler
            if logger_info['file_handler_id'] is not None:
                logger.remove(logger_info['file_handler_id'])

            # 移除控制台handler
            if logger_info['console_handler_id'] is not None:
                logger.remove(logger_info['console_handler_id'])

            del self.loggers[process_id]
            self.logger_ids.discard(process_id)


def monitored_target(target_func, args, health_queue, process_id, exception_queue, log_config_dict):
    """包装目标函数以支持健康检查和异常捕获"""
    process_logger = None

    try:
        # 设置进程专用日志器
        if log_config_dict:
            config = LogConfig(**log_config_dict)
            log_dir = Path(config.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)

            # 移除默认handler
            logger.remove()

            # 添加进程专用的文件handler
            log_file = log_dir / f"{process_id}_{'{time:YYYY-MM-DD}'}.log"
            logger.add(
                str(log_file),
                rotation=config.rotation,
                retention=config.retention,
                level=config.log_level,
                format=config.format,
                enqueue=config.enqueue,
                backtrace=config.backtrace,
                diagnose=config.diagnose
            )

            # 添加控制台输出（如果启用）
            if config.enable_console:
                logger.add(
                    sys.stderr,
                    level=config.console_level,
                    format=config.format,
                    backtrace=config.backtrace,
                    diagnose=config.diagnose
                )

        # 设置全局异常处理器
        def exception_handler(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return

            try:
                tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                tb_text = ''.join(tb_lines)

                exception_info = ExceptionInfo(
                    process_id=process_id,
                    pid=os.getpid(),
                    timestamp=datetime.now(),
                    exception_type=exc_type.__name__,
                    exception_message=str(exc_value),
                    traceback_info=tb_text,
                    function_name=exc_traceback.tb_frame.f_code.co_name if exc_traceback else "unknown",
                    line_number=exc_traceback.tb_lineno if exc_traceback else 0,
                    severity="CRITICAL"
                )

                # 发送异常信息到主进程
                if exception_queue:
                    try:
                        exception_queue.put(asdict(exception_info))
                    except:
                        pass

                # 记录到进程日志
                logger.critical(f"未捕获异常: {exc_type.__name__}: {exc_value}")
                logger.critical(f"Traceback: {tb_text}")

            except Exception as e:
                # 异常处理器本身出错，使用默认处理
                sys.__excepthook__(exc_type, exc_value, exc_traceback)

        # 安装异常处理器
        sys.excepthook = exception_handler

        # 启动健康心跳
        if health_queue:
            heartbeat_thread = threading.Thread(
                target=_heartbeat_worker,
                args=(health_queue, process_id, exception_queue)
            )
            heartbeat_thread.daemon = True
            heartbeat_thread.start()

        # 执行实际任务
        logger.info(f"{process_id} 开始执行任务")
        logger.info(f"{process_id}, target_func 是: {target_func}")
        logger.info(f"{process_id}, target_func 参数个数: {target_func.__code__.co_argcount}")
        logger.info(f"{process_id}, args 内容: {args}")
        logger.info(f"{process_id}, args 长度: {len(args)}")

        result = target_func(*args)
        logger.info(f"{process_id} 任务执行完成")
        return result

    except Exception as e:
        # 捕获并记录异常
        tb_text = traceback.format_exc()

        exception_info = ExceptionInfo(
            process_id=process_id,
            pid=os.getpid(),
            timestamp=datetime.now(),
            exception_type=type(e).__name__,
            exception_message=str(e),
            traceback_info=tb_text,
            function_name=traceback.extract_tb(e.__traceback__)[-1].name if e.__traceback__ else "unknown",
            line_number=traceback.extract_tb(e.__traceback__)[-1].lineno if e.__traceback__ else 0,
            severity="ERROR"
        )

        # 发送异常信息到主进程
        if exception_queue:
            try:
                exception_queue.put(asdict(exception_info))
            except:
                pass

        # 发送错误信息到健康检查队列
        if health_queue:
            try:
                health_queue.put(('ERROR', str(e), datetime.now()))
            except:
                pass

        # 记录到进程日志
        logger.error(f"{process_id} 执行过程中发生异常: {e}")
        logger.error(f"Traceback: {tb_text}")

        raise
    finally:
        # 发送结束信号
        if health_queue:
            try:
                health_queue.put(('FINISHED', 'Process completed', datetime.now()))
            except:
                pass

        logger.info(f"{process_id} 进程结束")


def _heartbeat_worker(health_queue, process_id, exception_queue):
    """健康心跳工作线程"""
    try:
        while True:
            try:
                health_queue.put(('HEARTBEAT', datetime.now(), os.getpid()))
                time.sleep(5)  # 每5秒发送一次心跳
            except Exception as e:
                # 心跳线程异常
                if exception_queue:
                    try:
                        exception_info = ExceptionInfo(
                            process_id=process_id,
                            pid=os.getpid(),
                            timestamp=datetime.now(),
                            exception_type=type(e).__name__,
                            exception_message=str(e),
                            traceback_info=traceback.format_exc(),
                            function_name="_heartbeat_worker",
                            line_number=0,
                            severity="WARNING"
                        )
                        exception_queue.put(asdict(exception_info))
                    except:
                        pass
                break
    except Exception as e:
        # 记录心跳线程的致命错误
        if exception_queue:
            try:
                exception_info = ExceptionInfo(
                    process_id=process_id,
                    pid=os.getpid(),
                    timestamp=datetime.now(),
                    exception_type=type(e).__name__,
                    exception_message=str(e),
                    traceback_info=traceback.format_exc(),
                    function_name="_heartbeat_worker",
                    line_number=0,
                    severity="CRITICAL"
                )
                exception_queue.put(asdict(exception_info))
            except:
                pass


class IntegratedProcessMonitor:
    def __init__(self,
                 main_log_config: LogConfig = None,
                 exception_log_config: LogConfig = None,
                 auto_setup_main_exception_handler: bool = True):
        """
        初始化进程监控器

        Args:
            main_log_config: 主进程日志配置
            exception_log_config: 全局异常日志配置
            auto_setup_main_exception_handler: 是否自动设置主进程异常处理器
        """
        # 日志管理器
        self.logger_manager = LoggerManager()

        # 设置主进程日志器
        self.main_logger = self.logger_manager.setup_main_process_logger(main_log_config)

        # 设置全局异常日志器
        self.exception_logger = self.logger_manager.setup_global_exception_logger(exception_log_config)

        # 异常收集
        self.exception_queue = multiprocessing.Queue()
        self.exception_history: List[ExceptionInfo] = []
        self.exception_callbacks: List[Callable] = []

        # 基本监控数据
        self.processes: Dict[str, Dict] = {}
        self.monitoring = True

        # 关键进程管理
        self.critical_processes: Set[str] = set()
        self.shutdown_on_critical_failure = True

        # 指标收集
        self.metrics_history: Dict[str, List[ProcessMetrics]] = {}
        self.current_metrics: Dict[str, ProcessMetrics] = {}

        # 系统信息
        self.cpu_count = psutil.cpu_count()  # 获取CPU核心数
        # CPU监控相关 - 存储psutil.Process对象用于CPU计算
        self.psutil_processes: Dict[str, psutil.Process] = {}
        self.cpu_last_call: Dict[str, float] = {}

        # 事件回调
        self.callbacks = {
            'on_start': [],
            'on_crash': [],
            'on_complete': [],
            'on_restart': [],
            'on_timeout': [],
            'on_unresponsive': [],
            'on_high_cpu': [],
            'on_high_memory': [],
            'on_critical_failure': [],
            'on_shutdown_triggered': [],
            'on_exception': [],  # 新增异常回调
            'on_main_exception': []  # 主进程异常回调
        }

        # 阈值配置
        self.thresholds = {
            'cpu_percent': 80.0,
            'memory_mb': 1000.0,
            'heartbeat_timeout': 30.0
        }

        # 记录系统信息
        self.main_logger.info(f"系统CPU核心数: {self.cpu_count}")
        self.main_logger.info("进程监控器初始化完成")

        # 设置主进程异常处理器
        if auto_setup_main_exception_handler:
            self.setup_main_process_exception_handler()

        # 启动异常收集线程
        self.start_exception_collector()

    def setup_main_process_exception_handler(self):
        """设置主进程异常处理器"""
        original_excepthook = sys.excepthook

        def main_exception_handler(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                self.main_logger.info("接收到键盘中断信号，正在优雅关闭...")
                self.stop_monitoring()
                original_excepthook(exc_type, exc_value, exc_traceback)
                return

            try:
                tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                tb_text = ''.join(tb_lines)

                exception_info = ExceptionInfo(
                    process_id="main_process",
                    pid=os.getpid(),
                    timestamp=datetime.now(),
                    exception_type=exc_type.__name__,
                    exception_message=str(exc_value),
                    traceback_info=tb_text,
                    function_name=exc_traceback.tb_frame.f_code.co_name if exc_traceback else "unknown",
                    line_number=exc_traceback.tb_lineno if exc_traceback else 0,
                    severity="CRITICAL"
                )

                # 记录到主进程日志
                self.main_logger.critical(f"主进程未捕获异常: {exc_type.__name__}: {exc_value}")
                self.main_logger.critical(f"异常堆栈:\n{tb_text}")

                # 记录到全局异常日志
                self.exception_logger.critical(
                    f"主进程异常 | 异常类型: {exception_info.exception_type} | "
                    f"异常信息: {exception_info.exception_message} | "
                    f"函数: {exception_info.function_name}:{exception_info.line_number}"
                )
                self.exception_logger.critical(f"异常堆栈:\n{exception_info.traceback_info}")

                # 保存到异常历史
                self.exception_history.append(exception_info)

                # 触发主进程异常回调
                self.trigger_callbacks('on_main_exception', 'main_process',
                                       exception_info=exception_info)

                # 执行注册的异常回调
                for callback in self.exception_callbacks:
                    try:
                        callback(exception_info)
                    except Exception as e:
                        self.main_logger.error(f"主进程异常回调执行失败: {e}")

            except Exception as e:
                # 异常处理器本身出错，使用默认处理
                self.main_logger.error(f"主进程异常处理器错误: {e}")
                original_excepthook(exc_type, exc_value, exc_traceback)
                return

            # 调用原始异常处理器
            original_excepthook(exc_type, exc_value, exc_traceback)

        sys.excepthook = main_exception_handler
        self.main_logger.info("主进程异常处理器已设置")

    def create_main_process_log_config(self,
                                       log_dir: str = "./log/main",
                                       log_level: str = "INFO",
                                       custom_format: str = None,
                                       enable_console: bool = True,
                                       console_level: str = "DEBUG") -> LogConfig:
        """创建主进程日志配置"""
        if custom_format is None:
            custom_format = "{time:YYYY-MM-DD HH:mm:ss} | {level} | MAIN | {module}:{function}:{line} | {message}"

        return self.logger_manager.create_logger_config(
            process_id="main_process",
            log_dir=log_dir,
            log_level=log_level,
            custom_format=custom_format,
            enable_console=enable_console,
            console_level=console_level
        )

    def create_exception_log_config(self,
                                    log_dir: str = "./log/exceptions",
                                    log_level: str = "ERROR",
                                    custom_format: str = None,
                                    enable_console: bool = True,
                                    console_level: str = "ERROR") -> LogConfig:
        """创建全局异常日志配置"""
        if custom_format is None:
            custom_format = "{time:YYYY-MM-DD HH:mm:ss} | {level} | EXCEPTION | {module}:{function}:{line} | {message}"

        return self.logger_manager.create_logger_config(
            process_id="global_exceptions",
            log_dir=log_dir,
            log_level=log_level,
            custom_format=custom_format,
            enable_console=enable_console,
            console_level=console_level
        )

    def create_process_log_config(self,
                                  process_id: str,
                                  log_level: str = "INFO",
                                  custom_format: str = None,
                                  enable_console: bool = False,
                                  console_level: str = "DEBUG") -> LogConfig:
        """为指定进程创建日志配置"""
        return self.logger_manager.create_logger_config(
            process_id=process_id,
            log_dir=f"./log/processes/{process_id}",
            log_level=log_level,
            custom_format=custom_format,
            enable_console=enable_console,
            console_level=console_level
        )

    def update_main_logger_config(self, config: LogConfig):
        """更新主进程日志配置"""
        # 移除旧的logger
        self.logger_manager.remove_logger("main_process")
        # 设置新的logger
        self.main_logger = self.logger_manager.setup_logger("main_process", config)
        self.main_logger.info("主进程日志配置已更新")

    def update_exception_logger_config(self, config: LogConfig):
        """更新全局异常日志配置"""
        # 移除旧的logger
        self.logger_manager.remove_logger("global_exceptions")
        # 设置新的logger
        self.exception_logger = self.logger_manager.setup_logger("global_exceptions", config)
        self.exception_logger.info("全局异常日志配置已更新")

    def register_exception_callback(self, callback: Callable[[ExceptionInfo], None]):
        """注册异常回调函数"""
        self.exception_callbacks.append(callback)
        self.main_logger.info(f"注册异常回调函数: {callback.__name__}")

    def start_exception_collector(self):
        """启动异常收集线程"""

        def collect_exceptions():
            while self.monitoring:
                try:
                    # 从队列中获取异常信息
                    exception_data = self.exception_queue.get(timeout=1)
                    exception_info = ExceptionInfo(**exception_data)

                    # 保存到历史记录
                    self.exception_history.append(exception_info)

                    # 记录到全局异常日志
                    self.exception_logger.error(
                        f"子进程异常 | 进程ID: {exception_info.process_id} | "
                        f"PID: {exception_info.pid} | "
                        f"异常类型: {exception_info.exception_type} | "
                        f"异常信息: {exception_info.exception_message} | "
                        f"函数: {exception_info.function_name}:{exception_info.line_number}"
                    )
                    self.exception_logger.error(f"异常堆栈:\n{exception_info.traceback_info}")

                    # 记录到主进程日志
                    self.main_logger.error(
                        f"收到子进程异常: {exception_info.process_id} - {exception_info.exception_type}: {exception_info.exception_message}")

                    # 触发异常回调
                    self.trigger_callbacks('on_exception', exception_info.process_id,
                                           exception_info=exception_info)

                    # 执行注册的异常回调
                    for callback in self.exception_callbacks:
                        try:
                            callback(exception_info)
                        except Exception as e:
                            self.main_logger.error(f"异常回调执行失败: {e}")

                    # 限制历史记录长度
                    if len(self.exception_history) > 1000:
                        self.exception_history = self.exception_history[-500:]

                except Empty:
                    continue
                except Exception as e:
                    self.main_logger.error(f"异常收集器错误: {e}")
                    self.exception_logger.error(f"异常收集器错误: {e}\n{traceback.format_exc()}")

        self.exception_thread = threading.Thread(target=collect_exceptions)
        self.exception_thread.daemon = True
        self.exception_thread.start()
        self.main_logger.info("异常收集线程已启动")

    def get_process_exceptions(self, process_id: str = None) -> List[ExceptionInfo]:
        """获取进程异常历史"""
        if process_id is None:
            return self.exception_history.copy()
        return [exc for exc in self.exception_history if exc.process_id == process_id]

    def get_exception_summary(self) -> Dict:
        """获取异常汇总信息"""
        summary = {
            'total_exceptions': len(self.exception_history),
            'by_process': {},
            'by_type': {},
            'recent_exceptions': []
        }

        for exc in self.exception_history:
            # 按进程统计
            if exc.process_id not in summary['by_process']:
                summary['by_process'][exc.process_id] = 0
            summary['by_process'][exc.process_id] += 1

            # 按异常类型统计
            if exc.exception_type not in summary['by_type']:
                summary['by_type'][exc.exception_type] = 0
            summary['by_type'][exc.exception_type] += 1

        # 最近的异常（最多10个）
        recent = sorted(self.exception_history, key=lambda x: x.timestamp, reverse=True)[:10]
        summary['recent_exceptions'] = [asdict(exc) for exc in recent]

        return summary

    def add_critical_process(self, process_id: str):
        """添加关键进程"""
        self.critical_processes.add(process_id)
        self.main_logger.info(f"添加关键进程: {process_id}")

    def remove_critical_process(self, process_id: str):
        """移除关键进程"""
        self.critical_processes.discard(process_id)
        self.main_logger.info(f"移除关键进程: {process_id}")

    def set_critical_processes(self, process_ids: List[str]):
        """设置关键进程列表"""
        self.critical_processes = set(process_ids)
        self.main_logger.info(f"设置关键进程列表: {process_ids}")

    def get_critical_processes(self) -> List[str]:
        """获取关键进程列表"""
        return list(self.critical_processes)

    def is_critical_process(self, process_id: str) -> bool:
        """检查是否为关键进程"""
        return process_id in self.critical_processes

    def check_critical_processes(self):
        """检查关键进程状态"""
        failed_critical = []

        for process_id in self.critical_processes:
            if process_id in self.processes:
                proc_info = self.processes[process_id]
                process = proc_info['process']

                if not process.is_alive():
                    # 关键进程已停止
                    failed_critical.append(process_id)
                    self.main_logger.critical(f"关键进程停止: {process_id} (退出码: {process.exitcode})")

                    # 触发关键进程失败回调
                    self.trigger_callbacks('on_critical_failure', process_id,
                                           exitcode=process.exitcode,
                                           process_type='critical')

        # 如果有关键进程失败且启用了关闭机制
        if failed_critical and self.shutdown_on_critical_failure:
            self.main_logger.critical(f"检测到关键进程失败: {failed_critical}")
            self.main_logger.critical("开始关闭所有其他进程...")

            # 触发关闭回调
            self.trigger_callbacks('on_shutdown_triggered',
                                   failed_critical[0],
                                   failed_processes=failed_critical,
                                   action='shutdown_all')

            self.shutdown_all_processes(exclude_critical=False)
            return True

        return False

    def shutdown_all_processes(self, exclude_critical=True):
        """关闭所有进程"""
        self.main_logger.warning("开始关闭所有进程...")

        for process_id, proc_info in list(self.processes.items()):
            # 如果设置了排除关键进程，则跳过关键进程
            if exclude_critical and self.is_critical_process(process_id):
                continue

            process = proc_info['process']
            if process and process.is_alive():
                self.main_logger.info(f"关闭进程: {process_id} (PID: {process.pid})")

                try:
                    # 先等待2秒 完成剩余工作
                    process.join(timeout=2)
                    # 先尝试优雅关闭
                    process.terminate()
                    process.join(timeout=5)

                    # 如果还没结束，强制杀死
                    if process.is_alive():
                        self.main_logger.warning(f"强制杀死进程: {process_id}")
                        kill_process_tree(process.pid)
                        process.kill()
                        process.join(timeout=2)

                except Exception as e:
                    self.main_logger.error(f"关闭进程失败 {process_id}: {e}")

        self.main_logger.warning("所有进程关闭完成")

    def start_worker(self, target_func, restart_target_func=None, args=(), name=None,
                     auto_restart=True, max_restarts=3, timeout=None, health_check=True,
                     is_critical=False, log_config: LogConfig = None):
        """启动工作进程"""
        process_id = name or f"Process-{len(self.processes)}"

        # 如果标记为关键进程，添加到关键进程列表
        if is_critical:
            self.add_critical_process(process_id)

        # 如果没有提供日志配置，创建默认配置
        if log_config is None:
            log_config = self.create_process_log_config(process_id)

        # 创建健康检查队列
        health_queue = multiprocessing.Queue() if health_check else None

        # 创建进程
        process = multiprocessing.Process(
            target=monitored_target,
            args=(target_func, args, health_queue, process_id,
                  self.exception_queue, asdict(log_config)),
            name=process_id
        )

        process.start()

        # 保存进程信息
        self.processes[process_id] = {
            'process': process,
            'target_func': target_func,
            'restart_target_func': restart_target_func,
            'args': args,
            'start_time': datetime.now(),
            'restart_count': 0,
            'last_heartbeat': datetime.now() if health_check else None,
            'status': 'RUNNING',
            'error_info': None,
            'health_queue': health_queue,
            'auto_restart': auto_restart,
            'max_restarts': max_restarts,
            'timeout': timeout,
            'health_check': health_check,
            'is_critical': is_critical,
            'log_config': log_config
        }

        # 初始化指标历史
        self.metrics_history[process_id] = []

        # 初始化CPU监控 - 延迟初始化psutil.Process对象
        try:
            # 稍等一下确保进程已启动
            time.sleep(0.1)
            if process.is_alive():
                self.psutil_processes[process_id] = psutil.Process(process.pid)
                # 第一次调用cpu_percent()来初始化（这次结果会是0，但为后续调用做准备）
                self.psutil_processes[process_id].cpu_percent()
                self.cpu_last_call[process_id] = time.time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        critical_flag = "🔴关键" if is_critical else "🟡普通"
        self.main_logger.info(f"启动进程: {process_id} (PID: {process.pid}) [{critical_flag}]")

        # 触发启动回调
        self.trigger_callbacks('on_start', process_id,
                               pid=process.pid, start_time=datetime.now(),
                               is_critical=is_critical)

        return process_id

    def check_process_status(self, process_id):
        """检查进程状态"""
        if process_id not in self.processes:
            return None

        proc_info = self.processes[process_id]
        process = proc_info['process']
        health_queue = proc_info['health_queue']

        # 处理健康检查队列
        if health_queue:
            while True:
                try:
                    msg_type, data, timestamp = health_queue.get_nowait()

                    if msg_type == 'HEARTBEAT':
                        proc_info['last_heartbeat'] = data
                    elif msg_type == 'ERROR':
                        proc_info['error_info'] = data
                        proc_info['status'] = 'ERROR'
                    elif msg_type == 'FINISHED':
                        proc_info['status'] = 'FINISHED'

                except:
                    break

        # 检查进程状态
        current_time = datetime.now()

        if not process.is_alive():
            # 清理psutil对象
            if process_id in self.psutil_processes:
                del self.psutil_processes[process_id]
            if process_id in self.cpu_last_call:
                del self.cpu_last_call[process_id]

            if process.exitcode == 0:
                proc_info['status'] = 'COMPLETED'
                self.main_logger.info(f"进程正常完成: {process_id}")
                # 触发完成回调
                self.trigger_callbacks('on_complete', process_id,
                                       exitcode=process.exitcode,
                                       runtime=current_time - proc_info['start_time'],
                                       is_critical=proc_info.get('is_critical', False))
            else:
                proc_info['status'] = 'CRASHED'
                self.main_logger.error(f"进程异常退出: {process_id} (退出码: {process.exitcode})")
                # 触发崩溃回调
                self.trigger_callbacks('on_crash', process_id,
                                       exitcode=process.exitcode,
                                       runtime=current_time - proc_info['start_time'],
                                       error_info=proc_info['error_info'],
                                       is_critical=proc_info.get('is_critical', False))

                # 处理自动重启（仅对非关键进程或允许重启的关键进程）
                if (proc_info['auto_restart'] and
                        proc_info['restart_count'] < proc_info['max_restarts']):
                    self.restart_process(process_id)

        elif proc_info['health_check'] and proc_info['last_heartbeat']:
            # 检查心跳超时
            heartbeat_age = current_time - proc_info['last_heartbeat']
            if heartbeat_age > timedelta(seconds=self.thresholds['heartbeat_timeout']):
                proc_info['status'] = 'UNRESPONSIVE'
                self.main_logger.warning(f"进程无响应: {process_id} (心跳超时: {heartbeat_age})")
                self.trigger_callbacks('on_unresponsive', process_id,
                                       heartbeat_age=heartbeat_age,
                                       is_critical=proc_info.get('is_critical', False))

        # 检查运行超时
        if proc_info['timeout']:
            runtime = current_time - proc_info['start_time']
            if runtime > proc_info['timeout']:
                self.main_logger.warning(f"进程超时: {process_id}")
                process.terminate()
                self.trigger_callbacks('on_timeout', process_id,
                                       timeout=proc_info['timeout'],
                                       runtime=runtime,
                                       is_critical=proc_info.get('is_critical', False))

        return {
            'process_id': process_id,
            'pid': process.pid if process.pid else 'N/A',
            'status': proc_info['status'],
            'exitcode': process.exitcode,
            'uptime': current_time - proc_info['start_time'],
            'restart_count': proc_info['restart_count'],
            'last_heartbeat_age': current_time - proc_info['last_heartbeat'] if proc_info['last_heartbeat'] else None,
            'error_info': proc_info['error_info'],
            'is_critical': proc_info.get('is_critical', False)
        }

    def restart_process(self, process_id):
        """重启进程"""
        if process_id not in self.processes:
            return False

        proc_info = self.processes[process_id]
        old_process = proc_info['process']

        self.main_logger.info(f"重启进程: {process_id}")

        # 清理旧进程和psutil对象
        if process_id in self.psutil_processes:
            del self.psutil_processes[process_id]
        if process_id in self.cpu_last_call:
            del self.cpu_last_call[process_id]

        if old_process.is_alive():
            old_process.terminate()
            old_process.join(timeout=5)

            if old_process.is_alive():
                old_process.kill()

        # 获取重启目标函数
        restart_func = proc_info['restart_target_func'] if proc_info['restart_target_func'] else proc_info[
            'target_func']

        # 创建新进程
        new_process = multiprocessing.Process(
            target=monitored_target,
            args=(restart_func, proc_info['args'], proc_info['health_queue'],
                  process_id, self.exception_queue, asdict(proc_info['log_config'])),
            name=process_id
        )

        new_process.start()

        # 更新进程信息
        proc_info['process'] = new_process
        proc_info['start_time'] = datetime.now()
        proc_info['restart_count'] += 1
        proc_info['last_heartbeat'] = datetime.now() if proc_info['health_check'] else None
        proc_info['status'] = 'RUNNING'
        proc_info['error_info'] = None

        # 重新初始化CPU监控
        try:
            time.sleep(0.1)
            if new_process.is_alive():
                self.psutil_processes[process_id] = psutil.Process(new_process.pid)
                self.psutil_processes[process_id].cpu_percent()
                self.cpu_last_call[process_id] = time.time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        self.main_logger.info(f"进程重启完成: {process_id} (新PID: {new_process.pid})")

        # 触发重启回调
        self.trigger_callbacks('on_restart', process_id,
                               new_pid=new_process.pid,
                               restart_count=proc_info['restart_count'],
                               is_critical=proc_info.get('is_critical', False))

        return True

    def print_process_status(self, status):
        """打印进程状态"""
        status_icons = {
            'RUNNING': '🟢',
            'COMPLETED': '✅',
            'CRASHED': '💥',
            'UNRESPONSIVE': '😵',
            'ERROR': '🔥',
            'FINISHED': '🏁'
        }

        icon = status_icons.get(status['status'], '❓')
        critical_flag = "🔴" if status.get('is_critical', False) else "🟡"
        heartbeat_info = ""

        if status['last_heartbeat_age'] is not None:
            heartbeat_info = f"心跳: {status['last_heartbeat_age']} 前"

        self.main_logger.info(f"{icon}{critical_flag} {status['process_id']:15} | "
                              f"PID: {str(status['pid']):6} | "
                              f"状态: {status['status']:12} | "
                              f"运行: {status['uptime']} | "
                              f"重启: {status['restart_count']} | "
                              f"{heartbeat_info}")

    def register_callback(self, event_type: str, callback: Callable):
        """注册事件回调"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
            self.main_logger.info(f"注册回调: {event_type}")

    def trigger_callbacks(self, event_type: str, process_id: str, **kwargs):
        """触发回调"""
        for callback in self.callbacks.get(event_type, []):
            try:
                callback(process_id, **kwargs)
            except Exception as e:
                self.main_logger.error(f"回调执行失败 {event_type}: {e}")

    def collect_metrics(self, process_id: str) -> Optional[ProcessMetrics]:
        """收集进程指标"""
        if process_id not in self.processes:
            return None

        proc_info = self.processes[process_id]
        process = proc_info['process']

        if not process or not process.is_alive():
            return None

        try:
            # 获取或创建psutil.Process对象
            if process_id not in self.psutil_processes:
                self.psutil_processes[process_id] = psutil.Process(process.pid)
                # 第一次调用cpu_percent()来初始化
                self.psutil_processes[process_id].cpu_percent()
                self.cpu_last_call[process_id] = time.time()
                cpu_percent = 0.0  # 第一次调用返回0
            else:
                p = self.psutil_processes[process_id]

                # 检查是否需要等待足够的时间间隔来获取准确的CPU使用率
                current_time = time.time()
                if (process_id in self.cpu_last_call and
                        current_time - self.cpu_last_call[process_id] < 1.0):
                    # 如果距离上次调用不足1秒，使用interval参数
                    cpu_percent = p.cpu_percent(interval=0.1)
                else:
                    # 使用非阻塞调用
                    cpu_percent = p.cpu_percent()

                self.cpu_last_call[process_id] = current_time
            # 计算标准化的CPU使用率（相对于单核）
            cpu_percent_normalized = cpu_percent / self.cpu_count
            # 获取内存信息
            memory_mb = self.psutil_processes[process_id].memory_info().rss / 1024 / 1024

            metrics = ProcessMetrics(
                process_id=process_id,
                pid=process.pid,
                status=proc_info['status'],
                cpu_percent=cpu_percent,  # 原始CPU使用率（可能超过100%）
                cpu_percent_normalized=cpu_percent_normalized,  # 标准化CPU使用率（0-100%）
                memory_mb=memory_mb,
                start_time=proc_info['start_time'],
                uptime=datetime.now() - proc_info['start_time'],
                restart_count=proc_info['restart_count'],
                last_heartbeat=proc_info['last_heartbeat'],
                exitcode=process.exitcode
            )

            # 保存当前指标
            self.current_metrics[process_id] = metrics

            # 保存历史记录
            self.metrics_history[process_id].append(metrics)

            # 限制历史记录长度
            if len(self.metrics_history[process_id]) > 100:
                self.metrics_history[process_id].pop(0)

            # 检查阈值告警
            self.check_thresholds(metrics)

            return metrics

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            self.main_logger.warning(f"无法收集进程指标 {process_id}: {e}")
            # 清理无效的psutil对象
            if process_id in self.psutil_processes:
                del self.psutil_processes[process_id]
            if process_id in self.cpu_last_call:
                del self.cpu_last_call[process_id]
            return None

    def check_thresholds(self, metrics: ProcessMetrics):
        """检查阈值"""
        # CPU使用率告警 - 使用标准化的CPU使用率
        if metrics.cpu_percent_normalized > self.thresholds['cpu_percent']:
            self.trigger_callbacks('on_high_cpu', metrics.process_id,
                                   cpu_percent=metrics.cpu_percent_normalized,
                                   cpu_percent_raw=metrics.cpu_percent,
                                   threshold=self.thresholds['cpu_percent'])

        # 内存使用告警
        if metrics.memory_mb > self.thresholds['memory_mb']:
            self.trigger_callbacks('on_high_memory', metrics.process_id,
                                   memory_mb=metrics.memory_mb,
                                   threshold=self.thresholds['memory_mb'])

    def monitor_all_processes(self):
        """监控所有进程"""
        current_time = time.strftime('%H:%M:%S')
        self.main_logger.info(f"\n=== 进程监控报告 ({current_time}) ===")

        # 首先检查关键进程
        critical_failed = self.check_critical_processes()
        if critical_failed:
            self.main_logger.critical("检测到关键进程失败，系统将关闭")
            return False  # 返回False表示需要停止监控

        for process_id in list(self.processes.keys()):
            # 检查基本状态
            status = self.check_process_status(process_id)
            if status:
                self.print_process_status(status)

            # 收集指标
            metrics = self.collect_metrics(process_id)
            if metrics:
                # 显示原始CPU使用率和标准化CPU使用率
                self.main_logger.info(f"    📊 CPU: {metrics.cpu_percent:.1f}% (原始) / "
                                      f"{metrics.cpu_percent_normalized:.1f}% (标准化) | "
                                      f"内存: {metrics.memory_mb:.1f}MB | "
                                      f"核心数: {self.cpu_count}")

        # 显示异常统计
        exception_summary = self.get_exception_summary()
        if exception_summary['total_exceptions'] > 0:
            self.main_logger.info(f"📈 总异常数: {exception_summary['total_exceptions']}")
            for process_id, count in exception_summary['by_process'].items():
                self.main_logger.info(f"    {process_id}: {count} 个异常")

        return True

    def start_monitoring(self, interval=5):
        """开始监控"""

        def monitor_loop():
            self.main_logger.info("开始集成进程监控")
            self.main_logger.info(f"关键进程: {list(self.critical_processes)}")

            while self.monitoring:
                try:
                    should_continue = self.monitor_all_processes()
                    if not should_continue:
                        self.main_logger.critical("监控检测到关键进程失败，停止监控")
                        break
                    time.sleep(interval)
                except Exception as e:
                    self.main_logger.error(f"监控循环错误: {e}")
                    self.exception_logger.error(f"监控循环错误: {e}\n{traceback.format_exc()}")

        self.monitor_thread = threading.Thread(target=monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        self.main_logger.info("监控线程已启动")

    def stop_monitoring(self):
        """停止监控"""
        self.main_logger.info("正在停止进程监控器...")
        self.monitoring = False

        if hasattr(self, 'monitor_thread') and self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        if hasattr(self, 'exception_thread') and self.exception_thread:
            self.exception_thread.join(timeout=5)

        # 清理psutil对象
        self.psutil_processes.clear()
        self.cpu_last_call.clear()

        # 清理所有进程
        self.shutdown_all_processes(exclude_critical=False)

        self.main_logger.info("进程监控器已停止")

    def export_exception_report(self, filename: str = None):
        """导出异常报告"""
        if filename is None:
            filename = f"exception_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        report = {
            'export_time': datetime.now().isoformat(),
            'summary': self.get_exception_summary(),
            'detailed_exceptions': [asdict(exc) for exc in self.exception_history]
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        self.main_logger.info(f"异常报告导出到: {filename}")
        return filename

  # 测试函数
def normal_worker():
    import time
    for i in range(10):
        logger.info(f"正常工作中... {i}")
        time.sleep(1)
    logger.info("工作完成")


def error_worker():
    import time
    time.sleep(2)
    logger.info("即将抛出异常...")
    raise ValueError("这是一个测试异常")

# 示例使用
if __name__ == "__main__":
    # 创建自定义的主进程日志配置
    main_config = LogConfig(
        log_dir="./log/main",
        log_level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | MAIN | {module}:{function}:{line} | {message}",
        enable_console=True,
        console_level="DEBUG"
    )

    # 创建自定义的异常日志配置
    exception_config = LogConfig(
        log_dir="./log/exceptions",
        log_level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | EXCEPTION | {module}:{function}:{line} | {message}",
        enable_console=True,
        console_level="ERROR"
    )

    # 创建监控器
    monitor = IntegratedProcessMonitor(
        main_log_config=main_config,
        exception_log_config=exception_config
    )


    # 注册异常回调
    def on_any_exception(exception_info):
        print(f"检测到异常: {exception_info.process_id} - {exception_info.exception_type}")


    monitor.register_exception_callback(on_any_exception)

    # 创建工作进程的日志配置
    worker1_config = monitor.create_process_log_config(
        "worker1",
        log_level="DEBUG",
        custom_format="{time} | {level} | Worker1 | {message}",
        enable_console=False
    )




    # 启动工作进程
    monitor.start_worker(normal_worker, name="worker1", log_config=worker1_config)
    monitor.start_worker(error_worker, name="worker2", auto_restart=False)

    try:
        # 启动监控
        monitor.start_monitoring(interval=3)

        # 模拟主进程工作
        for i in range(20):
            time.sleep(1)
            if i == 10:
                # 模拟主进程异常
                try:
                    x = 1 / 0
                except Exception as e:
                    monitor.main_logger.warning(f"捕获并处理了异常: {e}")

    except KeyboardInterrupt:
        monitor.main_logger.info("接收到中断信号")
    finally:
        monitor.stop_monitoring()

        # 导出异常报告
        report_file = monitor.export_exception_report()
        print(f"异常报告已导出: {report_file}")