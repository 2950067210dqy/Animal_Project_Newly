import logging
import os

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

from Module.Display_trajectory_new.handle.file_reader_handle import FileReaderHandle

logger = logging.getLogger(__name__)


class DataLoadThread(QThread):
    """数据加载线程"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    data_loaded = pyqtSignal(object)
    temperature_loaded = pyqtSignal(object)
    sheets_detected = pyqtSignal(list)

    def __init__(self, file_path, trajectory_sheet=None, temperature_sheet=None):
        super().__init__()
        self.file_path = file_path
        self.trajectory_sheet = trajectory_sheet
        self.temperature_sheet = temperature_sheet
        self.file_reader = FileReaderHandle()

    def run(self):
        try:
            self.progress.emit(10)

            # 首先检测文件中的所有sheet
            sheets = self.detect_sheets(self.file_path)
            if sheets:
                self.sheets_detected.emit(sheets)

            self.progress.emit(30)

            # 加载轨迹数据
            trajectory_df = self.load_trajectory_data(self.file_path, self.trajectory_sheet)
            if trajectory_df is not None and not trajectory_df.empty:
                self.data_loaded.emit(trajectory_df)
                self.progress.emit(70)

            # 加载温度数据
            temperature_df = self.load_temperature_data(self.file_path, self.temperature_sheet)
            if temperature_df is not None and not temperature_df.empty:
                self.temperature_loaded.emit(temperature_df)
                self.progress.emit(90)

            self.progress.emit(100)

            if trajectory_df is not None:
                self.finished.emit(True, f"成功加载案例笼子的数据")
            else:
                self.finished.emit(False, "未找到轨迹数据")

        except Exception as e:
            logger.error(f"数据加载失败: {str(e)}")
            self.finished.emit(False, f"数据加载失败: {str(e)}")

    def detect_sheets(self, file_path):
        """检测Excel文件中的所有sheet"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext in ['.xlsx', '.xls']:
                xl_file = pd.ExcelFile(file_path)
                return xl_file.sheet_names
            return []
        except Exception as e:
            logger.error(f"检测sheet失败: {e}")
            return []

    def load_trajectory_data(self, file_path, sheet_name=None):
        """加载轨迹数据"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            df = None

            if file_ext in ['.csv']:
                # CSV文件处理
                encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
                for encoding in encodings:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding)
                        break
                    except (UnicodeDecodeError, Exception):
                        continue

            elif file_ext in ['.xlsx', '.xls']:
                # Excel文件处理
                if sheet_name:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                else:
                    # 自动检测轨迹sheet
                    xl_file = pd.ExcelFile(file_path)
                    trajectory_sheet = self.find_trajectory_sheet(xl_file.sheet_names)
                    if trajectory_sheet:
                        df = pd.read_excel(file_path, sheet_name=trajectory_sheet)
                        logger.info(f"自动选择轨迹sheet: {trajectory_sheet}")
                    else:
                        # 如果没找到，使用第一个sheet
                        df = pd.read_excel(file_path, sheet_name=0)
                        logger.info("使用第一个sheet作为轨迹数据")

            return df
        except Exception as e:
            logger.error(f"加载轨迹数据失败: {e}")
            return None

    def load_temperature_data(self, file_path, sheet_name=None):
        """加载温度数据"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            df = None

            if file_ext in ['.xlsx', '.xls']:
                if sheet_name:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                else:
                    # 自动检测温度sheet
                    xl_file = pd.ExcelFile(file_path)
                    temperature_sheet = self.find_temperature_sheet(xl_file.sheet_names)
                    if temperature_sheet:
                        df = pd.read_excel(file_path, sheet_name=temperature_sheet)
                        logger.info(f"自动选择温度sheet: {temperature_sheet}")
                    else:
                        # 尝试在轨迹sheet中查找温度数据
                        trajectory_sheet = self.find_trajectory_sheet(xl_file.sheet_names)
                        if trajectory_sheet:
                            temp_df = pd.read_excel(file_path, sheet_name=trajectory_sheet)
                            if self.has_temperature_column(temp_df):
                                df = temp_df
                                logger.info("在轨迹sheet中找到温度数据")
            elif file_ext in ['.csv']:
                # CSV文件中查找温度数据
                encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
                for encoding in encodings:
                    try:
                        temp_df = pd.read_csv(file_path, encoding=encoding)
                        if self.has_temperature_column(temp_df):
                            df = temp_df
                        break
                    except (UnicodeDecodeError, Exception):
                        continue

            return df
        except Exception as e:
            logger.error(f"加载温度数据失败: {e}")
            return None

    def find_trajectory_sheet(self, sheet_names):
        """查找轨迹数据的sheet"""
        trajectory_keywords = [
            '轨迹', 'trajectory', 'track', '坐标', 'position',
            'movement', '移动', '路径', 'path', '数据', 'data'
        ]

        # 优先查找包含关键词的sheet
        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower()
            for keyword in trajectory_keywords:
                if keyword in sheet_lower:
                    return sheet_name

        # 如果没有找到关键词匹配，返回第一个不是温度相关的sheet
        temp_keywords = ['温度', 'temperature', 'temp', '环境','environment']
        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower()
            is_temp_sheet = any(keyword in sheet_lower for keyword in temp_keywords)
            if not is_temp_sheet:
                return sheet_name

        # 如果都没有匹配，返回第一个sheet
        return sheet_names[0] if sheet_names else None

    def find_temperature_sheet(self, sheet_names):
        """查找温度数据的sheet"""
        temperature_keywords = [
            '温度', 'temperature', 'temp', '环境', 'environment',
            '气温', '室温', '监控','monitor'
        ]

        for sheet_name in sheet_names:
            sheet_lower = sheet_name.lower()
            for keyword in temperature_keywords:
                if keyword in sheet_lower:
                    return sheet_name
        return None

    def has_temperature_column(self, df):
        """检查DataFrame是否包含温度列"""
        temp_column_names = [
            '均值温度(摄氏度)', '均值温度', '温度', 'temperature',
            'temp', 'Temperature', 'Temp', 'avg_temperature',
            '环境温度', '室温', '气温'
        ]

        for col_name in temp_column_names:
            if col_name in df.columns:
                return True
        return False