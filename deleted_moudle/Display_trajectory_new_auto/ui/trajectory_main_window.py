import math
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QComboBox,
                             QGroupBox, QGridLayout,
                             QTextEdit, QScrollArea, QSlider,QMessageBox)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from loguru import logger

from Module.Display_trajectory_new_auto.data.database_data_thread import DatabaseDataThread
from Module.Display_trajectory_new_auto.ui.trajectory_ui_components import (DetailedTrajectoryWindow, DynamicTrajectoryCanvas)
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.BaseWindow import BaseWindow

class TrajectoryMainWindow(BaseWindow):
    """基于数据库数据的动态轨迹监控主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("老鼠轨迹监测界面")
        self.resize(1600, 1000)

        # 数据处理对象
        self.data_handler = Monitor_Datas_Handle(db_name="C:/Users/Jack/Desktop/Lab/mousecages-project/database.db")

        # 可用鼠笼和画布
        self.available_cages = []
        self.trajectory_canvases = {}

        # 基于数据的线程
        self.data_thread = None

        # 自动运行状态
        self.auto_running = False

        # 统计信息
        self.total_real_points = 0
        self.total_rendered_points = 0

        # 详细窗口列表
        self.detail_windows = {}

        # 记录上一次的轴选择，用于恢复
        self.previous_x_axis = 'x'
        self.previous_y_axis = 'y'

        self.init_ui()

        # 自动启动
        QTimer.singleShot(1000, self.fully_auto_start)

    def init_ui(self):
        """初始化用户界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # 标题栏
        header_layout = self.create_auto_header()
        main_layout.addLayout(header_layout)

        # 控制面板
        control_panel = self.create_auto_control_panel()
        main_layout.addWidget(control_panel)

        # 画布区域
        self.canvas_area = QScrollArea()
        self.canvas_area.setWidgetResizable(True)
        canvas_widget = QWidget()
        self.canvas_layout = QGridLayout(canvas_widget)
        self.canvas_area.setWidget(canvas_widget)
        main_layout.addWidget(self.canvas_area)

        # 状态面板
        status_panel = self.create_auto_status_panel()
        main_layout.addWidget(status_panel)

    def create_auto_header(self):
        """创建标题栏"""
        layout = QHBoxLayout()

        title = QLabel("老鼠轨迹监测界面")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        title.setStyleSheet(
            "color: #2c3e50; padding: 15px; background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #ecf0f1, stop: 1 #bdc3c7); border-radius: 8px;")
        layout.addWidget(title)

        layout.addStretch()

        # 状态指示器
        self.status_indicator = QLabel("🔴 准备中")
        self.status_indicator.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.status_indicator.setStyleSheet(
            "color: #e74c3c; padding: 10px; background: #ffffff; border-radius: 5px; border: 2px solid #e74c3c;")
        layout.addWidget(self.status_indicator)

        return layout

    def create_auto_control_panel(self):
        """创建控制面板"""
        panel = QGroupBox("🎮 数据播放控制")

        layout = QHBoxLayout(panel)

        # 轴选择
        axis_group = QGroupBox("📊 显示轴")
        axis_layout = QGridLayout(axis_group)

        axis_layout.addWidget(QLabel("横轴:"), 0, 0)
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItems(['x', 'y', 'z'])
        self.x_axis_combo.setCurrentText('x')
        # 连接信号前记录初始值
        self.previous_x_axis = self.x_axis_combo.currentText()
        self.x_axis_combo.currentTextChanged.connect(self.on_axis_changed)
        axis_layout.addWidget(self.x_axis_combo, 0, 1)

        axis_layout.addWidget(QLabel("纵轴:"), 1, 0)
        self.y_axis_combo = QComboBox()
        self.y_axis_combo.addItems(['x', 'y', 'z'])
        self.y_axis_combo.setCurrentText('y')
        # 连接信号前记录初始值
        self.previous_y_axis = self.y_axis_combo.currentText()
        self.y_axis_combo.currentTextChanged.connect(self.on_axis_changed)
        axis_layout.addWidget(self.y_axis_combo, 1, 1)

        layout.addWidget(axis_group)

        # 播放控制
        playback_group = QGroupBox("⏯️ 播放控制")
        playback_layout = QVBoxLayout(playback_group)

        self.pause_resume_btn = QPushButton("⏸️ 暂停")
        self.pause_resume_btn.clicked.connect(self.toggle_pause_resume)
        self.pause_resume_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f39c12;
                        color: white;
                        padding: 12px 24px;
                        border: none;
                        border-radius: 8px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #e67e22;
                    }
                """)
        playback_layout.addWidget(self.pause_resume_btn)

        # 重置按钮
        self.reset_btn = QPushButton("🔄 重新播放")
        self.reset_btn.clicked.connect(self.reset_all_playback)
        self.reset_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3498db;
                        color: white;
                        padding: 8px 16px;
                        border: none;
                        border-radius: 5px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #2980b9;
                    }
                """)
        playback_layout.addWidget(self.reset_btn)

        layout.addWidget(playback_group)

        # 播放速度控制
        speed_group = QGroupBox("🚀 播放速度")
        speed_layout = QVBoxLayout(speed_group)

        speed_slider_layout = QHBoxLayout()
        speed_slider_layout.addWidget(QLabel("慢"))

        self.main_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.main_speed_slider.setMinimum(50)
        self.main_speed_slider.setMaximum(2000)
        self.main_speed_slider.setValue(1000)
        self.main_speed_slider.setInvertedAppearance(True)
        self.main_speed_slider.valueChanged.connect(self.on_main_speed_changed)
        speed_slider_layout.addWidget(self.main_speed_slider)

        speed_slider_layout.addWidget(QLabel("快"))
        speed_layout.addLayout(speed_slider_layout)

        self.main_speed_label = QLabel("1000ms")
        self.main_speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_speed_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        speed_layout.addWidget(self.main_speed_label)

        layout.addWidget(speed_group)

        # 数据统计
        stats_group = QGroupBox("📈 数据统计")
        stats_layout = QVBoxLayout(stats_group)

        self.cage_count_label = QLabel("鼠笼数量: 0")
        self.real_points_label = QLabel("数据点: 0")
        self.rendered_points_label = QLabel("已渲染点: 0")
        self.status_label = QLabel("状态: 准备中")

        for label in [self.cage_count_label, self.real_points_label, self.rendered_points_label, self.status_label]:
            label.setStyleSheet("color: #2c3e50; font-weight: bold;")
            stats_layout.addWidget(label)

        layout.addWidget(stats_group)

        return panel

    def create_auto_status_panel(self):
        """创建状态面板"""
        panel = QGroupBox("📊 数据播放日志")
        layout = QVBoxLayout(panel)

        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(100)
        self.status_text.setReadOnly(True)
        self.status_text.setStyleSheet("""
            QTextEdit {
                background-color: #2c3e50;
                color: #1abc9c;
                border: none;
                font-family: Consolas, monospace;
                font-size: 10px;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.status_text)

        return panel

    def on_main_speed_changed(self, value):
        """更改播放速度"""
        if self.data_thread:
            self.data_thread.set_play_speed(value)

        self.main_speed_label.setText(f"{value}ms")
        self.log_status(f"播放速度调整为 {value}ms/帧")

    def fully_auto_start(self):
        """自动启动"""
        self.log_status("系统自动启动...")

        try:
            # 获取可用鼠笼
            self.available_cages = self.data_handler.get_available_cages()

            if not self.available_cages:
                self.log_status("未发现可用鼠笼，系统待机...")
                QTimer.singleShot(5000, self.fully_auto_start)
                return

            self.log_status(f"发现 {len(self.available_cages)} 个鼠笼: {self.available_cages}")
            self.cage_count_label.setText(f"鼠笼数量: {len(self.available_cages)}")

            # 创建画布
            self.create_dynamic_plots()

            # 启动基于数据的播放
            self.start_real_data_playback()

        except Exception as e:
            error_msg = f"自动启动异常: {e}"
            self.log_status(error_msg)
            logger.error(error_msg)
            QTimer.singleShot(5000, self.fully_auto_start)

    def create_dynamic_plots(self):
        """创建动态轨迹图"""
        self.trajectory_canvases = {}  #清空之前的画布
        num_cages = len(self.available_cages)

        if num_cages <= 2:
            num_cols = 2
        elif num_cages <= 6:
            num_cols = 3
        elif num_cages <= 8:
            num_cols = 4
        else:
            num_cols = 5
        num_rows = math.ceil(num_cages / num_cols)  #总行数计算向上取整

        self.log_status(f"创建 {num_rows}×{num_cols} 数据播放布局")

        for i, cage_id in enumerate(self.available_cages):
            row = i // num_cols
            col = i % num_cols

            canvas = DynamicTrajectoryCanvas(cage_id, self.canvas_area.widget())
            canvas.set_main_window(self)
            self.canvas_layout.addWidget(canvas, row, col)
            self.trajectory_canvases[cage_id] = canvas

        self.log_status(f"已创建 {num_cages} 个数据播放画布")

    def start_real_data_playback(self):
        """启动数据播放"""
        if self.auto_running:
            return

        self.log_status("开始播放数据库轨迹...")

        # 启动基于数据的线程
        self.data_thread = DatabaseDataThread(self.data_handler, self.available_cages)
        self.data_thread.data_received.connect(self.on_real_data_received)
        self.data_thread.progress_updated.connect(self.on_progress_updated)
        self.data_thread.start()

        self.auto_running = True
        self.status_indicator.setText("🔴 播放中")
        self.status_indicator.setStyleSheet(
            "color: #27ae60; padding: 10px; background: #ffffff; border-radius: 5px; border: 2px solid #27ae60;")
        self.status_label.setText("状态: 播放中")

    def toggle_pause_resume(self):
        """切换暂停/恢复"""
        if not self.data_thread:
            return

        # 如果播放已完成，重新开始播放
        if (self.total_rendered_points >= self.total_real_points > 0 and
                self.pause_resume_btn.text() == "🔄 重新播放"):
            self.reset_all_playback()
            return

        if self.data_thread.is_paused():
            self.data_thread.resume()
            self.pause_resume_btn.setText("⏸️ 暂停")
            self.pause_resume_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f39c12;
                    color: white;
                    padding: 12px 24px;
                    border: none;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #e67e22;
                }
            """)
            self.status_indicator.setText("🔴 播放中")
            self.status_indicator.setStyleSheet(
                "color: #27ae60; padding: 10px; background: #ffffff; border-radius: 5px; border: 2px solid #27ae60;")
            self.status_label.setText("状态: 播放中")
            self.log_status("恢复数据播放")
        else:
            self.data_thread.pause()
            self.pause_resume_btn.setText("▶️ 播放")
            self.pause_resume_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    padding: 12px 24px;
                    border: none;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #2ecc71;
                }
            """)
            self.status_indicator.setText("⏸️ 已暂停")
            self.status_indicator.setStyleSheet(
                "color: #f39c12; padding: 10px; background: #ffffff; border-radius: 5px; border: 2px solid #f39c12;")
            self.status_label.setText("状态: 已暂停")
            self.log_status("暂停数据播放")

    def reset_all_playback(self):
        """重置所有播放进度"""
        if self.data_thread:
            self.data_thread.reset_all_progress()
            # 重新开始播放
            self.data_thread.resume()

        # 清空画布
        for canvas in self.trajectory_canvases.values():
            canvas.clear_trajectory()

        # 重置计数
        self.total_rendered_points = 0
        self.rendered_points_label.setText("已渲染点: 0")

        # 更新UI状态为播放中
        self.pause_resume_btn.setText("⏸️ 暂停")
        self.pause_resume_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.status_indicator.setText("🔴 播放中")
        self.status_indicator.setStyleSheet(
            "color: #27ae60; padding: 10px; background: #ffffff; border-radius: 5px; border: 2px solid #27ae60;")
        self.status_label.setText("状态: 播放中")

        self.log_status("已重置所有播放进度并重新开始播放")

    def on_axis_changed(self):
        """轴切换 - 增强版本，包含弹窗提示和自动恢复"""
        current_x_axis = self.x_axis_combo.currentText()
        current_y_axis = self.y_axis_combo.currentText()

        # 检查是否选择了相同的轴
        if current_x_axis == current_y_axis:
            # 显示错误弹窗
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle("轴选择错误")
            msg_box.setText("横轴和纵轴不能选择相同的坐标轴！")
            msg_box.setInformativeText(f"您当前选择的横轴和纵轴都是 '{current_x_axis}' 轴。\n请选择不同的坐标轴。")

            # 设置按钮
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)

            # 自定义样式
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #f8f9fa;
                    color: #2c3e50;
                    font-family: 'Microsoft YaHei';
                    font-size: 12px;
                }
                QMessageBox QLabel {
                    color: #2c3e50;
                    font-size: 12px;
                    padding: 10px;
                }
                QMessageBox QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    padding: 8px 20px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                    min-width: 60px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #c0392b;
           }
            """)

            # 显示弹窗
            msg_box.exec()

            # 记录日志
            self.log_status(f"❌ 轴选择错误：横轴和纵轴都选择了 '{current_x_axis}' 轴")

            # 恢复到之前的选择
            # 临时断开信号连接，避免递归调用
            self.x_axis_combo.blockSignals(True)
            self.y_axis_combo.blockSignals(True)

            # 恢复到之前的值
            self.x_axis_combo.setCurrentText(self.previous_x_axis)
            self.y_axis_combo.setCurrentText(self.previous_y_axis)

            # 重新连接信号
            self.x_axis_combo.blockSignals(False)
            self.y_axis_combo.blockSignals(False)

            self.log_status(f"🔄 已恢复到之前的设置：横轴={self.previous_x_axis}, 纵轴={self.previous_y_axis}")

            return

        # 如果选择有效，更新画布并记录新的选择
        try:
            # 更新所有画布的轴映射
            for canvas in self.trajectory_canvases.values():
                canvas.set_axis_mapping(current_x_axis, current_y_axis)

            # 记录成功的轴切换
            self.log_status(f"✅ 成功切换到 {current_x_axis.upper()}-{current_y_axis.upper()} 平面")

            # 更新记录的上一次选择
            self.previous_x_axis = current_x_axis
            self.previous_y_axis = current_y_axis

        except Exception as e:
            # 如果更新画布时出错，也恢复到之前的设置
            error_msg = f"更新轴映射时出错: {e}"
            logger.error(error_msg)
            self.log_status(f"❌ {error_msg}")

            # 显示错误弹窗
            error_box = QMessageBox()
            error_box.setIcon(QMessageBox.Icon.Critical)
            error_box.setWindowTitle("轴切换失败")
            error_box.setText("切换坐标轴时发生错误！")
            error_box.setInformativeText(f"错误信息：{str(e)}\n\n将恢复到之前的设置。")
            error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            error_box.exec()

            # 恢复到之前的选择
            self.x_axis_combo.blockSignals(True)
            self.y_axis_combo.blockSignals(True)
            self.x_axis_combo.setCurrentText(self.previous_x_axis)
            self.y_axis_combo.setCurrentText(self.previous_y_axis)
            self.x_axis_combo.blockSignals(False)
            self.y_axis_combo.blockSignals(False)

    def on_real_data_received(self, cage_data):
        """处理接收到的数据"""
        try:
            # 不再在这里计算渲染点数，只处理数据
            for cage_id, trajectory_data in cage_data.items():
                if cage_id in self.trajectory_canvases:
                    for data_point in trajectory_data:
                        self.trajectory_canvases[cage_id].add_trajectory_point(data_point)

        except Exception as e:
            logger.error(f"处理数据失败: {e}")

    def on_progress_updated(self, progress_info):
        """更新播放进度"""
        try:
            # 计算总数据点数
            total_real_points = sum([info['total'] for info in progress_info.values()])
            if total_real_points != self.total_real_points:
                self.total_real_points = total_real_points
                self.real_points_label.setText(f"数据点: {total_real_points}")

            # 计算已渲染点数
            current_rendered_points = sum([info['current'] for info in progress_info.values()])
            self.total_rendered_points = current_rendered_points
            self.rendered_points_label.setText(f"已渲染点: {self.total_rendered_points}")

            # 检查是否播放完成
            if self.total_rendered_points >= self.total_real_points and self.total_real_points > 0:
                self.on_playback_completed()

        except Exception as e:
            logger.error(f"更新进度失败: {e}")

    def on_playback_completed(self):
        """播放完成处理"""
        if not self.data_thread or self.data_thread.is_paused():
            return

        self.log_status("🎉 所有数据播放完成")

        # 停止数据线程
        if self.data_thread:
            self.data_thread.pause()

        # 更新UI状态
        self.pause_resume_btn.setText("🔄 重新播放")
        self.pause_resume_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)

        self.status_indicator.setText("✅ 播放完成")
        self.status_indicator.setStyleSheet(
            "color: #27ae60; padding: 10px; background: #ffffff; border-radius: 5px; border: 2px solid #27ae60;")
        self.status_label.setText("状态: 播放完成")

    def open_detailed_view(self, cage_id):
        """打开详细视图"""
        try:
            if cage_id in self.detail_windows and self.detail_windows[cage_id].isVisible():
                self.detail_windows[cage_id].raise_()
                self.detail_windows[cage_id].activateWindow()
                self.log_status(f"切换到鼠笼 {cage_id} 详细窗口")
                return

            detail_window = DetailedTrajectoryWindow(cage_id, self.data_thread, self)
            self.detail_windows[cage_id] = detail_window
            detail_window.show()

            self.log_status(f"打开鼠笼 {cage_id} 详细轨迹视图 (数据播放)")

        except Exception as e:
            logger.error(f"打开详细视图失败: {e}")

    def log_status(self, message):
        """记录状态信息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"

        self.status_text.append(formatted_message)

        # 自动滚动（避免用户手动滚动）
        cursor = self.status_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.status_text.setTextCursor(cursor)

    def closeEvent(self, event):
        """窗口关闭事件"""
        try:
            if self.auto_running and self.data_thread:
                self.data_thread.stop()

            for detail_window in self.detail_windows.values():
                if detail_window.isVisible():
                    detail_window.close()

            if self.data_handler:
                try:
                    if hasattr(self.data_handler, 'close'):
                        self.data_handler.close()
                except Exception as e:
                    logger.error(f"关闭数据处理器时出错: {e}")

            event.accept()

        except Exception as e:
            logger.error(f"关闭窗口时出错: {e}")
            event.accept()

