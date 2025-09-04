import itertools
from enum import Enum

from Module.UFC_UGC_ZOS_Test.entity.send_message import Send_Message
from Module.UFC_UGC_ZOS_Test.util.number_util import number_util


class Modbus_Slave_Tables(Enum):
    """
    数据库文件
    """
    UFC_monitor_data={
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
            }
    }
    UFC_out_port_state={
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
            }
    }
    UFC_sensor_status = {
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
            }
    }
    UFC_sensor_config = {
            "sensor_config": {
                'function_code': 3,
                'column': [
                    ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                    ("flow_config", "流量计配置流量", " TEXT "),
                    ("valve_opening_1", "调节阀1开度", " TEXT "),
                    ("valve_opening_2", "调节阀2开度", " TEXT "),
                    ("time", "获取时间", " TIMESTAMP ")
                ]
            }
    }
    UFC_module_information = {
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
    #03 04
    UGC_monitor_data={
        "monitor_data": {
            'function_code': 4,
            'column': [
                ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                ("flow_num_1", "流量计1", " INTEGER "),
                ("CO2_num", "CO2(%)", " REAL "),
                ("reserve", "保留", " REAL "),
                ("time", "获取时间", " TIMESTAMP ")
            ]
        }
    }
    UGC_out_port_state={
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
        }
    }
    UGC_sensor_status={
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
        }
    }
    UGC_sensor_config={
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
        }
    }
    UGC_module_information={
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
    ZOS_monitor_data={
        "monitor_data": {
            'function_code': 4,
            'column': [
                ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                ("oxygen_num", "氧气传感器测量值(%)", " REAL "),
                ("oxygen2_num", "氧气传感器2测量值(%)", " REAL "),
                ("time", "获取时间", " TIMESTAMP ")
            ]
        }
    }
    ZOS_out_port_state={
        "out_port_state": {
            'function_code': 1,
            'column': [
                ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                ("control_oxygen_sensor_relay", "控制氧传感器通断电继电器", " BOOLEAN "),
                ("time", "获取时间", " TIMESTAMP ")
            ]
        }
    }
    ZOS_sensor_status={
        "sensor_status": {
            'function_code': 2,
            'column': [
                ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                ("oxygen", "氧传感器状态", " BOOLEAN "),
                ("temperature", "温度传感器状态", " BOOLEAN "),
                ("time", "获取时间", " TIMESTAMP ")
            ]
        }
    }
    ZOS_sensor_config={
        "sensor_config": {
            'function_code': 3,
            'column': [
                ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
                ("oxygen_sensor_reserve", "氧传感器配置（预留）", " TEXT "),
                ("time", "获取时间", " TIMESTAMP ")
            ]
        }
    }
    ZOS_module_information={
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



    UFC_all={
        **UFC_monitor_data,
        **UFC_out_port_state,
        **UFC_sensor_status,
        **UFC_sensor_config,
        **UFC_module_information
    }

    UGC_all = {
        **UGC_monitor_data,
        **UGC_out_port_state,
        **UGC_sensor_status,
        **UGC_sensor_config,
        **UGC_module_information
    }
    ZOS_all = {
        **ZOS_monitor_data,
        **ZOS_out_port_state,
        **ZOS_sensor_status,
        **ZOS_sensor_config,
        **ZOS_module_information
    }



class Modbus_Slave_Ids(Enum):
    """
    远程地址大全
    """

    UFC = {
        "name": "UFC",
        "description": "气流控制模块",
        'address': 0x02,
        'int': int(0x02),
        'table': Modbus_Slave_Tables.UFC_monitor_data.value
    }
    UGC = {
        "name": "UGC",
        "description": "二氧化碳含量模块",
        'address': 0x03,
        'int': int(0x03),
        'table':  Modbus_Slave_Tables.UGC_monitor_data.value
    }
    ZOS = {
        "name": "ZOS",
        "description": "氧气含量测量模块",
        'address': 0x04,
        'int': int(0x04),
        'table': Modbus_Slave_Tables.ZOS_monitor_data.value
    }


class Modbus_Slave_Send_Messages_Module_Info(Enum):
    # 所有读取模块id信息报文
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





class Modbus_Slave_Send_Messages_Senior_State(Enum):
    # 所有读取传感器状态的报文信息
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



class Modbus_Slave_Send_Messages_Senior_Config(Enum):
    # 所有读取传感器配置信息报文
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


class  Modbus_Slave_Send_Messages_Senior_Data(Enum):
    #所有读取传感器数值报文
    # 所有读取数值信息报文
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







class Modbus_Slave_Send_Messages_All(Enum):
    # 所有读取数值信息报文
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



class Modbus_Slave_Type(Enum):
    # 将上面的分为鼠笼内的和鼠笼外的传感器
    Not_Each_Mouse_Cage = [
        Modbus_Slave_Ids.UFC, Modbus_Slave_Ids.UGC, Modbus_Slave_Ids.ZOS
    ]


    Not_Each_Mouse_Cage_Message_All = [
        Modbus_Slave_Send_Messages_All.UFC, Modbus_Slave_Send_Messages_All.UGC, Modbus_Slave_Send_Messages_All.ZOS
    ]

    Not_Each_Mouse_Cage_Message_Senior_Data = [
        Modbus_Slave_Send_Messages_Senior_Data.UFC, Modbus_Slave_Send_Messages_Senior_Data.UGC, Modbus_Slave_Send_Messages_Senior_Data.ZOS
    ]

    Not_Each_Mouse_Cage_Message_Senior_Config = [
        Modbus_Slave_Send_Messages_Senior_Config.UFC, Modbus_Slave_Send_Messages_Senior_Config.UGC, Modbus_Slave_Send_Messages_Senior_Config.ZOS
    ]

    Not_Each_Mouse_Cage_Message_Senior_State= [
        Modbus_Slave_Send_Messages_Senior_State.UFC, Modbus_Slave_Send_Messages_Senior_State.UGC, Modbus_Slave_Send_Messages_Senior_State.ZOS
    ]

    Not_Each_Mouse_Cage_Message_Module_Info = [
        Modbus_Slave_Send_Messages_Module_Info.UFC, Modbus_Slave_Send_Messages_Module_Info.UGC, Modbus_Slave_Send_Messages_Module_Info.ZOS
    ]
