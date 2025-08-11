import os
import sys
from cgitb import handler
from datetime import datetime

from PyQt6.QtGui import QStandardItemModel, QCursor, QStandardItem
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton,
    QWidget, QTreeView, QScrollArea, QMessageBox, QMenu, QInputDialog, QFileDialog
)
from PyQt6.QtCore import Qt, QPoint, QModelIndex, pyqtSignal

from public.config_class.global_setting import global_setting
from public.dao.SQLite.Experiment_Setting_DAO_Handle import Experiment_Setting_DAO_Handle
from public.entity.enum.Public_Enum import AnimalGender
from public.entity.experiment_setting_entity import Experiment_setting_entity, Group, Animal, AnimalGroupRecord, \
    AnimalGroupRecord_View
from theme.ThemeQt6 import ThemedWindow
from util.class_util import class_util


class InfoDialog(QMessageBox):
    """自定义对话框，用于显示动物信息"""

    def __init__(self, info=""):
        super().__init__()
        # 实验配置数据
        self.setting_data: Experiment_setting_entity = None
        self.setWindowTitle("详情信息")
        self.setText(info)
        self.setStandardButtons(QMessageBox.StandardButton.Ok)


class ContentWindow(ThemedWindow):
    # 更新group页面信号
    update_group_signal = pyqtSignal(bool)
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
        # 不允许任何节点编辑
        self.tree_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)

        # 添加双击事件
        # 连接双击信号
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        # 添加测试组
        # self.add_group("实验组 1")
        # self.add_group("实验组 2")

        # 连接按钮信号（示例）
        self.import_button.clicked.connect(self.import_template)
        self.save_button.clicked.connect(self.save_template)
        self.create_button.clicked.connect(self.create_experiment)
    def init_content(self,is_update=True):
        """

        :param is_update:是否触发group等其他界面的数据更新
        :return:
        """
        # 里面装的是Experiment_setting_entity
        self.setting_data: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)
        # 清空treeview
        self.clear_tree()
        if self.setting_data is not None:
            #添加group
            if len(self.setting_data.groups) > 0:
                for index, group in enumerate(self.setting_data.groups):
                    group: Group
                    self.add_group_view(f"动物分组/通道: {group.name}",group)
                    pass
            pass
            #添加动物与组的关系
            if len(self.setting_data.animalGroupRecords)>0:
                for index, animalGroupRecord in enumerate(self.setting_data.animalGroupRecords):
                    animalGroupRecord: AnimalGroupRecord
                    #  从groups和animals寻找到关系表中的类
                    animalGroupRecord_View = AnimalGroupRecord_View()
                    if len(self.setting_data.groups)>0:
                        for group in self.setting_data.groups:
                            group: Group
                            if group.id == animalGroupRecord.gid:
                                animalGroupRecord_View.group = group
                                break
                        pass
                    if len(self.setting_data.animals)>0:
                        for animal in self.setting_data.animals:
                            animal: Animal
                            if animal.id == animalGroupRecord.aid:
                                animalGroupRecord_View.animal = animal
                                break
                        pass
                    animalGroupRecord_View.id = animalGroupRecord.aid
                    animalGroupRecord_View.note = animalGroupRecord.note
                    animalGroupRecord_View.create_time = animalGroupRecord.create_time
                    animalGroupRecord_View.update_time = animalGroupRecord.update_time
                    # 添加显示组件
                    animal_item = QStandardItem(
                        f"动物名称: {animalGroupRecord_View.animal.name}, ID: {animalGroupRecord_View.animal.id_write}, 性别: {'雌性' if animalGroupRecord_View.animal.sex == AnimalGender.FEMALE.value else '雄性'}, 重量: {animalGroupRecord_View.animal.weight} {animalGroupRecord_View.animal.weight_unit}, 备注: {animalGroupRecord_View.animal.note}")

                    animal_item.setToolTip(
                        f"动物名称: {animalGroupRecord_View.animal.name}, ID: {animalGroupRecord_View.animal.id_write}, 性别: {'雌性' if animalGroupRecord_View.animal.sex == AnimalGender.FEMALE.value else '雄性'}, 重量: {animalGroupRecord_View.animal.weight} {animalGroupRecord_View.animal.weight_unit}, 备注: {animalGroupRecord_View.animal.note}")

                    # 存储动物信息
                    animal_item.setData(animalGroupRecord_View.animal,Qt.ItemDataRole.UserRole)

                    # 将动物项添加到组项中
                    # 找到group-item
                    for row in range(self.model.rowCount()):
                        group_item:QStandardItem=self.model.item(row)
                        group = group_item.data(Qt.ItemDataRole.UserRole)
                        if group.id ==animalGroupRecord_View.group.id:
                            group_item.appendRow(animal_item)
                            # 自动展开组节点
                            self.tree_view.expand(group_item.index())
                            break
        # 更新group页面
        if is_update:
            self.update_group_signal.emit(False)
        pass

    def on_item_double_clicked(self, index):
        """每个子节点的双击事件"""
        if index.isValid():
            text = ""
            item:QStandardItem = self.model.itemFromIndex(index)
            data = item.data(Qt.ItemDataRole.UserRole)
            # 根据类的属性备注来放详情信息
            item_attr = class_util.get_public_attributes_with_notes(data)
            for key, value in item_attr.items():
                text += f"{value['note']}:{value['value']}\n"
            dialog = InfoDialog(text)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
            dialog.exec()

    def add_group_view(self, group_name,group_data):
        """添加组界面"""
        group_item = QStandardItem(group_name)
        group_item.setData(group_data,Qt.ItemDataRole.UserRole)
        group_item.setToolTip(group_name)
        self.model.appendRow(group_item)
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
                    # 如果没有动物 就跳出弹窗提醒用户没有动物，去添加动物

                    if self.setting_data is not None and  self.setting_data.animals is not None and len(self.setting_data.animals) > 0:
                        self.add_animal(index)
                        pass
                    else:
                        msg_box = QMessageBox()
                        msg_box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
                        msg_box.setWindowTitle("注意")
                        msg_box.setText("尚未添加动物，请前往添加动物！")
                        msg_box.setIcon(QMessageBox.Icon.Warning)  # 设置图标
                        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)  # 添加确定按钮
                        msg_box.exec()  # 显示弹窗并等待用户操作
                        pass

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
                self.add_group()

    def add_group(self):
        """添加组"""
        group_nums, ok = QInputDialog.getInt(self, "添加分组", "请输入分组/通道个数:")
        if ok and group_nums:
            init_index = 0
            # 取最大name的那一个
            if self.setting_data is not None and len(self.setting_data.groups) > 0:
                int_group_names = [int(group.name) for group in self.setting_data.groups]
                init_index = max(int_group_names) + 1
            for i in range(int(group_nums)):
                if self.setting_data is not None:
                    self.setting_data.groups.append(
                        Group(id=init_index+i, name=str(init_index+i), create_time=datetime.now(),
                              update_time=datetime.now())
                    )

            global_setting.set_setting("experiment_setting", self.setting_data)
            self.init_content()
    def add_animal(self, group_index: QModelIndex):
        """添加动物"""

        animal_menu = QMenu()
        for animal in self.setting_data.animals:
            animal:Animal
            animal_menu.addAction(f"动物名称: {animal.name}, ID: {animal.id_write}, 性别: {'雌性' if animal.sex ==AnimalGender.FEMALE.value else '雄性'}, 重量: {animal.weight} {animal.weight_unit}, 备注: {animal.note}",
                                  lambda group_index=group_index, a=animal: self.add_animal_to_group(group_index, a))

        animal_menu.exec(QCursor.pos())

    def add_animal_to_group(self, group_index: QModelIndex, animal: Animal):
        """将动物添加到组/通道"""
        group_item:QStandardItem = self.model.itemFromIndex(group_index)
        group  = group_item.data(Qt.ItemDataRole.UserRole)
        # 如果动物-组关系不存在则添加
        if len( self.setting_data.animalGroupRecords)==0 or (group.id,animal.id) not in [(animalGroupRecord.gid,animalGroupRecord.aid) for animalGroupRecord in self.setting_data.animalGroupRecords] :

            if self.setting_data is not None :
                init_index = 0
                # 取最大name的那一个
                if self.setting_data is not None and len(self.setting_data.animalGroupRecords) > 0:
                    int_animalGroupRecords_ids = [int(animalGroupRecords.id) for animalGroupRecords in self.setting_data.animalGroupRecords]
                    init_index = max(int_animalGroupRecords_ids) + 1
                self.setting_data.animalGroupRecords.append(AnimalGroupRecord(id=init_index,aid=animal.id,gid=group.id,note="无",create_time=datetime.now(),update_time=datetime.now()))
            global_setting.set_setting("experiment_setting", self.setting_data)
            # 获取滚动条位置
            # 获取垂直滚动条的位置
            vertical_scroll_position = self.scroll_area.verticalScrollBar().value()
            self.init_content()
            # 更新界面后直接滑动到之前选中的位置
            self.scroll_area.verticalScrollBar().setValue(vertical_scroll_position)
        else:
            pass

    def show_animal_info(self, animal: str):
        """显示动物信息对话框"""
        info_dialog = AnimalInfoDialog(f"这是关于动物 {animal} 的信息。")
        info_dialog.exec()

    def delete_group(self, group_index: QModelIndex):
        """删除组 关联关系一并删除"""
        group_item: QStandardItem = self.model.itemFromIndex(group_index)
        group:Group = group_item.data(Qt.ItemDataRole.UserRole)
        # 先删除关联关系
        newAnimalGroupRecords=[]
        for animalGroupRecord in self.setting_data.animalGroupRecords:
            animalGroupRecord:AnimalGroupRecord
            if animalGroupRecord.gid != group.id :
                newAnimalGroupRecords.append(animalGroupRecord)
        self.setting_data.animalGroupRecords = newAnimalGroupRecords
        # 删除组
        newGroups= []
        for group_item in self.setting_data.groups:
            group_item:Group
            if group_item.id!=group.id:
                newGroups.append(group_item)
        self.setting_data.groups = newGroups
        global_setting.set_setting("experiment_setting", self.setting_data)
        # 获取垂直滚动条的位置
        vertical_scroll_position = self.scroll_area.verticalScrollBar().value()
        self.init_content()
        self.scroll_area.verticalScrollBar().setValue(vertical_scroll_position)

    def delete_animal(self, animal_index: QModelIndex):
        """删除动物 其实就是删除动物与组的关系"""
        animal_item: QStandardItem = self.model.itemFromIndex(animal_index)
        animal:Animal = animal_item.data(Qt.ItemDataRole.UserRole)
        group_item: QStandardItem = self.model.itemFromIndex(animal_index.parent())
        group: Group = group_item.data(Qt.ItemDataRole.UserRole)
        # 删除关联关系
        newAnimalGroupRecords = []
        for animalGroupRecord in self.setting_data.animalGroupRecords:
            animalGroupRecord: AnimalGroupRecord
            if animalGroupRecord.gid != group.id and animalGroupRecord.aid!=animal.id:
                newAnimalGroupRecords.append(animalGroupRecord)
        self.setting_data.animalGroupRecords = newAnimalGroupRecords
        global_setting.set_setting("experiment_setting", self.setting_data)
        # 获取垂直滚动条的位置
        vertical_scroll_position = self.scroll_area.verticalScrollBar().value()
        self.init_content()
        self.scroll_area.verticalScrollBar().setValue(vertical_scroll_position)



    def import_template(self):
        print("导入实验模板")  # 这里实现您的导入功能

    def save_template(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "保存实验模板", "", "db Files (*.db);;All Files (*)")

        if file_path:
            # 获取文件所在的文件夹路径
            folder_path = os.path.dirname(file_path)
            # 获取文件名称
            file_name = os.path.basename(file_path)
            handle =Experiment_Setting_DAO_Handle(db_fold_path=folder_path, db_name=file_name)
            handle.insert_data(data=self.setting_data)
            pass
        pass

    def create_experiment(self):
        print("创建实验")  # 这里实现您的创建实验功能


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.setWindowTitle("实验管理系统")
    window.resize(600, 400)
    window.show()
    sys.exit(app.exec())