
import matplotlib
from PyQt6.QtCore import Qt
from loguru import logger
from matplotlib.figure import Figure

matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
class ChartCanvas(FigureCanvas):
    """增强的图表画布，支持鼠标交互"""

    def __init__(self, figure: Figure, ax, parent=None):
        super().__init__(figure)
        self.setParent(parent)
        self.ax = ax
        self.figure = figure
        # 连接鼠标事件到图表
        self.mpl_connect('motion_notify_event', self.on_mouse_move)

        # 添加关键：启用鼠标事件
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _format_time_label(self, value: float) -> str:
        """将秒数格式化为时间标签 (HH:MM:SS)"""
        try:
            # 处理None值
            if value is None:
                return ""

            # 转换为float
            value = float(value)

            # 处理负数
            if value < 0:
                return f"-{self._format_time_label(-value)}"

            hours = int(value // 3600)
            minutes = int((value % 3600) // 60)
            seconds = int(value % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception as e:
            print(f"格式化时间标签出错: {e}")
            return str(value)
    def on_mouse_move(self, event):
        """鼠标移动事件 - 显示数据点提示"""
        # 检查事件是否有效
        if event is None or event.inaxes is None:
            self.clear_tooltip()
            return

        # 检查是否在坐标轴内
        if event.inaxes != self.ax:
            self.clear_tooltip()
            return

        # 检查坐标是否有效
        if event.xdata is None or event.ydata is None:
            self.clear_tooltip()
            return

        try:
            # 获取所有line对象
            for line in self.ax.get_lines():
                xdata = line.get_xdata()
                ydata = line.get_ydata()

                if len(xdata) == 0 or len(ydata) == 0:
                    continue

                # 查找最近的数据点
                min_dist = float('inf')
                closest_idx = -1

                for i in range(len(xdata)):
                    if xdata[i] is None or ydata[i] is None:
                        continue

                    try:
                        # 计算距离时需要处理不同类型的数据
                        x_val = float(xdata[i]) if not isinstance(xdata[i], str) else i
                        y_val = float(ydata[i]) if not isinstance(ydata[i], str) else 0

                        dist = ((event.xdata - x_val) ** 2 +
                                (event.ydata - y_val) ** 2) ** 0.5

                        if dist < min_dist:
                            min_dist = dist
                            closest_idx = i
                    except (TypeError, ValueError):
                        continue

                # 如果找到点且距离较近
                if closest_idx >= 0 and min_dist < 2:
                    label = line.get_label()
                    x_val = xdata[closest_idx]
                    y_val = ydata[closest_idx]

                    # # 格式化X值
                    # if isinstance(x_val, (int, float)):
                    #     x_str = f"{x_val:.2f}"
                    # else:
                    #     x_str = str(x_val)

                    # 格式化Y值
                    try:
                        y_str = f"{float(y_val):.2f}"
                    except (TypeError, ValueError):
                        y_str = str(y_val)

                    tooltip_text = f"{label}\nX: {self._format_time_label(x_val)}\nY: {y_str}"

                    # 清除旧的文本
                    self.clear_tooltip()

                    # 添加新的提示框
                    self.ax.text(event.xdata, event.ydata, tooltip_text,
                                 fontsize=9, ha='left', va='bottom',
                                 bbox=dict(boxstyle='round',
                                           facecolor='wheat', alpha=0.8,
                                           edgecolor='gray', linewidth=0.5))
                    self.draw_idle()  # 使用draw_idle而不是draw
                    return

            # self.clear_tooltip()
        except Exception as e:
            logger.error(f"鼠标交互出错: {e}")
            self.clear_tooltip()

    def clear_tooltip(self):
        """清除提示"""
        try:
            # 只清除文本注释，不是标题和标签
            if self.ax.texts:
                # 保留第一个文本（通常是标题），只删除后面的提示框
                while len(self.ax.texts) > 0:
                    text = self.ax.texts[-1]
                    # 只删除提示框（有bbox的文本）
                    if hasattr(text, 'get_bbox_patch') and text.get_bbox_patch() is not None:
                        text.remove()
                    else:
                        break
            self.draw_idle()
        except Exception as e:
            logger.error(f"清除提示出错: {e}")