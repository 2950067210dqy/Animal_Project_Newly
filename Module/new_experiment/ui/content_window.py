import sys

from PyQt6.QtGui import QStandardItemModel, QCursor, QStandardItem
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton,
    QWidget, QTreeView, QScrollArea, QMessageBox, QMenu, QInputDialog
)
from PyQt6.QtCore import Qt, QPoint, QModelIndex

from public.config_class.global_setting import global_setting
from public.entity.experiment_setting_entity import Experiment_setting_entity, Group
from theme.ThemeQt6 import ThemedWindow


class AnimalInfoDialog(QMessageBox):
    """自定义对话框，用于显示动物信息"""

    def __init__(self, animal_info):
        super().__init__()
        # 实验配置数据
        self.setting_data: Experiment_setting_entity = None
        self.setWindowTitle("动物信息")
        self.setText(animal_info)
        self.setStandardButtons(QMessageBox.StandardButton.Ok)


class ContentWindow(ThemedWindow):
    def __init__(self):
        super().__init__()
        # 实验配置数据
        self.setting_data: Experiment_setting_entity = None
        self._init_ui()
        self.init_content()
    def _init_ui(self):
        # 设置主窗口的布局
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        main_layout = QVBoxLayout(self.central_widget)

        # 创建顶部布局
        top_layout = QHBoxLayout()
        self.import_button = QPushButton("导入实验模板")
        self.save_button = QPushButton("保存实验模板")
        self.create_button = QPushButton("创建实验")

        top_layout.addWidget(self.import_button)
        top_layout.addWidget(self.save_button)
        top_layout.addWidget(self.create_button)

        # 添加顶部布局到主布局
        main_layout.addLayout(top_layout)

        # 创建内容布局
        self.content_layout = QVBoxLayout()
        self.tree_view = QTreeView()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.tree_view)
        self.scroll_area.setWidgetResizable(True)
        self.content_layout.addWidget(self.scroll_area)

        # 添加内容布局到主布局
        main_layout.addLayout(self.content_layout)

        # 设置树形模型
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["组/通道"])
        self.tree_view.setModel(self.model)

        # 连接右键菜单
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.open_menu)

        # 添加测试组
        # self.add_group("实验组 1")
        # self.add_group("实验组 2")

        # 连接按钮信号（示例）
        self.import_button.clicked.connect(self.import_template)
        self.save_button.clicked.connect(self.save_template)
        self.create_button.clicked.connect(self.create_experiment)
    def init_content(self):
        # 里面装的是Experiment_setting_entity
        self.setting_data: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)
        # 清空treeview
        self.clear_tree()
        if self.setting_data is not None:
            if len(self.setting_data.groups) > 0:
                for index, group in enumerate(self.setting_data.groups):
                    group: Group
                    self.add_group(f"动物分组/通道: {group.name}")
                    pass
            pass
        pass

    def clear_tree(self):
        """清空树视图"""
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["组/通道"])  # 可选: 重新设置列标题
    def open_menu(self, position: QPoint):
        """打开右键菜单"""
        index = self.tree_view.indexAt(position)
        menu = QMenu()

        if index.isValid():
            item = self.model.itemFromIndex(index)

            if item.parent() is None:  # 组节点
                add_animal_action = menu.addAction("添加动物")
                delete_group_action = menu.addAction("删除组/通道")

                action = menu.exec(self.tree_view.viewport().mapToGlobal(position))
                if action == add_animal_action:
                    self.add_animal(index)
                elif action == delete_group_action:
                    self.delete_group(index)
            else:  # 动物节点
                delete_animal_action = menu.addAction("删除动物")

                action = menu.exec(self.tree_view.viewport().mapToGlobal(position))
                if action == delete_animal_action:
                    self.delete_animal(index)
        else:
            # 如果点击在无效位置，可以选择其他操作，比如只显示添加组的选项
            add_group_action = menu.addAction("添加组")
            action = menu.exec(self.tree_view.viewport().mapToGlobal(position))
            if action == add_group_action:
                group_name, ok = QInputDialog.getText(self, "输入组名", "请输入组名:")
                if ok and group_name:
                    self.add_group(group_name)

    def add_animal(self, group_index: QModelIndex):
        """添加动物"""
        animal_menu = QMenu()
        animal_types = ["猫", "狗", "兔子", "鹦鹉"]
        for animal in animal_types:
            animal_menu.addAction(animal, lambda group_index=group_index, a=animal: self.add_animal_to_group(group_index, a))

        animal_menu.exec(QCursor.pos())

    def add_animal_to_group(self, group_index: QModelIndex, animal: str):
        """将动物添加到组/通道"""
        group_item = self.model.itemFromIndex(group_index)
        animal_item = QStandardItem(animal)
        animal_item.setToolTip(f"这是一只{animal}")

        # 存储动物信息
        animal_item.setData(animal)

        # 将动物项添加到组项中
        group_item.appendRow(animal_item)

        #自动展开组节点
        self.tree_view.expand(group_index)

    def show_animal_info(self, animal: str):
        """显示动物信息对话框"""
        info_dialog = AnimalInfoDialog(f"这是关于动物 {animal} 的信息。")
        info_dialog.exec()

    def delete_group(self, group_index: QModelIndex):
        """删除组"""
        self.model.removeRow(group_index.row())

    def delete_animal(self, animal_index: QModelIndex):
        """删除动物"""
        self.model.removeRow(animal_index.row(), animal_index.parent())

    def add_group(self, group_name: str):
        """添加组"""
        group_item = QStandardItem(group_name)
        self.model.appendRow(group_item)

    def import_template(self):
        print("导入实验模板")  # 这里实现您的导入功能

    def save_template(self):
        print("保存实验模板")  # 这里实现您的保存功能

    def create_experiment(self):
        print("创建实验")  # 这里实现您的创建实验功能


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.setWindowTitle("实验管理系统")
    window.resize(600, 400)
    window.show()
    sys.exit(app.exec())