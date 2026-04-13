import json
import time
from collections import defaultdict
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QFileDialog,
    QStackedWidget, QLineEdit, QMessageBox
)
from loguru import logger
from Module.coord_3d.ui.image_canvas import ImageCanvas
from Module.coord_3d.ui.canvas_3d import Canvas3D
from Module.coord_3d.ui.dashboard_2d import Dashboard2D
from Module.coord_3d.core.math_engine import (
    interpolate_grid, compute_grid_3d_coords, solve_camera_matrix,
    apply_homography, get_perspective_transform, is_point_in_polygon,
    solve_height_with_xyz, solve_x_with_yz, solve_xy_with_z
)
from theme.ThemeQt6 import ThemedWindow


class Coord3DIndex(ThemedWindow):
    def __init__(self, parent=None):
        super().__init__()
        self._view_mode = "topdown"
        self._tool_mode = "add"
        self._image_meta = {"fileName": "", "width": 0, "height": 0}
        self._near_comp = 0.0
        self._depth_comp = 40.0
        self._init_ui()
        self._init_customize_ui()
        self._init_function()
        self._init_style_sheet()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = QWidget()
        self._sidebar.setFixedWidth(280)
        self._sidebar.setObjectName("sidebar")
        sl = QVBoxLayout(self._sidebar)
        sl.setContentsMargins(12, 12, 12, 12)
        sl.setSpacing(8)

        sl.addWidget(self._lbl("3D 标定构建系统", "sidebarTitle"))
        sl.addWidget(self._lbl("DLT + 2D Interp Hybrid", "sidebarSub"))

        sl.addWidget(self._lbl("工程文件", "sectionLabel"))
        self._btn_load_image = QPushButton("载入底图")
        self._btn_load_json = QPushButton("导入 JSON")
        sl.addWidget(self._btn_load_image)
        sl.addWidget(self._btn_load_json)

        sl.addWidget(self._lbl("工作模式", "sectionLabel"))
        self._mode_btns = {}
        for key, text in [("topdown", "1. 俯视"), ("perspective", "2. 侧视"),
                           ("region", "3. 区域高度"), ("3d", "4. 构建3D预览"), ("chart", "5. 2D轨迹分析")]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            self._mode_btns[key] = btn
            sl.addWidget(btn)

        self._layer_widget = QWidget()
        lw = QVBoxLayout(self._layer_widget)
        lw.setContentsMargins(0, 0, 0, 0)
        lw.addWidget(self._lbl("当前图层", "sectionLabel"))
        self._layer_combo = QComboBox()
        self._layer_combo.addItems(["标签1 (地面)", "标签2 (近端垂直面)", "标签3 (中间垂直面)", "标签4 (远端垂直面)"])
        lw.addWidget(self._layer_combo)
        gr = QHBoxLayout()
        self._spin_cols = QSpinBox(); self._spin_cols.setRange(2, 200); self._spin_cols.setValue(18)
        self._spin_rows = QSpinBox(); self._spin_rows.setRange(2, 200); self._spin_rows.setValue(31)
        gr.addWidget(QLabel("列(X)")); gr.addWidget(self._spin_cols)
        gr.addWidget(QLabel("行(Y)")); gr.addWidget(self._spin_rows)
        lw.addLayout(gr)
        sl.addWidget(self._layer_widget)

        sl.addWidget(self._lbl("工具", "sectionLabel"))
        tr = QHBoxLayout()
        self._tool_btns = {}
        for key, text in [("add", "打点"), ("move", "移动"), ("delete", "删除"), ("pan", "平移"), ("yolo", "YOLO")]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            self._tool_btns[key] = btn
            tr.addWidget(btn)
        sl.addLayout(tr)

        self._complete_widget = QWidget()
        cw = QHBoxLayout(self._complete_widget)
        cw.setContentsMargins(0, 0, 0, 0)
        self._btn_complete = QPushButton("补全图层")
        self._btn_clear = QPushButton("清除")
        self._btn_clear.setFixedWidth(50)
        cw.addWidget(self._btn_complete)
        cw.addWidget(self._btn_clear)
        sl.addWidget(self._complete_widget)

        self._comp_widget = QWidget()
        pw = QVBoxLayout(self._comp_widget)
        pw.setContentsMargins(0, 0, 0, 0)
        pw.addWidget(self._lbl("Y轴补偿", "sectionLabel"))
        pr = QHBoxLayout()
        self._spin_near = QDoubleSpinBox(); self._spin_near.setRange(-200, 200); self._spin_near.setValue(0)
        self._spin_depth = QDoubleSpinBox(); self._spin_depth.setRange(-200, 200); self._spin_depth.setValue(40)
        pr.addWidget(QLabel("近端")); pr.addWidget(self._spin_near)
        pr.addWidget(QLabel("远端")); pr.addWidget(self._spin_depth)
        pw.addLayout(pr)
        sl.addWidget(self._comp_widget)

        self._region_widget = QWidget()
        rw = QVBoxLayout(self._region_widget)
        rw.setContentsMargins(0, 0, 0, 0)
        rw.addWidget(self._lbl("区域设置", "sectionLabel"))
        self._region_name = QLineEdit("测试体重秤")
        self._region_height = QDoubleSpinBox()
        self._region_height.setRange(0, 500)
        self._region_height.setValue(50)
        self._region_y = QLineEdit("180")
        rw.addWidget(QLabel("名称")); rw.addWidget(self._region_name)
        rw.addWidget(QLabel("基准高度Z(mm)")); rw.addWidget(self._region_height)
        rw.addWidget(QLabel("锁定Y(选填mm)")); rw.addWidget(self._region_y)
        self._btn_finish_region = QPushButton("保存并闭合区域")
        rw.addWidget(self._btn_finish_region)
        sl.addWidget(self._region_widget)

        sl.addWidget(self._lbl("透明度", "sectionLabel"))
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(80)
        sl.addWidget(self._opacity_slider)
        sl.addStretch()

        self._btn_export = QPushButton("导出 JSON")
        self._btn_export.setObjectName("exportBtn")
        sl.addWidget(self._btn_export)

        root.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._canvas = ImageCanvas()
        self._canvas3d = Canvas3D()
        self._dashboard2d = Dashboard2D()
        self._stack.addWidget(self._canvas)       # 0
        self._stack.addWidget(self._canvas3d)     # 1
        self._stack.addWidget(self._dashboard2d)  # 2
        root.addWidget(self._stack, 1)

    def _lbl(self, text, obj_name=""):
        l = QLabel(text)
        if obj_name:
            l.setObjectName(obj_name)
        return l

    def _init_customize_ui(self):
        self._set_mode("topdown")
        self._set_tool("add")

    def _init_function(self):
        for k, btn in self._mode_btns.items():
            btn.clicked.connect(lambda _, key=k: self._set_mode(key))
        for k, btn in self._tool_btns.items():
            btn.clicked.connect(lambda _, key=k: self._set_tool(key))
        self._btn_load_image.clicked.connect(self._load_image)
        self._btn_load_json.clicked.connect(self._load_json)
        self._btn_complete.clicked.connect(self._auto_complete)
        self._btn_clear.clicked.connect(self._clear_layer)
        self._btn_finish_region.clicked.connect(self._finish_region)
        self._btn_export.clicked.connect(self._export_json)
        self._opacity_slider.valueChanged.connect(lambda v: self._on_opacity(v))
        self._layer_combo.currentIndexChanged.connect(
            lambda i: setattr(self._canvas, "active_label", str(i + 1)))
        self._spin_near.valueChanged.connect(lambda v: setattr(self, "_near_comp", v))
        self._spin_depth.valueChanged.connect(lambda v: setattr(self, "_depth_comp", v))
        self._canvas.yolo_box_added.connect(self._solve_yolo)

    def _init_style_sheet(self):
        if not hasattr(self, '_sidebar'):
            return
        self._sidebar.setStyleSheet("""
            QWidget#sidebar { background: #1e293b; }
            QLabel#sidebarTitle { color: #f1f5f9; font-size: 14px; font-weight: bold; }
            QLabel#sidebarSub { color: #64748b; font-size: 10px; }
            QLabel#sectionLabel { color: #64748b; font-size: 10px; font-weight: bold; margin-top: 4px; }
            QPushButton { background: #334155; color: #cbd5e1; border: 1px solid #475569;
                          border-radius: 6px; padding: 5px; }
            QPushButton:hover { background: #475569; }
            QPushButton:checked { background: #3b82f6; color: white; border-color: #2563eb; }
            QPushButton#exportBtn { background: #059669; color: white; font-weight: bold; padding: 10px; }
            QPushButton#exportBtn:hover { background: #10b981; }
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
                background: #0f172a; color: #93c5fd; border: 1px solid #334155;
                border-radius: 4px; padding: 4px; }
            QSlider::groove:horizontal { background: #334155; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #10b981; width: 14px; height: 14px;
                                         border-radius: 7px; margin: -5px 0; }
        """)

    # ------------------------------------------------------------------ 模式
    def _set_mode(self, mode):
        self._view_mode = mode
        for k, btn in self._mode_btns.items():
            btn.setChecked(k == mode)
        is_img = mode in ("topdown", "perspective", "region")
        self._layer_widget.setVisible(is_img and mode != "region")
        self._complete_widget.setVisible(is_img and mode != "region")
        self._comp_widget.setVisible(mode == "perspective")
        self._region_widget.setVisible(mode == "region")
        self._canvas.tool_mode = "region" if mode == "region" else self._tool_mode
        if mode == "3d":
            self._stack.setCurrentIndex(1)
            self._refresh_3d()
        elif mode == "chart":
            self._stack.setCurrentIndex(2)
        else:
            self._stack.setCurrentIndex(0)

    def _set_tool(self, tool):
        self._tool_mode = tool
        for k, btn in self._tool_btns.items():
            btn.setChecked(k == tool)
        if self._view_mode != "region":
            self._canvas.tool_mode = tool

    def _on_opacity(self, val):
        self._canvas.point_opacity = val / 100.0
        self._canvas.update()

    # ------------------------------------------------------------------ 文件
    def _load_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "载入底图", "", "图片 (*.png *.jpg *.bmp *.jpeg)")
        if not path:
            return
        px = QPixmap(path)
        if px.isNull():
            return
        fname = path.replace("\\", "/").split("/")[-1]
        self._image_meta = {"fileName": fname, "width": px.width(), "height": px.height()}
        self._canvas.set_image(px)
        self._set_mode("topdown")

    def _load_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入JSON", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            pts, grid = [], []
            for s in data.get("shapes", []):
                pt = {"id": str(time.time_ns()), "x": s["points"][0][0],
                      "y": s["points"][0][1], "label": s.get("label", "1")}
                desc = s.get("description", "")
                if desc.startswith("grid_"):
                    parts = desc.split("_")
                    pt["c"] = int(parts[1])
                    pt["r"] = int(parts[2])
                    grid.append(pt)
                else:
                    pts.append(pt)
            self._canvas.points = pts
            self._canvas.grid_data = grid
            self._canvas.update()
        except Exception as e:
            logger.error(f"导入JSON失败: {e}")
            QMessageBox.warning(self, "错误", f"JSON解析失败: {e}")

    # ------------------------------------------------------------------ 补全
    def _auto_complete(self):
        label = str(self._layer_combo.currentIndex() + 1)
        active = [p for p in self._canvas.points if p.get("label") == label]
        if len(active) < 4:
            QMessageBox.warning(self, "提示", f"图层[{label}]至少需要4个控制点！")
            return
        grid = interpolate_grid(active, self._spin_cols.value(), self._spin_rows.value(), label)
        self._canvas.grid_data = [p for p in self._canvas.grid_data if p.get("label") != label] + grid
        self._canvas.update()

    def _clear_layer(self):
        label = str(self._layer_combo.currentIndex() + 1)
        self._canvas.grid_data = [p for p in self._canvas.grid_data if p.get("label") != label]
        self._canvas.update()

    # ------------------------------------------------------------------ 区域
    def _finish_region(self):
        pts = self._canvas.current_region_pts
        if len(pts) < 3:
            QMessageBox.warning(self, "提示", "至少需要3个点才能闭合区域")
            return
        self._canvas.regions.append({
            "id": str(time.time_ns()),
            "name": self._region_name.text(),
            "height": self._region_height.value(),
            "y_val": self._region_y.text(),
            "points": pts[:]
        })
        self._canvas.current_region_pts = []
        self._canvas.update()

    # ------------------------------------------------------------------ 3D
    def _refresh_3d(self):
        p3d = compute_grid_3d_coords(self._canvas.points, self._canvas.grid_data)
        lines3d = []
        by_label = defaultdict(list)
        for p in p3d:
            by_label[p.get("label", "1")].append(p)
        for lbl, pts in by_label.items():
            lk = {(p["c"], p["r"]): p for p in pts if p.get("c") is not None}
            for (c, r), p1 in lk.items():
                for dc, dr in [(1, 0), (0, 1)]:
                    p2 = lk.get((c + dc, r + dr))
                    if p2:
                        lines3d.append((p1, p2))
        self._canvas3d.set_data(p3d, lines3d, self._canvas.solved_yolo)

    # ------------------------------------------------------------------ YOLO
    def _solve_yolo(self, _box):
        p3d = compute_grid_3d_coords(self._canvas.points, self._canvas.grid_data)
        valid = [p for p in p3d if p.get("x3") is not None and p.get("label") in ("1", "2", "3", "4")]
        P = solve_camera_matrix(valid) if len(valid) >= 12 else None

        l1 = [p for p in self._canvas.grid_data + self._canvas.points if p.get("label") == "1"]
        ground_h = None
        if l1:
            mc = max((p.get("c", 0) for p in l1), default=0)
            mr = max((p.get("r", 0) for p in l1), default=0)
            lk = {(p["c"], p["r"]): p for p in l1 if p.get("c") is not None}
            pTL = lk.get((0, 0)); pTR = lk.get((mc, 0))
            pBL = lk.get((0, mr)); pBR = lk.get((mc, mr))
            if pTL and pTR and pBL and pBR:
                phys = [{"x": -90, "y": 310}, {"x": 90, "y": 310},
                        {"x": -90, "y": 0}, {"x": 90, "y": 0}]
                H1 = get_perspective_transform([pTL, pTR, pBL, pBR], phys)
                H2 = get_perspective_transform(phys, [pTL, pTR, pBL, pBR])
                if H1 and H2:
                    ground_h = {"Pix_to_XY": H1, "XY_to_Pix": H2}

        solved = []
        for box in self._canvas.yolo_boxes:
            uc = (box["startX"] + box["endX"]) / 2
            vb = max(box["startY"], box["endY"])
            vt = (box["startY"] + box["endY"]) / 2
            Zb, fY = 0.0, None
            for r in self._canvas.regions:
                if is_point_in_polygon({"x": uc, "y": vb}, r.get("points", [])):
                    Zb = r["height"]
                    fY = r.get("y_val", "")
                    break
            Xp, Yp = 0.0, 0.0
            if ground_h:
                raw = apply_homography(ground_h["Pix_to_XY"], {"x": uc, "y": vb})
                if raw:
                    Xp, Yp = raw["x"], raw["y"]
            if P and Zb > 0:
                if fY:
                    Yp = float(fY)
                    ex = solve_x_with_yz(P, uc, Yp, Zb)
                    if ex is not None:
                        Xp = ex
                else:
                    ep = solve_xy_with_z(P, uc, vb, Zb)
                    if ep:
                        Xp, Yp = ep["x"], ep["y"]
            Y_u = Yp
            if not (Zb > 0 and fY):
                ratio = max(0.0, min(1.0, Yp / 310))
                Yp = Yp - self._near_comp * (1 - ratio) + self._depth_comp * ratio
            Xf = max(-90.0, min(90.0, Xp))
            Yf = max(0.0, min(310.0, Yp))
            Yf_u = max(0.0, min(310.0, Y_u))
            mH = solve_height_with_xyz(P, Xf, Yf_u, Zb, vt) if P else 0.0
            mH = max(0.0, min(mH, 150 - Zb))
            shadow = apply_homography(ground_h["XY_to_Pix"], {"x": Xf, "y": Yf}) if ground_h else None
            solved.append({
                **box, "cx": uc, "cy": vb,
                "shadow_x": shadow["x"] if shadow else uc,
                "shadow_y": shadow["y"] if shadow else vb,
                "X": Xf, "Y": Yf, "Z_base": Zb, "mouseHeight": mH, "Z_total": Zb + mH
            })
        self._canvas.solved_yolo = solved
        self._canvas.update()
        self._dashboard2d.set_data(solved)

    # ------------------------------------------------------------------ 导出
    def _export_json(self):
        mode = self._view_mode
        if mode == "chart":
            data = {
                "format": "2D_Trajectory_Analysis", "unit": "mm",
                "points": [{"index": i + 1, "X": round(d["X"], 2), "Y": round(d["Y"], 2),
                             "Z_base": round(d["Z_base"], 2), "mouseHeight": round(d["mouseHeight"], 2),
                             "Z_total": round(d["Z_total"], 2)}
                            for i, d in enumerate(self._canvas.solved_yolo)]
            }
            suffix = "_trajectory.json"
        elif mode == "region":
            data = {
                "format": "Height_Constraint_Regions", "unit": "mm",
                "regions": [{"id": r["id"], "name": r["name"], "height_z": r["height"],
                              "fixed_y": r["y_val"],
                              "polygon_points": [[p["x"], p["y"]] for p in r["points"]]}
                             for r in self._canvas.regions]
            }
            suffix = "_height_regions.json"
        elif mode == "3d":
            p3d = compute_grid_3d_coords(self._canvas.points, self._canvas.grid_data)
            data = {
                "format": "3D_Point_Structure", "unit": "mm", "count": len(p3d),
                "points": [{"label": p["label"], "col": p.get("c"), "row": p.get("r"),
                             "x": round(p["x3"], 2), "y": round(p["y3"], 2), "z": round(p["z3"], 2)}
                            for p in p3d]
            }
            suffix = "_3d_points.json"
        else:
            shapes = []
            for p in self._canvas.grid_data:
                shapes.append({"label": p["label"],
                                "points": [[round(p["x"], 2), round(p["y"], 2)]],
                                "description": f"grid_{p.get('c', 0)}_{p.get('r', 0)}",
                                "shape_type": "point"})
            for p in self._canvas.points:
                shapes.append({"label": p.get("label", "1"),
                                "points": [[round(p["x"], 2), round(p["y"], 2)]],
                                "description": "manual", "shape_type": "point"})
            data = {"version": "5.0.1", "shapes": shapes,
                    "imageWidth": self._image_meta["width"],
                    "imageHeight": self._image_meta["height"]}
            suffix = "_grid_points.json"

        base = self._image_meta["fileName"].rsplit(".", 1)[0] or "export"
        path, _ = QFileDialog.getSaveFileName(self, "导出JSON", base + suffix, "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
