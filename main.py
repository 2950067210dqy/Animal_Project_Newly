import json
import logging as diagnostic_logging
import multiprocessing
import queue as queue_module
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from multiprocessing import Process, freeze_support
import os
import time
import psutil
from loguru import logger
from Service import main_response_Modbus, main_gui, main_monitor_data, main_deep_camera, main_infrared_camera
from public.config_class.Log_Config import LogConfig
from public.entity.queue.ObjectQueue import ObjectQueue
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.ProcessMonitor.ProcessMonitor import IntegratedProcessMonitor
from public.util.time_util import time_util



#进程监控器
monitor=None
runtime_diagnostics_queue = None
runtime_diagnostics_drop_lock = threading.Lock()
runtime_diagnostics_dropped = 0


def get_main_program_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


MAIN_PROGRAM_DIR = get_main_program_dir()


def resolve_main_program_path(*parts):
    return os.path.join(MAIN_PROGRAM_DIR, *parts)


def get_writable_log_root():
    candidates = [
        resolve_main_program_path("log"),
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "AnimalProject",
            "log",
        ),
        os.path.join(tempfile.gettempdir(), "AnimalProject", "log"),
    ]
    checked = set()
    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if candidate in checked:
            continue
        checked.add(candidate)
        try:
            os.makedirs(candidate, exist_ok=True)
            descriptor, probe_path = tempfile.mkstemp(
                prefix=".write_probe_",
                dir=candidate,
            )
            os.close(descriptor)
            os.remove(probe_path)
            return candidate
        except OSError:
            continue
    raise OSError("no writable log directory is available")


LOG_ROOT_DIR = get_writable_log_root()


def resolve_log_path(*parts):
    return os.path.join(LOG_ROOT_DIR, *parts)


def emit_runtime_diagnostic(source, event, message, pid=None):
    global runtime_diagnostics_dropped
    if runtime_diagnostics_queue is None:
        return
    with runtime_diagnostics_drop_lock:
        dropped_count = runtime_diagnostics_dropped
        record_message = str(message)
        if dropped_count:
            record_message = (
                f"{record_message}, "
                f"runtime_log_drops_since_last_success={dropped_count}"
            )
        record = {
            "timestamp": time.time(),
            "source": str(source),
            "event": str(event),
            "pid": int(os.getpid() if pid is None else pid),
            "message": record_message,
        }
        try:
            runtime_diagnostics_queue.put_nowait(record)
            runtime_diagnostics_dropped = 0
        except queue_module.Full:
            runtime_diagnostics_dropped = dropped_count + 1
        except (BrokenPipeError, EOFError, OSError):
            runtime_diagnostics_dropped = dropped_count + 1


def runtime_diagnostics_writer(diagnostics_queue):
    log_path = resolve_log_path(
        "runtime",
        "video_trajectory_runtime.log",
    )
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    diagnostics_logger = diagnostic_logging.getLogger(
        f"video_trajectory_runtime_writer_{os.getpid()}"
    )
    diagnostics_logger.setLevel(diagnostic_logging.INFO)
    diagnostics_logger.propagate = False
    diagnostics_logger.handlers.clear()
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=20 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        diagnostic_logging.Formatter(
            "%(asctime)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    diagnostics_logger.addHandler(file_handler)
    diagnostics_logger.info(
        f"process_monitor | diagnostics_started | pid={os.getpid()} | "
        f"path={log_path}"
    )

    try:
        while True:
            record = diagnostics_queue.get()
            if record is None:
                break
            diagnostics_logger.info(
                f"{record.get('source', 'unknown')} | "
                f"{record.get('event', 'runtime')} | "
                f"pid={record.get('pid', 0)} | "
                f"{record.get('message', '')}"
            )
    except (EOFError, OSError):
        pass
    finally:
        file_handler.flush()
        file_handler.close()
# ===================== 回调函数示例 =====================

def on_process_start(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "process_start",
        f"process={process_id}, critical={kwargs.get('is_critical', False)}",
        pid=kwargs.get("pid") or 0,
    )
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    logger.info(f"🎬 进程启动: {process_id} (PID: {kwargs.get('pid')}) {critical_info}")

def on_process_crash(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "process_crash",
        f"process={process_id}, exitcode={kwargs.get('exitcode')}, "
        f"runtime={kwargs.get('runtime', 0)}, error={kwargs.get('error_info')}",
    )
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"

    error_msg = (
            f"💥 进程崩溃: {process_id} {critical_info}\n"
            f"   退出码: {kwargs.get('exitcode')}\n"
            f"   运行时间: {kwargs.get('runtime', 0)}"
            + (f"\n   错误信息: {kwargs.get('error_info')}" if kwargs.get('error_info') else "")
    )
    logger.error(error_msg)
    # main_gui.on_crash(error_msg)
def on_process_complete(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "process_complete",
        f"process={process_id}, runtime={kwargs.get('runtime', 0)}",
    )
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    logger.info(f"✅ 进程完成: {process_id} {critical_info} (运行时间: {kwargs.get('runtime', 0)})")

def on_process_restart(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "process_restart",
        f"process={process_id}, new_pid={kwargs.get('new_pid')}, "
        f"restart_count={kwargs.get('restart_count')}",
        pid=kwargs.get("new_pid") or 0,
    )
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    logger.info(f"🔄 进程重启: {process_id} {critical_info}")
    logger.info(f"   新PID: {kwargs.get('new_pid')}")
    logger.info(f"   重启次数: {kwargs.get('restart_count')}")

def on_process_timeout(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "process_timeout",
        f"process={process_id}, timeout={kwargs.get('timeout')}, "
        f"runtime={kwargs.get('runtime', 0)}",
    )
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    logger.warning(f"⏰ 进程超时: {process_id} {critical_info}")
    logger.warning(f"   超时限制: {kwargs.get('timeout')}秒")
    logger.warning(f"   实际运行: {kwargs.get('runtime', 0)}")

def on_process_unresponsive(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "process_unresponsive",
        f"process={process_id}, heartbeat_age={kwargs.get('heartbeat_age', 0)}",
    )
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    error_msg = f"""😵 进程无响应: {process_id} {critical_info}
       心跳超时: {kwargs.get('heartbeat_age', 0)}"""
    logger.warning(
        error_msg
    )
    # main_gui.on_crash(error_msg)
def on_high_cpu(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "high_cpu",
        f"process={process_id}, cpu_percent={kwargs.get('cpu_percent', 0):.1f}, "
        f"threshold={kwargs.get('threshold', 0):.1f}",
    )
    logger.warning(f"🔥 CPU使用率过高: {process_id}")
    logger.warning(f"   当前: {kwargs.get('cpu_percent', 0):.1f}%")
    logger.warning(f"   阈值: {kwargs.get('threshold', 0):.1f}%")

def on_high_memory(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "high_memory",
        f"process={process_id}, memory_mb={kwargs.get('memory_mb', 0):.1f}, "
        f"threshold={kwargs.get('threshold', 0):.1f}",
    )
    logger.warning(f"🧠 内存使用过高: {process_id}")
    logger.warning(f"   当前: {kwargs.get('memory_mb', 0):.1f}MB")
    logger.warning(f"   阈值: {kwargs.get('threshold', 0):.1f}MB")

def on_process_metrics(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "process_metrics",
        f"process={process_id}, status={kwargs.get('status')}, "
        f"cpu_raw={kwargs.get('cpu_percent_raw', 0):.1f}, "
        f"cpu_normalized={kwargs.get('cpu_percent_normalized', 0):.1f}, "
        f"memory_mb={kwargs.get('memory_mb', 0):.1f}, "
        f"uptime_seconds={kwargs.get('uptime_seconds', 0):.1f}, "
        f"restart_count={kwargs.get('restart_count', 0)}",
        pid=kwargs.get("pid") or 0,
    )


def on_critical_failure(process_id, **kwargs):
    emit_runtime_diagnostic(
        "process_monitor",
        "critical_failure",
        f"process={process_id}, exitcode={kwargs.get('exitcode')}",
    )
    error_msg = f"""🚨 关键进程失败: {process_id}
       退出码: {kwargs.get('exitcode')}
       系统将关闭所有其他进程"""
    logger.critical(
        error_msg
    )
    # main_gui.on_crash(error_msg)
def on_shutdown_triggered(process_id, **kwargs):
    failed_processes = kwargs.get('failed_processes', [])
    emit_runtime_diagnostic(
        "process_monitor",
        "shutdown_triggered",
        f"process={process_id}, failed_processes={failed_processes}",
    )
    logger.critical(f"🛑 触发系统关闭，原因: 关键进程失败 {failed_processes}")
    logger.critical("   正在关闭所有进程...")
 # 注册异常回调
def on_any_exception(exception_info):
    emit_runtime_diagnostic(
        "process_monitor",
        "process_exception",
        f"process={exception_info.process_id}, "
        f"type={exception_info.exception_type}, "
        f"message={exception_info.exception_message}",
        pid=exception_info.pid,
    )
    logger.error(f"检测到异常: {exception_info.process_id} - {exception_info.exception_type}")
# 过滤日志

def kill_process_tree(pid, including_parent=True):
    """
    确认子进程没有启动其他子进程，如果有，必须递归管理或用系统命令杀死整个进程树。
    用 psutil 库递归杀死进程树
    multiprocessing.Process.terminate() 只会终止对应的单个进程，如果该进程启动了其他进程，这些“子进程”不会被自动终止，因而可能会在任务管理器中残留。
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



def test_integrated_monitor():
    freeze_support()
    multiprocessing.set_start_method('spawn', force=True)
    global runtime_diagnostics_queue
    runtime_diagnostics_queue = multiprocessing.Queue(maxsize=2048)
    diagnostics_thread = threading.Thread(
        target=runtime_diagnostics_writer,
        args=(runtime_diagnostics_queue,),
        name="video_trajectory_runtime_writer",
        daemon=True,
    )
    diagnostics_thread.start()
    # 加载日志配置
    # 移除默认处理器
    # logger.remove()

    logger.add(
        resolve_log_path("main", "main_{time:YYYY-MM-DD}.log"),
        rotation="00:00",  # 日志文件转存
        retention="30 days",  # 多长时间之后清理
        enqueue=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  |{process.name} | {thread.name} |  {name} : {module}:{line} | {message} </level>",

    )

    logger.info(f"{'-' * 40}main_start{'-' * 40}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")
    q = multiprocessing.Queue()  # 创建 Queue 消息传递
    send_message_q = multiprocessing.Queue()  # 发送查询报文的消息传递单独一个通道


    # 创建自定义的主进程日志配置
    main_config = LogConfig(
        log_dir=resolve_log_path("main"),
        log_level="DEBUG",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} |{process.name} | {thread.name} |  {name} :  {module}:{function}:{line} | {message} </level>",
        enable_console=True,
        console_level="DEBUG"
    )
    # 创建自定义的异常日志配置
    exception_config = LogConfig(
        log_dir=resolve_log_path("exceptions"),
        log_level="ERROR",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | EXCEPTION |{process.name} | {thread.name} |  {name} :  {module}:{function}:{line} | {message} </level>",
        enable_console=True,
        console_level="ERROR"
    )
    # 创建监控器
    global monitor
    # 创建监控器
    monitor = IntegratedProcessMonitor(
        main_log_config=main_config,
        exception_log_config=exception_config
    )

    # 设置自定义阈值
    monitor.thresholds['cpu_percent'] = 70.0
    monitor.thresholds['memory_mb'] = 2000.0
    monitor.thresholds['heartbeat_timeout']=30.0

    # 注册所有回调
    monitor.register_callback('on_start', on_process_start)
    monitor.register_callback('on_crash', on_process_crash)
    monitor.register_callback('on_complete', on_process_complete)
    monitor.register_callback('on_restart', on_process_restart)
    monitor.register_callback('on_timeout', on_process_timeout)
    monitor.register_callback('on_unresponsive', on_process_unresponsive)
    monitor.register_callback('on_high_cpu', on_high_cpu)
    monitor.register_callback('on_high_memory', on_high_memory)
    monitor.register_callback('on_metrics', on_process_metrics)
    monitor.register_callback('on_critical_failure', on_critical_failure)
    monitor.register_callback('on_shutdown_triggered', on_shutdown_triggered)
    monitor.register_exception_callback(on_any_exception)

    # 创建工作进程的日志配置 调试专用 记得注释
    p_response_comm_config = monitor.create_process_log_config(
        "p_response_comm",
        log_dir=resolve_log_path("processes", "p_response_comm"),
        log_level="DEBUG",
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | p_response_comm | {module}:{function}:{line} | {message} </level>",
        enable_console=True
    )
    monitor.start_worker(
        target_func=main_response_Modbus.main,
        args=(),
        name="p_response_comm",
        auto_restart=False,
        log_config=p_response_comm_config
    )

    p_monitor_data_config = monitor.create_process_log_config(
        "p_monitor_data",
        log_dir=resolve_log_path("processes", "p_monitor_data"),
        log_level="DEBUG",
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | p_monitor_data |{process.name} | {thread.name} |  {name} :  {module}:{function}:{line} | {message} </level> ",
        enable_console=True
    )
    monitor.start_worker(
        target_func=main_monitor_data.main,
        restart_target_func=main_monitor_data.restart,
        args=(q,send_message_q),
        name="p_monitor_data",
        auto_restart=True,
        log_config=p_monitor_data_config
    )
    p_deep_camera_config = monitor.create_process_log_config(
        "p_deep_camera",
        log_dir=resolve_log_path("processes", "p_deep_camera"),
        log_level="DEBUG",
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  | p_deep_camera | {process.name} | {thread.name} |  {name} : {module}:{function}:{line} | {message} </level>",
        enable_console=True
    )

    monitor.start_worker(
        target_func=main_deep_camera.main,
        restart_target_func=main_deep_camera.restart,
        args=(q, runtime_diagnostics_queue),
        name="p_deep_camera",
        auto_restart=True,
        log_config=p_deep_camera_config
    )

    p_infrared_camera_config = monitor.create_process_log_config(
        "p_infrared_camera",
        log_dir=resolve_log_path("processes", "p_infrared_camera"),
        log_level="DEBUG",
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | p_infrared_camera | {process.name} | {thread.name} |  {name} :  {module}:{function}:{line} | {message} </level> ",
        enable_console=True
    )
    monitor.start_worker(
        target_func=main_infrared_camera.main,
        restart_target_func=main_infrared_camera.restart,
        args=(q,),
        name="p_infrared_camera",
        auto_restart=True,
        log_config=p_infrared_camera_config
    )
    p_main_gui_config = monitor.create_process_log_config(
        "p_main_gui",
        log_dir=resolve_log_path("processes", "p_main_gui"),
        log_level="DEBUG",
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  | p_main_gui | {process.name} | {thread.name} |  {name} :  {module}:{function}:{line} | {message}  </level>",
        enable_console=True
    )
    monitor.start_worker(
        target_func=main_gui.main,
        args=(q, send_message_q, runtime_diagnostics_queue),
        name="p_main_gui",
        auto_restart=False,
        is_critical=True,  # 标记为关键进程
        log_config = p_main_gui_config
    )


    # 开始监控
    monitor.start_monitoring(interval=5)



if __name__ == "__main__" and os.path.basename(__file__) == "main.py":
    test_integrated_monitor()
