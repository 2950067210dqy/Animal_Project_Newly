import time
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QStatusBar, QLabel, QProgressBar

from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from public.entity.enum.Public_Enum import AppState
from public.util.time_util import time_util


class Time_thread(MyQThread):
    # 线程信号
    update_time_thread_doing = pyqtSignal()

    def __init__(self, update_time_main_signal):
        super(Time_thread, self).__init__(name="time_thread")
        # 获取主线程更新界面信号
        self.update_time_main_signal: pyqtSignal = update_time_main_signal
        pass

    def dosomething(self):
        # 不断获取系统时间

        # 实时获取当前时间（精确到微秒）
        current_time = datetime.now()

        # 转换为目标格式
        formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
        # 将时间发送信号到绑定槽函数
        self.update_time_main_signal.emit(formatted_time)
        time.sleep(1)
        # print(formatted_time)
        pass

    pass

class Start_Experiment_Time_thread(MyQThread ):
    # 线程信号
    update_time_thread_doing = pyqtSignal()

    def __init__(self, update_time_main_signal):
        super(Start_Experiment_Time_thread, self).__init__(name="Start_Experiment_Time_thread")
        # 获取主线程更新界面信号
        self.update_time_main_signal: pyqtSignal = update_time_main_signal
        pass

    def dosomething(self):
        # 不断获取系统时间
        start_time = global_setting.get_setting("start_experiment_time", time.time())
        pause_time = global_setting.get_setting("pause_experiment_time", [])
        relieve_pause_time = global_setting.get_setting("relieve_pause_experiment_time", [])
        if len(pause_time)==0 or len(relieve_pause_time)==0:
            delta_time_str = time_util.format_timedelta(a=datetime.now(),
                                                        b=datetime.fromtimestamp(
                                                            start_time))
        else:
            delta_time_str =time_util.operator_timedelta_str(
                time_util.format_timedelta(a=start_time,
                                           b=pause_time)

            )


        # 将时间发送信号到绑定槽函数
        self.update_time_main_signal.emit(delta_time_str)
        time.sleep(1)
        # print(formatted_time)
        pass

    pass

class CustomStatusBar(QStatusBar):
    # update_time的更新界面的主信号
    update_time_main_signal_gui_update = pyqtSignal(str)
    # 开始实验时间更新信号
    update_experiment_time_main_signal_gui_update = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        #添加时间label
        self.time_label = QLabel()
        self.time_label.setObjectName("time_label")
        self.addWidget(self.time_label)
        # 添加实验状态
        self.status_label = QLabel("未开始监测数据")
        self.status_label.setStyleSheet("QLabel { color: red; }")
        self.addWidget(self.status_label)
        # 添加 tip
        self.tip_label = QLabel("")
        self.addWidget(self.tip_label)

        # 添加 QProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.addPermanentWidget(self.progress_bar)  # 将进度条添加为永久小部件

        # 添加当前实验设置文件显示
        self.setting_file_name_label = QLabel("当前未存在实验文件")
        self.addWidget(self.setting_file_name_label)

        # 将更新时间信号绑定更新时间label界面函数
        self.update_time_main_signal_gui_update.connect(self.update_time_function_start_gui_update)
        # 启动子线程
        self.time_thread = Time_thread(update_time_main_signal=self.update_time_main_signal_gui_update)
        self.time_thread.start()
        self.start_Experiment_Time_thread=Start_Experiment_Time_thread(update_time_main_signal=self.update_experiment_time_main_signal_gui_update)


        self.update_experiment_time_main_signal_gui_update.connect(self.update_experiment_time_gui_update)

    def update_tip(self, message):
        self.tip_label.setText(message)
    def update_setting_file_name(self,message):
        self.setting_file_name_label.setText(message)
    def set_progress(self, value):
        self.progress_bar.setValue(value)

    def update_status(self,is_paused=False):
        if global_setting.get_setting("app_state",AppState.INITIALIZED)==AppState.MONITORING:
            if is_paused:
                self.start_Experiment_Time_thread.pause()
                self.status_label.setText("暂停中 "+self.status_label.text())
                self.status_label.setStyleSheet("QLabel { color: blue; }")
            else:

                self.status_label.setStyleSheet("QLabel { color:green; }")
                if self.start_Experiment_Time_thread.isPaused():
                    self.start_Experiment_Time_thread.resume()
                else:
                    self.status_label.setText(f"正在监测数据")
                    self.start_Experiment_Time_thread.start()
        else:
            self.start_Experiment_Time_thread.stop()
            self.status_label.setText("未开始监测数据")
            self.status_label.setStyleSheet("QLabel { color: red; }")

        # 更新时间功能 界面更新

    def update_experiment_time_gui_update(self, timeStr=""):

        self.status_label.setText(f"正在监测数据-已经监测 {timeStr}")
        self.status_label.setStyleSheet("QLabel { color:green; }")
        pass
    def update_time_function_start_gui_update(self, timeStr=""):
        #  获取控件
        # time_label: QLabel = self.findChild(QLabel, "time_label")
        # 设置文本
        self.time_label.setText(timeStr)
        pass