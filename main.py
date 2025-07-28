import os
import sys
import time
from multiprocessing import freeze_support

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication
from loguru import logger

from config_class.global_setting import global_setting
from config_class.ini_parser import ini_parser
from index.MainWindow_index import MainWindow_Index
from theme.ThemeManager import ThemeManager


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
    screen_rect = screen.availableGeometry()
    global_setting.set_setting("screen", screen_rect)
    # 绑定突出事件
    app.aboutToQuit.connect(quit_qt_application)
    # 主窗口实例化
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
    # 加载相机配置
    config_file_path = os.getcwd() +config_path+ "/gui_config.ini"

    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("gui配置文件读取成功。")
    else:
        logger.error("gui配置文件读取失败。")
        quit_qt_application()
    global_setting.set_setting("gui_config", config)

    # 风格默认是dark  light
    global_setting.set_setting("style", config['theme']['default'])
    # 图标风格 white black
    global_setting.set_setting("icon_style", "white")
    # 主题管理
    theme_manager = ThemeManager()
    global_setting.set_setting("theme_manager", theme_manager)
    # qt线程池
    thread_pool = QThreadPool()
    global_setting.set_setting("thread_pool", thread_pool)

    pass
if __name__ == "__main__" and os.path.basename(__file__) == "main.py":
    freeze_support()
    # 加载日志配置
    logger.add(
        "./log/main/main_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 日志文件转存
        retention="30 days",  # 多长时间之后清理
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}"
    )
    logger.info(f"{'-' * 40}main_start{'-' * 40}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")

    load_global_setting()
    # qt程序开始
    start_qt_application()