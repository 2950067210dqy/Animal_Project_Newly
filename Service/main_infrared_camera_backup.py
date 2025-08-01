# 加载日志配置
import csv
import multiprocessing
import threading
import traceback
from pathlib import Path
from threading import Thread

import numpy as np
from loguru import logger
import cv2 as cv

from public.component.dialog.index.infrared_camera_config_dialog_index import infrared_camera_config_dialog
from public.config_class.global_setting import global_setting
from public.config_class.ini_parser import ini_parser
from public.entity.MyQThread import MyQThread


from util.folder_util import folder_util
from util.json_util import json_util
from util.time_util import time_util
import argparse
import time
import os

from equipment.infrared_camera.senxor.utils import connect_senxor, data_to_frame, remap, \
    cv_filter, cv_render, \
    RollingAverageFilter, Display
from equipment.infrared_camera.senxor.utils import CVSegment
from imutils.video import VideoStream

# 删除线程
delete_file_thread = None
camera_list = []
# 被其他红外相机已经使用的串口
is_used_ports = []
np.set_printoptions(precision=1)

# global constants
# 删除线程和图像处理线程锁 保证同步
delete_process_lock = threading.Lock()
TIP_SEGM_PARAM = {
    # threshold-based segmentation
    # ----------------------------
    # supported: simple, otsu, adaptive
    'threshold_type': 'simple',
    # threshold value for simple thresholding
    'threshold': 190,
    'contour_minArea': -5,

    # contour analysis
    # ----------------
    # absolute value of the area of the smallest contour
    'min_contourarea': 5,
    # extention of the bounding box of the target contour
    # for estimating background temperature
    'bbox_extension': 10,
}

# 总图像帧数量
frame_nums = 0
lock = threading.Lock()


class read_queue_data_Thread(MyQThread):
    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.camera_list = None
        pass

    def dosomething(self):
        if not self.queue.empty():
            message = self.queue.get()
            if message is not None and isinstance(message, dict) and len(message) > 0 and 'to' in message and message[
                'to'] == 'main_infrared_camera':
                logger.error(f"{self.name}_get_message:{message}")
                if 'data' in message and message['data'] == 'stop':
                    if self.camera_list is not None:
                        for camera_struct_l in self.camera_list:
                            if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                                camera_struct_l['camera'].stop()
                        print("main_infrared_camera stop")
                        pass
            else:
                # 把消息放回去
                self.queue.put(message)

        pass


read_queue_data_thread = read_queue_data_Thread(name="main_infrared_camera_read_queue_data_thread")


class coordinate_writing:
    """
    将处理的坐标写入csv文件
    """

    def __init__(self, path, camera_id):
        self.path = path
        self.camera_id = camera_id
        self.csv_file = None
        self.csv_writer = None
        self.folder_path = self.path
        self.filename = self.folder_path + global_setting.get_setting("camera_config")['INFRARED_CAMERA'][
            'tmp_filename']

    def csv_create(self):
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
        with open(self.filename, mode='w', newline='', encoding='utf-8') as file:
            self.csv_file = file
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["Timestamp", "tmp(℃)"])

    def csv_write(self, file_base_name, t):
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
        with open(self.filename, mode='a', newline='', encoding='utf-8') as file:
            self.csv_file = file
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow([file_base_name, t])

    def csv_close(self):
        if self.csv_file is not None:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None


class TIP:
    """Thermal Image Pipeline"""

    def __init__(self, param):
        # 图像尺寸设置
        self.image_scale = param.get('image_scale', 1)
        self.ncol_nrow = param.get('fpa_ncol_nrow', (80, 62))
        self.image_size = (self.image_scale * self.ncol_nrow[0],
                           self.image_scale * self.ncol_nrow[1])
        # 伪彩色
        self.colormap = param.get('colormap', 'rainbow2')

        # 图像分割器初始化
        self.segment = CVSegment(param)

    def set_mean_temp_to_img(self, origin_image, mean_temp):
        """
        将平均温度放到图片上
        :return: image 更改之后的图片
        """
        # 定义文字内容
        if mean_temp is None:
            text = f"hs_mean: None degree C"
        else:
            text = f"hs_mean: {float(mean_temp)} degree C"

        # 定义文字位置（左上角坐标）
        position = (30, 30)

        # 定义字体
        font = cv.FONT_HERSHEY_SIMPLEX

        # 定义字体大小
        font_scale = 0.5

        # 定义颜色 (B, G, R)
        color = (0, 0, 0)

        # 定义线宽
        thickness = 1

        # 在图片上添加文字
        cv.putText(origin_image, text, position, font, font_scale, color, thickness, cv.LINE_AA)
        return origin_image

    def execute(self, frame):
        """Thermal data processing pipeline; produces image and stats/metrics"""
        # 把热图数据转成 8-bit 显示图像（通常是灰度或伪彩色图像）
        frame_uint8 = remap(frame)
        self.img_raw = cv_render(frame_uint8, resize=self.image_size,
                                 colormap=self.colormap,
                                 interpolation=cv.INTER_NEAREST, display=False)

        # 图像滤波并进行热点分割 对图像做滤波（如中值/双边滤波），然后用分割器提取热图中最热的区域（hotspot）。
        filtered_ui8 = cv_filter(frame_uint8, parameters={'blur_ks': 5},
                                 use_median=True, use_bilat=True)
        # 生成滤波图像
        # self.img_filtered = cv_render(filtered_ui8, resize=self.image_size,
        #                               colormap=self.colormap,
        #                               interpolation=cv.INTER_NEAREST, display=False)
        self.segment(frame=frame, frui8=filtered_ui8)

        # 渲染热点掩膜图像
        try:
            hs = self.segment.hotspots[0]
            hs_mask = hs.out_frames['hs_mask']
            hs_osd = hs.osd
        except IndexError:
            hs = None
            hs_mask = np.zeros(self.image_size, dtype='uint8')
            hs_osd = {}
        # self.img_hs_mask = cv_render(hs_mask, resize=self.image_size,
        #                              colormap='parula',
        #                              interpolation=cv.INTER_NEAREST, display=False)
        output_struct = {
            'hs_max': hs_osd.get('max', None),
            'hs_mean': hs_osd.get('mean', None),
        }
        self.img_raw = self.set_mean_temp_to_img(self.img_raw, output_struct['hs_mean'])
        # 返回处理后图像和温度统计数据。
        images = {
            'raw': self.img_raw,
            # 'filtered': self.img_filtered,
            # 'hotspot_mask': self.img_hs_mask,
        }

        return images, output_struct

    def __call__(self, thermal_data):
        return self.execute(thermal_data)


class Thermal_process(Thread):
    """
    温度处理线程
    """

    def __init__(self, path, id, serial_number):
        super().__init__()
        self.serial_number = serial_number
        self.path = path
        self.id = id
        self.running = None

        self.mi48 = None
        self.RA_Tmin = None
        self.RA_Tmax = None
        self.tip = None
        self.display = None
        self.vs = None
        self.test_frame = None
        self.init_state = None
        # 显示初始化失败的日志的控制变量
        self.init_error_log_show = False
        self.init_state = self.senxor_init()

    def parse_args(self):
        """
        参数解析
        :return:
        """
        parser = argparse.ArgumentParser()
        parser.add_argument('-tis', '--thermal-image-source', default=None, dest='tis_id',
                            help='Comport name (str) or thermal video source  ID (int)')
        parser.add_argument('-cis', '--color-image-source', type=int, default=None,
                            dest='cis_id',
                            help='Video source ID: 0=laptop cam, 1=USB webcam')
        parser.add_argument('-fps', '--framerate', default=5, type=int, dest='fps',
                            help='Frame rate per second')
        parser.add_argument('-c', '--colormap', default='rainbow2', type=str,
                            help='Colormap for the thermogram')
        parser.add_argument('--data_file', default=None, type=str,
                            help='file instead of camera stream')
        parser.add_argument('-v', '--video-record', default=False, dest='record_video',
                            action='store_true', help='Record a video of what is shown')
        parser.add_argument('-e', '--emissivity', type=float, default=0.95,
                            dest='emissivity', help='target emissivity')
        parser.add_argument('-histo', '--show-histogram', default=False, action='store_true',
                            dest='show_histogram', help='Show thermal image histogram')
        parser.add_argument('-plots', '--show-plots', default=False, action='store_true',
                            dest='show_plots',
                            help='Show plots of measured temperatures')
        parser.add_argument('-scale', '--thermal-image-scale-factor', default=4, type=int,
                            dest='img_scale', help='Scale factor for thermogram')

        args = parser.parse_args()
        return args

    def senxor_init(self):
        """
        温度传感器初始化
        :return:True or False
        """
        global is_used_ports
        args = self.parse_args()
        save_dir = args.save_dir if hasattr(args, 'save_dir') else './data'
        os.makedirs(save_dir, exist_ok=True)

        self.mi48, connected_port, port_names = connect_senxor(src=args.tis_id, name=f"infrared_camera_{self.id}",
                                                               is_used_ports=is_used_ports,
                                                               serial_number=self.serial_number)
        is_used_ports.append(connected_port)
        if self.mi48 is None:
            if not self.init_error_log_show:
                logger.error(
                    f'infrared camera_{self.id} | Cannot connect to SenXor | The following ports have SenXor attached {port_names}')
                self.init_error_log_show = True
            return False
            # sys.exit(1)
        else:
            logger.info(f'infrared camera_{self.id} | {self.mi48.sn} connected to {connected_port}')
        logger.info(f'infrared camera_{self.id} | camera_info: {self.mi48.camera_info}')

        self.mi48.set_fps(args.fps)
        self.mi48.regwrite(0xD0, 0x00)
        self.mi48.disable_filter(f1=True, f2=True, f3=True)
        self.mi48.enable_filter(f1=True, f2=True, f3=True)
        self.mi48.regwrite(0xC2, 0x64)
        self.mi48.set_emissivity(args.emissivity)
        self.mi48.set_offset_corr(3)
        self.mi48.start(stream=True, with_header=True)

        self.RA_Tmin = RollingAverageFilter(N=10)
        self.RA_Tmax = RollingAverageFilter(N=10)

        tip_param = {
            'colormap': args.colormap,
            'fpa_ncol_nrow': (self.mi48.cols, self.mi48.rows),
            'image_scale': args.img_scale,
        }
        tip_param.update(TIP_SEGM_PARAM)
        self.tip = TIP(tip_param)

        if args.cis_id is not None:
            self.vs = VideoStream(src=args.cis_id).start()
            self.test_frame = self.vs.read()
        else:
            self.vs = None
            self.test_frame = None

        if self.test_frame is None:
            self.vs = None

        display_options = {
            'window_coord': (0, 0),
            'window_title': f'{self.mi48.camera_id} ({self.mi48.name}), {args.cis_id}',
            'directory': r'data'
        }
        self.display = Display(display_options)

        self.images = {'thermal': {}}
        self.struct = {'thermal': {}}

        self.datasave = coordinate_writing(path=self.path, camera_id=self.id)
        self.datasave.csv_create()
        return True

    def stop(self):
        self.mi48.stop()
        cv.destroyAllWindows()
        self.datasave.csv_close()
        if self.vs is not None:
            self.vs.stop()
        self.running = False

    def run(self) -> None:
        # 图片保存路径 如果不存在则创建
        pic_save_path = self.path + global_setting.get_setting("camera_config")['INFRARED_CAMERA']['pic_dir']
        if not os.path.exists(pic_save_path):
            os.makedirs(pic_save_path)
        global frame_nums
        # 读取之前存储了多少图像
        with os.scandir(pic_save_path) as it:
            for entry in it:
                if entry.is_file():
                    with lock:
                        frame_nums += 1
        self.running = True
        logger.info(f"红外相机{self.id}开始运行")
        while self.running:
            # while True:
            # 如果初始化相机失败，则一直尝试初始化相机
            if not self.init_state:
                self.init_state = self.senxor_init()
                if not self.init_state:
                    continue
            with delete_process_lock:
                start_time = time.time()
                try:
                    raw_data, header = self.mi48.read()
                except Exception as e:
                    logger.error(f"红外相机_{self.id} | 异常，原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
                    self.init_state = False
                    self.init_error_log_show = False
                    continue
                if raw_data is None:
                    logger.error(f"红外相机_{self.id} | raw_data is None")
                    continue
                frame = data_to_frame(raw_data, (self.mi48.cols, self.mi48.rows),
                                      hflip=False)  # hflip与USB正反有关，朝上要翻转为true

                #
                Tmin, Tmax = self.RA_Tmin(frame.min()), self.RA_Tmax(frame.max())
                frame = np.clip(frame, Tmin, Tmax)
                _imgs, _struct = self.tip(frame)
                self.images['thermal'].update(_imgs)
                self.struct['thermal'].update(_struct)
                self.display.img = self.display.composer([self.images['thermal']['raw']])

                # self.display(self.display.img)  # 显示，可删除
                self.display.dir = Path(pic_save_path)
                file_base_name = time_util.get_format_file_from_time(time.time())
                self.display.save('{0}.bmp'.format(file_base_name))
                with lock:
                    frame_nums += 1
                self.datasave.csv_write(file_base_name, self.struct['thermal']['hs_mean'])  # 数据保存

                key = cv.waitKey(1) & 0xFF
                if key != -1:
                    if key == ord("q") or key == 27:
                        self.stop()
                end_time = time.time()
                logger.debug(
                    f"infrared_camera_{self.id}| image_process  | 图像处理线程一次处理时间：{end_time - start_time}秒 | 此时总图像帧数量:{frame_nums}")
            time.sleep(float(global_setting.get_setting("camera_config")['INFRARED_CAMERA']['delay']))

        pass


class Delete_file(Thread):
    """
    清除文件线程
    """

    def __init__(self, path, start_time):
        super().__init__()
        self.path = path
        self.start_time = start_time

    # 获得删除文件的大小
    def get_and_delete_files(self):

        total_size = 0
        total_nums = 0
        for root, dirs, files in os.walk(self.path):
            # logger.warning(f"{root} | {dirs} | {files}")
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)  # 获取文件大小（字节）
                    size = float(size / 1204 / 1024 / 1024)  # 将字节B转成GB
                    total_size += size
                    total_nums += 1
                    os.remove(file_path)  # 删除文件
                except Exception as e:
                    logger.error(
                        f"infrared_camera Failed to delete {file_path}: reason:{e} |  异常堆栈跟踪：{traceback.print_exc()}")
        global frame_nums
        with lock:
            logger.warning(f"红外相机 | 删除文件总大小: {total_size} G-bytes | 删除文件总数量： {total_nums} | 此时相机拍摄的图像数量：{frame_nums}")
            frame_nums = 0
        return total_size

    def stop(self):
        self.running = False

    def run(self) -> None:
        try:
            logger.info(f"红外相机删除文件线程开始运行")
            self.running = True
            while self.running:
                with delete_process_lock:
                    # 获取现在时间与上次删除时间之差
                    current_time = time.time()
                    elapsed = current_time - self.start_time
                    if elapsed >= float(global_setting.get_setting("camera_config")['DELETE']['interval_seconds']):
                        # 尝试删除文件
                        # 获取删除文件内的所有文件大小
                        self.get_and_delete_files()

                        logger.info(f"deep_camera 删除文件成功")
                        self.start_time = time.time()

                        pass
                    # logger.info(f"时间差{time_util.get_format_minute_from_time(elapsed)}")
                time.sleep(float(global_setting.get_setting("camera_config")['DELETE']['delay']))
        except Exception as e:
            logger.error(f"红外相机删除文件线程运行异常，异常原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
        pass


def load_global_setting():
    # 加载相机配置
    config_file_path = os.getcwd() + "./config/camera_config.ini"

    # 串口配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    config = ini_parser(config_file_path).read()
    if (len(config) != 0):
        logger.info("相机配置文件读取成功。")
    else:
        logger.error("相机配置文件读取失败。")
    global_setting.set_setting("camera_config", config)
    # 记录运行时间的开始时间
    start_time = time.time()
    global_setting.set_setting("start_time", start_time)
    logger.info(f"相机连接开始时间：{time_util.get_format_from_time(start_time)}")
    # 记录运行时上一次删除文件时间
    last_delete_time = time.time()
    global_setting.set_setting("last_delete_time", last_delete_time)
    return config


def check_setting_cameras_each_number():
    """
    检测是否有相机与鼠笼编号一一对应的文件，如果没有就显示界面让用户选完在进行相机连接，如果有文件则根据文件来一一对应
    :return:
    """
    config_file_path = f"./{global_setting.get_setting('camera_config')['INFRARED_CAMERA']['camera_to_mouse_cage_number_file_name']}"
    if folder_util.is_exist_file(
            config_file_path):
        # 存在配置文件
        # 读取配置文件
        serials = json_util.read_json_to_dict_list(config_file_path)
        init_camera_and_image_handle_thread(serials)
        pass
    else:
        # 不存在配置文件


        dialog_frame = infrared_camera_config_dialog(title="红外相机配置")
        dialog_frame.camera_config_finished_signal.connect(init_camera_and_image_handle_thread)
        dialog_frame.show_frame()


        pass


def init_camera_and_image_handle_thread(serials):
    global camera_list, read_queue_data_thread
    # global_setting.get_setting("queue").put({'data':'stop','to':'main_infrared_camera'})
    # 初始化保存路径
    path = global_setting.get_setting("camera_config")['STORAGE']['fold_path'] + \
           global_setting.get_setting("camera_config")['INFRARED_CAMERA']['path']
    # camera_nums = int(global_setting.get_setting("camera_config")['INFRARED_CAMERA']['nums'])
    camera_nums = len(serials)
    # 更改相机数量全局变量
    camera_config_temp = global_setting.get_setting("camera_config")
    camera_config_temp['INFRARED_CAMERA']['nums'] = camera_nums
    global_setting.set_setting("camera_config", camera_config_temp)
    camera_list = []
    for num in range(camera_nums):

        camera_struct = {}
        camera = None
        try:
            # 初始化
            camera = Thermal_process(
                path=path + f"{global_setting.get_setting('camera_config')['INFRARED_CAMERA']['mouse_cage_prefix']}{serials[num]['mouse_cage_number']}/",
                id=serials[num]['mouse_cage_number'], serial_number=serials[num]['serial'])
        except Exception as e:
            logger.error(f"红外相机{num + 1}初始化失败，失败原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
            # 所有线程停止
            delete_file_thread.stop()
            for camera_struct_l in camera_list:
                if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                    camera_struct_l['camera'].stop()
            continue

        camera.start()

        camera_struct['id'] = num + 1
        camera_struct['camera'] = camera
        camera_list.append(camera_struct)
    read_queue_data_thread.camera_list = camera_list
    pass


def main(q):
    # logger.remove(0)
    logger.add(
        "./log/infrared_camera/i_camera_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}"
    )
    logger.info(f"{'-' * 30}infrared_camera_start{'-' * 30}")
    logger.info(f"{__name__} | {os.path.basename(__file__)}|{os.getpid()}|{os.getppid()}")
    # 设置全局变量
    load_global_setting()
    # 读取共享信息线程
    global read_queue_data_thread
    read_queue_data_thread.queue = q
    read_queue_data_thread.start()
    global_setting.set_setting("queue", q)
    # 初始化保存路径
    path = global_setting.get_setting("camera_config")['STORAGE']['fold_path'] + \
           global_setting.get_setting("camera_config")['INFRARED_CAMERA']['path']
    # 删除文件线程
    delete_file_thread = Delete_file(path=path, start_time=global_setting.get_setting("start_time"))
    delete_file_thread.start()

    # 根据设置的相机数量来连接
    check_setting_cameras_each_number()
    global camera_list
    return camera_list, read_queue_data_thread, delete_file_thread,

if __name__ == "__main__":
    q = multiprocessing.Queue()
    main(q)
