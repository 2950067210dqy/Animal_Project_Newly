import os
import logging
import os

import matplotlib
import pandas as pd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QSplitter, QMessageBox, QFileDialog)

from Module.Display_trajectory_new.Utils.utils import Utils
from Module.Display_trajectory_new.handle.file_reader_handle import FileReaderHandle
# 导入分层模块
from Module.Display_trajectory_new.ui.control_panel import ControlPanel
from Module.Display_trajectory_new.ui.data_loader import DataLoadThread
from Module.Display_trajectory_new.ui.plot_panel import PlotPanel
from public.config_class.global_setting import global_setting
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.BaseWindow import BaseWindow

# 设置matplotlib使用支持中文的字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)


class TrajectoryViewer(BaseWindow):
    def __init__(self, db_name: str = None):
        super().__init__()

        # 设置窗口属性
        self.setWindowTitle("老鼠轨迹分析系统 - 3D动态显示")
        self.setObjectName("TrajectoryViewer")
        self.resize(1400, 900)

        # 初始化数据处理器
        self.file_reader = FileReaderHandle()

        # 初始化数据库连接
        if db_name:
            self.data_save = Monitor_Datas_Handle(db_name=db_name)
        else:
            self.data_save = Monitor_Datas_Handle()

        # 获取实验设置中的笼子信息
        self.experiment_setting = global_setting.get_setting("experiment_setting", None)
        self.available_gids = []
        if self.experiment_setting is not None:
            self.available_gids = [str(group.id) for group in self.experiment_setting.groups]

        # 初始化数据变量
        self.current_data = None
        self.current_x_data = []
        self.current_y_data = []
        self.current_z_data = []
        self.temperature_data = None
        self.current_temperature_values = []
        self.available_sheets = []
        self.current_file_path = None

        # 动画相关 - 修复：改用定时器控制动画
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.animation_step)
        self.is_playing = False
        self.current_frame = 0
        self.animation_speed = 50  # 1-100的速度值
        self.is_user_dragging = False  # 标记用户是否在拖动进度条

        # 温度显示定时器
        self.temp_timer = QTimer()
        self.temp_timer.timeout.connect(self.update_temperature_display)
        self.temp_index = 0

        # 初始化UI组件类
        self.control_panel = ControlPanel(self)
        self.plot_panel = PlotPanel(self)

        # 按照 BaseWindow 的要求初始化
        self._init_ui()
        self._init_customize_ui()
        self._init_function()
        self._init_style_sheet()
        self._init_custom_style_sheet()

    def _init_ui(self):
        """实例化ui - BaseWindow要求的抽象方法"""
        try:
            # 创建中央控件
            central_widget = QWidget()
            self.setCentralWidget(central_widget)

            # 创建主布局
            main_layout = QHBoxLayout(central_widget)
            main_layout.setSpacing(10)
            main_layout.setContentsMargins(10, 10, 10, 10)

            # 左侧控制面板
            control_panel = self.control_panel.create_control_panel()

            # 右侧绘图区域
            plot_panel = self.plot_panel.create_plot_panel()

            # 使用分割器
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(control_panel)
            splitter.addWidget(plot_panel)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 3)
            splitter.setSizes([350, 1050])

            main_layout.addWidget(splitter)

            logger.info("TrajectoryViewer 3D UI初始化完成")
        except Exception as e:
            logger.error(f"TrajectoryViewer UI初始化失败: {e}")
            import traceback
            traceback.print_exc()

    def _init_customize_ui(self):
        """实例化自定义ui"""
        try:
            pass
        except Exception as e:
            logger.error(f"自定义UI初始化失败: {e}")
        finally:
            super()._init_customize_ui()

    def _init_function(self):
        """实例化功能"""
        try:
            self.setup_connections()
            self.setup_initial_state()
        except Exception as e:
            logger.error(f"功能初始化失败: {e}")

    def _init_style_sheet(self):
        """加载qss样式表"""
        try:
            self.setStyleSheet(Utils.get_basic_stylesheet())
        except Exception as e:
            logger.error(f"基础样式表加载失败: {e}")

    def _init_custom_style_sheet(self):
        """加载自定义qss样式表"""
        try:
            pass
        except Exception as e:
            logger.error(f"自定义样式表加载失败: {e}")

    def setup_connections(self):
        """设置信号连接"""
        try:
            # 文件和数据控制
            self.select_file_btn.clicked.connect(self.select_data_file)
            self.load_data_btn.clicked.connect(self.load_selected_data)

            # 动画控制
            self.play_btn.clicked.connect(self.start_animation)
            self.pause_btn.clicked.connect(self.pause_animation)
            self.reset_btn.clicked.connect(self.reset_animation)

            # 修复：重新设计速度和进度滑块的连接
            self.speed_slider.valueChanged.connect(self.on_speed_changed)
            self.animation_progress.sliderPressed.connect(self.on_progress_slider_pressed)
            self.animation_progress.sliderReleased.connect(self.on_progress_slider_released)
            self.animation_progress.valueChanged.connect(self.on_progress_changed)

            # 3D设置
            self.show_points_cb.toggled.connect(self.update_3d_display)
            self.show_lines_cb.toggled.connect(self.update_3d_display)
            self.show_trail_cb.toggled.connect(self.update_3d_display)
            self.show_grid_cb.toggled.connect(self.update_3d_display)
            self.point_size_slider.valueChanged.connect(self.on_point_size_changed)

            # 工具栏连接
            self.view_reset_btn.clicked.connect(self.reset_view)
            self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
            self.export_btn.clicked.connect(self.export_plot)

            # 信息面板连接
            self.info_toggle_btn.clicked.connect(self.toggle_info_panel)

            logger.info("信号连接设置成功")
        except Exception as e:
            logger.error(f"设置信号连接失败: {e}")

    def setup_initial_state(self):
        """设置初始状态"""
        try:
            # 初始化sheet选择框
            if hasattr(self,'trajectory_sheet_combo'):
                self.trajectory_sheet_combo.setCurrentText("无sheet")
            if hasattr(self,'temperature_sheet_combo'):
                self.temperature_sheet_combo.setCurrentText("无sheet")
            self.log_message("老鼠轨迹分析系统 3D版本启动完成")
            self.plot_panel.init_empty_3d_plot()
            logger.info("初始状态设置完成")
        except Exception as e:
            logger.error(f"设置初始状态失败: {e}")

    # ===== 文件和数据处理方法 =====

    def select_data_file(self):
        """选择数据文件"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择数据文件",
                "",
                "所有支持的文件 (*.csv *.xlsx *.xls *.db *.sqlite *.sqlite3);;CSV文件 (*.csv);;Excel文件 (*.xlsx *.xls);;SQLite数据库 (*.db *.sqlite *.sqlite3);;所有文件 (*.*)"
            )

            if file_path:
                self.current_file_path = file_path
                filename = os.path.basename(file_path)
                self.file_path_label.setText(f"文件: {filename}")
                self.log_message(f"选择了文件: {filename}")

                # 检测Excel文件的sheet
                file_ext = os.path.splitext(file_path)[1].lower()
                if file_ext in ['.xlsx', '.xls']:
                    self.detect_sheets(file_path)

        except Exception as e:
            self.log_message(f"选择文件失败: {e}", "ERROR")

    def detect_sheets(self, file_path):
        """检测并显示Excel文件的sheet"""
        try:
            xl_file = pd.ExcelFile(file_path)
            self.available_sheets = xl_file.sheet_names

            # 更新sheet选择下拉框
            self.trajectory_sheet_combo.clear()
            self.temperature_sheet_combo.clear()

            # 添加"自动检测"选项
            self.trajectory_sheet_combo.addItem("自动检测")
            self.temperature_sheet_combo.addItem("自动检测")

            # 添加所有sheet
            self.trajectory_sheet_combo.addItems(self.available_sheets)
            self.temperature_sheet_combo.addItems(self.available_sheets)

            # 尝试自动选择合适的sheet
            trajectory_sheet = self.auto_detect_trajectory_sheet(self.available_sheets)
            temperature_sheet = self.auto_detect_temperature_sheet(self.available_sheets)

            if trajectory_sheet:
                index = self.trajectory_sheet_combo.findText(trajectory_sheet)
                if index >= 0:
                    self.trajectory_sheet_combo.setCurrentIndex(index)

            if temperature_sheet:
                index = self.temperature_sheet_combo.findText(temperature_sheet)
                if index >= 0:
                    self.temperature_sheet_combo.setCurrentIndex(index)

            self.log_message(f"检测到Excel文件包含 {len(self.available_sheets)} 个sheet")

        except Exception as e:
            self.log_message(f"检测Excel sheet失败: {e}", "ERROR")

    def auto_detect_trajectory_sheet(self, sheet_names):
        """自动检测轨迹数据sheet"""
        trajectory_keywords = [
            '轨迹', 'trajectory', 'track', '坐标', 'position',
            'movement', '移动', '路径', 'path', '数据'
        ]

        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower()
            for keyword in trajectory_keywords:
                if keyword in sheet_lower:
                    return sheet_name
        return None

    def auto_detect_temperature_sheet(self, sheet_names):
        """自动检测温度数据sheet"""
        temperature_keywords = [
            '温度', 'temperature', 'temp', '环境', 'environment',
            '气温', '室温', '监控'
        ]

        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower()
            for keyword in temperature_keywords:
                if keyword in sheet_lower:
                    return sheet_name
        return None

    def load_selected_data(self):
        """加载选中的数据"""
        try:
            if not self.current_file_path:
                QMessageBox.warning(self, "警告", "请先选择数据文件")
                return

            # 获取选择的sheet
            trajectory_sheet = self.trajectory_sheet_combo.currentText()
            temperature_sheet = self.temperature_sheet_combo.currentText()

            if trajectory_sheet == "自动检测":
                trajectory_sheet = None
            if temperature_sheet == "自动检测":
                temperature_sheet = None

            self.log_message(
                f"开始加载数据 - 轨迹sheet: {trajectory_sheet or '自动检测'}, 温度sheet: {temperature_sheet or '自动检测'}")

            # 创建加载线程
            self.load_thread = DataLoadThread(
                self.current_file_path,
                trajectory_sheet,
                temperature_sheet
            )

            self.load_thread.finished.connect(self.on_data_load_finished)
            self.load_thread.data_loaded.connect(self.on_data_loaded)
            self.load_thread.temperature_loaded.connect(self.on_temperature_loaded)
            self.load_thread.sheets_detected.connect(self.on_sheets_detected)

            # 启动线程
            self.load_thread.start()

        except Exception as e:
            self.log_message(f"启动数据加载失败: {e}", "ERROR")

    # ===== 数据加载回调方法 =====

    def on_sheets_detected(self, sheets):
        """检测到sheet时的回调"""
        self.available_sheets = sheets
        self.log_message(f"检测到 {len(sheets)} 个sheet: {', '.join(sheets)}")

    def on_data_loaded(self, df):
        """数据加载成功回调"""
        try:
            self.current_data = df
            self.log_message(f"成功读取轨迹数据，共 {len(df)} 行")

            # 显示数据列信息
            columns_info = f"轨迹数据列: {', '.join(df.columns.tolist())}"
            self.log_message(columns_info)

            # 自动检测XYZ坐标列
            x_col, y_col = self.file_reader.detect_trajectory_columns(df)

            # 检测Z轴坐标列
            z_col = None
            z_keywords = ['z', 'Z', 'z坐标', 'Z坐标', 'z_pos', 'z_position', 'Z_pos', 'Z_position']
            for col in df.columns:
                if any(keyword in col for keyword in z_keywords):
                    z_col = col
                    break

            if not z_col:
                for col in df.columns:
                    col_lower = col.lower()
                    if 'z' in col_lower and any(pos_word in col_lower for pos_word in ['pos', 'coord', '坐标']):
                        z_col = col
                        break

            if not z_col:
                df['z_coordinate'] = 0
                z_col = 'z_coordinate'
                self.log_message("未找到Z坐标列，设置Z坐标为0（2D轨迹显示）")

            if x_col and y_col:
                x_data = pd.to_numeric(df[x_col], errors='coerce').dropna().values
                y_data = pd.to_numeric(df[y_col], errors='coerce').dropna().values
                z_data = pd.to_numeric(df[z_col], errors='coerce').dropna().values

                min_len = min(len(x_data), len(y_data), len(z_data))
                self.current_x_data = x_data[:min_len]
                self.current_y_data = y_data[:min_len]
                self.current_z_data = z_data[:min_len]

                # 更新统计信息
                if hasattr(self, 'stats_label'):
                    self.stats_label.setText(f"数据点: {len(self.current_x_data)}")

                self.plot_panel.init_3d_plot()
                self.animation_progress.setRange(0, len(self.current_x_data) - 1)
                self.update_progress_label()

                self.log_message(f"轨迹数据已加载 - {len(self.current_x_data)} 个有效坐标点")
                self.log_message(f"使用列: X={x_col}, Y={y_col}, Z={z_col}")

            else:
                self.log_message("未能检测到坐标列", "WARNING")
                QMessageBox.warning(self, "警告", f"未能检测到X、Y坐标列\n可用列: {', '.join(df.columns)}")

        except Exception as e:
            self.log_message(f"处理轨迹数据失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()

    def on_temperature_loaded(self, temp_df):
        """温度数据加载回调"""
        try:
            if temp_df is not None and not temp_df.empty:
                # 显示温度数据列信息
                temp_columns_info = f"温度数据列: {', '.join(temp_df.columns.tolist())}"
                self.log_message(temp_columns_info)

                # 查找温度列
                temp_col = None
                temp_column_names = [
                    '均值温度(摄氏度)', '均值温度', '温度', 'temperature',
                    'temp', 'Temperature', 'Temp', 'avg_temperature',
                    '环境温度', '室温', '气温'
                ]

                for col_name in temp_column_names:
                    if col_name in temp_df.columns:
                        temp_col = col_name
                        break

                if temp_col:
                    temp_values = pd.to_numeric(temp_df[temp_col], errors='coerce').dropna()
                    if not temp_values.empty:
                        self.current_temperature_values = temp_values.values

                        self.log_message(f"温度数据已加载 - 使用列: {temp_col}")

                        # 立即显示温度并开始定时更新
                        self.update_temperature_display()
                        self.temp_timer.start(2000)
                    else:
                        self.log_message("温度数据无效", "WARNING")
                        self.current_temp_label.setText("当前温度: 数据无效")
                else:
                    available_cols = ', '.join(temp_df.columns.tolist())
                    self.log_message(f"未找到温度列，可用列: {available_cols}", "WARNING")
                    self.current_temp_label.setText("当前温度: 未找到温度列")
            else:
                self.log_message("没有找到温度数据", "INFO")
                self.current_temp_label.setText("当前温度: 无数据")

        except Exception as e:
            self.log_message(f"处理温度数据失败: {e}", "ERROR")
            self.current_temp_label.setText("当前温度: 加载失败")

    def on_data_load_finished(self, success, message):
        """数据加载完成回调"""
        if success:
            self.log_message(message)
            file_name = os.path.basename(self.current_file_path) if self.current_file_path else "数据文件"
            self.status_label.setText(f"数据加载成功 - {file_name}")
        else:
            self.log_message(message, "ERROR")
            QMessageBox.warning(self, "错误", message)

    # ===== 动画控制方法 =====

    def start_animation(self):
        """开始动画 - 使用QTimer控制"""
        try:
            if len(self.current_x_data) == 0:
                QMessageBox.warning(self, "警告", "请先加载数据")
                return

            self.is_playing = True
            self.update_animation_timer()
            self.log_message("动画开始播放")

        except Exception as e:
            self.log_message(f"启动动画失败: {e}", "ERROR")

    def update_animation_timer(self):
        """更新动画定时器间隔"""
        try:
            if self.is_playing:
                # 计算动画间隔：速度值越大，间隔越小（播放越快）
                speed_value = self.animation_speed
                interval = max(10, 2000 - (speed_value - 1) * 19)  # 最小间隔10ms
                self.animation_timer.start(interval)

        except Exception as e:
            self.log_message(f"更新动画定时器失败: {e}", "ERROR")

    def animation_step(self):
        """动画步进函数 - 每个定时器触发调用一次"""
        try:
            if not self.is_playing:
                return

            # 更新当前帧
            self.current_frame += 1
            if self.current_frame >= len(self.current_x_data):
                # 如果已经到达最后一帧,则停止动画
                self.is_playing = False
                self.animation_timer.stop()
                self.current_frame = 0
                self.animation_progress.setValue(0)
                self.update_progress_label()
                self.log_message("动画已结束")
                return

            # 更新进度条和标签（防止用户拖动时的冲突）
            if not self.is_user_dragging:
                self.animation_progress.setValue(self.current_frame)
                self.update_progress_label()

            # 更新图表
            self.update_frame_display(self.current_frame)

        except Exception as e:
            self.log_message(f"动画步进失败: {e}", "ERROR")

    def update_frame_display(self, frame):
        """更新帧显示"""
        try:
            if frame < len(self.current_x_data):
                # 获取设置
                point_size = self.point_size_slider.value()

                # 清除之前的散点
                if hasattr(self, 'current_point') and self.current_point:
                    self.current_point.remove()

                # 绘制当前点
                self.current_point = self.ax.scatter(
                    [self.current_x_data[frame]],
                    [self.current_y_data[frame]],
                    [self.current_z_data[frame]],
                    color='red', s=point_size, alpha=0.8
                )

                # 更新轨迹尾迹
                if self.show_trail_cb.isChecked():
                    # 从开始到当前帧，显示完整的已走过轨迹
                    end_idx = frame + 1
                    self.trail_line.set_data(
                        self.current_x_data[0:end_idx],
                        self.current_y_data[0:end_idx]
                    )
                    self.trail_line.set_3d_properties(self.current_z_data[0:end_idx])
                else:
                    self.trail_line.set_data([], [])
                    self.trail_line.set_3d_properties([])

                # 重新绘制图表
                self.canvas.draw()

        except Exception as e:
            self.log_message(f"更新帧显示失败: {e}", "ERROR")

    def pause_animation(self):
        """暂停动画"""
        try:
            self.is_playing = False
            self.animation_timer.stop()
            self.log_message("动画已暂停")
        except Exception as e:
            self.log_message(f"暂停动画失败: {e}", "ERROR")

    def reset_animation(self):
        """重置动画"""
        try:
            self.is_playing = False
            self.animation_timer.stop()
            self.current_frame = 0

            # 防止用户拖动冲突
            if not self.is_user_dragging:
                self.animation_progress.setValue(0)
                self.update_progress_label()

            # 重新初始化图表
            self.plot_panel.init_3d_plot()
            self.log_message("动画已重置")

        except Exception as e:
            self.log_message(f"重置动画失败: {e}", "ERROR")

    # ===== 控件事件处理方法 =====

    def on_speed_changed(self):
        """速度改变 - 修复：不重新创建动画，只更新定时器间隔"""
        try:
            value = self.speed_slider.value()
            self.speed_label.setText(str(value))
            self.animation_speed = value

            # 如果正在播放，更新定时器间隔
            if self.is_playing:
                self.update_animation_timer()

            self.log_message(f"动画速度已更新为: {value}")

        except Exception as e:
            self.log_message(f"更新动画速度失败: {e}", "ERROR")

    def on_progress_slider_pressed(self):
        """进度滑块被按下 - 标记用户开始拖动"""
        self.is_user_dragging = True

    def on_progress_slider_released(self):
        """进度滑块被释放 - 结束拖动状态"""
        self.is_user_dragging = False

    def on_progress_changed(self):
        """进度改变（手动拖动或程序更新）"""
        try:
            # 只有在用户手动拖动时才响应
            if self.is_user_dragging and len(self.current_x_data) > 0:
                frame = self.animation_progress.value()
                self.current_frame = frame
                self.update_progress_label()
                self.update_frame_display(frame)

        except Exception as e:
            self.log_message(f"处理进度变化失败: {e}", "ERROR")

    def on_point_size_changed(self):
        """点大小改变"""
        value = self.point_size_slider.value()
        self.point_size_label.setText(str(value))
        self.update_3d_display()

    def update_3d_display(self):
        """更新3D显示"""
        if len(self.current_x_data) > 0:
            self.plot_panel.init_3d_plot()

    def toggle_info_panel(self):
        """切换信息面板显示/隐藏"""
        try:
            if self.info_toggle_btn.isChecked():
                self.info_text.show()
                self.info_toggle_btn.setText("▼ 系统日志")
            else:
                self.info_text.hide()
                self.info_toggle_btn.setText("▶ 系统日志")
        except Exception as e:
            logger.error(f"切换信息面板失败: {e}")

    # ===== 其他方法 =====

    def update_progress_label(self):
        """更新进度标签显示"""
        try:
            if hasattr(self, 'progress_label') and len(self.current_x_data) > 0:
                current = self.current_frame + 1
                total = len(self.current_x_data)
                self.progress_label.setText(f"{current} / {total}")
        except Exception as e:
            logger.error(f"更新进度标签失败: {e}")

    def update_temperature_display(self):
        """更新温度显示"""
        try:
            if len(self.current_temperature_values) > 0:
                # 显示实时温度值（按时间顺序循环显示）
                current_temp = self.current_temperature_values[
                    self.temp_index % len(self.current_temperature_values)]

                self.current_temp_label.setText(f"实时温度: {current_temp:.4f}°C")

                self.temp_index += 1
            else:
                self.current_temp_label.setText("当前温度: -- °C")
        except Exception as e:
            self.log_message(f"更新温度显示失败: {e}", "ERROR")
            self.current_temp_label.setText("当前温度: 显示错误")

    def on_mouse_press(self, event):
        """鼠标按下事件"""
        pass

    def on_mouse_release(self, event):
        """鼠标释放事件"""
        pass

    def on_mouse_move(self, event):
        """鼠标移动事件"""
        pass

    def reset_view(self):
        """重置3D视图"""
        try:
            if hasattr(self, 'ax') and len(self.current_x_data) > 0:
                self.ax.view_init(elev=20, azim=45)
                self.canvas.draw()
                self.log_message("3D视图已重置")
        except Exception as e:
            self.log_message(f"重置视图失败: {e}", "ERROR")

    def toggle_fullscreen(self):
        """切换全屏显示"""
        try:
            if self.isFullScreen():
                self.showNormal()
                self.fullscreen_btn.setText("全屏显示")
                self.log_message("退出全屏模式")
            else:
                self.showFullScreen()
                self.fullscreen_btn.setText("退出全屏")
                self.log_message("进入全屏模式")
        except Exception as e:
            self.log_message(f"切换全屏失败: {e}", "ERROR")

    def export_plot(self):
        """导出图片"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出图片", "",
                "PNG文件 (*.png);;JPG文件 (*.jpg);;PDF文件 (*.pdf)"
            )
            if file_path:
                self.figure.savefig(file_path, dpi=300, bbox_inches='tight')
                self.log_message(f"图片已导出: {file_path}")
        except Exception as e:
            self.log_message(f"导出图片失败: {e}", "ERROR")

    def resizeEvent(self, event):
        """窗口大小改变事件"""
        try:
            super().resizeEvent(event)
            # 根据窗口大小调整字体
            if hasattr(self, 'figure'):
                width = self.width()
                if width > 1600:
                    font_size = 12
                elif width > 1200:
                    font_size = 11
                else:
                    font_size = 10

                # 更新图表字体大小
                if hasattr(self, 'ax'):
                    self.ax.tick_params(labelsize=font_size - 1)
        except Exception as e:
            logger.error(f"窗口调整失败: {e}")

    def log_message(self, message, level="INFO"):
        """记录日志消息"""
        Utils.log_message_to_widget(
            getattr(self, 'info_text', None),
            message,
            level
        )

    def closeEvent(self, event):
        """关闭事件处理"""
        try:
            # 停止动画和定时器
            if hasattr(self, 'animation_timer'):
                self.animation_timer.stop()
            if hasattr(self, 'temp_timer'):
                self.temp_timer.stop()

            # 停止加载线程
            if hasattr(self, 'load_thread') and self.load_thread.isRunning():
                self.load_thread.quit()
                self.load_thread.wait(1000)

            self.log_message("系统正在关闭...")
            super().closeEvent(event)
        except Exception as e:
            self.log_message(f"关闭失败: {e}", "ERROR")
            event.accept()