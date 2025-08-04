import itertools
import os
from enum import Enum

from loguru import logger

from public.config_class.global_setting import global_setting
from public.config_class.ini_parser import ini_parser
from public.entity.send_message import Send_Message
from util.number_util import number_util


def load_global_setting():
    # 加载监控数据配置
    # config_file_path = os.getcwd() + "./config/monitor_datas_config.ini"
    # # 配置数据{"section":{"key1":value1,"key2":value2,....}，...}
    # config = ini_parser(config_file_path).read()
    # if (len(config) != 0):
    #     logger.info("监控配置文件读取成功。")
    # else:
    #     logger.error("监控配置文件读取失败。")
    # global_setting.set_setting("monitor_data", config)
    # 加载gui配置存储到全局类中
    configer =ini_parser(os.getcwd() +"./config/gui_config.ini").read()
    if configer is None:
        logger.error(f"./gui_config.ini配置文件读取失败")
    global_setting.set_setting("configer", configer)
    return configer


class Modbus_Slave_Ids(Enum):
    """
    远程地址大全
    """

    UFC = {
        "name": "UFC",
        "description": "气流控制模块",
        'address': 0x02,
        'int': int(0x02),

        'table': {
            "monitor_data": {
                    'function_code':4,
                    'column': [
                            ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                            ("flow_num", "流量计测量值(sccm)", " INTEGER "),
                            ("diff_pressure_num", "差压计测量值(kPa)", " REAL "),
                            ("barometer_num_1", "气压计1测量值(kPa)", " REAL "),
                            ("barometer_num_2", "气压计2测量值(kPa)", " REAL "),
                            ("reserve_num_1", "备用1测量值", " REAL "),
                            ("reserve_num_2", "备用2测量值", " REAL "),
                            ("time", "获取时间", " TIMESTAMP ")
                                ],
            },
            "out_port_state": {
                'function_code': 1,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("reference_gas", "参考气", " BOOLEAN "),
                    ("delivery_valve", "输出阀", " BOOLEAN "),
                    ("magnetic_valve_cage_1", "鼠笼1的电磁阀", " BOOLEAN "),
                    ("magnetic_valve_cage_2", "鼠笼2的电磁阀", " BOOLEAN "),
                    ("magnetic_valve_cage_3", "鼠笼3的电磁阀", " BOOLEAN "),
                    ("magnetic_valve_cage_4", "鼠笼4的电磁阀", " BOOLEAN "),
                    ("magnetic_valve_cage_5", "鼠笼5的电磁阀", " BOOLEAN "),
                    ("magnetic_valve_cage_6", "鼠笼6的电磁阀", " BOOLEAN "),
                    ("magnetic_valve_cage_7", "鼠笼7的电磁阀", " BOOLEAN "),
                    ("magnetic_valve_cage_8", "鼠笼8的电磁阀", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_status": {
                'function_code': 2,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("flow", "流量", " BOOLEAN "),
                    ("diff_pressure", "差压", " BOOLEAN "),
                    ("barometer_1", "气压1", " BOOLEAN "),
                    ("barometer_2", "气压2", " BOOLEAN "),
                    ("reserve_1", "备用1", " BOOLEAN "),
                    ("reserve_2", "备用2", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_config": {
                'function_code': 3,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("flow_config", "流量计配置流量", " TEXT "),
                    ("valve_opening_1", "调节阀1开度", " TEXT "),
                    ("valve_opening_2", "调节阀2开度", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "module_information": {
                'function_code': 17,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("manufacturer", "生产厂商", " TEXT "),
                    ("hardware_version", "硬件版本", " TEXT "),
                    ("software_version", "软件版本", " TEXT "),
                    ("factory_address", "出厂地址", " TEXT "),
                    ("current_address", "当前地址", " TEXT "),
                    ("reserve_1", "预留1", " TEXT "),
                    ("reserve_2", "预留2", " TEXT "),
                    ("reserve_3", "预留3", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            }
        }
    }
    UGC = {
        "name": "UGC",
        "description": "二氧化碳含量模块",
        'address': 0x03,
        'int': int(0x03),
        'table': {
            "monitor_data": {
                'function_code': 4,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("flow_num_1", "流量计1", " INTEGER "),
                    ("flow_num_2", "流量计2", " INTEGER "),
                    ("temperature_num_1", "温度1(°C)", " REAL "),
                    ("temperature_num_2", "温度2(°C)", " REAL "),
                    ("humidity_num_1", "湿度1(%RH)", " REAL "),
                    ("humidity_num_2", "湿度2(%RH)", " REAL "),
                    ("air_pressure_num_1", "气压1(KPa)", " REAL "),
                    ("air_pressure_num_2", "气压2(KPa)", " REAL "),
                    ("CO2_num", "CO2", " REAL "),
                    ("reserve", "保留", " REAL "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "out_port_state": {
                'function_code': 1,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("reserve_7", "预留7", " BOOLEAN "),
                    ("reserve_6", "预留6", " BOOLEAN "),
                    ("reserve_5", "预留5", " BOOLEAN "),
                    ("reserve_4", "预留4", " BOOLEAN "),
                    ("reserve_3", "预留3", " BOOLEAN "),
                    ("reserve_2", "预留2", " BOOLEAN "),
                    ("reserve_1", "预留1", " BOOLEAN "),
                    ("control_valve_4", "调节阀4", " BOOLEAN "),
                    ("control_valve_3", "调节阀3", " BOOLEAN "),
                    ("control_valve_2", "调节阀2", " BOOLEAN "),
                    ("control_valve_1", "调节阀1", " BOOLEAN "),
                    ("valve_5_5", "五选一阀5", " BOOLEAN "),
                    ("valve_5_4", "五选一阀4", " BOOLEAN "),
                    ("valve_5_3", "五选一阀3", " BOOLEAN "),
                    ("valve_5_2", "五选一阀2", " BOOLEAN "),
                    ("valve_5_1", "五选一阀1", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_status": {
                'function_code': 2,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("reserve_7", "预留7", " BOOLEAN "),
                    ("reserve_6", "预留6", " BOOLEAN "),
                    ("reserve_5", "预留5", " BOOLEAN "),
                    ("reserve_4", "预留4", " BOOLEAN "),
                    ("reserve_3", "预留3", " BOOLEAN "),
                    ("reserve_2", "预留2", " BOOLEAN "),
                    ("reserve_1", "预留1", " BOOLEAN "),
                    ("CO2", "CO2", " BOOLEAN "),
                    ("air_pressure_2", "气压2", " BOOLEAN "),
                    ("air_pressure_1", "气压1", " BOOLEAN "),
                    ("humidity_2", "湿度2", " BOOLEAN "),
                    ("humidity_1", "湿度1", " BOOLEAN "),
                    ("temperature_2", "温度2", " BOOLEAN "),
                    ("temperature_1", "温度1", " BOOLEAN "),
                    ("flow_2", "流量2", " BOOLEAN "),
                    ("flow_1", "流量1", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_config": {
                'function_code': 3,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("valve_opening_1", "调节阀1开度", " TEXT "),
                    ("valve_opening_2", "调节阀2开度", " TEXT "),
                    ("valve_opening_3", "调节阀3开度", " TEXT "),
                    ("valve_opening_4", "调节阀4开度", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "module_information": {
                'function_code': 17,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("manufacturer", "生产厂商", " TEXT "),
                    ("hardware_version", "硬件版本", " TEXT "),
                    ("software_version", "软件版本", " TEXT "),
                    ("factory_address", "出厂地址", " TEXT "),
                    ("current_address", "当前地址", " TEXT "),
                    ("reserve_1", "预留1", " TEXT "),
                    ("reserve_2", "预留2", " TEXT "),
                    ("reserve_3", "预留3", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            }
        }
    }
    ZOS = {
        "name": "ZOS",
        "description": "氧气含量测量模块",
        'address': 0x04,
        'int': int(0x04),
        'table': {
             "monitor_data": {
                'function_code': 4,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("oxygen_num", "氧气传感器测量值(%)", " REAL "),
                    ("temperature_num", "温度传感器测量值(°C)", " REAL "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "out_port_state": {
                'function_code': 1,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("control_oxygen_sensor_relay", "控制氧传感器通断电继电器", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_status": {
                'function_code': 2,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("oxygen", "氧传感器状态", " BOOLEAN "),
                    ("temperature", "温度传感器状态", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_config": {
                'function_code': 3,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("oxygen_sensor_reserve", "氧传感器配置（预留）", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "module_information": {
                'function_code': 17,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("manufacturer", "生产厂商", " TEXT "),
                    ("hardware_version", "硬件版本", " TEXT "),
                    ("software_version", "软件版本", " TEXT "),
                    ("factory_address", "出厂地址", " TEXT "),
                    ("current_address", "当前地址", " TEXT "),
                    ("reserve_1", "预留1", " TEXT "),
                    ("reserve_2", "预留2", " TEXT "),
                    ("reserve_3", "预留3", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            }
        }
    }
    ENM = {
        "name": "ENM",
        "description": "鼠笼环境监控模块",
        'address': 0x01,
        'int': int(0x01),
        'table': {
            "monitor_data": {
                'function_code':4,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("temperature_num", "温度测量值(°C)", " REAL "),
                    ("humidity_num", "湿度测量值(%RH)", " REAL "),
                    ("noise_num", "噪声测量值(dB)", " REAL "),
                    ("barometer_num", "大气压测量值(KPa)", " REAL "),
                    ("running_wheel_num", "当前计量周期内跑轮圈数测量值", " REAL "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "out_port_state": {
                'function_code': 1,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("running_wheel_brake", "跑轮刹车", " BOOLEAN "),
                    ("light_control", "光照控制", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_status": {
                'function_code': 2,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("temperature", "温度传感器", " BOOLEAN "),
                    ("barometer", "气压传感器", " BOOLEAN "),
                    ("noise", "噪声传感器", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_config": {
                'function_code': 3,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("light_luminance", "光照亮度", " TEXT "),
                    ("light_color_temp", "光照色温", " TEXT "),
                    ("module_address", "模块地址", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "module_information": {
                'function_code': 17,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("manufacturer", "生产厂商", " TEXT "),
                    ("hardware_version", "硬件版本", " TEXT "),
                    ("software_version", "软件版本", " TEXT "),
                    ("factory_address", "出厂地址", " TEXT "),
                    ("current_address", "当前地址", " TEXT "),
                    ("reserve_1", "预留1", " TEXT "),
                    ("reserve_2", "预留2", " TEXT "),
                    ("reserve_3", "预留3", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            }
        }
        # 每个鼠笼都有该模块，
        # 地址还要加上当前鼠笼号*16
        # 例如鼠笼1的鼠笼环境监控模块地址就是0x11
    }
    DWM = {
        "name": "DWM",
        "description": "饮水监控模块",
        'address': 0x02,
        'int': int(0x02),
        'table': {
            "monitor_data": {
                'function_code': 4,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("weight_num", "重量测量值(g)", " REAL "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_status": {
                'function_code': 2,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("weight", "重量传感器状态", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "module_information": {
                'function_code': 17,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("manufacturer", "生产厂商", " TEXT "),
                    ("hardware_version", "硬件版本", " TEXT "),
                    ("software_version", "软件版本", " TEXT "),
                    ("factory_address", "出厂地址", " TEXT "),
                    ("current_address", "当前地址", " TEXT "),
                    ("reserve_1", "预留1", " TEXT "),
                    ("reserve_2", "预留2", " TEXT "),
                    ("reserve_3", "预留3", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            }
        }
        # 每个鼠笼都有该模块，
        # 地址还要加上当前鼠笼号*16
        # 例如鼠笼1的鼠笼环境监控模块地址就是0x11
    }
    EM = {
        "name": "EM",
        "description": "进食监控模块",
        'address': 0x03,
        'int': int(0x03),
        'table': {
             "monitor_data": {
                'function_code': 4,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("weight_num", "重量测量值(g)", " REAL "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "out_port_state": {
                'function_code': 1,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("food_switch", "食物开关", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_status": {
                'function_code': 2,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("steering_engine", "舵机", " BOOLEAN "),
                    ("weight", "重量传感器状态", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "module_information": {
                'function_code': 17,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("manufacturer", "生产厂商", " TEXT "),
                    ("hardware_version", "硬件版本", " TEXT "),
                    ("software_version", "软件版本", " TEXT "),
                    ("factory_address", "出厂地址", " TEXT "),
                    ("current_address", "当前地址", " TEXT "),
                    ("reserve_1", "预留1", " TEXT "),
                    ("reserve_2", "预留2", " TEXT "),
                    ("reserve_3", "预留3", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            }
        }
        # 每个鼠笼都有该模块，
        # 地址还要加上当前鼠笼号*16
        # 例如鼠笼1的鼠笼环境监控模块地址就是0x11
    }

    WM = {
        "name": "WM",
        "description": "称重模块",
        'address': 0x04,
        'int': int(0x04),
        'table': {
            "monitor_data": {
                'function_code': 4,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("weight_num", "重量测量值(g)", " REAL "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "sensor_status": {
                'function_code': 2,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("weight", "重量传感器状态", " BOOLEAN "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            },
            "module_information": {
                'function_code': 17,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("manufacturer", "生产厂商", " TEXT "),
                    ("hardware_version", "硬件版本", " TEXT "),
                    ("software_version", "软件版本", " TEXT "),
                    ("factory_address", "出厂地址", " TEXT "),
                    ("current_address", "当前地址", " TEXT "),
                    ("reserve_1", "预留1", " TEXT "),
                    ("reserve_2", "预留2", " TEXT "),
                    ("reserve_3", "预留3", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            }
        }
        # 每个鼠笼都有该模块，
        # 地址还要加上当前鼠笼号*16
        # 例如鼠笼1的鼠笼环境监控模块地址就是0x11
    }

class Modbus_Slave_Send_Messages_Module_Info(Enum):
    # 所有读取模块id信息报文
    load_global_setting()
    UFC = {
        'type': Modbus_Slave_Ids.UFC,
        'send_messages': [

            Send_Message(slave_address=Modbus_Slave_Ids.UFC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UFC.value['description'], function_code=17,
                         function_desc="读取模块ID信息等", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(0),
                    'slave_id': format(int(Modbus_Slave_Ids.UFC.value['address']), '02X'),
                    'function_code': format(int(f"{11}", 16), '02X'),
                }),
        ]
    }
    UGC = {
        'type': Modbus_Slave_Ids.UGC,
        'send_messages': [

            Send_Message(slave_address=Modbus_Slave_Ids.UGC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UGC.value['description'], function_code=17,
                         function_desc="读取模块ID信息等", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(0),
                    'slave_id': format(int(Modbus_Slave_Ids.UGC.value['address']), '02X'),
                    'function_code': format(int(f"{11}", 16), '02X'),
                }),
        ]
    }
    ZOS = {
        'type': Modbus_Slave_Ids.ZOS,
        'send_messages': [

            Send_Message(slave_address=Modbus_Slave_Ids.ZOS.value['address'],
                         slave_desc=Modbus_Slave_Ids.ZOS.value['description'], function_code=17,
                         function_desc="读取模块ID信息等", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(0),
                    'slave_id': format(int(Modbus_Slave_Ids.ZOS.value['address']), '02X'),
                    'function_code': format(int(f"{11}", 16), '02X'),
                }),
        ]
    }
    ENM = {
        'type': Modbus_Slave_Ids.ENM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.ENM.value['address'],
                             slave_desc=Modbus_Slave_Ids.ENM.value['description'], function_code=17,
                             function_desc="读取模块ID信息等", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list(0),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.ENM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{11}", 16), '02X'),
                    }),
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    EM = {
        'type': Modbus_Slave_Ids.EM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.EM.value['address'],
                             slave_desc=Modbus_Slave_Ids.EM.value['description'], function_code=17,
                             function_desc="读取模块ID信息等", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('00540008'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.EM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{11}", 16), '02X'),
                    }),
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    DWM = {
        'type': Modbus_Slave_Ids.DWM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.DWM.value['address'],
                             slave_desc=Modbus_Slave_Ids.DWM.value['description'], function_code=17,
                             function_desc="读取模块ID信息等", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('00540008'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.DWM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{11}", 16), '02X'),
                    }),
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)
        ]
    }
    WM = {
        'type': Modbus_Slave_Ids.WM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.WM.value['address'],
                             slave_desc=Modbus_Slave_Ids.WM.value['description'], function_code=17,
                             function_desc="读取模块ID信息等", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('00540008'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.WM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{11}", 16), '02X'),
                    }),
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }




class Modbus_Slave_Send_Messages_Senior_State(Enum):
    # 所有读取传感器状态的报文信息
    load_global_setting()
    UFC = {
        'type': Modbus_Slave_Ids.UFC,
        'send_messages': [

            Send_Message(slave_address=Modbus_Slave_Ids.UFC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UFC.value['description'], function_code=2,
                         function_desc="读传感器状态信息", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(6),
                    'slave_id': format(int(Modbus_Slave_Ids.UFC.value['address']), '02X'),
                    'function_code': format(int(f"{2}", 16), '02X'),
                }),
        ]
    }
    UGC = {
        'type': Modbus_Slave_Ids.UGC,
        'send_messages': [

            Send_Message(slave_address=Modbus_Slave_Ids.UGC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UGC.value['description'], function_code=2,
                         function_desc="读传感器状态信息", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(16),
                    'slave_id': format(int(Modbus_Slave_Ids.UGC.value['address']), '02X'),
                    'function_code': format(int(f"{2}", 16), '02X'),
                }),

        ]
    }
    ZOS = {
        'type': Modbus_Slave_Ids.ZOS,
        'send_messages': [

            Send_Message(slave_address=Modbus_Slave_Ids.ZOS.value['address'],
                         slave_desc=Modbus_Slave_Ids.ZOS.value['description'], function_code=2,
                         function_desc="读传感器状态信息", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(2),
                    'slave_id': format(int(Modbus_Slave_Ids.ZOS.value['address']), '02X'),
                    'function_code': format(int(f"{2}", 16), '02X'),
                }),

        ]
    }
    ENM = {
        'type': Modbus_Slave_Ids.ENM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.ENM.value['address'],
                             slave_desc=Modbus_Slave_Ids.ENM.value['description'], function_code=2,
                             function_desc="读传感器状态信息", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list(3),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.ENM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{2}", 16), '02X'),
                    }),

            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    EM = {
        'type': Modbus_Slave_Ids.EM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.EM.value['address'],
                             slave_desc=Modbus_Slave_Ids.EM.value['description'], function_code=2,
                             function_desc="读传感器状态信息", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('00800002'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.EM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{2}", 16), '02X'),
                    }),


            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    DWM = {
        'type': Modbus_Slave_Ids.DWM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.DWM.value['address'],
                             slave_desc=Modbus_Slave_Ids.DWM.value['description'], function_code=2,
                             function_desc="读传感器状态信息", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('00800002'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.DWM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{2}", 16), '02X'),
                    }),


            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)
        ]
    }
    WM = {
        'type': Modbus_Slave_Ids.WM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.WM.value['address'],
                             slave_desc=Modbus_Slave_Ids.WM.value['description'], function_code=2,
                             function_desc="读传感器状态信息", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('00800002'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.WM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{2}", 16), '02X'),
                    }),


            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }


class Modbus_Slave_Send_Messages_Senior_Config(Enum):
    # 所有读取传感器配置信息报文
    load_global_setting()
    UFC = {
        'type': Modbus_Slave_Ids.UFC,
        'send_messages': [

            Send_Message(slave_address=Modbus_Slave_Ids.UFC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UFC.value['description'], function_code=1,
                         function_desc="读输出端口状态信息", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(10),
                    'slave_id': format(int(Modbus_Slave_Ids.UFC.value['address']), '02X'),
                    'function_code': format(int(f"{1}", 16), '02X'),
                }),

            Send_Message(slave_address=Modbus_Slave_Ids.UFC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UFC.value['description'], function_code=3,
                         function_desc="读配置寄存器", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(3),
                    'slave_id': format(int(Modbus_Slave_Ids.UFC.value['address']), '02X'),
                    'function_code': format(int(f"{3}", 16), '02X'),
                }),


        ]
    }
    UGC = {
        'type': Modbus_Slave_Ids.UGC,
        'send_messages': [
            Send_Message(slave_address=Modbus_Slave_Ids.UGC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UGC.value['description'], function_code=1,
                         function_desc="读输出端口状态信息", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(16),
                    'slave_id': format(int(Modbus_Slave_Ids.UGC.value['address']), '02X'),
                    'function_code': format(int(f"{1}", 16), '02X'),
                }),

            Send_Message(slave_address=Modbus_Slave_Ids.UGC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UGC.value['description'], function_code=3,
                         function_desc="读配置寄存器", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(8),
                    'slave_id': format(int(Modbus_Slave_Ids.UGC.value['address']), '02X'),
                    'function_code': format(int(f"{3}", 16), '02X'),
                }),
        ]
    }
    ZOS = {
        'type': Modbus_Slave_Ids.ZOS,
        'send_messages': [

            Send_Message(slave_address=Modbus_Slave_Ids.ZOS.value['address'],
                         slave_desc=Modbus_Slave_Ids.ZOS.value['description'], function_code=1,
                         function_desc="读输出端口状态信息", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(1),
                    'slave_id': format(int(Modbus_Slave_Ids.ZOS.value['address']), '02X'),
                    'function_code': format(int(f"{1}", 16), '02X'),
                }),

            Send_Message(slave_address=Modbus_Slave_Ids.ZOS.value['address'],
                         slave_desc=Modbus_Slave_Ids.ZOS.value['description'], function_code=3,
                         function_desc="读配置寄存器", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(1),
                    'slave_id': format(int(Modbus_Slave_Ids.ZOS.value['address']), '02X'),
                    'function_code': format(int(f"{3}", 16), '02X'),
                }),
        ]
    }
    ENM = {
        'type': Modbus_Slave_Ids.ENM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.ENM.value['address'],
                             slave_desc=Modbus_Slave_Ids.ENM.value['description'], function_code=1,
                             function_desc="读输出端口状态信息", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list(2),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.ENM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{1}", 16), '02X'),
                    }),

                Send_Message(slave_address=Modbus_Slave_Ids.ENM.value['address'],
                             slave_desc=Modbus_Slave_Ids.ENM.value['description'], function_code=3,
                             function_desc="读配置寄存器", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list(3),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.ENM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{3}", 16), '02X'),
                    }),

            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    EM = {
        'type': Modbus_Slave_Ids.EM,
        'send_messages': [
            [

                Send_Message(slave_address=Modbus_Slave_Ids.EM.value['address'],
                             slave_desc=Modbus_Slave_Ids.EM.value['description'], function_code=1,
                             function_desc="读输出端口状态信息", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list(1),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.EM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{1}", 16), '02X'),
                    }),

            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    DWM = {
        'type': Modbus_Slave_Ids.DWM,
        'send_messages': [
            [

            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)
        ]
    }
    WM = {
        'type': Modbus_Slave_Ids.WM,
        'send_messages': [
            [

            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }

class  Modbus_Slave_Send_Messages_Senior_Data(Enum):
    #所有读取传感器数值报文
    # 所有读取数值信息报文
    load_global_setting()
    UFC = {
        'type': Modbus_Slave_Ids.UFC,
        'send_messages': [
            Send_Message(slave_address=Modbus_Slave_Ids.UFC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UFC.value['description'], function_code=4,
                         function_desc="读传感器测量值", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(6),
                    'slave_id': format(int(Modbus_Slave_Ids.UFC.value['address']), '02X'),
                    'function_code': format(int(f"{4}", 16), '02X'),
                }),
        ]
    }
    UGC = {
        'type': Modbus_Slave_Ids.UGC,
        'send_messages': [
            Send_Message(slave_address=Modbus_Slave_Ids.UGC.value['address'],
                         slave_desc=Modbus_Slave_Ids.UGC.value['description'], function_code=4,
                         function_desc="读传感器测量值", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(8),
                    'slave_id': format(int(Modbus_Slave_Ids.UGC.value['address']), '02X'),
                    'function_code': format(int(f"{4}", 16), '02X'),
                }),
        ]
    }
    ZOS = {
        'type': Modbus_Slave_Ids.ZOS,
        'send_messages': [
            Send_Message(slave_address=Modbus_Slave_Ids.ZOS.value['address'],
                         slave_desc=Modbus_Slave_Ids.ZOS.value['description'], function_code=4,
                         function_desc="读传感器测量值", message={
                    'port': None,
                    'data': number_util.set_int_to_4_bytes_list(2),
                    'slave_id': format(int(Modbus_Slave_Ids.ZOS.value['address']), '02X'),
                    'function_code': format(int(f"{4}", 16), '02X'),
                }),
        ]
    }
    ENM = {
        'type': Modbus_Slave_Ids.ENM,
        'send_messages': [
            [
                Send_Message(slave_address=Modbus_Slave_Ids.ENM.value['address'],
                             slave_desc=Modbus_Slave_Ids.ENM.value['description'], function_code=4,
                             function_desc="读传感器测量值", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list(7),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.ENM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{4}", 16), '02X'),
                    }),
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    EM = {
        'type': Modbus_Slave_Ids.EM,
        'send_messages': [
            [
                Send_Message(slave_address=Modbus_Slave_Ids.EM.value['address'],
                             slave_desc=Modbus_Slave_Ids.EM.value['description'], function_code=4,
                             function_desc="读传感器测量值", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('04010002'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.EM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{4}", 16), '02X'),
                    }),
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    DWM = {
        'type': Modbus_Slave_Ids.DWM,
        'send_messages': [
            [
                Send_Message(slave_address=Modbus_Slave_Ids.DWM.value['address'],
                             slave_desc=Modbus_Slave_Ids.DWM.value['description'], function_code=4,
                             function_desc="读传感器测量值", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('04010002'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.DWM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{4}", 16), '02X'),
                    }),
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)
        ]
    }
    WM = {
        'type': Modbus_Slave_Ids.WM,
        'send_messages': [
            [
                Send_Message(slave_address=Modbus_Slave_Ids.WM.value['address'],
                             slave_desc=Modbus_Slave_Ids.WM.value['description'], function_code=4,
                             function_desc="读传感器测量值", message={
                        'port': None,
                        'data': number_util.set_int_to_4_bytes_list('04010002'),
                        'slave_id': format(
                            int(Modbus_Slave_Ids.WM.value['address']) + 16 * carge_number,
                            '02X'),
                        'function_code': format(int(f"{4}", 16), '02X'),
                    }),
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    pass






class Modbus_Slave_Send_Messages_All(Enum):
    # 所有读取数值信息报文
    load_global_setting()
    UFC = {
        'type': Modbus_Slave_Ids.UFC,
        'send_messages': [
            send_message
            for send_message in list(itertools.chain(Modbus_Slave_Send_Messages_Senior_Data.UFC.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Senior_State.UFC.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Senior_Config.UFC.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Module_Info.UFC.value['send_messages'],
                                                     )
                                     )
        ]
    }
    UGC = {
        'type': Modbus_Slave_Ids.UGC,
        'send_messages': [
            send_message
            for send_message in list(itertools.chain(Modbus_Slave_Send_Messages_Senior_Data.UGC.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Senior_State.UGC.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Senior_Config.UGC.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Module_Info.UGC.value['send_messages'],
                                                     )
                                     )
        ]
    }
    ZOS = {
        'type': Modbus_Slave_Ids.ZOS,
        'send_messages': [
            send_message
            for send_message in list(itertools.chain(Modbus_Slave_Send_Messages_Senior_Data.ZOS.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Senior_State.ZOS.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Senior_Config.ZOS.value['send_messages'],
                                                     Modbus_Slave_Send_Messages_Module_Info.ZOS.value['send_messages'],
                                                     )
                                     )
        ]
    }
    ENM = {
        'type': Modbus_Slave_Ids.ENM,
        'send_messages': [
            [
                send_message
                for send_message in list(itertools.chain(Modbus_Slave_Send_Messages_Senior_Data.ENM.value['send_messages'][carge_number-1],
                                                         Modbus_Slave_Send_Messages_Senior_State.ENM.value['send_messages'][carge_number-1],
                                                         Modbus_Slave_Send_Messages_Senior_Config.ENM.value['send_messages'][carge_number-1],
                                                         Modbus_Slave_Send_Messages_Module_Info.ENM.value['send_messages'][carge_number-1],
                                                         )
                                         )
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    EM = {
        'type': Modbus_Slave_Ids.EM,
        'send_messages': [
            [
                send_message
                for send_message in
                list(itertools.chain(Modbus_Slave_Send_Messages_Senior_Data.EM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Senior_State.EM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Senior_Config.EM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Module_Info.EM.value['send_messages'][carge_number-1],
                                     )
                     )
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }
    DWM = {
        'type': Modbus_Slave_Ids.DWM,
        'send_messages': [
            [
                send_message
                for send_message in
                list(itertools.chain(Modbus_Slave_Send_Messages_Senior_Data.DWM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Senior_State.DWM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Senior_Config.DWM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Module_Info.DWM.value['send_messages'][carge_number-1],
                                     )
                     )
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)
        ]
    }
    WM = {
        'type': Modbus_Slave_Ids.WM,
        'send_messages': [
            [
                send_message
                for send_message in
                list(itertools.chain(Modbus_Slave_Send_Messages_Senior_Data.WM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Senior_State.WM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Senior_Config.WM.value['send_messages'][carge_number-1],
                                     Modbus_Slave_Send_Messages_Module_Info.WM.value['send_messages'][carge_number-1],
                                     )
                     )
            ]
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2)

        ]
    }


class Modbus_Slave_Type(Enum):
    # 将上面的分为鼠笼内的和鼠笼外的传感器
    Not_Each_Mouse_Cage = [
        Modbus_Slave_Ids.UFC, Modbus_Slave_Ids.UGC, Modbus_Slave_Ids.ZOS
    ]
    Each_Mouse_Cage = [
        Modbus_Slave_Ids.ENM, Modbus_Slave_Ids.EM, Modbus_Slave_Ids.DWM, Modbus_Slave_Ids.WM
    ]

    Not_Each_Mouse_Cage_Message_All = [
        Modbus_Slave_Send_Messages_All.UFC, Modbus_Slave_Send_Messages_All.UGC, Modbus_Slave_Send_Messages_All.ZOS
    ]
    Each_Mouse_Cage_Message_All = [
        Modbus_Slave_Send_Messages_All.ENM, Modbus_Slave_Send_Messages_All.EM, Modbus_Slave_Send_Messages_All.DWM,
        Modbus_Slave_Send_Messages_All.WM
    ]
    Not_Each_Mouse_Cage_Message_Senior_Data = [
        Modbus_Slave_Send_Messages_Senior_Data.UFC, Modbus_Slave_Send_Messages_Senior_Data.UGC, Modbus_Slave_Send_Messages_Senior_Data.ZOS
    ]
    Each_Mouse_Cage_Message_Senior_Data= [
        Modbus_Slave_Send_Messages_Senior_Data.ENM, Modbus_Slave_Send_Messages_Senior_Data.EM, Modbus_Slave_Send_Messages_Senior_Data.DWM,
        Modbus_Slave_Send_Messages_Senior_Data.WM
    ]
    Not_Each_Mouse_Cage_Message_Senior_Config = [
        Modbus_Slave_Send_Messages_Senior_Config.UFC, Modbus_Slave_Send_Messages_Senior_Config.UGC, Modbus_Slave_Send_Messages_Senior_Config.ZOS
    ]
    Each_Mouse_Cage_Message_Senior_Config = [
        Modbus_Slave_Send_Messages_Senior_Config.ENM, Modbus_Slave_Send_Messages_Senior_Config.EM, Modbus_Slave_Send_Messages_Senior_Config.DWM,
        Modbus_Slave_Send_Messages_Senior_Config.WM
    ]
    Not_Each_Mouse_Cage_Message_Senior_State= [
        Modbus_Slave_Send_Messages_Senior_State.UFC, Modbus_Slave_Send_Messages_Senior_State.UGC, Modbus_Slave_Send_Messages_Senior_State.ZOS
    ]
    Each_Mouse_Cage_Message_Senior_State = [
        Modbus_Slave_Send_Messages_Senior_State.ENM, Modbus_Slave_Send_Messages_Senior_State.EM, Modbus_Slave_Send_Messages_Senior_State.DWM,
        Modbus_Slave_Send_Messages_Senior_State.WM
    ]
    Not_Each_Mouse_Cage_Message_Module_Info = [
        Modbus_Slave_Send_Messages_Module_Info.UFC, Modbus_Slave_Send_Messages_Module_Info.UGC, Modbus_Slave_Send_Messages_Module_Info.ZOS
    ]
    Each_Mouse_Cage_Message_Module_Info = [
        Modbus_Slave_Send_Messages_Module_Info.ENM, Modbus_Slave_Send_Messages_Module_Info.EM, Modbus_Slave_Send_Messages_Module_Info.DWM,
        Modbus_Slave_Send_Messages_Module_Info.WM
    ]
