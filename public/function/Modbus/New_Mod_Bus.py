import copy
from datetime import datetime
import serial
import struct
import time
import threading
from typing import Optional, Tuple, List, Union
from contextlib import contextmanager
from loguru import logger
from public.config_class.global_setting import global_setting
from public.entity.enum.Public_Enum import ModBusResponseCode
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Modbus.Modbus_Response_Parser import Modbus_Response_Parser, get_module_name
from public.function.Modbus.Modbus_Type import Modbus_Slave_Type, Modbus_Slave_Ids
from public.util.time_util import time_util


class ModbusRTUMasterNew:
    """
    优化后的Modbus RTU通信类
    修复了多线程并发、串口占用和响应数据不一致问题
    """

    def __init__(self, port='COM1', baudrate=115200, timeout=1, origin=None):
        """初始化Modbus RTU Master"""
        # 基本参数
        self.sport = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.origin = origin

        # 连接管理 - 分离连接锁和操作锁
        self.ser: Optional[serial.Serial] = None
        self.is_connected = False

        # 使用两个锁：连接锁和操作锁，避免死锁
        self._connection_lock = threading.RLock()  # 连接管理锁
        self._operation_lock = threading.RLock()  # 操作锁（发送接收）

        # 连接状态标志
        self._connecting = False
        self._last_error_time = 0
        self._error_cooldown = 1.0  # 错误冷却时间

        # 响应读取采用非阻塞轮询，避免串口驱动在 read/reset 上无限占住采集线程。
        self._response_poll_interval = 0.005
        self._response_inter_byte_timeout = 0.02

        # 自动重连参数
        self.auto_reconnect = True
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 0.1

        # 性能优化缓存
        self._delay_cache = None
        self._last_delay_check = 0
        self._module_name_cache = {}
        self._table_name_cache = {}
        self._crc_table = self._build_crc_table()

    def _build_crc_table(self):
        """构建CRC查找表，提高计算效率"""
        table = []
        for i in range(256):
            crc = i
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
            table.append(crc)
        return table

    @contextmanager
    def _safe_operation_lock(self, timeout=3.0):
        """安全的操作锁管理器 - 缩短超时时间"""
        acquired = False
        try:
            acquired = self._operation_lock.acquire(timeout=timeout)
            if not acquired:
                raise TimeoutError(f"获取操作锁超时({timeout}秒)")
            yield
        finally:
            if acquired:
                self._operation_lock.release()

    @contextmanager
    def _safe_connection_lock(self, timeout=2.0):
        """安全的连接锁管理器 - 更短的超时时间"""
        acquired = False
        try:
            acquired = self._connection_lock.acquire(timeout=timeout)
            if not acquired:
                raise TimeoutError(f"获取连接锁超时({timeout}秒)")
            yield
        finally:
            if acquired:
                self._connection_lock.release()

    def _is_connection_healthy(self) -> bool:
        """检查连接健康状态 - 不加锁的快速检查"""
        try:
            if not self.ser or not self.ser.is_open:
                return False
            # 快速检查串口状态
            _ = self.ser.in_waiting
            return True
        except:
            return False

    def connect(self) -> bool:
        """建立串口连接 - 优化重连逻辑"""
        # 快速检查：如果连接正常，直接返回
        if self.is_connected and self._is_connection_healthy():
            return True

        try:
            with self._safe_connection_lock(timeout=2.0):
                # 双重检查：获得锁后再次检查
                if self.is_connected and self._is_connection_healthy():
                    return True

                # 防止并发重连
                if self._connecting:
                    return False

                self._connecting = True

                try:
                    # 关闭现有连接
                    self._close_connection_unsafe()

                    # 错误冷却
                    current_time = time.time()
                    if current_time - self._last_error_time < self._error_cooldown:
                        time.sleep(self._error_cooldown - (current_time - self._last_error_time))

                    logger.info(f"正在连接串口 {self.sport}...")

                    # 建立新连接
                    self.ser = serial.Serial(
                        port=self.sport,
                        baudrate=self.baudrate,
                        bytesize=8,
                        parity='N',
                        stopbits=1,
                        timeout=self.timeout,
                        write_timeout=self.timeout  # 添加写超时
                    )

                    self.is_connected = True
                    self._send_status_message("连接成功")
                    logger.info(f"{self.sport}-连接成功")
                    return True

                except Exception as e:
                    self.is_connected = False
                    self._last_error_time = time.time()
                    error_msg = f"连接失败: {e}"
                    self._send_status_message(error_msg)
                    logger.error(f"{self.sport}-{error_msg}")
                    return False
                finally:
                    self._connecting = False

        except TimeoutError as e:
            logger.error(f"{self.sport}-获取连接锁超时: {e}")
            return False
        except Exception as e:
            logger.error(f"{self.sport}-连接异常: {e}")
            return False

    def _close_connection_unsafe(self):
        """内部方法：关闭连接（不加锁版本）"""
        try:
            if self.ser:
                if self.ser.is_open:
                    self.ser.close()
        except:
            pass
        finally:
            self.ser = None
            self.is_connected = False

    def close(self):
        """公共方法：关闭连接"""
        try:
            with self._safe_connection_lock():
                self._close_connection_unsafe()
                logger.info(f"{self.sport}-连接已关闭")
        except Exception as e:
            logger.error(f"{self.sport}-关闭连接时出错: {e}")

    def _ensure_connection(self) -> bool:
        """确保连接可用，支持自动重连 - 优化版本"""
        if self.is_connected and self._is_connection_healthy():
            return True

        if not self.auto_reconnect:
            return False

        # 尝试重连
        for attempt in range(self.max_reconnect_attempts):
            try:
                logger.info(f"尝试重连 {attempt + 1}/{self.max_reconnect_attempts}")

                if attempt > 0:
                    time.sleep(self.reconnect_delay * attempt)  # 递增延迟

                # 使用connect方法重连
                if self.connect():
                    logger.info(f"{self.sport}-重连成功")
                    return True

            except Exception as e:
                logger.error(f"{self.origin}|{self.sport}-重连尝试 {attempt + 1} 失败: {e}")

        logger.error(f"{self.sport}-重连失败，已达到最大重试次数")
        return False

    def _drain_input_nonblocking(self):
        """丢弃上一条异常报文的残留字节，不调用可能阻塞的驱动清缓冲接口。"""
        if not self.ser or not self.ser.is_open:
            return

        original_timeout = self.ser.timeout
        discarded = 0
        try:
            self.ser.timeout = 0
            for _ in range(4):
                pending = self.ser.read(256)
                if not pending:
                    break
                discarded += len(pending)
            if discarded:
                logger.warning(
                    f"{self.sport}-丢弃上一条报文残留数据 {discarded} 字节"
                )
        except Exception as exc:
            logger.warning(f"{self.sport}-非阻塞清理串口输入缓冲失败: {exc}")
        finally:
            try:
                self.ser.timeout = original_timeout
            except Exception:
                pass

    @staticmethod
    def _response_length(response_prefix: bytes) -> Optional[int]:
        """根据 Modbus 响应头推断完整帧长度。"""
        if len(response_prefix) < 3:
            return None

        function_code = response_prefix[1]
        if function_code & 0x80:
            return 5
        if function_code in (1, 2, 3, 4):
            return 3 + response_prefix[2] + 2
        if function_code in (5, 6, 15, 16):
            return 8
        return None

    def _read_response_until_deadline(self) -> bytes:
        """以真正的截止时间读取响应，避免 pyserial read 长时间卡住。"""
        if not self.ser or not self.ser.is_open:
            return b''

        deadline = time.monotonic() + max(float(self.timeout), 1.0)
        original_timeout = self.ser.timeout
        response = bytearray()
        last_byte_time = None
        try:
            # timeout=0 使每次 read 立即返回，截止时间由本方法统一控制。
            self.ser.timeout = 0
            while time.monotonic() < deadline:
                chunk = self.ser.read(256)
                now = time.monotonic()
                if chunk:
                    response.extend(chunk)
                    last_byte_time = now
                    expected_length = self._response_length(response)
                    if expected_length is not None and len(response) >= expected_length:
                        return bytes(response[:expected_length])
                    if len(response) >= 256:
                        return bytes(response)
                elif (
                    response
                    and last_byte_time is not None
                    and now - last_byte_time >= self._response_inter_byte_timeout
                ):
                    # 已收到部分帧且总线保持静默，交给 CRC/长度校验统一判定。
                    return bytes(response)
                else:
                    time.sleep(self._response_poll_interval)
            return bytes(response)
        finally:
            try:
                self.ser.timeout = original_timeout
            except Exception:
                pass

    def _recover_serial_connection(self, reason: str):
        """将异常串口置为不可用，下一次请求通过统一重连流程恢复。"""
        logger.warning(f"{self.sport}-串口收发异常，准备重连: {reason}")
        self._close_connection_unsafe()

    def calculate_crc(self, data: bytes) -> bytes:
        """计算Modbus RTU CRC-16，使用查找表提高效率"""
        crc = 0xFFFF
        for byte in data:
            tbl_idx = (crc ^ byte) & 0xFF
            crc = ((crc >> 8) ^ self._crc_table[tbl_idx]) & 0xFFFF
        return struct.pack('<H', crc)

    def build_frame(self, slave_id: Union[str, int], function_code: Union[str, int],
                    data_hex_list: List[str]) -> Optional[bytes]:
        """构造完整 Modbus RTU 报文（包含CRC）"""
        try:
            # 统一转换为整数
            if isinstance(slave_id, str):
                slave_id = int(slave_id, 16)
            if isinstance(function_code, str):
                function_code = int(function_code, 16)

            data_bytes = [int(x, 16) for x in data_hex_list]

            # 组装帧
            frame = struct.pack('>B B', slave_id, function_code) + struct.pack('>' + 'B' * len(data_bytes), *data_bytes)
            crc = self.calculate_crc(frame)

            logger.debug(f"构造发送报文frame: {frame.hex()}|crc: {crc.hex()}")
            return frame + crc

        except Exception as e:
            error_msg = f"构造报文出错: {e}"
            self._send_status_message(error_msg)
            logger.error(f"{time_util.get_format_from_time(time.time())}-{self.sport}-{error_msg}")
            return None

    def get_table_name(self, slave_id):
        """获取表名 - 缓存优化版本"""
        if slave_id in self._table_name_cache:
            return self._table_name_cache[slave_id]

        try:
            slave_id_int = int(slave_id, 16)
            table_name = ""

            if slave_id_int == Modbus_Slave_Ids.ENM.value['int']:
                table_name = next(iter(Modbus_Slave_Ids.ENM.value['table'].keys()))
            elif slave_id_int > 16:
                # 鼠笼内传感器
                for type_item in Modbus_Slave_Type.Each_Mouse_Cage.value:
                    if type_item.value['int'] == (slave_id_int % 16):
                        table_name = next(iter(type_item.value['table'].keys()))
                        break
            else:
                # 非鼠笼内传感器
                for type_item in Modbus_Slave_Type.Not_Each_Mouse_Cage.value:
                    if type_item.value['int'] == (slave_id_int % 16):
                        table_name = next(iter(type_item.value['table'].keys()))
                        break

            # 缓存结果
            self._table_name_cache[slave_id] = table_name
            return table_name
        except:
            return ""

    def _get_cached_module_name(self, slave_id):
        """缓存模块名称"""
        if slave_id not in self._module_name_cache:
            self._module_name_cache[slave_id] = get_module_name(slave_id)
        return self._module_name_cache[slave_id]

    def _get_cached_delay(self):
        """缓存延迟配置，避免频繁访问全局设置"""
        current_time = time.time()
        if self._delay_cache is None or (current_time - self._last_delay_check) > 5:
            try:
                self._delay_cache = float(global_setting.get_setting('monitor_data')['SEND']['get_response_delay'])
                self._last_delay_check = current_time
            except:
                self._delay_cache = 0.05  # 减少默认延迟
        return self._delay_cache

    def _prepare_return_data(self, slave_id, function_code):
        """准备返回数据结构"""
        slave_id_int = int(slave_id, 16) if isinstance(slave_id, str) else slave_id

        return {
            'module_name': self._get_cached_module_name(slave_id),
            'table_name': self.get_table_name(slave_id),
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mouse_cage_number': slave_id_int // 16 if slave_id_int > 16 else 0,
            'data': [],
            'slave_id': slave_id,
            'function_code': function_code,
            'response_state':False,
            "response_code":ModBusResponseCode.ERROR,
            'response_msg':""
        }

    def send_command(self, slave_id: Union[str, int], function_code: Union[str, int],
                     data_hex_list: List[str], is_parse_response: bool = True) -> Tuple[
        Optional[bytes], Optional[str], bool, dict]:
        """发送Modbus RTU命令并获取响应（主要方法） - 优化版本"""

        # 准备返回数据
        return_data = self._prepare_return_data(slave_id, function_code)

        try:
            # 使用操作锁，而不是连接锁
            with self._safe_operation_lock(timeout= 5.0):

                # 每轮运行报文加1
                global_setting.set_setting("messages_sent_epoch_for_running",
                                           global_setting.get_setting("messages_sent_epoch_for_running", 0) + 1)

                # 确保连接可用（这里会使用连接锁）
                if not self._ensure_connection():
                    error_msg = f"{self.sport}-{slave_id, function_code, data_hex_list}-无法建立连接"
                    return_data['data'].append({'desc': '备注', 'value': error_msg})
                    logger.error(error_msg)
                    return None, None, False, return_data

                # 构造报文
                frame = self.build_frame(slave_id, function_code, data_hex_list)
                if frame is None:
                    return_data['data'].append({'desc': '备注', 'value': "构造发送报文 frame 为空"})
                    return None, None, False, return_data

                # 发送和接收（在同一个锁内完成）
                return self._send_and_receive(frame, slave_id, function_code, is_parse_response, return_data)

        except TimeoutError as e:
            error_msg = f"{self.sport}-操作超时: {e}"
            logger.error(error_msg)
            return_data['data'].append({'desc': '备注', 'value': error_msg})
            return_data['response_msg']=error_msg
            return_data['response_code'] =ModBusResponseCode.OPERATOR_TIMEOUT
            return_data['response_state'] = False
            return None, None, False, return_data
        except Exception as e:
            error_msg = f"串口通信异常: {e}"
            self._send_status_message(f"❗ {error_msg}")
            logger.error(f"{time_util.get_format_from_time(time.time())}-{self.sport}-❗ {error_msg}")
            return_data['data'].append({'desc': '备注', 'value': error_msg})

            # 通信异常时标记连接为不可用，但不立即关闭
            self.is_connected = False
            return None, None, False, return_data

    def _send_and_receive(self, frame: bytes, slave_id: Union[str, int],
                          function_code: Union[str, int], is_parse_response: bool,
                          return_data: dict) -> Tuple[Optional[bytes], Optional[str], bool, dict]:
        """发送报文并接收响应 - 原子操作"""
        try:
            # 不使用 reset_input/output_buffer：部分 USB 串口驱动在该调用处会阻塞。
            # 只用非阻塞读取清理上一条异常报文的残留字节。
            self._drain_input_nonblocking()

            # 发送数据
            self._send_status_message(f"发送数据帧{frame.hex()}")
            logger.info(f"{time_util.get_format_from_time(time.time())}-{self.sport}-发送数据帧{frame.hex()}")

            self.ser.write(frame)
            # write 已受 write_timeout 约束，不再额外调用可能阻塞的 flush。
            response = self._read_response_until_deadline()

            if not response:
                self._recover_serial_connection(
                    f"报文{frame.hex()}在{max(float(self.timeout), 1.0):.1f}秒内未收到响应"
                )

            # 验证响应
            return self._validate_response(response, slave_id, function_code,
                                           is_parse_response, frame, return_data)

        except Exception as e:
            error_msg = f"发送接收异常: {e}"
            logger.error(f"{self.sport}-{error_msg}")
            self._recover_serial_connection(error_msg)
            return_data['data'].append({'desc': '备注', 'value': error_msg})
            return_data['response_msg'] = error_msg
            return_data['response_code'] = ModBusResponseCode.SEND_RECEIVE_EXCEPTION
            return_data['response_state'] = False
            return None, None, False, return_data

    def _validate_response(self, response_bytes: bytes, slave_id: Union[str, int],
                           function_code: Union[str, int], is_parse_response: bool,
                           send_frame: bytes, return_data: dict) -> Tuple[Optional[bytes], Optional[str], bool, dict]:
        """验证响应数据 - 避免数据修改问题"""

        # 立即创建响应的不可变副本，避免数据竞争
        response = copy.deepcopy(response_bytes)  # 创建新的bytes对象

        # 超时判断
        if not response:
            error_msg = f"请求报文{send_frame.hex()}-Time OUT1-未获取到响应数据"
            self._log_error(error_msg, return_data)
            return_data['response_msg'] = error_msg
            return_data['response_code'] = ModBusResponseCode.VALIDATE_RESP_TIMEOUT1
            return_data['response_state'] = False
            return None, None, False, return_data

        # 数据长度检查
        if len(response) < 5:
            error_msg = f"请求报文{send_frame.hex()}-响应报文{response.hex()}-Time OUT2-返回数据位数错误"
            self._log_error(error_msg, return_data)
            return_data['response_msg'] = error_msg
            return_data['response_code'] = ModBusResponseCode.VALIDATE_RESP_TIMEOUT2
            return_data['response_state'] = False
            return response, response.hex(), False, return_data

        # CRC校验
        data_part = response[:-2]
        crc_received = response[-2:]
        crc_expected = self.calculate_crc(data_part)

        if crc_received != crc_expected:
            error_msg = f"请求报文{send_frame.hex()}-响应报文{response.hex()}-Time OUT3-数据错误，CRC验证失败"
            self._log_error(error_msg, return_data)
            return_data['response_msg'] = error_msg
            return_data['response_code'] = ModBusResponseCode.VALIDATE_RESP_TIMEOUT3
            return_data['response_state'] = False
            return response, response.hex(), False, return_data

        # 检查异常响应
        function_code_response = response[1]
        if function_code_response & 0x80:
            exception_code = response[2]
            error_msg = f"请求报文{send_frame.hex()}-响应报文{response.hex()}-异常：功能码=0x{function_code_response:02X}, 异常码=0x{exception_code:02X}"
            self._log_error(error_msg, return_data)
            return_data['response_msg'] = error_msg
            return_data['response_code'] = ModBusResponseCode.VALIDATE_RESP_FUNC_CODE_EXCEPTION
            return_data['response_state'] = False
            return response, response.hex(), False, return_data

        # 响应正常
        success_msg = f"请求报文{send_frame.hex()}-响应报文{response.hex()}-CRC校验通过，正常响应"
        self._send_status_message(success_msg)
        logger.info(f"{time_util.get_format_from_time(time.time())}-{self.sport}-{success_msg}")
        return_data['response_msg'] = success_msg
        return_data['response_code'] = ModBusResponseCode.SUCCESS
        return_data['response_state'] = True
        # 解析响应
        if is_parse_response:
            self.parse_response(response, response.hex(), True, slave_id, function_code)

        # 等待响应
        delay = self._get_cached_delay()
        if delay > 0:
            time.sleep(delay)

        return response, response.hex(), True, return_data

    def _log_error(self, error_msg: str, return_data: dict):
        """统一的错误日志记录"""
        full_msg = f"{time_util.get_format_from_time(time.time())}-{self.sport}-{error_msg}"
        self._send_status_message(full_msg)
        logger.error(full_msg)
        return_data['data'].append({'desc': '备注', 'value': error_msg})

    def _send_status_message(self, message: str):
        """发送状态消息到队列"""
        return  # 根据需要启用
        try:
            if self.origin is not None:
                message_struct = ObjectQueueItem(
                    to=self.origin,
                    data=f"{time_util.get_format_from_time(time.time())}-{self.sport}-{message}",
                    origin='main_monitor_data'
                )
                global_setting.get_setting("send_message_queue").put(message_struct)
        except Exception as e:
            logger.error(f"发送状态消息失败: {e}")

    def parse_response(self, response: bytes, response_hex: str, send_state: bool,
                       slave_id: Union[str, int], function_code: Union[str, int]):
        """解析响应报文"""
        logger.debug(f"开始解析报文: slave_id={response[0]:x}, func_code={response[1]}")

        if send_state:
            try:
                modbus_response_parser = Modbus_Response_Parser(
                    slave_id=f"{response[0]:x}",
                    function_code=response[1],
                    response=response,
                    response_hex=response_hex
                )
                return modbus_response_parser.parser()
            except Exception as e:
                logger.error(f"解析响应报文失败: {e}")
                return None, None
        return None, None

    def is_alive(self) -> bool:
        """检查连接是否正常"""
        return self.is_connected and self._is_connection_healthy()

    def __enter__(self):
        """支持with语句"""
        if self.connect():
            return self
        else:
            raise ConnectionError(f"无法连接到串口 {self.sport}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持with语句"""
        self.close()

    def __del__(self):
        """析构函数，确保资源清理"""
        try:
            self.close()
        except:
            pass
