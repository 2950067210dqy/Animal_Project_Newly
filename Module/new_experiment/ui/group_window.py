import sys

from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QListWidget, \
    QApplication, QPushButton, QMenu

from public.config_class.global_setting import global_setting
from public.entity.BaseWindow import BaseWindow
from theme.ThemeQt6 import ThemedWindow


class GroupWindow(BaseWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("动物管理系统")
        self.setGeometry(100, 100, 400, 300)

        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主垂直布局
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # 创建顶部布局
        self.top_layout = QHBoxLayout()
        main_layout.addLayout(self.top_layout)

        # 创建并添加标签到顶部布局
        quick_add_label = QLabel("快速添加")
        self.top_layout.addWidget(quick_add_label)

        # 创建只能写数字的输入框，默认值为1
        self.line_edit = QLineEdit()
        self.line_edit.setText("1")
        self.line_edit.setValidator(QIntValidator())  # 只允许输入数字
        self.top_layout.addWidget(self.line_edit)

        # 添加分组/动物通道标签
        channel_label = QLabel("个分组/动物通道")
        self.top_layout.addWidget(channel_label)

        # 添加确定添加按钮
        add_button = QPushButton("确定添加")
        add_button.clicked.connect(self.add_group)
        self.top_layout.addWidget(add_button)

        # 创建内容布局
        self.content_layout = QVBoxLayout()
        main_layout.addLayout(self.content_layout)

        # 添加滚动区域
        self.scroll_area = QScrollArea()
        self.content_layout.addWidget(self.scroll_area)

        # 创建列表控件并设置为滚动区域的内容
        self.list_widget = QListWidget()
        self.scroll_area.setWidget(self.list_widget)
        self.scroll_area.setWidgetResizable(True)  # 允许滚动区域大小可调整

        # 启用多选
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # 连接右键菜单事件
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
    def init_group(self):
        global_setting.get_setting("experiment_setting",None)
        pass
    def add_group(self):
        # 从输入框获取动物通道号，添加到列表中
        channel_number = self.line_edit.text()
        if channel_number.isdigit():  # 检查输入值是否为数字
            self.list_widget.addItem(f"动物 通道: {channel_number}")
            self.line_edit.clear()  # 清空输入框
            self.line_edit.setText("1")  # 重置输入框为默认值

    def show_context_menu(self, pos):
        # 创建右键菜单
        context_menu = QMenu(self)

        # 创建删除菜单项
        delete_action = context_menu.addAction("删除选项")
        delete_action.triggered.connect(self.delete_items)

        # 显示菜单
        context_menu.exec(self.list_widget.mapToGlobal(pos))

    def delete_items(self):
        # 删除选中的项
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

if __name__ == "__main__":
    app = QApplication(sys.argv)

    main_window = GroupWindow()
    main_window.show()

    sys.exit(app.exec())
