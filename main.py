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
    logger.error(f"💥 进程崩溃: {process_id} {critical_info}")
    logger.error(f"   退出码: {kwargs.get('exitcode')}")
    logger.error(f"   运行时间: {kwargs.get('runtime', 0)}")
    if kwargs.get('error_info'):
        logger.error(f"   错误信息: {kwargs.get('error_info')}")

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
    logger.warning(f"😵 进程无响应: {process_id} {critical_info}")
    logger.warning(f"   心跳超时: {kwargs.get('heartbeat_age', 0)}")

def on_high_cpu(process_id, **kwargs):
    logger.warning(f"🔥 CPU使用率过高: {process_id}")
    logger.warning(f"   当前: {kwargs.get('cpu_percent', 0):.1f}%")
    logger.warning(f"   阈值: {kwargs.get('threshold', 0):.1f}%")

def on_high_memory(process_id, **kwargs):
    logger.warning(f"🧠 内存使用过高: {process_id}")
    logger.warning(f"   当前: {kwargs.get('memory_mb', 0):.1f}MB")
    logger.warning(f"   阈值: {kwargs.get('threshold', 0):.1f}MB")

def on_critical_failure(process_id, **kwargs):
    logger.critical(f"🚨 关键进程失败: {process_id}")
    logger.critical(f"   退出码: {kwargs.get('exitcode')}")
    logger.critical("   系统将关闭所有其他进程")

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
def main():
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
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}",

    )

    logger.info(f"{'-' * 40}main_start{'-' * 40}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")
    q = multiprocessing.Queue()  # 创建 Queue 消息传递
    send_message_q = multiprocessing.Queue()  # 发送查询报文的消息传递单独一个通道
    # j= json.dumps(ObjectQueueItem(to="123",
    #                 data=f"{time_util.get_format_from_time(time.time())}",
    #                 origin='main_monitor_data'))
    p_response_comm = Process(target=main_response_Modbus.main, name="p_response_comm")

    p_gui = Process(target=main_gui.main, name="p_gui", args=(q, send_message_q))
    p_monitor_data = Process(target=main_monitor_data.main, name="p_monitor_data", args=(q, send_message_q))
    p_deep_camera = Process(target=main_deep_camera.main, name="p_deep_camera", args=(q,))
    p_infrared_camera = Process(target=main_infrared_camera.main, name="p_infrared_camera", args=(q,))
    try:
        logger.info(f"p_response_comm子进程开始运行")
        p_response_comm.start()
    except Exception as e:
        logger.error(f"p_response_comm子进程发生异常：{e} |  异常堆栈跟踪：{traceback.print_exc()}，准备终止该子进程")
        if p_response_comm.is_alive():
            kill_process_tree(p_response_comm.pid)
            p_response_comm.join(timeout=5)

    try:
        logger.info(f"p_monitor_data子进程开始运行")
        p_monitor_data.start()
    except Exception as e:
        logger.error(f"p_monitor_data子进程发生异常：{e} |  异常堆栈跟踪：{traceback.print_exc()}，准备终止该子进程")
        if p_monitor_data.is_alive():
            kill_process_tree(p_monitor_data.pid)
            p_monitor_data.join(timeout=5)
    try:
        logger.info(f"p_deep_camera子进程开始运行")
        p_deep_camera.start()
    except Exception as e:
        logger.error(f"p_deep_camera子进程发生异常：{e} |  异常堆栈跟踪：{traceback.print_exc()}，准备终止该子进程")
        if p_deep_camera.is_alive():
            kill_process_tree(p_deep_camera.pid)
            p_deep_camera.join(timeout=5)
    try:
        logger.info(f"p_infrared_camera子进程开始运行")
        p_infrared_camera.start()
    except Exception as e:
        logger.error(f"p_infrared_camera子进程发生异常：{e} |  异常堆栈跟踪：{traceback.print_exc()}，准备终止该子进程")
        if p_infrared_camera.is_alive():
            kill_process_tree(p_infrared_camera.pid)
            p_infrared_camera.join(timeout=5)
    try:
        logger.info(f"p_gui子进程开始运行")
        p_gui.start()
    except Exception as e:
        logger.error(f"p_gui子进程发生异常：{e} |  异常堆栈跟踪：{traceback.print_exc()}，准备终止该子进程")
        if p_gui.is_alive():
            kill_process_tree(p_gui.pid)
            p_gui.join(timeout=5)
    # 如果gui进程死亡 则将其他的进程全部终止
    is_loop = True
    while is_loop:
        # 检测 monitor_data进程是否存活
        if not p_monitor_data.is_alive():
            logger.error("p_monitor_data进程已停止！")
        # 检测 deep_camera进程是否存货
        if not p_deep_camera.is_alive():
            logger.error("p_deep_camera进程已停止！")
        # 检测 infrared_camera 进程是否存活
        if not p_infrared_camera.is_alive():
            logger.error("p_infrared_camera进程已停止！")
        # 检测 gui 进程是否存活
        if not p_gui.is_alive():
            logger.error(f"p_gui子进程已停止，同步终止子进程")

            if p_deep_camera.is_alive():
                kill_process_tree(p_deep_camera.pid)
                logger.error(f"终止p_deep_camera子进程")
                p_deep_camera.join(timeout=5)
                p_deep_camera.kill()
                pass
            else:
                kill_process_tree(p_deep_camera.pid)
                logger.error(f"p_deep_camera子进程已经不存活")
            if p_infrared_camera.is_alive():
                kill_process_tree(p_infrared_camera.pid)
                logger.error(f"终止p_infrared_camera子进程")
                p_infrared_camera.join(timeout=5)
                p_infrared_camera.kill()
                pass
            else:
                kill_process_tree(p_infrared_camera.pid)
                logger.error(f"p_infrared_camera子进程已经不存活")
            if p_response_comm.is_alive():
                kill_process_tree(p_infrared_camera.pid)
                logger.error(f"终止p_response_comm子进程")
                p_response_comm.join(timeout=5)
                p_response_comm.kill()
                pass
            else:
                kill_process_tree(p_infrared_camera.pid)
                logger.error(f"p_response_comm子进程已经不存活")
            if p_monitor_data.is_alive():
                kill_process_tree(p_monitor_data.pid)
                logger.error(f"终止p_monitor_data子进程")
                p_monitor_data.join(timeout=5)
                p_deep_camera.kill()
                pass
            else:
                kill_process_tree(p_monitor_data.pid)
                logger.error(f"p_monitor_data子进程已经不存活")
            is_loop = False
            break
        time.sleep(0.5)
    # 等待所有子进程退出
    p_response_comm.join()
    p_deep_camera.join()
    p_infrared_camera.join()
    p_monitor_data.join()
    p_gui.join()


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
        log_level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  | MAIN | {module}:{function}:{line} | {message} </level>",
        enable_console=True,
        console_level="INFO"
    )
    # 创建自定义的异常日志配置
    exception_config = LogConfig(
        log_dir="./log/exceptions",
        log_level="ERROR",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | EXCEPTION | {module}:{function}:{line} | {message} </level>",
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

    # 创建工作进程的日志配置
    p_response_comm_config = monitor.create_process_log_config(
        "p_response_comm",
        # log_level="DEBUG",
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
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | p_monitor_data | {module}:{function}:{line} | {message} </level> ",
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
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  | p_deep_camera | {module}:{function}:{line} | {message} </level>",
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
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level} | p_infrared_camera | {module}:{function}:{line} | {message} </level> ",
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
        custom_format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}  | p_main_gui | {module}:{function}:{line} | {message}  </level>",
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