import math
import multiprocessing
import os
import threading
import time
from typing import Any

from loguru import logger
from blinker import signal

from Service.UFC_UGC_ZOS_Service.function.gas_calibration.Gas_Carlibration import Zero_Carlibration, Range_Carlibration
from Service.UFC_UGC_ZOS_Service.function.gas_path_system.Gas_path_system import ZOS_gas_path_system, \
    UGC_gas_path_system, UFC_gas_path_system
from Service.UFC_UGC_ZOS_Service.function.gas_state_check.Gas_State_Check import UFC_Gas_State_Check
from public.config_class.global_setting import global_setting
from public.config_class.ini_parser import ini_parser
from public.entity.MyQThread import MyQThread, MyThread
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Timer.ProcederTimer import PeriodicTimer
from public.function.promise.AsyPromise import AsyPromise

# 过滤日志

# logger = logger.bind(category="deep_camera_logger")
read_queue_data_Thread_Lock = threading.Lock()
auto_wait_event = threading.Event()



class read_queue_data_Thread(MyQThread):
    def __init__(self, name):
        super().__init__(name)
        self.queue = None
        self.update_status_main_signal_gui_update = signal('update_status_main_signal_gui_update')
        pass

    def dosomething(self):
        if not self.queue.empty():
            message: ObjectQueueItem = self.queue.get()
            # message 结构{'to'发往哪个线程，'data'数据，'from'从哪来}

            if message is not None and isinstance(message, ObjectQueueItem) and message.to == 'UFC_UGC_ZOS_index':
                # logger.error(f"{self.name}_get_message:{message}")
                match message.title:
                    case '':
                        if self.update_status_main_signal_gui_update is not None:
                            with read_queue_data_Thread_Lock:
                                self.update_status_main_signal_gui_update.send(message.data)
                            pass
                    case _:
                        pass

            else:
                # 把消息放回去
                self.queue.put(message)


read_queue_data_thread = read_queue_data_Thread(name="UFC_UGC_ZOS_index_read_queue_data_thread")


class Monitor_start_state_Thread(MyThread):
    def __init__(self, name, UFC_gas_path_system_obj=None, UGC_gas_path_system_obj=None, ZOS_gas_path_system_obj=None,
                 update_start_state_signal=None):
        # UFC气路系统
        self.UFC_gas_path_system_obj: UFC_gas_path_system = UFC_gas_path_system_obj
        # UGC气路系统
        self.UGC_gas_path_system_obj: UGC_gas_path_system = UGC_gas_path_system_obj
        # ZOS气路系统
        self.ZOS_gas_path_system_obj: ZOS_gas_path_system = ZOS_gas_path_system_obj
        self.update_start_state_signal =update_start_state_signal

        super().__init__(name)

    def dosomething(self):
        logger.critical(f"UFC:{self.UFC_gas_path_system_obj.ufc_start_time_state},ZOS:{self.ZOS_gas_path_system_obj.zos_start_status}" )
        if self.UFC_gas_path_system_obj.ufc_start_time_state and self.ZOS_gas_path_system_obj.zos_start_status:

            self.update_start_state_signal.send()
        time.sleep(1)


class UFC_UGC_ZOS_index(MyQThread):
    def __init__(self):
        super().__init__(name="UFC_UGC_ZOS_index")
        self.ispause = False

        self.send_message = {
            'port': '',
            'data': '',
            'slave_id': 0,
            'function_code': 0,
            'timeout': 0
        }

        self.UFC_gas_path_system_obj: UFC_gas_path_system = None
        self.UGC_gas_path_system_obj: UGC_gas_path_system = None
        self.ZOS_gas_path_system_obj: ZOS_gas_path_system = None
        self.Zero_carlibration_obj: Zero_Carlibration = None
        self.Range_carlibration_obj: Range_Carlibration = None
        self.UFC_gas_state_check_obj: UFC_Gas_State_Check = None

        self.zos_start_timer: PeriodicTimer = None
        self.ufc_start_timer: PeriodicTimer = None
        self.calibration_start_timer: PeriodicTimer = None
        self.gas_state_check_timer: PeriodicTimer = None
        self.monitor_start_state_Thread: MyQThread = None


        self._init_data()
        self._init_function()

    def _init_data(self):
        config_file_path = os.getcwd() + "./" + "config/UFC_UGC_ZOS_Test.ini"
        configer = ini_parser(config_file_path).read()
        if len(configer) != 0:
            logger.info("UFC_UGC_ZOS_config配置文件读取成功。")
        else:
            logger.error("UFC_UGC_ZOS_config配置文件读取失败。")
        global_setting.set_setting("UFC_UGC_ZOS_config", configer)
        serial_lock = threading.Lock()
        global_setting.set_setting("serial_lock", serial_lock)

    def logger_info(self, text):

        if text and "\n" not in text:
            logger.debug(text)

    def _init_function(self):
        self.update_status_main_signal_gui_update = signal('update_status_main_signal_gui_update')
        self.update_status_main_signal_gui_update.connect(self.logger_info)
        self.update_start_state_signal = signal('update_start_state')
        self.update_start_state_signal.connect(self.update_start_state)

        self.start_signal = signal('start')
        self.start_signal.connect(self.start_btn_handle)
        self.run_signal = signal('run')
        self.run_signal.connect(self.run_btn_handle)
        self.carlibration_signal = signal('carlibration')
        self.carlibration_signal.connect(self.calibration_handle)
        self.gas_state_check_signal = signal('gas_state_check')
        self.gas_state_check_signal.connect(self.gas_state_check_handle)
        self.auto_finish_signal = signal('auto_finish')
        self.auto_finish_signal.connect(self.auto_finish_handle)

        self.UFC_gas_path_system_obj = UFC_gas_path_system()
        self.UGC_gas_path_system_obj = UGC_gas_path_system()
        self.ZOS_gas_path_system_obj = ZOS_gas_path_system()
        self.UFC_gas_path_system_obj.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.UGC_gas_path_system_obj.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.ZOS_gas_path_system_obj.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update

        self.Zero_carlibration_obj = Zero_Carlibration()
        self.Zero_carlibration_obj.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        self.Range_carlibration_obj = Range_Carlibration()
        self.Range_carlibration_obj.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update

        self.UFC_gas_state_check_obj = UFC_Gas_State_Check()
        self.UFC_gas_state_check_obj.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update

        global read_queue_data_thread
        read_queue_data_thread.update_status_main_signal_gui_update = self.update_status_main_signal_gui_update
        read_queue_data_thread.queue = global_setting.get_setting("send_message_queue")
        if read_queue_data_thread is not None and not read_queue_data_thread.isRunning():
            read_queue_data_thread.start()

    def auto_finish_handle(self):
        pass

    def update_start_state(self, sender, **kwargs):

        self.monitor_start_state_Thread.stop()
        self.close_timers()

        global auto_wait_event
        auto_wait_event.set()
        auto_wait_event.clear()

    def start_btn_handle(self):
        p = AsyPromise(self.ZOS_gas_path_system_obj.start).then(
            AsyPromise(
                self.UFC_gas_path_system_obj.start,
            ).then(
                AsyPromise(self.UGC_gas_path_system_obj.start).then(
                    AsyPromise(self.set_start_timers)
                ).catch(lambda e: logger.error(f"{e}"))
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))

        if self.monitor_start_state_Thread is None:
            self.monitor_start_state_Thread = Monitor_start_state_Thread(
                name="Monitor_start_state_Thread",
                UFC_gas_path_system_obj=self.UFC_gas_path_system_obj,
                UGC_gas_path_system_obj=self.UGC_gas_path_system_obj,
                ZOS_gas_path_system_obj=self.ZOS_gas_path_system_obj,
                update_start_state_signal=self.update_start_state_signal
            )
        self.monitor_start_state_Thread.start()



        return p

    def run_btn_handle(self):

        global auto_wait_event
        # 测试timeout
        auto_wait_event.wait()
        #每轮运行发送报文数量 赋值0
        global_setting.set_setting("messages_sent_epoch_for_running", 0)
        global_setting.set_setting("start_time_messages_sent_epoch_for_running", time.time())
        #通知鼠笼传感器解除阻塞开始运行
        wait_UFC_UGC_ZOS_start_event=global_setting.get_setting("wait_UFC_UGC_ZOS_start_event")
        wait_UFC_UGC_ZOS_start_event.set()
        wait_UFC_UGC_ZOS_start_event.clear()  # 重置事件
        p = AsyPromise(self.UFC_gas_path_system_obj.run).then(
            lambda v: AsyPromise(
                self.UGC_gas_path_system_obj.run,
            ).then(
                lambda v2: AsyPromise(self.ZOS_gas_path_system_obj.run)
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))


        return p

    def stop_btn_handle(self):
        if self.monitor_start_state_Thread is not None:
            self.monitor_start_state_Thread.stop()
        if self.UFC_gas_path_system_obj is not None and self.UFC_gas_path_system_obj.ufc_gas_path_system_run_thread is not None:
            self.UFC_gas_path_system_obj.ufc_gas_path_system_run_thread.stop()
        if self.UGC_gas_path_system_obj is not None and self.UGC_gas_path_system_obj.ugc_gas_path_system_run_thread is not None:
            self.UGC_gas_path_system_obj.ugc_gas_path_system_run_thread.stop()
        if self.ZOS_gas_path_system_obj is not None and self.ZOS_gas_path_system_obj.zos_gas_path_system_run_thread is not None:
            self.ZOS_gas_path_system_obj.zos_gas_path_system_run_thread.stop()
        self.close_timers()
        p = AsyPromise(self.UGC_gas_path_system_obj.stop).then(
            lambda v: AsyPromise(
                self.UFC_gas_path_system_obj.stop,
            ).then(
                lambda v2: AsyPromise(self.ZOS_gas_path_system_obj.stop)
            ).catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))
        return p

    def calibration_handle(self):
        self.set_calibration_start_timer()
        p = AsyPromise(lambda r,e:r()).then().catch(lambda e: logger.error(f"{e}"))
        return p
    def carlibation(self):
        p = AsyPromise(self.Zero_carlibration_obj.calibrate).then(
            lambda v: AsyPromise(
                self.Range_carlibration_obj.calibrate
            ).then().catch(lambda e: logger.error(f"{e}"))
        ).catch(lambda e: logger.error(f"{e}"))
        return p
        # # 测试   不需要校0标定
        # p = AsyPromise(
        #     self.Range_carlibration_obj.calibrate
        # ).then().catch(lambda e: logger.error(f"{e}"))
        # return p
        # p = AsyPromise(lambda r, e: r()).then().catch(lambda e: logger.error(f"{e}"))
        # return p

    def gas_state_check_handle(self):
        self.set_gas_state_check_timer()
        p = AsyPromise(lambda r,e:r()).then().catch(lambda e: logger.error(f"{e}"))
        return p
    def gas_state_check(self):
        p = AsyPromise(self.UFC_gas_state_check_obj.state_check).then(
        ).catch(lambda e: logger.error(f"{e}"))
        return p
        # p = AsyPromise(lambda r, e: r()).then().catch(lambda e: logger.error(f"{e}"))
        # return p



    def dosomething(self):
        self.start_btn_handle().then(
            self.run_btn_handle().then(
                self.calibration_handle().then(
                    self.gas_state_check_handle().then(
                        self.stop()
                    )
                )
            )
        )



    def pause(self):
        if self.UFC_gas_path_system_obj is not None and self.UFC_gas_path_system_obj.ufc_gas_path_system_run_thread is not None:
            self.UFC_gas_path_system_obj.ufc_gas_path_system_run_thread.pause()
        if self.UGC_gas_path_system_obj is not None and self.UGC_gas_path_system_obj.ugc_gas_path_system_run_thread is not None:
            self.UGC_gas_path_system_obj.ugc_gas_path_system_run_thread.pause()
        if self.ZOS_gas_path_system_obj is not None and self.ZOS_gas_path_system_obj.zos_gas_path_system_run_thread is not None:
            self.ZOS_gas_path_system_obj.zos_gas_path_system_run_thread.pause()

        if self.monitor_start_state_Thread is not None:
            self.monitor_start_state_Thread.pause()
        self.pause_timers()
        self.ispause = True

    def resume(self):
        if self.UFC_gas_path_system_obj is not None and self.UFC_gas_path_system_obj.ufc_gas_path_system_run_thread is not None:
            self.UFC_gas_path_system_obj.ufc_gas_path_system_run_thread.resume()
        if self.UGC_gas_path_system_obj is not None and self.UGC_gas_path_system_obj.ugc_gas_path_system_run_thread is not None:
            self.UGC_gas_path_system_obj.ugc_gas_path_system_run_thread.resume()
        if self.ZOS_gas_path_system_obj is not None and self.ZOS_gas_path_system_obj.zos_gas_path_system_run_thread is not None:
            self.ZOS_gas_path_system_obj.zos_gas_path_system_run_thread.resume()

        if self.monitor_start_state_Thread is not None:
            self.monitor_start_state_Thread.resume()
        self.resume_timers()
        self.ispause = False

    def set_start_timers(self, resolve, reject):

        self.set_zos_start_timer()
        # self.set_ufc_start_timer()
        resolve()

    def pause_timers(self):
        if self.zos_start_timer is not None and self.zos_start_timer.is_active():
            self.zos_start_timer.pause()
        if self.ufc_start_timer is not None and self.ufc_start_timer.is_active():
            self.ufc_start_timer.pause()
        if self.calibration_start_timer is not None and self.calibration_start_timer.is_active():
            self.calibration_start_timer.pause()
        if self.gas_state_check_timer is not None and self.gas_state_check_timer.is_active():
            self.gas_state_check_timer.pause()

    def resume_timers(self):
        if self.zos_start_timer is not None:
            self.zos_start_timer.resume()
        if self.ufc_start_timer is not None:
            self.ufc_start_timer.resume()
        if self.calibration_start_timer is not None:
            self.calibration_start_timer.resume()
        if self.gas_state_check_timer is not None:
            self.gas_state_check_timer.resume()

    def close_timers(self):
        if self.zos_start_timer is not None and (self.zos_start_timer.is_active() or self.zos_start_timer._is_paused):
            self.zos_start_timer.stop()
        if self.ufc_start_timer is not None and (self.ufc_start_timer.is_active() or self.ufc_start_timer._is_paused):
            self.ufc_start_timer.stop()
        if self.calibration_start_timer is not None and (
                self.calibration_start_timer.is_active() or self.calibration_start_timer._is_paused):
            self.calibration_start_timer.stop()
        if self.gas_state_check_timer is not None and (
                self.gas_state_check_timer.is_active() or self.gas_state_check_timer._is_paused):
            self.gas_state_check_timer.stop()

    def set_gas_state_check_timer(self):
        self.gas_state_check_timer = PeriodicTimer(
            interval_ms=float(
                global_setting.get_setting('UFC_UGC_ZOS_config')['Gas_State_Check']['start_time_delay']) * 1000,
            max_duration_ms=None,
            task=None,
            run_in_thread=True,
            run_immediately=True
        )
        self.gas_state_check_timer.set_task(self.gas_state_check)
        self.gas_state_check_timer.start()

    def set_calibration_start_timer(self):
        self.calibration_start_timer = PeriodicTimer(
            interval_ms=float(
                global_setting.get_setting('UFC_UGC_ZOS_config')['Calibration']['start_time_delay']) * 1000,
            max_duration_ms=None,
            task=None,
            run_in_thread=True,
            run_immediately=True
        )
        self.calibration_start_timer.set_task(self.carlibation)
        self.calibration_start_timer.start()

    def set_zos_start_timer(self):
        self.zos_start_timer = PeriodicTimer(
            interval_ms=float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['start_time_delay']) * 1000,
            max_duration_ms=float(global_setting.get_setting('UFC_UGC_ZOS_config')['ZOS']['start_time']) * 1000,
            task=None,
            run_in_thread=True,
            run_immediately=True
        )
        self.zos_start_timer.set_task(self.ZOS_gas_path_system_obj.zos_start_timer_task)
        self.zos_start_timer.start()

    def set_ufc_start_timer(self):
        try:
            self.ufc_start_timer = PeriodicTimer(
                interval_ms=float(
                    global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['start_wait_time_delay']) * 1000,
                max_duration_ms=float(
                    global_setting.get_setting('UFC_UGC_ZOS_config')['UFC']['start_wait_time']) * 1000,
                task=None,
                run_in_thread=True,
                timer_finished_callback=self.UFC_gas_path_system_obj.check_ufc_start_time_state,
                run_immediately=True
            )
        except Exception as e:
            logger.error(e)
        self.ufc_start_timer.set_task(self.UFC_gas_path_system_obj.ufc_start_timer_task)
        self.ufc_start_timer.start()