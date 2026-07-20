import os
import sys
import time
import threading
import traceback
from collections import deque
from typing import Any

import cv2
from PyQt6.QtCore import QCoreApplication
from loguru import logger

from public.config_class import global_load
from public.config_class.global_setting import global_setting
from public.entity.MyQThread import MyQThread
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.util.folder_util import folder_util
from public.util.json_util import json_util
from public.util.shared_video_frames import shared_video_frame_store
from public.util.time_util import time_util


logged_errors = set()
delete_file_thread = None
save_frame_thread = None
camera_list = []
frame_nums = 0
lock = threading.Lock()
delete_process_lock = threading.Lock()
# Image files may be deleted by the cleanup thread while capture is still writing.
file_locks = {}


def _camera_config():
    return global_setting.get_setting("camera_config")


def _deep_camera_config():
    return _camera_config()["DEEP_CAMERA"]


def _deep_delete_interval_seconds():
    deep_config = _deep_camera_config()
    return float(
        deep_config.get(
            "delete_interval_seconds",
            _camera_config()["DELETE"]["interval_seconds"],
        )
    )


def _deep_delete_delay():
    deep_config = _deep_camera_config()
    return float(
        deep_config.get(
            "delete_delay",
            _camera_config()["DELETE"]["delay"],
        )
    )


def _raw_save_interval_seconds():
    return float(_deep_camera_config().get("raw_save_interval_seconds", 1.0))


def _storage_root():
    config = _camera_config()
    return config["STORAGE"]["fold_path"] + config["DEEP_CAMERA"]["path"]


def _camera_base_path(mouse_cage_number):
    deep_config = _deep_camera_config()
    return os.path.join(
        _storage_root(),
        f"{deep_config['mouse_cage_prefix']}{mouse_cage_number}",
    ) + "/"


class read_queue_data_Thread(MyQThread):
    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.camera_list = None

    def dosomething(self):
        # This thread only consumes messages addressed to main_deep_camera.
        if self.queue is None or self.queue.empty():
            time.sleep(0.05)
            return

        try:
            message: ObjectQueueItem = self.queue.get()
        except Exception as e:
            logger.error(f"{self.name} receive queue message failed: {e}")
            return

        if message is None or message.is_Empty():
            return

        if not isinstance(message, ObjectQueueItem) or message.to != "main_deep_camera":
            self.queue.put(message)
            time.sleep(0.02)
            return

        logger.info(f"{self.name} message: {message}")

        match message.title:
            case "stop_running_cameras":
                if self.camera_list is not None:
                    for camera_struct in self.camera_list:
                        camera = camera_struct.get("camera")
                        if camera is not None:
                            camera.stop()
                            camera.terminal()
                        img_process = camera_struct.get("img_process")
                        if img_process is not None:
                            img_process.stop()
                            img_process.terminal()
            case "start":
                data = message.data or {}
                global_setting.set_setting(
                    "start_experiment_time",
                    data.get("start_experiment_time", time.time()),
                )
                global_setting.set_setting(
                    "pause_experiment_time",
                    data.get("pause_experiment_time", []),
                )
                global_setting.set_setting(
                    "relieve_pause_experiment_time",
                    data.get("relieve_pause_experiment_time", []),
                )
                start()
            case "pause":
                pause()
            case "stop":
                data = message.data or {}
                global_setting.set_setting(
                    "stop_experiment_time",
                    data.get("stop_experiment_time", time.time()),
                )
                stop()
            case "experiment_setting":
                data = message.data or {}
                global_setting.set_setting("experiment_setting", data.get("experiment_setting"))
                global_setting.set_setting(
                    "experiment_setting_file",
                    data.get("experiment_setting_file", ""),
                )
            case "camera_config":
                if message.data is not None:
                    init_camera_and_image_handle_thread(message.data)
            case _:
                pass


read_queue_data_thread = read_queue_data_Thread(name="main_deep_camera_read_queue_data_thread")


class Delete_file(MyQThread):
    def __init__(self, path, start_time):
        super().__init__(name="deep_camera_delete_file")
        self.path = path
        self.start_time = start_time

    def get_and_delete_files(self):
        global file_locks, frame_nums

        total_size_gb = 0.0
        total_nums = 0
        location_filename = _deep_camera_config().get("location_filename", "")

        for root, _dirs, files in os.walk(self.path):
            for file_name in files:
                ext = os.path.splitext(file_name)[1].lower()
                if location_filename and location_filename in file_name:
                    continue

                file_path = os.path.join(root, file_name)
                try:
                    total_size_gb += os.path.getsize(file_path) / 1024 / 1024 / 1024
                    total_nums += 1

                    # Guard image deletion with a per-file lock to reduce races with cv2.imwrite.
                    if ext in [".bmp", ".png"] and file_name in file_locks:
                        with file_locks[file_name]:
                            os.remove(file_path)
                        del file_locks[file_name]
                    else:
                        os.remove(file_path)
                except Exception as e:
                    logger.trace(
                        f"deep_camera delete file failed: {file_path}, reason: {e}, traceback: {traceback.format_exc()}"
                    )

        with lock:
            logger.warning(
                f"deep_camera delete files: total_size={total_size_gb:.3f}GB, total_count={total_nums}, captured_frames={frame_nums}"
            )
            frame_nums = 0

        return total_size_gb

    def dosomething(self):
        try:
            with delete_process_lock:
                current_time = time.time()
                elapsed = current_time - self.start_time
                if elapsed >= _deep_delete_interval_seconds():
                    self.get_and_delete_files()
                    logger.info("deep_camera delete files finished")
                    self.start_time = time.time()

            time.sleep(_deep_delete_delay())
        except Exception as e:
            logger.error(f"deep_camera delete thread failed: {e} | {traceback.format_exc()}")


class SaveRawFrameThread(MyQThread):
    def __init__(self, max_pending: int = 64):
        super().__init__(name="deep_camera_save_raw_frame")
        self.max_pending = max_pending
        self.pending_items: deque[tuple[str, str, Any]] = deque()
        self.pending_lock = threading.Lock()
        self.dropped_count = 0

    def submit_frame(self, output_path: str, file_name: str, frame):
        if not output_path or frame is None:
            return
        with self.pending_lock:
            if len(self.pending_items) >= self.max_pending:
                self.pending_items.popleft()
                self.dropped_count += 1
            self.pending_items.append((output_path, file_name, frame.copy()))

    def dosomething(self):
        item = None
        with self.pending_lock:
            if self.pending_items:
                item = self.pending_items.popleft()

        if item is None:
            time.sleep(0.01)
            return

        output_path, file_name, frame = item
        folder_path = os.path.dirname(output_path)
        if folder_path and not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)

        file_lock = file_locks.setdefault(file_name, threading.Lock())
        with file_lock:
            cv2.imwrite(output_path, frame)


def parse_uvc_device_index(device_identifier):
    # Support both raw indices and the persisted "uvc_index_x" format.
    if isinstance(device_identifier, int):
        return device_identifier
    if device_identifier is None:
        return None

    value = str(device_identifier).strip()
    if value.isdigit():
        return int(value)
    if value.startswith("uvc_index_"):
        suffix = value.replace("uvc_index_", "", 1)
        if suffix.isdigit():
            return int(suffix)
    return None


class UVCCameraProcessor(MyQThread):
    def __init__(self, path="", id=1, serial_number="", device_index=None):
        super().__init__(name=f"deep_camera_{id}")
        self.cage_number = int(id)
        self.serial_number = serial_number
        self.device_index = device_index if device_index is not None else parse_uvc_device_index(serial_number)
        self.id = id
        self.path = path
        self.capture = None
        self.fps = 30
        self.frame_width = 1280
        self.frame_height = 720
        self.frame_id = 0
        self.last_raw_save_time = 0.0
        self.init_state = self.init_camera()

    def _open_capture(self, index):
        # Try common Windows backends first, then fall back to OpenCV default.
        backends = []
        if hasattr(cv2, "CAP_DSHOW"):
            backends.append(cv2.CAP_DSHOW)
        if hasattr(cv2, "CAP_MSMF"):
            backends.append(cv2.CAP_MSMF)
        backends.append(None)

        for backend in backends:
            capture = cv2.VideoCapture(index, backend) if backend is not None else cv2.VideoCapture(index)
            if capture is not None and capture.isOpened():
                return capture
            if capture is not None:
                capture.release()
        return None

    def init_camera(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None

        if self.device_index is None:
            error_message = f"UVC camera config is invalid, serial={self.serial_number}"
            if error_message not in logged_errors:
                logger.error(error_message)
                logged_errors.add(error_message)
            return False

        self.capture = self._open_capture(self.device_index)
        if self.capture is None:
            error_message = f"UVC camera open failed, index={self.device_index}"
            if error_message not in logged_errors:
                logger.error(error_message)
                logged_errors.add(error_message)
            return False

        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        self.capture.set(cv2.CAP_PROP_FPS, self.fps)
        logger.info(f"deep_camera_{self.id} connected to UVC device {self.device_index}")
        return True

    def _ensure_dir(self, path):
        if not os.path.exists(path):
            os.makedirs(path)

    def img_save(self, image, *, timestamp: float):
        global save_frame_thread

        timestrf = time_util.get_format_file_from_time(timestamp)
        file_name = f"{timestrf}.bmp"
        deep_config = _deep_camera_config()
        color_dir = os.path.join(self.path, deep_config["color_dir"].strip("/\\"))
        self._ensure_dir(color_dir)
        color_path = os.path.join(color_dir, file_name)
        if save_frame_thread is not None and save_frame_thread.isRunning():
            save_frame_thread.submit_frame(color_path, file_name, image)
        return color_path, file_name

    def stop(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        shared_video_frame_store.clear_frame("deep_camera", self.cage_number)
        super().stop()

    def run(self):
        logger.warning(f"{self.name} thread has been started")
        self._running = True
        global frame_nums

        color_dir = os.path.join(self.path, _deep_camera_config()["color_dir"].strip("/\\"))
        self._ensure_dir(color_dir)

        with os.scandir(color_dir) as it:
            for entry in it:
                if entry.is_file():
                    with lock:
                        frame_nums += 1

        while self._running:
            self.mutex.lock()
            if self._paused:
                self.condition.wait(self.mutex)
            self.mutex.unlock()

            try:
                self.dosomething()
            except Exception as e:
                logger.error(f"deep_camera_{self.id} run failed: {e} | {traceback.format_exc()}")

    def dosomething(self):
        global frame_nums

        # Reconnect lazily if the device dropped during runtime.
        if not self.init_state:
            self.init_state = self.init_camera()
            if not self.init_state:
                time.sleep(float(_deep_camera_config()["delay"]))
                return

        if self.capture is None:
            self.init_state = False
            return

        start_time = time.time()
        ret, color_image = self.capture.read()
        if not ret or color_image is None:
            logger.error(f"deep_camera_{self.id} read frame failed from UVC device {self.device_index}")
            self.init_state = False
            time.sleep(float(_deep_camera_config()["delay"]))
            return

        timestamp = time.time()
        self.frame_id += 1
        raw_save_interval = _raw_save_interval_seconds()
        if raw_save_interval <= 0 or timestamp - self.last_raw_save_time >= raw_save_interval:
            self.img_save(color_image, timestamp=timestamp)
            self.last_raw_save_time = timestamp
        shared_video_frame_store.write_frame(
            "deep_camera",
            self.cage_number,
            color_image,
            frame_id=self.frame_id,
            timestamp=timestamp,
        )
        with lock:
            frame_nums += 1

        elapsed = time.time() - start_time
        logger.debug(
            f"deep_camera_{self.id} capture frame cost={elapsed:.3f}s total_frames={frame_nums}"
        )
        time.sleep(float(_deep_camera_config()["delay"]))


def load_global_setting():
    global_load.load_global_setting_without_Qt()
    start_time = time.time()
    global_setting.set_setting("start_time", start_time)
    global_setting.set_setting("last_delete_time", start_time)
    logger.info(f"deep_camera load settings at {time_util.get_format_from_time(start_time)}")


def check_setting_cameras_each_number():
    config_file_path = f"./{_deep_camera_config()['camera_to_mouse_cage_number_file_name']}"
    if folder_util.is_exist_file(config_file_path):
        serials = json_util.read_json_to_dict_list(config_file_path)
        init_camera_and_image_handle_thread(serials)
        return

    try:
        # Ask the GUI to open the cage-to-camera mapping dialog when no config exists.
        logger.error("deep_camera config mapping file not found, request config dialog")
        queue = global_setting.get_setting("queue", None)
        if queue is not None:
            queue.put(
                ObjectQueueItem(
                    origin="main_deep_camera",
                    to="main_gui",
                    title="deep_camera_config_dialog",
                    time=time_util.get_format_from_time(time.time()),
                )
            )
    except Exception as e:
        logger.error(f"open deep camera config dialog failed: {e}")


def init_camera_and_image_handle_thread(serials):
    global camera_list, read_queue_data_thread, delete_file_thread

    camera_nums = len(serials)
    camera_config_temp = _camera_config()
    camera_config_temp["DEEP_CAMERA"]["nums"] = camera_nums
    global_setting.set_setting("camera_config", camera_config_temp)

    if camera_list:
        for camera_struct in camera_list:
            camera = camera_struct.get("camera")
            if camera is not None:
                try:
                    if camera.isRunning():
                        camera.stop()
                except Exception as e:
                    logger.error(f"stop old deep camera thread failed: {e}")

            img_process = camera_struct.get("img_process")
            if img_process is not None:
                try:
                    if img_process.isRunning():
                        img_process.stop()
                except Exception as e:
                    logger.error(f"stop old deep camera process thread failed: {e}")

    camera_list = []

    for num in range(camera_nums):
        camera_struct = {}
        serial_config = serials[num]

        try:
            # Each mouse cage maps to one UVC device index from the saved config file.
            camera = UVCCameraProcessor(
                path=_camera_base_path(serial_config["mouse_cage_number"]),
                id=serial_config["mouse_cage_number"],
                serial_number=serial_config.get("serial"),
                device_index=serial_config.get("device_index"),
            )
        except Exception as e:
            logger.error(
                f"init deep camera failed, cage={serial_config['mouse_cage_number']}, reason={e} | {traceback.format_exc()}"
            )
            if delete_file_thread is not None:
                delete_file_thread.stop()
            for started_camera in camera_list:
                running_camera = started_camera.get("camera")
                if running_camera is not None:
                    running_camera.stop()
            continue

        camera.start()
        camera_struct["id"] = num + 1
        camera_struct["camera"] = camera
        camera_struct["img_process"] = None
        camera_list.append(camera_struct)

    logger.warning(f"{camera_list}")
    read_queue_data_thread.camera_list = camera_list


def main(q=None):
    global_setting.set_setting("queue", q)

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)

    logger.info(f"{'-' * 30}deep_camera_start{'-' * 30}")
    logger.info(f"{__name__} | {os.path.basename(__file__)} | {os.getpid()} | {os.getppid()}")

    load_global_setting()

    read_queue_data_thread.queue = q
    if read_queue_data_thread.isRunning():
        read_queue_data_thread.stop()
    read_queue_data_thread.start()

    return app.exec()


def start():
    global delete_file_thread, save_frame_thread

    try:
        logger.info(f"{'-' * 30}deep_camera_run{'-' * 30}")
        path = _storage_root()

        try:
            if delete_file_thread is not None and delete_file_thread.isRunning():
                delete_file_thread.stop()
        except Exception as e:
            logger.error(f"stop deep_camera_delete_file_thread failed: {e}")

        try:
            if save_frame_thread is not None and save_frame_thread.isRunning():
                save_frame_thread.stop()
                save_frame_thread.requestInterruption()
                save_frame_thread.wait(2000)
        except Exception as e:
            logger.error(f"stop deep_camera_save_raw_frame failed: {e}")

        save_frame_thread = SaveRawFrameThread()
        save_frame_thread.start()

        delete_file_thread = Delete_file(
            path=path,
            start_time=global_setting.get_setting("start_time", time.time()),
        )
        delete_file_thread.start()
        check_setting_cameras_each_number()
    except Exception as e:
        logger.error(f"deep_camera start failed: {e}")


def restart(q):
    main(q)
    start()


def pause():
    logger.info(f"{'-' * 30}deep_camera_pause{'-' * 30}")


def stop():
    global delete_file_thread, camera_list, save_frame_thread

    logger.info(f"{'-' * 30}deep_camera_stop{'-' * 30}")
    logger.warning("stop_deep_camera_thread")

    queue = global_setting.get_setting("queue", None)

    for i, camera_struct in enumerate(camera_list):
        camera = camera_struct.get("camera")
        if camera is not None:
            try:
                camera.stop()
                camera.deleteLater()
                if queue:
                    queue.put(
                        ObjectQueueItem(
                            origin="main_deep_camera",
                            to="MainWindow_index",
                            title="stop_deep_camera_return",
                            data=f"deep camera {i} stopped",
                            time=time_util.get_format_from_time(time.time()),
                        )
                    )
            except Exception as e:
                logger.error(f"stop deep camera thread failed: {e}")
                if queue:
                    queue.put(
                        ObjectQueueItem(
                            origin="main_deep_camera",
                            to="MainWindow_index",
                            title="stop_deep_camera_return",
                            data=f"deep camera {i} stop failed: {e}",
                            time=time_util.get_format_from_time(time.time()),
                        )
                    )

        img_process = camera_struct.get("img_process")
        if img_process is not None:
            try:
                img_process.stop()
                img_process.deleteLater()
            except Exception as e:
                logger.error(f"stop deep camera img_process failed: {e}")

    if delete_file_thread is not None:
        try:
            delete_file_thread.stop()
            delete_file_thread.deleteLater()
            if queue:
                queue.put(
                    ObjectQueueItem(
                        origin="main_deep_camera",
                        to="MainWindow_index",
                        title="stop_deep_camera_return",
                        data="deep camera delete thread stopped",
                        time=time_util.get_format_from_time(time.time()),
                    )
                )
        except Exception as e:
            logger.error(f"stop deep_camera_delete_file_thread failed: {e}")
            if queue:
                queue.put(
                    ObjectQueueItem(
                        origin="main_deep_camera",
                        to="MainWindow_index",
                        title="stop_deep_camera_return",
                        data=f"deep camera delete thread stop failed: {e}",
                        time=time_util.get_format_from_time(time.time()),
                    )
                )

    if save_frame_thread is not None:
        try:
            save_frame_thread.stop()
            save_frame_thread.requestInterruption()
            save_frame_thread.wait(2000)
        except Exception as e:
            logger.error(f"stop deep_camera_save_raw_frame failed: {e}")
        save_frame_thread = None


if __name__ == "__main__":
    main()
