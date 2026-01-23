import logging

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QSizePolicy)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)


class PlotPanel:
    """绘图面板类"""

    def __init__(self, parent):
        self.parent = parent

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
        self.parent.status_label = QLabel("请选择数据文件并加载数据...")
        self.parent.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.parent.status_label.setStyleSheet("""
            background-color: #e3f2fd; 
            padding: 8px; 
            border-radius: 5px; 
            font-size: 13px;
            border: 1px solid #bbdefb;
        """)
        self.parent.status_label.setMaximumHeight(35)
        layout.addWidget(self.parent.status_label)

        # 创建matplotlib 3D图表
        try:
            self.parent.figure = Figure(figsize=(14, 10), dpi=100)
            self.parent.figure.patch.set_facecolor('white')
            self.parent.canvas = FigureCanvas(self.parent.figure)
            self.parent.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # 启用交互式导航
            self.parent.canvas.mpl_connect('button_press_event', self.parent.on_mouse_press)
            self.parent.canvas.mpl_connect('button_release_event', self.parent.on_mouse_release)
            self.parent.canvas.mpl_connect('motion_notify_event', self.parent.on_mouse_move)

            layout.addWidget(self.parent.canvas)
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
        self.parent.view_reset_btn = QPushButton("重置视图")
        self.parent.view_reset_btn.setMaximumWidth(80)
        self.parent.view_reset_btn.setStyleSheet("background-color: #2196F3; font-size: 12px; padding: 5px;")

        self.parent.fullscreen_btn = QPushButton("全屏显示")
        self.parent.fullscreen_btn.setMaximumWidth(80)
        self.parent.fullscreen_btn.setStyleSheet("background-color: #9C27B0; font-size: 12px; padding: 5px;")

        self.parent.export_btn = QPushButton("导出图片")
        self.parent.export_btn.setMaximumWidth(80)
        self.parent.export_btn.setStyleSheet("background-color: #FF5722; font-size: 12px; padding: 5px;")

        layout.addWidget(QLabel("视图操作:"))
        layout.addWidget(self.parent.view_reset_btn)
        layout.addWidget(self.parent.fullscreen_btn)
        layout.addWidget(self.parent.export_btn)
        layout.addStretch()

        # 显示当前数据统计
        self.parent.stats_label = QLabel("数据点: 0")
        self.parent.stats_label.setStyleSheet("font-weight: bold; color: #666;")
        layout.addWidget(self.parent.stats_label)

        toolbar.setLayout(layout)
        return toolbar

    def init_empty_3d_plot(self):
        """初始化空的3D图表"""
        try:
            if hasattr(self.parent, 'figure') and hasattr(self.parent, 'canvas'):
                self.parent.figure.clear()
                ax = self.parent.figure.add_subplot(111, projection='3d')
                ax.text(0.5, 0.5, 0.5, 'Mouse 3D Trajectory Analysis System\n\n请加载数据查看3D轨迹',
                        horizontalalignment='center', verticalalignment='center',
                        transform=ax.transAxes, fontsize=16,
                        bbox=dict(boxstyle='round,pad=1', facecolor='lightblue', alpha=0.7))
                ax.set_title('Mouse 3D Trajectory Analysis System', fontsize=14, fontweight='bold')
                ax.set_xlabel('X (m)')
                ax.set_ylabel('Y (m)')
                ax.set_zlabel('Z (m)')
                self.parent.canvas.draw()
        except Exception as e:
            logger.error(f"初始化3D图表失败: {e}")

    def init_3d_plot(self):
        """初始化3D图表"""
        try:
            self.parent.figure.clear()
            self.parent.ax = self.parent.figure.add_subplot(111, projection='3d')

            # 设置图表标题
            self.parent.ax.set_title(f'3D Mouse Trajectory - Case-Cage', fontsize=14, fontweight='bold')

            # 设置坐标轴标签
            self.parent.ax.set_xlabel('X (m))')
            self.parent.ax.set_ylabel('Y (m))')
            self.parent.ax.set_zlabel('Z (m)')

            # 设置坐标轴刻度
            self.parent.ax.tick_params(axis='both', which='major', labelsize=10)

            # 绘制初始轨迹
            if len(self.parent.current_x_data) > 0:
                # 当前点
                self.parent.current_point = self.parent.ax.scatter([], [], [], color='red', s=100, alpha=0.8)

                # 轨迹尾迹
                self.parent.trail_line, = self.parent.ax.plot([], [], [], color='blue', linewidth=2, alpha=0.7)

                # 设置坐标轴范围
                self.parent.ax.set_xlim([np.min(self.parent.current_x_data), np.max(self.parent.current_x_data)])
                self.parent.ax.set_ylim([np.min(self.parent.current_y_data), np.max(self.parent.current_y_data)])
                self.parent.ax.set_zlim([np.min(self.parent.current_z_data), np.max(self.parent.current_z_data)])

            self.parent.canvas.draw()

        except Exception as e:
            logger.error(f"初始化3D图表失败: {e}")