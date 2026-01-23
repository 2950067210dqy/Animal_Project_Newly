import sqlite3
import logging

logger = logging.getLogger(__name__)


class DatabaseHandler:
    def __init__(self):
        self.connection = None
        self.db_path = None

    def connect_database(self, db_path):
        """连接数据库"""
        try:
            if self.connection:
                self.connection.close()

            self.db_path = db_path
            self.connection = sqlite3.connect(db_path)
            logger.info(f"数据库连接成功: {db_path}")
            return True

        except Exception as e:
            logger.error(f"连接数据库失败: {e}")
            return False

    def get_tables(self):
        """获取所有表名"""
        if not self.connection:
            return []

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            return [table[0] for table in tables]
        except Exception as e:
            logger.error(f"获取表名失败: {e}")
            return []

    def get_table_columns(self, table_name):
        """获取表的列信息"""
        if not self.connection or not table_name:
            return []

        try:
            cursor = self.connection.cursor()
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns_info = cursor.fetchall()
            return [col[1] for col in columns_info]
        except Exception as e:
            logger.error(f"获取表列信息失败: {e}")
            return []

    def get_table_count(self, table_name):
        """获取表的记录数"""
        if not self.connection or not table_name:
            return 0

        try:
            cursor = self.connection.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"获取表记录数失败: {e}")
            return 0

    def load_table_data(self, table_name, limit=1000):
        """加载表数据"""
        if not self.connection or not table_name:
            return []

        try:
            cursor = self.connection.cursor()
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"加载表数据失败: {e}")
            return []

    def close_connection(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None
