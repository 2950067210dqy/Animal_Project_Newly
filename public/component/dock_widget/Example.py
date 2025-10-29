import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QFrame, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QWidget, QSplitter)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QRect, QTimer, QSize
from PyQt6.QtGui import QMouseEvent, QPainter, QColor, QPen, QCloseEvent, QFont, QIcon


class DropZoneWidget(QWidget):
    """可拖拽区域的容器widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_highlighted = False
        self.setMinimumSize(300, 200)
        self.setAcceptDrops(True)

        self.setupUI()
        self.updateStyle()

    def setupUI(self):
        """设置UI"""
        layout = QVBoxLayout()
        self.label = QLabel()
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
            self.label.setStyleSheet("""
                QLabel {
                    color: #1976d2;
                    font-size: 15px;
                    font-weight: bold;
                    border: none;
                    background: transparent;
                }
            """)
        else:
            self.setStyleSheet("""
                QWidget {
                    background-color: #f8f9fa;
                    border: 2px dashed #dee2e6;
                    border-radius: 5px;
                }
            """)
            self.label.setText("可拖拽区域\n将分离的窗口拖到这里可以重新附加")
            self.label.setStyleSheet("""
                QLabel {
                    color: #6c757d;
                    font-size: 14px;
                    border: none;
                    background: transparent;
                }
            """)

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
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("""
            QWidget {
                background-color: #fdfdfd;
                border-bottom-left-radius: 5px;
                border-bottom-right-radius: 5px;
            }
        """)
        content_layout = QVBoxLayout(self.content_widget)
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
        layout.addWidget(self.content_widget)
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
            self.detached_window = CustomMainWindow(self)

            # 设置位置 - 确保鼠标在标题栏合适位置
            window_pos = global_pos - QPoint(self.width() // 2, 30)
            self.detached_window.move(window_pos)

            # 继承当前的拖拽状态到新窗口
            self.detached_window.start_dragging_from_detach(
                global_pos,
                self.drag_start_position
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
                self.detached_window.close_and_attach()
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


class CustomTitleBar(QFrame):
    """自定义标题栏"""

    def __init__(self, window, title, parent=None):
        super().__init__(parent)
        self.window = window
        self.title = title
        self.is_maximized = False

        # 窗口拖拽相关
        self.drag_position = QPoint()
        self.is_dragging = False

        self.setupUI()

    def setupUI(self):
        self.setFixedHeight(40)
        self.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 5, 0)
        layout.setSpacing(10)

        # 拖拽图标
        self.drag_icon = QLabel("≡")
        self.drag_icon.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 5px;
            }
        """)
        self.drag_icon.setCursor(Qt.CursorShape.OpenHandCursor)
        layout.addWidget(self.drag_icon)

        # 标题
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 14px;
                background: transparent;
                border: none;
            }
        """)
        layout.addWidget(self.title_label)

        layout.addStretch()

        # 状态指示器
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #f39c12; font-size: 16px; background: transparent; border: none;")
        layout.addWidget(self.status_indicator)

        # 控制按钮
        button_style = """
            QPushButton {
                background-color: transparent;
                border: none;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 5px;
                min-width: 30px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 3px;
            }
        """

        # 最小化按钮
        self.minimize_btn = QPushButton("−")
        self.minimize_btn.setStyleSheet(button_style)
        self.minimize_btn.clicked.connect(self.window.showMinimized)
        self.minimize_btn.setToolTip("最小化")
        layout.addWidget(self.minimize_btn)

        # 最大化/还原按钮
        self.maximize_btn = QPushButton("□")
        self.maximize_btn.setStyleSheet(button_style)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        self.maximize_btn.setToolTip("最大化")
        layout.addWidget(self.maximize_btn)

        # 关闭按钮
        self.close_btn = QPushButton("×")
        close_button_style = button_style + """
            QPushButton:hover {
                background-color: #e74c3c;
                border-radius: 3px;
            }
        """
        self.close_btn.setStyleSheet(close_button_style)
        self.close_btn.clicked.connect(self.window.close)
        self.close_btn.setToolTip("关闭 (重新附加)")
        layout.addWidget(self.close_btn)

    def toggle_maximize(self):
        """切换最大化状态"""
        if self.window.isMaximized():
            self.window.showNormal()
            self.maximize_btn.setText("□")
            self.maximize_btn.setToolTip("最大化")
            self.is_maximized = False
        else:
            self.window.showMaximized()
            self.maximize_btn.setText("❐")
            self.maximize_btn.setToolTip("还原")
            self.is_maximized = True

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint()
            self.is_dragging = True
            self.drag_icon.setStyleSheet("""
                QLabel {
                    color: #3498db;
                    font-size: 16px;
                    font-weight: bold;
                    background: transparent;
                    border: none;
                    padding: 5px;
                }
            """)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            # 如果窗口最大化，先还原
            if self.window.isMaximized():
                self.toggle_maximize()
                # 重新计算拖拽位置
                ratio = event.pos().x() / self.width()
                new_width = self.window.width()
                self.drag_position = QPoint(int(new_width * ratio), event.pos().y())

            # 移动窗口
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.window.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        self.drag_icon.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 5px;
            }
        """)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        """双击标题栏切换最大化"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()


class CustomMainWindow(QMainWindow):
    """自定义的主窗口，使用QFrame实现标题栏"""

    def __init__(self, draggable_frame):
        super().__init__()
        self.draggable_frame = draggable_frame
        self.is_dragging = False
        self.drag_offset = QPoint()
        self.drag_start_position = QPoint()
        self.should_attach_on_close = True

        # 用于检查拖拽区域的定时器
        self.drop_check_timer = QTimer()
        self.drop_check_timer.timeout.connect(self.checkDropZone)

        self.setupWindow()
        self.setupUI()

    def setupWindow(self):
        """设置窗口属性"""
        # 移除默认标题栏
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self.setMinimumSize(400, 300)
        self.resize(500, 400)

        # 添加阴影效果
        self.setStyleSheet("""
            QMainWindow {
                background-color: white;
                border: 1px solid #bdc3c7;
                border-radius: 8px;
            }
        """)

    def setupUI(self):
        """设置UI"""
        # 创建中央widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 自定义标题栏
        self.custom_title_bar = CustomTitleBar(self, f"独立窗口: {self.draggable_frame.title}")
        main_layout.addWidget(self.custom_title_bar)

        # 内容区域
        content_frame = QFrame()
        content_frame.setStyleSheet("""
            QFrame {
                background-color: #fdfdfd;
                border: none;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)

        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # 窗口信息
        info_label = QLabel(f"这是从 '{self.draggable_frame.title}' 分离出来的独立窗口")
        info_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                font-size: 16px;
                font-weight: bold;
                background-color: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
            }
        """)
        content_layout.addWidget(info_label)

        # 功能按钮区域
        button_frame = QFrame()
        button_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        button_layout = QVBoxLayout(button_frame)

        # 按钮样式
        button_style = """
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """

        # 测试按钮
        test_btn = QPushButton("测试功能按钮")
        test_btn.setStyleSheet(button_style)
        test_btn.clicked.connect(lambda: print(f"{self.draggable_frame.title} 测试按钮被点击"))
        button_layout.addWidget(test_btn)

        # 附加按钮
        attach_btn = QPushButton("🔗 重新附加到主窗口")
        attach_btn.setStyleSheet(
            button_style.replace("#3498db", "#27ae60").replace("#2980b9", "#229954").replace("#21618c", "#1e8449"))
        attach_btn.clicked.connect(self.attach_to_main)
        button_layout.addWidget(attach_btn)

        content_layout.addWidget(button_frame)

        # 窗口操作说明
        help_text = QLabel("""
        <b>窗口操作说明:</b><br>
        • 拖拽标题栏左侧的 ≡ 图标可以重新附加到主窗口的拖拽区域<br>
        • 双击标题栏可以最大化/还原窗口<br>
        • 使用标题栏右侧的按钮进行最小化、最大化、关闭操作<br>
        • 关闭窗口会自动重新附加到主窗口，而不是真正关闭<br>
        • 可以通过拖拽窗口边缘来调整窗口大小
        """)
        help_text.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-size: 12px;
                background-color: #e9ecef;
                border: 1px solid #ced4da;
                border-radius: 5px;
                padding: 15px;
                line-height: 1.4;
            }
        """)
        help_text.setWordWrap(True)
        content_layout.addWidget(help_text)

        content_layout.addStretch()

        main_layout.addWidget(content_frame)

        # 绑定拖拽事件到拖拽图标
        self.custom_title_bar.drag_icon.mousePressEvent = self.onDragIconMousePress
        self.custom_title_bar.drag_icon.mouseMoveEvent = self.onDragIconMouseMove
        self.custom_title_bar.drag_icon.mouseReleaseEvent = self.onDragIconMouseRelease

    def start_dragging_from_detach(self, current_pos, start_pos):
        """从分离操作开始拖拽"""
        self.is_dragging = True
        self.drag_start_position = start_pos
        self.drag_offset = current_pos - self.pos()
        self.custom_title_bar.drag_icon.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.drop_check_timer.start(50)

    def onDragIconMousePress(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.globalPosition().toPoint()
            self.is_dragging = True
            self.drag_offset = event.pos() + self.custom_title_bar.drag_icon.pos()
            self.custom_title_bar.drag_icon.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.custom_title_bar.drag_icon.setStyleSheet("""
                QLabel {
                    color: #3498db;
                    font-size: 16px;
                    font-weight: bold;
                    background: rgba(52, 152, 219, 0.2);
                    border: 1px solid #3498db;
                    border-radius: 3px;
                    padding: 5px;
                }
            """)
            self.drop_check_timer.start(50)
            event.accept()

    def onDragIconMouseMove(self, event):
        if (self.is_dragging and
                event.buttons() == Qt.MouseButton.LeftButton):
            # 移动窗口
            new_pos = event.globalPosition().toPoint() - self.drag_offset
            self.move(new_pos)
            event.accept()

    def onDragIconMouseRelease(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.custom_title_bar.drag_icon.setCursor(Qt.CursorShape.OpenHandCursor)
            self.custom_title_bar.drag_icon.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 16px;
                    font-weight: bold;
                    background: transparent;
                    border: none;
                    padding: 5px;
                }
            """)

            # 停止检查定时器
            if self.drop_check_timer.isActive():
                self.drop_check_timer.stop()

            # 检查是否在拖拽区域内
            if self.is_in_drop_zone():
                self.attach_to_main()
            else:
                # 清除高亮
                if self.draggable_frame.drop_zone_widget:
                    self.draggable_frame.drop_zone_widget.setHighlight(False)

            event.accept()

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

    def attach_to_main(self):
        """附加到主窗口"""
        self.should_attach_on_close = True
        self.draggable_frame.attachFrame()

    def close_and_attach(self):
        """关闭窗口并附加（不触发closeEvent中的附加逻辑）"""
        self.should_attach_on_close = False
        if self.drop_check_timer.isActive():
            self.drop_check_timer.stop()
        if self.draggable_frame.drop_zone_widget:
            self.draggable_frame.drop_zone_widget.setHighlight(False)
        self.close()

    def closeEvent(self, event: QCloseEvent):
        """重写关闭事件，关闭时自动附加回主窗口"""
        if self.should_attach_on_close:
            # 阻止窗口关闭，改为附加到主窗口
            event.ignore()
            self.attach_to_main()
        else:
            # 允许正常关闭
            if self.drop_check_timer.isActive():
                self.drop_check_timer.stop()
            if self.draggable_frame.drop_zone_widget:
                self.draggable_frame.drop_zone_widget.setHighlight(False)
            event.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("自定义标题栏 - 可拖拽Frame演示")
        self.setGeometry(100, 100, 1200, 800)

        self.setupUI()

    def setupUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 说明
        info_label = QLabel("""
        <b>自定义标题栏功能说明：</b><br>
        • 拖拽Frame的蓝色标题栏分离为具有自定义标题栏的独立窗口<br>
        • 独立窗口支持最大化、最小化、调整大小等完整窗口操作<br>
        • 拖拽独立窗口标题栏中的 ≡ 图标可以重新附加到主窗口<br>
        • 双击标题栏可以最大化/还原窗口<br>
        • 关闭独立窗口时会自动附加回主窗口，而不是关闭窗口<br>
        • 自定义标题栏提供完整的窗口控制功能
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

        self.frame3 = DraggableFrame("设置面板", self.drop_zone, left_widget)
        self.frame3.frameDetached.connect(self.onFrameDetached)
        self.frame3.frameAttached.connect(self.onFrameAttached)
        left_layout.addWidget(self.frame3)

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
        self.status_label.setText(f"状态：{frame.title} 已分离为自定义标题栏的独立窗口")
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