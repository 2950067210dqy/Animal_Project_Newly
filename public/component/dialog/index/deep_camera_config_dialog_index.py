import typing

from PyQt6 import QtGui
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QComboBox, QLabel, QPushButton, QDialogButtonBox
from loguru import logger


import pyrealsense2 as rs

from public.component.dialog.deep_camera_config_dialog import Ui_deep_camera_config_dialog
from public.config_class.global_setting import global_setting
from util.folder_util import folder_util
from util.json_util import json_util



class deep_camera_config_dialog(QDialog):
    """

    """

    camera_config_finished_signal = pyqtSignal(list)
    def scan_realsense(self):
        # 搜索相机
        ctx = rs.context()
        devices = ctx.query_devices()
        # 返回插在电脑上的相机的序列号
        camera_series_in_computer = []
        id = 1
        for dev in devices:
            serial = dev.get_info(rs.camera_info.serial_number)
            usb_port_id = dev.get_info(rs.camera_info.physical_port)
            camera_series_in_computer.append({'id': id, 'serial': serial})
            logger.info(f"serial:{serial}|usb_port_id:{usb_port_id} |len:{len(devices)}")
            id += 1
        return camera_series_in_computer

    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        # 加载qss样式表
        logger.warning("tab7——show")

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.warning("tab7--hide")

    def __init__(self, parent=None, geometry: QRect = None, title="",tip=""):
        super().__init__()
        # 相机序列号数据 [{'id','serial'}]
        self.tip=tip
        self.camera_series_list = []
        # 下拉框所需要的数据
        self.camera_series_list_select_need = []
        # 下拉框所选择的数据
        self.camera_series_choose_list = [None for _ in range(8)]
        # 避免下拉框事件无限循环的标志位
        # 用于阻止无限循环的标志
        self.block_signal = False
        # 下拉框
        self.mouse_cage_1_comboBox: QComboBox = None
        self.mouse_cage_2_comboBox: QComboBox = None
        self.mouse_cage_3_comboBox: QComboBox = None
        self.mouse_cage_4_comboBox: QComboBox = None
        self.mouse_cage_5_comboBox: QComboBox = None
        self.mouse_cage_6_comboBox: QComboBox = None
        self.mouse_cage_7_comboBox: QComboBox = None
        self.mouse_cage_8_comboBox: QComboBox = None
        # 已选择数据显示label
        self.mouse_cage_1_checked_label: QLabel = None
        self.mouse_cage_2_checked_label: QLabel = None
        self.mouse_cage_3_checked_label: QLabel = None
        self.mouse_cage_4_checked_label: QLabel = None
        self.mouse_cage_5_checked_label: QLabel = None
        self.mouse_cage_6_checked_label: QLabel = None
        self.mouse_cage_7_checked_label: QLabel = None
        self.mouse_cage_8_checked_label: QLabel = None
        # 已选择数据清除按钮
        self.mouse_cage_1_checked_label_btn: QPushButton = None
        self.mouse_cage_2_checked_label_btn: QPushButton = None
        self.mouse_cage_3_checked_label_btn: QPushButton = None
        self.mouse_cage_4_checked_label_btn: QPushButton = None
        self.mouse_cage_5_checked_label_btn: QPushButton = None
        self.mouse_cage_6_checked_label_btn: QPushButton = None
        self.mouse_cage_7_checked_label_btn: QPushButton = None
        self.mouse_cage_8_checked_label_btn: QPushButton = None
        # 刷新按钮
        self.refresh_btn: QPushButton = None
        # ok按钮
        self.ok_btn: QPushButton = None

        # 获得数据
        self.get_data()
        # 实例化ui
        self._init_ui(parent, geometry, title)
        # 实例化自定义ui
        self._init_customize_ui()
        # 初始化数据 如果有json配置文件 就初始化相关数据
        self.init_data()
        # 实例化功能
        self._init_function()

        pass

        # 实例化ui

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        # 有父窗口添加父窗口
        if parent != None and geometry != None:
            self.setParent(parent)
            self.setGeometry(geometry)
        else:
            pass
        self.ui = Ui_deep_camera_config_dialog()
        self.ui.setupUi(self)
        self.setParent(None)
        # 窗口总是在最顶层
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        # 隐藏右上角的关闭按钮
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setModal(True)
        self.setWindowTitle(title)
        pass

    def init_data(self):
        config_file_path = f"./{global_setting.get_setting('camera_config')['DEEP_CAMERA']['camera_to_mouse_cage_number_file_name']}"
        if folder_util.is_exist_file(
                config_file_path):
            # 读取配置文件
            serials = json_util.read_json_to_dict_list(config_file_path)
            for data in serials:
                match data['mouse_cage_number']:
                    case 1:
                        self.mouse_cage_1_checked_label.setText(f"{data['serial']}")

                        pass
                    case 2:
                        self.mouse_cage_2_checked_label.setText(f"{data['serial']}")

                        pass
                    case 3:
                        self.mouse_cage_3_checked_label.setText(f"{data['serial']}")

                        pass
                    case 4:
                        self.mouse_cage_4_checked_label.setText(f"{data['serial']}")

                        pass
                    case 5:
                        self.mouse_cage_5_checked_label.setText(f"{data['serial']}")

                        pass
                    case 6:
                        self.mouse_cage_6_checked_label.setText(f"{data['serial']}")

                        pass
                    case 7:
                        self.mouse_cage_7_checked_label.setText(f"{data['serial']}")

                        pass
                    case 8:
                        self.mouse_cage_8_checked_label.setText(f"{data['serial']}")

                        pass
                    case _:
                        pass
                self.camera_series_choose_list[data['mouse_cage_number'] - 1] = data
                # 将原本的下拉列表值给删掉
                self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                       item['serial'] !=
                                                       data['serial']]
                # 阻止所有信号
                self.toggle_signal_combox(True)
                # 刷新各个下拉列表
                self.init_combox()
                # 重新启用信号
                self.toggle_signal_combox(False)
                self.combox_connect_func()
            pass
        pass

    def get_data(self):
        self.camera_series_list = self.scan_realsense()
        self.camera_series_list_select_need = []
        for camera in self.camera_series_list:
            self.camera_series_list_select_need.append(camera)
        pass

    # 实例化自定义ui
    def _init_customize_ui(self):
        tip_label:QLabel =self.findChild(QLabel, 'tip_label')
        if tip_label is not None:
            tip_label.setText(f"{tip_label.text()}{self.tip}")
        self.init_label()
        self.init_label_btn()
        self.init_combox()
        self.init_btn_other()
        self.combox_connect_func()
        self.label_btn_connect_func()
        self.btn_other_connect_func()
        pass

    # 实例化功能
    def _init_function(self):

        pass

    def show_frame(self):

        self.show()

    def init_label(self):
        # 实例化label
        self.mouse_cage_1_checked_label: QLabel = self.findChild(QLabel, "d_mouse_cage_1_checked_value")
        self.mouse_cage_2_checked_label: QLabel = self.findChild(QLabel, "d_mouse_cage_2_checked_value")
        self.mouse_cage_3_checked_label: QLabel = self.findChild(QLabel, "d_mouse_cage_3_checked_value")
        self.mouse_cage_4_checked_label: QLabel = self.findChild(QLabel, "d_mouse_cage_4_checked_value")
        self.mouse_cage_5_checked_label: QLabel = self.findChild(QLabel, "d_mouse_cage_5_checked_value")
        self.mouse_cage_6_checked_label: QLabel = self.findChild(QLabel, "d_mouse_cage_6_checked_value")
        self.mouse_cage_7_checked_label: QLabel = self.findChild(QLabel, "d_mouse_cage_7_checked_value")
        self.mouse_cage_8_checked_label: QLabel = self.findChild(QLabel, "d_mouse_cage_8_checked_value")
        pass

    def init_label_btn(self):
        """
        实例化清除按钮
        :return:
        """
        self.mouse_cage_1_checked_label_btn: QPushButton = self.findChild(QPushButton,
                                                                          "d_mouse_cage_1_checked_value_btn")
        self.mouse_cage_2_checked_label_btn: QPushButton = self.findChild(QPushButton,
                                                                          "d_mouse_cage_2_checked_value_btn")
        self.mouse_cage_3_checked_label_btn: QPushButton = self.findChild(QPushButton,
                                                                          "d_mouse_cage_3_checked_value_btn")
        self.mouse_cage_4_checked_label_btn: QPushButton = self.findChild(QPushButton,
                                                                          "d_mouse_cage_4_checked_value_btn")
        self.mouse_cage_5_checked_label_btn: QPushButton = self.findChild(QPushButton,
                                                                          "d_mouse_cage_5_checked_value_btn")
        self.mouse_cage_6_checked_label_btn: QPushButton = self.findChild(QPushButton,
                                                                          "d_mouse_cage_6_checked_value_btn")
        self.mouse_cage_7_checked_label_btn: QPushButton = self.findChild(QPushButton,
                                                                          "d_mouse_cage_7_checked_value_btn")
        self.mouse_cage_8_checked_label_btn: QPushButton = self.findChild(QPushButton,
                                                                          "d_mouse_cage_8_checked_value_btn")
        pass

    def label_btn_connect_func(self):
        """
               清除按钮连接事件
               :return:
               """
        if self.mouse_cage_1_checked_label_btn is not None:
            self.mouse_cage_1_checked_label_btn.clicked.connect(lambda:
                                                                self.label_btn_func(1))
        if self.mouse_cage_2_checked_label_btn is not None:
            self.mouse_cage_2_checked_label_btn.clicked.connect(lambda:
                                                                self.label_btn_func(2))
        if self.mouse_cage_3_checked_label_btn is not None:
            self.mouse_cage_3_checked_label_btn.clicked.connect(lambda:
                                                                self.label_btn_func(3))
        if self.mouse_cage_4_checked_label_btn is not None:
            self.mouse_cage_4_checked_label_btn.clicked.connect(lambda:
                                                                self.label_btn_func(4))
        if self.mouse_cage_5_checked_label_btn is not None:
            self.mouse_cage_5_checked_label_btn.clicked.connect(lambda:
                                                                self.label_btn_func(5))
        if self.mouse_cage_6_checked_label_btn is not None:
            self.mouse_cage_6_checked_label_btn.clicked.connect(lambda:
                                                                self.label_btn_func(6))
        if self.mouse_cage_7_checked_label_btn is not None:
            self.mouse_cage_7_checked_label_btn.clicked.connect(lambda:
                                                                self.label_btn_func(7))
        if self.mouse_cage_8_checked_label_btn is not None:
            self.mouse_cage_8_checked_label_btn.clicked.connect(lambda:
                                                                self.label_btn_func(8))
        pass

    def label_btn_func(self, param):
        """
        清除按钮事件
        :param param:
        :return:
        """
        # 将之前选中的值放回到下拉列表中（如果有的话）
        if self.camera_series_choose_list[param - 1] is not None:
            self.camera_series_list_select_need.append(
                {'id': len(self.camera_series_list_select_need) + 1,
                 'serial': self.camera_series_choose_list[param - 1]["serial"]}
            )
        self.camera_series_choose_list[param - 1] = None
        # label显示选中的值
        match param:
            case 1:
                self.mouse_cage_1_checked_label.setText("未选中")
            case 2:
                self.mouse_cage_2_checked_label.setText("未选中")
            case 3:
                self.mouse_cage_3_checked_label.setText("未选中")
            case 4:
                self.mouse_cage_4_checked_label.setText("未选中")
            case 5:
                self.mouse_cage_5_checked_label.setText("未选中")
            case 6:
                self.mouse_cage_6_checked_label.setText("未选中")
            case 7:
                self.mouse_cage_7_checked_label.setText("未选中")
            case 8:
                self.mouse_cage_8_checked_label.setText("未选中")
            case _:
                pass

        # 阻止所有信号
        self.toggle_signal_combox(True)
        # 刷新各个下拉列表
        self.init_combox()
        # 重新启用信号
        self.toggle_signal_combox(False)
        self.combox_connect_func()
        pass

    # 实例化所有下拉框
    def init_combox(self):
        self.mouse_cage_1_comboBox: QComboBox = self.findChild(QComboBox, "d_mouse_cage_1_select")
        self.mouse_cage_2_comboBox: QComboBox = self.findChild(QComboBox, "d_mouse_cage_2_select")
        self.mouse_cage_3_comboBox: QComboBox = self.findChild(QComboBox, "d_mouse_cage_3_select")
        self.mouse_cage_4_comboBox: QComboBox = self.findChild(QComboBox, "d_mouse_cage_4_select")
        self.mouse_cage_5_comboBox: QComboBox = self.findChild(QComboBox, "d_mouse_cage_5_select")
        self.mouse_cage_6_comboBox: QComboBox = self.findChild(QComboBox, "d_mouse_cage_6_select")
        self.mouse_cage_7_comboBox: QComboBox = self.findChild(QComboBox, "d_mouse_cage_7_select")
        self.mouse_cage_8_comboBox: QComboBox = self.findChild(QComboBox, "d_mouse_cage_8_select")
        if self.mouse_cage_1_comboBox is not None:
            self.mouse_cage_1_comboBox.clear()
            for camera_obj in self.camera_series_list_select_need:
                self.mouse_cage_1_comboBox.addItem(f"-相机序列号: {camera_obj['serial']}")
                pass

        if self.mouse_cage_2_comboBox is not None:
            self.mouse_cage_2_comboBox.clear()
            for camera_obj in self.camera_series_list_select_need:
                self.mouse_cage_2_comboBox.addItem(f"-相机序列号: {camera_obj['serial']}")
                pass

        if self.mouse_cage_3_comboBox is not None:
            self.mouse_cage_3_comboBox.clear()
            for camera_obj in self.camera_series_list_select_need:
                self.mouse_cage_3_comboBox.addItem(f"-相机序列号: {camera_obj['serial']}")
                pass

        if self.mouse_cage_4_comboBox is not None:
            self.mouse_cage_4_comboBox.clear()
            for camera_obj in self.camera_series_list_select_need:
                self.mouse_cage_4_comboBox.addItem(f"-相机序列号: {camera_obj['serial']}")
                pass

        if self.mouse_cage_5_comboBox is not None:
            self.mouse_cage_5_comboBox.clear()
            for camera_obj in self.camera_series_list_select_need:
                self.mouse_cage_5_comboBox.addItem(f"-相机序列号: {camera_obj['serial']}")
                pass

        if self.mouse_cage_6_comboBox is not None:
            self.mouse_cage_6_comboBox.clear()
            for camera_obj in self.camera_series_list_select_need:
                self.mouse_cage_6_comboBox.addItem(f"-相机序列号: {camera_obj['serial']}")
                pass

        if self.mouse_cage_7_comboBox is not None:
            self.mouse_cage_7_comboBox.clear()
            for camera_obj in self.camera_series_list_select_need:
                self.mouse_cage_7_comboBox.addItem(f"-相机序列号: {camera_obj['serial']}")
                pass

        if self.mouse_cage_8_comboBox is not None:
            self.mouse_cage_8_comboBox.clear()
            for camera_obj in self.camera_series_list_select_need:
                self.mouse_cage_8_comboBox.addItem(f"-相机序列号: {camera_obj['serial']}")
                pass

    def toggle_signal_combox(self, flag=True):
        """
        改变是否阻止各个combox的信号
        :param flag:
        :return:
        """
        self.mouse_cage_1_comboBox.blockSignals(flag)
        self.mouse_cage_2_comboBox.blockSignals(flag)
        self.mouse_cage_3_comboBox.blockSignals(flag)
        self.mouse_cage_4_comboBox.blockSignals(flag)
        self.mouse_cage_5_comboBox.blockSignals(flag)
        self.mouse_cage_6_comboBox.blockSignals(flag)
        self.mouse_cage_7_comboBox.blockSignals(flag)
        self.mouse_cage_8_comboBox.blockSignals(flag)

    def combox_disconnect_func(self):
        """
               解除连接各个下拉框的事件
               :return:
               """
        if self.mouse_cage_1_comboBox is not None:
            self.mouse_cage_1_comboBox.disconnect()

        if self.mouse_cage_2_comboBox is not None:
            self.mouse_cage_2_comboBox.disconnect()

        if self.mouse_cage_3_comboBox is not None:
            self.mouse_cage_3_comboBox.disconnect()

        if self.mouse_cage_4_comboBox is not None:
            self.mouse_cage_4_comboBox.disconnect()

        if self.mouse_cage_5_comboBox is not None:
            self.mouse_cage_5_comboBox.disconnect()

        if self.mouse_cage_6_comboBox is not None:
            self.mouse_cage_6_comboBox.disconnect()

        if self.mouse_cage_7_comboBox is not None:
            self.mouse_cage_7_comboBox.disconnect()

        if self.mouse_cage_8_comboBox is not None:
            self.mouse_cage_8_comboBox.disconnect()

    def combox_connect_func(self):
        """
        连接各个下拉框的事件
        :return:
        """
        self.combox_disconnect_func()
        if self.mouse_cage_1_comboBox is not None:
            self.mouse_cage_1_comboBox.activated.connect(
                self.selection_change_mouse_cage_1_combox)
        if self.mouse_cage_2_comboBox is not None:
            self.mouse_cage_2_comboBox.activated.connect(
                self.selection_change_mouse_cage_2_combox)
        if self.mouse_cage_3_comboBox is not None:
            self.mouse_cage_3_comboBox.activated.connect(
                self.selection_change_mouse_cage_3_combox)
        if self.mouse_cage_4_comboBox is not None:
            self.mouse_cage_4_comboBox.activated.connect(
                self.selection_change_mouse_cage_4_combox)
        if self.mouse_cage_5_comboBox is not None:
            self.mouse_cage_5_comboBox.activated.connect(
                self.selection_change_mouse_cage_5_combox)
        if self.mouse_cage_6_comboBox is not None:
            self.mouse_cage_6_comboBox.activated.connect(
                self.selection_change_mouse_cage_6_combox)
        if self.mouse_cage_7_comboBox is not None:
            self.mouse_cage_7_comboBox.activated.connect(
                self.selection_change_mouse_cage_7_combox)
        if self.mouse_cage_8_comboBox is not None:
            self.mouse_cage_8_comboBox.activated.connect(
                self.selection_change_mouse_cage_8_combox)
        pass

    def selection_change_mouse_cage_1_combox(self, data_index):
        try:

            choose_value = {
                "mouse_cage_number": 1,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }
            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                   item['serial'] != self.camera_series_list_select_need[data_index][
                                                       'serial']]
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if self.camera_series_choose_list[0] is not None:
                self.camera_series_list_select_need.append(
                    {'id': len(self.camera_series_list_select_need) + 1,
                     'serial': self.camera_series_choose_list[0]["serial"]}
                )
            # 存储选中的下拉列表值
            self.camera_series_choose_list[0] = choose_value
            # label显示选中的值
            self.mouse_cage_1_checked_label.setText(choose_value['serial'])

            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()
            logger.debug(f"鼠笼1的{choose_value['serial']}已经被选中")

        except Exception as e:
            logger.error(e)
        pass

    def selection_change_mouse_cage_2_combox(self, data_index):
        try:

            choose_value = {
                "mouse_cage_number": 2,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }
            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                   item['serial'] != self.camera_series_list_select_need[data_index][
                                                       'serial']]
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if self.camera_series_choose_list[1] is not None:
                self.camera_series_list_select_need.append(
                    {'id': len(self.camera_series_list_select_need) + 1,
                     'serial': self.camera_series_choose_list[1]["serial"]}
                )
            # 存储选中的下拉列表值
            self.camera_series_choose_list[1] = choose_value
            # label显示选中的值
            self.mouse_cage_2_checked_label.setText(choose_value['serial'])

            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()
            logger.debug(f"鼠笼2的{choose_value['serial']}已经被选中")

        except Exception as e:
            logger.error(e)
        pass

    def selection_change_mouse_cage_3_combox(self, data_index):
        try:

            choose_value = {
                "mouse_cage_number": 3,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }
            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                   item['serial'] != self.camera_series_list_select_need[data_index][
                                                       'serial']]
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if self.camera_series_choose_list[2] is not None:
                self.camera_series_list_select_need.append(
                    {'id': len(self.camera_series_list_select_need) + 1,
                     'serial': self.camera_series_choose_list[2]["serial"]}
                )
            # 存储选中的下拉列表值
            self.camera_series_choose_list[2] = choose_value
            # label显示选中的值
            self.mouse_cage_3_checked_label.setText(choose_value['serial'])
            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()
            logger.debug(f"鼠笼3的{choose_value['serial']}已经被选中")

        except Exception as e:
            logger.error(e)
        pass

    def selection_change_mouse_cage_4_combox(self, data_index):
        try:

            choose_value = {
                "mouse_cage_number": 4,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }
            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                   item['serial'] != self.camera_series_list_select_need[data_index][
                                                       'serial']]
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if self.camera_series_choose_list[3] is not None:
                self.camera_series_list_select_need.append(
                    {'id': len(self.camera_series_list_select_need) + 1,
                     'serial': self.camera_series_choose_list[3]["serial"]}
                )
            # 存储选中的下拉列表值
            self.camera_series_choose_list[3] = choose_value
            # label显示选中的值
            self.mouse_cage_4_checked_label.setText(choose_value['serial'])

            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()
            logger.debug(f"鼠笼4的{choose_value['serial']}已经被选中")

        except Exception as e:
            logger.error(e)
        pass

    def selection_change_mouse_cage_5_combox(self, data_index):
        try:

            choose_value = {
                "mouse_cage_number": 5,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }
            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                   item['serial'] != self.camera_series_list_select_need[data_index][
                                                       'serial']]
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if self.camera_series_choose_list[4] is not None:
                self.camera_series_list_select_need.append(
                    {'id': len(self.camera_series_list_select_need) + 1,
                     'serial': self.camera_series_choose_list[4]["serial"]}
                )
            # 存储选中的下拉列表值
            self.camera_series_choose_list[4] = choose_value
            # label显示选中的值
            self.mouse_cage_5_checked_label.setText(choose_value['serial'])

            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()
            logger.debug(f"鼠笼5的{choose_value['serial']}已经被选中")

        except Exception as e:
            logger.error(e)
        pass

    def selection_change_mouse_cage_6_combox(self, data_index):
        try:

            choose_value = {
                "mouse_cage_number": 6,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }
            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                   item['serial'] != self.camera_series_list_select_need[data_index][
                                                       'serial']]
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if self.camera_series_choose_list[5] is not None:
                self.camera_series_list_select_need.append(
                    {'id': len(self.camera_series_list_select_need) + 1,
                     'serial': self.camera_series_choose_list[5]["serial"]}
                )
            # 存储选中的下拉列表值
            self.camera_series_choose_list[5] = choose_value
            # label显示选中的值
            self.mouse_cage_6_checked_label.setText(choose_value['serial'])

            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()
            logger.debug(f"鼠笼6的{choose_value['serial']}已经被选中")

        except Exception as e:
            logger.error(e)
        pass

    def selection_change_mouse_cage_7_combox(self, data_index):
        try:

            choose_value = {
                "mouse_cage_number": 7,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }
            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                   item['serial'] != self.camera_series_list_select_need[data_index][
                                                       'serial']]
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if self.camera_series_choose_list[6] is not None:
                self.camera_series_list_select_need.append(
                    {'id': len(self.camera_series_list_select_need) + 1,
                     'serial': self.camera_series_choose_list[6]["serial"]}
                )
            # 存储选中的下拉列表值
            self.camera_series_choose_list[6] = choose_value
            # label显示选中的值
            self.mouse_cage_7_checked_label.setText(choose_value['serial'])

            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()
            logger.debug(f"鼠笼7的{choose_value['serial']}已经被选中")

        except Exception as e:
            logger.error(e)
        pass

    def selection_change_mouse_cage_8_combox(self, data_index):
        try:

            choose_value = {
                "mouse_cage_number": 8,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }
            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [item for item in self.camera_series_list_select_need if
                                                   item['serial'] != self.camera_series_list_select_need[data_index][
                                                       'serial']]
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if self.camera_series_choose_list[7] is not None:
                self.camera_series_list_select_need.append(
                    {'id': len(self.camera_series_list_select_need) + 1,
                     'serial': self.camera_series_choose_list[7]["serial"]}
                )
            # 存储选中的下拉列表值
            self.camera_series_choose_list[7] = choose_value
            # label显示选中的值
            self.mouse_cage_8_checked_label.setText(choose_value['serial'])
            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()
            logger.debug(f"鼠笼8的{choose_value['serial']}已经被选中")
        except Exception as e:
            logger.error(e)
        pass

    def init_btn_other(self):
        # 实例化其他的按钮
        # 获取 OK 按钮的引用
        button_box = self.findChild(QDialogButtonBox, "dialog_btn")
        if button_box is not None:
            self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        # 获取 REFRESH 按钮的引用
        self.refresh_btn = self.findChild(QPushButton, "refresh")
        pass

    def btn_other_connect_func(self):
        # 其他的按钮事件连接
        if self.ok_button is not None:
            self.ok_button.clicked.connect(self.ok_func)
        if self.refresh_btn is not None:
            self.refresh_btn.clicked.connect(self.refresh_func)
        pass

    def refresh_func(self):
        """
        refresh按钮事件
        :return:
        """
        self.get_data()
        # 将原本的下拉列表值给删掉
        # print(f"need:{self.camera_series_list_select_need}")
        choose_list = [i['serial'] for i in self.camera_series_choose_list if i is not None]
        # print(f"choose_list:{choose_list}")
        camera_series_list_select_need_flag = []
        for item in self.camera_series_list_select_need:
            if item['serial'] not in choose_list:
                camera_series_list_select_need_flag.append(item)
        self.camera_series_list_select_need = camera_series_list_select_need_flag
        # print(f"after:{self.camera_series_list_select_need}")
        self.init_combox()

    def ok_func(self):
        """
        ok按钮事件
        :return:
        """
        # 清洗已选择的数据None
        choose_data = []
        for data in self.camera_series_choose_list:
            if data is not None:
                choose_data.append(data)
        logger.debug(f"选择的数据为：{choose_data}")

        # 1.把选择的数据存到json中
        config_file_path = f"./{global_setting.get_setting('camera_config')['DEEP_CAMERA']['camera_to_mouse_cage_number_file_name']}"
        json_util.store_json_from_dict_list(filename=config_file_path, data=choose_data)
        # 2.激活外面主函数的信号 实例化相机线程
        self.camera_config_finished_signal.emit(choose_data)
        pass
