import os
import sys
import time
from multiprocessing import freeze_support
from PyQt6.QtCore import QThreadPool, QRect
from PyQt6.QtWidgets import QApplication, QDialog
from loguru import logger
from index.MainWindow_index import MainWindow_Index
from index.Program_self_check import Program_self_check_index
from public.config_class import global_load
from public.config_class.global_setting import global_setting
from public.config_class.ini_parser import ini_parser
from public.entity.enum.Public_Enum import AppState
from public.function.Modbus.New_Mod_Bus import ModbusRTUMasterNew
from theme.ThemeManager import ThemeManager
# 过滤日志
#logger = logger.bind(category="gui_logger")
def quit_qt_application():
    """
    退出QT程序
    :return:
    """
    logger.error(f"{'-' * 40}quit Qt application{'-' * 40}")
    modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
    if modbus is not None:
        modbus.close()

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


def main(q, send_message_q):
    freeze_support()

    # logger.remove(0)
    logger.add(
        "./log/gui/gui_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # 日志文件转存
        retention="30 days",  # 多长时间之后清理
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}",
      
    )
    logger.info(f"{'-' * 40}main_gui_start{'-' * 40}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")
    global_load.load_global_setting()
    global_setting.set_setting("queue", q)
    global_setting.set_setting("send_message_queue", send_message_q)
    try:
        # qt程序开始
        start_qt_application()
    except Exception as e:
        logger.error(e)