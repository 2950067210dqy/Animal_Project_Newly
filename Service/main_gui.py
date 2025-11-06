import os
import sys
import time
from multiprocessing import freeze_support
from PyQt6.QtCore import QThreadPool, QRect, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from blinker import signal
from loguru import logger
from index.MainWindow_index import MainWindow_Index
from index.Program_self_check import Program_self_check_index
from public.component.dialog.index.deep_camera_config_dialog_index import deep_camera_config_dialog
from public.component.dialog.index.infrared_camera_config_dialog_index import infrared_camera_config_dialog

from public.config_class import global_load
from public.config_class.global_setting import global_setting
from public.config_class.ini_parser import ini_parser
from public.entity.MyQThread import MyThread, MyQThread
from public.entity.enum.Public_Enum import AppState
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Crash_handle.CrashHandle import CrashHandler
from public.function.Modbus.New_Mod_Bus import ModbusRTUMasterNew
from theme.ThemeManager import ThemeManager
# 过滤日志
#logger = logger.bind(category="gui_logger")


infrared_camera_config_dialog_obj =None
deep_camera_config_dialog_obj =None
class read_queue_data_Thread(MyQThread):
    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.camera_list = None
        pass

    def dosomething(self):
        if not self.queue.empty():
            try:
                message: ObjectQueueItem = self.queue.get()
            except Exception as e:
                logger.error(f"{self.name}发生错误{e}")
                return
            if message is not None and message.is_Empty():
                return
            if message is not None and isinstance(message, ObjectQueueItem) and message.to=='main_gui':
                logger.error(f"{self.name}_get_message:{message}")
                match message.title:
                    case "deep_camera_config_dialog":
                        QTimer.singleShot(200,self.show_deep_camera_config_dialog)

                        pass
                    case "infrared_camera_config_dialog":
                        QTimer.singleShot(100, self.show_infrared_camera_config_dialog)
                        pass
                    case _:
                        pass

            else:
                # 把消息放回去
                self.queue.put(message)

    def show_infrared_camera_config_dialog(self):
        global infrared_camera_config_dialog_obj
        infrared_camera_config_dialog_obj = infrared_camera_config_dialog(title="红外相机配置")
        # dialog_frame.camera_config_finished_signal.connect(init_camera_and_image_handle_thread)
        infrared_camera_config_dialog_obj.show_frame()
        pass

    def show_deep_camera_config_dialog(self):
        global deep_camera_config_dialog_obj
        deep_camera_config_dialog_obj = deep_camera_config_dialog(title="深度相机配置")
        # dialog_frame.camera_config_finished_signal.connect(init_camera_and_image_handle_thread)
        deep_camera_config_dialog_obj.show_frame()
        pass

        pass


read_queue_data_thread = read_queue_data_Thread(name="main_gui_read_queue_data_thread")
def quit_qt_application():
    """
    退出QT程序
    :return:
    """
    logger.error(f"{'-' * 40}quit Qt application{'-' * 40}")
    modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
    if modbus is not None:
        logger.error("stop_modbus_close_application")
        modbus.close()

    #
    # 等待5秒系统退出

    step = 5
    while step >= 0:
        step -= 1
        time.sleep(1)
    sys.exit(0)

def on_crash( error_msg):
    """处理崩溃事件"""
    logger.critical(f"Crash detected: {error_msg}...")
    modbus: ModbusRTUMasterNew = global_setting.get_setting("modbus", None)
    if modbus is not None:
        logger.error("stop_modbus_crash_application")
        modbus.close()

    # 显示崩溃对话框

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle("程序崩溃")
    msg_box.setText("程序发生了意外错误")
    msg_box.setDetailedText(error_msg)
    msg_box.setStandardButtons(
        QMessageBox.StandardButton.Ok |
        QMessageBox.StandardButton.Close
    )

    result = msg_box.exec()

    if result == QMessageBox.StandardButton.Close:
        logger.info("User chose to close application after crash")
        QApplication.quit()
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
    # 程序崩溃闪退监听
    crash_handler = CrashHandler()
    crash_handler.crash_signal.connect(on_crash)

    program_self_check_index_dialog = Program_self_check_index()
    program_self_check_index_dialog.activateWindow()
    return_Data = program_self_check_index_dialog.exec()
    if return_Data ==QDialog.DialogCode.Accepted:
        #点了确认
        # # 主窗口实例化

        main_window=MainWindow_Index()

        # 主窗口显示
        logger.info("Appliacation start")

        main_window.show_frame()
    # 系统退出
    sys.exit(app.exec())
    pass


def main(q, send_message_q):
    freeze_support()

    # logger.remove(0)
    # logger.add(
    #     "./log/gui/gui_{time:YYYY-MM-DD}.log",
    #     rotation="00:00",  # 日志文件转存
    #     retention="30 days",  # 多长时间之后清理
    #     enqueue=True,
    #     format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}",
    #
    # )
    logger.info(f"{'-' * 40}main_gui_start{'-' * 40}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")
    global_load.load_global_setting()
    global_setting.set_setting("queue", q)
    global_setting.set_setting("send_message_queue", send_message_q)
    global read_queue_data_thread
    read_queue_data_thread.queue = q
    read_queue_data_thread.start()

    # qt程序开始
    start_qt_application()
