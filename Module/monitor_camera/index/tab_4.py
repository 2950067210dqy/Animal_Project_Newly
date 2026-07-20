import os
import re
import time
import traceback
import typing
from datetime import datetime, timedelta

import cv2
from PyQt6 import QtGui
from PyQt6.QtCharts import QChart, QChartView, QDateTimeAxis, QScatterSeries, QValueAxis
from PyQt6.QtCore import QDateTime, QPointF, QRect, QRectF, Qt, pyqtSignal, QMargins
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from Module.mouse_trajectory.service import MouseTrajectoryThread
from Module.monitor_camera.ui.tab4_window import Ui_tab4_window
from public.component.dialog.index.infrared_camera_read_SN_dialog_index import infrared_camera_read_SN_dialog
from public.config_class.global_setting import global_setting
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.MyQThread import MyQThread
from public.util.folder_util import folder_util
from public.util.shared_video_frames import shared_video_frame_store
from theme.ThemeQt6 import ThemedWindow


class ImageLoaderThread(MyQThread):
    image_loaded = pyqtSignal(dict)

    def __init__(self, display_mode: str = "infrared"):
        super().__init__(name="tab4_image_loader")
        self.display_mode = display_mode
        self.refresh_camera_paths()

    def set_display_mode(self, display_mode: str):
        self.display_mode = display_mode

    def refresh_camera_paths(self):
        camera_config = global_setting.get_setting("camera_config")
        self.infrared_camera_nums = int(camera_config["INFRARED_CAMERA"]["nums"])

        self.infrared_path = []
        if self.display_mode != "video":
            infrared_folder_list = folder_util.list_directories(
                camera_config["STORAGE"]["fold_path"] + camera_config["INFRARED_CAMERA"]["path"]
            )

            self.infrared_path = [
                camera_config["STORAGE"]["fold_path"]
                + camera_config["INFRARED_CAMERA"]["path"]
                + f"{folder_name}/"
                + camera_config["INFRARED_CAMERA"]["pic_dir"]
                for folder_name in infrared_folder_list
            ]
        self.images = {"deep_camera_frames": {}, "infrared_camera": []}
        self.running = True

    def _get_sleep_delay(self, configer) -> float:
        if self.display_mode == "video":
            return 0.03
        return float(configer["monitor_camera_pic"]["delay"])

    @staticmethod
    def parse_filename_datetime(filename):
        base = os.path.splitext(filename)[0]
        try:
            return datetime.strptime(base, "%Y_%m_%d_%H_%M_%S_%f")
        except ValueError:
            return None

    def filter_files_earlier_than(self, folder, delta_seconds=10):
        now = datetime.now()
        threshold = now - timedelta(seconds=delta_seconds)

        result_files = []
        for file_name in os.listdir(folder):
            dt = self.parse_filename_datetime(file_name)
            if dt and dt < threshold:
                result_files.append((dt, file_name))

        if not result_files:
            return None

        result_files.sort(key=lambda item: item[0])
        return result_files[-1][1]

    def dosomething(self):
        try:
            self.refresh_camera_paths()
            configer = global_setting.get_setting("configer")
            infrared_camera_list = []

            if self.display_mode != "video":
                for path in self.infrared_path:
                    if not os.path.exists(path):
                        os.makedirs(path)
                    file_name = self.filter_files_earlier_than(
                        folder=path,
                        delta_seconds=float(configer["monitor_camera_pic"]["data_delay"]),
                    )
                    infrared_camera_list.append("" if file_name is None else os.path.join(path, file_name))

            deep_camera_frames = {}
            target_cages = set(int(cage) for cage in (global_setting.get_setting("mouse_cages", []) or []))
            experiment_setting = global_setting.get_setting("experiment_setting", None)
            if experiment_setting is not None and getattr(experiment_setting, "groups", None):
                for group in experiment_setting.groups:
                    if getattr(group, "is_selected", 0) == 1:
                        target_cages.add(int(group.id))

            for cage_number in sorted(target_cages):
                frame_payload = shared_video_frame_store.read_frame("deep_camera", cage_number)
                if frame_payload is not None:
                    deep_camera_frames[cage_number] = frame_payload

            self.images["deep_camera_frames"] = deep_camera_frames
            self.images["infrared_camera"] = infrared_camera_list
            self.image_loaded.emit(self.images)
            time.sleep(self._get_sleep_delay(configer))
        except Exception as e:
            logger.error(f"tab4线程异常，原因: {e} | 堆栈: {traceback.format_exc()}")


class AutoFitGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_scene()

    def fit_scene(self):
        scene = self.scene()
        if scene is None:
            return

        rect = scene.sceneRect()
        if rect.isNull():
            rect = scene.itemsBoundingRect()
        if rect.isNull():
            return

        self.resetTransform()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(rect.center())


class DisplayPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(8)

        self.group_box = QGroupBox("", self)
        self.group_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        group_layout = QVBoxLayout(self.group_box)
        group_layout.setContentsMargins(10, 10, 10, 10)
        group_layout.setSpacing(8)

        self.title_label = QLabel("", self.group_box)
        group_layout.addWidget(self.title_label)

        self.content_widget = QWidget(self.group_box)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        self.graphics_view = AutoFitGraphicsView(self.content_widget)
        self.graphics_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_layout.addWidget(self.graphics_view)

        self.placeholder_label = QLabel("", self.content_widget)
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setWordWrap(True)
        self.placeholder_label.hide()
        self.content_layout.addWidget(self.placeholder_label)

        self.custom_widget = None

        group_layout.addWidget(self.content_widget, 1)
        layout.addWidget(self.group_box, 1)

    def set_title(self, text):
        self.title_label.setText(text)

    def _detach_custom_widget(self):
        if self.custom_widget is None:
            return

        widget = self.custom_widget
        widget.hide()
        self.content_layout.removeWidget(widget)
        widget.setParent(None)
        self.custom_widget = None

    def show_custom_widget(self, widget: QWidget):
        if widget is None:
            return

        self.custom_widget = widget
        if widget.parent() is not self.content_widget:
            widget.setParent(self.content_widget)
        if self.content_layout.indexOf(widget) == -1:
            self.content_layout.insertWidget(0, widget, 1)

        self.graphics_view.hide()
        self.placeholder_label.hide()
        widget.show()

    def show_image(self, image_path):
        scene = self.graphics_view.scene()
        if scene is None:
            scene = QGraphicsScene()
            self.graphics_view.setScene(scene)

        self._detach_custom_widget()
        scene.clear()
        self.placeholder_label.hide()
        self.graphics_view.show()

        if image_path:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scene.addPixmap(pixmap)
                scene.setSceneRect(QRectF(pixmap.rect()))
                self.graphics_view.fit_scene()
                return

        scene.setSceneRect(
            0,
            0,
            max(self.graphics_view.viewport().width(), 1),
            max(self.graphics_view.viewport().height(), 1),
        )
        self.placeholder_label.setText("暂无画面")
        self.placeholder_label.show()
        self.graphics_view.hide()

    def show_frame(self, frame):
        scene = self.graphics_view.scene()
        if scene is None:
            scene = QGraphicsScene()
            self.graphics_view.setScene(scene)

        self._detach_custom_widget()
        scene.clear()
        self.placeholder_label.hide()
        self.graphics_view.show()

        if frame is not None:
            if len(frame.shape) == 2:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            else:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width = rgb_frame.shape[:2]
            bytes_per_line = rgb_frame.strides[0]
            image = QImage(
                rgb_frame.data,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888,
            ).copy()
            pixmap = QPixmap.fromImage(image)
            if not pixmap.isNull():
                scene.addPixmap(pixmap)
                scene.setSceneRect(QRectF(pixmap.rect()))
                self.graphics_view.fit_scene()
                return

        self.show_placeholder("暂无画面")

    def show_placeholder(self, text):
        scene = self.graphics_view.scene()
        if scene is None:
            scene = QGraphicsScene()
            self.graphics_view.setScene(scene)
        self._detach_custom_widget()
        scene.clear()
        scene.setSceneRect(0, 0, 1, 1)
        self.graphics_view.hide()
        self.placeholder_label.setText(text)
        self.placeholder_label.show()


class TemperatureTrendWidget(QWidget):
    def __init__(self, parent=None, max_points: int = 120):
        super().__init__(parent)
        self.max_points = max_points
        self.handle: Monitor_Datas_Handle | None = None
        self.all_points: list[QPointF] = []
        self.view_start_index = 0
        self.current_cage_number: int | None = None
        self.auto_save_enabled = True
        self.last_auto_save_bucket_by_cage: dict[int, str] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.chart = QChart()
        self.chart.legend().hide()
        self.chart.setBackgroundRoundness(0)
        self.chart.setMargins(QMargins(8, 4, 8, 50))

        self.series = QScatterSeries()
        self.series.setName("红外最大温度")
        self.series.setMarkerShape(QScatterSeries.MarkerShape.MarkerShapeCircle)
        self.series.setMarkerSize(8.0)
        self.series.setColor(QColor("#ff6b35"))
        self.series.setBorderColor(QColor("#ff6b35"))
        self.series.setPen(QPen(QColor("#ff6b35"), 1))
        self.chart.addSeries(self.series)

        self.x_axis = QDateTimeAxis()
        self.x_axis.setFormat("HH:mm:ss")
        self.x_axis.setTitleText("时间")
        self.x_axis.setTickCount(6)

        self.y_axis = QValueAxis()
        self.y_axis.setLabelFormat("%.2f")
        self.y_axis.setTitleText("温度 (°C)")
        self.y_axis.setTickCount(6)

        self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)

        self.chart_view = QChartView(self.chart, self)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.chart_view.setContentsMargins(0, 0, 0, 0)
        self.chart_view.setViewportMargins(0, 0, 0, 12)
        self.chart_view.setMinimumHeight(260)

        self.slider_row = QWidget(self)
        slider_row_layout = QHBoxLayout(self.slider_row)
        slider_row_layout.setContentsMargins(0, 0, 0, 0)
        slider_row_layout.setSpacing(8)

        self.slider_label = QLabel("时间范围", self.slider_row)
        self.slider_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.time_slider = QSlider(Qt.Orientation.Horizontal, self.slider_row)
        self.time_slider.setObjectName("temperature_time_slider")
        self.time_slider.setRange(0, 0)
        self.time_slider.setSingleStep(1)
        self.time_slider.setPageStep(max(1, self.max_points // 2))
        self.time_slider.setMinimumHeight(22)
        self.time_slider.setStyleSheet(
            """
            QSlider#temperature_time_slider::groove:horizontal {
                border: 1px solid #c7c7c7;
                height: 8px;
                background: #ececec;
                border-radius: 4px;
            }
            QSlider#temperature_time_slider::sub-page:horizontal {
                background: #ffb08f;
                border-radius: 4px;
            }
            QSlider#temperature_time_slider::handle:horizontal {
                background: #ff6b35;
                border: 1px solid #d95b2c;
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider#temperature_time_slider::handle:horizontal:hover {
                background: #ff814f;
            }
            """
        )
        self.time_slider.valueChanged.connect(self._on_slider_changed)

        self.slider_status_label = QLabel("", self.slider_row)
        self.slider_status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        slider_row_layout.addWidget(self.slider_label)
        slider_row_layout.addWidget(self.time_slider, 1)
        slider_row_layout.addWidget(self.slider_status_label)
        self.slider_row.hide()

        self.placeholder_label = QLabel("暂无温度数据", self)
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.hide()

        layout.addWidget(self.chart_view, 1)
        layout.addWidget(self.slider_row)
        layout.addWidget(self.placeholder_label, 1)
        self.setLayout(layout)
        self.clear_chart()

    def stop(self):
        if self.handle is not None:
            self.handle.stop()
            self.handle = None

    def _ensure_handle(self):
        if self.handle is None:
            self.handle = Monitor_Datas_Handle()

    @staticmethod
    def _parse_time(value):
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(str(value), fmt)
            except ValueError:
                continue
        return None

    def clear_chart(self, text: str = "暂无温度数据"):
        self.series.clear()
        self.all_points = []
        self.view_start_index = 0
        self.current_cage_number = None
        self.chart.setTitle("")
        self.chart_view.hide()
        self.time_slider.setEnabled(False)
        self.slider_status_label.clear()
        self.slider_row.hide()
        self.placeholder_label.setText(text)
        self.placeholder_label.show()

    def _build_points(self, meta_data, rows):
        column_names = [item["name"] for item in meta_data]
        points = []
        for row in rows:
            row_data = dict(zip(column_names, row))
            time_value = self._parse_time(row_data.get("time"))
            temp_value = row_data.get("tmp_hs_max")
            if temp_value is None:
                temp_value = row_data.get("tmp_hs_mean")
            if time_value is None or temp_value is None:
                continue
            try:
                points.append(QPointF(time_value.timestamp() * 1000, float(temp_value)))
            except (TypeError, ValueError):
                continue

        points.sort(key=lambda point: point.x())
        return points

    def _configure_slider(self, keep_latest: bool):
        total_points = len(self.all_points)
        max_start = max(total_points - self.max_points, 0)
        start_index = max_start if keep_latest else min(self.view_start_index, max_start)

        self.time_slider.blockSignals(True)
        self.time_slider.setRange(0, max_start)
        self.time_slider.setPageStep(max(1, min(self.max_points, max_start if max_start > 0 else 1)))
        self.time_slider.setValue(start_index)
        self.time_slider.setEnabled(total_points > 0)
        self.time_slider.blockSignals(False)

        self.view_start_index = start_index
        self.slider_status_label.setText(
            f"{min(total_points, start_index + 1)}-{min(total_points, start_index + self.max_points)} / {total_points}"
        )
        if max_start > 0:
            self.time_slider.setToolTip("拖动这里查看完整温度趋势")
        else:
            self.time_slider.setToolTip("当前数据量还没有超过单屏展示范围")
        self.slider_status_label.setToolTip("当前显示区间 / 总数据点数")
        self.slider_row.setVisible(total_points > 0)

    def _update_axes(self, points):
        x_min = int(points[0].x())
        x_max = int(points[-1].x())
        if x_min == x_max:
            x_min -= 1000
            x_max += 1000
        self.x_axis.setRange(
            QDateTime.fromMSecsSinceEpoch(x_min),
            QDateTime.fromMSecsSinceEpoch(x_max),
        )

        y_values = [point.y() for point in points]
        y_min = min(y_values)
        y_max = max(y_values)
        padding = max((y_max - y_min) * 0.15, 0.5)
        if y_min == y_max:
            padding = max(padding, 1.0)
        self.y_axis.setRange(y_min - padding, y_max + padding)

    def _render_current_window(self):
        if not self.all_points:
            self.clear_chart("暂无温度数据")
            return

        end_index = self.view_start_index + self.max_points
        visible_points = self.all_points[self.view_start_index:end_index]
        if not visible_points:
            visible_points = self.all_points[-self.max_points:]
            self.view_start_index = max(len(self.all_points) - len(visible_points), 0)

        self.series.clear()
        for point in visible_points:
            self.series.append(point)

        self._update_axes(visible_points)
        if self.current_cage_number is not None:
            self.chart.setTitle(f"鼠笼{self.current_cage_number}红外最大温度趋势")
        self.placeholder_label.hide()
        self.chart_view.show()
        self.slider_row.show()

    def _get_auto_save_dir(self, cage_number: int) -> str:
        experiment_setting_file = global_setting.get_setting("experiment_setting_file", None)
        experiment_name = "experiment"
        if experiment_setting_file is not None and os.path.exists(experiment_setting_file):
            experiment_name = os.path.splitext(os.path.basename(experiment_setting_file))[0]

        storage_setting = global_setting.get_setting("monitor_data")["STORAGE"]
        experiment_start_time = global_setting.get_setting("start_experiment_time", time.time())
        experiment_folder = (
            f"{experiment_name}_{datetime.fromtimestamp(experiment_start_time).strftime('%Y_%m_%d_%H_%M_%S_%f')}"
        )
        save_dir = os.path.join(
            os.getcwd() + storage_setting["fold_path"],
            storage_setting["sub_fold_path"],
            experiment_folder,
            "temperature_charts",
            f"cage_{cage_number}",
        )
        os.makedirs(save_dir, exist_ok=True)
        return save_dir

    def _auto_save_chart(self):
        if not self.auto_save_enabled or self.current_cage_number is None or not self.all_points:
            return

        try:
            save_bucket = datetime.now().strftime("%Y_%m_%d_%H_%M")
            if self.last_auto_save_bucket_by_cage.get(self.current_cage_number) == save_bucket:
                return

            save_dir = self._get_auto_save_dir(self.current_cage_number)
            file_name = (
                f"temperature_trend_cage_{self.current_cage_number}_"
                f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S_%f')}.png"
            )
            file_path = os.path.join(save_dir, file_name)
            if self.chart_view.grab().save(file_path, "PNG"):
                self.last_auto_save_bucket_by_cage[self.current_cage_number] = save_bucket
        except Exception as e:
            logger.debug(f"auto save temperature chart failed for cage {self.current_cage_number}: {e}")

    def _on_slider_changed(self, value: int):
        self.view_start_index = value
        self._render_current_window()

    def refresh_data(self, cage_number: int | None):
        if cage_number is None:
            self.clear_chart("请选择已开启笼子")
            return

        keep_latest = (
            cage_number != self.current_cage_number
            or not self.all_points
            or self.time_slider.value() >= self.time_slider.maximum()
        )
        self.current_cage_number = cage_number

        table_name = f"MouseInfrared_data_cage_{cage_number}"
        try:
            self._ensure_handle()
            meta_data = self.handle.query_meta_table_data_all(table_name)
            rows = self.handle.query_data_all(table_name)
        except Exception as e:
            logger.debug(f"读取鼠笼{cage_number}红外温度趋势失败: {e}")
            self.clear_chart("暂无温度数据")
            return

        if not meta_data or not rows:
            self.clear_chart("暂无温度数据")
            return

        self.all_points = self._build_points(meta_data, rows)
        if not self.all_points:
            self.clear_chart("暂无温度数据")
            return

        self._configure_slider(keep_latest)
        self._render_current_window()
        self._auto_save_chart()


class TemperatureTrendWidgetV2(QWidget):
    def __init__(self, parent=None, max_points: int = 120):
        super().__init__(parent)
        self.max_points = max_points
        self.handle: Monitor_Datas_Handle | None = None
        self.all_points: list[QPointF] = []
        self.view_start_index = 0
        self.current_cage_number: int | None = None
        self.is_following_latest = True
        self.auto_save_enabled = True
        self.last_auto_save_bucket_by_cage: dict[int, str] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.chart = QChart()
        self.chart.legend().hide()
        self.chart.setBackgroundRoundness(0)
        self.chart.setMargins(QMargins(8, 4, 8, 50))

        self.series = QScatterSeries()
        self.series.setName("红外最大温度")
        self.series.setMarkerShape(QScatterSeries.MarkerShape.MarkerShapeCircle)
        self.series.setMarkerSize(8.0)
        self.series.setColor(QColor("#ff6b35"))
        self.series.setBorderColor(QColor("#ff6b35"))
        self.series.setPen(QPen(QColor("#ff6b35"), 1))
        self.chart.addSeries(self.series)

        self.x_axis = QDateTimeAxis()
        self.x_axis.setFormat("HH:mm:ss")
        self.x_axis.setTitleText("时间")
        self.x_axis.setTickCount(6)

        self.y_axis = QValueAxis()
        self.y_axis.setLabelFormat("%.2f")
        self.y_axis.setTitleText("温度 (°C)")
        self.y_axis.setTickCount(6)

        self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)

        self.chart_view = QChartView(self.chart, self)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.chart_view.setContentsMargins(0, 0, 0, 0)
        self.chart_view.setViewportMargins(0, 0, 0, 24)
        self.chart_view.setMinimumHeight(260)

        self.slider_row = QWidget(self)
        self.slider_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.slider_row.setMinimumHeight(34)
        slider_row_layout = QHBoxLayout(self.slider_row)
        slider_row_layout.setContentsMargins(0, 0, 0, 0)
        slider_row_layout.setSpacing(8)

        self.slider_label = QLabel("历史窗口", self.slider_row)
        self.slider_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.time_slider = QSlider(Qt.Orientation.Horizontal, self.slider_row)
        self.time_slider.setObjectName("temperature_time_slider")
        self.time_slider.setRange(0, 0)
        self.time_slider.setSingleStep(1)
        self.time_slider.setPageStep(max(1, self.max_points // 2))
        self.time_slider.setMinimumHeight(22)
        self.time_slider.setStyleSheet(
            """
            QSlider#temperature_time_slider::groove:horizontal {
                border: 1px solid #c7c7c7;
                height: 8px;
                background: #ececec;
                border-radius: 4px;
            }
            QSlider#temperature_time_slider::sub-page:horizontal {
                background: #ffb08f;
                border-radius: 4px;
            }
            QSlider#temperature_time_slider::add-page:horizontal {
                background: #ececec;
                border-radius: 4px;
            }
            QSlider#temperature_time_slider::handle:horizontal {
                background: #ff6b35;
                border: 1px solid #d95b2c;
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider#temperature_time_slider::handle:horizontal:hover {
                background: #ff814f;
            }
            """
        )
        self.time_slider.valueChanged.connect(self._on_slider_changed)

        self.slider_status_label = QLabel("", self.slider_row)
        self.slider_status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        slider_row_layout.addWidget(self.slider_label)
        slider_row_layout.addWidget(self.time_slider, 1)
        slider_row_layout.addWidget(self.slider_status_label)
        self.slider_row.hide()

        self.placeholder_label = QLabel("暂无温度数据", self)
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.hide()

        layout.addWidget(self.chart_view, 1)
        layout.addWidget(self.slider_row)
        layout.addWidget(self.placeholder_label, 1)
        self.setLayout(layout)
        self.clear_chart()

    def stop(self):
        if self.handle is not None:
            self.handle.stop()
            self.handle = None

    def _ensure_handle(self):
        if self.handle is None:
            self.handle = Monitor_Datas_Handle()

    @staticmethod
    def _parse_time(value):
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(str(value), fmt)
            except ValueError:
                continue
        return None

    def clear_chart(self, text: str = "暂无温度数据"):
        self.series.clear()
        self.all_points = []
        self.view_start_index = 0
        self.current_cage_number = None
        self.is_following_latest = True
        self.chart.setTitle("")
        self.chart_view.hide()
        self.time_slider.blockSignals(True)
        self.time_slider.setRange(0, 0)
        self.time_slider.setValue(0)
        self.time_slider.blockSignals(False)
        self.time_slider.setEnabled(False)
        self.slider_status_label.clear()
        self.slider_row.hide()
        self.placeholder_label.setText(text)
        self.placeholder_label.show()

    def _build_points(self, meta_data, rows):
        column_names = [item["name"] for item in meta_data]
        points = []
        for row in rows:
            row_data = dict(zip(column_names, row))
            time_value = self._parse_time(row_data.get("time"))
            temp_value = row_data.get("tmp_hs_max")
            if temp_value is None:
                temp_value = row_data.get("tmp_hs_mean")
            if time_value is None or temp_value is None:
                continue
            try:
                points.append(QPointF(time_value.timestamp() * 1000, float(temp_value)))
            except (TypeError, ValueError):
                continue

        points.sort(key=lambda point: point.x())
        return points

    def _current_window_bounds(self):
        total_points = len(self.all_points)
        if total_points == 0:
            return 0, 0

        if total_points <= self.max_points:
            return 0, total_points

        start_index = min(max(self.view_start_index, 0), total_points - self.max_points)
        end_index = start_index + self.max_points
        return start_index, end_index

    def _update_slider_status(self):
        total_points = len(self.all_points)
        if total_points == 0:
            self.slider_status_label.clear()
            return

        start_index, end_index = self._current_window_bounds()
        self.slider_status_label.setText(f"{start_index + 1}-{end_index} / {total_points}")

    def _configure_slider(self, keep_latest: bool):
        total_points = len(self.all_points)
        has_history = total_points > self.max_points
        max_start = max(total_points - self.max_points, 0)

        if not has_history:
            self.view_start_index = 0
            self.is_following_latest = True
        elif keep_latest:
            self.view_start_index = max_start
            self.is_following_latest = True
        else:
            self.view_start_index = min(self.view_start_index, max_start)
            self.is_following_latest = self.view_start_index >= max_start

        self.time_slider.blockSignals(True)
        self.time_slider.setRange(0, max_start)
        self.time_slider.setPageStep(max(1, self.max_points // 2))
        self.time_slider.setValue(self.view_start_index)
        self.time_slider.blockSignals(False)

        self.time_slider.setEnabled(has_history)
        self.time_slider.setToolTip("拖动这里查看更早的温度数据" if has_history else "当前数据量未超过 120 个点")
        self.slider_status_label.setToolTip("当前显示区间 / 总数据点数")
        self._update_slider_status()
        self.slider_row.setVisible(has_history)

    def _update_axes(self, points):
        x_min = int(points[0].x())
        x_max = int(points[-1].x())
        if x_min == x_max:
            x_min -= 1000
            x_max += 1000
        self.x_axis.setRange(
            QDateTime.fromMSecsSinceEpoch(x_min),
            QDateTime.fromMSecsSinceEpoch(x_max),
        )

        y_values = [point.y() for point in points]
        y_min = min(y_values)
        y_max = max(y_values)
        padding = max((y_max - y_min) * 0.15, 0.5)
        if y_min == y_max:
            padding = max(padding, 1.0)
        self.y_axis.setRange(y_min - padding, y_max + padding)

    def _render_current_window(self):
        if not self.all_points:
            self.clear_chart("暂无温度数据")
            return

        start_index, end_index = self._current_window_bounds()
        visible_points = self.all_points[start_index:end_index]
        if not visible_points:
            self.clear_chart("暂无温度数据")
            return

        self.view_start_index = start_index
        self.series.clear()
        for point in visible_points:
            self.series.append(point)

        self._update_axes(visible_points)
        self._update_slider_status()
        if self.current_cage_number is not None:
            self.chart.setTitle(f"鼠笼{self.current_cage_number}红外最大温度趋势")
        self.placeholder_label.hide()
        self.chart_view.show()
        self.slider_row.setVisible(len(self.all_points) > self.max_points)

    def _get_auto_save_dir(self, cage_number: int) -> str:
        experiment_setting_file = global_setting.get_setting("experiment_setting_file", None)
        experiment_name = "experiment"
        if experiment_setting_file is not None and os.path.exists(experiment_setting_file):
            experiment_name = os.path.splitext(os.path.basename(experiment_setting_file))[0]

        storage_setting = global_setting.get_setting("monitor_data")["STORAGE"]
        experiment_start_time = global_setting.get_setting("start_experiment_time", time.time())
        experiment_folder = (
            f"{experiment_name}_{datetime.fromtimestamp(experiment_start_time).strftime('%Y_%m_%d_%H_%M_%S_%f')}"
        )
        save_dir = os.path.join(
            os.getcwd() + storage_setting["fold_path"],
            storage_setting["sub_fold_path"],
            experiment_folder,
            "temperature_charts",
            f"cage_{cage_number}",
        )
        os.makedirs(save_dir, exist_ok=True)
        return save_dir

    def _auto_save_chart(self):
        if not self.auto_save_enabled or self.current_cage_number is None or not self.all_points:
            return

        try:
            save_bucket = datetime.now().strftime("%Y_%m_%d_%H_%M")
            if self.last_auto_save_bucket_by_cage.get(self.current_cage_number) == save_bucket:
                return

            save_dir = self._get_auto_save_dir(self.current_cage_number)
            file_name = (
                f"temperature_trend_cage_{self.current_cage_number}_"
                f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S_%f')}.png"
            )
            file_path = os.path.join(save_dir, file_name)
            if self.chart_view.grab().save(file_path, "PNG"):
                self.last_auto_save_bucket_by_cage[self.current_cage_number] = save_bucket
        except Exception as e:
            logger.debug(f"auto save temperature chart failed for cage {self.current_cage_number}: {e}")

    def _on_slider_changed(self, value: int):
        self.view_start_index = value
        self.is_following_latest = value >= self.time_slider.maximum()
        self._render_current_window()

    def refresh_data(self, cage_number: int | None):
        if cage_number is None:
            self.clear_chart("请选择已开启笼子")
            return

        keep_latest = cage_number != self.current_cage_number or self.is_following_latest or not self.all_points
        self.current_cage_number = cage_number

        table_name = f"MouseInfrared_data_cage_{cage_number}"
        try:
            self._ensure_handle()
            meta_data = self.handle.query_meta_table_data_all(table_name)
            rows = self.handle.query_data_all(table_name)
        except Exception as e:
            logger.debug(f"读取鼠笼{cage_number}红外温度趋势失败: {e}")
            self.clear_chart("暂无温度数据")
            return

        if not meta_data or not rows:
            self.clear_chart("暂无温度数据")
            return

        self.all_points = self._build_points(meta_data, rows)
        if not self.all_points:
            self.clear_chart("暂无温度数据")
            return

        self._configure_slider(keep_latest)
        self._render_current_window()
        self._auto_save_chart()


TemperatureTrendWidget = TemperatureTrendWidgetV2


class Tab_4(ThemedWindow):
    MODE_INFRARED = "infrared"
    MODE_VIDEO = "video"

    def __init__(self, parent=None, geometry: QRect = None, title="", display_mode: str = MODE_INFRARED):
        super().__init__()
        self.charts_list = []
        self.loader_thread: ImageLoaderThread | None = None
        self.trajectory_thread: MouseTrajectoryThread | None = None
        self.infrared_camera_read_SN_dialog_frame = None
        self.current_cage_number: int | None = None
        self.current_mode = display_mode if display_mode in {self.MODE_INFRARED, self.MODE_VIDEO} else self.MODE_INFRARED
        self.latest_image_paths = {"infrared_camera": {}}
        self.latest_video_frames: dict[int, dict[str, typing.Any]] = {}
        self.latest_trajectory_plot_paths: dict[int, dict[str, str]] = {}
        self.latest_trajectory_annotation_frames: dict[int, typing.Any] = {}
        self.latest_trajectory_status: dict[int, str] = {}
        self.current_trajectory_plot_key = "xy_trajectory"
        self.temperature_widget: TemperatureTrendWidget | None = None
        self.last_enabled_cages: list[int] = []

        self._init_ui(parent, geometry, title)
        self._init_customize_ui()
        self._init_function()
        self._init_style_sheet()

    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        logger.warning("tab4-show")
        self.start_loader_thread()
        self.refresh_cage_selector()
        self.render_selected_content()
        super().showEvent(a0)

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.warning("tab4-hide")
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.pause()
        super().hideEvent(a0)

    def closeEvent(self, a0: typing.Optional[QtGui.QCloseEvent]) -> None:
        logger.warning("tab4-close")
        self.pause_loader_thread()
        self.stop_trajectory_thread()
        if self.temperature_widget is not None:
            self.temperature_widget.stop()
        super().closeEvent(a0)

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        if parent is not None and geometry is not None:
            self.setParent(parent)
            self.setGeometry(geometry)

        self.ui = Ui_tab4_window()
        self.ui.setupUi(self)

    def _init_customize_ui(self):
        self.init_auto_connect_ui()
        self.init_header_selectors()
        self.init_display_area()

    def init_auto_connect_ui(self):
        start_btn: QPushButton = self.findChild(QPushButton, "start_btn")
        stop_btn: QPushButton = self.findChild(QPushButton, "stop_btn")
        state_label: QLabel = self.findChild(QLabel, "state_label")
        for widget in (state_label, start_btn, stop_btn):
            if widget is not None:
                widget.hide()
        self.update_mode_specific_controls()

    def update_mode_specific_controls(self):
        infrared_camera_setting_btn: QPushButton = self.findChild(QPushButton, "infrared_camera_setting")
        if infrared_camera_setting_btn is None:
            return

        infrared_camera_setting_btn.setVisible(self.current_mode == self.MODE_INFRARED)
        if hasattr(self, "trajectory_plot_selector_label"):
            is_video_mode = self.current_mode == self.MODE_VIDEO
            self.trajectory_plot_selector_label.setVisible(is_video_mode)
            self.trajectory_plot_selector.setVisible(is_video_mode)

    def init_header_selectors(self):
        self.cage_selector_label = QLabel("已开启笼子:", self.ui.verticalLayoutWidget)
        self.cage_selector = QComboBox(self.ui.verticalLayoutWidget)
        self.cage_selector.setObjectName("enabled_cage_selector")
        self.cage_selector.setMinimumWidth(140)
        self.cage_selector.currentIndexChanged.connect(self.on_cage_changed)

        self.current_cage_label = QLabel("当前显示: 未选择", self.ui.verticalLayoutWidget)

        insert_index = max(self.ui.horizontalLayout.count() - 1, 0)
        self.ui.horizontalLayout.insertWidget(insert_index, self.cage_selector_label)
        self.ui.horizontalLayout.insertWidget(insert_index + 1, self.cage_selector)
        self.trajectory_plot_selector_label = QLabel("轨迹图", self.ui.verticalLayoutWidget)
        self.trajectory_plot_selector = QComboBox(self.ui.verticalLayoutWidget)
        self.trajectory_plot_selector.setObjectName("trajectory_plot_selector")
        self.trajectory_plot_selector.setMinimumWidth(150)
        self.trajectory_plot_selector.addItem("X-Y轨迹", "xy_trajectory")
        self.trajectory_plot_selector.addItem("高度轨迹", "height_trajectory")
        self.trajectory_plot_selector.addItem("停留热力图", "occupancy_heatmap")
        self.trajectory_plot_selector.currentIndexChanged.connect(self.on_trajectory_plot_changed)

        self.ui.horizontalLayout.insertWidget(insert_index + 2, self.current_cage_label)
        self.ui.horizontalLayout.insertWidget(insert_index + 3, self.trajectory_plot_selector_label)
        self.ui.horizontalLayout.insertWidget(insert_index + 4, self.trajectory_plot_selector)
        self.update_mode_specific_controls()

    def init_display_area(self):
        if hasattr(self.ui, "scrollArea"):
            self.ui.verticalLayout.removeWidget(self.ui.scrollArea)
            self.ui.scrollArea.setParent(None)

        self.monitor_content_widget = QWidget(self.ui.verticalLayoutWidget)
        self.monitor_content_widget.setObjectName("single_cage_monitor_content")
        self.monitor_content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        content_layout = QHBoxLayout(self.monitor_content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.left_panel = DisplayPanel(self.monitor_content_widget)
        self.right_panel = DisplayPanel(self.monitor_content_widget)
        self.temperature_widget = TemperatureTrendWidget()
        self.temperature_widget.hide()

        content_layout.addWidget(self.left_panel, 1)
        content_layout.addWidget(self.right_panel, 1)
        self.ui.verticalLayout.addWidget(self.monitor_content_widget, 1)

        self.refresh_cage_selector()
        self.render_selected_content()

    def start_loader_thread(self):
        self.refresh_cage_selector()
        self.start_trajectory_thread()
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.set_display_mode(self.current_mode)
            if self.loader_thread.isPaused():
                self.loader_thread.resume()
            return

        self.loader_thread = ImageLoaderThread(display_mode=self.current_mode)
        self.loader_thread.image_loaded.connect(self.update_image)
        self.loader_thread.start()

    def stop_loader_thread(self):
        if self.loader_thread is None:
            return

        if self.loader_thread.isRunning():
            self.loader_thread.stop()
            self.loader_thread.requestInterruption()
            self.loader_thread.wait(2000)

        self.loader_thread = None

    def start_trajectory_thread(self):
        if self.trajectory_thread is not None and self.trajectory_thread.isRunning():
            if self.trajectory_thread.isPaused():
                self.trajectory_thread.resume()
            return

        self.trajectory_thread = MouseTrajectoryThread()
        self.trajectory_thread.trajectory_ready.connect(self.update_trajectory_result)
        self.trajectory_thread.start()

    def stop_trajectory_thread(self):
        if self.trajectory_thread is None:
            return

        if self.trajectory_thread.isRunning():
            self.trajectory_thread.stop()
            self.trajectory_thread.requestInterruption()
            self.trajectory_thread.wait(2000)

        self.trajectory_thread = None

    def pause_loader_thread(self):
        if self.loader_thread is None:
            return

        if self.loader_thread.isRunning() and not self.loader_thread.isPaused():
            self.loader_thread.pause()

    def update_trajectory_result(self, result_dict):
        if not result_dict:
            return

        cage_number = int(result_dict.get("cage_number", 0) or 0)
        if cage_number <= 0:
            return

        self.latest_trajectory_plot_paths[cage_number] = result_dict.get("plot_paths", {}) or {}
        self.latest_trajectory_annotation_frames[cage_number] = result_dict.get("annotation_frame")
        self.latest_trajectory_status[cage_number] = result_dict.get("status", "")

        if self.current_mode == self.MODE_VIDEO and self.current_cage_number == cage_number:
            self.render_selected_content()

    def _build_cage_image_map(self, image_paths, prefix):
        cage_image_map = {}
        for image_path in image_paths:
            cage_number = self._extract_cage_number(image_path, prefix)
            if cage_number is not None:
                cage_image_map[cage_number] = image_path
        return cage_image_map

    @staticmethod
    def _extract_cage_number(image_path, prefix):
        if not image_path:
            return None

        match = re.search(rf"{re.escape(prefix)}(\d+)", image_path)
        if match is None:
            return None

        try:
            return int(match.group(1))
        except ValueError:
            return None

    def get_enabled_cages(self):
        mouse_cages = global_setting.get_setting("mouse_cages", None)
        if mouse_cages:
            return sorted({int(cage) for cage in mouse_cages})

        experiment_setting = global_setting.get_setting("experiment_setting", None)
        if experiment_setting is not None and getattr(experiment_setting, "groups", None):
            enabled_cages = [
                int(group.id)
                for group in experiment_setting.groups
                if getattr(group, "is_selected", 0) == 1
            ]
            if enabled_cages:
                return sorted(set(enabled_cages))

        available_cages = set(self.latest_video_frames.keys())
        available_cages.update(self.latest_image_paths["infrared_camera"].keys())
        return sorted(available_cages)

    def _get_selector_cages(self) -> list[int]:
        cages: list[int] = []
        for index in range(self.cage_selector.count()):
            cage_number = self.cage_selector.itemData(index)
            if cage_number is None:
                continue
            cages.append(int(cage_number))
        return cages

    def refresh_cage_selector(self):
        enabled_cages = self.get_enabled_cages()
        previous_cage = self.current_cage_number

        if not enabled_cages:
            self.current_cage_number = None
            self.last_enabled_cages = []
            self.cage_selector.blockSignals(True)
            self.cage_selector.clear()
            self.cage_selector.blockSignals(False)
            self.cage_selector.setEnabled(False)
            self.current_cage_label.setText("当前显示: 未选择")
            return

        if self.cage_selector.view().isVisible():
            return

        current_selector_cages = self._get_selector_cages()
        if current_selector_cages != enabled_cages:
            self.cage_selector.blockSignals(True)
            self.cage_selector.clear()
            for cage_number in enabled_cages:
                self.cage_selector.addItem(f"鼠笼{cage_number}", cage_number)
            self.cage_selector.blockSignals(False)
            self.last_enabled_cages = list(enabled_cages)

        self.cage_selector.setEnabled(True)
        target_cage = previous_cage if previous_cage in enabled_cages else enabled_cages[0]
        index = self.cage_selector.findData(target_cage)
        if index >= 0 and index != self.cage_selector.currentIndex():
            self.cage_selector.setCurrentIndex(index)
        self.current_cage_number = target_cage

    def on_cage_changed(self, index):
        if index < 0:
            return

        self.current_cage_number = self.cage_selector.itemData(index)
        self.render_selected_content()

    def on_trajectory_plot_changed(self, index):
        if index < 0:
            return

        self.current_trajectory_plot_key = self.trajectory_plot_selector.itemData(index) or "xy_trajectory"
        self.render_selected_content()

    def set_display_mode(self, mode: str):
        if mode not in {self.MODE_INFRARED, self.MODE_VIDEO}:
            return

        self.current_mode = mode
        if self.loader_thread is not None:
            self.loader_thread.set_display_mode(mode)
        self.update_mode_specific_controls()
        self.render_selected_content()

    def update_image(self, pixmap_path_dict):
        if pixmap_path_dict is None or "infrared_camera" not in pixmap_path_dict:
            logger.error("未获取到图片数据")
            return

        self.latest_video_frames = dict(pixmap_path_dict.get("deep_camera_frames", {}) or {})
        self.latest_image_paths = {
            "infrared_camera": self._build_cage_image_map(
                pixmap_path_dict["infrared_camera"],
                global_setting.get_setting("camera_config")["INFRARED_CAMERA"]["mouse_cage_prefix"],
            ),
        }

        if self.trajectory_thread is not None:
            self.trajectory_thread.submit_frames(self.latest_video_frames)

        self.refresh_cage_selector()
        self.render_selected_content()

    def render_selected_content(self):
        if self.current_cage_number is None:
            self.left_panel.set_title("左侧")
            self.right_panel.set_title("右侧")
            self.left_panel.show_placeholder("请选择已开启笼子")
            self.right_panel.show_placeholder("请选择已开启笼子")
            return

        cage_number = self.current_cage_number
        self.current_cage_label.setText(f"当前显示: 鼠笼{cage_number}")

        if self.current_mode == self.MODE_VIDEO:
            self.left_panel.set_title(f"视频图像 - 鼠笼{cage_number}")
            self.left_panel.show_image(self.latest_image_paths["deep_camera"].get(cage_number, ""))
            self.right_panel.set_title(f"轨迹 - 鼠笼{cage_number}")
            self.right_panel.show_placeholder("轨迹功能待接入")
            return

        self.left_panel.set_title(f"红外相机 - 鼠笼{cage_number}")
        self.left_panel.show_image(self.latest_image_paths["infrared_camera"].get(cage_number, ""))
        self.right_panel.set_title(f"温度 - 鼠笼{cage_number}")
        if self.temperature_widget is not None:
            self.temperature_widget.refresh_data(cage_number)
            self.right_panel.show_custom_widget(self.temperature_widget)
        else:
            self.right_panel.show_placeholder("温度功能待接入")

    def render_selected_content(self):
        if self.current_cage_number is None:
            self.left_panel.set_title("左侧")
            self.right_panel.set_title("右侧")
            self.left_panel.show_placeholder("请选择已开启笼子")
            self.right_panel.show_placeholder("请选择已开启笼子")
            return

        cage_number = self.current_cage_number
        self.current_cage_label.setText(f"当前显示: 鼠笼{cage_number}")

        if self.current_mode == self.MODE_VIDEO:
            self.left_panel.set_title(f"视频图像 - 鼠笼{cage_number}")
            self.left_panel.show_image(self.latest_image_paths["deep_camera"].get(cage_number, ""))
            self.right_panel.set_title(f"轨迹 - 鼠笼{cage_number}")
            trajectory_plot_path = self.latest_trajectory_plot_paths.get(cage_number, "")
            if trajectory_plot_path:
                self.right_panel.show_image(trajectory_plot_path)
            else:
                self.right_panel.show_placeholder("暂无轨迹数据")
            return

        self.left_panel.set_title(f"红外相机 - 鼠笼{cage_number}")
        self.left_panel.show_image(self.latest_image_paths["infrared_camera"].get(cage_number, ""))
        self.right_panel.set_title(f"温度 - 鼠笼{cage_number}")
        if self.temperature_widget is not None:
            self.temperature_widget.refresh_data(cage_number)
            self.right_panel.show_custom_widget(self.temperature_widget)
        else:
            self.right_panel.show_placeholder("暂无温度数据")

    def render_selected_content(self):
        if self.current_cage_number is None:
            self.left_panel.set_title("左侧")
            self.right_panel.set_title("右侧")
            self.left_panel.show_placeholder("请选择已开启笼子")
            self.right_panel.show_placeholder("请选择已开启笼子")
            return

        cage_number = self.current_cage_number
        self.current_cage_label.setText(f"当前显示: 鼠笼{cage_number}")

        if self.current_mode == self.MODE_VIDEO:
            self.left_panel.set_title(f"视频检测效果 - 鼠笼{cage_number}")
            annotation_frame = self.latest_trajectory_annotation_frames.get(cage_number)
            if annotation_frame is not None:
                self.left_panel.show_frame(annotation_frame)
            else:
                frame_payload = self.latest_video_frames.get(cage_number)
                self.left_panel.show_frame(None if frame_payload is None else frame_payload.get("frame"))

            plot_paths = self.latest_trajectory_plot_paths.get(cage_number, {})
            selected_plot_path = plot_paths.get(self.current_trajectory_plot_key, "")
            plot_label = self.trajectory_plot_selector.currentText() if hasattr(self, "trajectory_plot_selector") else "X-Y轨迹"
            self.right_panel.set_title(f"{plot_label} - 鼠笼{cage_number}")
            if selected_plot_path:
                self.right_panel.show_image(selected_plot_path)
            else:
                self.right_panel.show_placeholder("暂无轨迹数据")
            return

        self.left_panel.set_title(f"红外相机 - 鼠笼{cage_number}")
        self.left_panel.show_image(self.latest_image_paths["infrared_camera"].get(cage_number, ""))
        self.right_panel.set_title(f"温度 - 鼠笼{cage_number}")
        if self.temperature_widget is not None:
            self.temperature_widget.refresh_data(cage_number)
            self.right_panel.show_custom_widget(self.temperature_widget)
        else:
            self.right_panel.show_placeholder("暂无温度数据")

    def _init_function(self):
        self.init_btn_handle()

    def init_btn_handle(self):
        start_btn = self.findChild(QPushButton, "start_btn")
        stop_btn = self.findChild(QPushButton, "stop_btn")
        state_label: QLabel = self.findChild(QLabel, "state_label")
        infrared_camera_setting_btn = self.findChild(QPushButton, "infrared_camera_setting")

        start_btn.clicked.connect(lambda: self.start_btn_func(start_btn, stop_btn, state_label))
        stop_btn.clicked.connect(lambda: self.stop_btn_func(start_btn, stop_btn, state_label))
        infrared_camera_setting_btn.clicked.connect(
            lambda: self.infrared_camera_setting_btn_func(infrared_camera_setting_btn)
        )

    def start_btn_func(self, start_btn: QPushButton, stop_btn: QPushButton, state_label: QLabel):
        self.start_loader_thread()
        state_label.setText("已连接")
        stop_btn.setDisabled(False)
        start_btn.setDisabled(True)

    def stop_btn_func(self, start_btn: QPushButton, stop_btn: QPushButton, state_label: QLabel):
        self.pause_loader_thread()
        state_label.setText("未连接")
        stop_btn.setDisabled(True)
        start_btn.setDisabled(False)

    def infrared_camera_setting_btn_func(self, config_btn):
        self.infrared_camera_read_SN_dialog_frame = infrared_camera_read_SN_dialog(title="红外相机获取SN码")
        self.infrared_camera_read_SN_dialog_frame.show_frame()
