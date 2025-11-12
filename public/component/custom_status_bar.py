import time
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QStatusBar, QLabel, QProgressBar, QPushButton

from public.component.list_view.Custom_List_view import CustomListView
from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from public.entity.enum.Public_Enum import AppState
from public.util.time_util import time_util


class Time_thread(MyQThread):


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

    def __init__(self, update_time_main_signal,is_paused_experiment=False):
        super(Start_Experiment_Time_thread, self).__init__(name="Start_Experiment_Time_thread")
        # 获取主线程更新界面信号
        self.update_time_main_signal: pyqtSignal = update_time_main_signal
        self.is_paused_experiment=is_paused_experiment
        pass

    def dosomething(self):
        # 不断获取系统时间
        start_time = global_setting.get_setting("start_experiment_time", time.time())
        pause_time = global_setting.get_setting("pause_experiment_time", [])
        relieve_pause_time = global_setting.get_setting("relieve_pause_experiment_time", [])
        delta_time_str = ""
        if self.is_paused_experiment:
            # 暂停计算暂停时间
            if len(pause_time) > 0:
                delta_time_str =time_util.format_timedelta(a=datetime.now(),
                                                            b=datetime.fromtimestamp(
                                                                pause_time[len(pause_time) - 1]))
            pass
        else:
            # 计算运行时间
            if len(pause_time) == 0 or len(relieve_pause_time) == 0:
                # 没暂停过
                # 直接计算现在时间与开始实验时间之差
                delta_time_str = time_util.format_timedelta(a=datetime.now(),
                                                            b=datetime.fromtimestamp(
                                                                start_time))
            else:
                #暂停过
                for i in range(len(pause_time)):
                    if i==0:
                        delta_time_str =time_util.operator_timedelta_str(
                            a=delta_time_str,
                            b=time_util.format_timedelta(a=datetime.fromtimestamp(pause_time[i]),
                                                            b=datetime.fromtimestamp(
                                                                start_time)),
                            operator="+"

                        )
                    else:
                        delta_time_str = time_util.operator_timedelta_str(
                            a=delta_time_str,
                            b=time_util.format_timedelta(a=datetime.fromtimestamp(pause_time[i]),
                                                         b=datetime.fromtimestamp(
                                                             relieve_pause_time[i-1])),
                            operator="+"

                        )
                delta_time_str = time_util.operator_timedelta_str(
                    a=delta_time_str,
                    b=time_util.format_timedelta(a=datetime.now(),
                                                 b=datetime.fromtimestamp(
                                                     relieve_pause_time[len(relieve_pause_time) - 1])),
                    operator="+"

                )
                pass
            pass

        delta_time_dict={
            "is_paused":self.is_paused_experiment,
            "text":delta_time_str,

        }
        # 将时间发送信号到绑定槽函数
        self.update_time_main_signal.emit(delta_time_dict)
        time.sleep(1)
        # print(formatted_time)
        pass

    pass

class CustomStatusBar(QStatusBar):
    # update_time的更新界面的主信号
    update_time_main_signal_gui_update = pyqtSignal(str)
    # 开始实验时间更新信号
    update_experiment_time_main_signal_gui_update = pyqtSignal(dict)
    def __init__(self,main_gui,is_main=True):
        super().__init__()
        self.main_gui = main_gui
        if is_main:
            #添加时间label
            self.time_label = QLabel()
            self.time_label.setObjectName("time_label")
            self.addWidget(self.time_label)

            #程序状态
            self.app_status_label = QLabel("INITIALIZED")
            self.app_status_label.setObjectName("app_status_label")
            self.addWidget(self.app_status_label)
            # 添加实验状态
            self.status_label = QLabel("未开始监测数据")
            self.status_label.setStyleSheet("QLabel { color: red; }")
            self.addWidget(self.status_label)
        # 添加 tip
        self.tip_label =None
        # self.addWidget(self.tip_label)
        if is_main:

            # 添加当前实验设置文件显示
            self.setting_file_name_label = QLabel("当前未存在实验文件")
            self.addWidget(self.setting_file_name_label)

            # 添加 QProgressBar
            self.progress_bar = QProgressBar()
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            # self.addWidget(self.progress_bar)  # 将进度条添加为永久小部件

        self.tip_btn = QPushButton("教程帮助")
        self.tip_btn.setStyleSheet("QPushButton { font-weight:bolder; font-size: 15px;padding: 5px; }")
        self.tip_btn.clicked.connect(self.main_gui.restart_tutorial)

        self.addPermanentWidget(self.tip_btn)
        if is_main:
            # 将更新时间信号绑定更新时间label界面函数
            self.update_time_main_signal_gui_update.connect(self.update_time_function_start_gui_update)
            # 启动子线程
            self.time_thread = Time_thread(update_time_main_signal=self.update_time_main_signal_gui_update)
            self.time_thread.start()
            self.start_Experiment_Time_thread=Start_Experiment_Time_thread(update_time_main_signal=self.update_experiment_time_main_signal_gui_update)


            self.update_experiment_time_main_signal_gui_update.connect(self.update_experiment_time_gui_update)

    def update_tip(self, message):
        if self.tip_label is None:
            self.tip_label = CustomListView()
            self.addWidget(self.tip_label)
        self.tip_label.insert_data(message)
    def update_setting_file_name(self,message):
        self.setting_file_name_label.setText(message)
    def set_progress(self, value):
        self.progress_bar.setValue(value)
    def update_app_state(self):
        app_state = global_setting.get_setting("app_state",AppState.INITIALIZED)
        match app_state:
            case AppState.INITIALIZED:
                self.app_status_label.setText("INITIALIZED")
            case AppState.APPLYING:
                self.app_status_label.setText("APPLYING")
            case AppState.CONFIGURING:
                self.app_status_label.setText("CONFIGURING")
            case AppState.MONITORING:
                self.app_status_label.setText("MONITORING")
            case _:
                self.app_status_label.setText("UNKNOWN")
    def update_status(self,is_paused=False):
        if global_setting.get_setting("app_state",AppState.INITIALIZED)==AppState.MONITORING:
            if not self.start_Experiment_Time_thread.isStart():
                self.start_Experiment_Time_thread.start()
            if is_paused:
                self.start_Experiment_Time_thread.is_paused_experiment =True
            else:
                self.start_Experiment_Time_thread.is_paused_experiment=False
        else:
            self.start_Experiment_Time_thread.stop()

            self.status_label.setText("未开始监测数据")
            self.status_label.setStyleSheet("QLabel { color: red; }")

     # 更新时间功能 界面更新
    def update_experiment_time_gui_update(self, timeDict={"is_paused":False, "text":""}):
        if timeDict['is_paused']:
            self.status_label.setText(f"实验开始时间{time_util.get_format_from_time(global_setting.get_setting('start_experiment_time',time.time()))}-暂停监测数据-已经暂停监测 {timeDict['text']}")
            self.status_label.setStyleSheet("QLabel { color:blue; }")
        else:
            self.status_label.setText(f"实验开始时间{time_util.get_format_from_time(global_setting.get_setting('start_experiment_time',time.time()))}-正在监测数据-已经监测 {timeDict['text']}")
            self.status_label.setStyleSheet("QLabel { color:green; }")
            pass
        pass
    def update_time_function_start_gui_update(self, timeStr=""):
        #  获取控件
        # time_label: QLabel = self.findChild(QLabel, "time_label")
        # 设置文本
        self.time_label.setText(timeStr)
        pass