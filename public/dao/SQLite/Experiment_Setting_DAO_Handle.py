import os

from sympy.external.gmpy import remove

from public.config.experiment_setting_config import Setting_Table
from public.dao.SQLite.SQliteManager import SQLiteManager

from loguru import logger

from public.entity.experiment_setting_entity import Experiment_setting_entity, Group, Animal, AnimalGroupRecord
from public.util.class_util import class_util


class Experiment_Setting_DAO_Handle():
    def __init__(self,db_fold_path,db_name):
        """

        :param db_file_name:数据库文件路径
        """
        self.db_fold_path = db_fold_path
        self.db_name =os.path.join(self.db_fold_path, db_name)
        self.sqlite_manager: SQLiteManager = None
        self.init_construct()
    def init_construct(self):

        # 创建文件夹（如果不存在）
        os.makedirs(self.db_fold_path, exist_ok=True)
        if self.sqlite_manager is not None:
            self.stop()
        self.sqlite_manager = SQLiteManager(db_name=self.db_name)
        self.create_tables()
        pass
    def stop(self):
        self.sqlite_manager.close()
    def create_tables(self):
        # 实例化实验配置的数据表
        for table in Setting_Table:
            # 列
            columns = {item[0]: item[2] for item in table.value['column']}
            # 表名称
            table_name = f"{table.value['table_name']}"
            # 创建表
            if not self.sqlite_manager.is_exist_table(table_name):
                self.sqlite_manager.create_table(table_name,
                                                 columns)
                logger.info(f"数据库{ self.db_name}创建数据表{table_name}成功！")
            # 创建该表描述的表
            table_meta_name = f"{table_name}_meta"
            # 不存在则创建和插入
            if not self.sqlite_manager.is_exist_table(table_meta_name):
                self.sqlite_manager.create_meta_table(table_meta_name)
                logger.info(f"数据库{ self.db_name}创建表结构描述数据表{table_meta_name}成功！")
                # 插入描述信息
                for item in table.value['column']:
                    self.sqlite_manager.insert(table_meta_name, item_name=item[0], item_struct=item[2],
                                               description=item[1])
            pass
    def insert_data(self, data:Experiment_setting_entity):
        insert_state=[]
        # 添加数据到表里
        if data is not None:
            # group表
            for group in data.groups:
                group:Group
                table_name = Setting_Table.Group.value['table_name']
                # # 获取该表的column项
                table_name_meta = f"{table_name}_meta"
                columns_query = self.sqlite_manager.query(table_name_meta)
                columns= [i[0] for i in columns_query ]
                group_attr:dict=class_util.get_public_attributes_with_notes(group)
                datas = [group_attr.get(column,None)['value'] if group_attr.get(column,None) else None for column in columns ]
                result = self.sqlite_manager.insert_2(table_name, columns, datas)
                if result == 1:
                    insert_state.append(True)
                    logger.info(f"数据插入表{table_name}成功！")
                else:
                    insert_state.append(False)
                    logger.info(f"数据插入表{table_name}失败！")
           #Animal 表
            for animal in data.animals:
                animal:Animal
                table_name = Setting_Table.Animal.value['table_name']
                # # 获取该表的column项
                table_name_meta = f"{table_name}_meta"
                columns_query = self.sqlite_manager.query(table_name_meta)
                columns = [i[0] for i in columns_query]
                group_attr: dict = class_util.get_public_attributes_with_notes(animal)
                datas = [group_attr.get(column, None)['value'] if group_attr.get(column,
                                                                                                 None) else None
                         for column in columns]
                result = self.sqlite_manager.insert_2(table_name, columns, datas)
                if result == 1:
                    insert_state.append(True)
                    logger.info(f"数据插入表{table_name}成功！")
                else:
                    insert_state.append(False)
                    logger.info(f"数据插入表{table_name}失败！")
            #关系表
            for animalGroupRecord in data.animalGroupRecords:
                animalGroupRecord:AnimalGroupRecord
                table_name = Setting_Table.Group_Animal.value['table_name']
                # # 获取该表的column项
                table_name_meta = f"{table_name}_meta"
                columns_query = self.sqlite_manager.query(table_name_meta)
                columns = [i[0] for i in columns_query]
                group_attr: dict = class_util.get_public_attributes_with_notes(animalGroupRecord)
                datas = [group_attr.get(column, None)['value'] if group_attr.get(column,
                                                                                               None) else None
                         for column in columns]
                result = self.sqlite_manager.insert_2(table_name, columns, datas)
                if result == 1:
                    insert_state.append(True)
                    logger.info(f"数据插入表{table_name}成功！")
                else:
                    insert_state.append(False)
                    logger.info(f"数据插入表{table_name}失败！")
        return all(insert_state) if len(insert_state) > 0 else False
    def query_data_database_all(self):
        """
        获取数据库所有表的数据
        :return:
        """
        groups = []
        animals = []
        animalGroupRecords = []
        experiment_setting_entity=Experiment_setting_entity()
        for table in Setting_Table:
            # 表名称
            table_name = f"{table.value['table_name']}"
            # # 获取该表的column项
            table_name_meta = f"{table_name}_meta"
            columns_query = self.sqlite_manager.query(table_name_meta)
            columns = [i[0] for i in columns_query]
            results = self.query_data_table_all(table_name)
            for result in results:
                match table:
                    case Setting_Table.Group:
                        # 创建一个 group 实例，确保传入的参数有匹配类的构造函数
                        group_data = {column: result[i] for i, column in enumerate(columns)}
                        # 实例化 Group 对象
                        group = Group(**group_data)  # 使用解包操作符传递字典参数
                        groups.append(group)
                        pass
                    case Setting_Table.Animal:
                        # 创建一个 animal 实例，确保传入的参数有匹配类的构造函数
                        animal_data = {column: result[i] for i, column in enumerate(columns)}
                        # 实例化 animal 对象
                        animal =Animal(**animal_data)  # 使用解包操作符传递字典参数
                        animals.append( animal)
                        pass
                    case Setting_Table.Group_Animal:
                        # 创建一个 animal_group_record 实例，确保传入的参数有匹配类的构造函数
                        animal_group_record_data = {column: result[i] for i, column in enumerate(columns)}
                        # 实例化 animal_group_record 对象
                        animal_group_record = AnimalGroupRecord(**animal_group_record_data)  # 使用解包操作符传递字典参数
                        animalGroupRecords.append(animal_group_record)
                        pass
                    case _:
                        pass
        experiment_setting_entity.groups=groups
        experiment_setting_entity.animals=animals
        experiment_setting_entity.animalGroupRecords=animalGroupRecords
        return experiment_setting_entity

    def query_data_table_all(self, table_name):
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
    def remove_data_database_all_not_include_metaDB(self):
        """
        删除数据库中的所有数据表的数据，不包括数据表描述的数据表数据
        :return:
        """
        deleted_state=[]
        for table in Setting_Table:
            # 表名称
            table_name = f"{table.value['table_name']}"
            results_query = self.sqlite_manager.query_counts_conditions(table_name)

            results = 0
            if results_query is not None:
                results = results_query
            if results == 0:
                #空表就不删除
                deleted_state.append(True)
            else:
                deleted_state.append(self.remove_data_table_all(table_name))
        # print(deleted_state)
        return all(deleted_state) if len(deleted_state) > 0 else False
    def remove_data_table_all(self,table_name):
        """
        删除数据表中的所有数据
        :param table_name:
        :return:
        """
        result = self.sqlite_manager.delete(table_name)
        return result
