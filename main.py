import multiprocessing
import traceback
from multiprocessing import Process, freeze_support
import os
import subprocess
import sys
import time

import psutil
from loguru import logger

from Service import main_response_Modbus, main_gui

"""
确认子进程没有启动其他子进程，如果有，必须递归管理或用系统命令杀死整个进程树。
用 psutil 库递归杀死进程树
multiprocessing.Process.terminate() 只会终止对应的单个进程，如果该进程启动了其他进程，这些“子进程”不会被自动终止，因而可能会在任务管理器中残留。
"""
# 过滤日志
logger = logger.bind(category="main_logger")

def kill_process_tree(pid, including_parent=True):
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




if __name__ == "__main__" and os.path.basename(__file__) == "main.py":


    freeze_support()
    # 加载日志配置
    logger.add(
        "./log/main/main_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 日志文件转存
        retention="30 days",  # 多长时间之后清理
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}",
        filter = lambda record: record["extra"].get("category") == "main_logger"
    )
    logger.info(f"{'-' * 40}main_start{'-' * 40}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")

    q = multiprocessing.Queue()  # 创建 Queue 消息传递
    send_message_q = multiprocessing.Queue()  # 发送查询报文的消息传递单独一个通道

    p_response_comm = Process(target=main_response_Modbus.main, name="p_response_comm")


    p_gui = Process(target=main_gui.main, name="p_gui", args=(q, send_message_q))




    try:
        logger.info(f"p_response_comm子进程开始运行")
        p_response_comm.start()
    except Exception as e:
        logger.error(f"p_response_comm子进程发生异常：{e} |  异常堆栈跟踪：{traceback.print_exc()}，准备终止该子进程")
        if p_response_comm.is_alive():
            kill_process_tree(p_response_comm.pid)
            p_response_comm.join(timeout=5)
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

        # 检测 gui 进程是否存活
        if not p_gui.is_alive():
            logger.error(f"p_gui子进程已停止，同步终止p_comm子进程")

            if p_response_comm.is_alive():
                kill_process_tree(p_response_comm.pid)
                logger.error(f"终止p_response_comm子进程")
                p_response_comm.join(timeout=5)
                pass
            is_loop = False
            break
        time.sleep(0.5)

    # 等待所有子进程退出
    p_response_comm.join()
    p_gui.join()

else:
    pass
