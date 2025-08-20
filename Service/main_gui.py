import os
import sys
import time
from multiprocessing import freeze_support
from PyQt6.QtCore import QThreadPool, QRect
from PyQt6.QtWidgets import QApplication, QDialog
from loguru import logger
from index.MainWindow_index import MainWindow_Index
from index.Program_self_check import Program_self_check_index
from public.config_class.global_setting import global_setting
from public.config_class.ini_parser import ini_parser
from public.entity.enum.Public_Enum import AppState
from theme.ThemeManager import ThemeManager
# 过滤日志
logger = logger.bind(category="gui_logger")
def quit_qt_application():
    """
    退出QT程序
    :return:
    """
    logger.error(f"{'-' * 40}quit Qt application{'-' * 40}")
    #
    # 等待5秒系统退出
    step = 5
    while step >= 0:
        step -= 1
        time.sleep(1)
    sys.exit(0)
def start_qt_application():
    """
    qt程序开始
    :return: 无
    """
    # 启动qt
    logger.info("start Qt")
    app = QApplication(sys.argv)
    # 屏幕大小
    # 获取屏幕大小
    screen = app.primaryScreen()

    screen_rect :QRect= screen.availableGeometry()
    screen_rect.setHeight(screen_rect.height()-30)
    global_setting.set_setting("screen", screen_rect)
    # 绑定突出事件
    app.aboutToQuit.connect(quit_qt_application)
    program_self_check_index_dialog = Program_self_check_index()
    return_Data = program_self_check_index_dialog.exec()
    if return_Data ==QDialog.DialogCode.Accepted:
        #点了确认
        # # 主窗口实例化
        try:
            main_window=MainWindow_Index()
        except Exception as e:
            logger.error(f"gui程序实例化失败，原因:{e} ")
            return
        # 主窗口显示
        logger.info("Appliacation start")

        main_window.show_frame()
    # 系统退出
    sys.exit(app.exec())
    pass
def load_global_setting():
    config_path = "/config"
    # 加载配置
    config_file_path = os.getcwd() +config_path+ "/gui_config.ini"
    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    configer = ini_parser(config_file_path).read()
    if (len(configer) != 0):
        logger.info("gui配置文件读取成功。")
    else:
        logger.error("gui配置文件读取失败。")
        quit_qt_application()
    global_setting.set_setting("configer", configer)
    # 加载相机配置
    config_file_path = os.getcwd() +config_path+ "/camera_config.ini"
    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("相机配置文件读取成功。")
    else:
        logger.error("相机配置文件读取失败。")
    global_setting.set_setting("camera_config", config)
    # 加载监控数据配置
    config_file_path = os.getcwd() +config_path+ "/monitor_datas_config.ini"
    # 配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("监控配置文件读取成功。")
    else:
        logger.error("监控配置文件读取失败。")
    global_setting.set_setting("monitor_data", config)
    # 风格默认是dark  light
    global_setting.set_setting("style", configer['theme']['default'])
    # 图标风格 white black
    global_setting.set_setting("icon_style", "white")
    # 主题管理
    theme_manager = ThemeManager()
    global_setting.set_setting("theme_manager", theme_manager)
    # qt线程池
    thread_pool = QThreadPool()
    global_setting.set_setting("thread_pool", thread_pool)
    #程序状态
    global_setting.set_setting("app_state", AppState.INITIALIZED)
    pass

def main(q, send_message_q):
    freeze_support()
    # 加载日志配置
    logger.add(
        "./log/gui/gui_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 日志文件转存
        retention="30 days",  # 多长时间之后清理
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}",
        filter = lambda record: record["extra"].get("category") == "gui_logger"
    )
    logger.info(f"{'-' * 40}main_gui_start{'-' * 40}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")
    load_global_setting()
    global_setting.set_setting("queue", q)
    global_setting.set_setting("send_message_queue", send_message_q)
    try:
        # qt程序开始
        start_qt_application()
    except Exception as e:
        logger.error(e)