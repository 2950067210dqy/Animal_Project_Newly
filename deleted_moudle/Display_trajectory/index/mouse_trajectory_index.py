from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QFont
import random
import math
from datetime import datetime

from public.entity import BaseWidget
from public.config_class.global_setting import global_setting


class TrajectoryCanvas(BaseWidget):
    """单个老鼠轨迹绘制画布"""

    mouse_position_changed = pyqtSignal(int, float, float)  # mouse_id, x, y

    def __init__(self, mouse_id, mouse_name="Mouse", parent=None):
        super().__init__(parent)
        self.mouse_id = mouse_id
        self.mouse_name = mouse_name
        self.trajectory_points = []  # 存储轨迹点 [(x, y, timestamp), ...]
        self.current_position = QPointF(0, 0)
        self.is_tracking = False
        self.canvas_width = 400
        self.canvas_height = 300

        # 模拟老鼠运动参数
        self.speed = random.uniform(1.0, 2.0)  # 随机速度
        self.direction = random.uniform(0, 2 * math.pi)  # 随机方向
        self.direction_change_probability = 1  # 方向改变概率

        # 设置固定大小
        self.setFixedSize(self.canvas_width, self.canvas_height)

        # 初始化位置
        self.current_position = QPointF(
            random.uniform(50, self.canvas_width - 50),
            random.uniform(50, self.canvas_height - 50)
        )

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        self.setMinimumSize(self.canvas_width, self.canvas_height)

    def start_tracking(self):
        """开始轨迹追踪"""
        self.is_tracking = True
        self.trajectory_points.clear()
        self.update()

    def stop_tracking(self):
        """停止轨迹追踪"""
        self.is_tracking = False

    def clear_trajectory(self):
        """清除轨迹"""
        self.trajectory_points.clear()
        self.update()

    def update_mouse_position(self):
        """更新老鼠位置（模拟运动）"""
        if not self.is_tracking:
            return

        # 随机改变方向
        if random.random() < self.direction_change_probability:
            self.direction += random.uniform(-0.5, 0.5)

        # 计算新位置
        dx = self.speed * math.cos(self.direction)
        dy = self.speed * math.sin(self.direction)

        new_x = self.current_position.x() + dx
        new_y = self.current_position.y() + dy

        # 边界检测和反弹
        if new_x <= 10 or new_x >= self.canvas_width - 10:
            self.direction = math.pi - self.direction
            new_x = max(10, min(self.canvas_width - 10, new_x))

        if new_y <= 10 or new_y >= self.canvas_height - 10:
            self.direction = -self.direction
            new_y = max(10, min(self.canvas_height - 10, new_y))

        self.current_position = QPointF(new_x, new_y)

        # 添加轨迹点
        timestamp = datetime.now()
        self.trajectory_points.append((new_x, new_y, timestamp))

        # 限制轨迹点数量（保留最近1000个点）
        if len(self.trajectory_points) > 1000:
            self.trajectory_points = self.trajectory_points[-1000:]

        # 发送位置变化信号
        self.mouse_position_changed.emit(self.mouse_id, new_x, new_y)

        self.update()

    def paintEvent(self, event):
        """绘制事件"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 获取当前主题颜色
        theme_manager = global_setting.get_setting("theme_manager")
        if theme_manager:
            theme_colors = theme_manager.get_themes_color()
            text_color = QColor(theme_colors['--text'])
            border_color = QColor(theme_colors['--border'])
            highlight_color = QColor(theme_colors['--highlight'])
        else:
            text_color = QColor('#E1E1E1')
            border_color = QColor('#555555')
            highlight_color = QColor('#1B2431')

        # 绘制边框
        painter.setPen(QPen(border_color, 2))
        painter.drawRect(1, 1, self.canvas_width - 2, self.canvas_height - 2)

        # 绘制标题
        painter.setPen(text_color)
        painter.setFont(QFont('Arial', 10))
        painter.drawText(10, 20, f"{self.mouse_name} (ID: {self.mouse_id})")

        # 绘制轨迹线
        if len(self.trajectory_points) > 1:
            trajectory_color = QColor(85, 170, 255, 180)  # 半透明蓝色
            painter.setPen(QPen(trajectory_color, 2))

            for i in range(1, len(self.trajectory_points)):
                prev_point = self.trajectory_points[i - 1]
                curr_point = self.trajectory_points[i]
                painter.drawLine(
                    QPointF(prev_point[0], prev_point[1]),
                    QPointF(curr_point[0], curr_point[1])
                )

        # 绘制老鼠当前位置
        if self.is_tracking:
            mouse_color = QColor(255, 100, 100)  # 红色
        else:
            mouse_color = QColor(150, 150, 150)  # 灰色

        painter.setPen(QPen(mouse_color, 2))
        painter.setBrush(mouse_color)
        painter.drawEllipse(
            self.current_position.x() - 5,
            self.current_position.y() - 5,
            10, 10
        )

        # 显示坐标
        painter.setPen(text_color)
        painter.setFont(QFont('Arial', 8))
        coord_text = f"({self.current_position.x():.1f}, {self.current_position.y():.1f})"
        painter.drawText(10, self.canvas_height - 10, coord_text)

        # 显示轨迹点数量
        if self.trajectory_points:
            point_count_text = f"轨迹点: {len(self.trajectory_points)}"
            painter.drawText(10, self.canvas_height - 25, point_count_text)


class MouseCagePanel(BaseWidget):
    """单个老鼠笼面板"""

    def __init__(self, cage_id, mouse_count=1, parent=None):
        super().__init__(parent)
        self.cage_id = cage_id
        self.mouse_count = mouse_count
        self.trajectory_canvases = []
        self.tracking_timer = QTimer()
        self.tracking_timer.timeout.connect(self._update_all_mice)
        self.tracking_timer.setInterval(50)  # 50ms更新一次

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()

        # 笼子标题和控制按钮
        header_layout = QHBoxLayout()

        cage_label = QLabel(f"笼子 #{self.cage_id} ({self.mouse_count} 只老鼠)")
        cage_label.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        header_layout.addWidget(cage_label)

        header_layout.addStretch()

        # 控制按钮
        self.start_btn = QPushButton("开始追踪")
        self.stop_btn = QPushButton("停止追踪")
        self.clear_btn = QPushButton("清除轨迹")

        self.start_btn.clicked.connect(self.start_tracking)
        self.stop_btn.clicked.connect(self.stop_tracking)
        self.clear_btn.clicked.connect(self.clear_trajectory)

        header_layout.addWidget(self.start_btn)
        header_layout.addWidget(self.stop_btn)
        header_layout.addWidget(self.clear_btn)

        layout.addLayout(header_layout)

        # 创建轨迹画布网格
        canvas_layout = self._create_canvas_grid()
        layout.addLayout(canvas_layout)

        self.setLayout(layout)

    def _create_canvas_grid(self):
        """创建轨迹画布网格布局"""
        if self.mouse_count == 1:
            layout = QHBoxLayout()
            canvas = TrajectoryCanvas(1, f"笼子{self.cage_id}-老鼠1")
            canvas.mouse_position_changed.connect(self._on_mouse_position_changed)
            self.trajectory_canvases.append(canvas)
            layout.addWidget(canvas)
            return layout
        elif self.mouse_count == 2:
            layout = QHBoxLayout()
            for i in range(2):
                canvas = TrajectoryCanvas(i + 1, f"笼子{self.cage_id}-老鼠{i + 1}")
                canvas.mouse_position_changed.connect(self._on_mouse_position_changed)
                self.trajectory_canvases.append(canvas)
                layout.addWidget(canvas)
            return layout
        else:
            # 多于2只老鼠时，使用网格布局
            from PyQt6.QtWidgets import QGridLayout
            layout = QGridLayout()
            cols = 2 if self.mouse_count <= 4 else 3

            for i in range(self.mouse_count):
                canvas = TrajectoryCanvas(i + 1, f"笼子{self.cage_id}-老鼠{i + 1}")
                canvas.mouse_position_changed.connect(self._on_mouse_position_changed)
                self.trajectory_canvases.append(canvas)
                layout.addWidget(canvas, i // cols, i % cols)

            return layout

    def start_tracking(self):
        """开始追踪所有老鼠"""
        for canvas in self.trajectory_canvases:
            canvas.start_tracking()
        self.tracking_timer.start()

    def stop_tracking(self):
        """停止追踪所有老鼠"""
        self.tracking_timer.stop()
        for canvas in self.trajectory_canvases:
            canvas.stop_tracking()

    def clear_trajectory(self):
        """清除所有轨迹"""
        for canvas in self.trajectory_canvases:
            canvas.clear_trajectory()

    def _update_all_mice(self):
        """更新所有老鼠位置"""
        for canvas in self.trajectory_canvases:
            canvas.update_mouse_position()

    def _on_mouse_position_changed(self, mouse_id, x, y):
        """老鼠位置变化回调"""
        # 这里可以添加位置数据的处理逻辑
        pass