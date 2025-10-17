from datetime import datetime
import serial
import struct
import time
import threading
from typing import Optional, Tuple, List, Union, Dict
from contextlib import contextmanager

from loguru import logger

from public.config_class.global_setting import global_setting
from public.function.Modbus.Modbus_Response_Parser import Modbus_Response_Parser, get_module_name
from public.function.Modbus.Modbus_Type import Modbus_Slave_Type
from public.util.time_util import time_util


class ModbusRTUMasterNew:
    """
    高性能 Modbus RTU 通信类
    支持连接复用、自动重连、线程安全
    使用单例模式确保每个串口只有一个实例
    """

    # 类级别的实例字典和锁
    _instances: Dict[str, 'ModbusRTUMasterNew'] = {}
    _instances_lock = threading.Lock()

    # CRC 查表法优化（类级别，所有实例共享）
    _crc_table = None

    def __new__(cls, port='COM1', baudrate=115200, timeout=1, origin=None):
        """单例模式：确保每个串口只有一个实例"""
        key = f"{port}_{baudrate}"

        with cls._instances_lock:
            if key not in cls._instances:
                instance = super(ModbusRTUMasterNew, cls).__new__(cls)
                cls._instances[key] = instance
                instance._initialized = False
            return cls._instances[key]

    def __init__(self, port='COM1', baudrate=115200, timeout=1, origin=None):
        """初始化Modbus RTU Master（只初始化一次）"""
        if self._initialized:
            return

        # 基本参数
        self.sport = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.origin = origin

        # 连接管理
        self.ser: Optional[serial.Serial] = None
        self.is_connected = False

        # 使用RLock支持重入
        self._lock = threading.RLock()

        # 自动重连参数
        self.auto_reconnect = True
        self.max_reconnect_attempts = 3

        # 性能优化：缓存常用数据
        self._slave_id_cache = {}  # 缓存 slave_id 转换结果
        self._table_name_cache = {}  # 缓存 table_name 查询结果

        # 初始化 CRC 查表（类级别，只初始化一次）
        if ModbusRTUMasterNew._crc_table is None:
            ModbusRTUMasterNew._crc_table = self._init_crc_table()

        # 性能统计（可选）
        self._stats_enabled = False
        self._send_count = 0
        self._error_count = 0

        self._initialized = True
        logger.info(f"创建 ModbusRTUMaster 实例: {self.sport}")

    @staticmethod
    def _init_crc_table():
        """初始化 CRC16 查表，大幅提升 CRC 计算速度"""
        table = []
        for i in range(256):
            crc = i
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
            table.append(crc)
        return tuple(table)  # 使用 tuple 更快

    @contextmanager
    def _safe_lock(self, timeout=5):
        """安全的锁管理器（减少超时时间）"""
        acquired = self._lock.acquire(timeout=timeout)
        try:
            if not acquired:
                raise TimeoutError("获取锁超时")
            yield
        finally:
            if acquired:
                self._lock.release()

    def connect(self) -> bool:
        """建立串口连接"""
        try:
            with self._safe_lock():
                if self.is_connected and self.ser and self.ser.is_open:
                    return True

                self._close_connection_unsafe()
                time.sleep(0.05)  # 减少等待时间

                self.ser = serial.Serial(
                    port=self.sport,
                    baudrate=self.baudrate,
                    bytesize=8,
                    parity='N',
                    stopbits=1,
                    timeout=self.timeout,
                    write_timeout=self.timeout,  # 添加写超时
                    # 性能优化选项
                    exclusive=True,  # 独占模式
                    # inter_byte_timeout=None,  # 字节间超时
                )

                # 设置缓冲区大小（如果支持）
                try:
                    self.ser.set_buffer_size(rx_size=4096, tx_size=4096)
                except:
                    pass

                self.is_connected = True
                logger.info(f"{self.sport} 连接成功")
                return True

        except TimeoutError:
            logger.error(f"{self.sport} 获取锁超时")
            return False
        except serial.SerialException as e:
            logger.error(f"{self.sport} 串口连接失败: {e}")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"{self.sport} 连接失败: {e}")
            self.is_connected = False
            return False

    def _close_connection_unsafe(self):
        """关闭连接（不加锁版本）"""
        try:
            if self.ser:
                if self.ser.is_open:
                    self.ser.close()
                self.ser = None
        except:
            pass
        finally:
            self.ser = None
            self.is_connected = False

    def close(self):
        """关闭连接"""
        try:
            with self._safe_lock():
                self._close_connection_unsafe()
                logger.info(f"{self.sport} 连接已关闭")
        except Exception as e:
            logger.error(f"{self.sport} 关闭连接时出错: {e}")

    def _ensure_connection(self) -> bool:
        """确保连接可用（在锁内调用）"""
        if self.is_connected and self.ser and self.ser.is_open:
            return True

        if not self.auto_reconnect:
            return False

        # 快速重连
        for attempt in range(self.max_reconnect_attempts):
            try:
                self._close_connection_unsafe()
                time.sleep(0.1)  # 减少等待

                self.ser = serial.Serial(
                    port=self.sport,
                    baudrate=self.baudrate,
                    bytesize=8,
                    parity='N',
                    stopbits=1,
                    timeout=self.timeout,
                    write_timeout=self.timeout,
                    exclusive=True,
                )

                self.is_connected = True
                logger.info(f"{self.sport} 重连成功")
                return True

            except Exception as e:
                if attempt == self.max_reconnect_attempts - 1:
                    logger.error(f"{self.sport} 重连失败: {e}")
                time.sleep(0.1)

        return False

    def calculate_crc(self, data: bytes) -> bytes:
        """使用查表法计算 CRC16（性能提升 3-5 倍）"""
        crc = 0xFFFF
        for byte in data:
            index = (crc ^ byte) & 0xFF
            crc = (crc >> 8) ^ self._crc_table[index]
        return struct.pack('<H', crc)

    def build_frame(self, slave_id: Union[str, int], function_code: Union[str, int],
                    data_hex_list: List[str]) -> Optional[bytes]:
        """构造完整 Modbus RTU 报文（优化版本）"""
        try:
            # 使用缓存避免重复转换
            cache_key = (slave_id, function_code, tuple(data_hex_list))

            # 转换为整数（带缓存）
            if isinstance(slave_id, str):
                if slave_id not in self._slave_id_cache:
                    self._slave_id_cache[slave_id] = int(slave_id, 16)
                slave_id = self._slave_id_cache[slave_id]

            if isinstance(function_code, str):
                function_code = int(function_code, 16)

            # 批量转换（比逐个转换快）
            data_bytes = bytes(int(x, 16) for x in data_hex_list)

            # 直接构建字节串（比 struct.pack 更快）
            frame = bytes([slave_id, function_code]) + data_bytes
            crc = self.calculate_crc(frame)

            return frame + crc

        except Exception as e:
            logger.error(f"{self.sport} 构造报文出错: {e}")
            return None

    def get_table_name(self, slave_id):
        """获取表名（带缓存优化）"""
        # 使用缓存
        if slave_id in self._table_name_cache:
            return self._table_name_cache[slave_id]

        slave_id_int = int(slave_id, 16)
        result = ""

        if slave_id_int > 16:
            for type in Modbus_Slave_Type.Each_Mouse_Cage.value:
                if type.value['int'] == (slave_id_int % 16):
                    result = next(iter(type.value['table'].keys()))
                    break
        else:
            for type in Modbus_Slave_Type.Not_Each_Mouse_Cage.value:
                if type.value['int'] == (slave_id_int % 16):
                    result = next(iter(type.value['table'].keys()))
                    break

        # 缓存结果
        self._table_name_cache[slave_id] = result
        return result

    def send_command(self, slave_id: Union[str, int], function_code: Union[str, int],
                     data_hex_list: List[str], is_parse_response: bool = True) -> Tuple[
        Optional[bytes], Optional[str], bool, dict]:
        """发送Modbus RTU命令（性能优化版本）"""

        # 预先计算常用数据
        slave_id_int = int(slave_id, 16) if isinstance(slave_id, str) else slave_id

        return_data = {
            'module_name': get_module_name(slave_id),
            'table_name': self.get_table_name(slave_id),
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mouse_cage_number': slave_id_int // 16 if slave_id_int > 16 else 0,
            'data': [],
            'slave_id': slave_id,
            'function_code': function_code
        }

        try:
            with self._safe_lock(timeout=3):  # 减少锁超时时间
                # 统计
                if self._stats_enabled:
                    self._send_count += 1

                # 快速增加计数器
                global_setting.set_setting("messages_sent_epoch_for_running",
                                           global_setting.get_setting("messages_sent_epoch_for_running", 0) + 1)

                # 确保连接
                if not self._ensure_connection():
                    return_data['data'].append({'desc': '备注', 'value': f"{self.sport} 无法建立连接"})
                    if self._stats_enabled:
                        self._error_count += 1
                    return None, None, False, return_data

                # 构造报文
                frame = self.build_frame(slave_id, function_code, data_hex_list)
                if frame is None:
                    return_data['data'].append({'desc': '备注', 'value': "构造报文失败"})
                    return None, None, False, return_data

                # 清空缓冲区并发送（合并操作）
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()

                # 发送数据（一次性写入）
                bytes_written = self.ser.write(frame)
                if bytes_written != len(frame):
                    logger.warning(f"{self.sport} 写入字节数不匹配: {bytes_written}/{len(frame)}")

                # 读取响应（优化读取策略）
                # 先读取最小长度，然后根据需要继续读取
                response = bytearray()
                min_response_length = 5  # slave_id + func_code + data_len + crc(2)

                # 第一次读取
                chunk = self.ser.read(min_response_length)
                if not chunk:
                    return_data['data'].append({'desc': '备注', 'value': "响应超时"})
                    return None, None, False, return_data

                response.extend(chunk)

                # 根据功能码判断是否需要读取更多数据
                if len(response) >= 3:
                    expected_length = self._get_expected_response_length(response)
                    if expected_length > len(response):
                        remaining = self.ser.read(expected_length - len(response))
                        response.extend(remaining)

                response = bytes(response)

                # 验证响应
                return self._validate_response(response, slave_id, function_code,
                                               is_parse_response, frame, return_data)

        except TimeoutError:
            logger.error(f"{self.sport} 操作超时")
            return_data['data'].append({'desc': '备注', 'value': "操作超时"})
            return None, None, False, return_data
        except serial.SerialException as e:
            logger.error(f"{self.sport} 串口异常: {e}")
            return_data['data'].append({'desc': '备注', 'value': f"串口异常: {e}"})
            self.is_connected = False
            if self._stats_enabled:
                self._error_count += 1
            return None, None, False, return_data
        except Exception as e:
            logger.error(f"{self.sport} 通信异常: {e}")
            return_data['data'].append({'desc': '备注', 'value': f"异常: {e}"})
            self.is_connected = False
            return None, None, False, return_data

    def _get_expected_response_length(self, response: bytes) -> int:
        """根据响应头预测完整响应长度"""
        if len(response) < 3:
            return 256  # 默认最大长度

        function_code = response[1]

        # 异常响应
        if function_code & 0x80:
            return 5  # slave_id + func_code + exception_code + crc(2)

        # 读保持寄存器/输入寄存器 (0x03, 0x04)
        if function_code in (0x03, 0x04):
            byte_count = response[2]
            return 3 + byte_count + 2  # slave_id + func_code + byte_count + data + crc

        # 写单个寄存器 (0x06)
        if function_code == 0x06:
            return 8  # slave_id + func_code + address(2) + value(2) + crc(2)

        # 写多个寄存器 (0x10)
        if function_code == 0x10:
            return 8  # slave_id + func_code + address(2) + quantity(2) + crc(2)

        return 256  # 默认

    def _validate_response(self, response: bytes, slave_id: Union[str, int],
                           function_code: Union[str, int], is_parse_response: bool,
                           send_frame: bytes, return_data: dict) -> Tuple[
        Optional[bytes], Optional[str], bool, dict]:
        """验证响应数据（优化版本）"""

        # 快速检查
        if not response:
            return_data['data'].append({'desc': '备注', 'value': "无响应数据"})
            return None, None, False, return_data

        if len(response) < 5:
            return_data['data'].append({'desc': '备注', 'value': "响应数据过短"})
            return response, response.hex(), False, return_data

        # CRC 校验（使用查表法，已优化）
        data_part = response[:-2]
        crc_received = response[-2:]
        crc_expected = self.calculate_crc(data_part)

        if crc_received != crc_expected:
            return_data['data'].append({'desc': '备注', 'value': "CRC校验失败"})
            return response, response.hex(), False, return_data

        # 检查异常响应
        function_code_response = response[1]
        if function_code_response & 0x80:
            exception_code = response[2]
            return_data['data'].append({
                'desc': '备注',
                'value': f"异常: 0x{function_code_response:02X}, 异常码: 0x{exception_code:02X}"
            })
            return response, response.hex(), False, return_data

        # 解析响应（如果需要）
        if is_parse_response:
            self.parse_response(response, response.hex(), True, slave_id, function_code)

        # 延迟等待（从配置读取，可以优化为预读取）
        delay = float(global_setting.get_setting('monitor_data', {}).get('SEND', {}).get('get_response_delay', 0.01))
        if delay > 0:
            time.sleep(delay)

        return response, response.hex(), True, return_data

    def parse_response(self, response: bytes, response_hex: str, send_state: bool,
                       slave_id: Union[str, int], function_code: Union[str, int]):
        """解析响应报文"""
        if not send_state:
            return None, None

        try:
            modbus_response_parser = Modbus_Response_Parser(
                slave_id=f"{response[0]:x}",
                function_code=response[1],
                response=response,
                response_hex=response_hex
            )
            return modbus_response_parser.parser()
        except Exception as e:
            logger.error(f"解析响应失败: {e}")
            return None, None

    def is_alive(self) -> bool:
        """检查连接是否正常"""
        return self.is_connected and self.ser and self.ser.is_open

    def get_stats(self) -> dict:
        """获取性能统计"""
        return {
            'send_count': self._send_count,
            'error_count': self._error_count,
            'success_rate': (self._send_count - self._error_count) / max(self._send_count, 1)
        }

    def __enter__(self):
        """支持 with 语句"""
        if self.connect():
            return self
        raise ConnectionError(f"无法连接到串口 {self.sport}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句（不关闭连接，因为是单例）"""
        pass

    @classmethod
    def close_all(cls):
        """关闭所有串口连接"""
        with cls._instances_lock:
            for instance in cls._instances.values():
                try:
                    instance.close()
                except:
                    pass
            cls._instances.clear()
            logger.info("所有串口已关闭")