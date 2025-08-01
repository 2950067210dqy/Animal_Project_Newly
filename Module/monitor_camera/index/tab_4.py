import os
import time
import traceback
import typing
from datetime import datetime, timedelta

from PyQt6.QtGui import QPixmap
from loguru import logger



from Module.monitor_camera.ui.tab4_window import Ui_tab4_window

from public.component.dialog.index.deep_camera_config_dialog_index import deep_camera_config_dialog
from public.component.dialog.index.infrared_camera_config_dialog_index import infrared_camera_config_dialog
from public.component.dialog.index.infrared_camera_read_SN_dialog_index import infrared_camera_read_SN_dialog
from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from theme.ThemeQt6 import ThemedWindow
from PyQt6 import QtGui
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QPushButton, \
    QLabel

from util.folder_util import folder_util


class ImageLoaderThread(MyQThread):
    """
    连续获取早几秒钟的文件路径
    """
    image_loaded = pyqtSignal(dict)



    def __init__(self):
        super().__init__(name="tab4_image_loader")
        # 相机数量
        self.infrared_camera_nums = int(global_setting.get_setting("camera_config")['INFRARED_CAMERA']['nums'])
        self.deep_camera_nums = int(global_setting.get_setting("camera_config")['DEEP_CAMERA']['nums'])
        # 每个相机的图片路径
        infrared_folder_list = folder_util.list_directories(
            global_setting.get_setting("camera_config")['STORAGE']['fold_path'] + \
            global_setting.get_setting("camera_config")['INFRARED_CAMERA'][
                'path'])
        deep_folder_list = folder_util.list_directories(
            global_setting.get_setting("camera_config")['STORAGE']['fold_path'] + \
            global_setting.get_setting("camera_config")['DEEP_CAMERA'][
                'path'])
        self.infrared_path = [global_setting.get_setting("camera_config")['STORAGE']['fold_path'] + \
                              global_setting.get_setting("camera_config")['INFRARED_CAMERA'][
                                  'path'] + f"{i}/" +
                              global_setting.get_setting("camera_config")['INFRARED_CAMERA']['pic_dir']
                              for i in infrared_folder_list
                              ]
        self.deep_path = [global_setting.get_setting("camera_config")['STORAGE']['fold_path'] + \
                          global_setting.get_setting("camera_config")['DEEP_CAMERA'][
                              'path'] + f"{i}/" +
                          global_setting.get_setting("camera_config")['DEEP_CAMERA']['result_dir'] +
                          global_setting.get_setting("camera_config")['DEEP_CAMERA']['result_img_dir']
                          for i in deep_folder_list
                          ]
        self.images = {"deep_camera": [], "infrared_camera": []}
        self.running = True

    def parse_filename_datetime(self, filename):
        """
        从文件名中解析日期时间，假设格式为 '2025_05_22_14_30_45_123456.ext'
        """
        base = os.path.splitext(filename)[0]  # 去掉后缀
        try:
            dt = datetime.strptime(base, "%Y_%m_%d_%H_%M_%S_%f")
            return dt
        except ValueError:
            # 文件名格式不匹配，返回None
            return None

    def filter_files_earlier_than(self, folder, delta_seconds=10):
        """
        寻找文件夹内比现在时间早几秒的文件
        :param folder:
        :param delta_seconds:
        :return:
        """
        now = datetime.now()
        threshold = now - timedelta(seconds=delta_seconds)

        result_files = []
        for fn in os.listdir(folder):
            dt = self.parse_filename_datetime(fn)
            if dt and dt < threshold:
                result_files.append(fn)
        if len(result_files) == 0:
            return None
        else:
            return result_files[len(result_files) - 1]

    def dosomething(self):

        try:
            deep_camera_list = []
            infrared_camera_list = []
            for path in self.deep_path:
                if not os.path.exists(path):
                    os.makedirs(path)
                file_name_path = self.filter_files_earlier_than(folder=path, delta_seconds=float(
                    global_setting.get_setting("configer")['tab4_pic']['data_delay']))
                if file_name_path is None:
                    deep_camera_list.append("")
                else:
                    deep_camera_list.append(path + file_name_path)
                pass
            for path in self.infrared_path:
                if not os.path.exists(path):
                    os.makedirs(path)
                file_name_path = self.filter_files_earlier_than(folder=path, delta_seconds=float(
                    global_setting.get_setting("configer")['monitor_camera_pic']['data_delay']))
                if file_name_path is None:
                    infrared_camera_list.append("")
                else:
                    infrared_camera_list.append(path + "/" + file_name_path)
                pass
            self.images["deep_camera"] = deep_camera_list
            self.images["infrared_camera"] = infrared_camera_list
            self.image_loaded.emit(self.images)
            time.sleep(float(global_setting.get_setting("configer")['monitor_camera_pic']['delay']))
        except Exception as e:
            logger.error(f"tab4线程异常，原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")

    def stop(self):
        self.running = False
        self.wait()


class Tab_4(ThemedWindow):
    def showEvent(self, a0: typing.Optional[QtGui.QShowEvent]) -> None:
        # 加载qss样式表
        logger.warning("tab4——show")
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.resume()

    def hideEvent(self, a0: typing.Optional[QtGui.QHideEvent]) -> None:
        logger.warning("tab4--hide")
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.pause()

    def __init__(self, parent=None, geometry: QRect = None, title=""):
        super().__init__()
        # 图像列表
        self.charts_list = []
        # 对话框
        self.deep_camera_config_dialog_frame=None
        self.infrared_camera_config_dialog_frame=None
        self.infrared_camera_read_SN_dialog_frame=None
        # 实例化ui
        self._init_ui(parent, geometry, title)
        # 实例化自定义ui
        self._init_customize_ui()
        # 获取数据
        self.get_data()
        # 实例化功能
        self._init_function()
        # 加载qss样式表
        self._init_style_sheet()

        pass

        # 实例化ui

    def get_data(self):
        """
        获取数据
        :return:
        """
        self.loader_thread = ImageLoaderThread()
        self.loader_thread.image_loaded.connect(self.update_image)
        self.loader_thread.start()

    def _init_ui(self, parent=None, geometry: QRect = None, title=""):
        # 将ui文件转成py文件后 直接实例化该py文件里的类对象  uic工具转换之后就是这一段代码
        # 有父窗口添加父窗口
        if parent != None and geometry != None:
            self.setParent(parent)
            self.setGeometry(geometry)
        else:
            pass
        self.ui = Ui_tab4_window()
        self.ui.setupUi(self)

        self._retranslateUi()
        pass

        pass

    # 实例化自定义ui
    def _init_customize_ui(self):
        self.init_btn_label()

        self.init_graphy()

        pass

    def init_btn_label(self):
        """
        初始化按钮和label的初始信息
        :return:
        """
        start_btn: QPushButton = self.findChild(QPushButton, "start_btn")
        stop_btn: QPushButton = self.findChild(QPushButton, "stop_btn")
        state_label: QLabel = self.findChild(QLabel, "state_label")
        start_btn.setDisabled(False)
        stop_btn.setDisabled(True)
        state_label.setText("未连接")

        pass

    def update_image(self, pixmap_path_dict):
        if pixmap_path_dict is None or "deep_camera" not in pixmap_path_dict or "infrared_camera" not in pixmap_path_dict:
            logger.error("未获取到数据")
            return
        for i in range(len(pixmap_path_dict['deep_camera'])):
            # logger.critical(f"deep_camera | {pixmap_path_dict['deep_camera'][i]}")
            position = pixmap_path_dict['deep_camera'][i].find(
                global_setting.get_setting('camera_config')['DEEP_CAMERA']['mouse_cage_prefix']) + len(
                global_setting.get_setting('camera_config')['DEEP_CAMERA']['mouse_cage_prefix'])
            if pixmap_path_dict['deep_camera'][i] == "":
                pixmap = QPixmap()
            else:
                # 按比例缩放到目标宽高内
                pixmap = QPixmap(pixmap_path_dict['deep_camera'][i]).scaled(200, 200,
                                                                            Qt.AspectRatioMode.KeepAspectRatio)
            for graphics_view in self.graphics_view_left:

                if position < len(pixmap_path_dict['deep_camera'][i]) and graphics_view.objectName() != "" and \
                        graphics_view.objectName()[-1] == \
                        pixmap_path_dict['deep_camera'][i][position]:
                    if graphics_view.scene() is None:
                        # 无就创建
                        scene = QGraphicsScene()
                        pixmap_item = QGraphicsPixmapItem(pixmap)
                        scene.addItem(pixmap_item)

                        # 设置场景给视图
                        graphics_view.setScene(scene)
                    else:
                        # 有就更新
                        graphics_view.scene().clear()
                        graphics_view.scene().addPixmap(pixmap)

            else:
                pass

        for i in range(len(pixmap_path_dict['infrared_camera'])):
            # logger.critical(f"infrared_camera | {pixmap_path_dict['infrared_camera'][i]}")
            position = pixmap_path_dict['infrared_camera'][i].find(
                global_setting.get_setting('camera_config')['INFRARED_CAMERA']['mouse_cage_prefix']) + len(
                global_setting.get_setting('camera_config')['INFRARED_CAMERA']['mouse_cage_prefix'])
            if pixmap_path_dict['infrared_camera'][i] == "":
                pixmap = QPixmap()
            else:
                # 按比例缩放到目标宽高内
                pixmap = QPixmap(pixmap_path_dict['infrared_camera'][i]).scaled(200, 200,
                                                                                Qt.AspectRatioMode.KeepAspectRatio)
            for graphics_view in self.graphics_view_right:

                if position < len(pixmap_path_dict['infrared_camera'][i]) and graphics_view.objectName() != "" and \
                        graphics_view.objectName()[-1] == \
                        pixmap_path_dict['infrared_camera'][i][position]:
                    if graphics_view.scene() is None:
                        # 无就创建
                        scene = QGraphicsScene()
                        pixmap_item = QGraphicsPixmapItem(pixmap)
                        scene.addItem(pixmap_item)

                        # 设置场景给视图
                        graphics_view.setScene(scene)
                    else:
                        # 有就更新
                        graphics_view.scene().clear()
                        graphics_view.scene().addPixmap(pixmap)
                        pass

            else:
                pass
        pass

    def closeEvent(self, event):
        self.loader_thread.stop()
        super().closeEvent(event)

    def init_graphy(self):
        """
        实例化图片组件
        :return:
        """
        self.parent_layout = self.findChild(QHBoxLayout, "tab4_layout")
        self.graphics_view_list = self.findChildren(QGraphicsView)
        self.graphics_view_left = []
        self.graphics_view_right = []
        for i in range(len(self.graphics_view_list)):
            # logger.info(self.graphics_view_list[i].objectName())
            if "left" in self.graphics_view_list[i].objectName():
                # logger.error(f"left{i}")

                self.graphics_view_left.append(self.graphics_view_list[i])
                # 自动缩放视图，使图片完全显示，保持宽高比
                # self.graphics_view_list[i].fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
                pass
            elif "right" in self.graphics_view_list[i].objectName():
                # logger.error(f"right{i}")

                self.graphics_view_right.append(self.graphics_view_list[i])
                # 自动缩放视图，使图片完全显示，保持宽高比
                # self.graphics_view_list[i].fitInView(pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
                pass
            else:
                pass
            self.graphics_view_list[i].setDragMode(QGraphicsView.DragMode.ScrollHandDrag)  # 开启拖拽模式

    # 实例化功能
    def _init_function(self):
        self.init_btn_handle()
        pass

    def init_btn_handle(self):
        """
        将按钮绑定功能函数
        """
        # 找到两个按钮 和状态显示label
        start_btn = self.findChild(QPushButton, "start_btn")
        stop_btn = self.findChild(QPushButton, "stop_btn")
        state_label: QLabel = self.findChild(QLabel, "state_label")

        deep_camera_config_btn = self.findChild(QPushButton, "deep_camera_config")
        infrared_camera_config_btn = self.findChild(QPushButton, "infrared_camera_config")
        infrared_camera_setting_btn = self.findChild(QPushButton, "infrared_camera_setting")
        # 绑定功能
        start_btn.clicked.connect(lambda: self.start_btn_func(start_btn, stop_btn, state_label))
        stop_btn.clicked.connect(lambda: self.stop_btn_func(start_btn, stop_btn, state_label))
        deep_camera_config_btn.clicked.connect(lambda: self.deep_camera_config_btn_func(deep_camera_config_btn))
        infrared_camera_config_btn.clicked.connect(lambda: self.infrared_camera_config_btn_func(infrared_camera_config_btn))
        infrared_camera_setting_btn.clicked.connect(lambda: self.infrared_camera_setting_btn_func(infrared_camera_setting_btn))
        pass

    def start_btn_func(self, start_btn: QPushButton, stop_btn: QPushButton, state_label: QLabel):
        """
        开始按钮的函数
        :return:
        """

        state_label.setText("已连接")
        stop_btn.setDisabled(False)
        start_btn.setDisabled(True)

        pass

    def stop_btn_func(self, start_btn: QPushButton, stop_btn: QPushButton, state_label: QLabel):
        """
        停止按钮的函数
        :return:
        """
        state_label.setText("未连接")
        stop_btn.setDisabled(True)
        start_btn.setDisabled(False)
        pass

    def deep_camera_config_btn_func(self, config_btn):
        """
        config按钮函数 打开dialog
        :param config_btn:
        :return:
        """
        self.deep_camera_config_dialog_frame = deep_camera_config_dialog(title="深度相机配置",tip="\n设置好后要重新启动程序！！！！！！")
        # self.deep_camera_config_dialog_frame.camera_config_finished_signal.connect(init_camera_and_image_handle_thread)
        self.deep_camera_config_dialog_frame.show_frame()

        pass
    def infrared_camera_config_btn_func(self, config_btn):
        """
        config按钮函数 打开dialog
        :param config_btn:
        :return:
        """
        self.infrared_camera_config_dialog_frame = infrared_camera_config_dialog(title="红外相机配置",tip="\n设置好后要重新启动程序！！！！！！")
        # self.infrared_camera_config_dialog_frame.camera_config_finished_signal.connect(init_camera_and_image_handle_thread)
        self.infrared_camera_config_dialog_frame.show_frame()

        pass
    def infrared_camera_setting_btn_func(self, config_btn):
        """
        config按钮函数 打开dialog
        :param config_btn:
        :return:
        """
        self.infrared_camera_read_SN_dialog_frame = infrared_camera_read_SN_dialog(title="红外相机获取SN码")

        self.infrared_camera_read_SN_dialog_frame.show_frame()

        pass