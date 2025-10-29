import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QFrame, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QWidget, QSplitter)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QRect, QTimer
from PyQt6.QtGui import QMouseEvent, QPainter, QColor, QPen


class DropZoneWidget(QWidget):
    """可拖拽区域的容器widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_highlighted = False
        self.setMinimumSize(300, 200)
        self.setAcceptDrops(True)
        self.updateStyle()

        # 显示提示文本
        layout = QVBoxLayout()
        self.label = QLabel("可拖拽区域\n将分离的窗口拖到这里可以重新附加")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-size: 14px;
                border: none;
                background: transparent;
            }
        """)
        layout.addWidget(self.label)
        self.setLayout(layout)

    def updateStyle(self):
        """更新样式"""
        if self.is_highlighted:
            self.setStyleSheet("""
                QWidget {
                    background-color: #e3f2fd;
                    border: 3px solid #2196f3;
                    border-radius: 8px;
                }
            """)
            self.label.setText("松开鼠标以重新附加")
        else:
            self.setStyleSheet("""
                QWidget {
                    background-color: #f8f9fa;
                    border: 2px dashed #dee2e6;
                    border-radius: 5px;
                }
            """)
            self.label.setText("可拖拽区域\n将分离的窗口拖到这里可以重新附加")

    def setHighlight(self, highlight):
        """设置高亮状态"""
        if self.is_highlighted != highlight:
            self.is_highlighted = highlight
            self.updateStyle()


class DraggableFrame(QFrame):
    frameDetached = pyqtSignal(object)
    frameAttached = pyqtSignal(object)

    def __init__(self, title="", drop_zone_widget=None, parent=None):
        super().__init__(parent)
        self.title = title
        self.drop_zone_widget = drop_zone_widget
        self.is_detached = False
        self.detached_window = None
        self.original_parent = parent

        # 拖拽状态
        self.drag_start_position = QPoint()
        self.is_dragging = False
        self.drag_threshold = 30

        self.setupUI()
        self.setMinimumSize(200, 150)

    def setupUI(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setStyleSheet("""
            QFrame {
                border: 1px solid #bdc3c7;
                background-color: white;
                border-radius: 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(35)
        self.title_bar.setStyleSheet("""
            QFrame {
                background-color: #3498db;
                border: none;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
        """)
        self.title_bar.setCursor(Qt.CursorShape.OpenHandCursor)

        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(12, 0, 12, 0)

        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # 状态指示器
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #2ecc71; font-size: 16px;")
        title_layout.addWidget(self.status_indicator)

        # 内容区域
        content_widget = QWidget()
        content_widget.setStyleSheet("""
            QWidget {
                background-color: #fdfdfd;
                border-bottom-left-radius: 5px;
                border-bottom-right-radius: 5px;
            }
        """)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 15, 15, 15)

        content_layout.addWidget(QLabel(f"内容: {self.title}"))
        btn = QPushButton("测试按钮")
        btn.setMaximumWidth(120)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        content_layout.addWidget(btn)
        content_layout.addStretch()

        layout.addWidget(self.title_bar)
        layout.addWidget(content_widget)
        self.setLayout(layout)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否点击在标题栏
            title_rect = QRect(0, 0, self.width(), 35)
            if title_rect.contains(event.pos()):
                self.drag_start_position = event.globalPosition().toPoint()
                self.is_dragging = True
                self.title_bar.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.is_dragging and
                event.buttons() == Qt.MouseButton.LeftButton and
                not self.drag_start_position.isNull()):

            current_pos = event.globalPosition().toPoint()
            distance = (current_pos - self.drag_start_position).manhattanLength()

            if distance > self.drag_threshold and not self.is_detached:
                # 分离Frame
                self.detachFrame(current_pos)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.drag_start_position = QPoint()
            self.title_bar.setCursor(Qt.CursorShape.OpenHandCursor)

        super().mouseReleaseEvent(event)

    def detachFrame(self, global_pos):
        """分离Frame为独立窗口"""
        if self.is_detached:
            return

        try:
            # 创建独立窗口
            self.detached_window = DetachedWindow(self)

            # 设置位置 - 确保鼠标在标题栏中央
            window_pos = global_pos - QPoint(self.width() // 2, 17)
            self.detached_window.move(window_pos)

            # 继承当前的拖拽状态到新窗口
            self.detached_window.start_dragging_from_parent(
                global_pos - self.detached_window.pos()
            )

            self.detached_window.show()

            # 隐藏原Frame
            self.hide()
            self.is_detached = True

            self.frameDetached.emit(self)

        except Exception as e:
            print(f"分离Frame时出错: {e}")

    def attachFrame(self):
        """重新附加Frame"""
        if not self.is_detached:
            return

        try:
            # 关闭独立窗口
            if self.detached_window:
                self.detached_window.close()
                self.detached_window.deleteLater()
                self.detached_window = None

            # 显示原Frame
            self.show()
            self.is_detached = False

            # 重置拖拽状态
            self.is_dragging = False
            self.drag_start_position = QPoint()
            self.title_bar.setCursor(Qt.CursorShape.OpenHandCursor)

            self.frameAttached.emit(self)

        except Exception as e:
            print(f"附加Frame时出错: {e}")

    def updateStatus(self, status):
        """更新状态显示"""
        if status == "detached":
            self.status_indicator.setStyleSheet("color: #e74c3c; font-size: 16px;")
            self.title_bar.setStyleSheet("""
                QFrame {
                    background-color: #e74c3c;
                    border: none;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                }
            """)
        else:  # attached
            self.status_indicator.setStyleSheet("color: #2ecc71; font-size: 16px;")
            self.title_bar.setStyleSheet("""
                QFrame {
                    background-color: #3498db;
                    border: none;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                }
            """)


class DetachedWindow(QWidget):
    """独立的拖拽窗口"""

    def __init__(self, draggable_frame):
        super().__init__()
        self.draggable_frame = draggable_frame
        self.is_dragging = False
        self.drag_offset = QPoint()

        # 设置窗口属性
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

        # 用于检查拖拽区域的定时器
        self.drop_check_timer = QTimer()
        self.drop_check_timer.timeout.connect(self.checkDropZone)

        self.setupUI()
        self.resize(self.draggable_frame.size())

    def setupUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # 主容器
        self.container = QFrame()
        self.container.setFrameStyle(QFrame.Shape.Box)
        self.container.setLineWidth(2)
        self.container.setStyleSheet("""
            QFrame {
                border: 2px solid #e74c3c;
                background-color: white;
                border-radius: 5px;
            }
        """)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 标题栏
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(35)
        self.title_bar.setStyleSheet("""
            QFrame {
                background-color: #e74c3c;
                border: none;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
        """)
        self.title_bar.setCursor(Qt.CursorShape.OpenHandCursor)

        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(12, 0, 12, 0)

        title_label = QLabel(f"{self.draggable_frame.title} (独立)")
        title_label.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        status_indicator = QLabel("●")
        status_indicator.setStyleSheet("color: #f39c12; font-size: 16px;")
        title_layout.addWidget(status_indicator)

        # 内容区域
        content_widget = QWidget()
        content_widget.setStyleSheet("""
            QWidget {
                background-color: #fdfdfd;
                border-bottom-left-radius: 5px;
                border-bottom-right-radius: 5px;
            }
        """)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 15, 15, 15)

        content_layout.addWidget(QLabel(f"独立窗口: {self.draggable_frame.title}"))
        btn = QPushButton("测试按钮")
        btn.setMaximumWidth(120)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        content_layout.addWidget(btn)
        content_layout.addStretch()

        container_layout.addWidget(self.title_bar)
        container_layout.addWidget(content_widget)

        layout.addWidget(self.container)
        self.setLayout(layout)

    def start_dragging_from_parent(self, offset):
        """从父窗口继承拖拽状态"""
        self.is_dragging = True
        self.drag_offset = offset
        self.title_bar.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.drop_check_timer.start(50)  # 开始检查拖拽区域

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否点击在标题栏
            title_rect = QRect(0, 0, self.width(), 35)
            if title_rect.contains(event.pos()):
                self.is_dragging = True
                self.drag_offset = event.pos()
                self.title_bar.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.drop_check_timer.start(50)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.is_dragging and
                event.buttons() == Qt.MouseButton.LeftButton):
            # 移动窗口
            new_pos = event.globalPosition().toPoint() - self.drag_offset
            self.move(new_pos)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.title_bar.setCursor(Qt.CursorShape.OpenHandCursor)

            # 停止检查定时器
            if self.drop_check_timer.isActive():
                self.drop_check_timer.stop()

            # 检查是否在拖拽区域内
            if self.is_in_drop_zone():
                self.draggable_frame.attachFrame()
            else:
                # 清除高亮
                if self.draggable_frame.drop_zone_widget:
                    self.draggable_frame.drop_zone_widget.setHighlight(False)

            event.accept()
            return

        super().mouseReleaseEvent(event)

    def checkDropZone(self):
        """检查是否在拖拽区域内"""
        if not self.draggable_frame.drop_zone_widget:
            return

        try:
            in_zone = self.is_in_drop_zone()
            self.draggable_frame.drop_zone_widget.setHighlight(in_zone)

        except Exception as e:
            print(f"检查拖拽区域时出错: {e}")

    def is_in_drop_zone(self):
        """检查窗口是否在拖拽区域内"""
        if not self.draggable_frame.drop_zone_widget:
            return False

        try:
            # 获取窗口中心点
            window_center = self.geometry().center()

            # 获取拖拽区域的全局坐标
            drop_zone = self.draggable_frame.drop_zone_widget
            drop_zone_global_pos = drop_zone.mapToGlobal(QPoint(0, 0))
            drop_zone_rect = QRect(drop_zone_global_pos, drop_zone.size())

            return drop_zone_rect.contains(window_center)

        except Exception as e:
            print(f"检查区域包含时出错: {e}")
            return False

    def closeEvent(self, event):
        """窗口关闭时清理"""
        if self.drop_check_timer.isActive():
            self.drop_check_timer.stop()
        if self.draggable_frame.drop_zone_widget:
            self.draggable_frame.drop_zone_widget.setHighlight(False)
        super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("修复版 - 可拖拽Frame演示")
        self.setGeometry(100, 100, 1000, 700)

        self.setupUI()

    def setupUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 说明
        info_label = QLabel("""
        <b>修复版功能说明：</b><br>
        • 拖拽Frame的蓝色标题栏分离为独立窗口（拖拽事件无缝传递）<br>
        • 独立窗口拖到右侧区域时会高亮显示<br>
        • 在高亮区域松开鼠标可重新附加<br>
        • 修复了拖拽事件丢失和区域检测问题
        """)
        info_label.setStyleSheet("""
            QLabel {
                background-color: #e8f5e8;
                border: 1px solid #c3e6c3;
                border-radius: 5px;
                padding: 12px;
                font-size: 12px;
            }
        """)
        main_layout.addWidget(info_label)

        # 主要内容区域
        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧 - Frame容器
        left_widget = QWidget()
        left_widget.setStyleSheet("""
            QWidget {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
            }
        """)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(10)

        left_title = QLabel("Frame面板区域")
        left_title.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: #2c3e50; background: transparent; border: none;")
        left_layout.addWidget(left_title)

        # 右侧 - 可拖拽区域
        self.drop_zone = DropZoneWidget()

        # 创建可拖拽的Frame
        self.frame1 = DraggableFrame("数据面板", self.drop_zone, left_widget)
        self.frame1.frameDetached.connect(self.onFrameDetached)
        self.frame1.frameAttached.connect(self.onFrameAttached)
        left_layout.addWidget(self.frame1)

        self.frame2 = DraggableFrame("控制面板", self.drop_zone, left_widget)
        self.frame2.frameDetached.connect(self.onFrameDetached)
        self.frame2.frameAttached.connect(self.onFrameAttached)
        left_layout.addWidget(self.frame2)

        left_layout.addStretch()

        # 添加到分割器
        content_splitter.addWidget(left_widget)
        content_splitter.addWidget(self.drop_zone)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(content_splitter)

        # 状态栏
        self.status_label = QLabel("状态：所有面板已附加")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                border-radius: 4px;
                padding: 10px;
                color: #155724;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.status_label)

    def onFrameDetached(self, frame):
        frame.updateStatus("detached")
        self.status_label.setText(f"状态：{frame.title} 已分离为独立窗口")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #fff3cd;
                border: 1px solid #ffeaa7;
                border-radius: 4px;
                padding: 10px;
                color: #856404;
                font-weight: bold;
            }
        """)

    def onFrameAttached(self, frame):
        frame.updateStatus("attached")
        self.status_label.setText(f"状态：{frame.title} 已重新附加到主窗口")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                border-radius: 4px;
                padding: 10px;
                color: #155724;
                font-weight: bold;
            }
        """)

        # 2秒后恢复默认状态
        QTimer.singleShot(2000, self.resetStatus)

    def resetStatus(self):
        self.status_label.setText("状态：所有面板已附加")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())