from enum import Enum


class Setting_Table(Enum):
    Group = {
       "base_table_name":"group",
        "desc":"通道/组",
       'column': [
            ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
            ("name", "名称", " TEXT "),
            ("create_time", "获取时间", " TIMESTAMP "),
            ("update_time", "获取时间", " TIMESTAMP ")
        ],
    }

    Animal = {
        "base_table_name": "animals",
        "desc": "动物信息",
        'column': [
            ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
            ("id_write", "ID", " INTEGER "),
            ("name", "动物名称", " TEXT "),
            ("sex", "性别", " BOOLEAN "),
            ("weight", "重量", " REAL "),
            ("weight_unit", "重量单位", " TEXT "),
            ("note", "备注", " TEXT "),
            ("create_time", "获取时间", " TIMESTAMP "),
            ("update_time", "获取时间", " TIMESTAMP ")

        ],
    }

    Group_Animal= {
        "base_table_name": "group_animal",
        "desc": "组/通道-动物信息 关系表",
        'column': [
            ("id", "序号", " INTEGER PRIMARY KEY AUTOINCREMENT "),
            ("aid", "动物序号", " TEXT "),
            ("gid", "组/通道序号", " BOOLEAN "),
            ("note", "备注", " TEXT "),
            ("create_time", "获取时间", " TIMESTAMP "),
            ("update_time", "获取时间", " TIMESTAMP ")

        ],
    }