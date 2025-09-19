import threading

from PyQt6.QtCore import pyqtSignal
from loguru import logger

from Module.UFC_UGC_ZOS_Test.config_class.global_setting import global_setting
from Module.UFC_UGC_ZOS_Test.function.modbus.New_Mod_Bus import ModbusRTUMasterNew
from public.entity.queue.ObjectQueueItem import ObjectQueueItem


class Send_Message:
    def __init__(self,update_status_main_signal_gui_update=None,send_message=None,modbus=None):
        # 更新主线程状态栏消息信号
        self.update_status_main_signal_gui_update: pyqtSignal(str) =update_status_main_signal_gui_update
        self.send_message = send_message
        self.modbus: ModbusRTUMasterNew= global_setting.get_setting("modbus", None)
    def Send(self,resolve,reject):
        serial_lock = global_setting.get_setting('serial_lock', threading.Lock())
        with serial_lock:

            try:
                logger.info(self.send_message)
                response, response_hex, send_state = self.modbus.send_command(
                    slave_id=self.send_message['slave_id'],
                    function_code=self.send_message['function_code'],
                    data_hex_list=self.send_message['data']
                    , is_parse_response=False
                )
                # 响应报文是正确的，即发送状态时正确的 进行解析响应报文
                if send_state:
                    return_data, parser_message = self.modbus.parse_response(response=response,
                                                                             response_hex=response.hex(),
                                                                             send_state=True,
                                                                             slave_id=
                                                                             self.send_message['slave_id'],
                                                                             function_code=
                                                                             self.send_message['function_code'], )

                    # 把返回数据返回给源头
                    message_struct = ObjectQueueItem(to="UFC_UGC_ZOS_index", data=parser_message,
                                                     origin='UFC_UGC_ZOS_index_send_thread')

                    global_setting.get_setting("send_message_queue").put(message_struct)
                    logger.debug(f"UFC_UGC_ZOS_index_send_thread将响应报文的解析数据返回源头：{message_struct}")

            except Exception as e:
                self.modbus.close()
                logger.error(e)
                reject(e)
            finally:
                self.modbus.close()
                resolve({'data':return_data,"message":parser_message})
                pass

            pass
    def Send_no_promise(self):
        serial_lock = global_setting.get_setting('serial_lock', threading.Lock())
        with serial_lock:

            try:
                logger.info(self.send_message)

                response, response_hex, send_state = self.modbus.send_command(
                    slave_id=self.send_message['slave_id'],
                    function_code=self.send_message['function_code'],
                    data_hex_list=self.send_message['data']
                    , is_parse_response=False
                )
                # 响应报文是正确的，即发送状态时正确的 进行解析响应报文
                if send_state:
                    return_data, parser_message = self.modbus.parse_response(response=response,
                                                                             response_hex=response.hex(),
                                                                             send_state=True,
                                                                             slave_id=
                                                                             self.send_message['slave_id'],
                                                                             function_code=
                                                                             self.send_message['function_code'], )

                    # 把返回数据返回给源头
                    message_struct = ObjectQueueItem(to="UFC_UGC_ZOS_index", data=parser_message,
                                                     origin='UFC_UGC_ZOS_index_send_thread')
                    global_setting.get_setting("send_message_queue").put(message_struct)
                    logger.debug(f"UFC_UGC_ZOS_index_send_thread将响应报文的解析数据返回源头：{message_struct}")
                    pass

            except Exception as e:
                self.modbus.close()
                logger.error(e)
                return_data=None
                parser_message=None
            finally:
                self.modbus.close()
                return return_data, parser_message
                pass

        pass