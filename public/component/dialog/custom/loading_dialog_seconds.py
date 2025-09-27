import sys
from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QMainWindow, QProgressBar)
from PyQt6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QPixmap, QPainter, QPen


class AnimatedLoadingDialog(QDialog):
    def __init__(self, countdown_seconds=10, message="正在加载数据..."):
        super().__init__()
        self.countdown_seconds = countdown_seconds
        self.current_seconds = countdown_seconds
        self.message = message
        self.init_ui()
        self.start_countdown()
        self.start_progress_animation()

    def init_ui(self):
        self.setWindowTitle("加载中...")
        self.setFixedSize(400, 200)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
                border: 2px solid #007acc;
                border-radius: 10px;
            }
            QLabel {
                color: #333;
            }
            QProgressBar {
                border: 2px solid #007acc;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 3px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        self.title_label = QLabel("系统加载中")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        # 消息
        self.message_label = QLabel(self.message)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_font = QFont()
        message_font.setPointSize(10)
        self.message_label.setFont(message_font)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)

        # 倒计时和取消按钮的水平布局
        bottom_layout = QHBoxLayout()

        self.countdown_label = QLabel(f"剩余时间: {self.current_seconds}s")
        countdown_font = QFont()
        countdown_font.setPointSize(10)
        self.countdown_label.setFont(countdown_font)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setFixedSize(60, 30)
        self.cancel_button.clicked.connect(self.reject)

        bottom_layout.addWidget(self.countdown_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.cancel_button)

        # 添加所有控件到主布局
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)
        layout.addWidget(self.progress_bar)
        layout.addLayout(bottom_layout)

        self.setLayout(layout)
        self.center_on_screen()

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        dialog_geometry = self.frameGeometry()
        center_point = screen_geometry.center()
        dialog_geometry.moveCenter(center_point)
        self.move(dialog_geometry.topLeft())

    def start_countdown(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)

    def start_progress_animation(self):
        """启动进度条动画"""
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(100)  # 每100ms更新一次进度条

    def update_countdown(self):
        self.current_seconds -= 1
        self.countdown_label.setText(f"剩余时间: {self.current_seconds}s")

        # 根据剩余时间改变消息
        if self.current_seconds <= 3:
            self.message_label.setText("即将完成...")
        elif self.current_seconds <= 5:
            self.message_label.setText("正在处理最后步骤...")

        if self.current_seconds <= 0:
            self.timer.stop()
            self.progress_timer.stop()
            self.progress_bar.setValue(100)
            self.message_label.setText("加载完成！")

            # 延迟500ms后关闭对话框
            QTimer.singleShot(500, self.accept)

    def update_progress(self):
        """更新进度条"""
        elapsed_time = self.countdown_seconds - self.current_seconds
        progress = int((elapsed_time / self.countdown_seconds) * 100)
        self.progress_bar.setValue(min(progress, 100))