import sqlite3

from loguru import logger


class SQLiteManager():
    TIME_COLUMN_NAME = 'time'

    def __init__(self, db_name):
        """初始化数据库连接."""
        self.connection = sqlite3.connect(db_name)
        # WAL模式提供更好的并发性，读取器不会阻塞写入器，反之亦然
        self.connection.execute('PRAGMA journal_mode=WAL')  # 启用WAL模式
        # logger.info(f"数据库{db_name}连接成功")
        self.cursor = self.connection.cursor()

    def is_exist_table(self, table_name):
        """查询数据表是否存在"""
        sql = f"""
        SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';
        """
        self.cursor.execute(sql)

        # 获取结果
        result = self.cursor.fetchone()
        # 如果结果不为 None，则表存在
        return result is not None

    def create_table(self, table_name, columns):
        """创建表."""
        columns_with_types = ', '.join(f"{name} {datatype}" for name, datatype in columns.items())
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_with_types}) ;"
        self.cursor.execute(sql)
        self.connection.commit()

    def create_meta_table(self, table_name):
        """创建描述表"""
        sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            item_name TEXT PRIMARY KEY,
            item_struct TEXT, --数据类型 比如TEXT REAL等
            description TEXT
            );   
        """
        self.cursor.execute(sql)
        self.connection.commit()

    def insert(self, table_name, **kwargs):
        """插入数据，防止 SQL 注入."""
        columns = ', '.join(kwargs.keys())
        placeholders = ', '.join('?' * len(kwargs))  # 使用 ? 占位符
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders});"
        self.cursor.execute(sql, tuple(kwargs.values()))  # 使用参数化查询
        self.connection.commit()
        return self.cursor.rowcount

    def insert_2(self, table_name, columns_flag, datas):
        """插入数据，防止 SQL 注入."""
        columns = ', '.join(columns_flag)
        placeholders = ', '.join('?' * len(datas))  # 使用 ? 占位符
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders});"
        self.cursor.execute(sql, tuple(datas))  # 使用参数化查询
        self.connection.commit()
        return self.cursor.rowcount

    def insert_not_columns(self, table_name, datas):
        placeholders = ', '.join('?' * len(datas))  # 使用 ? 占位符
        sql = f"INSERT INTO {table_name}  VALUES ({placeholders});"
        self.cursor.execute(sql, tuple(datas))  # 使用参数化查询
        self.connection.commit()
        return self.cursor.rowcount
        pass

    def query_conditions(self, table_name, conditions=""):
        """查询数据，."""
        sql = f"SELECT * FROM {table_name} "
        sql += conditions
        self.cursor.execute(sql)

        return self.cursor.fetchall()
    def query_counts_conditions(self, table_name, conditions=""):
        """查询数据，."""
        sql = f"SELECT COUNT(*) FROM {table_name} "
        sql += conditions
        self.cursor.execute(sql)

        return self.cursor.fetchone()[0]
    def query(self, table_name, **kwargs):
        """查询数据，防止 SQL 注入."""
        sql = f"SELECT * FROM {table_name}"
        if kwargs:
            conditions = ' AND '.join(f"{key} = ?" for key in kwargs.keys())
            sql += f" WHERE {conditions};"
            self.cursor.execute(sql, tuple(kwargs.values()))  # 使用参数化查询
        else:
            self.cursor.execute(sql)

        return self.cursor.fetchall()

    def query_current_Data(self, table_name, **kwargs):
        """查询数据，防止 SQL 注入."""
        sql = f"SELECT * FROM {table_name}"
        if kwargs:
            conditions = ' AND '.join(f"{key} = ?" for key in kwargs.keys())
            sql += f" WHERE {conditions} "
            sql += f" ORDER BY time DESC LIMIT 1 ;"
            self.cursor.execute(sql, tuple(kwargs.values()))  # 使用参数化查询
        else:
            sql += f" ORDER BY time DESC LIMIT 1 ;"
            self.cursor.execute(sql)

        return self.cursor.fetchall()

    def query_current_Data_columns(self, table_name, columns, **kwargs):
        """查询数据，防止 SQL 注入."""
        columns_sql = ', '.join(columns)
        sql = f"SELECT {columns_sql} FROM {table_name}"
        if kwargs:
            conditions = ' AND '.join(f"{key} = ?" for key in kwargs.keys())
            sql += f" WHERE {conditions} "
            sql += f" ORDER BY time DESC LIMIT 1 ;"
            self.cursor.execute(sql, tuple(kwargs.values()))  # 使用参数化查询
        else:
            sql += f" ORDER BY time DESC LIMIT 1 ;"
            self.cursor.execute(sql)

        return self.cursor.fetchall()
    def query_paging(self, table_name, rows_per_page, start_row,conditions=""):
        """查询数据，."""
        sql = f"SELECT * FROM {table_name} "
        sql += conditions
        sql+=f" ORDER BY id DESC LIMIT {rows_per_page} OFFSET {start_row}"
        self.cursor.execute(sql)

        return self.cursor.fetchall()
        pass
    def update(self, table_name, criteria, **kwargs):
        """更新数据，防止 SQL 注入."""
        set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
        conditions = ' AND '.join(f"{key} = ?" for key in criteria.keys())
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {conditions};"
        self.cursor.execute(sql, tuple(kwargs.values()) + tuple(criteria.values()))  # 使用参数化查询
        self.connection.commit()

    def delete(self, table_name, **kwargs):
        """删除数据，防止 SQL 注入."""
        conditions = ' AND '.join(f"{key} = ?" for key in kwargs.keys())
        sql = f"DELETE FROM {table_name} WHERE {conditions};"
        self.cursor.execute(sql, tuple(kwargs.values()))  # 使用参数化查询
        self.connection.commit()

    def close(self):
        """关闭数据库连接."""
        self.cursor.close()
        self.connection.close()




class ReadOnlyUser(SQLiteManager):
    """读取用户类."""

    def __init__(self, db_name):
        super().__init__(db_name)

    def insert(self, *args, **kwargs):
        raise PermissionError("该用户没有写入权限。")

    def update(self, *args, **kwargs):
        raise PermissionError("该用户没有写入权限。")

    def delete(self, *args, **kwargs):
        raise PermissionError("该用户没有写入权限。")


class WriteOnlyUser(SQLiteManager):
    """写入用户类."""

    def __init__(self, db_name):
        super().__init__(db_name)

    def query(self, *args, **kwargs):
        raise PermissionError("该用户没有读取权限。")


def test():
    db = SQLiteManager('example.db')

    # 创建表
    db.create_table('users', {'id': 'INTEGER PRIMARY KEY AUTOINCREMENT', 'name': 'TEXT', 'age': 'INTEGER'})

    # 插入数据
    db.insert('users', name='Alice', age=30)
    db.insert('users', name='Bob', age=25)

    # 查询数据
    print("所有用户:", db.query('users'))
    print("查询年龄为30的用户:", db.query('users', age=30))

    # 更新数据
    db.update('users', {'name': 'Alice'}, age=31)

    # 查询更新后的数据
    print("更新后所有用户:", db.query('users'))

    # 删除数据
    db.delete('users', name='Bob')

    # 查询删除后的数据
    print("删除后所有用户:", db.query('users'))

    # 关闭数据库连接
    db.close()
    # 读取用户示例
    read_user = ReadOnlyUser('example.db')
    # 尝试写入读取用户（会引发权限错误）
    try:
        read_user.insert('users', name='Charlie', age=40)
    except PermissionError as e:
        print(e)

    # 写入用户示例
    write_user = WriteOnlyUser('example.db')
    # 尝试读取写入用户（会引发权限错误）
    try:
        print(write_user.query('users'))
    except PermissionError as e:
        print(e)


if __name__ == "__main__":
    test()
