"""
2D 轨迹分析面板 - 用 QPainter 绘制 X-Y 俯视轨迹 + 高度变化曲线
"""
import math
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSizePolicy


class TrajectoryView(QWidget):
    """X-Y 俯视轨迹图"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: list = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: list):
        self.data = data or []
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(15, 23, 42))

        W, H = self.width(), self.height()
        pad_x, pad_y = 55, 35
        min_x, max_x = -100, 100
        min_y, max_y = -10, 320

        def map_x(x): return pad_x + (x - min_x) / (max_x - min_x) * (W - 2 * pad_x)
        def map_y(y): return H - pad_y - (y - min_y) / (max_y - min_y) * (H - 2 * pad_y)

        # 网格
        painter.setPen(QPen(QColor(30, 41, 59), 1))
        for x in [-90, -45, 0, 45, 90]:
            painter.drawLine(QPointF(map_x(x), map_y(min_y)), QPointF(map_x(x), map_y(max_y)))
        for y in [0, 100, 200, 310]:
            painter.drawLine(QPointF(map_x(min_x), map_y(y)), QPointF(map_x(max_x), map_y(y)))

        # 刻度
        painter.setPen(QColor(71, 85, 105))
        painter.setFont(QFont('Arial', 9))
        for x in [-90, 0, 90]:
            painter.drawText(QPointF(map_x(x) - 10, map_y(min_y) + 15), str(x))
        for y in [0, 100, 200, 310]:
            painter.drawText(QPointF(map_x(min_x) - 35, map_y(y) + 4), str(y))

        if not self.data:
            painter.setPen(QColor(100, 116, 139))
            painter.setFont(QFont('Arial', 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '暂无轨迹数据\n请先框选目标')
            return

        # 轨迹线
        painter.setPen(QPen(QColor(34, 211, 238, 178), 2))
        for i in range(len(self.data) - 1):
            d, nxt = self.data[i], self.data[i + 1]
            painter.drawLine(QPointF(map_x(d['X']), map_y(d['Y'])),
                             QPointF(map_x(nxt['X']), map_y(nxt['Y'])))

        # 点
        for i, d in enumerate(self.data):
            painter.setBrush(QBrush(QColor(250, 204, 21)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(map_x(d['X']), map_y(d['Y'])), 5, 5)
            painter.setPen(QColor(254, 240, 138))
            painter.setFont(QFont('Arial', 9, QFont.Weight.Bold))
            painter.drawText(QPointF(map_x(d['X']) + 8, map_y(d['Y']) - 8), str(i + 1))

        # 标题
        painter.setPen(QColor(34, 211, 238))
        painter.setFont(QFont('Arial', 10, QFont.Weight.Bold))
        painter.drawText(QPointF(pad_x, 20), '二维俯视轨迹 (X-Y 平面)')


class HeightCurveView(QWidget):
    """高度变化曲线图"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: list = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: list):
        self.data = data or []
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(15, 23, 42))

        W, H = self.width(), self.height()
        pad_x, pad_y = 55, 35
        min_x, max_x = -100, 100

        if self.data:
            heights = [d['mouseHeight'] for d in self.data]
            raw_max, raw_min = max(heights), min(heights)
            rng = (raw_max - raw_min) or 20
            max_h = min(150.0, raw_max + rng * 0.2)
            min_h = max(0.0, raw_min - rng * 0.2)
        else:
            max_h, min_h = 150.0, 0.0

        def map_x(x): return pad_x + (x - min_x) / (max_x - min_x) * (W - 2 * pad_x)
        def map_h(h): return H - pad_y - (h - min_h) / (max_h - min_h) * (H - 2 * pad_y)

        # 网格
        painter.setPen(QPen(QColor(30, 41, 59), 1))
        for i in range(6):
            h_val = min_h + i * (max_h - min_h) / 5
            painter.drawLine(QPointF(pad_x, map_h(h_val)), QPointF(W - pad_x, map_h(h_val)))
            painter.setPen(QColor(71, 85, 105))
            painter.setFont(QFont('Arial', 8))
            painter.drawText(QPointF(pad_x - 45, map_h(h_val) + 4), f'{h_val:.1f}')
            painter.setPen(QPen(QColor(30, 41, 59), 1))
        for x in [-90, -45, 0, 45, 90]:
            painter.drawLine(QPointF(map_x(x), pad_y), QPointF(map_x(x), H - pad_y))
            painter.setPen(QColor(71, 85, 105))
            painter.setFont(QFont('Arial', 8))
            painter.drawText(QPointF(map_x(x) - 10, H - pad_y + 15), str(x))
            painter.setPen(QPen(QColor(30, 41, 59), 1))

        if not self.data:
            painter.setPen(QColor(100, 116, 139))
            painter.setFont(QFont('Arial', 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '暂无高度数据')
            return

        # 折线
        pts = [QPointF(map_x(d['X']), map_h(d['mouseHeight'])) for d in self.data]
        painter.setPen(QPen(QColor(250, 204, 21), 3))
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])

        # 点 + 标注
        for i, (d, pt) in enumerate(zip(self.data, pts)):
            painter.setBrush(QBrush(QColor(52, 211, 238)))
            painter.setPen(QPen(QColor(15, 23, 42), 2))
            painter.drawEllipse(pt, 5, 5)
            painter.setPen(QColor(207, 250, 254))
            painter.setFont(QFont('Arial', 9, QFont.Weight.Bold))
            painter.drawText(QPointF(pt.x() - 15, pt.y() - 12), f'{d["mouseHeight"]:.1f}')

        # 标题
        painter.setPen(QColor(250, 204, 21))
        painter.setFont(QFont('Arial', 10, QFont.Weight.Bold))
        painter.drawText(QPointF(pad_x, 20), '高度变化曲线 (Height vs X)')


class Dashboard2D(QWidget):
    """2D 轨迹分析面板（左：俯视轨迹，右：高度曲线）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.trajectory_view = TrajectoryView()
        self.height_view = HeightCurveView()
        layout.addWidget(self.trajectory_view)
        layout.addWidget(self.height_view)

    def set_data(self, data: list):
        self.trajectory_view.set_data(data)
        self.height_view.set_data(data)
