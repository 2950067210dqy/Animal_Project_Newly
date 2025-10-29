
import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QFrame, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QWidget, QSplitter, QScrollArea)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QRect, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QMouseEvent, QPainter, QColor, QPen, QCloseEvent, QFont, QIcon, QScreen

from public.component.dock_widget.DraggableDockWidget import TabNavigator, DraggableContainer, DropZoneWidget, \
    DraggableFrame


# ========================= 演示应用 =========================

class DemoMainWindow(QWidget):
    """演示如何使用拖拽框架的主窗口 - 朴素风格"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tab导航 + 拖拽框架(朴素风格)")
        self.frames = []  # 存储所有Frame的引用

        self.setupUI()

    def setupUI(self):

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 朴素的说明
        info_label = QLabel("""
                <b>Tab导航 + 拖拽框架演示：</b><br>
                • <b>Tab导航栏</b>：点击标签导航到对应Frame，拖拽标签可以重新排序<br>
                • <b>拖拽反馈</b>：拖拽时有清晰的视觉提示和实时预览效果<br>
                • <b>上方容器</b>：Frame的原始父容器，支持横向滚动<br>
                • <b>下方区域</b>：额外的拖拽区域，支持重新附加功能<br>
                • <b>朴素风格</b>：使用简洁的配色和适度的视觉效果
                """)
        info_label.setStyleSheet("""
                    QLabel {
                        background-color: #f8f9fa;
                        border: 1px solid #dee2e6;
                        border-radius: 4px;
                        padding: 10px;
                        font-size: 11px;
                        color: #495057;
                    }
                """)
        main_layout.addWidget(info_label)

        # Tab导航栏
        self.tab_navigator = TabNavigator()
        self.tab_navigator.tabClicked.connect(self.navigateToFrame)
        self.tab_navigator.tabOrderChanged.connect(self.onTabOrderChanged)
        main_layout.addWidget(self.tab_navigator)

        # 主要内容区域 - 垂直分割
        content_splitter = QSplitter(Qt.Orientation.Vertical)

        # 上方 - 横向滚动的DraggableContainer
        self.upper_scroll = QScrollArea()
        self.upper_scroll.setWidgetResizable(True)
        self.upper_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.upper_scroll.setMinimumHeight(320)

        # 使用DraggableContainer作为父容器
        self.container = DraggableContainer()
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(12, 12, 12, 12)
        self.container_layout.setSpacing(12)

        # 先添加标题说明
        title_container = QWidget()
        title_container.setFixedWidth(180)
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)

        container_title = QLabel("拖拽容器\n(灰色高亮)")
        container_title.setStyleSheet("""
                    QLabel {
                        font-weight: bold; 
                        font-size: 13px; 
                        color: #495057; 
                        background: #ffffff; 
                        border: 1px solid #c0c4c8;
                        border-radius: 3px;
                        padding: 8px;
                        text-align: center;
                    }
                """)
        container_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(container_title)
        title_layout.addStretch()

        self.container_layout.addWidget(title_container)

        # 下方 - 使用DropZoneWidget
        self.drop_zone = DropZoneWidget()
        self.drop_zone.setMinimumHeight(180)

        # 创建可拖拽的Frame
        self.createDraggableFrames(self.container_layout)

        # 设置滚动区域
        self.upper_scroll.setWidget(self.container)

        # 添加到分割器
        content_splitter.addWidget(self.upper_scroll)
        content_splitter.addWidget(self.drop_zone)
        content_splitter.setStretchFactor(0, 2)
        content_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(content_splitter)

        # 朴素的状态栏
        self.status_label = QLabel("状态：所有面板已附加")
        self.status_label.setStyleSheet("""
                    QLabel {
                        background-color: #d4edda;
                        border: 1px solid #c3e6cb;
                        border-radius: 3px;
                        padding: 8px;
                        color: #155724;
                        font-weight: bold;
                        font-size: 11px;
                    }
                """)
        main_layout.addWidget(self.status_label)

    def createDraggableFrames(self, layout):
        """创建朴素的拖拽Frame示例"""

        # Frame 1 - 默认内容
        frame1 = DraggableFrame("数据面板", parent=self.container)
        frame1.frameDetached.connect(self.onFrameDetached)
        frame1.frameAttached.connect(self.onFrameAttached)
        layout.addWidget(frame1)
        self.frames.append(frame1)
        self.tab_navigator.addFrame(frame1)

        # Frame 2 - 自定义内容
        custom_content2 = QWidget()
        custom_layout2 = QVBoxLayout(custom_content2)
        custom_layout2.addWidget(QLabel("控制面板内容"))

        btn_group = QWidget()
        btn_layout = QVBoxLayout(btn_group)
        for i, text in enumerate(["开始", "暂停", "停止"]):
            btn = QPushButton(text)
            btn.setStyleSheet("""
                        QPushButton {
                            background-color: #6c757d;
                            color: white;
                            border: none;
                            padding: 6px 12px;
                            border-radius: 2px;
                            font-weight: bold;
                            font-size: 11px;
                        }
                        QPushButton:hover {
                            background-color: #5a6268;
                        }
                    """)
            btn.clicked.connect(lambda checked, t=text: print(f"点击了{t}按钮"))
            btn_layout.addWidget(btn)

        custom_layout2.addWidget(btn_group)
        custom_layout2.addStretch()

        frame2 = DraggableFrame("控制面板", custom_content2, self.container)
        frame2.frameDetached.connect(self.onFrameDetached)
        frame2.frameAttached.connect(self.onFrameAttached)
        layout.addWidget(frame2)
        self.frames.append(frame2)
        self.tab_navigator.addFrame(frame2)

        # Frame 3 - 设置面板
        custom_content3 = QWidget()
        custom_layout3 = QVBoxLayout(custom_content3)

        for setting in ["启用日志", "自动保存", "显示提示"]:
            from PyQt6.QtWidgets import QCheckBox
            checkbox = QCheckBox(setting)
            checkbox.setChecked(True)
            checkbox.setStyleSheet("""
                        QCheckBox {
                            font-weight: bold;
                            color: #495057;
                            font-size: 11px;
                        }
                        QCheckBox::indicator {
                            width: 16px;
                            height: 16px;
                        }
                        QCheckBox::indicator:checked {
                            background-color: #28a745;
                            border: 1px solid #28a745;
                            border-radius: 2px;
                        }
                    """)
            custom_layout3.addWidget(checkbox)

        custom_layout3.addStretch()

        frame3 = DraggableFrame("设置面板", custom_content3, self.container)
        frame3.frameDetached.connect(self.onFrameDetached)
        frame3.frameAttached.connect(self.onFrameAttached)
        layout.addWidget(frame3)
        self.frames.append(frame3)
        self.tab_navigator.addFrame(frame3)

        # 更多Frame
        frame_titles = ["网络监控", "系统状态", "性能指标", "日志查看", "用户管理", "权限控制"]
        for i, title in enumerate(frame_titles, 4):
            frame = DraggableFrame(title, parent=self.container)
            frame.frameDetached.connect(self.onFrameDetached)
            frame.frameAttached.connect(self.onFrameAttached)
            layout.addWidget(frame)
            self.frames.append(frame)
            self.tab_navigator.addFrame(frame)

        # 使用说明
        usage_info_widget = QWidget()
        usage_info_widget.setFixedWidth(260)
        usage_info_layout = QVBoxLayout(usage_info_widget)

        usage_info = QLabel("""💡 使用说明：
        • 点击Tab标签快速导航
        • 拖拽Tab重新排序（有反馈）
        • 拖拽Frame标题栏分离窗口
        • 拖拽到高亮区域重新附加
        • 支持横向滚动浏览""")
        usage_info.setStyleSheet("""
                    QLabel {
                        background-color: #f8f9fa;
                        border: 1px dashed #adb5bd;
                        border-radius: 4px;
                        padding: 8px;
                        color: #495057;
                        font-size: 10px;
                    }
                """)
        usage_info.setWordWrap(True)
        usage_info_layout.addWidget(usage_info)
        usage_info_layout.addStretch()

        layout.addWidget(usage_info_widget)

    def createDraggableFrames(self, layout):
        """创建朴素的拖拽Frame示例"""

        # Frame 1 - 默认内容
        frame1 = DraggableFrame("数据面板", parent=self.container)
        frame1.frameDetached.connect(self.onFrameDetached)
        frame1.frameAttached.connect(self.onFrameAttached)
        layout.addWidget(frame1)
        self.frames.append(frame1)
        self.tab_navigator.addFrame(frame1)

        # Frame 2 - 自定义内容
        custom_content2 = QWidget()
        custom_layout2 = QVBoxLayout(custom_content2)
        custom_layout2.addWidget(QLabel("控制面板内容"))

        btn_group = QWidget()
        btn_layout = QVBoxLayout(btn_group)
        for i, text in enumerate(["开始", "暂停", "停止"]):
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #6c757d;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 2px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #5a6268;
                }
            """)
            btn.clicked.connect(lambda checked, t=text: print(f"点击了{t}按钮"))
            btn_layout.addWidget(btn)

        custom_layout2.addWidget(btn_group)
        custom_layout2.addStretch()

        frame2 = DraggableFrame("控制面板", custom_content2, self.container)
        frame2.frameDetached.connect(self.onFrameDetached)
        frame2.frameAttached.connect(self.onFrameAttached)
        layout.addWidget(frame2)
        self.frames.append(frame2)
        self.tab_navigator.addFrame(frame2)

        # Frame 3 - 设置面板
        custom_content3 = QWidget()
        custom_layout3 = QVBoxLayout(custom_content3)

        for setting in ["启用日志", "自动保存", "显示提示"]:
            from PyQt6.QtWidgets import QCheckBox
            checkbox = QCheckBox(setting)
            checkbox.setChecked(True)
            checkbox.setStyleSheet("""
                QCheckBox {
                    font-weight: bold;
                    color: #495057;
                    font-size: 11px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                }
                QCheckBox::indicator:checked {
                    background-color: #28a745;
                    border: 1px solid #28a745;
                    border-radius: 2px;
                }
            """)
            custom_layout3.addWidget(checkbox)

        custom_layout3.addStretch()

        frame3 = DraggableFrame("设置面板", custom_content3, self.container)
        frame3.frameDetached.connect(self.onFrameDetached)
        frame3.frameAttached.connect(self.onFrameAttached)
        layout.addWidget(frame3)
        self.frames.append(frame3)
        self.tab_navigator.addFrame(frame3)

        # 更多Frame
        frame_titles = ["网络监控", "系统状态", "性能指标", "日志查看", "用户管理", "权限控制"]
        for i, title in enumerate(frame_titles, 4):
            frame = DraggableFrame(title, parent=self.container)
            frame.frameDetached.connect(self.onFrameDetached)
            frame.frameAttached.connect(self.onFrameAttached)
            layout.addWidget(frame)
            self.frames.append(frame)
            self.tab_navigator.addFrame(frame)

        # 使用说明
        usage_info_widget = QWidget()
        usage_info_widget.setFixedWidth(260)
        usage_info_layout = QVBoxLayout(usage_info_widget)

        usage_info = QLabel("""💡 使用说明：
• 点击Tab标签快速导航
• 拖拽Tab重新排序（有反馈）
• 拖拽Frame标题栏分离窗口
• 拖拽到高亮区域重新附加
• 支持横向滚动浏览""")
        usage_info.setStyleSheet("""
            QLabel {
                background-color: #f8f9fa;
                border: 1px dashed #adb5bd;
                border-radius: 4px;
                padding: 8px;
                color: #495057;
                font-size: 10px;
            }
        """)
        usage_info.setWordWrap(True)
        usage_info_layout.addWidget(usage_info)
        usage_info_layout.addStretch()

        layout.addWidget(usage_info_widget)

    def onTabOrderChanged(self, new_frame_order):
        """响应Tab重排序事件，重新排列Frame"""
        print(f"Tab重排序，新顺序: {[f.title for f in new_frame_order]}")

        # 收集所有widget
        frame_widgets = []
        other_widgets = []

        for i in range(self.container_layout.count()):
            item = self.container_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, DraggableFrame):
                    frame_widgets.append(widget)
                else:
                    other_widgets.append((i, widget))

        # 移除所有Frame widget
        for frame in frame_widgets:
            self.container_layout.removeWidget(frame)

        # 按新顺序重新插入Frame（从索引1开始，跳过标题容器）
        insert_index = 1
        for frame in new_frame_order:
            if frame in frame_widgets:
                self.container_layout.insertWidget(insert_index, frame)
                insert_index += 1

        # 更新frames列表
        self.frames = new_frame_order.copy()

        # 更新状态显示
        self.status_label.setText("状态：Tab和Frame重排序完成")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #cce5ff;
                border: 1px solid #99ccff;
                border-radius: 3px;
                padding: 8px;
                color: #0066cc;
                font-weight: bold;
                font-size: 11px;
            }
        """)

        QTimer.singleShot(2000, self.resetStatus)

    def navigateToFrame(self, frame):
        """导航到指定Frame"""
        if frame.isVisible() and not frame.is_detached:
            # 滚动到Frame位置
            self.upper_scroll.ensureWidgetVisible(frame)
            # 简单的高亮效果
            self.highlightFrame(frame)

    def highlightFrame(self, frame):
        """高亮指定Frame"""
        original_style = frame.styleSheet()
        highlight_style = """
            QFrame {
                border: 2px solid #ffc107;
                background-color: #fff9c4;
                border-radius: 3px;
            }
        """
        frame.setStyleSheet(highlight_style)
        QTimer.singleShot(1000, lambda: frame.setStyleSheet(original_style))

    def onFrameDetached(self, frame):
        frame.updateStatus("detached")
        self.tab_navigator.updateFrameStatus(frame, True)

        # 为独立窗口添加拖拽区域
        if frame.detached_window:
            frame.detached_window.addDropZone(self.drop_zone)

        self.status_label.setText(f"状态：{frame.title} 已分离")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #fff3cd;
                border: 1px solid #ffeaa7;
                border-radius: 3px;
                padding: 8px;
                color: #856404;
                font-weight: bold;
                font-size: 11px;
            }
        """)

    def onFrameAttached(self, frame):
        frame.updateStatus("attached")
        self.tab_navigator.updateFrameStatus(frame, False)

        self.status_label.setText(f"状态：{frame.title} 已重新附加")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                border-radius: 3px;
                padding: 8px;
                color: #155724;
                font-weight: bold;
                font-size: 11px;
            }
        """)

        QTimer.singleShot(2000, self.resetStatus)

    def resetStatus(self):
        self.status_label.setText("状态：所有面板已附加")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                border-radius: 3px;
                padding: 8px;
                color: #155724;
                font-weight: bold;
                font-size: 11px;
            }
        """)


# ========================= 使用示例 =========================

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 演示主窗口
    demo_window = DemoMainWindow()
    demo_window.show()

    sys.exit(app.exec())