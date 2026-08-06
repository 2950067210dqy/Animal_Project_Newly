import time
import typing

import cv2
from PyQt6 import QtGui
from PyQt6.QtCore import QRect, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QPushButton
from loguru import logger

from public.component.dialog.deep_camera_config_dialog import Ui_deep_camera_config_dialog
from public.config_class.global_setting import global_setting
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.util.folder_util import folder_util
from public.util.json_util import json_util
from public.util.time_util import time_util


class UVCCameraScanThread(QThread):
    scan_finished = pyqtSignal(list, str)

    def run(self):
        try:
            cameras = []
            for scan_round in range(2):
                cameras = self._scan_once()
                if cameras or scan_round == 1:
                    break
                self.msleep(750)
            self.scan_finished.emit(cameras, "")
        except Exception as error:
            logger.exception(f"scan UVC cameras failed: {error}")
            self.scan_finished.emit([], str(error))

    @staticmethod
    def _scan_once():
        cameras = []
        for index in range(10):
            capture = None
            for backend in UVCCameraScanThread._backends():
                candidate = cv2.VideoCapture(index, backend) if backend is not None else cv2.VideoCapture(index)
                if candidate is None or not candidate.isOpened():
                    if candidate is not None:
                        candidate.release()
                    continue

                frame_ok = False
                for _ in range(5):
                    frame_ok, _ = candidate.read()
                    if frame_ok:
                        break
                if frame_ok:
                    capture = candidate
                    break
                else:
                    candidate.release()

            if capture is None:
                continue

            try:
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                cameras.append(
                    {
                        "id": len(cameras) + 1,
                        "serial": f"uvc_index_{index}",
                        "instance_id": f"uvc_index_{index}",
                        "display_name": (
                            f"UVC Camera {index} ({width}x{height})"
                            if width and height
                            else f"UVC Camera {index}"
                        ),
                        "device_index": index,
                    }
                )
                logger.info(f"Found UVC camera: index={index}, size={width}x{height}")
            finally:
                capture.release()
        logger.info(f"UVC camera scan completed: count={len(cameras)}")
        return cameras

    @staticmethod
    def _backends():
        backends = []
        if hasattr(cv2, "CAP_DSHOW"):
            backends.append(cv2.CAP_DSHOW)
        if hasattr(cv2, "CAP_MSMF"):
            backends.append(cv2.CAP_MSMF)
        backends.append(None)
        return backends


class deep_camera_config_dialog(QDialog):
    def __init__(self, parent=None, geometry: QRect = None, title="", tip=""):
        super().__init__()
        self.tip = tip
        self.camera_series_list = []
        self.camera_series_list_select_need = []
        self.camera_series_choose_list = [None for _ in range(8)]

        self.combo_boxes: dict[int, QComboBox] = {}
        self.checked_labels: dict[int, QLabel] = {}
        self.clear_buttons: dict[int, QPushButton] = {}

        self.refresh_btn: QPushButton | None = None
        self.ok_btn: QPushButton | None = None
        self.scan_thread: UVCCameraScanThread | None = None

        self._init_ui(parent, geometry, title)
        self._init_customize_ui()
        self.init_data()

    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        logger.warning("deep_config_dialog-show")
        super().showEvent(a0)

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.warning("deep_config_dialog-hide")
        super().hideEvent(a0)

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        if parent is not None and geometry is not None:
            self.setParent(parent)
            self.setGeometry(geometry)

        self.ui = Ui_deep_camera_config_dialog()
        self.ui.setupUi(self)
        self.setParent(None)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setModal(True)
        self.setWindowTitle(title)

    def _init_customize_ui(self):
        tip_label: QLabel = self.findChild(QLabel, "tip_label")
        if tip_label is not None:
            tip_label.setText(f"{tip_label.text()}{self.tip}")

        for cage_num in range(1, 9):
            combo = self.findChild(QComboBox, f"d_mouse_cage_{cage_num}_select")
            label = self.findChild(QLabel, f"d_mouse_cage_{cage_num}_checked_value")
            btn = self.findChild(QPushButton, f"d_mouse_cage_{cage_num}_checked_value_btn")
            if combo is not None:
                self.combo_boxes[cage_num] = combo
            if label is not None:
                self.checked_labels[cage_num] = label
            if btn is not None:
                self.clear_buttons[cage_num] = btn

        button_box = self.findChild(QDialogButtonBox, "dialog_btn")
        if button_box is not None:
            try:
                button_box.accepted.disconnect()
            except TypeError:
                pass
            self.ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.refresh_btn = self.findChild(QPushButton, "refresh")

        self.init_combox()
        self.bind_events()

    def bind_events(self):
        for cage_num, btn in self.clear_buttons.items():
            btn.clicked.connect(lambda checked=False, n=cage_num: self.label_btn_func(n))

        for cage_num, combo in self.combo_boxes.items():
            combo.activated.connect(lambda data_index, n=cage_num: self.selection_change_combox(n, data_index))

        if self.refresh_btn is not None:
            self.refresh_btn.clicked.connect(self.refresh_func)
        if self.ok_btn is not None:
            self.ok_btn.clicked.connect(self.ok_func)

    def init_data(self):
        config_file_path = f"./{global_setting.get_setting('camera_config')['DEEP_CAMERA']['camera_to_mouse_cage_number_file_name']}"
        if not folder_util.is_exist_file(config_file_path):
            return

        serials = json_util.read_json_to_dict_list(config_file_path)
        for data in serials:
            cage_num = data.get("mouse_cage_number")
            if not isinstance(cage_num, int) or cage_num < 1 or cage_num > 8:
                continue

            self.camera_series_choose_list[cage_num - 1] = data
            if cage_num in self.checked_labels:
                self.checked_labels[cage_num].setText(data.get("display_name") or data.get("serial", "未选中"))

        selected_serials = {
            item.get("serial")
            for item in self.camera_series_choose_list
            if item is not None
        }
        self.camera_series_list_select_need = [
            item for item in self.camera_series_list_select_need if item.get("serial") not in selected_serials
        ]
        self.init_combox()

    def init_combox(self):
        for combo in self.combo_boxes.values():
            combo.blockSignals(True)
            combo.clear()
            for camera_obj in self.camera_series_list_select_need:
                combo.addItem(f"-相机: {camera_obj.get('display_name', camera_obj.get('serial', ''))}")
            combo.blockSignals(False)

    def label_btn_func(self, cage_num):
        old_value = self.camera_series_choose_list[cage_num - 1]
        if old_value is not None:
            self.camera_series_list_select_need.append(
                {
                    "id": len(self.camera_series_list_select_need) + 1,
                    "serial": old_value.get("serial"),
                    "instance_id": old_value.get("instance_id", old_value.get("serial")),
                    "display_name": old_value.get("display_name", old_value.get("serial")),
                    "device_index": old_value.get("device_index"),
                }
            )

        self.camera_series_choose_list[cage_num - 1] = None
        if cage_num in self.checked_labels:
            self.checked_labels[cage_num].setText("未选中")
        self.init_combox()

    def selection_change_combox(self, cage_num, data_index):
        if data_index < 0 or data_index >= len(self.camera_series_list_select_need):
            return

        selected_camera = self.camera_series_list_select_need[data_index]
        old_value = self.camera_series_choose_list[cage_num - 1]
        if old_value is not None:
            self.camera_series_list_select_need.append(
                {
                    "id": len(self.camera_series_list_select_need) + 1,
                    "serial": old_value.get("serial"),
                    "instance_id": old_value.get("instance_id", old_value.get("serial")),
                    "display_name": old_value.get("display_name", old_value.get("serial")),
                    "device_index": old_value.get("device_index"),
                }
            )

        self.camera_series_choose_list[cage_num - 1] = {
            "mouse_cage_number": cage_num,
            "serial": selected_camera.get("serial"),
            "instance_id": selected_camera.get("instance_id", selected_camera.get("serial")),
            "display_name": selected_camera.get("display_name", selected_camera.get("serial")),
            "device_index": selected_camera.get("device_index"),
        }

        self.camera_series_list_select_need = [
            item for idx, item in enumerate(self.camera_series_list_select_need) if idx != data_index
        ]

        if cage_num in self.checked_labels:
            self.checked_labels[cage_num].setText(
                self.camera_series_choose_list[cage_num - 1].get("display_name")
                or self.camera_series_choose_list[cage_num - 1].get("serial", "未选中")
            )
        self.init_combox()

    def refresh_func(self):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            return

        if self.refresh_btn is not None:
            self.refresh_btn.setEnabled(False)
        if self.ok_btn is not None:
            self.ok_btn.setEnabled(False)

        self.scan_thread = UVCCameraScanThread(self)
        self.scan_thread.scan_finished.connect(self._apply_scan_result)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.start()

    def _apply_scan_result(self, cameras, error):
        self.camera_series_list = [item for item in cameras if isinstance(item, dict)]
        self.camera_series_list_select_need = list(self.camera_series_list)
        selected_serials = {
            item.get("serial")
            for item in self.camera_series_choose_list
            if item is not None
        }
        self.camera_series_list_select_need = [
            item for item in self.camera_series_list_select_need if item.get("serial") not in selected_serials
        ]
        self.init_combox()

        if self.refresh_btn is not None:
            self.refresh_btn.setEnabled(True)
        if self.ok_btn is not None:
            self.ok_btn.setEnabled(True)
        self.scan_thread = None

        if error:
            logger.error(f"deep camera refresh failed: {error}")

    def ok_func(self):
        choose_data = [item for item in self.camera_series_choose_list if item is not None]
        config_file_path = f"./{global_setting.get_setting('camera_config')['DEEP_CAMERA']['camera_to_mouse_cage_number_file_name']}"
        if not choose_data and folder_util.is_exist_file(config_file_path):
            old_data = json_util.read_json_to_dict_list(config_file_path)
            if old_data:
                QMessageBox.warning(self, "无法保存", "当前未选择任何深度相机，原配置不会被清空。")
                return
        json_util.store_json_from_dict_list(filename=config_file_path, data=choose_data)

        queue = global_setting.get_setting("queue", None)
        if queue is not None:
            queue.put(
                ObjectQueueItem(
                    origin="deep_camera_config_dialog_index",
                    to="main_deep_camera",
                    data=choose_data,
                    title="camera_config",
                    time=time_util.get_format_from_time(time.time()),
                )
            )

        self.accept()

    def show_frame(self):
        QTimer.singleShot(0, self.refresh_func)
        self.exec()
