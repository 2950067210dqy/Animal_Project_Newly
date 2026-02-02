import numpy as np

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import proj3d
import matplotlib.pyplot as plt

from PyQt6.QtCore import pyqtSignal, QTimer, QObject
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class MiniTrajectory3DPlotter(QObject):
    """小型3D轨迹绘制器 - 支持逐点动画绘制"""

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

        # 坐标轴固定（默认True）
        self.fixed_x = True
        self.fixed_y = True
        self.fixed_z = True
        self.x_min, self.x_max = -0.10, 0.10
        self.y_min, self.y_max = -0.05, 0.05
        self.z_min, self.z_max = 0.10, 0.40

        # 关键：分离显示范围和缓存范围
        self.z_display_min = 0.10
        self.z_display_max = 0.40
        self.z_data_min = 0.10  # 用于颜色映射的数据范围
        self.z_data_max = 0.40

        self.trajectory_lines = []
        self.scatter_points = None
        self.cmap = plt.cm.viridis

        # 保存相机状态
        self.camera_elev = 15
        self.camera_azim = 45

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

    def create_figure(self, figsize=(4, 3.5), dpi=80) -> FigureCanvas:
        """创建matplotlib图表和canvas"""
        try:
            self.fig = Figure(figsize=figsize, dpi=dpi)
            self.fig.patch.set_facecolor('white')

            # ===== 关键：大幅增加边距，为刻度标签留出足够空间 =====
            self.fig.subplots_adjust(
                left=0.15,  # 左边距（为Y轴标签）
                right=0.90,  # 右边距
                top=0.85,  # 顶部距离
                bottom=0.25  # 增加底部距离（为X轴标签和刻度）
            )

            self.ax = self.fig.add_subplot(111, projection='3d')

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

            # 初始化坐标轴一次
            self._setup_axes()
            self.axes_initialized = True

            return self.canvas

        except Exception as e:
            logger.error(f"创建图表失败: {e}", exc_info=True)
            raise

    def set_axis_fixed(self, fixed_x=True, fixed_y=True, fixed_z=True):
        """设置是否固定坐标轴"""
        self.fixed_x = fixed_x
        self.fixed_y = fixed_y
        self.fixed_z = fixed_z

    def set_axis_limits(self, x_min, x_max, y_min, y_max, z_min, z_max):
        """设置坐标轴限制"""
        self.x_min, self.x_max = x_min, x_max
        self.y_min, self.y_max = y_min, y_max
        self.z_min, self.z_max = z_min, z_max
        # 同时更新显示范围
        self.z_display_min = z_min
        self.z_display_max = z_max
        self.z_data_min = z_min
        self.z_data_max = z_max

    def _apply_axis_limits(self):
        """应用坐标轴范围限制 - 关键方法"""
        if self.ax is None:
            return

        # 强制固定坐标轴范围 - 使用显示范围而不是数据范围
        self.ax.set_xlim(self.x_min, self.x_max)
        self.ax.set_ylim(self.y_min, self.y_max)
        self.ax.set_zlim(self.z_display_min, self.z_display_max)

        # 设置坐标轴纵横比
        self.ax.set_box_aspect((
            (self.x_max - self.x_min),
            (self.y_max - self.y_min),
            (self.z_display_max - self.z_display_min)
        ))

    def _customize_axis_ticks(self):
        """自定义坐标轴刻度 - 确保清晰显示"""
        try:
            if self.ax is None:
                return

            # 设置 X 轴刻度
            x_ticks = np.linspace(self.x_min, self.x_max, 5)
            self.ax.set_xticks(x_ticks)
            self.ax.set_xticklabels([f'{x:.2f}' for x in x_ticks], fontsize=7)

            # 设置 Y 轴刻度
            y_ticks = np.linspace(self.y_min, self.y_max, 5)
            self.ax.set_yticks(y_ticks)
            self.ax.set_yticklabels([f'{y:.2f}' for y in y_ticks], fontsize=7)

            # 设置 Z 轴刻度 - 使用显示范围
            z_ticks = np.linspace(self.z_display_min, self.z_display_max, 5)
            self.ax.set_zticks(z_ticks)
            self.ax.set_zticklabels([f'{z:.2f}' for z in z_ticks], fontsize=7)

        except Exception as e:
            logger.error(f"自定义刻度失败: {e}")

    def _setup_axes(self):
        """设置3D坐标轴 - 优化刻度标签显示"""
        try:
            if self.ax is None:
                logger.error("坐标轴未初始化")
                return

            # 清空现有内容
            self.ax.clear()
            self.trajectory_lines = []
            self.scatter_points = None

            # ===== 关键改进1：减少刻度数量，避免拥挤 =====
            # X轴：只显示3个主要刻度
            x_ticks = np.linspace(self.x_min, self.x_max, 3)
            self.ax.set_xticks(x_ticks)
            self.ax.set_xticklabels([f'{x:.2f}' for x in x_ticks], fontsize=8)

            # Y轴：只显示3个主要刻度
            y_ticks = np.linspace(self.y_min, self.y_max, 3)
            self.ax.set_yticks(y_ticks)
            self.ax.set_yticklabels([f'{y:.2f}' for y in y_ticks], fontsize=8)

            # Z轴：显示4个刻度
            z_ticks = np.linspace(self.z_display_min, self.z_display_max, 4)
            self.ax.set_zticks(z_ticks)
            self.ax.set_zticklabels([f'{z:.2f}' for z in z_ticks], fontsize=8)

            # ===== 关键改进2：优化轴标签位置 =====
            self.ax.set_xlabel('X轴 (m)', fontsize=10, fontweight='bold', labelpad=20)
            self.ax.set_ylabel('Y轴 (m)', fontsize=10, fontweight='bold', labelpad=20)
            self.ax.set_zlabel('Z轴 (m)', fontsize=10, fontweight='bold', labelpad=15)

            # ===== 关键改进3：增加刻度标签的间距 =====
            self.ax.tick_params(axis='x', labelsize=8, pad=10, length=4, width=1)
            self.ax.tick_params(axis='y', labelsize=8, pad=10, length=4, width=1)
            self.ax.tick_params(axis='z', labelsize=8, pad=8, length=4, width=1)

            # ===== 关键改进4：优化3D视角，让X和Y轴更清晰 =====
            self.ax.view_init(elev=25, azim=35)  # 调整角度让X/Y轴更可见

            # ===== 关键改进5：启用网格 =====
            self.ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.6)

            # ===== 关键改进6：应用坐标轴范围 =====
            self._apply_axis_limits()

            # ===== 关键改进7：优化背景 =====
            self.ax.xaxis.pane.fill = True
            self.ax.yaxis.pane.fill = True
            self.ax.zaxis.pane.fill = True

            self.ax.xaxis.pane.set_facecolor('#f5f5f5')
            self.ax.yaxis.pane.set_facecolor('#f5f5f5')
            self.ax.zaxis.pane.set_facecolor('#f5f5f5')

            self.ax.xaxis.pane.set_edgecolor('#cccccc')
            self.ax.yaxis.pane.set_edgecolor('#cccccc')
            self.ax.zaxis.pane.set_edgecolor('#cccccc')

            # ===== 关键改进8：调整坐标轴纵横比 =====
            self.ax.set_box_aspect((1.2, 1.0, 1.8))  # X稍微拉长，Z更长

            # 立即刷新
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.draw_idle()

        except Exception as e:
            logger.error(f"设置坐标轴失败: {e}", exc_info=True)

    def _draw_single_segment(self, coord1: Dict, coord2: Dict, index: int, total: int):
        """绘制单条线段"""
        try:
            x1 = float(coord1.get('center_x', 0))
            y1 = float(coord1.get('center_y', 0))
            z1 = float(coord1.get('center_z', 0))

            x2 = float(coord2.get('center_x', 0))
            y2 = float(coord2.get('center_y', 0))
            z2 = float(coord2.get('center_z', 0))

            # 检查坐标是否有效
            if any(not np.isfinite(val) for val in [x1, y1, z1, x2, y2, z2]):
                logger.warning(f"发现无效坐标，跳过此线段")
                return

            # 检查 z 值范围，避免除零错误 - 使用数据范围而非显示范围
            z_range = self.z_data_max - self.z_data_min
            if z_range < 1e-6:  # 防止除零
                z_normalized = 0.5
            else:
                z_normalized = (z2 - self.z_data_min) / z_range
                z_normalized = np.clip(z_normalized, 0, 1)

            color = self.cmap(z_normalized)

            # 绘制线段
            line = self.ax.plot(
                [x1, x2],
                [y1, y2],
                [z1, z2],
                color=color,
                linewidth=1.5,
                alpha=0.8
            )[0]

            self.trajectory_lines.append(line)
        except Exception as e:
            logger.error(f"绘制线段失败: {e}", exc_info=True)

    def draw_trajectory_3d_incremental(self, coordinates: List[Dict]) -> bool:
        """增量绘制3D轨迹（逐点绘制）"""
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

                    # 关键：确保数据范围在显示范围内
                    if self.z_data_min < self.z_display_min:
                        self.z_display_min = self.z_data_min - 0.01
                    if self.z_data_max > self.z_display_max:
                        self.z_display_max = self.z_data_max + 0.01

                else:
                    logger.warning("Z值计算失败，使用默认范围")
            except Exception as z_error:
                logger.error(f"计算Z值范围失败: {z_error}")

            # 关键改进：只在第一次或者数据范围变化时重新设置坐标轴
            if not self.axes_initialized:
                self._setup_axes()
                self.axes_initialized = True
            else:
                # 只更新Z轴范围（如果需要）
                self._apply_axis_limits()

            # 立即绘制初始点
            if len(coordinates) > 0:
                try:
                    coord0 = coordinates[0]
                    x0 = float(coord0.get('center_x', 0))
                    y0 = float(coord0.get('center_y', 0))
                    z0 = float(coord0.get('center_z', 0))

                    if not all(np.isfinite([x0, y0, z0])):
                        logger.error(f"起点坐标无效: x0={x0}, y0={y0}, z0={z0}")
                        return False

                    # 绘制起点
                    self.scatter_points = self.ax.scatter(
                        [x0], [y0], [z0],
                        c='green',  # 改为绿色表示起点
                        s=100,
                        marker='o',
                        alpha=0.9,
                        edgecolors='darkgreen',
                        linewidth=2,
                        label='start'
                    )

                    # 再次确保坐标轴范围固定
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

    def start_animation(self, animation_speed: int = 50):
        """启动轨迹动画"""
        try:

            if not hasattr(self, 'animation_data') or not self.animation_data:
                logger.error("没有动画数据，请先调用 draw_trajectory_3d_incremental")
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
                        y_end = float(last_coord.get('center_y', 0))
                        z_end = float(last_coord.get('center_z', 0))

                        self.ax.scatter(
                            [x_end], [y_end], [z_end],
                            c='red',
                            s=100,
                            marker='o',
                            alpha=0.9,
                            edgecolors='darkred',
                            linewidth=2,
                            label='end'
                        )
                        self.canvas.draw_idle()
                    except Exception as e:
                        logger.error(f"绘制终点失败: {e}")

                self.animation_progress_updated.emit(100)
                self.animation_finished.emit()
                return

            coord1 = self.animation_data[self.animation_index]
            coord2 = self.animation_data[self.animation_index + 1]

            self._draw_single_segment(coord1, coord2, self.animation_index, len(self.animation_data))

            # 只在需要时重新应用范围，而不是完全重新设置
            self._apply_axis_limits()

            # 刷新画布
            self.canvas.draw_idle()

            # 更新进度
            progress = int((self.animation_index / max(1, len(self.animation_data) - 2)) * 100)
            self.animation_progress_updated.emit(progress)

            # 发送坐标信息
            self.coordinate_info_updated.emit({
                'x': float(coord2.get('center_x', 0)),
                'y': float(coord2.get('center_y', 0)),
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

        # 关键：不清空轨迹线，保持显示
        logger.info("动画已停止")

    def clear_figure(self):
        """清空图表"""
        try:
            if self.ax is not None:
                self.ax.clear()
                self._setup_axes()  # 清空后重新设置坐标轴
            self.trajectory_lines = []
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