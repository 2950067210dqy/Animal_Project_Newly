import os
import time
from datetime import datetime
from typing import Dict, Any, List

from loguru import logger


from public.config_class.global_setting import global_setting
from public.dao.SQLite.SQliteManager import SQLiteManager
from public.entity.dict.AdvancedFuzzyDict import FuzzyDict
from public.entity.experiment_setting_entity import Experiment_setting_entity
from public.function.DataCaculation import Data_Caculation
from public.function.DataCaculation.Data_Caculation import DataCaculation
from public.function.Modbus.Modbus_Type import Modbus_Slave_Type, Modbus_Slave_Ids
# 监控数据操作类
from public.util.time_util import time_util
#logger = logger.bind(category="deep_camera_logger")

class Monitor_Datas_Handle():
    ZERO_FILL_MONITOR_DESCS = {
        "CO2(%)",
        "氧浓度(%)",
        "补偿后氧气浓度(%)",
        "温度测量值(°C)",
        "温度测量值(℃)",
        "ZOS温度测量值(°C)",
        "ZOS温度测量值(℃)",
        "湿度测量值(%RH)",
        "噪声测量值(dB)",
    }

    def __init__(self,db_name=None):
        # 实验设置
        self.experiment_setting: Experiment_setting_entity = global_setting.get_setting("experiment_setting", None)
        self.experiment_setting_file = global_setting.get_setting("experiment_setting_file", None)
        self.sqlite_manager: SQLiteManager = None
        self.zero_fill_cache = {}
        self.init_construct(db_name)

        self.conn = None  # 为检测结果处理准备连接

    def init_construct(self,db_name):
        if db_name is None:
            self.db_name = self.create_db_not_time()
        else:
            self.db_name = db_name
        if self.sqlite_manager is not None:
            self.stop()
        self.sqlite_manager = SQLiteManager(db_name=self.db_name)
        if db_name is None:
            self.create_tables()
        pass

    def stop(self):
        self.sqlite_manager.close()
        if self.conn:
            self.conn.close()
    def create_db_not_time(self):
        """创建数据库 不按时间分库，直接一个实验一个库"""
        # 获取实验配置文件名称
        file_name_without_extension = ""
        experiment_setting_file = global_setting.get_setting("experiment_setting_file", None)
        if experiment_setting_file is not None and os.path.exists(experiment_setting_file):
            # 获取文件名称
            file_name = os.path.basename(experiment_setting_file)
            # 不带扩展名的文件名称
            file_name_without_extension = os.path.splitext(file_name)[0]
        # 定义文件夹路径
        folder_path = os.getcwd() + global_setting.get_setting('monitor_data')['STORAGE']['fold_path'] + os.path.join(

            global_setting.get_setting('monitor_data')['STORAGE']['sub_fold_path'],
            f"{file_name_without_extension}_{time_util.get_format_file_from_time(global_setting.get_setting('start_experiment_time', time.time()))}",
            f'data'
        )

        # 创建文件夹（如果不存在）
        os.makedirs(folder_path, exist_ok=True)
        db_name = f"data.db"
        db_file_path = os.path.join(folder_path, db_name)
        return db_file_path
    def create_db(self):
        """
        创建数据库
        :return:
        """
        year, month, day, hour, minute, second = time_util.get_current_times_info()
        # 获取实验配置文件名称
        file_name_without_extension =""
        experiment_setting_file = global_setting.get_setting("experiment_setting_file", None)
        if experiment_setting_file is not None and os.path.exists(experiment_setting_file):
            # 获取文件名称
            file_name = os.path.basename(experiment_setting_file)
            # 不带扩展名的文件名称
            file_name_without_extension = os.path.splitext(file_name)[0]
        # 定义文件夹路径
        folder_path =os.getcwd()+ global_setting.get_setting('monitor_data')['STORAGE']['fold_path'] + os.path.join(

            global_setting.get_setting('monitor_data')['STORAGE']['sub_fold_path'], f"{file_name_without_extension}_{time_util.get_format_file_from_time(global_setting.get_setting('start_experiment_time',time.time()))}",f'{year}', f'{month}')

        # 创建文件夹（如果不存在）
        os.makedirs(folder_path, exist_ok=True)
        db_name = f"{day}.db"
        db_file_path = os.path.join(folder_path, db_name)
        return db_file_path

    def create_tables(self):
        if self.experiment_setting is not None:

            gids = [group.id for group in self.experiment_setting.groups ]
            # 实例化相机数据项项的数据表
            for data_type in Modbus_Slave_Type.Cameras.value:
                # 每个鼠笼都要实例化，除了参考气路
                for carge_number in gids:
                    for table_name_short in data_type.value['table']:
                        # 列
                        columns = {item[0]: item[2] for item in data_type.value['table'][table_name_short]['column']}
                        # 表名称
                        table_name = f"{data_type.value['name']}_{table_name_short}_cage_{carge_number}"
                        # 创建表
                        if not self.sqlite_manager.is_exist_table(table_name):
                            self.sqlite_manager.create_table(table_name,
                                                             columns)
                            # logger.info(f"数据库{self.db_name}创建数据表{table_name}成功！")
                        # 创建该表描述的表
                        table_meta_name = f"{table_name}_meta"
                        # 不存在则创建和插入
                        if not self.sqlite_manager.is_exist_table(table_meta_name):
                            self.sqlite_manager.create_meta_table(table_meta_name)
                            # logger.info(f"数据库{self.db_name}创建表结构描述数据表{table_meta_name}成功！")
                            # 插入描述信息
                            for item in data_type.value['table'][table_name_short]['column']:
                                self.sqlite_manager.insert_or_ignore(table_meta_name, item_name=item[0],
                                                                     item_struct=item[2],
                                                                     description=item[1])
            self._migrate_mouse_infrared_tables(gids)
            self._migrate_o2_compensation_tables(
                gids=gids,
                reference_cage_number=int(global_setting.get_setting('configer')['mouse_cage']['reference'])
            )
            # 实例化每轮次数据表
            for data_type in Modbus_Slave_Type.Epochs.value:
                # 添加cage_0 给参考气存储数据 这里的-1代表总轮次表，表名为Epoch_data_all 不带后面的cage_-1
                for carge_number in [-1,int(global_setting.get_setting('configer')['mouse_cage']['reference'])]+gids:
                    for table_name_short in data_type.value['table']:
                        # 列
                        columns = {item[0]: item[2] for item in data_type.value['table'][table_name_short]['column']}
                        # 表名称
                        # 总表 表名为Epoch_data_all 不带后面的cage_-1
                        if carge_number ==-1:
                            table_name = f"{data_type.value['name']}_{table_name_short}_all"
                        else:
                            table_name = f"{data_type.value['name']}_{table_name_short}_cage_{carge_number}"
                        # 创建表
                        if not self.sqlite_manager.is_exist_table(table_name):
                            self.sqlite_manager.create_table(table_name,
                                                             columns)
                            # logger.info(f"数据库{self.db_name}创建数据表{table_name}成功！")
                        # 创建该表描述的表
                        table_meta_name = f"{table_name}_meta"
                        # 不存在则创建和插入
                        if not self.sqlite_manager.is_exist_table(table_meta_name):
                            self.sqlite_manager.create_meta_table(table_meta_name)
                            # logger.info(f"数据库{self.db_name}创建表结构描述数据表{table_meta_name}成功！")
                            # 插入描述信息
                            for item in data_type.value['table'][table_name_short]['column']:
                                self.sqlite_manager.insert_or_ignore(table_meta_name, item_name=item[0], item_struct=item[2],
                                                           description=item[1])

            # 实例化其他数据项的数据表
            for data_type in Modbus_Slave_Type.Calibrations.value:
                for table_name_short in data_type.value['table']:
                    # 列
                    columns = {item[0]: item[2] for item in data_type.value['table'][table_name_short]['column']}
                    # 表名称
                    table_name = f"{data_type.value['name']}_{table_name_short}"
                    # 创建表
                    if not self.sqlite_manager.is_exist_table(table_name):
                        self.sqlite_manager.create_table(table_name,
                                                         columns)
                        # logger.info(f"数据库{self.db_name}创建数据表{table_name}成功！")
                    # 创建该表描述的表
                    table_meta_name = f"{table_name}_meta"
                    # 不存在则创建和插入
                    if not self.sqlite_manager.is_exist_table(table_meta_name):
                        self.sqlite_manager.create_meta_table(table_meta_name)
                        # logger.info(f"数据库{self.db_name}创建表结构描述数据表{table_meta_name}成功！")
                        # 插入描述信息
                        for item in data_type.value['table'][table_name_short]['column']:
                            self.sqlite_manager.insert_or_ignore(table_meta_name, item_name=item[0], item_struct=item[2],
                                                       description=item[1])
            # 实例化公共传感器数据的数据表
            for data_type in Modbus_Slave_Type.Not_Each_Mouse_Cage.value:
                # 添加cage_8 给参考气存储数据
                for carge_number in [int(global_setting.get_setting('configer')['mouse_cage']['reference'])]+gids:
                    for table_name_short in data_type.value['table']:
                        # 列
                        columns = {item[0]: item[2] for item in data_type.value['table'][table_name_short]['column']}
                        # 表名称
                        table_name = f"{data_type.value['name']}_{table_name_short}_cage_{carge_number}"
                        # 创建表
                        if not self.sqlite_manager.is_exist_table(table_name):
                            self.sqlite_manager.create_table(table_name,
                                                             columns)
                            # logger.info(f"数据库{self.db_name}创建数据表{table_name}成功！")
                        # 创建该表描述的表
                        table_meta_name = f"{table_name}_meta"
                        # 不存在则创建和插入
                        if not self.sqlite_manager.is_exist_table(table_meta_name):
                            self.sqlite_manager.create_meta_table(table_meta_name)
                            # logger.info(f"数据库{self.db_name}创建表结构描述数据表{table_meta_name}成功！")
                            # 插入描述信息
                            for item in data_type.value['table'][table_name_short]['column']:
                                self.sqlite_manager.insert_or_ignore(table_meta_name, item_name=item[0], item_struct=item[2],
                                                           description=item[1])
                pass
        # 实例化每个笼子里的传感器的数据表

            reference_cage_number = int(global_setting.get_setting('configer')['mouse_cage']['reference'])
            for data_type in Modbus_Slave_Type.Each_Mouse_Cage.value:
                cage_numbers = gids
                if data_type == Modbus_Slave_Ids.ENM:
                    cage_numbers = [reference_cage_number] + gids
                for carge_number in cage_numbers:
                    for table_name_short in data_type.value['table']:
                        # 列
                        columns = {item[0]: item[2] for item in data_type.value['table'][table_name_short]['column']}
                        # 表名称
                        table_name = f"{data_type.value['name']}_{table_name_short}_cage_{carge_number}"
                        # 创建表
                        if not self.sqlite_manager.is_exist_table(table_name):
                            self.sqlite_manager.create_table(table_name,
                                                             columns)
                            # logger.info(f"数据库{self.db_name}创建数据表{table_name}成功！")
                        # 创建该表描述的表
                        table_meta_name = f"{table_name}_meta"
                        # 不存在则创建和插入
                        if not self.sqlite_manager.is_exist_table(table_meta_name):
                            # logger.info(f"数据库{self.db_name}创建表结构描述数据表{table_meta_name}成功！")
                            self.sqlite_manager.create_meta_table(table_meta_name)
                            # 插入描述信息
                            for item in data_type.value['table'][table_name_short]['column']:
                                self.sqlite_manager.insert(table_meta_name, item_name=item[0], item_struct=item[2],
                                                           description=item[1])
        pass

    def _migrate_mouse_infrared_tables(self, gids):
        for cage_number in gids:
            self._migrate_mouse_infrared_table(f"MouseInfrared_data_cage_{cage_number}")

    def _migrate_mouse_infrared_table(self, table_name):
        old_column_name = "tmp_hs_mean"
        new_column_name = "tmp_hs_max"
        new_description = "最大值温度(摄氏度)"
        meta_table_name = f"{table_name}_meta"

        if not self.sqlite_manager.is_exist_table(table_name):
            return

        with self.sqlite_manager.execute_transaction() as cursor:
            quoted_table_name = self.sqlite_manager.quote_ident(table_name)
            cursor.execute(f"PRAGMA table_info({quoted_table_name})")
            table_columns = [row[1] for row in cursor.fetchall()]

            if old_column_name in table_columns and new_column_name not in table_columns:
                cursor.execute(
                    f'ALTER TABLE {quoted_table_name} RENAME COLUMN "{old_column_name}" TO "{new_column_name}"'
                )

            if not self.sqlite_manager.is_exist_table(meta_table_name):
                return

            quoted_meta_table_name = self.sqlite_manager.quote_ident(meta_table_name)
            cursor.execute(
                f"SELECT item_name FROM {quoted_meta_table_name} WHERE item_name = ?",
                (old_column_name,)
            )
            if cursor.fetchone() is not None:
                cursor.execute(
                    f"UPDATE {quoted_meta_table_name} "
                    f"SET item_name = ?, description = ? "
                    f"WHERE item_name = ?",
                    (new_column_name, new_description, old_column_name)
                )
            else:
                cursor.execute(
                    f"UPDATE {quoted_meta_table_name} SET description = ? WHERE item_name = ?",
                    (new_description, new_column_name)
                )

    def _migrate_o2_compensation_tables(self, gids, reference_cage_number):
        zos_desc = "补偿后氧气浓度(%)"

        for cage_number in [reference_cage_number] + gids:
            self._ensure_column_and_meta(
                table_name=f"ZOS_monitor_data_cage_{cage_number}",
                column_name="oxygen_compensation_num",
                column_struct=" REAL ",
                description=zos_desc
            )

        for cage_number in [-1, reference_cage_number] + gids:
            if cage_number == -1:
                table_name = "Epoch_data_all"
            else:
                table_name = f"Epoch_data_cage_{cage_number}"
            self._ensure_column_and_meta(
                table_name=table_name,
                column_name="ZOS_oxygen_compensation_num",
                column_struct=" REAL ",
                description=zos_desc
            )

    def _ensure_column_and_meta(self, table_name, column_name, column_struct, description):
        if not self.sqlite_manager.is_exist_table(table_name):
            return

        meta_table_name = f"{table_name}_meta"
        with self.sqlite_manager.execute_transaction() as cursor:
            quoted_table_name = self.sqlite_manager.quote_ident(table_name)
            cursor.execute(f"PRAGMA table_info({quoted_table_name})")
            table_columns = [row[1] for row in cursor.fetchall()]

            if column_name not in table_columns:
                cursor.execute(
                    f"ALTER TABLE {quoted_table_name} ADD COLUMN "
                    f"{self.sqlite_manager.quote_ident(column_name)} {column_struct}"
                )

            if not self.sqlite_manager.is_exist_table(meta_table_name):
                return

            quoted_meta_table_name = self.sqlite_manager.quote_ident(meta_table_name)
            cursor.execute(
                f"SELECT item_name FROM {quoted_meta_table_name} WHERE item_name = ?",
                (column_name,)
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"INSERT INTO {quoted_meta_table_name} (item_name, item_struct, description) "
                    f"VALUES (?, ?, ?)",
                    (column_name, column_struct, description)
                )
            else:
                cursor.execute(
                    f"UPDATE {quoted_meta_table_name} SET description = ?, item_struct = ? WHERE item_name = ?",
                    (description, column_struct, column_name)
                )

    def _map_data_compact_with_none(self,data_list, columns_mapping):
        """
        我的columns_all_except_id列表装着我数据表的所有列名以及列的描述，例如[{'序号':'id'}.......],
        现在我的data['data']拥有数据 [
            {'desc': '温度测量值(℃)', 'value': -85.9},
            {'desc': '湿度测量值(%RH)', 'value': 93.9},
            {'desc': '噪声测量值(dB)', 'value': 190.1},
            {'desc': '大气压测量值(KPa)', 'value': 2275.6},
            {'desc': '当前计量周期内跑轮圈数测量值', 'value': 8501.028},
            {'desc': '备注', 'value': None}
        ],
        我该怎么根据data['data']里的列的描述desc去columns_all_except_id找着对应的列名，
        并且将data['data']里desc所在字典的'value'键的值与我们所找着对应的列名给形成键值对的字典，
        例如{'id':0},如果data['data']没有在columns_all_except_id找着对应的列名，
        则将键值对列名的值为None
        :param data_list:
        :param columns_mapping:
        :return:输出: {'id': None, 'temperature': -85.9, 'humidity': 93.9, 'noise': 190.1, 'pressure': 2275.6, 'wheel_count': 8501.028, 'remarks': None, 'other_field': None}
        """
        # 创建描述到列名的映射
        desc_to_column = columns_mapping

        # 创建数据的描述到值的映射 模糊查询 因为可能键会有细微差异
        desc_to_value =FuzzyDict({item['desc']: item['value'] for item in data_list})

        # 为所有列创建映射
        result = {column: desc_to_value.fuzzy_get(desc) for desc, column in desc_to_column.items()}

        return result

    def _coerce_numeric_value(self, value):
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _query_latest_non_zero_value(self, table_name, column_name):
        if not column_name:
            return None

        quoted_table_name = self.sqlite_manager.quote_ident(table_name)
        quoted_column_name = self.sqlite_manager.quote_ident(column_name)
        sql = (
            f"SELECT {quoted_column_name} FROM {quoted_table_name} "
            f"WHERE {quoted_column_name} IS NOT NULL "
            f"AND ABS(CAST({quoted_column_name} AS REAL)) > ? "
            f"ORDER BY time DESC LIMIT 1"
        )

        with self.sqlite_manager.execute_transaction(auto_commit=True) as cursor:
            cursor.execute(sql, (1e-12,))
            row = cursor.fetchone()
            return row[0] if row else None

    def _fill_monitor_zero_values(self, table_name, data_items, columns_all_except_id):
        for data_item in data_items:
            desc = data_item.get('desc')
            if desc not in self.ZERO_FILL_MONITOR_DESCS:
                continue

            numeric_value = self._coerce_numeric_value(data_item.get('value'))
            if numeric_value is None:
                continue

            cache_key = (table_name, desc)
            if abs(numeric_value) <= 1e-12:
                previous_value = self.zero_fill_cache.get(cache_key)
                if previous_value is None:
                    previous_value = self._query_latest_non_zero_value(
                        table_name=table_name,
                        column_name=columns_all_except_id.get(desc)
                    )
                    if previous_value is not None:
                        self.zero_fill_cache[cache_key] = previous_value

                if previous_value is not None:
                    logger.debug(f"{table_name} | {desc} 检测到零值，回填上一条非零值: {previous_value}")
                    data_item['value'] = previous_value
            else:
                self.zero_fill_cache[cache_key] = data_item.get('value')

    def insert_data(self, data):
        """

        :param data:
        :return: success ：是否成功, error 错误信息
        """


        # 添加数据到表里
        if data is not None:
            # logger.critical(f"{data}")
            # 清洗数据
            for data_item in data['data']:
                if isinstance(data_item['value'],list) and len(data_item['value']) ==0:
                    data_item['value'] =None
            # 公共传感器：
            if data['mouse_cage_number'] == -1:
                # 获取该表名称
                table_name = f"{data['module_name']}_{data['table_name']}"
                # # 获取该表的column项
                table_name_meta = f"{table_name}_meta"
                columns_query = self.sqlite_manager.query(table_name_meta)
                # 把id列去掉 因为id自增
                columns_all_except_id = {i[2]:i[0] for i in columns_query if i[0] != 'id' }
                if data.get('table_name') == 'monitor_data':
                    self._fill_monitor_zero_values(table_name, data['data'], columns_all_except_id)
                data_store = self._map_data_compact_with_none(data['data'], columns_all_except_id)
                data_store['time'] = data['time']
                # logger.critical(f"{data}|||{columns_all_except_id}|||{data_store}")
                result = self.sqlite_manager.insert(table_name, **data_store)
                if result == 1:
                    logger.info(f"数据插入表{table_name}成功！")
                    return True, None
                else:
                    logger.info(f"数据插入表{table_name}失败！")
                    return False, f"数据插入表{table_name}失败！"

            else:  # 每个鼠笼传感器以及气路传感器和每轮次数据：
                # 获取该表名称
                table_name = f"{data['module_name']}_{data['table_name']}_cage_{data['mouse_cage_number']}"
                # # 获取该表的column项
                table_name_meta = f"{table_name}_meta"
                columns_query = self.sqlite_manager.query(table_name_meta)
                # 把id列去掉 因为id自增
                columns_all_except_id = {i[2]:i[0] for i in columns_query if i[0] != 'id' }
                if data.get('table_name') == 'monitor_data':
                    self._fill_monitor_zero_values(table_name, data['data'], columns_all_except_id)
                data_store = self._map_data_compact_with_none(data['data'], columns_all_except_id)
                data_store['time'] = data['time']
                # logger.critical(f"{data}|||{columns_all_except_id}|||{data_store}")
                result = self.sqlite_manager.insert(table_name, **data_store)
                if result == 1:
                    logger.info(f"数据插入表{table_name}成功！")
                    return True, None
                else:
                    logger.info(f"数据插入表{table_name}失败！")
                    return False, f"数据插入表{table_name}失败！"
        else:
            return False
            pass

    def query_data(self, table_name):
        """
        获取数据库的数据表的单行最新的数据
        :param table_name:
        :return:
        """
        results_query = self.sqlite_manager.query_current_Data(table_name)
        columns_query = self.sqlite_manager.query(f"{table_name}_meta")
        return_data = []
        results = []
        columns = []
        if results_query is not None and len(results_query) > 0:
            # 不要id 和time
            results = list(results_query[0])[1:-1]
        if columns_query is not None and len(columns_query) > 0:
            # 不要id 和time
            columns = [i[2] for i in columns_query][1:-1]
        for value, description in zip(results, columns):
            return_data.append({'desc': description, 'value': value})
        return return_data
        pass
    def query_data_all(self, table_name):
        """
        获取数据库的数据表的所有的数据
        :param table_name:
        :return:
        """
        results_query = self.sqlite_manager.query(table_name)

        results = []

        if results_query is not None and len(results_query) > 0:
            results = results_query
        return results
        pass
    def query_data_counts(self, table_name):
        """
        获取数据库的数据表的所有的数据的数量
        :param table_name:
        :return:
        """
        results_query = self.sqlite_manager.query_counts_conditions(table_name)

        results = 0

        if results_query is not None:
            results = results_query
        return results
        pass
    def query_data_paging(self, table_name,rows_per_page,start_row):
        """
        获取数据库的数据表的分页的数据
        :param table_name:
        :param rows_per_page:每一页几行
        :param start_row:第几行开始
        :return:
        """
        results_query = self.sqlite_manager.query_paging(table_name,rows_per_page,start_row)

        results = []

        if results_query is not None and len(results_query) > 0:
            results = results_query
        return results
        pass
    def query_current_one_data(self,table_name):
        results_query = self.sqlite_manager.query_current_Data(table_name)

        return_results = None

        if results_query is not None and len(results_query) > 0:
            results = results_query[0]
            # 寻找列名
            columns_query_result = self.sqlite_manager.query(f"{table_name}_meta")
            if columns_query_result is not None and len(columns_query_result) > 0:
                columns_query =[i[0] for i in columns_query_result]
                # logger.critical(f"columns_query:{columns_query},columns_query_result:{columns_query_result}")
                return_results=dict(zip(columns_query, results))
                return return_results
            else:
                return return_results

        else:
            return return_results
    def query_data_one_column_current(self, table_name, columns_flag):
        """
        获取指定列的单个最新的数据
        :param table_name:
        :param columns_flag:
        :return:
        """
        if len(columns_flag) > 0:
            conditions = "  where "
        else:
            conditions = ""
        for columns_signle in columns_flag:
            if columns_signle == columns_flag[-1]:
                conditions += f" item_name = '{columns_signle}' "
            else:
                conditions += f" item_name = '{columns_signle}' or "
        columns_query = self.sqlite_manager.query_conditions(f"{table_name}_meta", conditions)

        results_query = self.sqlite_manager.query_current_Data_columns(table_name, [i[0] for i in columns_query])
        return_data = {}
        results = []
        columns_name = []
        columns_desc = []
        if results_query is not None and len(results_query) > 0:
            results = list(results_query[0])
        if columns_query is not None and len(columns_query) > 0:
            columns_name = [i[0] for i in columns_query]
            columns_desc = [i[2] for i in columns_query]
            pass
        for value, column_name, column_desc in zip(results, columns_name, columns_desc):
            return_data[column_name] = {'desc': column_desc, 'value': value}
        """\
        return_data
        {
            'temperature':{
            'desc':'温度',
            'value':1
            },
            .....
        }
        """
        return [return_data]

    def query_meta_table_data(self, table_name):
        """
        获取表结构数据 item_desc 去除id remarks time列
        :param table_name:
        :return:
        """
        columns_query = self.sqlite_manager.query(f"{table_name}_meta")
        columns_desc = []
        if columns_query is not None and len(columns_query) > 0:
            columns_desc = [{'desc':i[2],'name':i[0]} for i in columns_query][1:-2]
        return columns_desc

    def query_meta_table_data_all(self, table_name):
        """
        获取表结构数据 item_desc
        :param table_name:
        :return:
        """
        columns_query = self.sqlite_manager.query(f"{table_name}_meta")
        columns_desc = []
        if columns_query is not None and len(columns_query) > 0:
            columns_desc = [{'desc': i[2], 'name': i[0]} for i in columns_query]
        return columns_desc

    def query_monitor_data_all_tables_paging(self, page: int = 1,
            page_size: int = 100,all_column_datas=[])-> dict:
        """
        :param page 第几页
        :param page_size 每页多少
        :param all_column_datas 用户选择的列数据
        :return:把传入的表按 time 字段联立并分页返回结果，返回字典包含:
          - total_items: 总行数（time 的并集大小）
          - total_pages
          - page (实际返回页，1-based)
          - page_size
          - columns: 列名列表（与 rows 中 dict 的 key 对应）
          - rows: 列表，每行为 dict（key=列名, value=值）

        从 SQLite 数据库中找出所有表名（排除名称中包含 "meta" 的表，大小写不敏感）；
        仅保留包含 time 字段的表；
        将这些表按 time 联立（以 time 的并集为主），把各表的其它字段并列（别名为 表名__列名，避免重名）；
        支持分页（page 1-based，page_size），并返回总条数、总页数、当前页数据等分页信息。
        注意事项：

            SQLite 没有 FULL OUTER JOIN，所以用 UNION 把各表的 time 合并成一个派生表 all_times，然后 LEFT JOIN 每个表；
            为防止 SQL 注入与标识符冲突，对表名与列名使用双引号转义（quote_ident）；
            统计总条数时使用 SELECT COUNT(*) FROM ( ... UNION ... )；
            LIMIT / OFFSET 用于分页（page 从 1 开始）。如果数据量很大，COUNT 与 UNION 可能较慢，建议为 time 列建索引或在后端分片

        """
        if len(all_column_datas) == 0:
            return {}
        tables = self.sqlite_manager.get_tables_with_time(exclude_substr=["meta","Epoch_data"],columns=['time'])
        result = self.sqlite_manager.query_joined_by_time( tables, page=page, page_size=page_size, order_asc=True)

        result_title = ["时间"]

        # 找到中文列名
        for columns in result["columns"][1:]:
            columns_split = columns.split('__')
            table_name = columns_split[0]
            column_name = columns_split[1]
            columns_query =self.sqlite_manager.query_conditions(table_name=f"{table_name}_meta", conditions=f" where item_name='{column_name}'")
            print(columns_query,table_name,column_name)
            result_title.append(columns_query[0][2])
        result["columns_title"]=result_title
        # print("参与联立的表:", tables)
        # print(
        #     f"总条数: {result['total_items']}, 总页数: {result['total_pages']}, 当前页: {result['page']}, 每页: {result['page_size']}")
        # print("列:", result["columns"])
        # print("示例行（最多 10 行）:")
        # for i, row in enumerate(result["rows"][:10]):
        #     print(i + 1, row)

        if len(result) == 0:
            return {}
        # caculation_handle = DataCaculation(sqlite_manager = self.sqlite_manager)
        #
        # return_results = caculation_handle.caculate_data(columns=all_column_datas,datas=result)


        return result
        pass
    def query_epoch_data_all_tables_paging(self,gid:int=0, page: int = 1,
            page_size: int = 100,all_column_datas=[])-> dict:
        """
        :param gid 鼠笼/通道几的数据  如果为-1 则获取总表Epoch_data_all的数据
        :param page 第几页
        :param page_size 每页多少
        :param all_column_datas 用户选择的列数据
        :return:把传入的表按 time 字段联立并分页返回结果，返回字典包含:
          - total_items: 总行数（time 的并集大小）
          - total_pages
          - page (实际返回页，1-based)
          - page_size
          - columns: 列名列表（与 rows 中 dict 的 key 对应）
          - rows: 列表，每行为 dict（key=列名, value=值）

        从 SQLite 数据库中找出epoch_Data；

        支持分页（page 1-based，page_size），并返回总条数、总页数、当前页数据等分页信息。
        注意事项：

            SQLite 没有 FULL OUTER JOIN，所以用 UNION 把各表的 time 合并成一个派生表 all_times，然后 LEFT JOIN 每个表；
            为防止 SQL 注入与标识符冲突，对表名与列名使用双引号转义（quote_ident）；
            统计总条数时使用 SELECT COUNT(*) FROM ( ... UNION ... )；
            LIMIT / OFFSET 用于分页（page 从 1 开始）。如果数据量很大，COUNT 与 UNION 可能较慢，建议为 time 列建索引或在后端分片

        """
        if len(all_column_datas) == 0:
            return {}
        # 如果为-1 则获取总表Epoch_data_all的数据
        if gid == -1:
            table_name = f"Epoch_data_all"
            pass
        else:
            table_name = f"Epoch_data_cage_{gid}"
        result = self.sqlite_manager.query_Epoch_datas( table_name, page=page, page_size=page_size, order_asc=True )
        result_title = []

        # 找到中文列名
        for columns in result["columns"]:

            columns_query =self.sqlite_manager.query_conditions(table_name=f"{table_name}_meta", conditions=f" where item_name='{columns}'")
            if columns_query and len(columns_query) > 0:
                result_title.append(columns_query[0][2])
        result["columns_title"]=result_title
        # print("参与联立的表:", tables)
        # print(
        #     f"总条数: {result['total_items']}, 总页数: {result['total_pages']}, 当前页: {result['page']}, 每页: {result['page_size']}")
        # print("列:", result["columns"])
        # print("示例行（最多 10 行）:")
        # for i, row in enumerate(result["rows"][:10]):
        #     print(i + 1, row)
        # logger.critical(result)
        if len(result) == 0:
            return {}
        # caculation_handle = DataCaculation(sqlite_manager = self.sqlite_manager)
        #
        # return_results = caculation_handle.caculate_data(columns=all_column_datas,datas=result)

        return result

        pass
    def query_epoch_data_all_tables_expect_text_column(self,gid:int=0,
            page_size: int = 100)-> dict:
        """
        :param gid 鼠笼/通道几的数据  如果为-1 则获取总表Epoch_data_all的数据
        :param page_size 容量多少
        :return:把传入的表按 time 字段联立并分页返回结果，返回字典包含:
          - total_items: 总行数（time 的并集大小）
          - columns: 列名列表（与 rows 中 dict 的 key 对应）
          - rows: 列表，每行为 dict（key=列名, value=值）

        从 SQLite 数据库中找出epoch_Data的最新数量数据除了文字列；


        注意事项：

            SQLite 没有 FULL OUTER JOIN，所以用 UNION 把各表的 time 合并成一个派生表 all_times，然后 LEFT JOIN 每个表；
            为防止 SQL 注入与标识符冲突，对表名与列名使用双引号转义（quote_ident）；
            统计总条数时使用 SELECT COUNT(*) FROM ( ... UNION ... )；
            LIMIT / OFFSET 用于分页（page 从 1 开始）。如果数据量很大，COUNT 与 UNION 可能较慢，建议为 time 列建索引或在后端分片

        """
        # 如果为-1 则获取总表Epoch_data_all的数据
        if gid == -1:
            table_name = f"Epoch_data_all"
            pass
        else:
            table_name = f"Epoch_data_cage_{gid}"
        result = self.sqlite_manager.query_Epoch_datas( table_name, page=1, page_size=page_size, order_asc=True )
        result_title = []

        # 找到中文列名
        for columns in result["columns"]:

            columns_query =self.sqlite_manager.query_conditions(table_name=f"{table_name}_meta", conditions=f" where item_name='{columns}'")
            if columns_query and len(columns_query) > 0:
                result_title.append(columns_query[0][2])
        result["columns_title"]=result_title
        # print("参与联立的表:", tables)
        # print(
        #     f"总条数: {result['total_items']}, 总页数: {result['total_pages']}, 当前页: {result['page']}, 每页: {result['page_size']}")
        # print("列:", result["columns"])
        # print("示例行（最多 10 行）:")
        # for i, row in enumerate(result["rows"][:10]):
        #     print(i + 1, row)
        # logger.critical(result)
        if len(result) == 0:
            return {}
        # caculation_handle = DataCaculation(sqlite_manager = self.sqlite_manager)
        #
        # return_results = caculation_handle.caculate_data(columns=all_column_datas,datas=result)

        return result

        pass
    def query_monitor_data_all_tables(self, all_column_datas=[]) -> dict:
        pass


    def query_epoch_actual_end_time(self, start_time, end_time=None):
        if end_time is None:
            end_time = time.time()
        tables = self.sqlite_manager.get_tables_with_time(exclude_substr=["meta","Epoch_data"], columns=['time'])
        return self.sqlite_manager.get_latest_time_across_tables(tables, start_time=start_time, end_time=end_time)

    def query_data_in_line_with_epoch_data(self,start_time,end_time, start_exclusive=False):
        # 找出当前时间段的所有数据表的数据除了meta表
        tables = self.sqlite_manager.get_tables_with_time(exclude_substr=["meta","Epoch_data"],columns=['time'])
        # logger.critical(tables)
        # 执行查询
        results, columns = self.sqlite_manager.get_multi_table_data(tables,
            start_time, end_time, join_type="separate", start_exclusive=start_exclusive
        )
        # logger.critical(results)
        # logger.critical(columns)
        return results, columns

        pass

    """
    @author wangjie
    @create_time 2025-11-27
    @start
    """
    def get_available_cages(self):
        """
        获取数据库中存在的鼠笼编号列表

        Returns:
            list: 排序后的鼠笼编号列表
        """
        try:
            logger.info("=== 开始获取可用鼠笼列表 ===")

            # 获取所有表名
            tables = self.sqlite_manager.get_all_tables()
            logger.info(f"数据库中总共找到 {len(tables)} 个表:")
            for table in tables:
                logger.info(f"  表名: {table}")

            cage_numbers = []
            for table_name in tables:
                logger.info(f"检查表: {table_name}")

                if table_name.startswith("MouseDeepPosition_data_cage_") and not table_name.endswith("_meta"):
                    logger.info(f"  匹配的鼠笼表: {table_name}")
                    # 提取鼠笼编号
                    cage_number = table_name.replace("MouseDeepPosition_data_cage_", "")
                    logger.info(f"  提取的鼠笼编号字符串: '{cage_number}'")

                    try:
                        cage_num = int(cage_number)
                        cage_numbers.append(cage_num)
                        logger.info(f"  成功转换为数字: {cage_num}")
                    except ValueError as e:
                        logger.error(f"  无法转换为数字: {e}")
                        continue

            result = sorted(cage_numbers)
            logger.info(f"最终找到的鼠笼编号: {result}")
            return result

        except Exception as e:
            logger.error(f"获取可用鼠笼列表失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    # def get_trajectory_data(self, cage_id, start_time=None, end_time=None, limit=None):
    #     """
    #     获取指定鼠笼的轨迹数据
    #
    #     Args:
    #         cage_id (int): 鼠笼编号
    #         start_time (str, optional): 开始时间，格式: 'YYYY-MM-DD HH:MM:SS'
    #         end_time (str, optional): 结束时间，格式: 'YYYY-MM-DD HH:MM:SS'
    #         limit (int, optional): 限制返回的数据条数
    #
    #     Returns:
    #         dict: 包含轨迹数据的字典
    #     """
    #     try:
    #         print(f"=== 开始获取鼠笼 {cage_id} 的轨迹数据 ===")
    #
    #         table_name = f"MouseDeepPosition_data_cage_{cage_id}"
    #
    #         # 检查表是否存在
    #         if not self.sqlite_manager.check_table_exists(table_name):
    #             return {
    #                 'success': False,
    #                 'data': [],
    #                 'total_count': 0,
    #                 'message': f'鼠笼 {cage_id} 的数据表不存在'
    #             }
    #
    #         # 获取总数据条数
    #         total_count = self.sqlite_manager.get_table_data_count(table_name, start_time, end_time)
    #         print(f"表 {table_name} 中符合条件的数据总数: {total_count}")
    #
    #         # 获取XYZ轨迹数据
    #         rows = self.sqlite_manager.get_trajectory_xyz_data_by_table(
    #             table_name, start_time=start_time, end_time=end_time, limit=limit
    #         )
    #
    #         print(f"实际获取到 {len(rows)} 条轨迹数据")
    #
    #         # 转换数据格式
    #         trajectory_data = []
    #         for row in rows:
    #             time_val, x, y, z = row
    #             trajectory_data.append([
    #                 time_val,
    #                 float(x) if x is not None else 0.0,
    #                 float(y) if y is not None else 0.0,
    #                 float(z) if z is not None else 0.0
    #             ])
    #
    #         if len(trajectory_data) > 0:
    #             print(f"数据示例 - 前3条:")
    #             for i, data_point in enumerate(trajectory_data[:3]):
    #                 print(
    #                     f"  {i + 1}: 时间={data_point[0]}, x={data_point[1]:.2f}, y={data_point[2]:.2f}, z={data_point[3]:.2f}")
    #
    #         return {
    #             'success': True,
    #             'data': trajectory_data,
    #             'total_count': total_count,
    #             'message': f'成功获取 {len(trajectory_data)} 条轨迹数据'
    #         }
    #
    #     except Exception as e:
    #         error_msg = f"获取轨迹数据失败: {e}"
    #         print(error_msg)
    #         import traceback
    #         traceback.print_exc()
    #         return {
    #             'success': False,
    #             'data': [],
    #             'total_count': 0,
    #             'message': error_msg
    #         }
    """
    @author wangjie
    @create_time 2025-11-27
    @end
    """


    """
    @author wangjie
    @create_time 2025-12-01
    @start
    """
    def get_trajectory_data(self, cage_id, limit=None):
        """
        获取指定鼠笼的轨迹数据

        Args:
            cage_id (int): 鼠笼编号
            limit (int, optional): 限制返回的数据条数

        Returns:
            dict: 包含轨迹数据和相关信息的字典
        """
        try:
            logger.info(f"=== 开始获取鼠笼 {cage_id} 的轨迹数据 ===")

            table_name = f"MouseDeepPosition_data_cage_{cage_id}"

            # 检查表是否存在
            if not self.sqlite_manager.check_table_exists(table_name):
                return {
                    'success': False,
                    'data': [],
                    'total_count': 0,
                    'message': f'鼠笼 {cage_id} 的数据表不存在'
                }

            # 获取总数据条数
            total_count = self.sqlite_manager.get_table_data_count(table_name)
            logger.info(f"表 {table_name} 中的数据总数: {total_count}")

            # 获取XYZ轨迹数据 - 注意这里不要查询time列
            rows = self.sqlite_manager.get_trajectory_xyz_data(table_name, limit=limit)

            # 防御性检查：确保 rows 不是 None
            if rows is None:
                logger.error("⚠️ 警告：查询返回了 None")
                rows = []

            logger.info(f"实际获取到 {len(rows)} 条轨迹数据")

            # 转换数据格式
            trajectory_data = []
            valid_count = 0
            null_count = 0

            for row in rows:
                try:
                    image_name, x, y, z = row

                    # 处理null值
                    x_val = float(x) if x is not None else None
                    y_val = float(y) if y is not None else None
                    z_val = float(z) if z is not None else None

                    if x_val is not None and y_val is not None and z_val is not None:
                        valid_count += 1
                    else:
                        null_count += 1

                    trajectory_data.append([
                        image_name,
                        x_val,
                        y_val,
                        z_val
                    ])
                except Exception as row_error:
                    logger.error(f"处理数据行时出错: {row}, 错误: {row_error}")
                    continue

            logger.info(f"📊 数据统计: 总共 {len(trajectory_data)} 条, 有效 {valid_count} 条, null {null_count} 条")

            if len(trajectory_data) > 0:
                logger.info(f"数据示例 - 前3条:")
                for i, data_point in enumerate(trajectory_data[:3]):
                    try:
                        x_str = f"{data_point[1]:.3f}" if data_point[1] is not None else "null"
                        y_str = f"{data_point[2]:.3f}" if data_point[2] is not None else "null"
                        z_str = f"{data_point[3]:.3f}" if data_point[3] is not None else "null"
                        logger.info(f"  {i + 1}: 图像={data_point[0]}, x={x_str}, y={y_str}, z={z_str}")
                    except Exception as e:
                        logger.error(f"  {i + 1}: 数据格式错误: {data_point}")

            return {
                'success': True,
                'data': trajectory_data,
                'total_count': len(trajectory_data),
                'valid_count': valid_count,
                'null_count': null_count,
                'message': f'成功获取 {len(trajectory_data)} 条轨迹数据 (有效: {valid_count}, 无效: {null_count})'
            }

        except Exception as e:
            error_msg = f"获取轨迹数据失败: {e}"
            logger.error(error_msg)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'data': [],
                'total_count': 0,
                'message': error_msg
            }

    """
    @author wangjie
    @create_time 2025-12-01
    @end
    """

    """
    @author wangjie
    @create_time 2025-12-29
    @start
    """
    def get_trajectory_data(self):
        """获取轨迹数据"""
        try:
            cursor = self.conn.cursor()
            query = """
                    SELECT image_name, \
                           median_X, \
                           median_Y, \
                           median_Z,
                           center_X, \
                           center_Y, \
                           center_Z, \
                           confidence, \
                           num_contour_points
                    FROM trajectory_data
                    ORDER BY image_name \
                    """
            cursor.execute(query)
            rows = cursor.fetchall()

            # 转换为字典列表
            columns = ['image_name', 'median_X', 'median_Y', 'median_Z',
                       'center_X', 'center_Y', 'center_Z', 'confidence', 'num_contour_points']

            result = []
            for row in rows:
                result.append(dict(zip(columns, row)))

            return result
        except Exception as e:
            logger.error(f"获取轨迹数据失败: {e}")
            return []

    """
    @author wangjie
    @create_time 2025-12-29
    @end
    """

    """
    @author wangjie
    @create_time 2026-1-5
    @start
    """

    def get_all_cage_ids(self, table_prefix='DetectionResults_data_cage') -> List[int]:
        """
        获取指定类型表的笼子编号
        :param table_prefix: 表前缀，如 'DetectionResults_data_cage', 'MouseInfrared_data_cage' 等
        """
        try:
            with self.execute_transaction(auto_commit=True) as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    f"AND name LIKE '{table_prefix}_%' "
                    "AND name NOT LIKE '%_meta'"
                )
                tables = cursor.fetchall()

                cage_ids = []
                for table_tuple in tables:
                    table_name = table_tuple[0]
                    cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                    count = cursor.fetchone()[0]

                    if count > 0:
                        import re
                        match = re.search(r'cage_(\d+)$', table_name)
                        if match:
                            cage_id = int(match.group(1))
                            cage_ids.append(cage_id)
                            logger.info(f"笼子 {cage_id} 在表 {table_name} 有 {count} 条数据")

                cage_ids = sorted(set(cage_ids))
                return cage_ids

        except Exception as e:
            logger.error(f"获取笼子ID失败: {e}")
            return []

    def get_trajectory_data_by_cage(self, cage_id: int) -> List[Dict[str, Any]]:
        """
        获取指定笼子的轨迹数据 (center_x, center_y, center_z)
        从 DetectionResults_data_cage_* 表中查询

        Args:
            cage_id: 笼子编号

        Returns:
            轨迹数据列表，每个元素包含:
            {
                'center_x': float,   # X坐标 (水平)
                'center_y': float,   # Y坐标 (高度)
                'center_z': float,   # Z坐标 (深度)
            }
        """
        try:
            # 调用 SQLiteManager 的方法获取轨迹数据
            trajectory_data = self.sqlite_manager.get_trajectory_data_by_cage(cage_id=cage_id)

            logger.info(f"笼子 {cage_id} 查询到 {len(trajectory_data)} 个轨迹点")
            return trajectory_data

        except Exception as e:
            logger.error(f"查询笼子 {cage_id} 的轨迹数据失败: {e}")
            return []

    def get_cage_data_count(self, cage_id: int) -> int:
        """
        获取指定笼子的数据点数量

        Args:
            cage_id: 笼子编号

        Returns:
            数据点数量
        """
        try:
            table_name = f"DetectionResults_data_cage_{cage_id}"

            # 检查表是否存在
            if not self.sqlite_manager.is_exist_table(table_name):
                logger.warning(f"表 {table_name} 不存在")
                return 0

            with self.sqlite_manager.execute_transaction(auto_commit=True) as cursor:
                cursor.execute(
                    f'SELECT COUNT(*) FROM "{table_name}" '
                    f'WHERE center_x IS NOT NULL AND center_y IS NOT NULL AND center_z IS NOT NULL'
                )
                result = cursor.fetchone()
                count = result[0] if result else 0
                logger.debug(f"笼子 {cage_id} 有效数据点数量: {count}")
                return count

        except Exception as e:
            logger.error(f"获取笼子 {cage_id} 数据数量失败: {e}")
            return 0

    """
    @author wangjie
    @create_time 2026-1-5
    @end
    """
