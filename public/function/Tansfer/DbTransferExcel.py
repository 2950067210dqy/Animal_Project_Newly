#sqlite db文件转成excel文件
import re
from pathlib import Path
from typing import List, Tuple

import pandas as pd
from loguru import logger

from public.dao.SQLite.Monitor_Datas_Handle import Monitor_Datas_Handle


class DbTransferExcel():
    INVALID_SHEET_CHARS = r'[:\\/*?\[\]]'
    MAX_SHEET_LEN = 31
    def __init__(self,db_name=None):
        self.handler = Monitor_Datas_Handle(db_name)
        pass
    def stop(self):
        self.handler.stop()


    def sanitize_sheet_name(self,name: str, used: set) -> str:
        # 删除非法字符，替换为空格，截断到 31 字符，确保唯一（添加数字后缀）
        s = re.sub(self.INVALID_SHEET_CHARS, " ", name)
        s = s.strip()
        if not s:
            s = "sheet"
        if len(s) > self.MAX_SHEET_LEN:
            s = s[:self.MAX_SHEET_LEN]
        base = s
        i = 1
        while s in used:
            suffix = f"_{i}"
            allowed_len = self.MAX_SHEET_LEN - len(suffix)
            s = (base[:allowed_len] + suffix) if len(base) > allowed_len else (base + suffix)
            i += 1
        used.add(s)
        return s

    def get_table_list(self) -> List[Tuple[str, str]]:
        # 返回 (name, type) 列表，排除 sqlite_ 开头的内部表

        self.handler.sqlite_manager.cursor.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%meta%' ORDER BY name"
        )
        return self.handler.sqlite_manager.cursor.fetchall()



    def convert_bytes_columns(self,df: pd.DataFrame) -> pd.DataFrame:
        # 将 bytes/bytearray/memoryview 转为 hex 字符串（可读）
        for col in df.columns:
            # 查找列中是否存在 bytes-like
            sample = df[col].dropna()
            if sample.empty:
                continue
            first = sample.iloc[0]
            if isinstance(first, (bytes, bytearray, memoryview)):
                df[col] = df[col].apply(lambda x: x.hex() if isinstance(x, (bytes, bytearray, memoryview)) else x)
        return df

    def export_db_to_excel(self,writer: pd.ExcelWriter, combine_mode: bool, sheet_used: set,
                           chunksize: int = None):

        try:
            tables = self.get_table_list()
            if not tables:

                return

            for name, typ in tables:
                # 构造 sheet 名

                raw_sheet = name
                sheet_name = self.sanitize_sheet_name(raw_sheet, sheet_used)

                sql = f"SELECT * FROM {name}"
                logger.info(f"[INFO] 从 db 的 {typ} {name} 导出到 sheet '{sheet_name}' ...")
                if chunksize and chunksize > 0:
                    startrow = 0
                    # 使用 pandas.read_sql_query 的 chunksize 返回迭代器
                    for i, chunk in enumerate(pd.read_sql_query(sql, self.handler.sqlite_manager.connection, chunksize=chunksize)):
                        df = self.convert_bytes_columns(chunk)
                        # header 仅写入第一块
                        header = (startrow == 0)
                        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=startrow, header=header)
                        startrow += len(df)
                else:
                    df = pd.read_sql_query(sql, self.handler.sqlite_manager.connection,)
                    df = self.convert_bytes_columns(df)
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
        finally:
            self.handler.stop()
    pass