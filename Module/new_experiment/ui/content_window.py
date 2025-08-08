import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QToolBox, QListView, QScrollArea, QDialog, QLabel,
    QLineEdit, QDialogButtonBox, QMenu, QVBoxLayout as QVBoxLayoutDialog
)
from PyQt6.QtCore import QStringListModel, Qt

from theme.ThemeQt6 import ThemedWindow


class AnimalInfoDialog(QDialog):
    def __init__(self, animal=None):
        super().__init__()
        self.setWindowTitle("动物信息")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.layout = QVBoxLayout()

        self.name_label = QLabel("动物名称:")
        self.id_label = QLabel("动物ID:")
        self.gender_label = QLabel("动物性别:")
        self.weight_label = QLabel("动物重量:")
        self.notes_label = QLabel("备注:")

        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.id_label)
        self.layout.addWidget(self.gender_label)
        self.layout.addWidget(self.weight_label)
        self.layout.addWidget(self.notes_label)

        if animal:
            self.populate_fields(animal)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        self.layout.addWidget(button_box)

        self.setLayout(self.layout)

    def populate_fields(self, animal):
        self.name_label.setText(f"动物名称: {animal['name']}")
        self.id_label.setText(f"动物ID: {animal['id']}")
        self.gender_label.setText(f"动物性别: {animal['gender']}")
        self.weight_label.setText(f"动物重量: {animal['weight']}")
        self.notes_label.setText(f"备注: {animal['notes']}")


class ContentWindow(ThemedWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("实验模板管理系统")
        self.setGeometry(100, 100, 600, 400)

        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 创建主垂直布局
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # 创建顶部布局
        self.top_layout = QHBoxLayout()
        main_layout.addLayout(self.top_layout)

        # 添加按钮
        import_template_button = QPushButton("导入实验模板")
        save_template_button = QPushButton("保存实验模板")
        create_experiment_button = QPushButton("创建实验")

        self.top_layout.addWidget(import_template_button)
        self.top_layout.addWidget(save_template_button)
        self.top_layout.addWidget(create_experiment_button)

        # 创建内容布局
        self.content_layout = QVBoxLayout()
        main_layout.addLayout(self.content_layout)

        # 创建工具箱
        self.toolbox = QToolBox()
        self.content_layout.addWidget(self.toolbox)

        # 当前组索引
        self.current_group_index = 0

        # 添加示例组
        self.add_group('实验通道 1')
        self.add_group('实验通道 2')

        # 显示窗口
        self.show()

    def add_group(self, group_name):
        # 创建一个新的 QListView，用于显示动物数据
        list_view = QListView()
        list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        list_view.customContextMenuRequested.connect(self.show_group_context_menu)

        # 添加一个滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidget(list_view)
        scroll_area.setWidgetResizable(True)

        # 将组和列表视图进行关联
        self.toolbox.addItem(scroll_area, group_name)

    def show_group_context_menu(self, pos):
        context_menu = QMenu(self)

        add_animal_action = context_menu.addAction("添加动物")
        add_animal_action.triggered.connect(self.show_add_animal_menu)

        delete_group_action = context_menu.addAction("删除该组/通道")
        delete_group_action.triggered.connect(self.delete_group)

        context_menu.exec(self.sender().mapToGlobal(pos))

    def show_add_animal_menu(self):
        animal_menu = QMenu(self)

        # 添加动物类型
        animal_types = ["小白兔", "小黑狗", "小橘猫"]
        for animal in animal_types:
            action = animal_menu.addAction(animal)
            action.triggered.connect(lambda checked, animal=animal: self.add_animal_to_group(animal))

        animal_menu.exec(self.mapToGlobal(self.cursor().pos()))

    def add_animal_to_group(self, animal_name):
        current_widget = self.toolbox.currentWidget()
        current_list_view = current_widget.widget()

        # 添加动物的信息
        animal_info = {'name': animal_name, 'id': "001", 'gender': "未知", 'weight': "0.5 kg", 'notes': "无"}

        model = QStringListModel()
        current_items = model.stringList()
        current_items.append(
            f"名称: {animal_info['name']}, ID: {animal_info['id']}, 性别: {animal_info['gender']}, 重量: {animal_info['weight']}, 备注: {animal_info['notes']}")
        model.setStringList(current_items)

        current_list_view.setModel(model)

        # 连接双击事件
        current_list_view.doubleClicked.connect(lambda index: self.show_animal_info(animal_info))

    def delete_group(self):
        current_index = self.toolbox.currentIndex()
        self.toolbox.removeItem(current_index)

    def show_animal_info(self, animal):
        dialog = AnimalInfoDialog(animal)
        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    main_window = ContentWindow()
    main_window.show()

    sys.exit(app.exec())