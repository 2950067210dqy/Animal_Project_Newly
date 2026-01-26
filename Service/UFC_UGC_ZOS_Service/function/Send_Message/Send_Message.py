import threading
import time

from PyQt6.QtCore import pyqtSignal
from blinker.base import _PNamespaceSignal
from loguru import logger

from public.config_class.global_setting import global_setting
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Modbus.Modbus_Type import Modbus_Slave_Type
from public.function.Modbus.New_Mod_Bus import ModbusRTUMasterNew
from public.util.time_util import time_util


#logger = logger.bind(category="deep_camera_logger")
class Send_Message:
    def __init__(self,update_status_main_signal_gui_update=None,send_message=None,modbus=None):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: _PNamespaceSignal =update_status_main_signal_gui_update
        self.send_message = send_message
        self.modbus: ModbusRTUMasterNew= global_setting.get_setting("modbus", None)


    def Send(self,resolve,reject):
        serial_lock = global_setting.get_setting('serial_lock', threading.Lock())
        with serial_lock:
            return_data = None

            parser_message=None
            try:
                logger.info(self.send_message)
                start_time = time.time()
                response, response_hex, send_state,return_data = self.modbus.send_command(
                    slave_id=self.send_message['slave_id'],
                    function_code=self.send_message['function_code'],
                    data_hex_list=self.send_message['data']
                    , is_parse_response=False
                )
                end_time = time.time()
                if response is not None:
                    logger.critical(f"报文{response.hex()}发收时间：{(end_time - start_time):.3f}秒")
                else:
                    logger.critical(
                        f"报文{self.send_message['slave_id']}{self.send_message['function_code']}{self.send_message['data']},出现问题！：发收时间：{(end_time - start_time):.3f}秒")
                # 响应报文是正确的，即发送状态时正确的 进行解析响应报文
                if send_state:
                    # start_time = time.time()
                    return_data, parser_message = self.modbus.parse_response(response=response,
                                                                             response_hex=response.hex(),
                                                                             send_state=True,
                                                                             slave_id=
                                                                             self.send_message['slave_id'],
                                                                             function_code=
                                                                             self.send_message['function_code'], )

                    # end_time = time.time()
                    # logger.critical(f"报文{response.hex()}解析时间：{(end_time - start_time):.3f}秒")
                    #将解析数据返回给主菜单
                    self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | {parser_message}")
                    return_data['data'].append({'desc': '备注', 'value': None})
                else:
                    # 将错误信息返回给主菜单
                    if return_data :
                        for data in return_data['data']:
                            if data and data.get('desc') and data.get('desc')=='备注':
                                self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} |{data.get('value')}")
                                break
                    pass
                # 把返回数据返回给源头
                message_struct = ObjectQueueItem(to="UFC_UGC_ZOS_index",
                                                 data=parser_message,
                                                 origin='UFC_UGC_ZOS_index_send_thread')

                global_setting.get_setting("send_message_queue").put(message_struct)
                # logger.debug(f"UFC_UGC_ZOS_index_send_thread将响应报文的解析数据返回源头：{message_struct}")


            except Exception as e:

                logger.error(f"{e}")
                reject(e)
            finally:

                resolve({"data":return_data,"message":parser_message})
                pass

            pass
    def Send_no_promise(self):
        serial_lock = global_setting.get_setting('serial_lock', threading.Lock())
        with serial_lock:
            return_data = None
            parser_message = None
            try:
                logger.info(self.send_message)
                start_time = time.time()
                response, response_hex, send_state ,return_data = self.modbus.send_command(
                    slave_id=self.send_message['slave_id'],
                    function_code=self.send_message['function_code'],
                    data_hex_list=self.send_message['data']
                    , is_parse_response=False
                )
                end_time = time.time()
                if response is not None:
                    logger.critical(f"报文{response.hex()}发收时间：{(end_time - start_time):.3f}秒")
                else:
                    logger.critical(
                        f"报文{self.send_message['slave_id']}{self.send_message['function_code']}{self.send_message['data']},出现问题！：发收时间：{(end_time - start_time):.3f}秒")
                # 响应报文是正确的，即发送状态时正确的 进行解析响应报文
                if send_state:
                    # start_time = time.time()
                    return_data, parser_message = self.modbus.parse_response(response=response,
                                                                             response_hex=response.hex(),
                                                                             send_state=True,
                                                                             slave_id=
                                                                             self.send_message['slave_id'],
                                                                             function_code=
                                                                             self.send_message['function_code'], )

                    # end_time = time.time()
                    # logger.critical(f"报文{response.hex()}解析时间：{(end_time - start_time):.3f}秒")
                    # 将解析数据返回给主菜单
                    self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | {parser_message}")
                    return_data['data'].append({'desc': '备注', 'value': None})
                else:
                    # 将错误信息返回给主菜单
                    if return_data :
                        for data in return_data['data']:
                            if data and data.get('desc') and data.get('desc')=='备注':
                                self.update_status_main_signal_gui_update.send(f"{time_util.get_format_from_time(time.time())} | {data.get('value')}")
                                break
                # 把返回数据返回给源头
                message_struct = ObjectQueueItem(to="UFC_UGC_ZOS_index",
                                                 data=parser_message,
                                                 origin='UFC_UGC_ZOS_index_send_thread')
                global_setting.get_setting("send_message_queue").put(message_struct)
                # logger.debug(f"UFC_UGC_ZOS_index_send_thread将响应报文的解析数据返回源头：{message_struct}")
                pass

            except Exception as e:

                logger.error(f"{e}")
                return_data = None
                parser_message = None
            finally:

                return return_data, parser_message
                pass

        pass