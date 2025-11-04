import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLineEdit, QHBoxLayout
from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem




class CustomListView(QMainWindow):
    def __init__(self):
        super().__init__()
        self._init_ui()
        self.init_model()
    def _init_ui(self):
        """初始化UI界面"""
        self.setWindowTitle("QListView with Scroll Bar")
        self.setGeometry(100, 100, 400, 500)

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建布局
        layout = QVBoxLayout(central_widget)

        # 创建QListView
        from PyQt6.QtWidgets import QListView
        self.list_view = QListView()

        # 设置滚动条策略
        self.list_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 添加到布局
        layout.addWidget(self.list_view)
        pass

    def _init_customize_ui(self):
        pass

    def _init_function(self):
        pass

    def _init_custom_style_sheet(self):
        pass









    def init_model(self):
        """初始化数据模型"""
        self.model = QStandardItemModel()
        self.list_view.setModel(self.model)



    def insert_data(self, data):
        """
        插入新数据到列表最前面的接口方法

        Args:
            data (str): 要插入的数据
        """
        if isinstance(data, str):
            item = QStandardItem(data)
        else:
            item = QStandardItem(str(data))

        # 插入到第一行（索引0）
        self.model.insertRow(0, item)

        # 可选：滚动到顶部显示新添加的数据
        self.list_view.scrollToTop()

    def insert_multiple_data(self, data_list):
        """
        批量插入多个数据的接口方法

        Args:
            data_list (list): 要插入的数据列表
        """
        for data in reversed(data_list):  # 反向插入保持顺序
            self.insert_data(data)



    def get_all_data(self):
        """
        获取所有数据的方法

        Returns:
            list: 包含所有数据的列表
        """
        data_list = []
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item:
                data_list.append(item.text())
        return data_list

    def clear_all_data(self):
        """清空所有数据的方法"""
        self.model.clear()


def main():
    app = QApplication(sys.argv)
    window = CustomListView()
    window.show()

    # 示例：程序启动后自动添加一些数据
    import threading
    import time

    def auto_add_data():
        time.sleep(2)
        for i in range(5):
            window.insert_data(f"自动添加的数据 {i + 1}")
            time.sleep(1)

    # 启动自动添加数据的线程（仅用于演示）
    thread = threading.Thread(target=auto_add_data, daemon=True)
    thread.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
