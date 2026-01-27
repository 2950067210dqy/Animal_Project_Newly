from PyQt6 import QtCore, QtGui, QtWidgets
from loguru import logger


class Ui_Main_window(object):
    def setupUi(self, Main_window, enabled_cage_ids=None):
        """
        根据开启的笼子ID动态创建UI
        enabled_cage_ids: 开启的笼子ID列表，如果为None则默认使用1-16
        按照顺序依次排列，每行4个，没有开启的笼子不创建
        但网格大小固定为16个笼子的标准大小
        """
        # 如果没有提供笼子ID，则默认使用1-16
        if enabled_cage_ids is None:
            enabled_cage_ids = list(range(1, 17))

        Main_window.setObjectName("Main_window")
        Main_window.resize(1400, 900)
        self.centralwidget = QtWidgets.QWidget(parent=Main_window)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayoutWidget = QtWidgets.QWidget(parent=self.centralwidget)
        self.verticalLayoutWidget.setGeometry(QtCore.QRect(0, 0, 1398, 851))
        self.verticalLayoutWidget.setObjectName("verticalLayoutWidget")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.verticalLayoutWidget)
        self.verticalLayout.setContentsMargins(5, 5, 5, 5)
        self.verticalLayout.setObjectName("verticalLayout")

        # 顶部控制栏
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetDefaultConstraint)
        self.horizontalLayout.setObjectName("horizontalLayout")

        self.label = QtWidgets.QLabel(parent=self.verticalLayoutWidget)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)

        self.state_label = QtWidgets.QLabel(parent=self.verticalLayoutWidget)
        self.state_label.setObjectName("state_label")
        self.horizontalLayout.addWidget(self.state_label)

        self.start_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget)
        self.start_btn.setObjectName("start_btn")
        self.horizontalLayout.addWidget(self.start_btn)

        self.stop_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget)
        self.stop_btn.setObjectName("stop_btn")
        self.horizontalLayout.addWidget(self.stop_btn)

        self.pause_resume_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget)
        self.pause_resume_btn.setObjectName("pause_resume_btn")
        self.horizontalLayout.addWidget(self.pause_resume_btn)

        self.deep_camera_config = QtWidgets.QPushButton(parent=self.verticalLayoutWidget)
        self.deep_camera_config.setObjectName("deep_camera_config")
        self.horizontalLayout.addWidget(self.deep_camera_config)

        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Policy.Expanding,
                                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.horizontalLayout.addItem(spacerItem)

        self.verticalLayout.addLayout(self.horizontalLayout)

        # ==================== 固定大小的网格布局：按开启的笼子依次排列 ====================
        self.gridLayout_main = QtWidgets.QGridLayout()
        self.gridLayout_main.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_main.setSpacing(10)
        self.gridLayout_main.setObjectName("gridLayout_main")

        # 创建笼子的GroupBox和图形视图
        self.cage_widgets = {}

        # 固定网格大小参数（按16个笼子的标准）
        FIXED_ROWS = 4
        FIXED_COLS = 4

        # 对开启的笼子进行排序
        sorted_enabled_cage_ids = sorted(enabled_cage_ids)
        cage_count = len(sorted_enabled_cage_ids)

        logger.info(f"创建固定网格布局: {FIXED_ROWS} 行 × {FIXED_COLS} 列，显示 {cage_count} 个笼子")

        # 只为开启的笼子创建UI，按顺序排列
        for idx, cage_id in enumerate(sorted_enabled_cage_ids):
            row = idx // FIXED_COLS
            col = idx % FIXED_COLS

            # 创建GroupBox
            groupBox = QtWidgets.QGroupBox(parent=self.verticalLayoutWidget)
            groupBox.setObjectName(f"groupBox_cage_{cage_id}")
            groupBox.setTitle(f"鼠笼 {cage_id}")

            font = QtGui.QFont()
            font.setPointSize(5)
            groupBox.setFont(font)

            # 创建垂直布局
            vLayout = QtWidgets.QVBoxLayout(groupBox)
            vLayout.setContentsMargins(5, 5, 5, 5)
            vLayout.setSpacing(0)
            vLayout.setObjectName(f"vLayout_cage_{cage_id}")

            # 创建 canvas 容器（直接填充整个 GroupBox）
            canvas_widget = QtWidgets.QWidget(parent=groupBox)
            canvas_widget.setObjectName(f"canvas_cage_{cage_id}")
            canvas_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                        QtWidgets.QSizePolicy.Policy.Expanding)
            vLayout.addWidget(canvas_widget, 1)

            # 添加到网格布局
            self.gridLayout_main.addWidget(groupBox, row, col)

            # 存储引用
            self.cage_widgets[cage_id] = {
                'groupBox': groupBox,
                'canvas_widget': canvas_widget
            }

            logger.info(f"创建笼子 {cage_id} UI: 位置({row}, {col})")

        # ============== 关键：设置固定的网格权重（按4x4标准）==============
        # 为所有4行设置固定权重
        for row in range(FIXED_ROWS):
            self.gridLayout_main.setRowStretch(row, 1)

        # 为所有4列设置固定权重
        for col in range(FIXED_COLS):
            self.gridLayout_main.setColumnStretch(col, 1)

        # 添加空白占位符到未使用的网格位置，保持布局稳定
        for position in range(cage_count, FIXED_ROWS * FIXED_COLS):
            row = position // FIXED_COLS
            col = position % FIXED_COLS

            # 创建透明的占位符
            spacer_widget = QtWidgets.QWidget()
            spacer_widget.setStyleSheet("background: transparent;")
            spacer_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                        QtWidgets.QSizePolicy.Policy.Expanding)

            self.gridLayout_main.addWidget(spacer_widget, row, col)
            logger.debug(f"添加占位符到位置({row}, {col})")

        self.verticalLayout.addLayout(self.gridLayout_main)
        self.verticalLayout.setStretch(1, 6)

        Main_window.setCentralWidget(self.centralwidget)

        # 菜单栏
        self.menubar = QtWidgets.QMenuBar(parent=Main_window)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1400, 22))
        self.menubar.setObjectName("menubar")
        Main_window.setMenuBar(self.menubar)

        # 状态栏
        self.statusbar = QtWidgets.QStatusBar(parent=Main_window)
        self.statusbar.setObjectName("statusbar")
        Main_window.setStatusBar(self.statusbar)

        self.retranslateUi(Main_window)
        QtCore.QMetaObject.connectSlotsByName(Main_window)

    def retranslateUi(self, Main_window):
        _translate = QtCore.QCoreApplication.translate
        Main_window.setWindowTitle(_translate("Main_window", "三维轨迹监测系统"))
        self.label.setText(_translate("Main_window", "系统状态："))
        self.state_label.setText(_translate("Main_window", "未连接"))
        self.start_btn.setText(_translate("Main_window", "开始连接"))
        self.stop_btn.setText(_translate("Main_window", "停止连接"))
        self.pause_resume_btn.setText(_translate("Main_window", "全部暂停"))
        self.deep_camera_config.setText(_translate("Main_window", "相机配置"))