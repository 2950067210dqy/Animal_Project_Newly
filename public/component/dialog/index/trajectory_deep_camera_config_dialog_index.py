import time
import typing

from PyQt6 import QtGui
from PyQt6.QtCore import QRect, Qt, pyqtSignal, QCoreApplication
from PyQt6.QtWidgets import QDialog, QComboBox, QLabel, QPushButton, QDialogButtonBox
from loguru import logger

import pyrealsense2 as rs

from public.component.dialog.trajectory_deep_camera_config_dialog import Ui_deep_camera_config_dialog
from public.config_class.global_setting import global_setting
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.util.folder_util import folder_util
from public.util.json_util import json_util
from public.util.time_util import time_util


class trajectory_deep_camera_config_dialog(QDialog):
    """
    深度相机配置对话框 - 支持动态笼子数量
    """

    def scan_realsense(self):
        """扫描连接的RealSense相机"""
        try:
            ctx = rs.context()
            devices = ctx.query_devices()
            camera_series_in_computer = []
            id = 1
            for dev in devices:
                serial = dev.get_info(rs.camera_info.serial_number)
                usb_port_id = dev.get_info(rs.camera_info.physical_port)
                camera_series_in_computer.append({'id': id, 'serial': serial})
                logger.info(f"Found camera: serial={serial}, usb_port_id={usb_port_id}")
                id += 1
            return camera_series_in_computer
        except Exception as e:
            logger.error(f"扫描相机失败: {e}")
            return []

    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        logger.info("相机配置对话框显示")

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.info("相机配置对话框隐藏")

    def __init__(self, parent=None, geometry: QRect = None, title="", tip=""):
        super().__init__()

        # ==================== 获取开启的笼子ID ====================
        self.enabled_cage_ids = self._get_enabled_cage_ids()

        if not self.enabled_cage_ids:
            logger.warning("没有找到开启的笼子，使用默认配置 1-16")
            self.enabled_cage_ids = list(range(1, 17))

        logger.info(f"相机配置对话框初始化，笼子数量: {len(self.enabled_cage_ids)}")

        # 相机序列号数据 [{'id','serial'}]
        self.tip = tip
        self.camera_series_list = []
        # 下拉框所需要的数据
        self.camera_series_list_select_need = []

        # ==================== 修改：改为字典存储，支持动态笼子数量 ====================
        # 下拉框所选择的数据 - {cage_id: data}
        self.camera_series_choose_dict = {}

        # 下拉框 - {cage_id: QComboBox}
        self.mouse_cage_comboBox_dict = {}
        # 已选择数据显示label - {cage_id: QLabel}
        self.mouse_cage_checked_label_dict = {}
        # 已选择数据清除按钮 - {cage_id: QPushButton}
        self.mouse_cage_checked_label_btn_dict = {}

        # 刷新按钮
        self.refresh_btn: QPushButton = None
        # ok按钮
        self.ok_button: QPushButton = None

        # 获得数据
        self.get_data()
        # 实例化ui（传入开启的笼子ID）
        self._init_ui(parent, geometry, title)
        # 实例化自定义ui
        self._init_customize_ui()
        # 初始化数据 如果有json配置文件 就初始化相关数据
        self.init_data()
        # 实例化功能
        self._init_function()

    def _get_enabled_cage_ids(self):
        """
        获取用户开启的笼子ID列表
        从 experiment_setting 中读取已启用的分组
        """
        try:
            experiment_setting = global_setting.get_setting("experiment_setting", None)

            if experiment_setting is None:
                logger.warning("experiment_setting 未初始化")
                return []

            # 获取所有已启用的分组（is_selected == 1）
            if hasattr(experiment_setting, 'groups') and experiment_setting.groups:
                enabled_groups = [g for g in experiment_setting.groups if g.is_selected == 1]
                enabled_cage_ids = [g.id for g in enabled_groups]

                logger.info(f"成功获取开启的笼子列表: {sorted(enabled_cage_ids)}")
                return sorted(enabled_cage_ids)
            else:
                logger.warning("experiment_setting 中没有找到已启用的分组")
                return []
        except Exception as e:
            logger.error(f"获取开启的笼子ID失败: {e}")
            return []

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        """初始化UI"""
        if parent is not None and geometry is not None:
            self.setParent(parent)
            self.setGeometry(geometry)

        # ==================== 关键修改：传入开启的笼子ID到UI初始化 ====================
        self.ui = Ui_deep_camera_config_dialog()
        self.ui.setupUi(self, enabled_cage_ids=self.enabled_cage_ids)

        self.setParent(None)
        # 隐藏右上角的关闭按钮
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setModal(True)
        self.setWindowTitle(title)

    def init_data(self):
        """初始化数据 - 从配置文件加载已保存的相机配置"""
        try:
            config_file_path = f"./{global_setting.get_setting('camera_config')['DEEP_CAMERA']['camera_to_mouse_cage_number_file_name']}"

            if folder_util.is_exist_file(config_file_path):
                # 读取配置文件
                serials = json_util.read_json_to_dict_list(config_file_path)

                for data in serials:
                    mouse_cage_number = data['mouse_cage_number']

                    # 只加载在开启笼子列表中的配置
                    if mouse_cage_number in self.enabled_cage_ids:
                        # 更新label显示已选择的序列号
                        if mouse_cage_number in self.mouse_cage_checked_label_dict:
                            self.mouse_cage_checked_label_dict[mouse_cage_number].setText(f"{data['serial']}")

                        self.camera_series_choose_dict[mouse_cage_number] = data

                        # 将原本的下拉列表值给删掉
                        self.camera_series_list_select_need = [
                            item for item in self.camera_series_list_select_need
                            if item['serial'] != data['serial']
                        ]

                # 阻止所有信号
                self.toggle_signal_combox(True)
                # 刷新各个下拉列表
                self.init_combox()
                # 重新启用信号
                self.toggle_signal_combox(False)
                self.combox_connect_func()

                logger.info("已加载相机配置文件")
            else:
                logger.info("没有找到相机配置文件，使用默认配置")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")

    def get_data(self):
        """获取相机列表"""
        self.camera_series_list = self.scan_realsense()
        self.camera_series_list_select_need = []
        for camera in self.camera_series_list:
            self.camera_series_list_select_need.append(camera)

    def _init_customize_ui(self):
        """初始化自定义UI"""
        tip_label: QLabel = self.findChild(QLabel, 'tip_label')
        if tip_label is not None:
            tip_label.setText(f"{tip_label.text()}{self.tip}")

        self.init_label()
        self.init_label_btn()
        self.init_combox()
        self.init_btn_other()
        self.combox_connect_func()
        self.label_btn_connect_func()
        self.btn_other_connect_func()

    def _init_function(self):
        pass

    def show_frame(self):
        """显示对话框"""
        self.exec()

    def init_label(self):
        """实例化label - 只初始化开启的笼子"""
        for cage_id in self.enabled_cage_ids:
            label_name = f"d_mouse_cage_{cage_id}_checked_value"
            label = self.findChild(QLabel, label_name)
            if label is not None:
                self.mouse_cage_checked_label_dict[cage_id] = label
                logger.debug(f"初始化笼子 {cage_id} 的label")

    def init_label_btn(self):
        """实例化清除按钮 - 只初始化开启的笼子"""
        for cage_id in self.enabled_cage_ids:
            btn_name = f"d_mouse_cage_{cage_id}_checked_value_btn"
            btn = self.findChild(QPushButton, btn_name)
            if btn is not None:
                self.mouse_cage_checked_label_btn_dict[cage_id] = btn
                logger.debug(f"初始化笼子 {cage_id} 的清除按钮")

    def label_btn_connect_func(self):
        """清除按钮连接事件 - 只连接开启的笼子"""
        for cage_id in self.enabled_cage_ids:
            if cage_id in self.mouse_cage_checked_label_btn_dict:
                btn = self.mouse_cage_checked_label_btn_dict[cage_id]
                btn.clicked.connect(
                    lambda checked=False, cage_num=cage_id: self.label_btn_func(cage_num)
                )

    def label_btn_func(self, cage_num):
        """
        清除按钮事件
        :param cage_num: 笼子号
        :return:
        """
        try:
            # 将之前选中的值放回到下拉列表中（如果有的话）
            if cage_num in self.camera_series_choose_dict:
                self.camera_series_list_select_need.append({
                    'id': len(self.camera_series_list_select_need) + 1,
                    'serial': self.camera_series_choose_dict[cage_num]["serial"]
                })

            # 删除选择记录
            if cage_num in self.camera_series_choose_dict:
                del self.camera_series_choose_dict[cage_num]

            # label显示未选中
            if cage_num in self.mouse_cage_checked_label_dict:
                self.mouse_cage_checked_label_dict[cage_num].setText("未选中")

            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()

            logger.debug(f"笼子{cage_num}的映射已清除")
        except Exception as e:
            logger.error(f"清除笼子{cage_num}的映射失败: {e}")

    def init_combox(self):
        """实例化下拉框 - 只初始化开启的笼子"""
        for cage_id in self.enabled_cage_ids:
            combo_name = f"d_mouse_cage_{cage_id}_select"
            combo: QComboBox = self.findChild(QComboBox, combo_name)

            if combo is not None:
                combo.clear()
                for camera_obj in self.camera_series_list_select_need:
                    combo.addItem(f"-相机序列号: {camera_obj['serial']}")
                self.mouse_cage_comboBox_dict[cage_id] = combo
                logger.debug(f"初始化笼子 {cage_id} 的下拉框")

    def toggle_signal_combox(self, flag=True):
        """
        改变是否阻止下拉框的信号
        :param flag: True为阻止，False为启用
        :return:
        """
        for cage_id in self.mouse_cage_comboBox_dict:
            self.mouse_cage_comboBox_dict[cage_id].blockSignals(flag)

    def combox_disconnect_func(self):
        """解除连接下拉框的事件"""
        for cage_id in self.mouse_cage_comboBox_dict:
            try:
                self.mouse_cage_comboBox_dict[cage_id].disconnect()
            except:
                pass

    def combox_connect_func(self):
        """连接下拉框的事件"""
        self.combox_disconnect_func()
        for cage_id in self.enabled_cage_ids:
            if cage_id in self.mouse_cage_comboBox_dict:
                self.mouse_cage_comboBox_dict[cage_id].activated.connect(
                    lambda data_index, cage_num=cage_id: self.selection_change_combox(cage_num, data_index)
                )

    def selection_change_combox(self, cage_num, data_index):
        """
        下拉框选择变化事件 - 通用处理所有开启的笼子
        :param cage_num: 笼子号
        :param data_index: 下拉框选择的索引
        :return:
        """
        try:
            if data_index >= len(self.camera_series_list_select_need):
                logger.warning(f"笼子{cage_num}的索引{data_index}超出范围")
                return

            choose_value = {
                "mouse_cage_number": cage_num,
                "serial": self.camera_series_list_select_need[data_index]['serial']
            }

            # 将原本的下拉列表值给删掉
            self.camera_series_list_select_need = [
                item for item in self.camera_series_list_select_need
                if item['serial'] != self.camera_series_list_select_need[data_index]['serial']
            ]

            # 将之前选中的值放回到下拉列表中（如果有的话）
            if cage_num in self.camera_series_choose_dict:
                self.camera_series_list_select_need.append({
                    'id': len(self.camera_series_list_select_need) + 1,
                    'serial': self.camera_series_choose_dict[cage_num]["serial"]
                })

            # 存储选中的下拉列表值
            self.camera_series_choose_dict[cage_num] = choose_value

            # label显示选中的值
            if cage_num in self.mouse_cage_checked_label_dict:
                self.mouse_cage_checked_label_dict[cage_num].setText(choose_value['serial'])

            # 阻止所有信号
            self.toggle_signal_combox(True)
            # 刷新各个下拉列表
            self.init_combox()
            # 重新启用信号
            self.toggle_signal_combox(False)
            self.combox_connect_func()

            logger.debug(f"笼子{cage_num}的{choose_value['serial']}已经被选中")

        except Exception as e:
            logger.error(f"笼子{cage_num}选择变化时出错: {e}")

    def init_btn_other(self):
        """实例化其他的按钮"""
        # 获取 OK 按钮的引用
        button_box = self.findChild(QDialogButtonBox, "dialog_btn")
        if button_box is not None:
            self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)

        # 获取 REFRESH 按钮的引用
        self.refresh_btn = self.findChild(QPushButton, "refresh")

    def btn_other_connect_func(self):
        """其他的按钮事件连接"""
        if self.ok_button is not None:
            self.ok_button.clicked.connect(self.ok_func)
        if self.refresh_btn is not None:
            self.refresh_btn.clicked.connect(self.refresh_func)

    def refresh_func(self):
        """
        refresh按钮事件 - 刷新相机列表
        :return:
        """
        try:
            self.get_data()
            # 获取已选择的序列号列表
            choose_list = [i['serial'] for i in self.camera_series_choose_dict.values() if i is not None]
            # 过滤掉已选择的序列号
            camera_series_list_select_need_flag = []
            for item in self.camera_series_list_select_need:
                if item['serial'] not in choose_list:
                    camera_series_list_select_need_flag.append(item)

            self.camera_series_list_select_need = camera_series_list_select_need_flag
            # 刷新下拉列表
            self.init_combox()
            logger.info("相机列表已刷新")
        except Exception as e:
            logger.error(f"刷新相机列表时出错: {e}")

    def ok_func(self):
        """
        ok按钮事件 - 保存配置
        :return:
        """
        try:
            # 清洗已选择的数据，转换为列表
            choose_data = []
            for cage_id in sorted(self.camera_series_choose_dict.keys()):
                data = self.camera_series_choose_dict[cage_id]
                if data is not None:
                    choose_data.append(data)

            logger.debug(f"选择的数据为：{choose_data}")

            # 1.把选择的数据存到json中
            config_file_path = f"./{global_setting.get_setting('camera_config')['DEEP_CAMERA']['camera_to_mouse_cage_number_file_name']}"
            json_util.store_json_from_dict_list(filename=config_file_path, data=choose_data)

            # 2.激活外面主函数的信号 实例化相机线程
            queue = global_setting.get_setting("queue", None)
            if queue is not None:
                queue.put(ObjectQueueItem(
                    origin="deep_camera_config_dialog_index",
                    to='main_deep_camera',
                    data=choose_data,
                    title="camera_config",
                    time=time_util.get_format_from_time(time.time())
                ))

            logger.info("相机配置已保存")
            self.accept()

        except Exception as e:
            logger.error(f"保存配置时出错: {e}")