import sqlite3
import pandas as pd
import re

# 连接数据库
conn = sqlite3.connect('data.db')

# 获取所有表名（排除系统表）
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
all_tables = [row[0] for row in cursor.fetchall() if not row[0].startswith('sqlite_')]

# 分离数据表和元数据表
all_data_tables = [table for table in all_tables if not table.endswith('_meta')]
meta_tables = [table for table in all_tables if table.endswith('_meta')]

# 排除末尾数字为2-8的数据表
data_tables = []
for table in all_data_tables:
    # 检查表名是否以数字2-8结尾
    if re.search(r'[2-8]$', table):
        print(f"跳过表: {table} (末尾数字为2-8)")
        continue
    data_tables.append(table)

print(f"发现数据表: {data_tables}")
print(f"发现元数据表: {meta_tables}")

# 导出到Excel
with pd.ExcelWriter('data_export.xlsx', engine='xlsxwriter') as writer:
    # 导出数据表
    for table_name in data_tables:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
            df.to_excel(writer, sheet_name=table_name, index=False)
            print(f"已导出数据表: {table_name}")
        except Exception as e:
            print(f"导出数据表 {table_name} 时出错: {e}")

    # # 导出对应的元数据表
    # for table_name in data_tables:
    #     meta_table_name = f"{table_name}_meta"
    #     if meta_table_name in meta_tables:
    #         try:
    #             meta_df = pd.read_sql_query(f"SELECT * FROM {meta_table_name}", conn)
    #             meta_df.to_excel(writer, sheet_name=meta_table_name, index=False)
    #             print(f"已导出元数据表: {meta_table_name}")
    #         except Exception as e:
    #             print(f"导出元数据表 {meta_table_name} 时出错: {e}")
    #     else:
    #         print(f"警告: 未找到对应的元数据表 {meta_table_name}")

conn.close()
print("数据导出完成!")