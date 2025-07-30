import os
from datetime import datetime

from loguru import logger


from public.config_class.global_setting import global_setting
from public.dao.SQLite.SQliteManager import SQLiteManager
from public.function.Modbus.Modbus_Type import Modbus_Slave_Type
# 监控数据操作类
from util.time_util import time_util


class Monitor_Datas_Handle():
    def __init__(self):
        self.sqlite_manager: SQLiteManager = None
        self.init_construct()

    def init_construct(self):
        self.db_name = self.create_db()
        if self.sqlite_manager is not None:
            self.stop()
        self.sqlite_manager = SQLiteManager(db_name=self.db_name)
        self.create_tables()
        pass

    def stop(self):
        self.sqlite_manager.close()

    def create_db(self):
        """
        创建数据库
        :return:
        """
        year, week_number, weekday = time_util.get_current_week_info()
        # 定义文件夹路径
        folder_path =os.getcwd()+ global_setting.get_setting('monitor_data')['STORAGE']['fold_path'] + os.path.join(

            global_setting.get_setting('monitor_data')['STORAGE']['sub_fold_path'], f'{year}', f'{week_number:02}')

        # 创建文件夹（如果不存在）
        os.makedirs(folder_path, exist_ok=True)
        db_name = f"{weekday}.db"
        db_file_path = os.path.join(folder_path, db_name)
        return db_file_path

    def create_tables(self):
        # 实例化公共传感器数据的数据表
        for data_type in Modbus_Slave_Type.Not_Each_Mouse_Cage.value:
            for table_name_short in data_type.value['table']:
                # 列
                columns = {item[0]: item[2] for item in data_type.value['table'][table_name_short]['column']}
                # 表名称
                table_name = f"{data_type.value['name']}_{table_name_short}"
                # 创建表
                if not self.sqlite_manager.is_exist_table(table_name):
                    self.sqlite_manager.create_table(table_name,
                                                     columns)
                    logger.info(f"数据库{self.db_name}创建数据表{table_name}成功！")
                # 创建该表描述的表
                table_meta_name = f"{table_name}_meta"
                # 不存在则创建和插入
                if not self.sqlite_manager.is_exist_table(table_meta_name):
                    self.sqlite_manager.create_meta_table(table_meta_name)
                    logger.info(f"数据库{self.db_name}创建表结构描述数据表{table_meta_name}成功！")
                    # 插入描述信息
                    for item in data_type.value['table'][table_name_short]['column']:
                        self.sqlite_manager.insert(table_meta_name, item_name=item[0], item_struct=item[2],
                                                   description=item[1])
            pass
        # 实例化每个笼子里的传感器的数据表
        for data_type in Modbus_Slave_Type.Each_Mouse_Cage.value:
            for carge_number in range(1, int(global_setting.get_setting("configer")['mouse_cage']['nums']) + 1 if
            int(global_setting.get_setting("configer")['mouse_cage']['nums']) is not None else 2):
                for table_name_short in data_type.value['table']:
                    # 列
                    columns = {item[0]: item[2] for item in data_type.value['table'][table_name_short]['column']}
                    # 表名称
                    table_name = f"{data_type.value['name']}_{table_name_short}_cage_{carge_number}"
                    # 创建表
                    if not self.sqlite_manager.is_exist_table(table_name):
                        self.sqlite_manager.create_table(table_name,
                                                         columns)
                        logger.info(f"数据库{self.db_name}创建数据表{table_name}成功！")
                    # 创建该表描述的表
                    table_meta_name = f"{table_name}_meta"
                    # 不存在则创建和插入
                    if not self.sqlite_manager.is_exist_table(table_meta_name):
                        logger.info(f"数据库{self.db_name}创建表结构描述数据表{table_meta_name}成功！")
                        self.sqlite_manager.create_meta_table(table_meta_name)
                        # 插入描述信息
                        for item in data_type.value['table'][table_name_short]['column']:
                            self.sqlite_manager.insert(table_meta_name, item_name=item[0], item_struct=item[2],
                                                       description=item[1])
        pass

    def insert_data(self, data):
        # 添加数据到表里
        if data is not None:
            # 公共传感器：
            if data['mouse_cage_number'] == 0:
                # 获取该表名称
                table_name = f"{data['module_name']}_{data['table_name']}"
                # # 获取该表的column项
                table_name_meta = f"{table_name}_meta"
                columns_query = self.sqlite_manager.query(table_name_meta)
                columns = [i[0] for i in columns_query if i[0] != 'id']
                datas = [i['value'] for i in data['data']]
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # 本地时间格式
                datas.append(current_time)
                result = self.sqlite_manager.insert_2(table_name, columns, datas)
                if result == 1:
                    logger.info(f"数据插入表{table_name}成功！")
                else:
                    logger.info(f"数据插入表{table_name}失败！")
            else:  # 每个鼠笼传感器：
                # 获取该表名称
                table_name = f"{data['module_name']}_{data['table_name']}_cage_{data['mouse_cage_number']}"
                # # 获取该表的column项
                table_name_meta = f"{table_name}_meta"
                columns_query = self.sqlite_manager.query(table_name_meta)
                columns = [i[0] for i in columns_query if i[0] != 'id']
                datas = [i['value'] for i in data['data']]
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # 本地时间格式
                datas.append(current_time)
                result = self.sqlite_manager.insert_2(table_name, columns, datas)
                if result == 1:
                    logger.info(f"数据插入表{table_name}成功！")
                else:
                    logger.info(f"数据插入表{table_name}失败！")
                pass
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
            # 不要id 和time
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
            # 不要id 和time
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
            # 不要id 和time
            results = results_query
        return results
        pass
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
        获取表结构数据 item_desc
        :param table_name:
        :return:
        """
        columns_query = self.sqlite_manager.query(f"{table_name}_meta")
        columns_desc = []
        if columns_query is not None and len(columns_query) > 0:
            columns_desc = [{'desc':i[2],'name':i[0]} for i in columns_query][1:-1]
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