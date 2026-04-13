"""
3D 预览画布 - 用 QPainter 手写渲染，与 React Canvas 版本逻辑一致
支持鼠标拖拽旋转、滚轮缩放
"""
import math
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtWidgets import QWidget

LAYER_COLORS = {
    '1': (34, 197, 94),
    '2': (249, 115, 22),
    '3': (236, 72, 153),
    '4': (6, 182, 212),
}

# 鼠笼物理边界框顶点
_BOX_BOTTOM = [(-90, 0, 0), (90, 0, 0), (90, 310, 0), (-90, 310, 0)]
_BOX_TOP    = [(-90, 0, 150), (90, 0, 150), (90, 310, 150), (-90, 310, 150)]


class Canvas3D(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

        self.p3d: list = []          # [{'x3','y3','z3','label','is_manual_covered'}]
        self.lines3d: list = []      # [({'x3','y3','z3','label'}, {...})]
        self.solved_yolo: list = []  # [{'X','Y','Z_base','Z_total','mouseHeight'}]

        self._scale = 1.0
        self._cam_yaw = math.pi / 4
        self._cam_pitch = math.pi / 6
        self._panning = False
        self._last_pos = QPointF()

    def set_data(self, p3d: list, lines3d: list, solved_yolo: list = None):
        self.p3d = p3d or []
        self.lines3d = lines3d or []
        self.solved_yolo = solved_yolo or []
        self.update()

    # ------------------------------------------------------------------ 投影
    def _project(self, X: float, Y: float, Z: float) -> QPointF:
        cx = self.width() / 2
        cy = self.height() / 2 + 100
        x = X / 360
        y = (Y - 155) / 360
        z = (Z - 75) / 360
        x1 = x * math.cos(self._cam_yaw) - y * math.sin(self._cam_yaw)
        y1 = x * math.sin(self._cam_yaw) + y * math.cos(self._cam_yaw)
        y2 = y1 * math.cos(self._cam_pitch) + z * math.sin(self._cam_pitch)
        s = self._scale * min(self.width(), self.height()) * 0.8
        return QPointF(cx + x1 * s, cy - y2 * s)

    # ------------------------------------------------------------------ 鼠标
    def wheelEvent(self, e):
        factor = math.exp(-e.angleDelta().y() * 0.002)
        self._scale = max(0.05, min(15.0, self._scale * factor))
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._last_pos = e.position()

    def mouseMoveEvent(self, e):
        if self._panning:
            dx = e.position().x() - self._last_pos.x()
            dy = e.position().y() - self._last_pos.y()
            self._cam_yaw += dx * 0.005
            self._cam_pitch = max(-1.5, min(1.5, self._cam_pitch + dy * 0.005))
            self._last_pos = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        self._panning = False

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(15, 23, 42))

        # 边界框
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(4):
            b1 = self._project(*_BOX_BOTTOM[i])
            b2 = self._project(*_BOX_BOTTOM[(i + 1) % 4])
            t1 = self._project(*_BOX_TOP[i])
            t2 = self._project(*_BOX_TOP[(i + 1) % 4])
            painter.drawLine(b1, b2)
            painter.drawLine(t1, t2)
            painter.drawLine(b1, t1)

        # 网格线
        for p1, p2 in self.lines3d:
            r, g, b = LAYER_COLORS.get(p1.get('label', '1'), (255, 255, 255))
            painter.setPen(QPen(QColor(r, g, b, 178), 1))
            pt1 = self._project(p1['x3'], p1['y3'], p1['z3'])
            pt2 = self._project(p2['x3'], p2['y3'], p2['z3'])
            painter.drawLine(pt1, pt2)

        # 3D点
        for p in self.p3d:
            r, g, b = LAYER_COLORS.get(p.get('label', '1'), (255, 255, 255))
            pt = self._project(p['x3'], p['y3'], p['z3'])
            if p.get('is_manual_covered'):
                painter.setBrush(QBrush(QColor(r, g, b, 230)))
                painter.setPen(QPen(QColor(255, 255, 255, 204), 1.5))
                painter.drawEllipse(pt, 3.5, 3.5)
            else:
                painter.setBrush(QBrush(QColor(r, g, b, 178)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(pt, 2.0, 2.0)

        # YOLO解算结果
        for p in self.solved_yolo:
            b_pt = self._project(p['X'], p['Y'], p['Z_base'])
            t_pt = self._project(p['X'], p['Y'], p['Z_total'])
            pen = QPen(QColor(254, 240, 138, 153), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(b_pt, t_pt)
            painter.setBrush(QBrush(QColor(250, 204, 21)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(t_pt, 4.5, 4.5)
            painter.setPen(QColor(254, 240, 138))
            painter.setFont(QFont('Arial', 9))
            painter.drawText(QPointF(t_pt.x() + 10, t_pt.y() - 5),
                             f"H:{p.get('mouseHeight', 0):.1f}mm")

        # 提示文字
        if not self.p3d and not self.solved_yolo:
            painter.setPen(QColor(100, 116, 139))
            painter.setFont(QFont('Arial', 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             '暂无3D数据\n请先在图像模式下打点并补全网格')
