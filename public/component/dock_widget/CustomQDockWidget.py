from PyQt6.QtWidgets import QWidget, QVBoxLayout, QDockWidget


class CustomDockWidget(QDockWidget):
    def __init__(self, title, main_window, parent=None):
        super().__init__(title, parent)


        # 创建一个 QWidget 作为 QDockWidget 的内容
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main_window)
        self.setWidget(content_widget)