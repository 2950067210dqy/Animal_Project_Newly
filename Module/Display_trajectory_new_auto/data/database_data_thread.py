import time
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal
from loguru import logger

class DatabaseDataThread(QThread):
    """基于数据库数据的动态绘制线程"""
    data_received = pyqtSignal(dict)  # {cage_id: [new_data_point]}
    progress_updated = pyqtSignal(dict)  # {cage_id: {'current': int, 'total': int}}

    def __init__(self, data_handler, cage_ids):
        super().__init__()
        self.data_handler = data_handler
        self.cage_ids = cage_ids
        self.running = False
        self.paused = False

        # 每个鼠笼的数据和当前播放位置
        self.cage_data = {cage_id: [] for cage_id in cage_ids}
        self.current_indices = {cage_id: 0 for cage_id in cage_ids}
        self.total_counts = {cage_id: 0 for cage_id in cage_ids}

        # 播放速度（毫秒）
        self.play_speed = 1000

    def load_all_data_from_database(self):
        """从数据库加载所有数据"""
        for cage_id in self.cage_ids:
            try:
                logger.info(f"正在从数据库加载鼠笼 {cage_id} 的数据...")

                # 获取该鼠笼的所有轨迹数据
                result = self.data_handler.get_trajectory_data(
                    cage_id=cage_id,
                    limit=None  # 获取所有数据，不限制数量
                )

                if result['success'] and result['data']:
                    # 验证并处理数据
                    validated_data = []
                    for raw_point in result['data']:
                        validated_point = self.validate_data_point(raw_point)
                        if validated_point:
                            validated_data.append(validated_point)

                    # 按时间戳排序确保顺序正确
                    validated_data.sort(key=lambda x: x[0])

                    self.cage_data[cage_id] = validated_data
                    self.total_counts[cage_id] = len(validated_data)
                    self.current_indices[cage_id] = 0

                    logger.info(f"鼠笼 {cage_id}: 成功加载 {len(validated_data)} 条数据记录")
                else:
                    logger.warning(f"鼠笼 {cage_id}: 数据库中没有找到数据")
                    self.cage_data[cage_id] = []
                    self.total_counts[cage_id] = 0
                    self.current_indices[cage_id] = 0

            except Exception as e:
                logger.error(f"加载鼠笼 {cage_id} 数据失败: {e}")
                self.cage_data[cage_id] = []
                self.total_counts[cage_id] = 0
                self.current_indices[cage_id] = 0

    def validate_data_point(self, data_point):
        """验证和转换数据点格式"""
        try:
            if not data_point or len(data_point) < 4:
                return None

            # 转换时间戳
            timestamp = data_point[0]
            if isinstance(timestamp, str):
                try:
                    if '.' in timestamp:
                        timestamp = float(timestamp)
                    else:
                        # 尝试解析日期时间字符串
                        try:
                            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                            timestamp = dt.timestamp()
                        except:
                            dt = datetime.strptime(timestamp.split('.')[0], "%Y-%m-%d %H:%M:%S")
                            timestamp = dt.timestamp()
                except:
                    timestamp = time.time()
            elif not isinstance(timestamp, (int, float)):
                timestamp = time.time()

            # 转换坐标
            x = float(data_point[1]) if data_point[1] is not None else 0.0
            y = float(data_point[2]) if data_point[2] is not None else 0.0
            z = float(data_point[3]) if data_point[3] is not None else 0.0

            return [timestamp, x, y, z]

        except Exception as e:
            logger.error(f"验证数据点失败: {e}")
            return None

    def get_next_data_batch(self):
        """获取下一批数据点（每个鼠笼一个点）"""
        current_batch = {}
        progress_info = {}

        for cage_id in self.cage_ids:
            cage_data_list = self.cage_data[cage_id]
            current_index = self.current_indices[cage_id]
            total_count = self.total_counts[cage_id]

            # 更新进度信息
            progress_info[cage_id] = {
                'current': current_index,
                'total': total_count
            }

            # 获取下一个数据点
            if current_index < len(cage_data_list):
                data_point = cage_data_list[current_index]
                current_batch[cage_id] = [data_point]
                self.current_indices[cage_id] += 1
            elif total_count > 0:
                # 数据播放完毕，重新开始
                self.current_indices[cage_id] = 0
                if cage_data_list:  # 确保有数据
                    data_point = cage_data_list[0]
                    current_batch[cage_id] = [data_point]
                    self.current_indices[cage_id] = 1

        return current_batch, progress_info

    def get_all_data_for_cage(self, cage_id):
        """获取指定鼠笼的所有数据"""
        return self.cage_data.get(cage_id, [])

    def set_play_speed(self, speed_ms):
        """设置播放速度"""
        self.play_speed = max(50, min(3000, speed_ms))  # 限制在50ms-3000ms之间

    def reset_all_progress(self):
        """重置所有鼠笼的播放进度"""
        for cage_id in self.cage_ids:
            self.current_indices[cage_id] = 0
        logger.info("已重置所有鼠笼的播放进度")

    def run(self):
        """线程主循环 - 基于数据库数据"""
        self.running = True
        logger.info(f"开始数据的动态轨迹播放: {self.cage_ids}")

        # 首先加载所有数据
        self.load_all_data_from_database()

        # 检查是否有数据可播放
        total_data_points = sum(self.total_counts.values())
        if total_data_points == 0:
            logger.warning("没有找到任何数据，线程待机...")
            self.running = False
            return

        logger.info(f"总共加载了 {total_data_points} 个数据点，开始动态播放...")

        while self.running:
            try:
                if self.paused:
                    self.msleep(100)
                    continue

                # 获取下一批数据
                current_batch, progress_info = self.get_next_data_batch()

                # 发送数据和进度信息
                if current_batch:
                    self.data_received.emit(current_batch)

                self.progress_updated.emit(progress_info)

                # 根据设置的播放速度暂停
                self.msleep(self.play_speed)

            except Exception as e:
                logger.error(f"数据播放线程出错: {e}")
                self.msleep(1000)

    def pause(self):
        """暂停播放"""
        self.paused = True

    def resume(self):
        """恢复播放"""
        self.paused = False

    def is_paused(self):
        """检查是否暂停"""
        return self.paused

    def stop(self):
        """停止线程"""
        self.running = False
        self.quit()
        self.wait()
