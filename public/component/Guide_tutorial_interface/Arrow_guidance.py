import sys
import math
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *


class ArrowOverlayWidget(QWidget):
    """优化的箭头引导"""

    def __init__(self, target_widget, text, parent=None):
        super().__init__(parent)
        self.target_widget = target_widget
        self.text = text
        self.parent_window = parent
        self.arrow_direction = "bottom"

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 监听父窗口的大小变化
        if parent:
            parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        """监听父窗口事件"""
        if obj == self.parent_window and event.type() == QEvent.Type.Resize:
            self.resize(self.parent_window.size())
            self.move(0, 0)
            self.update()
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # 绘制更透明的遮罩 (从150改为70)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

            # 检查目标控件是否仍然可见
            if not self.target_widget or not self.target_widget.isVisible():
                return

            # 获取目标控件的位置和大小
            target_rect = self.target_widget.geometry()
            global_pos = self.target_widget.mapToGlobal(QPoint(0, 0))
            local_pos = self.mapFromGlobal(global_pos)
            highlight_rect = QRect(local_pos, target_rect.size())

            # 确保高亮区域在窗口范围内
            highlight_rect = highlight_rect.intersected(self.rect())

            if highlight_rect.isEmpty():
                return

            # 计算文字区域和箭头方向 - 增大文字区域
            text_rect, arrow_direction = self.calculate_text_position_and_arrow(highlight_rect)
            self.arrow_direction = arrow_direction

            # 清除高亮区域 - 扩大清除范围
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            expanded_highlight = highlight_rect.adjusted(-10, -10, 10, 10)
            painter.fillRect(expanded_highlight,Qt.GlobalColor.transparent)  # 使用半透明黑色

            # 绘制高亮边框
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            self.draw_highlight_effect(painter, highlight_rect)

            # 绘制文字气泡和箭头
            self.draw_speech_bubble(painter, text_rect, highlight_rect, arrow_direction)

        except Exception as e:
            print(f"绘制错误: {e}")

    def draw_highlight_effect(self, painter, rect):
        """绘制高亮发光效果"""
        try:
            # 外层发光
            for i in range(12, 0, -1):
                alpha = max(0, min(100, 40 - i * 2))  # 降低发光透明度
                pen = QPen(QColor(0, 150, 255, alpha), i)
                painter.setPen(pen)
                expanded_rect = rect.adjusted(-i // 2, -i // 2, i // 2, i // 2)
                painter.drawRoundedRect(expanded_rect, 6, 6)

            # 主边框
            pen = QPen(QColor(0, 150, 255, 255), 3)
            painter.setPen(pen)
            painter.drawRoundedRect(rect, 6, 6)
        except Exception as e:
            print(f"高亮效果绘制错误: {e}")

    def calculate_text_position_and_arrow(self, highlight_rect):
        """计算文字位置和箭头方向 - 动态调整文字区域"""
        try:
            window_rect = self.rect()
            margin = 25

            # 根据文字内容计算合适的文字区域大小
            lines = self.text.split('\n')
            text_width = 350
            text_height = 50 * len(lines) + 50  # 每行50px, 加上上下边距

            # 计算各个方向的可用空间
            space_below = window_rect.bottom() - highlight_rect.bottom()
            space_above = highlight_rect.top()
            space_right = window_rect.right() - highlight_rect.right()
            space_left = highlight_rect.left()

            # 优先级：下方 -> 上方 -> 右侧 -> 左侧
            if space_below >= text_height + margin:
                x = max(margin, min(highlight_rect.center().x() - text_width // 2,
                                    window_rect.width() - text_width - margin))
                y = highlight_rect.bottom() + margin
                return QRect(x, y, text_width, text_height), "up"

            elif space_above >= text_height + margin:
                x = max(margin, min(highlight_rect.center().x() - text_width // 2,
                                    window_rect.width() - text_width - margin))
                y = highlight_rect.top() - text_height - margin
                return QRect(x, y, text_width, text_height), "down"

            elif space_right >= text_width + margin:
                x = highlight_rect.right() + margin
                y = max(margin, min(highlight_rect.center().y() - text_height // 2,
                                    window_rect.height() - text_height - margin))
                return QRect(x, y, text_width, text_height), "left"

            else:
                # 默认放在左侧或者可用空间最大的地方
                x = max(margin, highlight_rect.left() - text_width - margin)
                y = max(margin, min(highlight_rect.center().y() - text_height // 2,
                                    window_rect.height() - text_height - margin))
                return QRect(x, y, text_width, text_height), "right"

        except Exception as e:
            print(f"位置计算错误: {e}")
            # 返回默认位置
            return QRect(50, 50, 350, 140), "down"

    def draw_speech_bubble(self, painter, text_rect, highlight_rect, arrow_direction):
        """绘制语音气泡和箭头"""
        try:
            bubble_color = QColor(255, 255, 255, 250)  # 更不透明的背景
            border_color = QColor(0, 150, 255, 200)

            # 创建气泡路径
            bubble_path = QPainterPath()
            corner_radius = 15  # 增大圆角
            arrow_size = 18  # 增大箭头

            # 根据箭头方向调整气泡形状
            adjusted_rect = QRectF(text_rect)

            if arrow_direction == "up":
                adjusted_rect.setTop(adjusted_rect.top() + arrow_size)
            elif arrow_direction == "down":
                adjusted_rect.setBottom(adjusted_rect.bottom() - arrow_size)
            elif arrow_direction == "left":
                adjusted_rect.setLeft(adjusted_rect.left() + arrow_size)
            elif arrow_direction == "right":
                adjusted_rect.setRight(adjusted_rect.right() - arrow_size)

            # 绘制圆角矩形气泡
            bubble_path.addRoundedRect(adjusted_rect, corner_radius, corner_radius)

            # 计算并添加箭头
            arrow_points = self.calculate_arrow_points(text_rect, highlight_rect, arrow_direction, arrow_size)
            if arrow_points:
                arrow_path = QPainterPath()
                arrow_path.addPolygon(QPolygonF(arrow_points))
                bubble_path = bubble_path.united(arrow_path)

            # 绘制气泡阴影
            shadow_path = QPainterPath(bubble_path)
            shadow_transform = QTransform()
            shadow_transform.translate(4, 4)
            shadow_path = shadow_transform.map(shadow_path)
            painter.fillPath(shadow_path, QColor(0, 0, 0, 60))

            # 绘制气泡主体
            painter.fillPath(bubble_path, bubble_color)
            painter.strokePath(bubble_path, QPen(border_color, 2))

            # 绘制文字
            self.draw_text_content(painter, adjusted_rect)

        except Exception as e:
            print(f"气泡绘制错误: {e}")

    def calculate_arrow_points(self, text_rect, highlight_rect, direction, arrow_size):
        """计算箭头的三个顶点"""
        try:
            if direction == "up":
                tip_x = max(text_rect.left() + 30,
                            min(highlight_rect.center().x(), text_rect.right() - 30))
                tip_y = text_rect.top()
                base_y = text_rect.top() + arrow_size
                return [
                    QPointF(tip_x, tip_y),
                    QPointF(tip_x - arrow_size, base_y),
                    QPointF(tip_x + arrow_size, base_y)
                ]
            elif direction == "down":
                tip_x = max(text_rect.left() + 30,
                            min(highlight_rect.center().x(), text_rect.right() - 30))
                tip_y = text_rect.bottom()
                base_y = text_rect.bottom() - arrow_size
                return [
                    QPointF(tip_x, tip_y),
                    QPointF(tip_x - arrow_size, base_y),
                    QPointF(tip_x + arrow_size, base_y)
                ]
            elif direction == "left":
                tip_y = max(text_rect.top() + 30,
                            min(highlight_rect.center().y(), text_rect.bottom() - 30))
                tip_x = text_rect.left()
                base_x = text_rect.left() + arrow_size
                return [
                    QPointF(tip_x, tip_y),
                    QPointF(base_x, tip_y - arrow_size),
                    QPointF(base_x, tip_y + arrow_size)
                ]
            else:  # right
                tip_y = max(text_rect.top() + 30,
                            min(highlight_rect.center().y(), text_rect.bottom() - 30))
                tip_x = text_rect.right()
                base_x = text_rect.right() - arrow_size
                return [
                    QPointF(tip_x, tip_y),
                    QPointF(base_x, tip_y - arrow_size),
                    QPointF(base_x, tip_y + arrow_size)
                ]
        except Exception as e:
            print(f"箭头计算错误: {e}")
            return []

    def draw_text_content(self, painter, text_rect):
        """绘制优化的文字内容"""
        try:
            painter.setPen(QColor(50, 50, 50))

            # 计算文字区域（增大边距）
            content_rect = text_rect.adjusted(20, 20, -20, -40)

            # 分割文字（标题和内容）
            lines = self.text.split('\n')
            if lines:
                title = lines[0]
                content = '\n'.join(lines[1:]) if len(lines) > 1 else ""

                # 绘制标题
                title_font = QFont()
                title_font.setPointSize(13)
                title_font.setBold(True)
                painter.setFont(title_font)

                title_rect = QRect(int(content_rect.x()), int(content_rect.y()),
                                   int(content_rect.width()), 30)
                painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft, title)

                # 绘制内容
                if content:
                    content_font = QFont()
                    content_font.setPointSize(11)
                    painter.setFont(content_font)
                    painter.setPen(QColor(80, 80, 80))

                    content_rect_adjusted = QRect(int(content_rect.x()), int(content_rect.y()) + 35,
                                                  int(content_rect.width()), int(content_rect.height()) - 35)
                    painter.drawText(content_rect_adjusted,
                                     Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                                     content)

            # 绘制"点击继续"提示
            hint_font = QFont()
            hint_font.setPointSize(10)
            hint_font.setItalic(True)
            painter.setFont(hint_font)
            painter.setPen(QColor(100, 150, 255))

            hint_rect = QRect(int(text_rect.x()) + 20, int(text_rect.bottom()) - 35,
                              int(text_rect.width()) - 40, 25)
            painter.drawText(hint_rect, Qt.AlignmentFlag.AlignRight, "💡 点击任意位置继续")

        except Exception as e:
            print(f"文字绘制错误: {e}")