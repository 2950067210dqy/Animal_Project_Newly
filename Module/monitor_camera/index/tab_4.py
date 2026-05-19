import os
import re
import time
import traceback
import typing
from datetime import datetime, timedelta

from PyQt6 import QtGui
from PyQt6.QtCharts import QChart, QChartView, QDateTimeAxis, QSplineSeries, QValueAxis
from PyQt6.QtCore import QDateTime, QPointF, QRect, QRectF, Qt, pyqtSignal, QMargins
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

from Module.monitor_camera.ui.tab4_window import Ui_tab4_window
from public.component.dialog.index.infrared_camera_read_SN_dialog_index import infrared_camera_read_SN_dialog
from public.config_class.global_setting import global_setting
from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle
from public.entity.MyQThread import MyQThread
from public.util.folder_util import folder_util
from theme.ThemeQt6 import ThemedWindow


class ImageLoaderThread(MyQThread):
    image_loaded = pyqtSignal(dict)

    def __init__(self):
        super().__init__(name="tab4_image_loader")
        self.refresh_camera_paths()

    def refresh_camera_paths(self):
        camera_config = global_setting.get_setting("camera_config")
        self.infrared_camera_nums = int(camera_config["INFRARED_CAMERA"]["nums"])
        self.deep_camera_nums = int(camera_config["DEEP_CAMERA"]["nums"])

        infrared_folder_list = folder_util.list_directories(
            camera_config["STORAGE"]["fold_path"] + camera_config["INFRARED_CAMERA"]["path"]
        )
        deep_folder_list = folder_util.list_directories(
            camera_config["STORAGE"]["fold_path"] + camera_config["DEEP_CAMERA"]["path"]
        )

        self.infrared_path = [
            camera_config["STORAGE"]["fold_path"]
            + camera_config["INFRARED_CAMERA"]["path"]
            + f"{folder_name}/"
            + camera_config["INFRARED_CAMERA"]["pic_dir"]
            for folder_name in infrared_folder_list
        ]
        self.deep_path = [
            camera_config["STORAGE"]["fold_path"]
            + camera_config["DEEP_CAMERA"]["path"]
            + f"{folder_name}/"
            + camera_config["DEEP_CAMERA"]["result_dir"]
            + camera_config["DEEP_CAMERA"]["result_img_dir"]
            for folder_name in deep_folder_list
        ]
        self.images = {"deep_camera": [], "infrared_camera": []}
        self.running = True

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
            deep_camera_list = []
            infrared_camera_list = []

            for path in self.deep_path:
                if not os.path.exists(path):
                    os.makedirs(path)
                file_name = self.filter_files_earlier_than(
                    folder=path,
                    delta_seconds=float(configer["monitor_camera_pic"]["data_delay"]),
                )
                deep_camera_list.append("" if file_name is None else os.path.join(path, file_name))

            for path in self.infrared_path:
                if not os.path.exists(path):
                    os.makedirs(path)
                file_name = self.filter_files_earlier_than(
                    folder=path,
                    delta_seconds=float(configer["monitor_camera_pic"]["data_delay"]),
                )
                infrared_camera_list.append("" if file_name is None else os.path.join(path, file_name))

            self.images["deep_camera"] = deep_camera_list
            self.images["infrared_camera"] = infrared_camera_list
            self.image_loaded.emit(self.images)
            time.sleep(float(configer["monitor_camera_pic"]["delay"]))
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

        if self.custom_widget is not None:
            self.custom_widget.hide()
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

    def show_placeholder(self, text):
        scene = self.graphics_view.scene()
        if scene is None:
            scene = QGraphicsScene()
            self.graphics_view.setScene(scene)
        if self.custom_widget is not None:
            self.custom_widget.hide()
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
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.chart = QChart()
        self.chart.legend().hide()
        self.chart.setBackgroundRoundness(0)
        # 给底部横轴刻度和标题预留更明确的显示空间
        self.chart.setMargins(QMargins(8, 4, 8, 50))

        self.series = QSplineSeries()
        self.series.setName("红外均值温度")
        self.series.setPen(QPen(QColor("#ff6b35"), 2))
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

        self.placeholder_label = QLabel("暂无温度数据", self)
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.hide()

        layout.addWidget(self.chart_view, 1)
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
        self.chart.setTitle("")
        self.chart_view.hide()
        self.placeholder_label.setText(text)
        self.placeholder_label.show()

    def refresh_data(self, cage_number: int | None):
        if cage_number is None:
            self.clear_chart("请选择已开启笼子")
            return

        table_name = f"MouseInfrared_data_cage_{cage_number}"
        try:
            self._ensure_handle()
            meta_data = self.handle.query_meta_table_data_all(table_name)
            rows = self.handle.query_data_paging(table_name, self.max_points, 0)
        except Exception as e:
            logger.debug(f"读取鼠笼{cage_number}红外温度趋势失败: {e}")
            self.clear_chart("暂无温度数据")
            return

        if not meta_data or not rows:
            self.clear_chart("暂无温度数据")
            return

        column_names = [item["name"] for item in meta_data]
        points = []
        for row in reversed(rows):
            row_data = dict(zip(column_names, row))
            time_value = self._parse_time(row_data.get("time"))
            temp_value = row_data.get("tmp_hs_mean")
            if time_value is None or temp_value is None:
                continue
            try:
                points.append(QPointF(time_value.timestamp() * 1000, float(temp_value)))
            except (TypeError, ValueError):
                continue

        if not points:
            self.clear_chart("暂无温度数据")
            return

        self.series.clear()
        for point in points:
            self.series.append(point)

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

        self.chart.setTitle(f"鼠笼{cage_number}红外均值温度趋势")
        self.placeholder_label.hide()
        self.chart_view.show()


class Tab_4(ThemedWindow):
    MODE_INFRARED = "infrared"
    MODE_VIDEO = "video"

    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        self.charts_list = []
        self.loader_thread: ImageLoaderThread | None = None
        self.infrared_camera_read_SN_dialog_frame = None
        self.current_cage_number: int | None = None
        self.current_mode = self.MODE_INFRARED
        self.latest_image_paths = {"deep_camera": {}, "infrared_camera": {}}
        self.temperature_widget: TemperatureTrendWidget | None = None

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

    def init_header_selectors(self):
        self.mode_selector_label = QLabel("显示部分:", self.ui.verticalLayoutWidget)
        self.mode_selector = QComboBox(self.ui.verticalLayoutWidget)
        self.mode_selector.setObjectName("display_mode_selector")
        self.mode_selector.addItem("红外部分", self.MODE_INFRARED)
        self.mode_selector.addItem("视频部分", self.MODE_VIDEO)
        self.mode_selector.setMinimumWidth(120)
        self.mode_selector.currentIndexChanged.connect(self.on_mode_changed)

        self.cage_selector_label = QLabel("已开启笼子:", self.ui.verticalLayoutWidget)
        self.cage_selector = QComboBox(self.ui.verticalLayoutWidget)
        self.cage_selector.setObjectName("enabled_cage_selector")
        self.cage_selector.setMinimumWidth(140)
        self.cage_selector.currentIndexChanged.connect(self.on_cage_changed)

        self.current_cage_label = QLabel("当前显示: 未选择", self.ui.verticalLayoutWidget)

        insert_index = max(self.ui.horizontalLayout.count() - 1, 0)
        self.ui.horizontalLayout.insertWidget(insert_index, self.mode_selector_label)
        self.ui.horizontalLayout.insertWidget(insert_index + 1, self.mode_selector)
        self.ui.horizontalLayout.insertWidget(insert_index + 2, self.cage_selector_label)
        self.ui.horizontalLayout.insertWidget(insert_index + 3, self.cage_selector)
        self.ui.horizontalLayout.insertWidget(insert_index + 4, self.current_cage_label)

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
        self.temperature_widget = TemperatureTrendWidget(self.right_panel.content_widget)

        content_layout.addWidget(self.left_panel, 1)
        content_layout.addWidget(self.right_panel, 1)
        self.ui.verticalLayout.addWidget(self.monitor_content_widget, 1)

        self.refresh_cage_selector()
        self.render_selected_content()

    def start_loader_thread(self):
        self.refresh_cage_selector()
        if self.loader_thread is not None and self.loader_thread.isRunning():
            if self.loader_thread.isPaused():
                self.loader_thread.resume()
            return

        self.loader_thread = ImageLoaderThread()
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

    def pause_loader_thread(self):
        if self.loader_thread is None:
            return

        if self.loader_thread.isRunning() and not self.loader_thread.isPaused():
            self.loader_thread.pause()

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

        available_cages = set(self.latest_image_paths["deep_camera"].keys())
        available_cages.update(self.latest_image_paths["infrared_camera"].keys())
        return sorted(available_cages)

    def refresh_cage_selector(self):
        enabled_cages = self.get_enabled_cages()
        previous_cage = self.current_cage_number

        self.cage_selector.blockSignals(True)
        self.cage_selector.clear()
        for cage_number in enabled_cages:
            self.cage_selector.addItem(f"鼠笼{cage_number}", cage_number)
        self.cage_selector.blockSignals(False)

        if not enabled_cages:
            self.current_cage_number = None
            self.cage_selector.setEnabled(False)
            self.current_cage_label.setText("当前显示: 未选择")
            return

        self.cage_selector.setEnabled(True)
        target_cage = previous_cage if previous_cage in enabled_cages else enabled_cages[0]
        index = self.cage_selector.findData(target_cage)
        if index >= 0:
            self.cage_selector.setCurrentIndex(index)
        self.current_cage_number = target_cage

    def on_cage_changed(self, index):
        if index < 0:
            return

        self.current_cage_number = self.cage_selector.itemData(index)
        self.render_selected_content()

    def on_mode_changed(self, index):
        if index < 0:
            return

        self.current_mode = self.mode_selector.itemData(index)
        self.render_selected_content()

    def update_image(self, pixmap_path_dict):
        if pixmap_path_dict is None or "deep_camera" not in pixmap_path_dict or "infrared_camera" not in pixmap_path_dict:
            logger.error("未获取到图片数据")
            return

        self.latest_image_paths = {
            "deep_camera": self._build_cage_image_map(
                pixmap_path_dict["deep_camera"],
                global_setting.get_setting("camera_config")["DEEP_CAMERA"]["mouse_cage_prefix"],
            ),
            "infrared_camera": self._build_cage_image_map(
                pixmap_path_dict["infrared_camera"],
                global_setting.get_setting("camera_config")["INFRARED_CAMERA"]["mouse_cage_prefix"],
            ),
        }

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
            self.left_panel.set_title(f"三维 - 鼠笼{cage_number}")
            self.left_panel.show_image(self.latest_image_paths["deep_camera"].get(cage_number, ""))
            self.right_panel.set_title(f"轨迹 - 鼠笼{cage_number}")
            self.right_panel.show_placeholder("轨迹功能待接入")
            return

        self.left_panel.set_title(f"红外 - 鼠笼{cage_number}")
        self.left_panel.show_image(self.latest_image_paths["infrared_camera"].get(cage_number, ""))
        self.right_panel.set_title(f"温度 - 鼠笼{cage_number}")
        if self.temperature_widget is not None:
            self.temperature_widget.refresh_data(cage_number)
            self.right_panel.show_custom_widget(self.temperature_widget)
        else:
            self.right_panel.show_placeholder("温度功能待接入")

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
