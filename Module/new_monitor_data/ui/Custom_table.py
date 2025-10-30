from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtWidgets import QTableWidget, QToolTip
from PyQt6.QtGui import QCursor

from Module.new_monitor_data.ui.TableCellDetailDialog import CellDetailDialog


class CustomTableWidget(QTableWidget):
    """自定义表格控件 - 简化版本"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

        self.hover_timer = QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.show_tooltip)


        # 使用行列索引而不是item引用
        self.current_hover_row = -1
        self.current_hover_column = -1
        self.hover_delay = 500

        self.cellClicked.connect(self.on_cell_double_clicked)

    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        super().mouseMoveEvent(event)

        item = self.itemAt(event.pos())
        if item:
            try:
                row = item.row()
                column = item.column()
            except (RuntimeError, AttributeError):
                row = -1
                column = -1
        else:
            row = -1
            column = -1
        if row != self.current_hover_row or column != self.current_hover_column:
            # QToolTip.hideText()  # 隐藏之前的提示
            self.current_hover_row = row
            self.current_hover_column = column

            if row >= 0 and column >= 0:
                # 设置鼠标样式
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                # 启动悬停计时器
                self.hover_timer.start(self.hover_delay)
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                self.hover_timer.stop()

    def get_cell_content_safe(self, row, column):
        """安全地获取单元格内容"""
        try:
            # 检查行列索引是否有效
            if (row < 0 or row >= self.rowCount() or
                    column < 0 or column >= self.columnCount()):
                return ""

            item = self.item(row, column)
            if item is None:
                return ""

            return item.text()
        except (RuntimeError, AttributeError, IndexError):
            return ""

    def show_tooltip(self):
        """显示工具提示"""
        if self.current_hover_row < 0 or self.current_hover_column < 0:
            return

        cell_content =self.get_cell_content_safe(self.current_hover_row, self.current_hover_column)

        # 只有当内容较长时才显示
        if  cell_content and len(cell_content) > 10:
            # 格式化显示内容
            formatted_content = f"<div style='max-width: 300px; word-wrap: break-word;'>{cell_content}</div>"

            # 显示在鼠标位置
            QToolTip.showText(QCursor.pos(), formatted_content, self)

    def leaveEvent(self, event):
        """鼠标离开控件时的处理"""
        super().leaveEvent(event)
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.hover_timer.stop()
        # 延迟隐藏 tooltip，给用户足够的时间移动到 tooltip 上
        QTimer.singleShot(5000, QToolTip.hideText)
        self.current_hover_row = -1
        self.current_hover_column = -1

    def on_cell_double_clicked(self, row, column):
        """处理单元格双击事件"""
        QToolTip.hideText()

        item = self.item(row, column)
        if item:
            cell_value = item.text()
        else:
            cell_value = ""

        column_name = self.horizontalHeaderItem(column).text() if self.horizontalHeaderItem(
            column) else f"列{column + 1}"

        dialog = CellDetailDialog(cell_value, row, column, column_name, self)
        dialog.exec()