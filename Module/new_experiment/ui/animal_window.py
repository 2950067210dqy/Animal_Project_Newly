import datetime
import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMainWindow, QWidget, QVBoxLayout, \
    QHBoxLayout, QPushButton, QListWidget, QScrollArea, QMenu, QLabel, QApplication, QComboBox, QRadioButton, \
    QListWidgetItem

from public.config_class.global_setting import global_setting
from public.entity.enum.Public_Enum import AnimalGender
from public.entity.experiment_setting_entity import Experiment_setting_entity, Animal, AnimalGroupRecord
from theme.ThemeQt6 import ThemedWindow


import itertools
class AnimalDialog(QDialog):
    def __init__(self, animal=None):
        super().__init__()
        self.setting_data:Experiment_setting_entity = None
        self.setWindowTitle("动物信息")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        # 创建表单布局
        self.layout = QFormLayout(self)

        # 动物名称输入框
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入动物名称")
        self.layout.addRow("动物名称:", self.name_edit)

        # 动物ID输入框
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("输入动物ID")
        self.layout.addRow("动物ID:", self.id_edit)

        # 动物性别单选按钮
        self.gender_group = {}
        male_radio = QRadioButton("雄性")
        female_radio = QRadioButton("雌性")
        self.gender_group['Male'] = male_radio
        self.gender_group['Female'] = female_radio
        self.layout.addRow(QLabel("性别:"), male_radio)
        self.layout.addRow(QLabel(""), female_radio)  # 添加空行以放置第二个单选按钮

        # 动物重量和单位输入框
        self.weight_edit = QLineEdit()
        self.weight_edit.setPlaceholderText("输入动物重量")
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["kg", "g", "lb"])  # 重量单位下拉框
        self.layout.addRow("动物重量:", self.weight_edit)
        self.layout.addRow("单位:", self.unit_combo)

        # 动物备注输入框
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("输入备注")
        self.layout.addRow("备注:", self.notes_edit)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)

        if animal:
            self.populate_fields(animal)

    def populate_fields(self, animal):
        self.name_edit.setText(animal['name'])
        self.id_edit.setText(animal['id'])
        if animal['gender'] == 'Male':
            self.gender_group['Male'].setChecked(True)
        else:
            self.gender_group['Female'].setChecked(True)
        self.weight_edit.setText(animal['weight'])
        self.unit_combo.setCurrentText(animal['unit'])
        self.notes_edit.setText(animal['notes'])

    def get_animal_info(self):

        gender = 'Male' if self.gender_group['Male'].isChecked() else 'Female'
        return {
            'name': self.name_edit.text(),
            'id': self.id_edit.text(),
            'gender': gender,
            'weight': self.weight_edit.text(),
            'unit': self.unit_combo.currentText(),
            'notes': self.notes_edit.text(),
        }

class AnimalWindow(ThemedWindow):
    # 更新content页面信号
    update_content_signal = pyqtSignal()
    def __init__(self):
        super().__init__()


        self.animal_index_init = itertools.count()  # 无穷自增序列
        self._init_ui()
        self.init_animal()
    def _init_ui(self):
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

        # 添加创建动物按钮
        create_animal_button = QPushButton("创建动物")
        create_animal_button.clicked.connect(self.show_animal_dialog)
        self.top_layout.addWidget(create_animal_button)

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

        # 连接双击事件
        self.list_widget.itemDoubleClicked.connect(self.edit_animal_info)
    def init_animal(self):
        # 里面装的是Experiment_setting_entity
        self.setting_data: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)
        self.list_widget.clear()
        if self.setting_data is not None:
            if len(self.setting_data.animals) > 0:
                for index, animal in enumerate(self.setting_data.animals):
                    animal: Animal
                    item = QListWidgetItem(f"动物名称: {animal.name}, ID: {animal.id_write}, 性别: {'雌性' if animal.sex ==AnimalGender.FEMALE.value else '雄性'}, 重量: {animal.weight} {animal.weight_unit}, 备注: {animal.note}")
                    item.setToolTip(f"动物名称: {animal.name}, ID: {animal.id_write}, 性别: {'雌性' if animal.sex ==AnimalGender.FEMALE.value else '雄性'}, 重量: {animal.weight} {animal.weight_unit}, 备注: {animal.note}")
                    item.setData(Qt.ItemDataRole.UserRole, animal)  # 设置自定义数据
                    self.list_widget.addItem(item)
                    pass
            pass
        pass
        # 更新content页面
        self.update_content_signal.emit()
        pass
    # 添加动物
    def show_animal_dialog(self):
        dialog = AnimalDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:  # 如果用户点击了OK按钮
            animal_info = dialog.get_animal_info()
            self.setting_data.animals.append(Animal(id=next(self.animal_index_init),name=animal_info['name'],id_write=animal_info['id'],sex= animal_info['gender'],weight=animal_info['weight'],weight_unit=animal_info['unit'],note=animal_info['notes'],create_time=datetime.datetime.now(),update_time=datetime.datetime.now()))
        global_setting.set_setting("experiment_setting", self.setting_data)
        self.init_animal()

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
            item_data: Animal = item.data(Qt.ItemDataRole.UserRole)
            # 删除animal
            for index, animal in enumerate(self.setting_data.animals):
                animal: Animal
                if item_data is animal:
                    self.setting_data.animals.remove(animal)
            # 删除groups和animals关系
            for index, group_animal_record in enumerate(self.setting_data.animalGroupRecords):
                group_animal_record: AnimalGroupRecord
                if item_data.id == group_animal_record.aid:
                    self.setting_data.animalGroupRecords.remove(group_animal_record)
        global_setting.set_setting("experiment_setting", self.setting_data)
        self.init_animal()

    def edit_animal_info(self, item:QListWidgetItem):
        # 获取动物信息
        animal_info = self.parse_animal_info(item.text())
        dialog = AnimalDialog(animal_info)
        if dialog.exec() == QDialog.DialogCode.Accepted:  # 如果用户点击了OK按钮
            updated_info = dialog.get_animal_info()
            item_data:Animal = item.data(Qt.ItemDataRole.UserRole)
            for index, animal in enumerate(self.setting_data.animals):
                if animal.id == item_data.id:
                    self.setting_data.animals[index].name = updated_info['name']
                    self.setting_data.animals[index].id_write = updated_info['id']
                    self.setting_data.animals[index].sex = updated_info['gender']
                    self.setting_data.animals[index].weight = updated_info['weight']
                    self.setting_data.animals[index].weight_unit = updated_info['unit']
                    self.setting_data.animals[index].note = updated_info['notes']
                    self.setting_data.animals[index].update_time= datetime.datetime.now()

            global_setting.set_setting("experiment_setting", self.setting_data)
            self.init_animal()

    def parse_animal_info(self, text):
        # 解析动物信息的文本以供编辑
        parts = text.split(", ")
        name = parts[0].split(": ")[1]
        animal_id = parts[1].split(": ")[1]
        gender = parts[2].split(": ")[1]
        weight_unit = parts[3].split(": ")[1].split(" ")
        weight = weight_unit[0]
        unit = weight_unit[1]
        notes = parts[4].split(": ")[1]
        return {
            'name': name,
            'id': animal_id,
            'gender': gender,
            'weight': weight,
            'unit': unit,
            'notes': notes,
        }

if __name__ == "__main__":
    app = QApplication(sys.argv)

    main_window = AnimalWindow()
    main_window.show()

    sys.exit(app.exec())