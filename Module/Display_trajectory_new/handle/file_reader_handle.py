# file_reader_handle.py
from typing import Tuple

import pandas as pd


class FileReaderHandle:
    """文件读取处理类 - 负责CSV的读取"""

    def __init__(self):
        self.supported_formats = ['.csv', '.xlsx', '.xls']

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
    # def detect_trajectory_columns(self, df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    #     """检测轨迹数据的X、Y坐标列"""
    #     try:
    #         columns = df.columns.tolist()
    #         x_col = None
    #         y_col = None
    #
    #         # X坐标列的可能名称
    #         x_patterns = ['x', 'X', 'x_coord', 'X_coord', 'x_position', 'X_position',
    #                       'longitude', 'Longitude', 'pos_x', 'PosX']
    #
    #         # Y坐标列的可能名称
    #         y_patterns = ['y', 'Y', 'y_coord', 'Y_coord', 'y_position', 'Y_position',
    #                       'latitude', 'Latitude', 'pos_y', 'PosY']
    #
    #         # 精确匹配
    #         for col in columns:
    #             if col in x_patterns:
    #                 x_col = col
    #             if col in y_patterns:
    #                 y_col = col
    #
    #         # 如果精确匹配失败，尝试模糊匹配
    #         if not x_col:
    #             for col in columns:
    #                 col_lower = col.lower()
    #                 if 'x' in col_lower and ('coord' in col_lower or 'pos' in col_lower):
    #                     x_col = col
    #                     break
    #
    #         if not y_col:
    #             for col in columns:
    #                 col_lower = col.lower()
    #                 if 'y' in col_lower and ('coord' in col_lower or 'pos' in col_lower):
    #                     y_col = col
    #                     break
    #
    #         # 最后尝试：查找包含数值数据的列
    #         if not x_col or not y_col:
    #             numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    #             if len(numeric_cols) >= 2:
    #                 if not x_col:
    #                     x_col = numeric_cols[0]
    #                 if not y_col:
    #                     y_col = numeric_cols[1]
    #
    #         return x_col, y_col
    #
    #     except Exception as e:
    #         print(f"检测坐标列失败: {e}")
    #         return None, None


