import sys
from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QProgressBar, QPushButton, QListView, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QStandardItemModel, QStandardItem
from loguru import logger


class AnimatedLoadingDialog(QDialog):
    insert_data_signal=pyqtSignal(str)
    def __init__(self, countdown_seconds=10, message="正在加载数据...", title="系统加载中", show_listview=True):
        super().__init__()
        self.countdown_seconds = countdown_seconds
        self.current_seconds = countdown_seconds
        self.message = message
        self.title = title
        self.show_listview = show_listview

        # 进度条相关属性
        self.manual_progress = 0
        self.progress_max = 100
        self.use_manual_progress = False  # 是否使用手动进度控制
        self.task_completed = False  # 任务是否完成标志

        self.init_ui()
        self.init_listview()
        self.start_countdown()
        if not self.use_manual_progress:
            self.start_progress_animation()
        self.insert_data_signal.connect(self.insert_list_data)

    def init_ui(self):
        self.setWindowTitle(self.title)
        # 根据是否显示listview调整窗口大小
        if self.show_listview:
            self.setFixedSize(700, 500)
        else:
            self.setFixedSize(400, 200)

        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
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
            QListView {
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: white;
                selection-background-color: #007acc;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        self.title_label = QLabel(self.title)
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

        # 添加基本控件到布局
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)
        layout.addWidget(self.progress_bar)

        # QListView（可控制显示/隐藏）
        self.list_view = QListView()
        self.list_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        if self.show_listview:
            layout.addWidget(self.list_view)
        else:
            self.list_view.hide()

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

        # 添加底部布局
        layout.addLayout(bottom_layout)

        self.setLayout(layout)
        self.center_on_screen()

    def init_listview(self):
        """初始化ListView的数据模型"""
        self.list_model = QStandardItemModel()
        self.list_view.setModel(self.list_model)

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
        """启动进度条动画（基于倒计时）"""
        if not self.use_manual_progress:
            self.progress_timer = QTimer()
            self.progress_timer.timeout.connect(self.update_progress)
            self.progress_timer.start(100)  # 每100ms更新一次进度条

    def update_countdown(self):
        self.current_seconds -= 1
        self.countdown_label.setText(f"剩余时间: {self.current_seconds}s")

        # 如果使用手动进度控制，检查任务是否完成
        if self.use_manual_progress and not self.task_completed:
            # 根据剩余时间改变消息（但不影响手动任务）
            if self.current_seconds <= 3:
                if not self.task_completed:
                    pass  # 保持当前消息，不覆盖任务状态消息
            elif self.current_seconds <= 5:
                if not self.task_completed:
                    pass  # 保持当前消息，不覆盖任务状态消息
        else:
            # 自动模式下的消息更新
            if self.current_seconds <= 3:
                self.message_label.setText("即将完成...")
            elif self.current_seconds <= 5:
                self.message_label.setText("正在处理最后步骤...")

        if self.current_seconds <= 0:
            self.timer.stop()
            if hasattr(self, 'progress_timer'):
                self.progress_timer.stop()

            # 检查是否使用手动进度控制且任务未完成
            if self.use_manual_progress and not self.task_completed:
                self.show_timeout_error()
            else:
                # 正常完成
                self.progress_bar.setValue(100)
                self.message_label.setText("加载完成！")
                # 延迟500ms后关闭对话框
                QTimer.singleShot(500, self.accept)

    def update_progress(self):
        """更新进度条（基于倒计时）"""
        if not self.use_manual_progress:
            elapsed_time = self.countdown_seconds - self.current_seconds
            progress = int((elapsed_time / self.countdown_seconds) * 100)
            self.progress_bar.setValue(min(progress, 100))

    def show_timeout_error(self):
        """显示超时错误弹窗"""

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("任务超时")
        msg_box.setText("任务执行超时！")
        msg_box.setInformativeText("任务未能在规定时间内完成，请检查网络连接或重试。")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)

        # 设置弹窗样式
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #f0f0f0;
            }
            QMessageBox QLabel {
                color: #333;
            }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)

        # 显示弹窗并等待用户点击
        result = msg_box.exec()
        if result == QMessageBox.StandardButton.Ok:
            self.reject()  # 关闭主窗口

    # ==================== QListView 相关接口 ====================

    def show_listview(self):
        """显示QListView"""
        if not self.show_listview:
            self.show_listview = True
            self.list_view.show()
            self.layout().addWidget(self.list_view)
            self.setFixedSize(500, 400)
            self.center_on_screen()

    def hide_listview(self):
        """隐藏QListView"""
        if self.show_listview:
            self.show_listview = False
            self.list_view.hide()
            self.layout().removeWidget(self.list_view)
            self.setFixedSize(400, 200)
            self.center_on_screen()

    def insert_list_data(self, data):
        """
        插入数据到QListView最前面

        Args:
            data (str): 要插入的数据
        """
        if isinstance(data, str):
            item = QStandardItem(data)
        else:
            item = QStandardItem(str(data))

        # 插入到第一行（索引0）
        self.list_model.insertRow(0, item)

        # 滚动到顶部显示新添加的数据
        self.list_view.scrollToTop()

    def insert_multiple_list_data(self, data_list):
        """
        批量插入多个数据到QListView

        Args:
            data_list (list): 要插入的数据列表
        """
        for data in reversed(data_list):  # 反向插入保持顺序
            self.insert_list_data(data)

    def clear_list_data(self):
        """清空QListView中的所有数据"""
        self.list_model.clear()

    def get_all_list_data(self):
        """
        获取QListView中的所有数据

        Returns:
            list: 包含所有数据的列表
        """
        data_list = []
        for row in range(self.list_model.rowCount()):
            item = self.list_model.item(row)
            if item:
                data_list.append(item.text())
        return data_list

    # ==================== 进度条手动控制接口 ====================

    def set_progress_range(self, minimum=0, maximum=100):
        """
        设置进度条的范围

        Args:
            minimum (int): 最小值
            maximum (int): 最大值
        """
        self.progress_bar.setMinimum(minimum)
        self.progress_bar.setMaximum(maximum)
        self.progress_max = maximum
        self.use_manual_progress = True

        # 停止自动进度条动画
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()

    def set_progress_value(self, value):
        """
        设置进度条的当前值

        Args:
            value (int): 进度值
        """
        self.manual_progress = value
        self.progress_bar.setValue(value)
        self.use_manual_progress = True

        # 检查任务是否完成
        if value >= self.progress_max:
            self.complete_task()

    def update_progress_value(self, increment=1):
        """
        更新进度条的值（增加指定数量）

        Args:
            increment (int): 增加的数量，默认为1
        """
        self.manual_progress += increment
        self.manual_progress = min(self.manual_progress, self.progress_max)
        self.progress_bar.setValue(self.manual_progress)
        self.use_manual_progress = True

        # 检查任务是否完成
        if self.manual_progress >= self.progress_max:
            self.complete_task()

    def complete_task(self):
        """手动标记任务完成"""
        self.task_completed = True
        self.message_label.setText("任务完成！")

        # 停止倒计时
        if hasattr(self, 'timer'):
            self.timer.stop()

        # 延迟2000ms后关闭对话框
        QTimer.singleShot(2000, self.accept)

    def get_progress_value(self):
        """
        获取当前进度条的值

        Returns:
            int: 当前进度值
        """
        return self.progress_bar.value()

    def reset_progress(self):
        """重置进度条到0"""
        self.manual_progress = 0
        self.progress_bar.setValue(0)
        self.task_completed = False

    def is_task_completed(self):
        """
        检查任务是否完成

        Returns:
            bool: 任务完成状态
        """
        return self.task_completed


# 使用示例
def main():
    app = QApplication(sys.argv)

    # 创建加载对话框
    dialog = AnimatedLoadingDialog(
        countdown_seconds=10,  # 设置较短的倒计时用于测试
        message="正在处理数据...",
        title="数据处理中",
        show_listview=True
    )

    # 演示QListView功能
    dialog.insert_list_data("开始处理数据...")
    dialog.insert_list_data("连接到服务器")
    dialog.insert_list_data("验证用户权限")

    # 演示手动进度条控制
    dialog.set_progress_range(0, 50)
    dialog.set_progress_value(5)

    # 模拟数据处理过程
    def simulate_process():
        import time
        for i in range(1, 11):  # 模拟10个步骤
            time.sleep(0.8)  # 每步0.8秒，总共8秒
            dialog.insert_list_data(f"处理步骤 {i} 完成")
            dialog.update_progress_value(4)  # 每次增加4，10次后达到45，最后一次会触发完成

            # 模拟最后一步完成整个任务
            if i == 10:
                dialog.update_progress_value(5)  # 达到50，触发任务完成

    def simulate_timeout_process():
        """模拟超时情况 - 任务执行时间超过倒计时"""
        import time
        for i in range(1, 6):
            time.sleep(2.5)  # 每步2.5秒，会导致超时
            dialog.insert_list_data(f"缓慢处理步骤 {i}")
            dialog.update_progress_value(8)

    # 选择模拟场景
    scenario = "normal"  # 可以改为 "timeout" 测试超时情况

    if scenario == "normal":
        # 正常完成场景
        import threading
        thread = threading.Thread(target=simulate_process, daemon=True)
        thread.start()
    else:
        # 超时场景
        import threading
        thread = threading.Thread(target=simulate_timeout_process, daemon=True)
        thread.start()

    result = dialog.exec()
    print(f"对话框结果: {'接受' if result == QDialog.DialogCode.Accepted else '拒绝'}")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
