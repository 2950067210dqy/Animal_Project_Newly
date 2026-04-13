"""
图像画布组件 - 支持打点、YOLO框选、区域绘制、平移缩放
"""
import math
from PyQt6.QtCore import Qt, QPointF, pyqtSignal, QRectF
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QPixmap,
                          QFont, QPolygonF, QTransform)
from PyQt6.QtWidgets import QWidget

LAYER_COLORS = {
    '1': QColor(34, 197, 94),
    '2': QColor(249, 115, 22),
    '3': QColor(236, 72, 153),
    '4': QColor(6, 182, 212),
}


class ImageCanvas(QWidget):
    point_added = pyqtSignal(dict)
    point_deleted = pyqtSignal(str)
    yolo_box_added = pyqtSignal(dict)
    yolo_box_deleted = pyqtSignal(str)
    region_point_added = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pixmap: QPixmap = None
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._panning = False
        self._last_pan_pos = QPointF()

        # 数据
        self.points: list = []        # [{'id', 'x', 'y', 'label'}]
        self.grid_data: list = []     # [{'id', 'x', 'y', 'label', 'c', 'r', 'is_manual_covered'}]
        self.yolo_boxes: list = []    # [{'id', 'startX', 'startY', 'endX', 'endY', ...solved}]
        self.regions: list = []       # [{'id', 'name', 'height', 'y_val', 'points': [...]}]
        self.current_region_pts: list = []
        self.solved_yolo: list = []   # 解算后的yolo数据

        # 绘制中的yolo框
        self._drawing_yolo: dict = None
        self._dragging_id: str = None

        # 工具模式: 'add' | 'move' | 'delete' | 'pan' | 'yolo' | 'region'
        self.tool_mode = 'add'
        self.active_label = '1'
        self.point_opacity = 0.8

    # ------------------------------------------------------------------ 数据
    def set_image(self, pixmap: QPixmap):
        self._pixmap = pixmap
        if pixmap:
            sw = self.width() / pixmap.width()
            sh = self.height() / pixmap.height()
            self._scale = min(sw, sh, 1.0)
            self._offset = QPointF(
                (self.width() - pixmap.width() * self._scale) / 2,
                (self.height() - pixmap.height() * self._scale) / 2
            )
        self.update()

    def clear_all(self):
        self.points.clear()
        self.grid_data.clear()
        self.yolo_boxes.clear()
        self.regions.clear()
        self.current_region_pts.clear()
        self.solved_yolo.clear()
        self._drawing_yolo = None
        self.update()

    # ------------------------------------------------------------------ 坐标转换
    def _to_image(self, screen_pt: QPointF) -> QPointF:
        return QPointF(
            (screen_pt.x() - self._offset.x()) / self._scale,
            (screen_pt.y() - self._offset.y()) / self._scale
        )

    def _to_screen(self, img_pt: QPointF) -> QPointF:
        return QPointF(
            img_pt.x() * self._scale + self._offset.x(),
            img_pt.y() * self._scale + self._offset.y()
        )

    # ------------------------------------------------------------------ 鼠标事件
    def wheelEvent(self, e):
        factor = math.exp(-e.angleDelta().y() * 0.002)
        mouse_pos = e.position()
        img_x = (mouse_pos.x() - self._offset.x()) / self._scale
        img_y = (mouse_pos.y() - self._offset.y()) / self._scale
        self._scale = max(0.05, min(15.0, self._scale * factor))
        self._offset = QPointF(
            mouse_pos.x() - img_x * self._scale,
            mouse_pos.y() - img_y * self._scale
        )
        self.update()

    def mousePressEvent(self, e):
        pos = e.position()
        img_pos = self._to_image(pos)
        pt = {'x': img_pos.x(), 'y': img_pos.y()}

        if self.tool_mode == 'pan' or e.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_pan_pos = pos
            return

        if e.button() != Qt.MouseButton.LeftButton:
            return

        if self.tool_mode == 'region':
            self.current_region_pts.append({'x': pt['x'], 'y': pt['y']})
            self.region_point_added.emit({'x': pt['x'], 'y': pt['y']})
            self.update()
            return

        if self.tool_mode == 'yolo':
            self._drawing_yolo = {'startX': pt['x'], 'startY': pt['y'],
                                   'currentX': pt['x'], 'currentY': pt['y']}
            return

        if self.tool_mode == 'move':
            threshold = 15 / self._scale
            for p in self.points:
                if p.get('label') == self.active_label:
                    if math.hypot(p['x'] - pt['x'], p['y'] - pt['y']) < threshold:
                        self._dragging_id = p['id']
                        return
            for p in self.grid_data:
                if p.get('label') == self.active_label:
                    if math.hypot(p['x'] - pt['x'], p['y'] - pt['y']) < threshold:
                        self._dragging_id = p['id']
                        return
            return

        if self.tool_mode == 'delete':
            threshold = 15 / self._scale
            self.points = [p for p in self.points if not (
                p.get('label') == self.active_label and
                math.hypot(p['x'] - pt['x'], p['y'] - pt['y']) < threshold
            )]
            self.grid_data = [p for p in self.grid_data if not (
                p.get('label') == self.active_label and
                math.hypot(p['x'] - pt['x'], p['y'] - pt['y']) < threshold
            )]
            # 删除yolo框
            self.yolo_boxes = [b for b in self.yolo_boxes if not (
                min(b['startX'], b['endX']) <= pt['x'] <= max(b['startX'], b['endX']) and
                min(b['startY'], b['endY']) <= pt['y'] <= max(b['startY'], b['endY'])
            )]
            self.update()
            return

        if self.tool_mode == 'add':
            import time
            new_pt = {'id': str(time.time_ns()), 'x': pt['x'], 'y': pt['y'], 'label': self.active_label}
            self.points.append(new_pt)
            self.point_added.emit(new_pt)
            self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._panning:
            dx = pos.x() - self._last_pan_pos.x()
            dy = pos.y() - self._last_pan_pos.y()
            self._offset += QPointF(dx, dy)
            self._last_pan_pos = pos
            self.update()
            return

        img_pos = self._to_image(pos)
        pt = {'x': img_pos.x(), 'y': img_pos.y()}

        if self._drawing_yolo:
            self._drawing_yolo['currentX'] = pt['x']
            self._drawing_yolo['currentY'] = pt['y']
            self.update()
            return

        if self._dragging_id and self.tool_mode == 'move':
            for p in self.points:
                if p['id'] == self._dragging_id:
                    p['x'] = pt['x']; p['y'] = pt['y']
            for p in self.grid_data:
                if p['id'] == self._dragging_id:
                    p['x'] = pt['x']; p['y'] = pt['y']
            self.update()

    def mouseReleaseEvent(self, e):
        if self._panning:
            self._panning = False
            return
        if self._drawing_yolo:
            import time
            box = self._drawing_yolo
            if abs(box['startX'] - box['currentX']) > 5:
                new_box = {
                    'id': str(time.time_ns()),
                    'startX': box['startX'], 'startY': box['startY'],
                    'endX': box['currentX'], 'endY': box['currentY']
                }
                self.yolo_boxes.append(new_box)
                self.yolo_box_added.emit(new_box)
            self._drawing_yolo = None
            self.update()
        self._dragging_id = None

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        painter.fillRect(self.rect(), QColor(15, 23, 42))

        if not self._pixmap:
            painter.setPen(QColor(100, 116, 139))
            painter.setFont(QFont('Arial', 14))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '请载入底图')
            return

        # 图像
        painter.save()
        painter.translate(self._offset)
        painter.scale(self._scale, self._scale)
        painter.drawPixmap(0, 0, self._pixmap)

        # 网格线
        self._draw_grid_lines(painter)

        # 网格点（补全点）
        for p in self.grid_data:
            if p.get('is_manual_covered'):
                continue
            color = LAYER_COLORS.get(p.get('label', '1'), QColor(255, 255, 255))
            alpha = int(self.point_opacity * (255 if p.get('label') == self.active_label else 90))
            color.setAlpha(alpha)
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor(0, 0, 0, int(self.point_opacity * 128)), 1 / self._scale))
            r = 3.5 / self._scale
            painter.drawEllipse(QPointF(p['x'], p['y']), r, r)

        # 手动打点
        for p in self.points:
            color = LAYER_COLORS.get(p.get('label', '1'), QColor(255, 255, 255))
            alpha = int(min(255, self.point_opacity * 255 + (51 if p.get('label') == self.active_label else 0)))
            color.setAlpha(alpha)
            painter.setBrush(QBrush(color))
            pen_alpha = 255 if p.get('label') == self.active_label else 153
            painter.setPen(QPen(QColor(255, 255, 255, pen_alpha), 1.5 / self._scale))
            r = 4.5 / self._scale
            painter.drawEllipse(QPointF(p['x'], p['y']), r, r)

        # YOLO框 + 解算结果
        for box in self.solved_yolo:
            painter.setPen(QPen(QColor(250, 204, 21), 2 / self._scale))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            x1 = min(box['startX'], box['endX'])
            y1 = min(box['startY'], box['endY'])
            w = abs(box['endX'] - box['startX'])
            h = abs(box['endY'] - box['startY'])
            painter.drawRect(QRectF(x1, y1, w, h))
            # 中心点
            painter.setBrush(QBrush(QColor(52, 211, 238)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(box.get('cx', 0), box.get('cy', 0)), 5 / self._scale, 5 / self._scale)
            # 高度标注
            painter.setPen(QColor(254, 240, 138))
            painter.setFont(QFont('Arial', max(8, int(11 / self._scale))))
            painter.drawText(QPointF(box.get('cx', 0) + 8 / self._scale, box.get('cy', 0) - 10 / self._scale),
                             f"鼠高:{box.get('mouseHeight', 0):.1f}mm")

        # 区域
        for region in self.regions:
            pts = region.get('points', [])
            if len(pts) < 3:
                continue
            poly = QPolygonF([QPointF(p['x'], p['y']) for p in pts])
            painter.setBrush(QBrush(QColor(168, 85, 247, 38)))
            painter.setPen(QPen(QColor(168, 85, 247, 153), 2 / self._scale))
            painter.drawPolygon(poly)
            painter.setPen(QColor(192, 132, 252))
            painter.setFont(QFont('Arial', max(8, int(12 / self._scale))))
            painter.drawText(QPointF(pts[0]['x'], pts[0]['y'] - 5 / self._scale),
                             f"{region['name']} (Z:{region['height']}mm)")

        # 正在绘制的区域
        if self.current_region_pts:
            poly = QPolygonF([QPointF(p['x'], p['y']) for p in self.current_region_pts])
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(168, 85, 247, 204), 2 / self._scale))
            painter.drawPolyline(poly)
            for p in self.current_region_pts:
                painter.setBrush(QBrush(QColor(168, 85, 247)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(p['x'], p['y']), 4 / self._scale, 4 / self._scale)

        # 正在绘制的YOLO框
        if self._drawing_yolo:
            b = self._drawing_yolo
            painter.setPen(QPen(QColor(254, 240, 138), 2 / self._scale, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            x1 = min(b['startX'], b['currentX'])
            y1 = min(b['startY'], b['currentY'])
            painter.drawRect(QRectF(x1, y1, abs(b['currentX'] - b['startX']), abs(b['currentY'] - b['startY'])))

        painter.restore()

    def _draw_grid_lines(self, painter: QPainter):
        """绘制网格连线"""
        from collections import defaultdict
        by_label = defaultdict(list)
        for p in self.grid_data:
            by_label[p.get('label', '1')].append(p)

        for lbl, pts in by_label.items():
            color = LAYER_COLORS.get(lbl, QColor(255, 255, 255))
            alpha = int(self.point_opacity * (179 if lbl == self.active_label else 89))
            color.setAlpha(alpha)
            lw = (2 if lbl == self.active_label else 1) / self._scale
            painter.setPen(QPen(color, lw))

            pt_lookup = {(p['c'], p['r']): p for p in pts if p.get('c') is not None}
            for (c, r), p1 in pt_lookup.items():
                for dc, dr in [(1, 0), (0, 1)]:
                    p2 = pt_lookup.get((c + dc, r + dr))
                    if p2:
                        painter.drawLine(QPointF(p1['x'], p1['y']), QPointF(p2['x'], p2['y']))
