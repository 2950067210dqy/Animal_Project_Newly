from PyQt6.QtWidgets import QStatusBar, QLabel, QProgressBar

from public.config_class.global_setting import global_setting


class CustomStatusBar(QStatusBar):
    def __init__(self):
        super().__init__()

        # 添加实验状态
        self.status_label = QLabel("未开始监测数据")
        self.status_label.setStyleSheet("QLabel { color: red; }")
        self.addWidget(self.status_label)
        # 添加 tip
        self.tip_label = QLabel("Ready")
        self.addWidget(self.tip_label)

        # 添加 QProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.addPermanentWidget(self.progress_bar)  # 将进度条添加为永久小部件

    def update_tip(self, message):
        self.tip_label.setText(message)

    def set_progress(self, value):
        self.progress_bar.setValue(value)

    def update_status(self):
        status = global_setting.get_setting("experiment",False)
        if status:
            self.status_label.setText("正在监测数据")
            self.status_label.setStyleSheet("QLabel { color:green; }")
        else:
            self.status_label.setText("未开始监测数据")
            self.status_label.setStyleSheet("QLabel { color: red; }")