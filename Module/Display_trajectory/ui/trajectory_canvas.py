import sys
import random
import math
import json
import numpy as np
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MouseDetection:
    """老鼠检测数据结构"""
    mouse_id: int
    x: float
    y: float
    confidence: float
    timestamp: datetime
    box_width: float = 0.0
    box_height: float = 0.0


class MouseDataProvider:
    """老鼠数据提供器基类"""

    def get_mouse_positions(self) -> List[MouseDetection]:
        """获取当前帧的老鼠位置数据"""
        raise NotImplementedError

    def start_detection(self):
        """开始检测"""
        pass

    def stop_detection(self):
        """停止检测"""
        pass

    def is_active(self) -> bool:
        """检查是否处于活动状态"""
        return False


class RandomMouseProvider(MouseDataProvider):
    """随机数据提供器（用于测试）"""

    def __init__(self, mouse_count: int = 1, canvas_width: int = 300, canvas_height: int = 200):
        self.mouse_count = mouse_count
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.active = False

        # 设置边界
        self.margin = 10
        self.min_x = self.margin
        self.max_x = canvas_width - self.margin
        self.min_y = self.margin
        self.max_y = canvas_height - self.margin

        # 初始化老鼠位置
        self.mouse_positions = []
        self._initialize_positions()

    def _initialize_positions(self):
        """初始化老鼠位置"""
        self.mouse_positions = []
        for i in range(self.mouse_count):
            x = random.uniform(self.min_x, self.max_x)
            y = random.uniform(self.min_y, self.max_y)
            self.mouse_positions.append([x, y])

    def get_mouse_positions(self) -> List[MouseDetection]:
        """获取随机生成的老鼠位置"""
        if not self.active:
            return []

        detections = []
        current_time = datetime.now()

        # 更新位置
        for i in range(len(self.mouse_positions)):
            # 随机移动
            dx = random.uniform(-5, 5)
            dy = random.uniform(-5, 5)

            new_x = self.mouse_positions[i][0] + dx
            new_y = self.mouse_positions[i][1] + dy

            # 边界检测和反弹
            if new_x <= self.min_x or new_x >= self.max_x:
                dx = -dx * 0.5
            if new_y <= self.min_y or new_y >= self.max_y:
                dy = -dy * 0.5

            new_x = max(self.min_x, min(self.max_x, self.mouse_positions[i][0] + dx))
            new_y = max(self.min_y, min(self.max_y, self.mouse_positions[i][1] + dy))

            self.mouse_positions[i] = [new_x, new_y]

            # 创建检测数据
            detection = MouseDetection(
                mouse_id=i,
                x=new_x,
                y=new_y,
                confidence=random.uniform(0.7, 0.95),
                timestamp=current_time,
                box_width=random.uniform(15, 25),
                box_height=random.uniform(15, 25)
            )
            detections.append(detection)

        return detections

    def start_detection(self):
        self.active = True

    def stop_detection(self):
        self.active = False

    def is_active(self) -> bool:
        return self.active


class YOLOMouseProvider(MouseDataProvider):
    """YOLO模型数据提供器"""

    def __init__(self, camera_id: int = 0, model_path: str = "", canvas_width: int = 300, canvas_height: int = 200):
        self.camera_id = camera_id
        self.model_path = model_path
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.active = False

        # YOLO相关变量（待实现）
        self.model = None
        self.cap = None
        self.frame_width = 640
        self.frame_height = 480

        # 老鼠追踪
        self.mouse_tracker = {}  # 用于追踪老鼠ID
        self.next_mouse_id = 0

    def _initialize_yolo(self):
        """初始化YOLO模型"""
        try:
            # TODO: 导入YOLO相关库
            # import cv2
            # from ultralytics import YOLO
            #
            # self.model = YOLO(self.model_path)
            # self.cap = cv2.VideoCapture(self.camera_id)
            #
            # if self.cap.isOpened():
            #     self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            #     self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            #     return True

            print(f"YOLO模型初始化 - 模型路径: {self.model_path}, 摄像头ID: {self.camera_id}")
            return False  # 暂时返回False，等实现时改为True

        except Exception as e:
            print(f"YOLO初始化失败: {e}")
            return False

    def _convert_coordinates(self, yolo_x: float, yolo_y: float) -> Tuple[float, float]:
        """将YOLO坐标转换为画布坐标"""
        # YOLO输出的是相对于原始图像的绝对坐标
        # 需要转换为画布坐标系
        canvas_x = (yolo_x / self.frame_width) * self.canvas_width
        canvas_y = (yolo_y / self.frame_height) * self.canvas_height

        # 确保在画布边界内
        margin = 10
        canvas_x = max(margin, min(self.canvas_width - margin, canvas_x))
        canvas_y = max(margin, min(self.canvas_height - margin, canvas_y))

        return canvas_x, canvas_y

    def _track_mice(self, detections) -> List[MouseDetection]:
        """简单的老鼠追踪算法"""
        current_time = datetime.now()
        tracked_detections = []

        # TODO: 实现更复杂的追踪算法（如卡尔曼滤波、匈牙利算法等）
        # 目前使用简单的最近邻匹配

        for detection in detections:
            # 转换坐标
            canvas_x, canvas_y = self._convert_coordinates(detection['x'], detection['y'])

            # 分配或更新老鼠ID
            mouse_id = self._assign_mouse_id(canvas_x, canvas_y)

            tracked_detection = MouseDetection(
                mouse_id=mouse_id,
                x=canvas_x,
                y=canvas_y,
                confidence=detection['confidence'],
                timestamp=current_time,
                box_width=detection.get('width', 20),
                box_height=detection.get('height', 20)
            )
            tracked_detections.append(tracked_detection)

        return tracked_detections

    def _assign_mouse_id(self, x: float, y: float) -> int:
        """分配或匹配老鼠ID"""
        # 简单的距离匹配
        min_distance = float('inf')
        assigned_id = None

        for mouse_id, last_pos in self.mouse_tracker.items():
            distance = math.sqrt((x - last_pos[0]) ** 2 + (y - last_pos[1]) ** 2)
            if distance < min_distance and distance < 50:  # 50像素阈值
                min_distance = distance
                assigned_id = mouse_id

        if assigned_id is None:
            # 分配新ID
            assigned_id = self.next_mouse_id
            self.next_mouse_id += 1

        # 更新位置
        self.mouse_tracker[assigned_id] = (x, y)
        return assigned_id

    def get_mouse_positions(self) -> List[MouseDetection]:
        """从YOLO模型获取老鼠位置"""
        if not self.active or self.model is None:
            return []

        try:
            # TODO: 实现YOLO检测
            # ret, frame = self.cap.read()
            # if not ret:
            #     return []
            #
            # # YOLO推理
            # results = self.model(frame)
            #
            # # 解析结果
            # detections = []
            # for result in results:
            #     for box in result.boxes:
            #         if box.cls == 0:  # 假设0是老鼠类别
            #             x, y, w, h = box.xywh[0].cpu().numpy()
            #             confidence = box.conf.cpu().numpy()[0]
            #
            #             detections.append({
            #                 'x': float(x),
            #                 'y': float(y),
            #                 'width': float(w),
            #                 'height': float(h),
            #                 'confidence': float(confidence)
            #             })
            #
            # return self._track_mice(detections)

            # 暂时返回空列表
            print("YOLO检测运行中...")
            return []

        except Exception as e:
            print(f"YOLO检测错误: {e}")
            return []

    def start_detection(self):
        """开始YOLO检测"""
        if self._initialize_yolo():
            self.active = True
            print("YOLO检测已启动")
        else:
            print("YOLO检测启动失败")

    def stop_detection(self):
        """停止YOLO检测"""
        self.active = False
        if self.cap is not None:
            # self.cap.release()
            pass
        print("YOLO检测已停止")

    def is_active(self) -> bool:
        return self.active


class TrajectoryCanvas(QWidget):
    """轨迹绘制画布"""

    def __init__(self, width=300, height=200):
        super().__init__()
        self.canvas_width = width
        self.canvas_height = height
        self.setFixedSize(width, height)

        # 数据提供器
        self.data_provider: Optional[MouseDataProvider] = None

        # 轨迹数据
        self.trajectory_points = {}  # mouse_id -> list of points
        self.mouse_positions = {}  # mouse_id -> current position
        self.mouse_confidence = {}  # mouse_id -> confidence

        # 设置画布边界
        self.margin = 10
        self.effective_width = width - 2 * self.margin
        self.effective_height = height - 2 * self.margin
        self.min_x = self.margin
        self.max_x = width - self.margin
        self.min_y = self.margin
        self.max_y = height - self.margin

        # 背景颜色
        self.setStyleSheet("background-color: #2D3748; border: 1px solid #4A5568;")

    def set_data_provider(self, provider: MouseDataProvider):
        """设置数据提供器"""
        if self.data_provider:
            self.data_provider.stop_detection()

        self.data_provider = provider
        self.clear_trajectory()

    def set_random_mode(self, mouse_count: int = 1):
        """设置随机模式"""
        provider = RandomMouseProvider(
            mouse_count=mouse_count,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height
        )
        self.set_data_provider(provider)

    def set_yolo_mode(self, camera_id: int = 0, model_path: str = ""):
        """设置YOLO模式"""
        provider = YOLOMouseProvider(
            camera_id=camera_id,
            model_path=model_path,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height
        )
        self.set_data_provider(provider)

    def update_mouse_positions(self):
        """更新老鼠位置"""
        if not self.data_provider:
            return

        # 获取检测数据
        detections = self.data_provider.get_mouse_positions()

        # 更新位置和轨迹
        current_mouse_ids = set()
        for detection in detections:
            mouse_id = detection.mouse_id
            current_mouse_ids.add(mouse_id)

            # 更新当前位置
            self.mouse_positions[mouse_id] = (detection.x, detection.y)
            self.mouse_confidence[mouse_id] = detection.confidence

            # 添加轨迹点
            if mouse_id not in self.trajectory_points:
                self.trajectory_points[mouse_id] = []

            self.trajectory_points[mouse_id].append([detection.x, detection.y])

            # 限制轨迹点数量
            if len(self.trajectory_points[mouse_id]) > 1000:
                self.trajectory_points[mouse_id] = self.trajectory_points[mouse_id][-500:]

        # 清理不再检测到的老鼠（可选）
        # 注意：YOLO可能有漏检，所以可能不需要立即清理
        # self._cleanup_missing_mice(current_mouse_ids)

    def clear_trajectory(self):
        """清除轨迹"""
        self.trajectory_points = {}
        self.mouse_positions = {}
        self.mouse_confidence = {}
        self.update()

    def start_tracking(self):
        """开始追踪"""
        if self.data_provider:
            self.data_provider.start_detection()

    def stop_tracking(self):
        """停止追踪"""
        if self.data_provider:
            self.data_provider.stop_detection()

    def is_tracking(self):
        """检查是否在追踪"""
        return self.data_provider and self.data_provider.is_active()

    def paintEvent(self, event):
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制背景网格
        self._draw_grid(painter)

        # 绘制边界
        self._draw_boundary(painter)

        # 绘制轨迹
        self._draw_trajectories(painter)

        # 绘制当前老鼠位置
        self._draw_mice(painter)

        # 绘制信息
        self._draw_info(painter)

    def _draw_grid(self, painter):
        """绘制网格"""
        pen = QPen(QColor(75, 85, 99), 1)
        painter.setPen(pen)

        grid_size = 20
        for x in range(self.min_x, self.max_x + 1, grid_size):
            painter.drawLine(x, self.min_y, x, self.max_y)
        for y in range(self.min_y, self.max_y + 1, grid_size):
            painter.drawLine(self.min_x, y, self.max_x, y)

    def _draw_boundary(self, painter):
        """绘制边界"""
        pen = QPen(QColor(255, 255, 255), 2)
        painter.setPen(pen)
        painter.drawRect(self.min_x, self.min_y,
                         self.effective_width, self.effective_height)

    def _draw_trajectories(self, painter):
        """绘制轨迹"""
        colors = [
            QColor(255, 99, 132),  # 红色
            QColor(54, 162, 235),  # 蓝色
            QColor(255, 205, 86),  # 黄色
            QColor(75, 192, 192),  # 青色
            QColor(153, 102, 255),  # 紫色
            QColor(255, 159, 64),  # 橙色
            QColor(199, 199, 199),  # 灰色
            QColor(83, 102, 255),  # 靛蓝
        ]

        for mouse_id, trajectory in self.trajectory_points.items():
            if len(trajectory) < 2:
                continue

            color = colors[mouse_id % len(colors)]
            pen = QPen(color, 2)
            painter.setPen(pen)

            # 绘制轨迹线
            for j in range(len(trajectory) - 1):
                x1, y1 = trajectory[j]
                x2, y2 = trajectory[j + 1]
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

    def _draw_mice(self, painter):
        """绘制老鼠当前位置"""
        colors = [
            QColor(255, 99, 132),  # 红色
            QColor(54, 162, 235),  # 蓝色
            QColor(255, 205, 86),  # 黄色
            QColor(75, 192, 192),  # 青色
            QColor(153, 102, 255),  # 紫色
            QColor(255, 159, 64),  # 橙色
            QColor(199, 199, 199),  # 灰色
            QColor(83, 102, 255),  # 靛蓝
        ]

        for mouse_id, pos in self.mouse_positions.items():
            color = colors[mouse_id % len(colors)]
            confidence = self.mouse_confidence.get(mouse_id, 1.0)

            # 根据置信度调整透明度
            alpha = int(255 * confidence)
            color.setAlpha(alpha)

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(), 2))

            x, y = pos
            painter.drawEllipse(int(x - 6), int(y - 6), 12, 12)

            # 绘制老鼠ID
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(int(x + 8), int(y - 8), f"#{mouse_id}")

    def _draw_info(self, painter):
        """绘制信息"""
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setFont(QFont("Arial", 9))

        info_text = f"老鼠数量: {len(self.mouse_positions)}"
        if self.data_provider:
            mode = "YOLO" if isinstance(self.data_provider, YOLOMouseProvider) else "随机"
            info_text += f" | 模式: {mode}"
            if self.data_provider.is_active():
                info_text += " | 运行中"
            else:
                info_text += " | 已停止"

        painter.drawText(10, self.canvas_height - 10, info_text)

    def get_trajectory_data(self):
        """获取轨迹数据"""
        return {
            'mouse_positions': dict(self.mouse_positions),
            'trajectories': dict(self.trajectory_points),
            'confidence': dict(self.mouse_confidence)
        }


class MouseCagePanel(QWidget):
    """单个笼子面板"""

    cage_status_changed = pyqtSignal(int, str)

    def __init__(self, cage_id=1, mouse_count=1):
        super().__init__()
        self.cage_id = cage_id
        self.mouse_count = mouse_count
        self.is_tracking_active = False

        self._init_ui()
        self._setup_timer()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        layout.setSpacing(5)

        # 标题
        title_label = QLabel(f"笼子 #{self.cage_id}")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 12pt;
                font-weight: bold;
                color: #E1E1E1;
                background-color: #4A5568;
                padding: 5px;
                border-radius: 4px;
                margin-bottom: 5px;
            }
        """)
        layout.addWidget(title_label)

        # 轨迹画布
        self.trajectory_canvas = TrajectoryCanvas(width=320, height=200)
        self.trajectory_canvas.set_random_mode(self.mouse_count)  # 默认使用随机模式
        layout.addWidget(self.trajectory_canvas)

        # 控制按钮
        button_layout = QHBoxLayout()

        self.start_btn = QPushButton("开始")
        self.stop_btn = QPushButton("暂停")
        self.clear_btn = QPushButton("清除")
        self.mode_btn = QPushButton("切换模式")

        button_style = """
            QPushButton {
                min-width: 50px;
                min-height: 25px;
                border-radius: 3px;
                font-size: 9pt;
                background-color: #4A5568;
                color: #E1E1E1;
                border: 1px solid #666;
            }
            QPushButton:hover {
                background-color: #5A6578;
            }
            QPushButton:pressed {
                background-color: #3A4558;
            }
        """

        for btn in [self.start_btn, self.stop_btn, self.clear_btn, self.mode_btn]:
            btn.setStyleSheet(button_style)

        self.start_btn.clicked.connect(self.start_tracking)
        self.stop_btn.clicked.connect(self.stop_tracking)
        self.clear_btn.clicked.connect(self.clear_trajectory)
        self.mode_btn.clicked.connect(self.toggle_mode)

        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.mode_btn)

        layout.addLayout(button_layout)

        # 状态标签
        self.status_label = QLabel("状态: 已停止 | 模式: 随机")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 9pt;
                color: #A0AEC0;
                padding: 2px;
            }
        """)
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        # 设置面板样式
        self.setStyleSheet("""
            MouseCagePanel {
                background-color: #2D3748;
                border: 2px solid #4A5568;
                border-radius: 8px;
                margin: 5px;
            }
        """)

    def _setup_timer(self):
        """设置定时器"""
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_tracking)
        self.timer.setInterval(100)  # 100ms更新一次

    def start_tracking(self):
        """开始追踪"""
        if not self.is_tracking_active:
            self.is_tracking_active = True
            self.trajectory_canvas.start_tracking()
            self.timer.start()
            self._update_status()
            self.cage_status_changed.emit(self.cage_id, "tracking")

    def stop_tracking(self):
        """停止追踪"""
        if self.is_tracking_active:
            self.is_tracking_active = False
            self.trajectory_canvas.stop_tracking()
            self.timer.stop()
            self._update_status()
            self.cage_status_changed.emit(self.cage_id, "stopped")

    def clear_trajectory(self):
        """清除轨迹"""
        self.trajectory_canvas.clear_trajectory()
        self._update_status()
        self.cage_status_changed.emit(self.cage_id, "cleared")

    def toggle_mode(self):
        """切换模式"""
        current_provider = self.trajectory_canvas.data_provider

        if isinstance(current_provider, RandomMouseProvider):
            # 切换到YOLO模式
            self.trajectory_canvas.set_yolo_mode(camera_id=0, model_path="yolo_mouse_model.pt")
        else:
            # 切换到随机模式
            self.trajectory_canvas.set_random_mode(self.mouse_count)

        self._update_status()

    def _update_status(self):
        """更新状态显示"""
        status = "运行中" if self.is_tracking_active else "已停止"

        provider = self.trajectory_canvas.data_provider
        if isinstance(provider, YOLOMouseProvider):
            mode = "YOLO"
        elif isinstance(provider, RandomMouseProvider):
            mode = "随机"
        else:
            mode = "未知"

        self.status_label.setText(f"状态: {status} | 模式: {mode}")

    def _update_tracking(self):
        """更新追踪数据"""
        if self.is_tracking_active:
            self.trajectory_canvas.update_mouse_positions()
            self.trajectory_canvas.update()

    def set_yolo_config(self, camera_id: int = 0, model_path: str = ""):
        """设置YOLO配置"""
        self.trajectory_canvas.set_yolo_mode(camera_id, model_path)
        self._update_status()

    def get_trajectory_data(self):
        """获取轨迹数据"""
        return {
            'cage_id': self.cage_id,
            'is_tracking': self.is_tracking_active,
            'trajectory_data': self.trajectory_canvas.get_trajectory_data()
        }

