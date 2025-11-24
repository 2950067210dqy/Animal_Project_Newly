import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QComboBox, QLabel,
                             QTextEdit, QFileDialog, QSplitter, QGroupBox,
                             QMessageBox, QTabWidget, QSizePolicy, QScrollArea,
                             QGridLayout, QSlider, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPalette, QColor
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.animation as animation
import matplotlib
import logging
import numpy as np
import pandas as pd
import sqlite3
import os
from datetime import datetime
from public.entity.BaseWindow import BaseWindow
from public.config_class.global_setting import global_setting
from Module.Display_trajectory_new.handle.file_reader_handle import FileReaderHandle
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle

# 设置matplotlib使用支持中文的字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)


class DataLoadThread(QThread):
    """数据加载线程"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    data_loaded = pyqtSignal(object)
    temperature_loaded = pyqtSignal(object)
    sheets_detected = pyqtSignal(list)

    def __init__(self, file_path, cage_id, trajectory_sheet=None, temperature_sheet=None):
        super().__init__()
        self.file_path = file_path
        self.cage_id = cage_id
        self.trajectory_sheet = trajectory_sheet
        self.temperature_sheet = temperature_sheet
        self.file_reader = FileReaderHandle()

    def run(self):
        try:
            self.progress.emit(10)

            # 首先检测文件中的所有sheet
            sheets = self.detect_sheets(self.file_path)
            if sheets:
                self.sheets_detected.emit(sheets)

            self.progress.emit(30)

            # 加载轨迹数据
            trajectory_df = self.load_trajectory_data(self.file_path, self.trajectory_sheet)
            if trajectory_df is not None and not trajectory_df.empty:
                self.data_loaded.emit(trajectory_df)
                self.progress.emit(70)

            # 加载温度数据
            temperature_df = self.load_temperature_data(self.file_path, self.temperature_sheet)
            if temperature_df is not None and not temperature_df.empty:
                self.temperature_loaded.emit(temperature_df)
                self.progress.emit(90)

            self.progress.emit(100)

            if trajectory_df is not None:
                self.finished.emit(True, f"成功加载笼 {self.cage_id} 的数据")
            else:
                self.finished.emit(False, "未找到轨迹数据")

        except Exception as e:
            logger.error(f"数据加载失败: {str(e)}")
            self.finished.emit(False, f"数据加载失败: {str(e)}")

    def detect_sheets(self, file_path):
        """检测Excel文件中的所有sheet"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext in ['.xlsx', '.xls']:
                xl_file = pd.ExcelFile(file_path)
                return xl_file.sheet_names
            return []
        except Exception as e:
            logger.error(f"检测sheet失败: {e}")
            return []

    def load_trajectory_data(self, file_path, sheet_name=None):
        """加载轨迹数据"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            df = None

            if file_ext in ['.csv']:
                # CSV文件处理
                encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
                for encoding in encodings:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding)
                        break
                    except (UnicodeDecodeError, Exception):
                        continue

            elif file_ext in ['.xlsx', '.xls']:
                # Excel文件处理
                if sheet_name:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                else:
                    # 自动检测轨迹sheet
                    xl_file = pd.ExcelFile(file_path)
                    trajectory_sheet = self.find_trajectory_sheet(xl_file.sheet_names)
                    if trajectory_sheet:
                        df = pd.read_excel(file_path, sheet_name=trajectory_sheet)
                        logger.info(f"自动选择轨迹sheet: {trajectory_sheet}")
                    else:
                        # 如果没找到，使用第一个sheet
                        df = pd.read_excel(file_path, sheet_name=0)
                        logger.info("使用第一个sheet作为轨迹数据")

            elif file_ext in ['.db', '.sqlite', '.sqlite3']:
                # SQLite数据库处理
                conn = sqlite3.connect(file_path)
                try:
                    df = pd.read_sql_query(
                        f"SELECT * FROM trajectory_data WHERE cage_id = '{self.cage_id}' ORDER BY timestamp", conn)
                except:
                    df = pd.read_sql_query("SELECT * FROM trajectory_data ORDER BY timestamp", conn)
                finally:
                    conn.close()

            return df
        except Exception as e:
            logger.error(f"加载轨迹数据失败: {e}")
            return None

    def load_temperature_data(self, file_path, sheet_name=None):
        """加载温度数据"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            df = None

            if file_ext in ['.xlsx', '.xls']:
                if sheet_name:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                else:
                    # 自动检测温度sheet
                    xl_file = pd.ExcelFile(file_path)
                    temperature_sheet = self.find_temperature_sheet(xl_file.sheet_names)
                    if temperature_sheet:
                        df = pd.read_excel(file_path, sheet_name=temperature_sheet)
                        logger.info(f"自动选择温度sheet: {temperature_sheet}")
                    else:
                        # 尝试在轨迹sheet中查找温度数据
                        trajectory_sheet = self.find_trajectory_sheet(xl_file.sheet_names)
                        if trajectory_sheet:
                            temp_df = pd.read_excel(file_path, sheet_name=trajectory_sheet)
                            if self.has_temperature_column(temp_df):
                                df = temp_df
                                logger.info("在轨迹sheet中找到温度数据")
            elif file_ext in ['.csv']:
                # CSV文件中查找温度数据
                encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
                for encoding in encodings:
                    try:
                        temp_df = pd.read_csv(file_path, encoding=encoding)
                        if self.has_temperature_column(temp_df):
                            df = temp_df
                        break
                    except (UnicodeDecodeError, Exception):
                        continue

            return df
        except Exception as e:
            logger.error(f"加载温度数据失败: {e}")
            return None

    def find_trajectory_sheet(self, sheet_names):
        """查找轨迹数据的sheet"""
        trajectory_keywords = [
            '轨迹', 'trajectory', 'track', '坐标', 'position',
            'movement', '移动', '路径', 'path', '数据'
        ]

        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower()
            for keyword in trajectory_keywords:
                if keyword in sheet_lower:
                    return sheet_name

        # 如果没有找到关键词匹配，返回第一个不是温度相关的sheet
        temp_keywords = ['温度', 'temperature', 'temp', '环境']
        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower()
            is_temp_sheet = any(keyword in sheet_lower for keyword in temp_keywords)
            if not is_temp_sheet:
                return sheet_name

        return sheet_names[0] if sheet_names else None

    def find_temperature_sheet(self, sheet_names):
        """查找温度数据的sheet"""
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

    def has_temperature_column(self, df):
        """检查DataFrame是否包含温度列"""
        temp_column_names = [
            '均值温度(摄氏度)', '均值温度', '温度', 'temperature',
            'temp', 'Temperature', 'Temp', 'avg_temperature',
            '环境温度', '室温', '气温'
        ]

        for col_name in temp_column_names:
            if col_name in df.columns:
                return True
        return False


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
            control_panel = self.create_control_panel()

            # 右侧绘图区域
            plot_panel = self.create_plot_panel()

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
            self.setStyleSheet(self.get_basic_stylesheet())
        except Exception as e:
            logger.error(f"基础样式表加载失败: {e}")

    def _init_custom_style_sheet(self):
        """加载自定义qss样式表"""
        try:
            pass
        except Exception as e:
            logger.error(f"自定义样式表加载失败: {e}")

    def get_basic_stylesheet(self):
        """获取基础样式表"""
        return """
        QWidget {
            background-color: #f5f5f5;
        }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #cccccc;
            border-radius: 8px;
            margin-top: 1ex;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        QPushButton {
            background-color: #4CAF50;
            border: none;
            color: white;
            padding: 8px 16px;
            text-align: center;
            font-size: 14px;
            border-radius: 4px;
            min-height: 30px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
        QPushButton:disabled {
            background-color: #cccccc;
            color: #666666;
        }
        """

    def create_control_panel(self):
        """创建左侧控制面板"""
        panel = QWidget()
        panel.setMaximumWidth(450)
        panel.setMinimumWidth(350)

        # 使用滚动区域包装控制面板
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 创建主控制容器
        control_container = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 使用选项卡组织控制面板
        tab_widget = QTabWidget()

        # 数据选项卡
        data_tab = self.create_data_tab()
        tab_widget.addTab(data_tab, "数据控制")

        # 动画选项卡
        animation_tab = self.create_animation_tab()
        tab_widget.addTab(animation_tab, "动画控制")

        # 显示选项卡
        display_tab = self.create_display_tab()
        tab_widget.addTab(display_tab, "显示设置")

        layout.addWidget(tab_widget)

        # 温度显示组
        layout.addWidget(self.create_temperature_group())

        # 信息显示组
        info_group = self.create_collapsible_info_group()
        layout.addWidget(info_group)

        control_container.setLayout(layout)
        scroll_area.setWidget(control_container)

        # 将滚动区域包装在面板中
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll_area)
        panel.setLayout(panel_layout)

        return panel

    def create_data_tab(self):
        """创建数据控制选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 文件选择组
        layout.addWidget(self.create_file_selection_group())

        # Sheet选择组
        layout.addWidget(self.create_sheet_selection_group())

        # 笼子选择组
        layout.addWidget(self.create_cage_group())

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_animation_tab(self):
        """创建动画控制选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 动画控制组
        layout.addWidget(self.create_animation_control_group())

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_display_tab(self):
        """创建显示设置选项卡"""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # 3D设置组
        layout.addWidget(self.create_3d_settings_group())

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def create_file_selection_group(self):
        """创建文件选择组"""
        file_group = QGroupBox("选择数据文件")
        layout = QVBoxLayout()

        # 文件路径显示
        self.file_path_label = QLabel("文件: 未选择")
        self.file_path_label.setWordWrap(True)
        self.file_path_label.setStyleSheet("background-color: #f9f9f9; padding: 8px; border-radius: 4px;")
        layout.addWidget(self.file_path_label)

        # 选择文件按钮
        self.select_file_btn = QPushButton("选择数据文件")
        layout.addWidget(self.select_file_btn)

        file_group.setLayout(layout)
        return file_group

    def create_sheet_selection_group(self):
        """创建Sheet选择组"""
        sheet_group = QGroupBox("Excel Sheet选择")
        layout = QVBoxLayout()

        # 轨迹数据Sheet选择
        traj_layout = QHBoxLayout()
        traj_layout.addWidget(QLabel("轨迹数据:"))
        self.trajectory_sheet_combo = QComboBox()
        traj_layout.addWidget(self.trajectory_sheet_combo)
        layout.addLayout(traj_layout)

        # 温度数据Sheet选择
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(QLabel("温度数据:"))
        self.temperature_sheet_combo = QComboBox()
        temp_layout.addWidget(self.temperature_sheet_combo)
        layout.addLayout(temp_layout)

        # 加载数据按钮
        self.load_data_btn = QPushButton("加载选定数据")
        self.load_data_btn.setStyleSheet("background-color: #FF9800;")
        layout.addWidget(self.load_data_btn)

        sheet_group.setLayout(layout)
        return sheet_group

    def create_cage_group(self):
        """创建老鼠笼选择组"""
        cage_group = QGroupBox("老鼠笼选择")
        layout = QVBoxLayout()

        # 笼编号选择
        cage_layout = QHBoxLayout()
        cage_layout.addWidget(QLabel("笼编号:"))
        self.cage_combo = QComboBox()
        cage_layout.addWidget(self.cage_combo)

        # 刷新按钮
        self.refresh_cages_btn = QPushButton("刷新")
        self.refresh_cages_btn.setMaximumWidth(60)
        cage_layout.addWidget(self.refresh_cages_btn)

        layout.addLayout(cage_layout)

        cage_group.setLayout(layout)
        return cage_group

    def create_plot_panel(self):
        """创建右侧绘图面板"""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 创建工具栏
        toolbar = self.create_plot_toolbar()
        layout.addWidget(toolbar)

        # 状态标签
        self.status_label = QLabel("请选择数据文件并加载数据...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            background-color: #e3f2fd; 
            padding: 8px; 
            border-radius: 5px; 
            font-size: 13px;
            border: 1px solid #bbdefb;
        """)
        self.status_label.setMaximumHeight(35)
        layout.addWidget(self.status_label)

        # 创建matplotlib 3D图表
        try:
            self.figure = Figure(figsize=(14, 10), dpi=100)
            self.figure.patch.set_facecolor('white')
            self.canvas = FigureCanvas(self.figure)
            self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # 启用交互式导航
            self.canvas.mpl_connect('button_press_event', self.on_mouse_press)
            self.canvas.mpl_connect('button_release_event', self.on_mouse_release)
            self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)

            layout.addWidget(self.canvas)
            logger.info("matplotlib 3D图表创建成功")
        except Exception as e:
            logger.error(f"创建matplotlib图表失败: {e}")
            placeholder = QLabel("3D图表区域\n(matplotlib加载失败)")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("background-color: white; border: 1px solid #ccc; font-size: 16px;")
            placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(placeholder)

        panel.setLayout(layout)
        return panel

    def create_plot_toolbar(self):
        """创建绘图工具栏"""
        toolbar = QWidget()
        toolbar.setMaximumHeight(40)
        toolbar.setStyleSheet("background-color: #f0f0f0; border-radius: 5px;")

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        # 视图控制按钮
        self.view_reset_btn = QPushButton("重置视图")
        self.view_reset_btn.setMaximumWidth(80)
        self.view_reset_btn.setStyleSheet("background-color: #2196F3; font-size: 12px; padding: 5px;")

        self.fullscreen_btn = QPushButton("全屏显示")
        self.fullscreen_btn.setMaximumWidth(80)
        self.fullscreen_btn.setStyleSheet("background-color: #9C27B0; font-size: 12px; padding: 5px;")

        self.export_btn = QPushButton("导出图片")
        self.export_btn.setMaximumWidth(80)
        self.export_btn.setStyleSheet("background-color: #FF5722; font-size: 12px; padding: 5px;")

        layout.addWidget(QLabel("视图操作:"))
        layout.addWidget(self.view_reset_btn)
        layout.addWidget(self.fullscreen_btn)
        layout.addWidget(self.export_btn)
        layout.addStretch()

        # 显示当前数据统计
        self.stats_label = QLabel("数据点: 0")
        self.stats_label.setStyleSheet("font-weight: bold; color: #666;")
        layout.addWidget(self.stats_label)

        toolbar.setLayout(layout)
        return toolbar

    def create_collapsible_info_group(self):
        """创建可折叠的信息显示组"""
        # 主容器
        container = QWidget()
        container.setMaximumHeight(200)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 折叠按钮
        self.info_toggle_btn = QPushButton("▼ 系统日志")
        self.info_toggle_btn.setCheckable(True)
        self.info_toggle_btn.setChecked(True)
        self.info_toggle_btn.setMaximumHeight(30)
        self.info_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                border: none;
                padding: 5px;
                text-align: left;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #455A64;
            }
        """)
        self.info_toggle_btn.clicked.connect(self.toggle_info_panel)
        layout.addWidget(self.info_toggle_btn)

        # 信息文本区域
        self.info_text = QTextEdit()
        self.info_text.setMaximumHeight(150)
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet("""
            font-family: Consolas, monospace; 
            font-size: 10px;
            background-color: #263238;
            color: #E0E0E0;
            border: 1px solid #37474F;
        """)
        layout.addWidget(self.info_text)

        container.setLayout(layout)
        return container

    def create_temperature_group(self):
        """创建温度显示组"""
        temp_group = QGroupBox("老鼠温度监控")
        temp_group.setMaximumHeight(80)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 15, 10, 10)

        # 当前温度显示
        self.current_temp_label = QLabel("当前温度: 等待数据...")
        self.current_temp_label.setStyleSheet("""
            background-color: #e8f5e8;
            border: 2px solid #4CAF50;
            border-radius: 6px;
            padding: 8px;
            font-size: 14px;
            font-weight: bold;
            color: #2E7D32;
        """)
        self.current_temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_temp_label.setMaximumHeight(40)
        layout.addWidget(self.current_temp_label)

        temp_group.setLayout(layout)
        return temp_group

    def create_animation_control_group(self):
        """创建动画控制组"""
        anim_group = QGroupBox("动画控制")
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # 播放控制按钮
        btn_frame = QWidget()
        btn_layout = QGridLayout()
        btn_layout.setSpacing(5)

        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setStyleSheet("background-color: #FF9800; font-weight: bold;")
        self.pause_btn = QPushButton("⏸ 暂停")
        self.pause_btn.setStyleSheet("background-color: #f44336; font-weight: bold;")
        self.reset_btn = QPushButton("⏹ 重置")
        self.reset_btn.setStyleSheet("background-color: #9C27B0; font-weight: bold;")

        btn_layout.addWidget(self.play_btn, 0, 0)
        btn_layout.addWidget(self.pause_btn, 0, 1)
        btn_layout.addWidget(self.reset_btn, 1, 0, 1, 2)

        btn_frame.setLayout(btn_layout)
        layout.addWidget(btn_frame)

        # 速度控制
        speed_frame = QWidget()
        speed_layout = QVBoxLayout()
        speed_layout.setSpacing(3)

        speed_label_layout = QHBoxLayout()
        speed_label_layout.addWidget(QLabel("播放速度:"))
        self.speed_label = QLabel("50")
        self.speed_label.setStyleSheet("font-weight: bold; color: #1976D2;")
        speed_label_layout.addStretch()
        speed_label_layout.addWidget(self.speed_label)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(50)

        speed_layout.addLayout(speed_label_layout)
        speed_layout.addWidget(self.speed_slider)
        speed_frame.setLayout(speed_layout)
        layout.addWidget(speed_frame)

        # 播放进度控制
        progress_frame = QWidget()
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(3)

        # 进度标签布局
        progress_label_layout = QHBoxLayout()
        progress_label_layout.addWidget(QLabel("播放进度:"))
        self.progress_label = QLabel("0 / 0")
        self.progress_label.setStyleSheet("font-weight: bold; color: #1976D2;")
        progress_label_layout.addStretch()
        progress_label_layout.addWidget(self.progress_label)

        self.animation_progress = QSlider(Qt.Orientation.Horizontal)
        self.animation_progress.setRange(0, 100)

        progress_layout.addLayout(progress_label_layout)
        progress_layout.addWidget(self.animation_progress)

        progress_frame.setLayout(progress_layout)
        layout.addWidget(progress_frame)

        anim_group.setLayout(layout)
        return anim_group

    def create_3d_settings_group(self):
        """创建3D设置组"""
        settings_group = QGroupBox("3D显示设置")
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # 显示选项
        display_frame = QWidget()
        display_layout = QGridLayout()
        display_layout.setSpacing(5)

        self.show_points_cb = QCheckBox("显示数据点")
        self.show_points_cb.setChecked(True)
        self.show_lines_cb = QCheckBox("显示连接线")
        self.show_lines_cb.setChecked(True)
        self.show_trail_cb = QCheckBox("显示轨迹尾迹")
        self.show_trail_cb.setChecked(True)
        self.show_grid_cb = QCheckBox("显示网格")
        self.show_grid_cb.setChecked(True)

        display_layout.addWidget(self.show_points_cb, 0, 0)
        display_layout.addWidget(self.show_lines_cb, 0, 1)
        display_layout.addWidget(self.show_trail_cb, 1, 0)
        display_layout.addWidget(self.show_grid_cb, 1, 1)

        display_frame.setLayout(display_layout)
        layout.addWidget(display_frame)

        # 样式控制
        style_frame = QWidget()
        style_layout = QVBoxLayout()
        style_layout.setSpacing(5)

        # 点大小
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("点大小:"))
        self.point_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.point_size_slider.setRange(10, 200)
        self.point_size_slider.setValue(50)
        size_layout.addWidget(self.point_size_slider)
        self.point_size_label = QLabel("50")
        self.point_size_label.setMinimumWidth(30)
        self.point_size_label.setStyleSheet("font-weight: bold;")
        size_layout.addWidget(self.point_size_label)
        style_layout.addLayout(size_layout)

        # 尾迹长度
        trail_layout = QHBoxLayout()
        trail_layout.addWidget(QLabel("尾迹长度:"))
        self.trail_length_slider = QSlider(Qt.Orientation.Horizontal)
        self.trail_length_slider.setRange(10, 500)
        self.trail_length_slider.setValue(100)
        trail_layout.addWidget(self.trail_length_slider)
        self.trail_length_label = QLabel("100")
        self.trail_length_label.setMinimumWidth(30)
        self.trail_length_label.setStyleSheet("font-weight: bold;")
        trail_layout.addWidget(self.trail_length_label)
        style_layout.addLayout(trail_layout)

        style_frame.setLayout(style_layout)
        layout.addWidget(style_frame)

        # 颜色方案
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("颜色方案:"))
        self.color_scheme_combo = QComboBox()
        self.color_scheme_combo.addItems([
            "默认蓝色", "热力图", "彩虹色", "时间渐变",
            "速度映射", "距离映射"
        ])
        color_layout.addWidget(self.color_scheme_combo)
        layout.addLayout(color_layout)

        settings_group.setLayout(layout)
        return settings_group

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

    def update_progress_label(self):
        """更新进度标签显示"""
        try:
            if hasattr(self, 'progress_label') and len(self.current_x_data) > 0:
                current = self.current_frame + 1
                total = len(self.current_x_data)
                self.progress_label.setText(f"{current} / {total}")
        except Exception as e:
            logger.error(f"更新进度标签失败: {e}")

    def setup_connections(self):
        """设置信号连接"""
        try:
            # 文件和数据控制
            self.select_file_btn.clicked.connect(self.select_data_file)
            self.load_data_btn.clicked.connect(self.load_selected_data)
            self.cage_combo.currentTextChanged.connect(self.on_cage_changed)
            self.refresh_cages_btn.clicked.connect(self.refresh_cages)

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
            self.trail_length_slider.valueChanged.connect(self.on_trail_length_changed)
            self.color_scheme_combo.currentTextChanged.connect(self.on_color_scheme_changed)

            # 工具栏连接
            self.view_reset_btn.clicked.connect(self.reset_view)
            self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
            self.export_btn.clicked.connect(self.export_plot)

            logger.info("信号连接设置成功")
        except Exception as e:
            logger.error(f"设置信号连接失败: {e}")

    def setup_initial_state(self):
        """设置初始状态"""
        try:
            self.log_message("老鼠轨迹分析系统 3D版本启动完成")
            self.init_empty_3d_plot()
            self.load_available_cages()
            logger.info("初始状态设置完成")
        except Exception as e:
            logger.error(f"设置初始状态失败: {e}")

    def load_available_cages(self):
        """加载可用的笼子"""
        try:
            if self.available_gids:
                self.cage_combo.clear()
                self.cage_combo.addItems(self.available_gids)
                self.log_message(
                    f"从实验设置加载了 {len(self.available_gids)} 个笼子: {', '.join(self.available_gids)}")
            else:
                try:
                    db_cages = self.data_save.get_available_cages_for_trajectory()
                    if db_cages:
                        self.available_gids = db_cages
                        self.cage_combo.clear()
                        self.cage_combo.addItems(db_cages)
                        self.log_message(f"从数据库加载了 {len(db_cages)} 个笼子: {', '.join(db_cages)}")
                    else:
                        self.log_message("没有找到可用的笼子", "WARNING")
                except:
                    # 如果数据库访问失败，添加一些默认笼子
                    default_cages = ["Cage_001", "Cage_002", "Cage_003"]
                    self.cage_combo.clear()
                    self.cage_combo.addItems(default_cages)
                    self.log_message("使用默认笼子列表")

        except Exception as e:
            self.log_message(f"加载笼子列表失败: {e}", "ERROR")

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
                else:
                    # 非Excel文件直接加载
                    self.load_data(file_path)

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

            cage_id = self.cage_combo.currentText()
            if not cage_id:
                QMessageBox.warning(self, "警告", "请先选择老鼠笼")
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
                cage_id,
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

    def load_data(self, file_path):
        """加载数据（非Excel文件使用）"""
        try:
            cage_id = self.cage_combo.currentText()
            if not cage_id:
                QMessageBox.warning(self, "警告", "请先选择老鼠笼")
                return

            self.log_message(f"开始加载 {file_path} 中的笼 {cage_id} 数据")

            # 创建加载线程
            self.load_thread = DataLoadThread(file_path, cage_id)
            self.load_thread.finished.connect(self.on_data_load_finished)
            self.load_thread.data_loaded.connect(self.on_data_loaded)
            self.load_thread.temperature_loaded.connect(self.on_temperature_loaded)

            # 启动线程
            self.load_thread.start()

        except Exception as e:
            self.log_message(f"启动数据加载失败: {e}", "ERROR")

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

                self.init_3d_plot()
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

    def init_3d_plot(self):
        """初始化3D图表"""
        try:
            self.figure.clear()
            self.ax = self.figure.add_subplot(111, projection='3d')

            # 设置图表标题
            cage_id = self.cage_combo.currentText()
            self.ax.set_title(f'3D Mouse Trajectory - Cage ID: {cage_id}', fontsize=14, fontweight='bold')

            # 设置坐标轴标签
            self.ax.set_xlabel('X Position')
            self.ax.set_ylabel('Y Position')
            self.ax.set_zlabel('Z Position')

            # 设置坐标轴刻度
            self.ax.tick_params(axis='both', which='major', labelsize=10)

            # 绘制初始轨迹
            if len(self.current_x_data) > 0:
                # 当前点
                self.current_point = self.ax.scatter([], [], [], color='red', s=100, alpha=0.8)

                # 轨迹尾迹
                self.trail_line, = self.ax.plot([], [], [], color='blue', linewidth=2, alpha=0.7)

                # 设置坐标轴范围
                self.ax.set_xlim([np.min(self.current_x_data), np.max(self.current_x_data)])
                self.ax.set_ylim([np.min(self.current_y_data), np.max(self.current_y_data)])
                self.ax.set_zlim([np.min(self.current_z_data), np.max(self.current_z_data)])

            self.canvas.draw()

        except Exception as e:
            self.log_message(f"初始化3D图表失败: {e}", "ERROR")

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
            self.init_3d_plot()
            self.log_message("动画已重置")

        except Exception as e:
            self.log_message(f"重置动画失败: {e}", "ERROR")

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

    def on_trail_length_changed(self):
        """尾迹长度改变"""
        value = self.trail_length_slider.value()
        self.trail_length_label.setText(str(value))

    def update_3d_display(self):
        """更新3D显示"""
        if len(self.current_x_data) > 0:
            self.init_3d_plot()

    def on_mouse_press(self, event):
        """鼠标按下事件"""
        pass

    def on_mouse_release(self, event):
        """鼠标释放事件"""
        pass

    def on_mouse_move(self, event):
        """鼠标移动事件"""
        pass

    def refresh_cages(self):
        """刷新笼列表"""
        try:
            self.load_available_cages()
            self.log_message("笼列表已刷新")
        except Exception as e:
            self.log_message(f"刷新笼列表失败: {e}", "ERROR")

    def on_cage_changed(self):
        """笼选择改变时的处理"""
        try:
            cage_id = self.cage_combo.currentText()
            if not cage_id:
                return

            self.log_message(f"选择老鼠笼: {cage_id}")

        except Exception as e:
            self.log_message(f"处理笼选择失败: {e}", "ERROR")

    def on_data_load_finished(self, success, message):
        """数据加载完成回调"""
        if success:
            self.log_message(message)
            file_name = os.path.basename(self.current_file_path) if self.current_file_path else "数据文件"
            self.status_label.setText(f"数据加载成功 - {file_name}")
        else:
            self.log_message(message, "ERROR")
            QMessageBox.warning(self, "错误", message)

    def init_empty_3d_plot(self):
        """初始化空的3D图表"""
        try:
            if hasattr(self, 'figure') and hasattr(self, 'canvas'):
                self.figure.clear()
                ax = self.figure.add_subplot(111, projection='3d')
                ax.text(0.5, 0.5, 0.5, 'Mouse 3D Trajectory Analysis System\n\n请加载数据查看3D轨迹',
                        horizontalalignment='center', verticalalignment='center',
                        transform=ax.transAxes, fontsize=16,
                        bbox=dict(boxstyle='round,pad=1', facecolor='lightblue', alpha=0.7))
                ax.set_title('Mouse 3D Trajectory Analysis System', fontsize=14, fontweight='bold')
                ax.set_xlabel('X Position')
                ax.set_ylabel('Y Position')
                ax.set_zlabel('Z Position')
                self.canvas.draw()
        except Exception as e:
            logger.error(f"初始化3D图表失败: {e}")

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
                self, "导出图片",
                f"trajectory_{self.cage_combo.currentText()}.png",
                "PNG文件 (*.png);;JPG文件 (*.jpg);;PDF文件 (*.pdf)"
            )
            if file_path:
                self.figure.savefig(file_path, dpi=300, bbox_inches='tight')
                self.log_message(f"图片已导出: {file_path}")
        except Exception as e:
            self.log_message(f"导出图片失败: {e}", "ERROR")

    def on_color_scheme_changed(self):
        """颜色方案改变"""
        try:
            scheme = self.color_scheme_combo.currentText()
            self.log_message(f"颜色方案已更改为: {scheme}")
            self.update_3d_display()
        except Exception as e:
            self.log_message(f"更改颜色方案失败: {e}", "ERROR")

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
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {level}: {message}"
            if hasattr(self, 'info_text'):
                self.info_text.append(formatted_message)
                scrollbar = self.info_text.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
            if level == "INFO":
                logger.info(message)
            elif level == "ERROR":
                logger.error(message)
            else:
                logger.warning(message)
        except Exception as e:
            logger.error(f"记录日志失败: {e}")

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
