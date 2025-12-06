import os
import time
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QComboBox, QGroupBox, QSlider,
                             QFileDialog, QMessageBox)
from PyQt6.QtCore import QTimer, Qt, QStandardPaths
from PyQt6.QtGui import QFont
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from collections import deque
from loguru import logger

class DynamicDetailed2DCanvas(FigureCanvas):
    """动态2D轨迹画布 - 逐步绘制轨迹"""

    def __init__(self, cage_id, width=7, height=6, dpi=100):
        self.cage_id = cage_id
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='white')
        super().__init__(self.fig)

        self.ax = self.fig.add_subplot(111)

        # 动态数据存储
        self.trajectory_x = []
        self.trajectory_y = []
        self.current_x_axis = 'x'
        self.current_y_axis = 'y'

        # 颜色配置
        self.trajectory_color = '#3498db'
        self.start_color = '#27ae60'
        self.current_color = '#e74c3c'

        # 绘图元素
        self.trajectory_line = None
        self.start_point = None
        self.current_point = None

        self.init_plot()

    def init_plot(self):
        """初始化动态绘图"""
        self.ax.clear()
        self.trajectory_x.clear()
        self.trajectory_y.clear()

        self.ax.set_title(f'鼠笼 {self.cage_id} - 2D轨迹动态绘制',
                          fontsize=14, fontweight='bold', color='#2c3e50')
        self.ax.grid(True, alpha=0.3, linestyle='--')
        self.ax.set_facecolor('#f8f9fa')
        self.ax.set_xlabel(f'{self.current_x_axis.upper()}坐标 (m)', fontsize=12)
        self.ax.set_ylabel(f'{self.current_y_axis.upper()}坐标 (m)', fontsize=12)

        # 初始化绘图元素
        self.trajectory_line, = self.ax.plot([], [], color=self.trajectory_color,
                                             linewidth=2, alpha=0.8, label='轨迹路径')
        self.start_point, = self.ax.plot([], [], 'o', color=self.start_color,
                                         markersize=12, label='起始点', zorder=10,
                                         markeredgecolor='white', markeredgewidth=2)
        self.current_point, = self.ax.plot([], [], 'o', color=self.current_color,
                                           markersize=10, label='当前位置', zorder=11,
                                           markeredgecolor='white', markeredgewidth=2)

        self.ax.legend(fontsize=10, loc='best')
        self.ax.set_aspect('equal', adjustable='box')

        self.draw()

    def add_dynamic_point(self, x, y, x_axis, y_axis, point_index):
        """动态添加轨迹点"""
        self.current_x_axis = x_axis
        self.current_y_axis = y_axis

        # 添加新点
        self.trajectory_x.append(x)
        self.trajectory_y.append(y)

        # 更新轨迹线
        self.trajectory_line.set_data(self.trajectory_x, self.trajectory_y)

        # 更新起始点（第一个点）
        if len(self.trajectory_x) == 1:
            self.start_point.set_data([self.trajectory_x[0]], [self.trajectory_y[0]])

        # 更新当前位置点（最新点）
        self.current_point.set_data([self.trajectory_x[-1]], [self.trajectory_y[-1]])

        # 动态调整视图范围
        if len(self.trajectory_x) > 1:
            self.adjust_view_range()

        # 更新标题
        self.ax.set_title(
            f'鼠笼 {self.cage_id} - {x_axis.upper()}-{y_axis.upper()} 轨迹 ({len(self.trajectory_x)}点) - 动态绘制中',
            fontsize=14, fontweight='bold', color='#2c3e50')
        self.ax.set_xlabel(f'{x_axis.upper()}坐标 (m)', fontsize=12)
        self.ax.set_ylabel(f'{y_axis.upper()}坐标 (m)', fontsize=12)

        self.draw()

    def adjust_view_range(self):
        """动态调整视图范围"""
        if len(self.trajectory_x) > 0 and len(self.trajectory_y) > 0:
            margin_factor = 0.1

            x_min, x_max = min(self.trajectory_x), max(self.trajectory_x)
            y_min, y_max = min(self.trajectory_y), max(self.trajectory_y)

            x_margin = (x_max - x_min) * margin_factor if x_max != x_min else 20
            y_margin = (y_max - y_min) * margin_factor if y_max != y_min else 20

            self.ax.set_xlim(x_min - x_margin, x_max + x_margin)
            self.ax.set_ylim(y_min - y_margin, y_max + y_margin)


class DynamicDetailed3DCanvas(FigureCanvas):
    """动态3D轨迹画布 - 逐步绘制轨迹"""

    def __init__(self, cage_id, width=7, height=6, dpi=100):
        self.cage_id = cage_id
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='white')
        super().__init__(self.fig)

        self.ax = self.fig.add_subplot(111, projection='3d')

        # 动态数据存储
        self.trajectory_x = []
        self.trajectory_y = []
        self.trajectory_z = []

        # 颜色配置
        self.trajectory_color = '#3498db'
        self.start_color = '#27ae60'
        self.current_color = '#e74c3c'

        # 绘图元素
        self.trajectory_line = None
        self.start_point = None
        self.current_point = None

        self.init_plot()

    def init_plot(self):
        """初始化3D动态绘图 - 优化版本"""
        self.ax.clear()
        self.trajectory_x.clear()
        self.trajectory_y.clear()
        self.trajectory_z.clear()

        self.ax.set_title(f'鼠笼 {self.cage_id} - 3D轨迹动态绘制 (可拖拽旋转)',
                          fontsize=14, fontweight='bold', color='#2c3e50')

        # 设置标签
        self.ax.set_xlabel('X坐标 (m)', fontsize=10, labelpad=10)
        self.ax.set_ylabel('Z坐标 (m)', fontsize=10, labelpad=10)
        self.ax.set_zlabel('Y坐标 (m)', fontsize=10, labelpad=10)

        # 设置更好的视角
        self.ax.view_init(elev=20, azim=45)

        # 优化背景和网格
        self.ax.xaxis.pane.fill = False
        self.ax.yaxis.pane.fill = False
        self.ax.zaxis.pane.fill = False
        self.ax.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)

        # 设置面板样式
        self.ax.xaxis.pane.set_edgecolor('gray')
        self.ax.yaxis.pane.set_edgecolor('gray')
        self.ax.zaxis.pane.set_edgecolor('gray')
        self.ax.xaxis.pane.set_alpha(0.1)
        self.ax.yaxis.pane.set_alpha(0.1)
        self.ax.zaxis.pane.set_alpha(0.1)

        # 初始化3D绘图元素
        self.trajectory_line, = self.ax.plot([], [], [], color=self.trajectory_color,
                                             linewidth=1.5, alpha=0.7, label='3D轨迹')
        self.start_point = self.ax.scatter([], [], [], color=self.start_color,
                                           s=100, label='起始点', zorder=10,
                                           marker='o', edgecolors='white', linewidths=1.5)
        self.current_point = self.ax.scatter([], [], [], color=self.current_color,
                                             s=80, label='当前位置', zorder=11,
                                             marker='o', edgecolors='white', linewidths=1.5)

        self.ax.legend(fontsize=9, loc='upper left', framealpha=0.9)

        self.draw()

    def add_dynamic_point(self, x, y, z, point_index):
        """动态添加3D轨迹点 - 优化显示效果"""
        # 添加新点 - 调整Y轴和Z轴映射
        self.trajectory_x.append(x)
        self.trajectory_y.append(z)  # 原来的Z坐标现在映射到Y轴
        self.trajectory_z.append(y)  # 原来的Y坐标现在映射到Z轴

        # 清除并重新绘制
        self.ax.clear()
        self.ax.set_title(f'鼠笼 {self.cage_id} - 3D轨迹 ({len(self.trajectory_x)}点) - 动态绘制中',
                          fontsize=14, fontweight='bold', color='#2c3e50')

        # 设置标签
        self.ax.set_xlabel('X坐标 (m)', fontsize=10, labelpad=10)
        self.ax.set_ylabel('Z坐标 (m)', fontsize=10, labelpad=10)
        self.ax.set_zlabel('Y坐标 (m)', fontsize=10, labelpad=10)

        # 绘制3D轨迹线 - 优化线条样式
        if len(self.trajectory_x) > 1:
            self.ax.plot(self.trajectory_x, self.trajectory_y, self.trajectory_z,
                         color=self.trajectory_color, linewidth=1.5, alpha=0.7,
                         label='3D轨迹', marker='o', markersize=2, markevery=5)

        # 绘制起始点
        if len(self.trajectory_x) > 0:
            self.ax.scatter([self.trajectory_x[0]], [self.trajectory_y[0]], [self.trajectory_z[0]],
                            color=self.start_color, s=100, label='起始点', zorder=10,
                            marker='o', edgecolors='white', linewidths=1.5)

        # 绘制当前位置点
        if len(self.trajectory_x) > 0:
            self.ax.scatter([self.trajectory_x[-1]], [self.trajectory_y[-1]], [self.trajectory_z[-1]],
                            color=self.current_color, s=80, label='当前位置', zorder=11,
                            marker='o', edgecolors='white', linewidths=1.5)

        # 优化坐标轴显示
        self.set_axes_equal_optimized()

        # 设置更好的视角
        self.ax.view_init(elev=20, azim=45)  # 调整视角

        # 优化网格和背景
        self.ax.grid(True, alpha=0.2, linestyle='-', linewidth=0.5)
        self.ax.xaxis.pane.fill = False
        self.ax.yaxis.pane.fill = False
        self.ax.zaxis.pane.fill = False

        # 设置面板颜色
        self.ax.xaxis.pane.set_edgecolor('gray')
        self.ax.yaxis.pane.set_edgecolor('gray')
        self.ax.zaxis.pane.set_edgecolor('gray')
        self.ax.xaxis.pane.set_alpha(0.1)
        self.ax.yaxis.pane.set_alpha(0.1)
        self.ax.zaxis.pane.set_alpha(0.1)

        # 图例
        self.ax.legend(fontsize=9, loc='upper left', framealpha=0.9)

        self.draw()

    def set_axes_equal_optimized(self):
        """优化的坐标轴等比例设置"""
        if len(self.trajectory_x) == 0:
            return

        # 计算数据范围
        x_range = [min(self.trajectory_x), max(self.trajectory_x)]
        y_range = [min(self.trajectory_y), max(self.trajectory_y)]
        z_range = [min(self.trajectory_z), max(self.trajectory_z)]

        # 计算各轴的实际范围大小
        x_span = x_range[1] - x_range[0] if x_range[1] != x_range[0] else 0.1
        y_span = y_range[1] - y_range[0] if y_range[1] != y_range[0] else 0.1
        z_span = z_range[1] - z_range[0] if z_range[1] != z_range[0] else 0.1

        # 计算中心点
        x_center = sum(x_range) / 2
        y_center = sum(y_range) / 2
        z_center = sum(z_range) / 2

        # 使用合理的显示范围
        max_span = max(x_span, y_span, z_span)

        # 如果某个轴的范围太大，进行适当压缩
        if y_span > 3 * max(x_span, z_span):  # Y轴过大
            display_y_span = min(y_span, max_span * 1.5)
        else:
            display_y_span = max_span

        if z_span > 3 * max(x_span, y_span):  # Z轴过大
            display_z_span = min(z_span, max_span * 1.5)
        else:
            display_z_span = max_span

        # 设置显示范围
        margin = max_span * 0.1

        self.ax.set_xlim(x_center - max_span / 2 - margin, x_center + max_span / 2 + margin)
        self.ax.set_ylim(y_center - display_y_span / 2 - margin, y_center + display_y_span / 2 + margin)
        self.ax.set_zlim(z_center - display_z_span / 2 - margin, z_center + display_z_span / 2 + margin)

        # 设置合理的坐标轴比例
        if y_span > 3 * max(x_span, z_span) or z_span > 3 * max(x_span, y_span):
            self.ax.set_box_aspect([1, 0.8, 0.8])  # 压缩过大的轴
        else:
            self.ax.set_box_aspect([1, 1, 1])  # 等比例显示

    def set_axes_equal(self):
        """设置3D坐标轴等比例 - 针对Z轴过大的情况优化"""
        if len(self.trajectory_x) == 0:
            return

        # 计算数据范围
        x_range = [min(self.trajectory_x), max(self.trajectory_x)]
        y_range = [min(self.trajectory_y), max(self.trajectory_y)]
        z_range = [min(self.trajectory_z), max(self.trajectory_z)]

        # 计算各轴的实际范围大小
        x_span = x_range[1] - x_range[0]
        y_span = y_range[1] - y_range[0]
        z_span = z_range[1] - z_range[0]

        # 计算中心点
        x_center = sum(x_range) / 2
        y_center = sum(y_range) / 2
        z_center = sum(z_range) / 2

        # 检测Z轴是否过大（超过X、Y轴范围的2倍）
        if z_span > 2 * max(x_span, y_span):
            # Z轴过大，采用压缩策略

            # 使用X、Y轴的最大范围作为基准
            base_range = max(x_span, y_span)
            if base_range == 0:
                base_range = 0.1  # 防止除零

            # 设置显示范围 - Z轴压缩显示
            margin = base_range * 0.15  # 15%边距

            self.ax.set_xlim(x_center - base_range / 2 - margin, x_center + base_range / 2 + margin)
            self.ax.set_ylim(y_center - base_range / 2 - margin, y_center + base_range / 2 + margin)

            # Z轴使用压缩后的范围，但保持数据的相对位置
            compressed_z_range = base_range * 0.8  # Z轴显示范围为基准范围的80%
            self.ax.set_zlim(z_center - compressed_z_range / 2, z_center + compressed_z_range / 2)

            # 设置坐标轴比例 - Z轴压缩
            self.ax.set_box_aspect([1, 1, 0.6])  # Z轴高度为X、Y轴的60%

        else:
            # 正常情况，使用等比例显示
            max_range = max(x_span, y_span, z_span) / 2
            if max_range == 0:
                max_range = 0.1

            margin = max_range * 0.1
            self.ax.set_xlim(x_center - max_range - margin, x_center + max_range + margin)
            self.ax.set_ylim(y_center - max_range - margin, y_center + max_range + margin)
            self.ax.set_zlim(z_center - max_range - margin, z_center + max_range + margin)

            # 等比例显示
            self.ax.set_box_aspect([1, 1, 1])

    # def set_axes_equal(self):
    #     """设置3D坐标轴等比例"""
    #     if len(self.trajectory_x) == 0:
    #         return
    #
    #     # 计算数据范围
    #     x_range = [min(self.trajectory_x), max(self.trajectory_x)]
    #     y_range = [min(self.trajectory_y), max(self.trajectory_y)]
    #     z_range = [min(self.trajectory_z), max(self.trajectory_z)]
    #
    #     # 计算中心点和最大范围
    #     x_center = sum(x_range) / 2
    #     y_center = sum(y_range) / 2
    #     z_center = sum(z_range) / 2
    #
    #     max_range = max(
    #         x_range[1] - x_range[0],
    #         y_range[1] - y_range[0],
    #         z_range[1] - z_range[0]
    #     ) / 2
    #
    #     # 设置等比例坐标轴
    #     if max_range > 0:
    #         margin = max_range * 0.1  # 添加10%边距
    #         self.ax.set_xlim(x_center - max_range - margin, x_center + max_range + margin)
    #         self.ax.set_ylim(y_center - max_range - margin, y_center + max_range + margin)
    #         self.ax.set_zlim(z_center - max_range - margin, z_center + max_range + margin)


class DynamicTrajectoryCanvas(FigureCanvas):
    """动态轨迹绘制画布 - 支持点击跳转和基于数据"""

    def __init__(self, cage_id, parent=None, width=5, height=4, dpi=80):
        self.cage_id = cage_id
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='white')
        super().__init__(self.fig)
        self.setParent(parent)

        # 创建子图
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title(f'鼠笼 {cage_id} - 轨迹播放', fontsize=11, fontweight='bold')
        self.ax.grid(True, alpha=0.3)
        self.ax.set_aspect('equal')

        # 数据存储
        self.max_points = 5000
        self.trajectory_x = deque(maxlen=self.max_points)
        self.trajectory_y = deque(maxlen=self.max_points)
        self.trajectory_z = deque(maxlen=self.max_points)
        self.times = deque(maxlen=self.max_points)

        # 颜色配置
        self.trajectory_color = '#3498db'
        self.current_point_color = '#e74c3c'
        self.start_point_color = '#27ae60'

        # 绘图元素
        self.trajectory_lines = []
        self.current_point = None
        self.start_point = None

        # 轴选择
        self.x_axis = 'x'
        self.y_axis = 'y'

        # 点击事件连接
        self.mpl_connect('button_press_event', self.on_click)

        self.main_window = None
        self.point_count = 0

        self.init_plot()

    def set_main_window(self, main_window):
        """设置主窗口引用"""
        self.main_window = main_window

    def on_click(self, event):
        """处理鼠标点击事件"""
        if event.inaxes == self.ax:
            if self.main_window:
                self.main_window.open_detailed_view(self.cage_id)

    def init_plot(self):
        """初始化绘图"""
        self.ax.clear()
        self.trajectory_lines.clear()

        title_text = f'鼠笼 {self.cage_id} - {self.x_axis.upper()}-{self.y_axis.upper()} 轨迹 (点击查看详情)'
        self.ax.set_title(title_text, fontsize=10, fontweight='bold', color='#2c3e50')

        self.ax.grid(True, alpha=0.2, linestyle='--')
        self.ax.set_xlabel(f'{self.x_axis.upper()}坐标 (m)', fontsize=9)
        self.ax.set_ylabel(f'{self.y_axis.upper()}坐标 (m)', fontsize=9)
        self.ax.set_facecolor('#f8f9fa')
        self.ax.patch.set_edgecolor('#3498db')
        self.ax.patch.set_linewidth(2)

        # 创建绘图元素
        self.current_point, = self.ax.plot([], [], 'o', markersize=8,
                                           color=self.current_point_color, label='当前位置', zorder=10)
        self.start_point, = self.ax.plot([], [], 'o', markersize=8,
                                         color=self.start_point_color, label='起始位置', zorder=10)

        self.ax.legend(loc='upper right', fontsize=8, framealpha=0.9)
        self.ax.tick_params(labelsize=8)
        self.point_count = 0
        self.draw()

    def set_axis_mapping(self, x_axis, y_axis):
        """设置轴映射"""
        self.x_axis = x_axis
        self.y_axis = y_axis
        self.init_plot()
        self.redraw_all_trajectory()

    def get_axis_data(self, axis):
        """根据轴名称获取对应的数据"""
        if axis == 'x':
            return list(self.trajectory_x)
        elif axis == 'y':
            return list(self.trajectory_y)
        elif axis == 'z':
            return list(self.trajectory_z)
        return []

    def add_trajectory_point(self, data_point):
        """添加轨迹点"""
        self.times.append(data_point[0])
        self.trajectory_x.append(data_point[1])
        self.trajectory_y.append(data_point[2])
        self.trajectory_z.append(data_point[3])
        self.point_count += 1
        self.update_dynamic_plot()

    def update_dynamic_plot(self):
        """更新动态绘图"""
        if len(self.trajectory_x) == 0:
            return

        x_data = self.get_axis_data(self.x_axis)
        y_data = self.get_axis_data(self.y_axis)

        if len(x_data) == 0 or len(y_data) == 0:
            return

        # 绘制最新的线段
        if len(x_data) > 1:
            new_line, = self.ax.plot([x_data[-2], x_data[-1]], [y_data[-2], y_data[-1]],
                                     color=self.trajectory_color, linewidth=2, alpha=0.8)
            self.trajectory_lines.append(new_line)

            # 限制线段数量
            if len(self.trajectory_lines) > self.max_points:
                old_line = self.trajectory_lines.pop(0)
                if old_line in self.ax.lines:
                    old_line.remove()

        # 更新当前位置点
        if len(x_data) > 0:
            self.current_point.set_data([x_data[-1]], [y_data[-1]])

        # 更新起始位置点
        if len(x_data) > 0:
            self.start_point.set_data([x_data[0]], [y_data[0]])

        # 调整视图范围
        self.adjust_view_range(x_data, y_data)

        # 更新标题
        title_text = f'鼠笼 {self.cage_id} - {self.x_axis.upper()}-{self.y_axis.upper()} 轨迹 ({len(x_data)}点) - 点击查看详情'
        self.ax.set_title(title_text, fontsize=10, fontweight='bold', color='#2c3e50')

        self.draw()

    def redraw_all_trajectory(self):
        """重新绘制所有轨迹"""
        if len(self.trajectory_x) == 0:
            return

        x_data = self.get_axis_data(self.x_axis)
        y_data = self.get_axis_data(self.y_axis)

        if len(x_data) == 0 or len(y_data) == 0:
            return

        # 清除旧的轨迹线段
        self.trajectory_lines.clear()

        # 重新绘制完整轨迹
        if len(x_data) > 1:
            trajectory_line, = self.ax.plot(x_data, y_data,
                                            color=self.trajectory_color,
                                            linewidth=1.5, alpha=0.8, label='轨迹路径')
            self.trajectory_lines.append(trajectory_line)

        # 更新点位
        if len(x_data) > 0:
            self.current_point.set_data([x_data[-1]], [y_data[-1]])
            self.start_point.set_data([x_data[0]], [y_data[0]])

        self.adjust_view_range(x_data, y_data)

        title_text = f'鼠笼 {self.cage_id} - {self.x_axis.upper()}-{self.y_axis.upper()} 轨迹 ({len(x_data)}点) - 点击查看详情'
        self.ax.set_title(title_text, fontsize=10, fontweight='bold', color='#2c3e50')

        self.draw()

    def adjust_view_range(self, x_data, y_data):
        """调整视图范围"""
        if len(x_data) > 0 and len(y_data) > 0:
            margin_factor = 0.1

            x_min, x_max = min(x_data), max(x_data)
            y_min, y_max = min(y_data), max(y_data)

            x_margin = (x_max - x_min) * margin_factor if x_max != x_min else 20
            y_margin = (y_max - y_min) * margin_factor if y_max != y_min else 20

            self.ax.set_xlim(x_min - x_margin, x_max + x_margin)
            self.ax.set_ylim(y_min - y_margin, y_max + y_margin)

    def clear_trajectory(self):
        """清除轨迹数据"""
        self.trajectory_x.clear()
        self.trajectory_y.clear()
        self.trajectory_z.clear()
        self.times.clear()
        self.point_count = 0
        self.trajectory_lines.clear()
        self.init_plot()


class DetailedTrajectoryWindow(QMainWindow):
    """详细轨迹显示窗口 - 基于数据库数据的动态绘制"""

    def __init__(self, cage_id, data_thread, parent=None):
        super().__init__(parent)
        self.cage_id = cage_id
        self.data_thread = data_thread
        self.main_window = parent
        self.setWindowTitle(f"鼠笼 {cage_id} - 详细轨迹分析")
        self.resize(1400, 800)

        # 轨迹数据
        self.real_trajectory_data = []
        self.current_draw_index = 0

        # 进度信息
        self.total_data_points = 0
        self.current_progress = 0

        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, 
                           stop: 0 #f0f2f5, stop: 1 #e8eaed);
            }
        """)

        self.init_ui()
        self.load_real_data_from_database()

        # 连接数据线程信号
        if self.data_thread:
            self.data_thread.data_received.connect(self.on_real_data_received)
            self.data_thread.progress_updated.connect(self.on_progress_updated)

        # 动态绘制定时器
        self.dynamic_timer = QTimer()
        self.dynamic_timer.timeout.connect(self.dynamic_draw_step)
        self.dynamic_timer.start(200)  # 每200ms检查一次

    def init_ui(self):
        """初始化用户界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # 标题栏
        title_layout = self.create_title_bar()
        main_layout.addLayout(title_layout)

        # 控制面板
        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel)

        # 图表区域
        charts_layout = QHBoxLayout()

        # 2D轨迹图
        self.canvas_2d = DynamicDetailed2DCanvas(self.cage_id, width=7, height=6)
        charts_layout.addWidget(self.canvas_2d)

        # 3D轨迹图
        self.canvas_3d = DynamicDetailed3DCanvas(self.cage_id, width=7, height=6)
        charts_layout.addWidget(self.canvas_3d)

        main_layout.addLayout(charts_layout)

        # 状态栏
        self.status_label = QLabel(f"鼠笼 {self.cage_id} - 正在加载数据...")
        self.status_label.setStyleSheet("color: #2c3e50; font-weight: bold; padding: 10px;")
        main_layout.addWidget(self.status_label)

    def create_title_bar(self):
        """创建标题栏"""
        layout = QHBoxLayout()

        title = QLabel(f"🐭 鼠笼 {self.cage_id} 详细轨迹分析")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title.setStyleSheet("""
            color: white; 
            padding: 15px; 
            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, 
                       stop: 0 #3498db, stop: 1 #2980b9); 
            border-radius: 8px;
        """)
        layout.addWidget(title)

        layout.addStretch()

        # 进度显示
        self.progress_label = QLabel("加载中...")
        self.progress_label.setStyleSheet("""
            color: white;
            background-color: #2c3e50;
            padding: 10px;
            border-radius: 6px;
            font-weight: bold;
        """)
        layout.addWidget(self.progress_label)

        # 关闭按钮
        close_btn = QPushButton("❌ 关闭")
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        layout.addWidget(close_btn)

        return layout

    def create_control_panel(self):
        """创建控制面板"""
        panel = QGroupBox("🎛️ 显示控制")
        layout = QHBoxLayout(panel)

        # 播放控制
        control_group = QGroupBox("⏯️ 播放控制")
        control_layout = QVBoxLayout(control_group)

        self.play_pause_btn = QPushButton("⏸️ 暂停")
        self.play_pause_btn.clicked.connect(self.toggle_pause_resume)
        self.play_pause_btn.setStyleSheet("""
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
        control_layout.addWidget(self.play_pause_btn)


        self.reset_btn = QPushButton("🔄 重新播放")
        self.reset_btn.clicked.connect(self.restart_drawing)
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
        control_layout.addWidget(self.reset_btn)

        # 播放速度控制
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("播放速度:"))
        self.draw_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.draw_speed_slider.setMinimum(50)
        self.draw_speed_slider.setMaximum(2000)
        self.draw_speed_slider.setValue(1000)
        self.draw_speed_slider.valueChanged.connect(self.on_draw_speed_changed)
        speed_layout.addWidget(self.draw_speed_slider)

        self.speed_label = QLabel("1000ms")
        speed_layout.addWidget(self.speed_label)

        control_layout.addLayout(speed_layout)

        layout.addWidget(control_group)

        # 导出控制 - 新增部分
        export_group = QGroupBox("📸 图片导出")
        export_layout = QVBoxLayout(export_group)

        # 2D图片导出
        export_2d_btn = QPushButton("💾 导出2D轨迹图")
        export_2d_btn.clicked.connect(self.export_2d_image)
        export_2d_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        export_layout.addWidget(export_2d_btn)

        # 3D图片导出
        export_3d_btn = QPushButton("💾 导出3D轨迹图")
        export_3d_btn.clicked.connect(self.export_3d_image)
        export_3d_btn.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7d3c98;
            }
        """)
        export_layout.addWidget(export_3d_btn)

        # 导出所有图片
        export_all_btn = QPushButton("📷 导出所有图片")
        export_all_btn.clicked.connect(self.export_all_images)
        export_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
        """)
        export_layout.addWidget(export_all_btn)

        layout.addWidget(export_group)

        # 数据统计
        stats_group = QGroupBox("📊 数据统计")
        stats_layout = QVBoxLayout(stats_group)

        self.data_count_label = QLabel("数据总量: 加载中...")
        self.current_position_label = QLabel("当前位置: -")
        self.completion_label = QLabel("完成度: 0%")

        for label in [self.data_count_label, self.current_position_label, self.completion_label]:
            label.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 11px;")
            stats_layout.addWidget(label)

        layout.addWidget(stats_group)

        panel.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin: 5px;
                padding-top: 15px;
                background: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #2c3e50;
                font-size: 12px;
            }
        """)

        return panel

    def load_real_data_from_database(self):
        """直接从数据库加载数据"""
        try:
            if self.data_thread:
                # 从数据线程获取数据
                self.real_trajectory_data = self.data_thread.get_all_data_for_cage(self.cage_id)

            if not self.real_trajectory_data and hasattr(self.main_window, 'data_handler'):
                # 如果数据线程没有数据，直接从数据库读取
                result = self.main_window.data_handler.get_trajectory_data(
                    cage_id=self.cage_id,
                    limit=None  # 获取所有数据
                )

                if result['success'] and result['data']:
                    validated_data = []
                    for data_point in result['data']:
                        validated_point = self.validate_data_point(data_point)
                        if validated_point:
                            validated_data.append(validated_point)

                    self.real_trajectory_data = sorted(validated_data, key=lambda x: x[0])

            self.total_data_points = len(self.real_trajectory_data)
            self.current_draw_index = 0

            # 更新统计信息
            self.data_count_label.setText(f"数据总量: {self.total_data_points} 条记录")

            if self.total_data_points > 0:
                self.canvas_2d.init_plot()
                self.canvas_3d.init_plot()
                self.status_label.setText(f"已加载 {self.total_data_points} 条数据记录，准备动态播放")
                self.progress_label.setText(f"0/{self.total_data_points}")
            else:
                self.status_label.setText("该鼠笼没有轨迹数据")
                self.progress_label.setText("无数据")

        except Exception as e:
            self.status_label.setText(f"加载数据失败: {e}")
            logger.error(f"加载数据失败: {e}")

    def validate_data_point(self, data_point):
        """验证数据点格式"""
        try:
            if not data_point or len(data_point) < 4:
                return None

            timestamp = data_point[0]
            if isinstance(timestamp, str):
                try:
                    if '.' in timestamp:
                        timestamp = float(timestamp)
                    else:
                        try:
                            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                            timestamp = dt.timestamp()
                        except:
                            dt = datetime.strptime(timestamp.split('.')[0], "%Y-%m-%d %H:%M:%S")
                            timestamp = dt.timestamp()
                except:
                    timestamp = time.time()
            elif not isinstance(timestamp, (int, float)):
                timestamp = time.time()

            x = float(data_point[1]) if data_point[1] is not None else 0.0
            y = float(data_point[2]) if data_point[2] is not None else 0.0
            z = float(data_point[3]) if data_point[3] is not None else 0.0

            return [timestamp, x, y, z]

        except Exception as e:
            logger.error(f"验证数据点失败: {e}")
            return None

    def on_real_data_received(self, cage_data):
        """处理从数据线程接收到的数据"""
        if self.cage_id in cage_data:
            # 这里不需要处理，因为我们基于本地加载的数据进行绘制
            pass

    def on_progress_updated(self, progress_info):
        """更新播放进度信息"""
        if self.cage_id in progress_info:
            cage_progress = progress_info[self.cage_id]
            current = cage_progress['current']
            total = cage_progress['total']

            if total > 0:
                percentage = (current / total) * 100
                self.progress_label.setText(f"{current}/{total} ({percentage:.1f}%)")
                self.current_position_label.setText(f"当前位置: 第 {current} 条记录")
                self.completion_label.setText(f"完成度: {percentage:.1f}%")

    def dynamic_draw_step(self):
        """基于数据的动态绘制步骤"""
        if not self.real_trajectory_data:
            return

        # 根据数据线程的进度来同步绘制
        if self.data_thread and self.cage_id in self.data_thread.current_indices:
            target_index = self.data_thread.current_indices[self.cage_id]
        else:
            return

        # 绘制到目标索引
        while self.current_draw_index < target_index and self.current_draw_index < len(self.real_trajectory_data):
            try:
                current_point = self.real_trajectory_data[self.current_draw_index]

                # 获取坐标
                axis_map = {'x': 1, 'y': 2, 'z': 3}
                x_coord = current_point[axis_map[self.main_window.x_axis_combo.currentText()]]
                y_coord = current_point[axis_map[self.main_window.y_axis_combo.currentText()]]
                z_coord = current_point[3]

                # 添加到画布
                self.canvas_2d.add_dynamic_point(x_coord, y_coord,
                                                 self.main_window.x_axis_combo.currentText(),
                                                 self.main_window.y_axis_combo.currentText(),
                                                 self.current_draw_index)
                self.canvas_3d.add_dynamic_point(x_coord, y_coord, z_coord,
                                                 self.current_draw_index)

                self.current_draw_index += 1

                # 更新状态
                if self.total_data_points > 0:
                    progress = (self.current_draw_index / self.total_data_points) * 100
                    self.status_label.setText(
                        f"播放数据进度: {self.current_draw_index}/{self.total_data_points} ({progress:.1f}%)")

            except Exception as e:
                logger.error(f"绘制数据点失败: {e}")
                break

    def get_default_export_path(self):
        """获取默认的导出路径"""
        try:
            # 尝试获取桌面路径
            desktop_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
            if desktop_path and os.path.exists(desktop_path):
                export_dir = os.path.join(desktop_path, "轨迹图片导出")
            else:
                # 如果获取不到桌面路径，使用当前目录
                export_dir = os.path.join(os.getcwd(), "轨迹图片导出")

            # 创建导出目录
            os.makedirs(export_dir, exist_ok=True)
            return export_dir
        except Exception as e:
            logger.error(f"创建导出目录失败: {e}")
            return os.getcwd()

    def generate_filename(self, chart_type):
        """生成文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        axis_info = ""

        if chart_type == "2D" and hasattr(self.main_window, 'x_axis_combo'):
            x_axis = self.main_window.x_axis_combo.currentText()
            y_axis = self.main_window.y_axis_combo.currentText()
            axis_info = f"_{x_axis}{y_axis}"

        filename = f"鼠笼{self.cage_id}_{chart_type}轨迹{axis_info}_{timestamp}.png"
        return filename

    def export_2d_image(self):
        """导出2D轨迹图片"""
        try:
            # 获取默认路径和文件名
            default_dir = self.get_default_export_path()
            default_filename = self.generate_filename("2D")
            default_path = os.path.join(default_dir, default_filename)

            # 打开文件保存对话框
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出2D轨迹图片",
                default_path,
                "PNG图片 (*.png);;JPG图片 (*.jpg);;所有文件 (*.*)"
            )

            if file_path:
                # 暂停动态绘制
                timer_was_active = self.dynamic_timer.isActive()
                if timer_was_active:
                    self.dynamic_timer.stop()

                # 设置高分辨率
                original_dpi = self.canvas_2d.fig.dpi
                self.canvas_2d.fig.set_dpi(300)  # 设置高分辨率

                # 调整图片大小和布局
                self.canvas_2d.fig.set_size_inches(12, 10)  # 设置图片尺寸
                self.canvas_2d.fig.tight_layout(pad=2.0)  # 调整布局

                # 保存图片
                self.canvas_2d.fig.savefig(
                    file_path,
                    dpi=300,
                    bbox_inches='tight',
                    facecolor='white',
                    edgecolor='none',
                    format='png' if file_path.endswith('.png') else 'jpg'
                )

                # 恢复原始设置
                self.canvas_2d.fig.set_dpi(original_dpi)
                self.canvas_2d.fig.set_size_inches(7, 6)
                self.canvas_2d.fig.tight_layout()
                self.canvas_2d.draw()

                # 恢复动态绘制
                if timer_was_active:
                    self.dynamic_timer.start()

                QMessageBox.information(self, "导出成功", f"2D轨迹图已成功导出到:\n{file_path}")
                logger.info(f"2D轨迹图导出成功: {file_path}")

        except Exception as e:
            error_msg = f"导出2D轨迹图失败: {e}"
            QMessageBox.critical(self, "导出失败", error_msg)
            logger.error(error_msg)

    def export_3d_image(self):
        """导出3D轨迹图片"""
        try:
            # 获取默认路径和文件名
            default_dir = self.get_default_export_path()
            default_filename = self.generate_filename("3D")
            default_path = os.path.join(default_dir, default_filename)

            # 打开文件保存对话框
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出3D轨迹图片",
                default_path,
                "PNG图片 (*.png);;JPG图片 (*.jpg);;所有文件 (*.*)"
            )

            if file_path:
                # 暂停动态绘制
                timer_was_active = self.dynamic_timer.isActive()
                if timer_was_active:
                    self.dynamic_timer.stop()

                # 设置高分辨率
                original_dpi = self.canvas_3d.fig.dpi
                self.canvas_3d.fig.set_dpi(300)  # 设置高分辨率

                # 调整图片大小和布局
                self.canvas_3d.fig.set_size_inches(12, 10)  # 设置图片尺寸
                self.canvas_3d.fig.tight_layout(pad=2.0)  # 调整布局

                # 保存图片
                self.canvas_3d.fig.savefig(
                    file_path,
                    dpi=300,
                    bbox_inches='tight',
                    facecolor='white',
                    edgecolor='none',
                    format='png' if file_path.endswith('.png') else 'jpg'
                )

                # 恢复原始设置
                self.canvas_3d.fig.set_dpi(original_dpi)
                self.canvas_3d.fig.set_size_inches(7, 6)
                self.canvas_3d.fig.tight_layout()
                self.canvas_3d.draw()

                # 恢复动态绘制
                if timer_was_active:
                    self.dynamic_timer.start()

                QMessageBox.information(self, "导出成功", f"3D轨迹图已成功导出到:\n{file_path}")
                logger.info(f"3D轨迹图导出成功: {file_path}")

        except Exception as e:
            error_msg = f"导出3D轨迹图失败: {e}"
            QMessageBox.critical(self, "导出失败", error_msg)
            logger.error(error_msg)

    def export_all_images(self):
        """导出所有图片"""
        try:
            # 选择导出目录
            default_dir = self.get_default_export_path()
            export_dir = QFileDialog.getExistingDirectory(
                self,
                "选择导出目录",
                default_dir
            )

            if not export_dir:
                return

            # 暂停动态绘制
            timer_was_active = self.dynamic_timer.isActive()
            if timer_was_active:
                self.dynamic_timer.stop()

            exported_files = []

            # 导出2D图片
            try:
                filename_2d = self.generate_filename("2D")
                file_path_2d = os.path.join(export_dir, filename_2d)

                # 设置高分辨率
                original_dpi_2d = self.canvas_2d.fig.dpi
                self.canvas_2d.fig.set_dpi(300)
                self.canvas_2d.fig.set_size_inches(12, 10)
                self.canvas_2d.fig.tight_layout(pad=2.0)

                self.canvas_2d.fig.savefig(
                    file_path_2d,
                    dpi=300,
                    bbox_inches='tight',
                    facecolor='white',
                    edgecolor='none',
                    format='png'
                )

                # 恢复原始设置
                self.canvas_2d.fig.set_dpi(original_dpi_2d)
                self.canvas_2d.fig.set_size_inches(7, 6)
                self.canvas_2d.fig.tight_layout()
                self.canvas_2d.draw()

                exported_files.append(f"✅ 2D轨迹图: {filename_2d}")

            except Exception as e:
                exported_files.append(f"❌ 2D轨迹图导出失败: {e}")

            # 导出3D图片
            try:
                filename_3d = self.generate_filename("3D")
                file_path_3d = os.path.join(export_dir, filename_3d)

                # 设置高分辨率
                original_dpi_3d = self.canvas_3d.fig.dpi
                self.canvas_3d.fig.set_dpi(300)
                self.canvas_3d.fig.set_size_inches(12, 10)
                self.canvas_3d.fig.tight_layout(pad=2.0)

                self.canvas_3d.fig.savefig(
                    file_path_3d,
                    dpi=300,
                    bbox_inches='tight',
                    facecolor='white',
                    edgecolor='none',
                    format='png'
                )

                # 恢复原始设置
                self.canvas_3d.fig.set_dpi(original_dpi_3d)
                self.canvas_3d.fig.set_size_inches(7, 6)
                self.canvas_3d.fig.tight_layout()
                self.canvas_3d.draw()

                exported_files.append(f"✅ 3D轨迹图: {filename_3d}")

            except Exception as e:
                exported_files.append(f"❌ 3D轨迹图导出失败: {e}")

            # 恢复动态绘制
            if timer_was_active:
                self.dynamic_timer.start()

            # 显示导出结果
            result_message = f"批量导出完成！\n导出目录: {export_dir}\n\n导出结果:\n" + "\n".join(exported_files)
            QMessageBox.information(self, "批量导出完成", result_message)

            logger.info(f"批量导出完成: {export_dir}")

        except Exception as e:
            error_msg = f"批量导出失败: {e}"
            QMessageBox.critical(self, "导出失败", error_msg)
            logger.error(error_msg)

    def toggle_pause_resume(self):
        """切换暂停/恢复"""
        if not self.data_thread:
            return

        if self.data_thread.is_paused():
            self.data_thread.resume()
            self.play_pause_btn.setText("⏸️ 暂停")
            self.play_pause_btn.setStyleSheet("""
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
        else:
            self.data_thread.pause()
            self.play_pause_btn.setText("▶️ 播放")
            self.play_pause_btn.setStyleSheet("""
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

    def restart_drawing(self):
        """重新开始绘制"""
        self.current_draw_index = 0
        self.canvas_2d.init_plot()
        self.canvas_3d.init_plot()

        # 重置数据线程进度
        if self.data_thread:
            self.data_thread.current_indices[self.cage_id] = 0

        self.status_label.setText("重新开始播放数据...")

    def on_draw_speed_changed(self, value):
        """更改绘制速度"""
        self.dynamic_timer.setInterval(value)
        self.speed_label.setText(f"{value}ms")

        # 同时更新数据线程的播放速度
        if self.data_thread:
            self.data_thread.set_play_speed(value)

    def update_2d_view(self):
        """更新2D视图"""
        x_axis = self.x_axis_2d.currentText()
        y_axis = self.y_axis_2d.currentText()

        if x_axis == y_axis:
            self.status_label.setText("X轴和Y轴不能相同")
            return

        self.restart_drawing()

    def closeEvent(self, event):
        """窗口关闭事件"""
        if hasattr(self, 'dynamic_timer'):
            self.dynamic_timer.stop()

        if hasattr(self,'play_pause_btn'):
            self.play_pause_btn.setText("▶️ 播放")


        if self.main_window and hasattr(self.main_window, 'detail_windows'):
            if self.cage_id in self.main_window.detail_windows:
                del self.main_window.detail_windows[self.cage_id]
        event.accept()

