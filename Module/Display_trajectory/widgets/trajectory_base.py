# from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsLineItem, QGraphicsEllipseItem
# from PyQt6.QtGui import QPen, QColor, QBrush, QPainter
# from PyQt6.QtCore import QPointF, Qt
# from theme.ThemeQt6 import ThemedWidget  # 项目统一主题组件基类
# from loguru import logger
#
#
# class TrajectoryBaseWidget(ThemedWidget, QGraphicsView):
#     """2D轨迹组件（模仿user_monitor的widget：继承ThemedWidget+Qt基础组件）"""
#
#     def __init__(self, parent=None):
#         # 先初始化主题基类，再初始化Qt组件（和user_monitor的widget初始化顺序一致）
#         ThemedWidget.__init__(self, parent)
#         QGraphicsView.__init__(self, parent)
#
#         self.logger = logger
#         self._init_theme()  # 主题初始化（继承ThemedWidget的必填方法，和user_monitor一致）
#         self._init_params()
#         self._init_scene()
#
#     def _init_theme(self):
#         """主题初始化（模仿user_monitor的widget主题配置）"""
#         # 复用ThemedWidget的主题样式，若user_monitor有自定义主题，此处完全复制
#         self.set_theme_style()  # ThemedWidget的统一方法
#         self.set_background_color(self.theme.bg_color)  # 从主题获取背景色（示例）
#
#     def _init_params(self):
#         """初始化参数（和之前一致，仅适配主题）"""
#         self.trajectory_lines = []
#         self.trajectory_points = []
#         self.start_point_item = None
#         self.end_point_item = None
#         # 从主题获取轨迹默认颜色（模仿user_monitor的主题化配置）
#         self.current_color = self.theme.primary_color or QColor(255, 0, 0)
#         self.cage_width = 600
#         self.cage_height = 400
#         self.grid_step = 50
#         self.is_dragging = False
#         self.drag_start_pos = QPointF()
#
#     def _init_scene(self):
#         """初始化场景（和之前一致，添加主题适配）"""
#         self.scene = QGraphicsScene(self)
#         self.setScene(self.scene)
#         self.setRenderHint(QPainter.RenderHint.Antialiasing)
#         self.setSceneRect(0, 0, self.cage_width, self.cage_height)
#         self._draw_cage()
#         self._draw_grid()
#         self.logger.debug("2D轨迹组件初始化完成（已应用主题）")
#
#     def _draw_cage(self):
#         """绘制鼠笼（从主题获取边框颜色，模仿user_monitor）"""
#         cage_pen = QPen(self.theme.border_color or QColor(0, 0, 0), 3)
#         self.scene.addRect(0, 0, self.cage_width, self.cage_height, cage_pen)
#
#     def _draw_grid(self):
#         """绘制网格（从主题获取网格颜色，模仿user_monitor）"""
#         grid_pen = QPen(self.theme.grid_color or QColor(200, 200, 200), 1)
#         for y in range(0, self.cage_height + 1, self.grid_step):
#             self.scene.addLine(0, y, self.cage_width, y, grid_pen)
#         for x in range(0, self.cage_width + 1, self.grid_step):
#             self.scene.addLine(x, 0, x, self.cage_height, grid_pen)
#
#     # 以下update_trajectory、_draw_trajectory_lines等方法不变，仅颜色从主题获取
#     def update_trajectory(self, points_list):
#         try:
#             if not isinstance(points_list, list) or len(points_list) < 2:
#                 self.logger.warning("轨迹点格式错误")
#                 return
#             self._clear_trajectory()
#             self.trajectory_points = points_list
#             self._draw_trajectory_lines()
#             self._mark_start_end()
#         except Exception as e:
#             self.logger.error(f"更新轨迹失败：{str(e)}")
#
#     def _draw_trajectory_lines(self):
#         trajectory_pen = QPen(self.current_color, 2)
#         for i in range(len(self.trajectory_points) - 1):
#             x1, y1 = self._clamp_point(self.trajectory_points[i])
#             x2, y2 = self._clamp_point(self.trajectory_points[i + 1])
#             line_item = QGraphicsLineItem(x1, y1, x2, y2)
#             line_item.setPen(trajectory_pen)
#             self.scene.addItem(line_item)
#             self.trajectory_lines.append(line_item)
#
#     def _mark_start_end(self):
#         sx, sy = self._clamp_point(self.trajectory_points[0])
#         self.start_point_item = QGraphicsEllipseItem(sx - 5, sy - 5, 10, 10)
#         self.start_point_item.setBrush(QBrush(self.theme.success_color or QColor(0, 255, 0)))
#         self.scene.addItem(self.start_point_item)
#
#         ex, ey = self._clamp_point(self.trajectory_points[-1])
#         self.end_point_item = QGraphicsEllipseItem(ex - 5, ey - 5, 10, 10)
#         self.end_point_item.setBrush(QBrush(self.theme.info_color or QColor(0, 0, 255)))
#         self.scene.addItem(self.end_point_item)
#
#     def _clamp_point(self, point):
#         x, y = point
#         return max(0, min(self.cage_width, x)), max(0, min(self.cage_height, y))
#
#     def clear_trajectory(self):
#         self._clear_trajectory()
#
#     def _clear_trajectory(self):
#         for line in self.trajectory_lines:
#             self.scene.removeItem(line)
#         self.trajectory_lines.clear()
#         if self.start_point_item:
#             self.scene.removeItem(self.start_point_item)
#             self.start_point_item = None
#         if self.end_point_item:
#             self.scene.removeItem(self.end_point_item)
#             self.end_point_item = None
#
#     # 交互方法不变
#     def wheelEvent(self, event):
#         zoom_factor = 1.1 if event.angleDelta().y() > 0 else 0.9
#         self.scale(zoom_factor, zoom_factor)
#
#     def mousePressEvent(self, event):
#         if event.button() == Qt.MouseButton.LeftButton:
#             self.is_dragging = True
#             self.drag_start_pos = self.mapToScene(event.pos())
#
#     def mouseMoveEvent(self, event):
#         if self.is_dragging:
#             current_pos = self.mapToScene(event.pos())
#             delta = current_pos - self.drag_start_pos
#             self.translate(delta.x(), delta.y())
#             self.drag_start_pos = current_pos
#
#     def mouseReleaseEvent(self, event):
#         if event.button() == Qt.MouseButton.LeftButton:
#             self.is_dragging = False