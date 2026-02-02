import os
import time
import typing
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, QRect
from PyQt6.QtWidgets import (
    QPushButton, QLabel, QMessageBox
)
from loguru import logger

from Module.mouse_trajectory.ui.main_window import Ui_Main_window
from public.component.dialog.index.trajectory_deep_camera_config_dialog_index import \
    trajectory_deep_camera_config_dialog
from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from theme.ThemeQt6 import ThemedWindow


class CoordinateLoaderThread(MyQThread):
    """
    从数据库读取鼠标坐标数据的线程
    支持首次完整加载和增量更新
    """
    # 定义信号
    coordinate_loaded = pyqtSignal(dict)
    new_coordinates = pyqtSignal(int, dict)
    loading_started = pyqtSignal()
    first_load_completed = pyqtSignal(dict)

    def __init__(self, data_handler, enabled_cage_ids, delay_seconds=0):
        super().__init__(name="CoordinateLoader")
        self.data_handler = data_handler
        self.enabled_cage_ids = enabled_cage_ids
        self.delay_seconds = delay_seconds
        self.last_data_length = {}
        self.last_read_time = {}
        self.cage_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="cage_reader")
        self.lock = Lock()
        self.should_start_loading = False
        self.first_load_done = {}

    def set_start_loading(self, should_start: bool):
        """控制数据加载的开始/停止"""
        self.should_start_loading = should_start
        if should_start:
            logger.info("数据加载已启用")
            self.first_load_done.clear()
            self.last_data_length.clear()
            self.last_read_time.clear()
        else:
            logger.info("数据加载已禁用")

    def load_cage_coordinates(self, cage_id: int, last_read_time: typing.Optional[str] = None) -> list:
        """加载指定笼子的坐标数据"""
        try:
            if last_read_time:
                coordinates = self.data_handler.get_trajectory_data_by_cage_after_time(cage_id, last_read_time)
            else:
                coordinates = self.data_handler.get_trajectory_data_by_cage(cage_id)

            return coordinates if coordinates else []
        except Exception as e:
            logger.error(f"加载笼子 {cage_id} 坐标数据失败: {e}")
            return []

    def process_single_cage(self, cage_id: int, all_coordinates: dict):
        """处理单个笼子的数据"""
        if not self._running or not self.should_start_loading:
            return

        try:
            with self.lock:
                last_time = self.last_read_time.get(cage_id, None)
                is_first_load = cage_id not in self.first_load_done

            if is_first_load:
                logger.info(f"[笼子 {cage_id}] 首次加载开始")
                coordinates = self.load_cage_coordinates(cage_id, last_read_time=None)

                if coordinates and len(coordinates) > 0:
                    all_coordinates[cage_id] = coordinates

                    with self.lock:
                        self.first_load_done[cage_id] = True
                        self.last_data_length[cage_id] = len(coordinates)
                        self.last_read_time[cage_id] = coordinates[-1].get('time', '')

                    logger.info(f"[笼子 {cage_id}] 首次加载完成: {len(coordinates)} 个数据点")
                    self.first_load_completed.emit({cage_id: coordinates})
                else:
                    logger.warning(f"[笼子 {cage_id}] 首次加载无数据")
                    with self.lock:
                        self.first_load_done[cage_id] = True

            else:
                coordinates = self.load_cage_coordinates(cage_id, last_read_time=last_time)

                if coordinates and len(coordinates) > 0:
                    new_count = len(coordinates)
                    self.new_coordinates.emit(cage_id, {cage_id: coordinates})

                    with self.lock:
                        self.last_data_length[cage_id] += new_count
                        self.last_read_time[cage_id] = coordinates[-1].get('time', '')

        except Exception as e:
            logger.error(f"[笼子 {cage_id}] 处理失败: {e}", exc_info=True)

    def dosomething(self):
        """主循环"""
        if not self._running:
            return

        if not self.should_start_loading:
            time.sleep(0.1)
            return

        try:
            all_coordinates = {}
            futures = {}

            for cage_id in self.enabled_cage_ids:
                if not self._running:
                    break
                future = self.cage_executor.submit(self.process_single_cage, cage_id, all_coordinates)
                futures[future] = cage_id

            for future in as_completed(futures.keys(), timeout=120):
                if not self._running:
                    break
                cage_id = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"[笼子 {cage_id}] 处理异常: {e}")

            if all_coordinates:
                self.coordinate_loaded.emit(all_coordinates)

            try:
                refresh_interval = float(
                    global_setting.get_setting("configer")['monitor_camera_pic']['delay']
                )
            except:
                refresh_interval = 2.0

            time.sleep(refresh_interval)

        except Exception as e:
            logger.error(f"坐标加载循环异常: {e}")
            time.sleep(1)

    def __del__(self):
        """清理线程池"""
        try:
            self.cage_executor.shutdown(wait=False)
            logger.info("线程池已关闭")
        except:
            pass
        super().__del__()


class Trajectory(ThemedWindow):
    """轨迹显示窗口 - 根据笼子ID读取对应摄像机数据"""

    def showEvent(self, event):
        """窗口显示事件"""
        if not self._ui_initialized:
            self._initialize_ui()
        super().showEvent(event)

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.info("Trajectory窗口隐藏")
        if self.coordinate_loader_thread is not None and self.coordinate_loader_thread.isStart():
            self.coordinate_loader_thread.pause()
        super().hideEvent(a0)

    def closeEvent(self, a0: typing.Optional[QtGui.QCloseEvent]) -> None:
        logger.info("Trajectory窗口关闭")

        if self.coordinate_loader_thread is not None and self.coordinate_loader_thread.isStart():
            self.coordinate_loader_thread.stop()
            self.coordinate_loader_thread.wait()

        super().closeEvent(a0)

    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()

        self.enabled_cage_ids = []
        self.experiment_setting = None

        self.coordinate_loader_thread = None
        self.data_handler = None

        self.trajectory_deep_camera_config_dialog_frame = None
        self.cage_pause_status = {}
        self.cage_has_data = {}
        self.system_running = False

        self.cage_all_data = {}

        self.ui = None
        self._ui_initialized = False

        self._init_parent = parent
        self._init_geometry = geometry
        self._init_title = title

    def _get_enabled_cage_ids(self):
        """获取用户开启的笼子ID列表"""
        self.enabled_cage_ids = []

        self.experiment_setting = global_setting.get_setting("experiment_setting", None)

        if self.experiment_setting is None:
            logger.warning("experiment_setting 未初始化，使用默认配置")
            return []

        if hasattr(self.experiment_setting, 'groups') and self.experiment_setting.groups:
            enabled_groups = [g for g in self.experiment_setting.groups if g.is_selected == 1]
            self.enabled_cage_ids = sorted([g.id for g in enabled_groups])
            logger.info(f"成功获取开启的笼子列表: {self.enabled_cage_ids}")
            return self.enabled_cage_ids
        else:
            logger.warning("experiment_setting 中没有找到已启用的分组")
            return []

    def _init_data_handler(self):
        """初始化数据处理器"""
        try:
            from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle

            db_path = r"C:/WorkSpace/Animal_Project_Newly/data/monitor_data/2_2026_01_04_21_33_06_690/data/data.db"

            logger.info(f"尝试连接数据库: {db_path}")

            if not os.path.exists(db_path):
                logger.error(f"数据库文件不存在: {db_path}")

                base_path = r"C:/WorkSpace/Animal_Project_Newly/data/monitor_data/"
                if os.path.exists(base_path):
                    logger.info(f"查找 {base_path} 下的数据库文件...")
                    for root, dirs, files in os.walk(base_path):
                        for file in files:
                            if file == "data.db":
                                found_db = os.path.join(root, file)
                                logger.info(f"找到数据库文件: {found_db}")
                                db_path = found_db
                                break

            logger.info("创建 Monitor_Datas_Handle 实例...")
            self.data_handler = Monitor_Datas_Handle(db_name=db_path)

            if self.data_handler is None:
                logger.error("Monitor_Datas_Handle 初始化返回 None")
                return False

            logger.info("初始化坐标加载线程...")
            self.coordinate_loader_thread = CoordinateLoaderThread(
                self.data_handler,
                enabled_cage_ids=self.enabled_cage_ids
            )

            self.coordinate_loader_thread.first_load_completed.connect(self.on_first_load_completed)
            self.coordinate_loader_thread.new_coordinates.connect(self.update_new_coordinates)

            logger.info(f"数据处理器初始化完成，数据库路径: {db_path}")
            return True

        except Exception as e:
            logger.error(f"初始化数据处理失败: {e}", exc_info=True)
            self.data_handler = None
            return False

    def on_first_load_completed(self, cage_data):
        """首次数据加载完成的处理"""
        try:
            logger.info("首次数据加载完成")

            for cage_id, coordinates in cage_data.items():
                if cage_id not in self.enabled_cage_ids:
                    continue

                self.cage_has_data[cage_id] = True
                self.cage_all_data[cage_id] = coordinates

                logger.info(f"笼子 {cage_id} 加载了 {len(coordinates)} 条数据")

            if hasattr(self, 'ui') and hasattr(self.ui, 'state_label'):
                self.ui.state_label.setText("运行中")
                self.ui.state_label.setStyleSheet("color: green; font-weight: bold;")

            self.system_running = True
            logger.info("系统运行状态已更新")

        except Exception as e:
            logger.error(f"处理首次数据加载完成失败: {e}", exc_info=True)

    def update_new_coordinates(self, cage_id: int, new_coordinates_dict: dict):
        """增量更新坐标数据"""
        if cage_id not in new_coordinates_dict:
            return

        try:
            new_data = new_coordinates_dict[cage_id]

            if not new_data or len(new_data) == 0:
                return

            if cage_id not in self.cage_all_data:
                self.cage_all_data[cage_id] = []

            self.cage_all_data[cage_id].extend(new_data)

            logger.debug(f"笼子 {cage_id} 新增 {len(new_data)} 条数据，总计 {len(self.cage_all_data[cage_id])} 条")

        except Exception as e:
            logger.error(f"增量更新笼子 {cage_id} 坐标数据失败: {e}")

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        """初始化UI"""
        if parent is not None and geometry is not None:
            self.setParent(parent)
            self.setGeometry(geometry)

        self._get_enabled_cage_ids()

        if not self.enabled_cage_ids:
            logger.warning("没有找到开启的笼子，使用默认配置")
            self.enabled_cage_ids = list(range(1, 17))

        logger.info(f"UI初始化：将创建 {len(self.enabled_cage_ids)} 个笼子的界面")

        self.ui = Ui_Main_window()
        self.ui.setupUi(self, enabled_cage_ids=self.enabled_cage_ids)

    def _init_customize_ui(self):
        """初始化自定义UI"""
        self.init_btn_label()

        for cage_id in self.enabled_cage_ids:
            self.cage_pause_status[cage_id] = False
            self.cage_has_data[cage_id] = False
            self.cage_all_data[cage_id] = []

    def init_btn_label(self):
        """初始化按钮和label"""
        start_btn: QPushButton = self.findChild(QPushButton, "start_btn")
        stop_btn: QPushButton = self.findChild(QPushButton, "stop_btn")
        pause_resume_btn: QPushButton = self.findChild(QPushButton, "pause_resume_btn")
        state_label: QLabel = self.findChild(QLabel, "state_label")

        if start_btn:
            start_btn.setDisabled(False)
        if stop_btn:
            stop_btn.setDisabled(True)
        if pause_resume_btn:
            pause_resume_btn.setDisabled(True)
            pause_resume_btn.setText("全部暂停")
        if state_label:
            state_label.setText("未连接")

    def _init_function(self):
        """实例化功能"""
        self.init_btn_handle()

    def init_btn_handle(self):
        """将按钮绑定功能函数"""
        start_btn = self.findChild(QPushButton, "start_btn")
        stop_btn = self.findChild(QPushButton, "stop_btn")
        pause_resume_btn = self.findChild(QPushButton, "pause_resume_btn")
        state_label: QLabel = self.findChild(QLabel, "state_label")
        deep_camera_config_btn = self.findChild(QPushButton, "deep_camera_config")

        if start_btn:
            start_btn.clicked.connect(lambda: self.start_btn_func(start_btn, stop_btn, pause_resume_btn, state_label))
        if stop_btn:
            stop_btn.clicked.connect(lambda: self.stop_btn_func(start_btn, stop_btn, pause_resume_btn, state_label))
        if pause_resume_btn:
            pause_resume_btn.clicked.connect(lambda: self.pause_resume_all_btn_func(pause_resume_btn, state_label))
        if deep_camera_config_btn:
            deep_camera_config_btn.clicked.connect(lambda: self.deep_camera_config_btn_func())

    def start_btn_func(self, start_btn: QPushButton, stop_btn: QPushButton,
                       pause_resume_btn: QPushButton, state_label: QLabel):
        """开始按钮的函数"""
        try:
            logger.info("启动系统...")

            if self.data_handler is None:
                logger.info("数据处理器未初始化，尝试初始化...")
                if not self._init_data_handler():
                    logger.error("数据处理器初始化失败")
                    QMessageBox.critical(self, "错误", "数据库连接失败！\n\n请检查数据库文件和路径。")
                    return

            state_label.setText("连接成功")
            state_label.setStyleSheet("color: green; font-weight: bold;")
            stop_btn.setDisabled(False)
            start_btn.setDisabled(True)
            pause_resume_btn.setDisabled(False)
            pause_resume_btn.setText("全部暂停")
            self.system_running = True

            for cage_id in self.enabled_cage_ids:
                self.cage_pause_status[cage_id] = False
                self.cage_all_data[cage_id] = []

            if not self.coordinate_loader_thread.isStart():
                logger.info("启动坐标加载线程...")
                self.coordinate_loader_thread.start()

            logger.info("启用数据加载...")
            self.coordinate_loader_thread.set_start_loading(True)

            logger.info("系统启动完成，开始加载数据...")

        except Exception as e:
            logger.error(f"启动系统失败: {e}", exc_info=True)
            QMessageBox.critical(self, "错误", f"启动系统失败: {str(e)}")

    def stop_btn_func(self, start_btn: QPushButton, stop_btn: QPushButton,
                      pause_resume_btn: QPushButton, state_label: QLabel):
        """停止按钮的函数"""
        try:
            reply = QMessageBox.question(
                self, "确认",
                "确定要停止连接吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                logger.info("停止系统")

                if self.coordinate_loader_thread is not None:
                    self.coordinate_loader_thread.set_start_loading(False)

                state_label.setText("未连接")
                state_label.setStyleSheet("color: red; font-weight: bold;")
                stop_btn.setDisabled(True)
                start_btn.setDisabled(False)
                pause_resume_btn.setDisabled(True)
                pause_resume_btn.setText("全部暂停")
                self.system_running = False

                for cage_id in self.enabled_cage_ids:
                    self.cage_pause_status[cage_id] = False
                    self.cage_has_data[cage_id] = False
                    self.cage_all_data[cage_id] = []

                logger.info("系统已停止")
        except Exception as e:
            logger.error(f"停止系统失败: {e}")

    def pause_resume_all_btn_func(self, pause_resume_btn: QPushButton, state_label: QLabel):
        """全部暂停/继续按钮"""
        try:
            if not self.system_running:
                QMessageBox.warning(self, "警告", "系统未启动，请先开始连接")
                return

            is_paused = pause_resume_btn.text() == "全部继续"

            if is_paused:
                for cage_id in self.enabled_cage_ids:
                    self.cage_pause_status[cage_id] = False

                pause_resume_btn.setText("全部暂停")
                state_label.setText("已连接")
                state_label.setStyleSheet("color: green; font-weight: bold;")
                logger.info("所有笼子已继续")
            else:
                for cage_id in self.enabled_cage_ids:
                    self.cage_pause_status[cage_id] = True

                pause_resume_btn.setText("全部继续")
                state_label.setText("已暂停")
                state_label.setStyleSheet("color: orange; font-weight: bold;")
                logger.info("所有笼子已暂停")
        except Exception as e:
            logger.error(f"暂停/继续所有笼子失败: {e}")

    def deep_camera_config_btn_func(self):
        """深度相机配置按钮函数"""
        try:
            self.trajectory_deep_camera_config_dialog_frame = trajectory_deep_camera_config_dialog(
                title="深度相机配置",
                tip="\n设置好后要重新启动程序！！！！！！"
            )
            self.trajectory_deep_camera_config_dialog_frame.show_frame()
            logger.info("打开深度相机配置对话框")
        except Exception as e:
            logger.error(f"打开深度相机配置对话框失败: {e}")
            QMessageBox.critical(self, "错误", f"打开配置对话框失败: {e}")

    def _init_style_sheet(self):
        """初始化样式表"""
        pass

    def _initialize_ui(self):
        """执行UI初始化"""
        if self._ui_initialized:
            return

        self._init_ui(self._init_parent, self._init_geometry, self._init_title)
        self._init_customize_ui()
        self._init_function()
        self._init_style_sheet()

        self._ui_initialized = True