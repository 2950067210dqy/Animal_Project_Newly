# file_reader_handle.py
import pandas as pd
import os
import sqlite3
from typing import List, Tuple, Optional
import numpy as np
from datetime import datetime


class FileReaderHandle:
    """文件读取处理类 - 负责CSV和数据库文件的读取"""

    def __init__(self):
        self.supported_formats = ['.csv', '.xlsx', '.xls']

    class FileReaderHandle:
        def __init__(self):
            self.supported_formats = ['.csv', '.xlsx', '.xls', '.db', '.sqlite', '.sqlite3']

        def auto_detect_file_format(self, file_path: str) -> Optional[pd.DataFrame]:
            """自动检测文件格式并读取"""
            try:
                file_ext = os.path.splitext(file_path)[1].lower()

                if file_ext == '.csv':
                    return self.read_csv_file(file_path)
                elif file_ext in ['.xlsx', '.xls']:
                    return self.read_excel_file(file_path)
                elif file_ext in ['.db', '.sqlite', '.sqlite3']:
                    return self.read_database_file(file_path)
                else:
                    print(f"不支持的文件格式: {file_ext}")
                    return None

            except Exception as e:
                print(f"读取文件失败: {e}")
                return None

        def read_csv_file(self, file_path: str) -> Optional[pd.DataFrame]:
            """读取CSV文件"""
            try:
                # 尝试不同的编码
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']

                for encoding in encodings:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding)
                        print(f"成功读取CSV文件，编码: {encoding}")
                        return df
                    except UnicodeDecodeError:
                        continue

                print("所有编码尝试失败")
                return None

            except Exception as e:
                print(f"读取CSV文件失败: {e}")
                return None

        def read_excel_file(self, file_path: str) -> Optional[pd.DataFrame]:
            """读取Excel文件"""
            try:
                df = pd.read_excel(file_path)
                print("成功读取Excel文件")
                return df
            except Exception as e:
                print(f"读取Excel文件失败: {e}")
                return None

        def read_database_file(self, file_path: str) -> Optional[pd.DataFrame]:
            """读取数据库文件并提取CSV数据"""
            try:
                conn = sqlite3.connect(file_path)

                # 获取数据库中的所有表
                tables = self.get_database_tables(conn)

                if not tables:
                    print("数据库中没有找到表")
                    conn.close()
                    return None

                # 如果只有一个表，直接读取
                if len(tables) == 1:
                    table_name = tables[0]
                    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
                    conn.close()
                    print(f"成功从数据库表 {table_name} 读取数据")
                    return df

                # 如果有多个表，尝试找到最可能包含轨迹数据的表
                best_table = self.find_best_trajectory_table(conn, tables)

                if best_table:
                    df = pd.read_sql_query(f"SELECT * FROM {best_table}", conn)
                    conn.close()
                    print(f"成功从数据库表 {best_table} 读取轨迹数据")
                    return df
                else:
                    # 返回第一个表的数据
                    df = pd.read_sql_query(f"SELECT * FROM {tables[0]}", conn)
                    conn.close()
                    print(f"使用默认表 {tables[0]} 的数据")
                    return df

            except Exception as e:
                print(f"读取数据库文件失败: {e}")
                return None

        def get_database_tables(self, conn) -> List[str]:
            """获取数据库中的所有表名"""
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [table[0] for table in cursor.fetchall()]
                return tables
            except Exception as e:
                print(f"获取数据库表失败: {e}")
                return []

        def get_database_info(self, file_path: str) -> dict:
            """获取数据库文件的详细信息"""
            try:
                conn = sqlite3.connect(file_path)
                info = {
                    'tables': [],
                    'total_records': 0,
                    'file_size': os.path.getsize(file_path)
                }

                tables = self.get_database_tables(conn)

                for table in tables:
                    try:
                        cursor = conn.cursor()
                        # 获取表的行数
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        row_count = cursor.fetchone()[0]

                        # 获取表的列信息
                        cursor.execute(f"PRAGMA table_info({table})")
                        columns = [col[1] for col in cursor.fetchall()]

                        table_info = {
                            'name': table,
                            'rows': row_count,
                            'columns': columns,
                            'column_count': len(columns)
                        }

                        info['tables'].append(table_info)
                        info['total_records'] += row_count

                    except Exception as e:
                        print(f"获取表 {table} 信息失败: {e}")

                conn.close()
                return info

            except Exception as e:
                print(f"获取数据库信息失败: {e}")
                return {}

        def find_best_trajectory_table(self, conn, tables: List[str]) -> Optional[str]:
            """找到最可能包含轨迹数据的表"""
            try:
                trajectory_indicators = ['x', 'y', 'coordinate', 'position', 'trajectory', 'mouse', 'rat']

                best_score = 0
                best_table = None

                for table in tables:
                    try:
                        cursor = conn.cursor()
                        cursor.execute(f"PRAGMA table_info({table})")
                        columns = [col[1].lower() for col in cursor.fetchall()]

                        score = 0
                        # 检查是否包含坐标相关的列
                        for indicator in trajectory_indicators:
                            for col in columns:
                                if indicator in col:
                                    score += 1

                        # 额外加分：如果同时包含x和y相关的列
                        has_x = any('x' in col for col in columns)
                        has_y = any('y' in col for col in columns)
                        if has_x and has_y:
                            score += 5

                        if score > best_score:
                            best_score = score
                            best_table = table

                    except Exception as e:
                        print(f"分析表 {table} 失败: {e}")
                        continue

                return best_table

            except Exception as e:
                print(f"查找最佳轨迹表失败: {e}")
                return None

        def detect_trajectory_columns(self, df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
            """检测轨迹数据的X、Y坐标列"""
            try:
                columns = df.columns.tolist()
                x_col = None
                y_col = None

                # X坐标列的可能名称
                x_patterns = ['x', 'X', 'x_coord', 'X_coord', 'x_position', 'X_position',
                              'longitude', 'Longitude', 'pos_x', 'PosX']

                # Y坐标列的可能名称
                y_patterns = ['y', 'Y', 'y_coord', 'Y_coord', 'y_position', 'Y_position',
                              'latitude', 'Latitude', 'pos_y', 'PosY']

                # 精确匹配
                for col in columns:
                    if col in x_patterns:
                        x_col = col
                    if col in y_patterns:
                        y_col = col

                # 如果精确匹配失败，尝试模糊匹配
                if not x_col:
                    for col in columns:
                        col_lower = col.lower()
                        if 'x' in col_lower and ('coord' in col_lower or 'pos' in col_lower):
                            x_col = col
                            break

                if not y_col:
                    for col in columns:
                        col_lower = col.lower()
                        if 'y' in col_lower and ('coord' in col_lower or 'pos' in col_lower):
                            y_col = col
                            break

                # 最后尝试：查找包含数值数据的列
                if not x_col or not y_col:
                    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                    if len(numeric_cols) >= 2:
                        if not x_col:
                            x_col = numeric_cols[0]
                        if not y_col:
                            y_col = numeric_cols[1]

                return x_col, y_col

            except Exception as e:
                print(f"检测坐标列失败: {e}")
                return None, None

        def detect_temperature_column(self, df: pd.DataFrame) -> Optional[str]:
            """检测温度数据列"""
            try:
                columns = df.columns.tolist()

                # 温度列的可能名称
                temp_patterns = ['temperature', 'Temperature', 'temp', 'Temp', 'T',
                                 'temperature_c', 'temperature_celsius', '温度', '气温']

                # 精确匹配
                for col in columns:
                    if col in temp_patterns:
                        return col

                # 模糊匹配
                for col in columns:
                    col_lower = col.lower()
                    if 'temp' in col_lower:
                        return col

                return None

            except Exception as e:
                print(f"检测温度列失败: {e}")
                return None

        def get_table_preview(self, file_path: str, table_name: str, limit: int = 5) -> Optional[pd.DataFrame]:
            """获取指定表的预览数据"""
            try:
                conn = sqlite3.connect(file_path)
                df = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT {limit}", conn)
                conn.close()
                return df
            except Exception as e:
                print(f"获取表预览失败: {e}")
                return None

    def read_csv_file(self, file_path: str) -> Optional[pd.DataFrame]:
        """读取CSV文件"""
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")

            # 尝试不同的编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'ascii']
            df = None

            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    print(f"成功使用 {encoding} 编码读取文件")
                    break
                except UnicodeDecodeError:
                    continue

            if df is None:
                raise Exception("无法使用任何编码读取CSV文件")

            return df

        except Exception as e:
            print(f"读取CSV文件失败: {e}")
            return None

    def read_excel_file(self, file_path: str) -> Optional[pd.DataFrame]:
        """读取Excel文件"""
        try:
            df = pd.read_excel(file_path)
            return df
        except Exception as e:
            print(f"读取Excel文件失败: {e}")
            return None

    def auto_detect_file_format(self, file_path: str) -> Optional[pd.DataFrame]:
        """自动检测文件格式并读取"""
        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext == '.csv':
            return self.read_csv_file(file_path)
        elif file_ext in ['.xlsx', '.xls']:
            return self.read_excel_file(file_path)
        else:
            print(f"不支持的文件格式: {file_ext}")
            return None

    def detect_trajectory_columns(self, df: pd.DataFrame) -> Tuple[str, str]:
        """检测轨迹坐标列"""
        columns = df.columns.tolist()
        x_col, y_col = None, None

        # X坐标候选
        x_candidates = ['x', 'X', 'pos_x', 'position_x', 'coord_x', 'longitude', 'lon']
        for candidate in x_candidates:
            for col in columns:
                if candidate.lower() in col.lower():
                    x_col = col
                    break
            if x_col:
                break

        # Y坐标候选
        y_candidates = ['y', 'Y', 'pos_y', 'position_y', 'coord_y', 'latitude', 'lat']
        for candidate in y_candidates:
            for col in columns:
                if candidate.lower() in col.lower():
                    y_col = col
                    break
            if y_col:
                break

        return x_col, y_col

    def detect_temperature_column(self, df: pd.DataFrame) -> Optional[str]:
        """检测温度列"""
        columns = df.columns.tolist()

        temp_candidates = ['temperature', 'temp', 'Temperature', 'TEMP', 'celsius', 'degree']
        for candidate in temp_candidates:
            for col in columns:
                if candidate.lower() in col.lower():
                    return col

        # 如果没找到明确的温度列，看是否有数值列可能是温度
        for col in columns:
            try:
                values = pd.to_numeric(df[col], errors='coerce').dropna()
                if not values.empty:
                    # 假设温度在合理范围内（0-50摄氏度）
                    if values.min() >= 0 and values.max() <= 50:
                        return col
            except:
                continue

        return None

    def extract_cage_data(self, df: pd.DataFrame, cage_id: str) -> pd.DataFrame:
        """从数据中提取指定笼子的数据"""
        try:
            # 检查是否有cage_id或gid列
            cage_columns = ['cage_id', 'gid', 'cage', 'group_id']
            cage_col = None

            for col in cage_columns:
                if col in df.columns:
                    cage_col = col
                    break

            if cage_col:
                cage_data = df[df[cage_col] == cage_id]
                return cage_data
            else:
                print("未找到笼子ID列，返回全部数据")
                return df

        except Exception as e:
            print(f"提取笼子数据失败: {e}")
            return df