import math
import sqlite3
from typing import List, Dict, Any

from loguru import logger


class SQLiteManager():
    TIME_COLUMN_NAME = 'time'

    def __init__(self, db_name):
        """初始化数据库连接."""
        #check_same_thread 参数设置为 False，这将允许在多个线程之间共享连接。但这样做会引入线程安全问题
        self.connection = sqlite3.connect(db_name,check_same_thread=False)
        # WAL模式提供更好的并发性，读取器不会阻塞写入器，反之亦然
        # self.connection.execute('PRAGMA journal_mode=WAL')  # 启用WAL模式
        # logger.info(f"数据库{db_name}连接成功")
        self.cursor = self.connection.cursor()

    def quote_ident(self,name: str) -> str:
        """用双引号安全引用 SQLite 标识符（表名或列名）。"""
        return '"' + name.replace('"', '""') + '"'

    def get_non_meta_tables_with_time(self,exclude_substr="meta",columns:list =['time']) -> List[str]:
        """
        返回数据库中不包含 'meta'（不区分大小写）的表名，并且该表具有 columns列。
        """
        cur = self.connection.cursor()
        # 先找出所有表（排除 name 包含 meta 的）
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) NOT LIKE ?",
            ("% %meta%".replace(" ", ""),)  # just to keep placeholder style; simplified below
        )
        # Above is awkward with placeholder; do simpler:
        cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND lower(name) NOT LIKE '%{exclude_substr}%'")
        rows = cur.fetchall()
        tables = [r[0] for r in rows]

        good = []
        for t in tables:
            q = self.quote_ident(t)
            # 获取表结构，判断是否存在 columns 列（列名完全为 column）
            cur.execute(f"PRAGMA table_info({q})")
            cols = [r[1] for r in cur.fetchall()]  # PRAGMA table_info 返回 rows: (cid,name,type,...)
            if  all([column in cols for column in columns]):
                good.append(t)
        return good

    def build_all_times_sql(self,tables: List[str]) -> str:
        """
        构造用于 all_times 的子查询 SQL（UNION 去重）。
        例如: SELECT time FROM "t1" UNION SELECT time FROM "t2"
        """
        selects = [f"SELECT time FROM {self.quote_ident(t)}" for t in tables]
        return " UNION ".join(selects)

    def count_all_times(self, all_times_sql: str) -> int:
        """统计 all_times 的行数（即所有表 time 的并集大小）。"""
        count_sql = f"SELECT COUNT(*) FROM ({all_times_sql}) AS _all_times_count"
        self.cursor.execute(count_sql)
        return  self.cursor.fetchone()[0] or 0

    def query_joined_by_time(self,
            tables: List[str],
            page: int = 1,
            page_size: int = 100,
            order_asc: bool = True
    ) -> Dict[str, Any]:
        """
        把传入的表按 time 字段联立并分页返回结果，返回字典包含:
          - total_items: 总行数（time 的并集大小）
          - total_pages
          - page (实际返回页，1-based)
          - page_size
          - columns: 列名列表（与 rows 中 dict 的 key 对应）
          - rows: 列表，每行为 dict（key=列名, value=值）
        """
        if page_size <= 0:
            raise ValueError("page_size must be > 0")
        if not tables:
            return {
                "total_items": 0,
                "total_pages": 0,
                "page": 1,
                "page_size": page_size,
                "columns": [],
                "rows": []
            }



        # 构造 all_times SQL
        all_times_sql =self.build_all_times_sql(tables)

        # 统计总条数
        total_items =self. count_all_times(all_times_sql)
        total_pages = max(1, math.ceil(total_items / page_size)) if total_items > 0 else 0

        # 修正 page 边界（1-based）
        if total_pages == 0:
            page = 1
        else:
            page = max(1, min(page, total_pages))

        offset = (page - 1) * page_size

        # 构造 SELECT 列与 JOIN 子句
        select_cols = [f"all_times.time AS {self.quote_ident('time')}"]
        join_clauses = []
        for t in tables:
            q_t = self.quote_ident(t)
            self.cursor.execute(f"PRAGMA table_info({q_t})")
            col_rows = self.cursor.fetchall()
            col_names = [r[1] for r in col_rows]

            # 为该表的每个非 time 列生成别名： table__col
            for col in col_names:
                if col == "time":
                    continue
                alias = f"{t}__{col}"
                # SELECT "table"."col" AS "table__col"
                select_cols.append(f"{q_t}.{self.quote_ident(col)} AS {self.quote_ident(alias)}")

            # LEFT JOIN 表
            join_clauses.append(f"LEFT JOIN {q_t} ON {q_t}.time = all_times.time")

        select_clause = ",\n  ".join(select_cols)
        join_clause = "\n  ".join(join_clauses)
        order = "DESC" if order_asc else "ASC"

        # 最终 SQL，带 LIMIT/OFFSET 用于分页
        final_sql = f"""
    SELECT
      {select_clause}
    FROM
      ({all_times_sql}) AS all_times
      {join_clause}
    ORDER BY all_times.time {order}
    LIMIT ? OFFSET ?
    """

        self.cursor.execute(final_sql, (page_size, offset))
        rows =self.cursor.fetchall()
        colnames = [desc[0] for desc in self.cursor.description]

        result_rows = [dict(zip(colnames, r)) for r in rows]

        return {
            "total_items": total_items,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
            "columns": colnames,
            "rows": result_rows
        }


    def convert_to_foreign_key_sql(self,foreign_key_dict):
        """
        将 foreign_key_dict:{
            "key":['aid','gid'],
            "reference_key":[Animal (id),Group (id)],
        }转换成
        FOREIGN KEY (aid) REFERENCES Animal(id),
        FOREIGN KEY (gid) REFERENCES Group(id)
        sql语句
        :param foreign_key_dict:
        :return:
        """
        foreign_keys = []

        # 获取键和引用键
        keys = foreign_key_dict["key"]
        reference_keys = foreign_key_dict["reference_key"]

        # 确保键和引用键数量一致
        if len(keys) != len(reference_keys):
            return ""

        # 构建 SQL 外键约束语句
        for key, reference in zip(keys, reference_keys):
            table_ref, column_ref = reference.split('(')
            column_ref = column_ref.strip(') ')
            foreign_keys.append(f"FOREIGN KEY ({key}) REFERENCES {table_ref.strip()}({column_ref})")

        # 连接所有的外键语句，用逗号分隔
        return ",\n".join(foreign_keys)
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

    def create_table(self, table_name, columns,foreign_key_dict:dict=None):
        """创建表.
        :param foreign_key_dict:{
            "key":['aid','gid'],
            "reference_key":[Animal (id),Group (id)],
        }
        """
        columns_with_types = ', '.join(f"{name} {datatype}" for name, datatype in columns.items())
        if foreign_key_dict:
            foreign_key_sqls =",\n"+ self.convert_to_foreign_key_sql(foreign_key_dict)
        else:
            foreign_key_sqls = ""
        sql = f"""CREATE TABLE IF NOT EXISTS "{table_name}" (
                        {columns_with_types}{foreign_key_sqls}
                    ) ;"""
        # print(sql)
        self.cursor.execute(sql)
        self.connection.commit()

    def create_meta_table(self, table_name):
        """创建描述表"""
        sql = f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
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
        sql = f"""INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders});"""
        self.cursor.execute(sql, tuple(kwargs.values()))  # 使用参数化查询
        self.connection.commit()
        return self.cursor.rowcount

    def insert_2(self, table_name, columns_flag, datas):
        """插入数据，防止 SQL 注入."""
        columns = ', '.join(columns_flag)
        placeholders = ', '.join('?' * len(datas))  # 使用 ? 占位符
        sql = f"""INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders});"""
        self.cursor.execute(sql, tuple(datas))  # 使用参数化查询
        self.connection.commit()
        return self.cursor.rowcount

    def insert_not_columns(self, table_name, datas):
        placeholders = ', '.join('?' * len(datas))  # 使用 ? 占位符
        sql = f"""INSERT INTO "{table_name}"  VALUES ({placeholders});"""
        self.cursor.execute(sql, tuple(datas))  # 使用参数化查询
        self.connection.commit()
        return self.cursor.rowcount
        pass

    def query_conditions(self, table_name, conditions=""):
        """查询数据，."""
        sql = f"""SELECT * FROM "{table_name}" """
        sql += conditions
        # print(sql)
        self.cursor.execute(sql)

        return self.cursor.fetchall()
    def query_counts_conditions(self, table_name, conditions=""):
        """查询数据，."""
        sql = f"""SELECT COUNT(*) FROM "{table_name}" """
        sql += conditions
        self.cursor.execute(sql)

        return self.cursor.fetchone()[0]
    def query(self, table_name, **kwargs):
        """查询数据，防止 SQL 注入."""
        sql = f"""SELECT * FROM "{table_name}" """
        if kwargs:
            conditions = ' AND '.join(f"{key} = ?" for key in kwargs.keys())
            sql += f" WHERE {conditions};"
            self.cursor.execute(sql, tuple(kwargs.values()))  # 使用参数化查询
        else:
            self.cursor.execute(sql)

        return self.cursor.fetchall()

    def query_current_Data(self, table_name, **kwargs):
        """查询数据，防止 SQL 注入."""
        sql = f"""SELECT * FROM "{table_name}" """
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
        sql = f"""SELECT {columns_sql} FROM "{table_name}" """
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
        sql = f"""SELECT * FROM "{table_name}" """
        sql += conditions
        sql+=f" ORDER BY id DESC LIMIT {rows_per_page} OFFSET {start_row}"
        self.cursor.execute(sql)

        return self.cursor.fetchall()
        pass
    def update(self, table_name, criteria, **kwargs):
        """更新数据，防止 SQL 注入."""
        set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
        conditions = ' AND '.join(f"{key} = ?" for key in criteria.keys())
        sql = f"""UPDATE "{table_name}" SET {set_clause} WHERE {conditions};"""
        self.cursor.execute(sql, tuple(kwargs.values()) + tuple(criteria.values()))  # 使用参数化查询
        self.connection.commit()
        return self.cursor.rowcount
    def delete(self, table_name, **kwargs):
        """删除数据，防止 SQL 注入."""
        conditions = ' AND '.join(f"{key} = ?" for key in kwargs.keys())
        if len(kwargs) > 0:
            conditions = f" WHERE {conditions} "
        sql = f"""DELETE FROM "{table_name}" {conditions} ;"""
        self.cursor.execute(sql, tuple(kwargs.values()))  # 使用参数化查询
        self.connection.commit()
        return self.cursor.rowcount
    def close(self):
        # 使用 PRAGMA wal_checkpoint 进行合并
        # self.connection.execute('PRAGMA wal_checkpoint(TRUNCATE);')#TRUNCATE会删除WAL文件
        # self.connection.execute('PRAGMA journal_mode=DELETE;')  # 将WAL模式变为默认模式
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
