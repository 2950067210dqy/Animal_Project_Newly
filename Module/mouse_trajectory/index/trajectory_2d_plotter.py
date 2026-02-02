import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from PyQt6.QtCore import pyqtSignal, QTimer, QObject
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class MiniTrajectory2DPlotter(QObject):
    """2D平面轨迹绘制器 - X-Z平面，支持逐点动画绘制"""

    animation_progress_updated = pyqtSignal(int)
    coordinate_info_updated = pyqtSignal(dict)
    animation_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._setup_chinese_font()

        self.fig: Optional[Figure] = None
        self.ax = None
        self.canvas: Optional[FigureCanvas] = None

        self.is_animating = False
        self.animation_paused = False
        self.animation_index = 0
        self.animation_data: List[Dict] = []
        self.animation_timer: Optional[QTimer] = None
        self.animation_speed_multiplier = 1.0

        # 坐标轴范围
        self.x_min, self.x_max = -0.10, 0.10
        self.z_min, self.z_max = 0.10, 0.40

        # 用于颜色映射的数据范围
        self.z_data_min = 0.10
        self.z_data_max = 0.40

        self.trajectory_line = None
        self.scatter_points = None
        self.cmap = plt.cm.viridis

        # 标记是否已初始化过坐标轴
        self.axes_initialized = False

    def _setup_chinese_font(self):
        """设置中文字体"""
        try:
            import platform
            from matplotlib.font_manager import FontProperties

            system = platform.system()

            if system == "Windows":
                chinese_fonts = ['SimHei', 'Microsoft YaHei', 'KaiTi', 'FangSong']
            elif system == "Darwin":
                chinese_fonts = ['PingFang SC', 'Heiti SC', 'STHeiti', 'Arial Unicode MS']
            else:
                chinese_fonts = ['WenQuanYi Micro Hei', 'Droid Sans Fallback', 'DejaVu Sans']

            font_set = False
            for font_name in chinese_fonts:
                try:
                    plt.rcParams['font.sans-serif'] = [font_name] + plt.rcParams['font.sans-serif']
                    plt.rcParams['axes.unicode_minus'] = False
                    font_set = True
                    break
                except Exception:
                    continue

            if not font_set:
                logger.warning("未能设置中文字体")
                plt.rcParams['font.sans-serif'] = ['DejaVu Sans']

        except Exception as e:
            logger.error(f"设置中文字体失败: {e}")

    def create_figure(self, figsize=(5, 4), dpi=100) -> FigureCanvas:
        """创建matplotlib图表和canvas"""
        try:
            self.fig = Figure(figsize=figsize, dpi=dpi)
            self.fig.patch.set_facecolor('white')

            # 优化布局 - 为标签和刻度预留足够空间
            self.fig.subplots_adjust(
                left=0.12,
                right=0.95,
                top=0.92,
                bottom=0.12
            )

            self.ax = self.fig.add_subplot(111)

            self.canvas = FigureCanvas(self.fig)
            self.canvas.setStyleSheet("""
                QWidget {
                    background-color: white;
                    border: 1px solid lightgray;
                    margin: 0px;
                    padding: 0px;
                }
            """)

            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self._draw_animation_step)

            # 初始化坐标轴
            self._setup_axes()
            self.axes_initialized = True

            return self.canvas

        except Exception as e:
            logger.error(f"创建图表失败: {e}", exc_info=True)
            raise

    def set_axis_limits(self, x_min, x_max, z_min, z_max):
        """设置坐标轴限制"""
        self.x_min, self.x_max = x_min, x_max
        self.z_min, self.z_max = z_min, z_max
        self.z_data_min = z_min
        self.z_data_max = z_max

    def _apply_axis_limits(self):
        """应用坐标轴范围限制"""
        if self.ax is None:
            return

        self.ax.set_xlim(self.x_min, self.x_max)
        self.ax.set_ylim(self.z_min, self.z_max)

        # 设置坐标轴纵横比（根据物理尺寸）
        aspect_ratio = (self.x_max - self.x_min) / (self.z_max - self.z_min)
        self.ax.set_aspect(aspect_ratio, adjustable='box')

    def _setup_axes(self):
        """设置2D坐标轴"""
        try:
            if self.ax is None:
                logger.error("坐标轴未初始化")
                return

            # 清空现有内容
            self.ax.clear()
            self.trajectory_line = None
            self.scatter_points = None

            # ===== 设置X轴（水平） =====
            x_ticks = np.linspace(self.x_min, self.x_max, 5)
            self.ax.set_xticks(x_ticks)
            self.ax.set_xticklabels([f'{x:.2f}' for x in x_ticks], fontsize=9)
            self.ax.set_xlabel('X水平 (m)', fontsize=11, fontweight='bold', labelpad=15)

            # ===== 设置Z轴（竖直） =====
            z_ticks = np.linspace(self.z_min, self.z_max, 5)
            self.ax.set_yticks(z_ticks)
            self.ax.set_yticklabels([f'{z:.2f}' for z in z_ticks], fontsize=9)
            self.ax.set_ylabel('Z竖直 (m)', fontsize=11, fontweight='bold', labelpad=15)

            # ===== 设置标题 =====
            self.ax.set_title('二维平面轨迹 (X-Z，无 Y 高度)', fontsize=12, fontweight='bold', pad=20)

            # ===== 增加刻度标签间距 =====
            self.ax.tick_params(axis='x', labelsize=9, pad=10, length=5, width=1)
            self.ax.tick_params(axis='y', labelsize=9, pad=10, length=5, width=1)

            # ===== 启用网格 =====
            self.ax.grid(True, alpha=0.4, linestyle='--', linewidth=0.6, color='gray')

            # ===== 应用坐标轴范围 =====
            self._apply_axis_limits()

            # ===== 设置背景色 =====
            self.ax.set_facecolor('#f9f9f9')

            # ===== 设置坐标轴样式 =====
            self.ax.spines['top'].set_visible(True)
            self.ax.spines['right'].set_visible(True)
            self.ax.spines['left'].set_visible(True)
            self.ax.spines['bottom'].set_visible(True)
            self.ax.spines['top'].set_color('#cccccc')
            self.ax.spines['right'].set_color('#cccccc')
            self.ax.spines['left'].set_color('#333333')
            self.ax.spines['bottom'].set_color('#333333')
            self.ax.spines['left'].set_linewidth(1.5)
            self.ax.spines['bottom'].set_linewidth(1.5)

            # 立即刷新
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.draw_idle()

        except Exception as e:
            logger.error(f"设置坐标轴失败: {e}", exc_info=True)

    def draw_trajectory_2d_incremental(self, coordinates: List[Dict]) -> bool:
        """增量绘制2D轨迹（逐点绘制）"""
        try:
            if not coordinates or len(coordinates) < 2:
                logger.warning("坐标数据不足，至少需要2个点")
                return False

            # 计算 z 值的范围 - 仅用于颜色映射
            try:
                z_values = [float(coord.get('center_z', 0)) for coord in coordinates]
                z_values = [z for z in z_values if np.isfinite(z)]

                if z_values:
                    self.z_data_min = min(z_values)
                    self.z_data_max = max(z_values)
                    logger.info(f"Z值范围: [{self.z_data_min:.3f}, {self.z_data_max:.3f}]")

                    # 确保数据范围在显示范围内
                    if self.z_data_min < self.z_min:
                        self.z_min = self.z_data_min - 0.01
                    if self.z_data_max > self.z_max:
                        self.z_max = self.z_data_max + 0.01

                else:
                    logger.warning("Z值计算失败，使用默认范围")
            except Exception as z_error:
                logger.error(f"计算Z值范围失败: {z_error}")

            # 只在第一次或者数据范围变化时重新设置坐标轴
            if not self.axes_initialized:
                self._setup_axes()
                self.axes_initialized = True
            else:
                # 只更新范围（如果需要）
                self._apply_axis_limits()

            # 立即绘制初始点
            if len(coordinates) > 0:
                try:
                    coord0 = coordinates[0]
                    x0 = float(coord0.get('center_x', 0))
                    z0 = float(coord0.get('center_z', 0))

                    if not all(np.isfinite([x0, z0])):
                        logger.error(f"起点坐标无效: x0={x0}, z0={z0}")
                        return False

                    # 绘制起点（绿色）
                    self.scatter_points = self.ax.scatter(
                        [x0], [z0],
                        c='green',
                        s=150,
                        marker='o',
                        alpha=0.9,
                        edgecolors='darkgreen',
                        linewidth=2,
                        label='start',
                        zorder=5
                    )

                    # 重新应用范围
                    self._apply_axis_limits()

                    # 立即刷新画布
                    if self.canvas:
                        self.canvas.draw_idle()
                    else:
                        logger.error(f"canvas 不存在")
                        return False

                except Exception as start_point_error:
                    logger.error(f"绘制起点失败: {start_point_error}", exc_info=True)
                    return False

            # 准备动画数据
            self.animation_data = list(coordinates)
            self.animation_index = 0

            return True

        except Exception as e:
            logger.error(f"绘制轨迹失败: {e}", exc_info=True)
            return False

    def _draw_single_segment(self, coord1: Dict, coord2: Dict, index: int, total: int):
        """绘制单条线段"""
        try:
            x1 = float(coord1.get('center_x', 0))
            z1 = float(coord1.get('center_z', 0))

            x2 = float(coord2.get('center_x', 0))
            z2 = float(coord2.get('center_z', 0))

            # 检查坐标是否有效
            if any(not np.isfinite(val) for val in [x1, z1, x2, z2]):
                logger.warning(f"发现无效坐标，跳过此线段")
                return

            # 计算Z方向的颜色
            z_range = self.z_data_max - self.z_data_min
            if z_range < 1e-6:
                z_normalized = 0.5
            else:
                z_normalized = (z2 - self.z_data_min) / z_range
                z_normalized = np.clip(z_normalized, 0, 1)

            color = self.cmap(z_normalized)

            # 绘制线段
            line = self.ax.plot(
                [x1, x2],
                [z1, z2],
                color=color,
                linewidth=2.0,
                alpha=0.85,
                solid_capstyle='round',
                solid_joinstyle='round'
            )[0]

        except Exception as e:
            logger.error(f"绘制线段失败: {e}", exc_info=True)

    def start_animation(self, animation_speed: int = 50):
        """启动轨迹动画"""
        try:
            if not hasattr(self, 'animation_data') or not self.animation_data:
                logger.error("没有动画数据，请先调用 draw_trajectory_2d_incremental")
                return False

            if len(self.animation_data) < 2:
                logger.error("动画数据不足，至少需要2个点")
                return False

            if self.animation_timer:
                logger.info("停止现有动画")
                self.animation_timer.stop()

            self.animation_index = 0
            self.is_animating = True
            self.animation_paused = False

            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self._draw_animation_step)

            # 根据速度倍数调整间隔
            interval = max(10, int(animation_speed / max(self.animation_speed_multiplier, 0.1)))
            self.animation_timer.start(interval)

            logger.info(f"2D动画已启动，数据点数: {len(self.animation_data)}")
            return True

        except Exception as e:
            logger.error(f"启动动画失败: {e}", exc_info=True)
            return False

    def _draw_animation_step(self):
        """动画的每一步"""
        try:
            if not self.is_animating or self.animation_paused:
                return

            if self.animation_index >= len(self.animation_data) - 1:
                if self.animation_timer:
                    self.animation_timer.stop()
                self.is_animating = False

                # 绘制终点（红色）
                if len(self.animation_data) > 0:
                    try:
                        last_coord = self.animation_data[-1]
                        x_end = float(last_coord.get('center_x', 0))
                        z_end = float(last_coord.get('center_z', 0))

                        self.ax.scatter(
                            [x_end], [z_end],
                            c='red',
                            s=150,
                            marker='o',
                            alpha=0.9,
                            edgecolors='darkred',
                            linewidth=2,
                            label='end',
                            zorder=5
                        )

                        # 添加图例
                        self.ax.legend(loc='upper right', fontsize=10, framealpha=0.9)

                        self.canvas.draw_idle()
                    except Exception as e:
                        logger.error(f"绘制终点失败: {e}")

                self.animation_progress_updated.emit(100)
                self.animation_finished.emit()
                logger.info("2D动画已完成")
                return

            coord1 = self.animation_data[self.animation_index]
            coord2 = self.animation_data[self.animation_index + 1]

            self._draw_single_segment(coord1, coord2, self.animation_index, len(self.animation_data))

            # 重新应用范围
            self._apply_axis_limits()

            # 刷新画布
            self.canvas.draw_idle()

            # 更新进度
            progress = int((self.animation_index / max(1, len(self.animation_data) - 2)) * 100)
            self.animation_progress_updated.emit(progress)

            # 发送坐标信息
            self.coordinate_info_updated.emit({
                'x': float(coord2.get('center_x', 0)),
                'z': float(coord2.get('center_z', 0)),
                'index': self.animation_index + 1,
                'total': len(self.animation_data)
            })

            self.animation_index += 1

        except Exception as e:
            logger.error(f"动画步骤失败: {e}", exc_info=True)
            self.is_animating = False

    def pause_animation(self):
        """暂停动画"""
        if self.is_animating and not self.animation_paused:
            self.animation_paused = True
            if self.animation_timer:
                self.animation_timer.stop()
            logger.info("动画已暂停")

    def resume_animation(self):
        """继续动画"""
        if self.is_animating and self.animation_paused:
            self.animation_paused = False
            if self.animation_timer:
                interval = max(10, int(50 * (1.0 / max(self.animation_speed_multiplier, 0.1))))
                self.animation_timer.start(interval)
            logger.info("动画已继续")

    def stop_animation(self):
        """停止动画"""
        if self.animation_timer:
            self.animation_timer.stop()
        self.is_animating = False
        self.animation_paused = False
        self.animation_index = 0
        logger.info("动画已停止")

    def clear_figure(self):
        """清空图表"""
        try:
            if self.ax is not None:
                self.ax.clear()
                self._setup_axes()
            self.trajectory_line = None
            self.scatter_points = None
            if self.canvas:
                self.canvas.draw_idle()
        except Exception as e:
            logger.error(f"清空图表失败: {e}")

    def __del__(self):
        """清理资源"""
        try:
            if self.animation_timer:
                self.animation_timer.stop()
            if self.canvas:
                self.canvas.close()
        except:
            pass