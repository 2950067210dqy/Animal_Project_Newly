import json
import multiprocessing
import sys
import traceback
from datetime import datetime
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
# ===================== 回调函数示例 =====================

def on_process_start(process_id, **kwargs):
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    logger.info(f"🎬 进程启动: {process_id} (PID: {kwargs.get('pid')}) {critical_info}")

def on_process_crash(process_id, **kwargs):
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
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    logger.info(f"✅ 进程完成: {process_id} {critical_info} (运行时间: {kwargs.get('runtime', 0)})")

def on_process_restart(process_id, **kwargs):
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    logger.info(f"🔄 进程重启: {process_id} {critical_info}")
    logger.info(f"   新PID: {kwargs.get('new_pid')}")
    logger.info(f"   重启次数: {kwargs.get('restart_count')}")

def on_process_timeout(process_id, **kwargs):
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    logger.warning(f"⏰ 进程超时: {process_id} {critical_info}")
    logger.warning(f"   超时限制: {kwargs.get('timeout')}秒")
    logger.warning(f"   实际运行: {kwargs.get('runtime', 0)}")

def on_process_unresponsive(process_id, **kwargs):
    critical_info = "【关键进程】" if kwargs.get('is_critical') else "【普通进程】"
    error_msg = f"""😵 进程无响应: {process_id} {critical_info}
       心跳超时: {kwargs.get('heartbeat_age', 0)}"""
    logger.warning(
        error_msg
    )
    # main_gui.on_crash(error_msg)
def on_high_cpu(process_id, **kwargs):
    logger.warning(f"🔥 CPU使用率过高: {process_id}")
    logger.warning(f"   当前: {kwargs.get('cpu_percent', 0):.1f}%")
    logger.warning(f"   阈值: {kwargs.get('threshold', 0):.1f}%")

def on_high_memory(process_id, **kwargs):
    logger.warning(f"🧠 内存使用过高: {process_id}")
    logger.warning(f"   当前: {kwargs.get('memory_mb', 0):.1f}MB")
    logger.warning(f"   阈值: {kwargs.get('threshold', 0):.1f}MB")

def on_critical_failure(process_id, **kwargs):
    error_msg = f"""🚨 关键进程失败: {process_id}
       退出码: {kwargs.get('exitcode')}
       系统将关闭所有其他进程"""
    logger.critical(
        error_msg
    )
    # main_gui.on_crash(error_msg)
def on_shutdown_triggered(process_id, **kwargs):
    failed_processes = kwargs.get('failed_processes', [])
    logger.critical(f"🛑 触发系统关闭，原因: 关键进程失败 {failed_processes}")
    logger.critical("   正在关闭所有进程...")
 # 注册异常回调
def on_any_exception(exception_info):
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
    # 加载日志配置
    # 移除默认处理器
    # logger.remove()

    logger.add(
        "./log/main/main_{time:YYYY-MM-DD}.log",
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
        log_dir="./log/main",
        log_level="DEBUG",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} |{process.name} | {thread.name} |  {name} :  {module}:{function}:{line} | {message} </level>",
        enable_console=True,
        console_level="DEBUG"
    )
    # 创建自定义的异常日志配置
    exception_config = LogConfig(
        log_dir="./log/exceptions",
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
    monitor.register_exception_callback(on_any_exception)

    # 创建工作进程的日志配置 调试专用 记得注释
    p_response_comm_config = monitor.create_process_log_config(
        "p_response_comm",
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
        log_level="DEBUG",
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  | p_deep_camera | {process.name} | {thread.name} |  {name} : {module}:{function}:{line} | {message} </level>",
        enable_console=True
    )

    monitor.start_worker(
        target_func=main_deep_camera.main,
        restart_target_func=main_deep_camera.restart,
        args=(q,),
        name="p_deep_camera",
        auto_restart=True,
        log_config=p_deep_camera_config
    )

    p_infrared_camera_config = monitor.create_process_log_config(
        "p_infrared_camera",
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
        log_level="DEBUG",
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  | p_main_gui | {process.name} | {thread.name} |  {name} :  {module}:{function}:{line} | {message}  </level>",
        enable_console=True
    )
    monitor.start_worker(
        target_func=main_gui.main,
        args=(q,send_message_q),
        name="p_main_gui",
        auto_restart=False,
        is_critical=True,  # 标记为关键进程
        log_config = p_main_gui_config
    )


    # 开始监控
    monitor.start_monitoring(interval=5)



if __name__ == "__main__" and os.path.basename(__file__) == "main.py":
    test_integrated_monitor()