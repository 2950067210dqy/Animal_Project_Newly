from datetime import datetime
import serial
import struct
import time
import threading
from typing import Optional, Tuple, List, Union
from contextlib import contextmanager

from loguru import logger

from public.config_class.global_setting import global_setting
from public.entity.queue.ObjectQueueItem import ObjectQueueItem
from public.function.Modbus.Modbus_Response_Parser import Modbus_Response_Parser, get_module_name
from public.function.Modbus.Modbus_Type import Modbus_Slave_Type
from public.util.time_util import time_util

class ModbusRTUMasterNew:
    """
    可随时随处调用的Modbus RTU通信类
    - 支持连接复用、自动重连、线程安全（改进版）
    改动要点：
    - 使用一个短超时的 reentrant lock 来保护串口读写和状态变更
    - 避免在锁内做长时间阻塞的重连循环；将重连尝试拆分为最小单位并在失败时释放锁等待
    - 在打开串口失败时释放资源并记录更清晰的日志
    - 串口读写均使用 lock，且读写超时可控
    """

    def __init__(self, port='COM1', baudrate=115200, timeout=1, origin=None):
        # 基本参数
        self.sport = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.origin = origin

        # 连接管理
        self.ser: Optional[serial.Serial] = None
        self.is_connected = False

        # 使用RLock支持重入，避免死锁。缩短单次等待，减少“获取锁超时”风险。
        self._lock = threading.RLock()
        self._lock_acquire_timeout = 3.0  # 单次获取锁最大等待（秒）

        # 自动重连参数
        self.auto_reconnect = True
        self.max_reconnect_attempts = 3
        self.reconnect_interval = 0.5

        # 用于防止并发重连：只有一个线程允许做连接/重连操作
        self._connect_lock = threading.Lock()
        # 记录最近一次连接尝试时间，防止短时间重复频繁打开串口
        self._last_connect_attempt = 0.0
        self._connect_cooldown = 0.2

    @contextmanager
    def _safe_lock(self):
        """安全的锁管理器：尝试获取锁，超时就抛出 TimeoutError"""
        acquired = False
        try:
            acquired = self._lock.acquire(timeout=self._lock_acquire_timeout)
            if not acquired:
                raise TimeoutError("获取锁超时")
            yield
        finally:
            if acquired:
                try:
                    self._lock.release()
                except RuntimeError:
                    # 已经释放或未获取：忽略
                    pass

    def _open_serial(self) -> None:
        """内部：实际打开串口（不加上外层 RLock，需调用方在合适时机获取锁或 connect_lock）"""
        # pyserial 在打开端口时如果被占用会 raise PermissionError
        # 将异常抛出去由调用方处理
        self.ser = serial.Serial(
            port=self.sport,
            baudrate=self.baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=self.timeout
        )
        self.is_connected = True

    def connect(self) -> bool:
        """建立串口连接（线程安全）"""
        now = time.time()
        # 限制太频繁的调用
        if now - self._last_connect_attempt < self._connect_cooldown:
            # 如果刚刚尝试过，直接返回当前状态
            return self.is_connected and self.ser and self.ser.is_open

        self._last_connect_attempt = now

        # 使用 connect_lock 防止多个线程同时创建 serial 对象导致竞争/PermissionError
        if not self._connect_lock.acquire(blocking=True, timeout=5):
            logger.error(f"{self.sport}-获取连接锁超时")
            return False

        try:
            with self._safe_lock():
                if self.is_connected and self.ser and self.ser.is_open:
                    return True

                # 先关闭旧的（不在外层异常情况下）
                self._close_connection_unsafe()

                logger.info(f"正在连接串口 {self.sport}...")
                try:
                    self._open_serial()
                except Exception as e:
                    # 打开失败，不要保持 ser 为部分状态
                    self._close_connection_unsafe()
                    self._send_status_message(f"连接失败: {e}")
                    logger.error(f"{self.sport}-连接失败: {e}")
                    return False

                self._send_status_message(f"连接成功")
                logger.info(f"{self.sport}-连接成功")
                return True

        except TimeoutError as e:
            logger.error(f"{self.sport}-获取锁超时: {e}")
            return False
        finally:
            try:
                self._connect_lock.release()
            except Exception:
                pass

    def _close_connection_unsafe(self):
        """内部方法：关闭连接（不加锁版本）"""
        try:
            if self.ser:
                try:
                    if self.ser.is_open:
                        self.ser.close()
                except Exception:
                    # 强制忽略关闭时的异常
                    pass
        finally:
            self.ser = None
            self.is_connected = False

    def close(self):
        """公共方法：关闭连接"""
        # 关闭时尝试获取锁，若获取不到说明可能被其他线程占用，等待短时间再试
        try:
            with self._safe_lock():
                self._close_connection_unsafe()
                logger.info(f"{self.sport}-连接已关闭")
        except TimeoutError:
            # 若锁获取超时，仍尝试用连接锁独占关闭
            if self._connect_lock.acquire(timeout=5):
                try:
                    self._close_connection_unsafe()
                    logger.info(f"{self.sport}-连接已关闭（使用连接锁）")
                finally:
                    try:
                        self._connect_lock.release()
                    except Exception:
                        pass
            else:
                logger.error(f"{self.sport}-关闭连接时无法获取锁，放弃本次关闭请求")
        except Exception as e:
            logger.error(f"{self.sport}-关闭连接时出错: {e}")

    def _ensure_connection(self) -> bool:
        """
        确保连接可用，支持自动重连
        说明：
        - 为避免长时间持锁进行重连，重连逻辑会先快速判断，并在必要时逐次尝试重连；
          每次重连尝试会获取连接锁和短时 _safe_lock 来保证状态一致性。
        """
        # 快速检查当前连接
        if self.is_connected and self.ser:
            try:
                # 简单访问属性验证
                _ = self.ser.is_open
                return True
            except Exception:
                # 标记断开，继续重连尝试
                self.is_connected = False

        if not self.auto_reconnect:
            return False

        # 逐次尝试重连
        for attempt in range(self.max_reconnect_attempts):
            # 等待、避免多个线程同时重连：使用 connect_lock
            got = self._connect_lock.acquire(timeout=5)
            if not got:
                logger.warning(f"{self.sport}-重连时无法获取 connect_lock，尝试下一轮")
                time.sleep(self.reconnect_interval)
                continue

            try:
                # 在短锁保护下再检查一次状态，避免重复打开
                try:
                    with self._safe_lock():
                        if self.is_connected and self.ser and self.ser.is_open:
                            return True
                        # 尝试打开
                        logger.info(f"尝试重连 {attempt + 1}/{self.max_reconnect_attempts} to {self.sport}")
                        try:
                            self._open_serial()
                            logger.info(f"{self.sport}-重连成功")
                            return True
                        except Exception as e:
                            # 打开失败，清理状态并继续尝试
                            logger.error(f"{self.sport}-重连尝试 {attempt + 1} 失败: {e}")
                            self._close_connection_unsafe()
                except TimeoutError:
                    logger.error(f"{self.sport}-重连时获取主锁超时")
                    # 让出 connect_lock 并等待下次尝试
            finally:
                try:
                    self._connect_lock.release()
                except Exception:
                    pass

            time.sleep(self.reconnect_interval)

        # 尝试完仍失败
        return False

    def _send_status_message(self, message: str):
        """发送状态消息到队列（无锁版本），保持原有行为：若 origin 为 None 则直接返回"""
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

    def calculate_crc(self, data: bytes) -> bytes:
        """计算Modbus RTU CRC-16，小端返回"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
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

            # 组装帧（动态打包长度）
            fmt = ">B B " + " ".join(["B"] * len(data_bytes))
            frame = struct.pack(fmt, slave_id, function_code, *data_bytes)
            crc = self.calculate_crc(frame)

            logger.info(f"构造发送报文frame: {frame.hex()}|crc: {crc.hex()}")
            return frame + crc

        except Exception as e:
            error_msg = f"构造报文出错: {e}"
            self._send_status_message(error_msg)
            logger.error(f"{time_util.get_format_from_time(time.time())}-{self.sport}-{error_msg}")
            return None

    def get_table_name(self, slave_id):
        slave_id_int = int(slave_id, 16)
        if slave_id_int > 16:
            mouse_cage_number = slave_id_int // 16
            for type in Modbus_Slave_Type.Each_Mouse_Cage.value:
                if type.value['int'] == (slave_id_int % 16):
                    return next(iter(type.value['table'].keys()))
        else:
            for type in Modbus_Slave_Type.Not_Each_Mouse_Cage.value:
                if type.value['int'] == (slave_id_int % 16):
                    return next(iter(type.value['table'].keys()))
        return ""

    def send_command(self, slave_id: Union[str, int], function_code: Union[str, int],
                     data_hex_list: List[str], is_parse_response: bool = True) -> Tuple[
        Optional[bytes], Optional[str], bool, dict]:
        """
        发送Modbus RTU命令并获取响应（主要方法）
        - 串口读写会在 _safe_lock 内执行，确保不会有并发的读写冲突
        - 若无法建立连接，会尝试重连（受 max_reconnect_attempts 限制）
        """
        return_data = {}
        return_data['module_name'] = get_module_name(slave_id)
        return_data['table_name'] = self.get_table_name(slave_id)
        return_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return_data['mouse_cage_number'] = int(slave_id, 16) // 16 if int(slave_id, 16) > 16 else 0
        return_data['data'] = []
        return_data['slave_id'] = slave_id
        return_data['function_code'] = function_code

        # 尝试在限定时间内获取锁并进行串口操作
        try:
            with self._safe_lock():
                # 统计消息数（保持原行为）
                global_setting.set_setting("messages_sent_epoch_for_running",
                                          global_setting.get_setting("messages_sent_epoch_for_running", 0) + 1)

                if not self._ensure_connection():
                    msg = f"{self.sport}-无法建立连接"
                    logger.error(msg)
                    return_data['data'].append({'desc': '备注', 'value': msg})
                    return None, None, False, return_data

                # 构造报文
                frame = self.build_frame(slave_id, function_code, data_hex_list)
                if frame is None:
                    return_data['data'].append({'desc': '备注', 'value': f"构造发送报文 frame 为空"})
                    return None, None, False, return_data

                # 发送数据
                self._send_status_message(f"发送数据帧{frame.hex()}")
                logger.info(f"{time_util.get_format_from_time(time.time())}-{self.sport}-发送数据帧{frame.hex()}")

                # 串口 I/O：确保缓冲区清理 & 写入然后读取
                try:
                    # reset buffers guarded by lock
                    try:
                        self.ser.reset_input_buffer()
                        self.ser.reset_output_buffer()
                    except Exception:
                        # 某些虚拟串口可能不支持 reset_*
                        pass

                    # 写入
                    self.ser.write(frame)

                    # 读取响应：使用配置的 timeout，在 read() 时不会无限阻塞
                    # 这里尽量避免在锁内进行长时间 sleep；但 read() 本身可能阻塞到 timeout
                    response = self.ser.read(256)
                except Exception as e:
                    # I/O 错误：关闭连接并返回错误
                    logger.error(f"{self.sport}-串口读写异常: {e}")
                    self._send_status_message(f"串口读写异常: {e}")
                    self.is_connected = False
                    self._close_connection_unsafe()
                    return_data['data'].append({'desc': '备注', 'value': f"串口读写异常: {e}"})
                    return None, None, False, return_data

                # 验证响应
                return self._validate_response(response, slave_id, function_code, is_parse_response, frame, return_data)

        except TimeoutError as e:
            logger.error(f"{self.sport}-操作获取锁超时: {e}")
            return_data['data'].append({'desc': '备注', 'value': f"{self.sport}-操作超时: {e}"})
            return None, None, False, return_data
        except Exception as e:
            error_msg = f"串口通信异常: {e}"
            self._send_status_message(f"❗ {error_msg}")
            logger.error(f"{time_util.get_format_from_time(time.time())}-{self.sport}-❗ {error_msg}")
            return_data['data'].append({'desc': '备注', 'value': f"{error_msg}"})
            self.is_connected = False
            return None, None, False, return_data

    def _validate_response(self, response: bytes, slave_id: Union[str, int],
                           function_code: Union[str, int], is_parse_response: bool, send_frame, return_data) -> Tuple[
        Optional[bytes], Optional[str], bool, dict]:
        """验证响应数据"""
        if not response:
            self._send_status_message(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应-Time OUT1-未获取到响应数据")
            logger.error(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应-Time OUT1-未获取到响应数据")
            return_data['data'].append({'desc': '备注', 'value': f"请求报文{send_frame.hex()}-Time OUT1-未获取到响应数据"})
            return None, None, False, return_data

        if len(response) < 5:
            self._send_status_message(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应报文{response.hex()}-Time OUT2-返回数据位数错误")
            logger.error(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应报文{response.hex()}-Time OUT2-返回数据位数错误")
            return_data['data'].append({'desc': '备注', 'value': f"请求报文{send_frame.hex()}-响应报文{response.hex()}-Time OUT2-返回数据位数错误"})
            return response, response.hex(), False, return_data

        data_part = response[:-2]
        crc_received = response[-2:]
        crc_expected = self.calculate_crc(data_part)

        if crc_received != crc_expected:
            self._send_status_message(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应报文{response.hex()}-Time OUT3-数据错误，CRC验证失败")
            logger.error(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应报文{response.hex()}-Time OUT3-数据错误，CRC验证失败")
            return_data['data'].append({'desc': '备注', 'value': f"请求报文{send_frame.hex()}-响应报文{response.hex()}-Time OUT3-数据错误，CRC验证失败"})
            return response, response.hex(), False, return_data

        function_code_response = response[1]
        if function_code_response & 0x80:
            exception_code = response[2]
            error_msg = f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应报文{response.hex()}-异常：功能码=0x{function_code_response:02X}, 异常码=0x{exception_code:02X}"
            self._send_status_message(error_msg)
            logger.error(f"{error_msg}")
            return_data['data'].append({'desc': '备注', 'value': f"请求报文{send_frame.hex()}-响应报文{response.hex()}-异常：功能码=0x{function_code_response:02X}, 异常码=0x{exception_code:02X}"})
            return response, response.hex(), False, return_data

        # 正常响应
        self._send_status_message(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应报文{response.hex()}-CRC校验通过，正常响应")
        logger.info(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应报文{response.hex()}-CRC校验通过，正常响应")

        self._send_status_message(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应-收到响应消息-{response.hex()}-数据部分{data_part.hex()}")
        logger.info(f"{time_util.get_format_from_time(time.time())}-{self.sport}-请求报文{send_frame.hex()}响应-收到响应消息-{response.hex()}-数据部分{data_part.hex()}")

        if is_parse_response:
            # 尽量不要在重锁下做解析（如果解析耗时较长），但现有 parser 只是解析 bytes，应该较快。
            try:
                self.parse_response(response, response.hex(), True, slave_id, function_code)
            except Exception as e:
                logger.error(f"解析响应时出错: {e}")

        # 延迟可配置
        delay = float(global_setting.get_setting('monitor_data')['SEND']['get_response_delay'])
        if delay > 0:
            time.sleep(delay)
        return response, response.hex(), True, return_data

    def parse_response(self, response: bytes, response_hex: str, send_state: bool,
                       slave_id: Union[str, int], function_code: Union[str, int]):
        """解析响应报文"""
        logger.info(f"response[0](slave_id)-{response[0]}|slave_id:{slave_id}|response-{response}|response_hex-{response_hex}|send_state-{send_state}|response[1](FUNC_CODE)-{response[1]}|function_code:{function_code}")
        if send_state:
            logger.info("开始解析报文")
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
        try:
            return self.is_connected and self.ser and self.ser.is_open
        except:
            return False

    def __enter__(self):
        if self.connect():
            return self
        else:
            raise ConnectionError(f"无法连接到串口 {self.sport}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
