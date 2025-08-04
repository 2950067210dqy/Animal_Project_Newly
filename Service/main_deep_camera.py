import json
import threading
import traceback
from threading import Thread

from loguru import logger

from public.component.dialog.index.deep_camera_config_dialog_index import deep_camera_config_dialog
from public.config_class.global_setting import global_setting
from public.config_class.ini_parser import ini_parser
from public.entity.MyQThread import MyQThread
from util.folder_util import folder_util
from util.json_util import json_util

from util.time_util import time_util
import pyrealsense2 as rs
import cv2
import csv

from ultralytics import YOLO
import os
import time
import numpy as np

"""
修改：连接相机时间优化
"""
# 过滤日志
logger = logger.bind(category="deep_camera_logger")
# 删除文件线程
delete_file_thread = None
camera_list = []

frame_nums = 0
lock = threading.Lock()

# 删除线程和图像处理线程锁 保证同步
delete_process_lock = threading.Lock()

processed_log_lock = threading.Lock()
# 相机参数
intrinsics = os.getcwd() +"./config/deep_camera_intrinsics.json"

# 为每个文件创建一个锁，存储在字典里
file_locks = {}


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
                'to'] == 'main_deep_camera':
                logger.error(f"{self.name}_message:{message}")
                if 'data' in message and message['data'] == 'stop':
                    if self.camera_list is not None:
                        for camera_struct_l in self.camera_list:
                            if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                                camera_struct_l['camera'].stop()
                                camera_struct_l['camera'].terminal()
                            if len(camera_struct_l) != 0 and 'img_process' in camera_struct_l:
                                camera_struct_l['img_process'].stop()
                                camera_struct_l['img_process'].terminal()
                        pass
            else:
                # 把消息放回去
                self.queue.put(message)

        pass


read_queue_data_thread = read_queue_data_Thread(name="main_deep_camera_read_queue_data_thread")


class coordinate_writing:
    """
    将处理的坐标写入csv文件
    """

    def __init__(self, path, camera_id):
        self.path = path
        self.camera_id = camera_id
        self.csv_file = None
        self.csv_writer = None
        self.folder_path = self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['result_dir']
        self.filename = self.folder_path + global_setting.get_setting("camera_config")['DEEP_CAMERA'][
            'location_filename']

    def csv_create(self):
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
        with open(self.filename, mode='w', newline='', encoding='utf-8') as file:
            self.csv_file = file
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["base_file_name", "X (m)", "Y (m)", "Z (m)"])

    def csv_write(self, file_base_name, x, y, z):
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
        with open(self.filename, mode='a', newline='', encoding='utf-8') as file:
            self.csv_file = file
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow([file_base_name, x, y, z])

    def csv_close(self):
        if self.csv_file is not None:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None


class Detection:
    """
    使用yolo模型探查坐标
    """

    def __init__(self, path, camera_id):
        self.path = path
        self.camera_id = camera_id
        self.model = YOLO( os.getcwd() +'./model/best.pt')
        self.data_save = coordinate_writing(path=path, camera_id=camera_id)
        self.data_save.csv_create()
        self.intrinsics, self.unit = self.get_intrinsics(intrinsics)

    def get_intrinsics(self, intrinsics):
        with open(intrinsics, "r") as f:
            intrinsics_data = json.load(f)

        depth_intrin = rs.intrinsics()
        depth_intrin.width = intrinsics_data["width"]
        depth_intrin.height = intrinsics_data["height"]
        depth_intrin.ppx = intrinsics_data["ppx"]
        depth_intrin.ppy = intrinsics_data["ppy"]
        depth_intrin.fx = intrinsics_data["fx"]
        depth_intrin.fy = intrinsics_data["fy"]
        depth_intrin.model = rs.distortion(intrinsics_data["model"])
        depth_intrin.coeffs = intrinsics_data["coeffs"]
        unit = intrinsics_data["units"]
        return depth_intrin, unit

    def img_save(self, image, timestamp):
        img = global_setting.get_setting("camera_config")['DEEP_CAMERA']['result_dir'] + \
              global_setting.get_setting("camera_config")['DEEP_CAMERA']['result_img_dir']
        if not os.path.exists(self.path + img):
            os.makedirs(self.path + img)
        cv2.imwrite(self.path + img + "{0}.bmp".format(timestamp), image)

    def detect(self, color_image, depth_frame, file_base_name):
        if os.path.exists(color_image) and os.path.isfile(color_image) and os.path.exists(
                depth_frame) and os.path.isfile(depth_frame):
            try:
                if file_base_name + ".bmp" in file_locks:
                    with file_locks[file_base_name + ".bmp"]:
                        imge = cv2.imread(color_image)
                else:
                    imge = cv2.imread(color_image)
            except Exception as e:
                logger.error(
                    f"camera_{self.camera_id}图像处理程序读取{file_base_name}.bmp文件出错，原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
                return
            results = self.model(imge, classes=[0], verbose=False)
            # 处理检测结果
            for result in results:
                boxes = result.boxes.xyxy.cpu().numpy()
                if len(boxes) == 0:
                    x, y, z = 'NaN'
                    self.data_save.csv_write(file_base_name, x, y, z)
                    self.img_save(imge, file_base_name)
                    # with lock:
                    #     logger.info(
                    #         f'深度相机camera_{self.camera_id}的图像{file_base_name}处理结果保存成功 | x, y, z = NaN')
                    continue
                # 获取检测框坐标
                x1, y1, x2, y2 = map(int, boxes[0])
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                # 获取深度坐标
                try:
                    if file_base_name + ".npy" in file_locks:
                        with file_locks[file_base_name + ".npy"]:
                            depth = np.load(depth_frame)
                    else:
                        depth = np.load(depth_frame)
                except Exception as e:
                    logger.error(
                        f"camera_{self.camera_id}图像处理程序读取{file_base_name}.npy文件出错，原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
                    return
                    #  读取到的深度信息/1000 为真实的深度信息，单位为m
                depth = depth[center_y, center_x] * self.unit
                # depth = float(depth)   # 转换为米
                point_3d = rs.rs2_deproject_pixel_to_point(self.intrinsics, [center_x, center_y], depth)
                # print(f"point_3d{point_3d}")
                x, y, z = map(lambda v: round(v, 3), point_3d)

                # 写入
                self.data_save.csv_write(file_base_name, x, y, z)

                # 可视化
                imge = self.draw_overlay(imge, x1, y1, x2, y2, center_x, center_y, x, y, z)
                self.img_save(imge, file_base_name)
                # with lock:
                #     logger.info(
                #         f'深度相机camera_{self.camera_id}的图像{file_base_name}处理结果保存成功. | x, y, z ={x},{y},{z}')
        else:
            if os.path.exists(color_image) or os.path.isfile(color_image):
                logger.error(f"deep_camera_{self.camera_id} | {file_base_name}.bmp文件不存在")
                pass
            if os.path.exists(depth_frame) or os.path.isfile(depth_frame):
                logger.error(f"deep_camera_{self.camera_id} | {file_base_name}.npy文件不存在")
                pass

    # 绘制可视化信息
    def draw_overlay(self, image, x1, y1, x2, y2, center_x, center_y, x, y, z):
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(image, (center_x, center_y), 5, (0, 0, 255), -1)
        text = f"X: {x:.2f}m, Y: {y:.2f}m, Z: {z:.2f}m"
        cv2.putText(image, text, (x1, max(y1 - 10, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        return image


class Img_process(MyQThread):
    """
    将bmp文件和npm文件进行处理 线程处理
    """

    def __init__(self, path, camera_id):
        super().__init__(name=f"deep_camera_img_process_{camera_id}")
        self.path = path
        self.camera_id = camera_id
        self.dection = Detection(path=self.path, camera_id=self.camera_id)
        # 创建存储路径
        if not os.path.exists(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['color_dir']):
            os.makedirs(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['color_dir'])
        if not os.path.exists(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['depth_dir']):
            os.makedirs(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['depth_dir'])
        pass

    def clear_processed(self):
        """
        清空日志文件
        :return:
        """
        log = []
        # 保存更新后的日志
        with open(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['processed_log_filename'],
                  'w') as f:
            json.dump(log, f)
        pass

    def mark_as_processed(self, filename):
        """
        标记文件为已处理并存入json日志文件中
        :param filename:
        :return:
        """
        log = []

        # 尝试读取已存在的日志文件
        if os.path.exists(
                self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['processed_log_filename']):
            try:
                with open(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA'][
                    'processed_log_filename'], 'r') as f:
                    log = json.load(f)
            except (json.JSONDecodeError, IOError):
                log = []

        # 避免重复添加
        if filename not in log:
            log.append(filename)

        # 保存更新后的日志
        with open(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['processed_log_filename'],
                  'w') as f:
            json.dump(log, f)

    def has_been_processed(self, filename):
        """
        判断文件是否已经处理
        :param filename:
        :return:
        """
        if not os.path.exists(
                self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['processed_log_filename']):
            return False
        with open(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['processed_log_filename'],
                  'r') as f:
            log = json.load(f)
        return filename in log

    def dosomething(self) :
        with delete_process_lock:
            start_time = time.time()
            """处理文件夹中的文件"""
            # color文件夹下的 对bmp文件名牌序

            files = sorted(f for f in os.listdir(
                self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['color_dir']) if
                           f.endswith(".bmp"))

            # 从日志文件中获取最后处理的文件名
            last_processed_file = None
            processed_log_path = self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA'][
                'processed_log_filename']
            if os.path.exists(processed_log_path):
                with processed_log_lock:
                    try:
                        with open(processed_log_path, 'r') as f:
                            log = json.load(f)
                    except FileNotFoundError:
                        # 如果文件不存在，则创建文件并写入默认内容
                        with open(processed_log_path, 'w') as f:
                            json.dump([], f)
                if log:
                    last_processed_file = log[-1]  # 获取最后处理的文件

            # 如果是增量处理，从上次未处理的文件开始
            start_processing = False
            # 一次处理文件的数量
            handle_files_nums = 0
            for file in files:
                if last_processed_file:
                    if not start_processing and file == last_processed_file:
                        start_processing = True
                    if not start_processing:
                        continue  # 如果未到达上次处理的文件，跳过
                base_name = os.path.splitext(file)[0]
                # 在这里进行文件处理（可以替换为实际的处理函数）
                bmp_path = os.path.join(
                    self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['color_dir'], file)
                npy_path = os.path.join(
                    self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['depth_dir'],
                    base_name + ".npy")

                self.dection.detect(bmp_path, npy_path, base_name)

                # 处理完毕后，标记文件为已处理
                with processed_log_lock:
                    self.mark_as_processed(file)
                handle_files_nums += 1
            # 如果遍历完所有文件start_processing还是False 则processed_log日志文件出现问题，直接清空processed_log日志文件
            if not start_processing:
                self.clear_processed()
            self.dection.data_save.csv_close()
            end_time = time.time()
            logger.debug(
                f"deep_camera_{self.camera_id} | image_process |  图像处理线程一次处理时间：{end_time - start_time}秒 | 共处理{handle_files_nums}个图像文件 | 此时总图像帧数量:{frame_nums}")
        time.sleep(float(global_setting.get_setting("camera_config")['DEEP_CAMERA']['process_delay']))
        pass


class Delete_file(MyQThread):
    """
    清除文件线程
    """

    def __init__(self, path, start_time):
        super().__init__(name=f"deep_camera_delete_file")
        self.path = path
        self.start_time = start_time

    # 获得删除文件的大小
    def get_and_delete_files(self):
        global file_locks
        total_size = 0
        total_nums = 0
        for root, dirs, files in os.walk(self.path):
            # logger.warning(f"{root} | {dirs} | {files}")
            # 将深度信息npy文件排除 不删除
            # if "depth" not in root:
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)  # 获取文件大小（字节）
                    size = float(size / 1204 / 1024 / 1024)  # 将字节B转成GB
                    total_size += size
                    total_nums += 1
                    if file.split(".")[1] in ['bmp', 'npy']:
                        # 对bmp和npy文件锁删除
                        if file in file_locks:
                            with file_locks[file]:
                                os.remove(file_path)  # 删除文件
                        else:
                            os.remove(file_path)  # 删除文件
                        # 删除文件后释放锁
                        if file in file_locks:
                            del file_locks[file]
                    else:
                        os.remove(file_path)  # 删除文件
                except Exception as e:
                    logger.trace(
                        f"deep_camera Failed to delete {file_path}: reason:{e} |  异常堆栈跟踪：{traceback.print_exc()}")
        global frame_nums
        with lock:
            logger.warning(f"深度相机 | 删除文件总大小: {total_size} G-bytes | 删除文件总数量： {total_nums} | 此时相机拍摄的图像数量：{frame_nums}")
            frame_nums = 0
        return total_size



    def dosomething(self) :
        try:
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
            logger.error(f"深度相机删除文件线程运行异常，异常原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
        pass


class RealSenseProcessor(MyQThread):
    """
    相机线程
    """

    def __init__(self, path='', id=1, serial_number=""):
        super().__init__(name=f"deep_camera_{id}")
        self.serial_number = serial_number
        self.id = id
        self.path = path
        self.init_state = self.init_camera()

    def check_pipeline_status(self):
        try:
            # 获取当前的传输状态
            frames = self.pipeline.wait_for_frames(timeout_ms=5000)
            return True
        except Exception as e:
            return False

    def init_camera(self):
        """
        初始化相机
        :return:True 连接成功 False连接失败
        """
        # 帧率
        self.fps = 30
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_device(self.serial_number)
        self.config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, self.fps)
        self.config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, self.fps)
        self.align = rs.align(rs.stream.color)
        try:
            # 尝试启动 RealSense 流
            self.pipeline.start(self.config)

            # logger.info(f"深度相机_{self.id} | 设备已连接。")
            return True
        except Exception as e:
            logger.error(f"深度相机_{self.id} | 设备未连接: 异常原因{e} |   异常堆栈跟踪：{traceback.print_exc()}")
            return False

    def img_save(self, image, depth_image):
        global file_locks
        timestrf = time_util.get_format_file_from_time(time.time())
        directory_color = self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['color_dir']
        if not os.path.exists(directory_color):
            os.makedirs(directory_color)  # 递归创建目录
        cv2.imwrite(directory_color + f"/{timestrf}.bmp", image)
        #  为文件添加线程锁
        file_locks[f'{timestrf}.bmp'] = threading.Lock()
        directory_depth = self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['depth_dir']
        if not os.path.exists(directory_depth):
            os.makedirs(directory_depth)  # 递归创建目录
        np.save(directory_depth + f"/{timestrf}.npy", depth_image)
        #  为文件添加线程锁
        file_locks[f'{timestrf}.npy'] = threading.Lock()


    def stop(self):
        self.pipeline.stop()
        super().stop()

    # 启动，获取一帧
    def run(self):
        logger.warning(f"{self.name} thread has been started！")
        global frame_nums
        # 读取之前存储了多少图像
        with os.scandir(self.path + global_setting.get_setting("camera_config")['DEEP_CAMERA']['color_dir']) as it:
            for entry in it:
                if entry.is_file():
                    with lock:
                        frame_nums += 1
        last_frame_number = None
        while self._running:
            self.mutex.lock()
            if self._paused:
                self.condition.wait(self.mutex)  # 等待条件变量
            self.mutex.unlock()

            try:
                # 执行一些工作（替代为你需要的任务）
                self.dosomething(last_frame_number)
            except Exception as e:
                logger.error(f"deep_相机{self.id}运行异常，异常原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")


    def dosomething(self,last_frame_number=None):
        global frame_nums
        # 如果初始化相机失败，则一直尝试初始化相机
        if not self.init_state:
            self.init_state = self.init_camera()
            if not self.init_state:
                return
        # if not self.check_pipeline_status():
        #     self.init_camera()
        #     pass

        # 等待一帧 连续拍
        # asyncio.run()
        # 本来wait_for_frames就是同步等待帧，
        start_time = time.time()
        frames = None
        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=500)
        except RuntimeError as e:
            logger.error(f"deep_camera{self.id}获取帧失败，RuntimeError: {e}")
        except Exception as e:
            logger.error(f"deep_camera{self.id}获取帧失败，异常原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
            self.init_state = False
            return
            pass
        if not frames:
            if last_frame_number is None:
                last_frame_number = 0
            # 帧不存在
            last_frame_number += (
                float(global_setting.get_setting("camera_config")['DEEP_CAMERA']['delay']))
            logger.error(f"deep_camera_{self.id} | lose frame | 丢帧！| frames = None")
            return
        # 对其深度与RGB帧
        frames = self.align.process(frames)
        color_frame = frames.get_color_frame()
        depth_frame = frames.get_depth_frame()

        if not color_frame or not depth_frame:
            # 帧不存在
            if last_frame_number is None:
                last_frame_number = 0
            last_frame_number += (
                float(global_setting.get_setting("camera_config")['DEEP_CAMERA']['delay']))
            logger.error(f"deep_camera_{self.id}| lose frame | 丢帧！| color_frame or depth_frame = None")
            return
        current_frame_number = color_frame.get_frame_number()
        logger.debug(
            f"deep_camera_{self.id} | image_get_frame_number |  获取当前帧，帧序号为：{current_frame_number} | 上一帧序号为：{last_frame_number} | 两帧相差:{current_frame_number if last_frame_number is None else current_frame_number - last_frame_number}")
        # 检查是否跳帧
        if last_frame_number is not None and (
                current_frame_number < last_frame_number + self.fps - (float(
            global_setting.get_setting("camera_config")['DEEP_CAMERA'][
                'delay']) + 1) or current_frame_number > last_frame_number + self.fps + (
                        float(global_setting.get_setting("camera_config")['DEEP_CAMERA']['delay']) + 1)):
            logger.error(
                f"deep_camera_{self.id} | lose frame | 发现丢帧！上帧编号: {last_frame_number} | 当前帧编号: {current_frame_number - self.fps - (float(global_setting.get_setting('camera_config')['DEEP_CAMERA']['delay']))} |真实当前帧编号：{current_frame_number}")

        last_frame_number = current_frame_number
        # 转换图像格式
        color_image = np.asanyarray(color_frame.get_data())
        depth_image = np.asanyarray(depth_frame.get_data())
        self.img_save(color_image, depth_image)
        with lock:
            frame_nums += 1
        # self.running = False
        end_time = time.time()
        logger.debug(
            f"deep_camera_{self.id} | image_read | 图像获取帧线程一次处理时间：{end_time - start_time}秒  | 此时总图像帧数量:{frame_nums}")
        time.sleep(float(global_setting.get_setting("camera_config")['DEEP_CAMERA']['delay']))
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
    config_file_path = f"./{global_setting.get_setting('camera_config')['DEEP_CAMERA']['camera_to_mouse_cage_number_file_name']}"
    if folder_util.is_exist_file(
            config_file_path):
        # 存在配置文件
        # 读取配置文件
        serials = json_util.read_json_to_dict_list(config_file_path)
        init_camera_and_image_handle_thread(serials)
        pass
    else:
        # 不存在配置文件

        try:
            dialog_frame = deep_camera_config_dialog(title="深度相机配置")
            dialog_frame.camera_config_finished_signal.connect(init_camera_and_image_handle_thread)
            dialog_frame.show_frame()
        except Exception as e:
            logger.error(e)

        pass


def init_camera_and_image_handle_thread(serials):
    global camera_list, read_queue_data_thread
    # global_setting.get_setting("queue").put({'data': 'stop', 'to': 'main_deep_camera'})
    # 初始化保存路径
    path = global_setting.get_setting("camera_config")['STORAGE']['fold_path'] + \
           global_setting.get_setting("camera_config")['DEEP_CAMERA']['path']
    # 相机和图像处理线程初始化
    # camera_nums = int(global_setting.get_setting("camera_config")['DEEP_CAMERA']['nums'])
    camera_nums = len(serials)
    # 更改相机数量全局变量
    camera_config_temp = global_setting.get_setting("camera_config")
    camera_config_temp['DEEP_CAMERA']['nums'] = camera_nums
    global_setting.set_setting("camera_config", camera_config_temp)
    # 之前正在运行的相机thread全部结束
    if len(camera_list)>0:
        for camera_struct_l in camera_list:
            if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                try:
                    if camera_struct_l['camera'] is not None and camera_struct_l['camera'].isRunning():
                        camera_struct_l['camera'].stop()

                except Exception as e:
                    logger.error(f"关闭实验监测错误，原因：{e}")
            if len(camera_struct_l) != 0 and 'img_process' in camera_struct_l:
                try:
                    if camera_struct_l['img_process'] is not None and camera_struct_l['img_process'].isRunning():
                        camera_struct_l['img_process'].stop()

                except Exception as e:
                    logger.error(f"关闭实验监测错误，原因：{e}")
    camera_list = []
    # serials = ["230322273703", "230322274766"]
    for num in range(camera_nums):
        camera_struct = {}
        camera = None
        try:
            # 相机初始化
            camera = RealSenseProcessor(
                path=path + f"{global_setting.get_setting('camera_config')['DEEP_CAMERA']['mouse_cage_prefix']}{serials[num]['mouse_cage_number']}/",
                id=serials[num]['mouse_cage_number'],
                serial_number=serials[num]['serial'])
        except Exception as e:
            logger.error(f"deep相机{serials[num]['mouse_cage_number']}初始化失败，失败原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
            # 所有线程停止
            delete_file_thread.stop()
            delete_file_thread.terminal()
            for camera_struct_l in camera_list:
                if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                    camera_struct_l['camera'].stop()

                if len(camera_struct_l) != 0 and 'img_process' in camera_struct_l:
                    camera_struct_l['img_process'].stop()

            continue
        img_process = None
        try:
            # 图像处理初始化
            img_process = Img_process(
                path=path + f"{global_setting.get_setting('camera_config')['DEEP_CAMERA']['mouse_cage_prefix']}{serials[num]['mouse_cage_number']}/",
                camera_id=serials[num]['mouse_cage_number'])
        except Exception as e:
            logger.error(
                f"deep 图像处理相机{serials[num]['mouse_cage_number']}初始化失败，失败原因：{e} |  异常堆栈跟踪：{traceback.print_exc()}")
            # 所有线程停止
            delete_file_thread.stop()
            delete_file_thread.terminal()
            for camera_struct_l in camera_list:
                if len(camera_struct_l) != 0 and 'camera' in camera_struct_l:
                    camera_struct_l['camera'].stop()

                if len(camera_struct_l) != 0 and 'img_process' in camera_struct_l:
                    camera_struct_l['img_process'].stop()

            continue
        camera.start()
        img_process.start()
        camera_struct['id'] = num + 1
        camera_struct['camera'] = camera
        camera_struct['img_process'] = img_process
        camera_list.append(camera_struct)
        pass
    read_queue_data_thread.camera_list = camera_list
    pass


def main(q):
    # 加载日志配置
    # logger.remove(0)
    # 過濾日志
    logger.add(
        "./log/deep_camera/d_camera_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} |{process.name} | {thread.name} |  {name} : {module}:{line} | {message}",
        filter = lambda record: record["extra"].get("category") == "deep_camera_logger"
    )
    logger.info(f"{'-' * 30}deep_camera_start{'-' * 30}")
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
           global_setting.get_setting("camera_config")['DEEP_CAMERA']['path']
    # 删除文件线程
    delete_file_thread = Delete_file(path=path, start_time=global_setting.get_setting("start_time"))
    delete_file_thread.start()
    # 根据设置的相机数量来连接
    check_setting_cameras_each_number()
    global camera_list
    return camera_list,read_queue_data_thread,delete_file_thread,
    # stop
    # camera1.pipeline.stop()


if __name__ == "__main__":
    main()
