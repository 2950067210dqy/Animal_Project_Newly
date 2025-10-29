import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QScrollArea,
                             QSplitter, QLabel, QHBoxLayout, QGridLayout)
from PyQt6.QtCore import Qt, QTimer

from public.component.dock_widget.DraggableDockWidget import TabNavigator, DraggableContainer, DraggableFrame


class DemoDraggableDockWidget(QWidget):
    """演示如何使用拖拽框架的主窗口 - 朴素风格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tab导航 + 拖拽框架演示 (朴素风格)")
        self.setGeometry(100, 100, 1300, 750)
        self.frames = []  # 存储所有Frame的引用

        self.setupUI()

    def setupUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Tab导航栏
        self.tab_navigator = TabNavigator()
        self.tab_navigator.tabClicked.connect(self.navigateToFrame)
        self.tab_navigator.tabOrderChanged.connect(self.onTabOrderChanged)
        main_layout.addWidget(self.tab_navigator)

        # 上方 - 横向滚动的DraggableContainer
        self.upper_scroll = QScrollArea()
        self.upper_scroll.setWidgetResizable(True)
        self.upper_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.upper_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # self.upper_scroll.setMinimumHeight(650)  # 增加高度以容纳2行

        # 使用DraggableContainer作为父容器
        self.container = DraggableContainer()
        # 改为网格布局 - 2行n列
        self.container_layout = QGridLayout(self.container)
        self.container_layout.setObjectName("container_layout")
        self.container_layout.setContentsMargins(12, 12, 12, 12)
        self.container_layout.setSpacing(12)

        # 关键步骤：将container设置为scroll area的widget
        self.upper_scroll.setWidget(self.container)

        main_layout.addWidget(self.upper_scroll)

    def addFrames(self, widgets):
        """添加Frame组件 - 按2行n列排列"""
        for i, widget in enumerate(widgets):
            # 确保widget有合适的最小尺寸
            if widget.minimumSize().width() == 0:
                widget.setMinimumSize(200, 150)

            frame = DraggableFrame(widget.windowTitle(), widget, self.container)
            frame.frameDetached.connect(self.onFrameDetached)
            frame.frameAttached.connect(self.onFrameAttached)

            # 计算网格位置：2行n列
            row = i % 2  # 行索引：0或1
            col = i // 2  # 列索引：0, 1, 2, ...

            self.container_layout.addWidget(frame, row, col)
            self.frames.append(frame)
            self.tab_navigator.addFrame(frame)

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

    def onFrameAttached(self, frame):
        frame.updateStatus("attached")
        self.tab_navigator.updateFrameStatus(frame, False)

        # 重新排列网格布局
        self.rearrangeGridLayout()

    def rearrangeGridLayout(self):
        """重新排列网格布局"""
        # 收集所有可见的Frame
        visible_frames = [frame for frame in self.frames if frame.isVisible() and not frame.is_detached]

        # 清除现有布局
        for frame in self.frames:
            self.container_layout.removeWidget(frame)

        # 重新按2行n列排列
        for i, frame in enumerate(visible_frames):
            row = i % 2
            col = i // 2
            self.container_layout.addWidget(frame, row, col)

    def onTabOrderChanged(self, new_frame_order):
        """响应Tab重排序事件，重新排列Frame"""
        print(f"Tab重排序，新顺序: {[f.title for f in new_frame_order]}")

        # 更新frames列表
        self.frames = new_frame_order.copy()

        # 重新排列网格布局
        self.rearrangeGridLayout()

    def remove_all(self):
        """将界面恢复到初始状态"""
        # 移除所有Frame
        for frame in self.frames:
            self.container_layout.removeWidget(frame)
            frame.deleteLater()
        self.frames.clear()
        #
        # # 清空Tab导航栏
        # # # 清空Tab导航栏
        # # for i in range(self.tab_navigator.tab_layout.count() - 1, -1, -1):
        # #     item = self.tab_navigator.tab_layout.itemAt(i)
        # #     if item and item.widget():
        # #         self.tab_navigator.tab_layout.removeWidget(item.widget())
        # #         item.widget().deleteLater()
        #
        # # 重置网格布局
        # self.container_layout.setParent(None)
        # self.container_layout.deleteLater()
        # self.container_layout = QGridLayout(self.container)
        # self.container_layout.setContentsMargins(12, 12, 12, 12)
        # self.container_layout.setSpacing(12)
        # self.container.setLayout(self.container_layout)

# 示例使用
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 创建一些测试用的 QWidget 并添加内容
    widget1 = QWidget()
    widget1.setWindowTitle("数据面板")
    layout1 = QVBoxLayout(widget1)
    layout1.addWidget(QLabel("这是数据面板的内容"))
    layout1.addWidget(QLabel("包含各种数据显示组件"))
    widget1.setMinimumSize(250, 200)

    widget2 = QWidget()
    widget2.setWindowTitle("控制面板")
    layout2 = QVBoxLayout(widget2)
    layout2.addWidget(QLabel("这是控制面板的内容"))
    layout2.addWidget(QLabel("包含各种控制按钮"))
    widget2.setMinimumSize(250, 200)

    widget3 = QWidget()
    widget3.setWindowTitle("设置面板")
    layout3 = QVBoxLayout(widget3)
    layout3.addWidget(QLabel("这是设置面板的内容"))
    layout3.addWidget(QLabel("包含各种设置选项"))
    widget3.setMinimumSize(250, 200)

    widget4 = QWidget()
    widget4.setWindowTitle("监控面板")
    layout4 = QVBoxLayout(widget4)
    layout4.addWidget(QLabel("这是监控面板的内容"))
    layout4.addWidget(QLabel("包含各种监控信息"))
    widget4.setMinimumSize(250, 200)

    widget5 = QWidget()
    widget5.setWindowTitle("日志面板")
    layout5 = QVBoxLayout(widget5)
    layout5.addWidget(QLabel("这是日志面板的内容"))
    layout5.addWidget(QLabel("包含各种日志信息"))
    widget5.setMinimumSize(250, 200)

    widget6 = QWidget()
    widget6.setWindowTitle("统计面板")
    layout6 = QVBoxLayout(widget6)
    layout6.addWidget(QLabel("这是统计面板的内容"))
    layout6.addWidget(QLabel("包含各种统计图表"))
    widget6.setMinimumSize(250, 200)

    widget7 = QWidget()
    widget7.setWindowTitle("统计面板")
    layout7 = QVBoxLayout(widget7)
    layout7.addWidget(QLabel("这是统计面板的内容"))
    layout7.addWidget(QLabel("包含各种统计图表"))
    widget7.setMinimumSize(250, 200)

    widget8 = QWidget()
    widget8.setWindowTitle("统计面板")
    layout8 = QVBoxLayout(widget8)
    layout8.addWidget(QLabel("这是统计面板的内容"))
    layout8.addWidget(QLabel("包含各种统计图表"))
    widget8.setMinimumSize(250, 200)

    widget9 = QWidget()
    widget9.setWindowTitle("统计面板")
    layout9 = QVBoxLayout(widget9)
    layout9.addWidget(QLabel("这是统计面板的内容"))
    layout9.addWidget(QLabel("包含各种统计图表"))
    widget9.setMinimumSize(250, 200)

    widget10 = QWidget()
    widget10.setWindowTitle("统计面板")
    layout10 = QVBoxLayout(widget10)
    layout10.addWidget(QLabel("这是统计面板的内容"))
    layout10.addWidget(QLabel("包含各种统计图表"))
    widget10.setMinimumSize(250, 200)

    widget11 = QWidget()
    widget11.setWindowTitle("统计面板")
    layout11 = QVBoxLayout(widget11)
    layout11.addWidget(QLabel("这是统计面板的内容"))
    layout11.addWidget(QLabel("包含各种统计图表"))
    widget11.setMinimumSize(250, 200)

    widget12 = QWidget()
    widget12.setWindowTitle("统计面板")
    layout12 = QVBoxLayout(widget12)
    layout12.addWidget(QLabel("这是统计面板的内容"))
    layout12.addWidget(QLabel("包含各种统计图表"))
    widget12.setMinimumSize(250, 200)

    widget13 = QWidget()
    widget13.setWindowTitle("统计面板")
    layout13 = QVBoxLayout(widget13)
    layout13.addWidget(QLabel("这是统计面板的内容"))
    layout13.addWidget(QLabel("包含各种统计图表"))
    widget13.setMinimumSize(250, 200)

    widget14 = QWidget()
    widget14.setWindowTitle("统计面板")
    layout14 = QVBoxLayout(widget14)
    layout14.addWidget(QLabel("这是统计面板的内容"))
    layout14.addWidget(QLabel("包含各种统计图表"))
    widget14.setMinimumSize(250, 200)
    # 创建 DemoWidget 并添加 Frame
    demo_widget = DemoDraggableDockWidget()
    demo_widget.remove_all()
    demo_widget.addFrames([widget1, widget2, widget3, widget4, widget5, widget6, widget7, widget8, widget9, widget10, widget11, widget12, widget13, widget14])
    demo_widget.show()

    sys.exit(app.exec())