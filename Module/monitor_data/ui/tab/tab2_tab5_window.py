# Form implementation generated from reading ui file 'tab2_tab5_window.ui'
#
# Created by: PyQt6 UI code generator 6.9.1
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_tab_5_window(object):
    def setupUi(self, tab_5_window):
        tab_5_window.setObjectName("tab_5_window")
        tab_5_window.resize(1083, 813)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(tab_5_window.sizePolicy().hasHeightForWidth())
        tab_5_window.setSizePolicy(sizePolicy)
        self.centralwidget = QtWidgets.QWidget(parent=tab_5_window)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.centralwidget.sizePolicy().hasHeightForWidth())
        self.centralwidget.setSizePolicy(sizePolicy)
        self.centralwidget.setObjectName("centralwidget")
        self.horizontalLayoutWidget = QtWidgets.QWidget(parent=self.centralwidget)
        self.horizontalLayoutWidget.setGeometry(QtCore.QRect(0, 0, 1081, 771))
        self.horizontalLayoutWidget.setObjectName("horizontalLayoutWidget")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.horizontalLayoutWidget)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 100)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.right_layout = QtWidgets.QVBoxLayout()
        self.right_layout.setContentsMargins(-1, -1, -1, 50)
        self.right_layout.setObjectName("right_layout")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setContentsMargins(5, 5, 5, 5)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.start = QtWidgets.QPushButton(parent=self.horizontalLayoutWidget)
        self.start.setObjectName("start")
        self.horizontalLayout_2.addWidget(self.start)
        self.stop = QtWidgets.QPushButton(parent=self.horizontalLayoutWidget)
        self.stop.setObjectName("stop")
        self.horizontalLayout_2.addWidget(self.stop)
        self.refresh = QtWidgets.QPushButton(parent=self.horizontalLayoutWidget)
        self.refresh.setObjectName("refresh")
        self.horizontalLayout_2.addWidget(self.refresh)
        self.right_layout.addLayout(self.horizontalLayout_2)
        self.function_03_layout = QtWidgets.QVBoxLayout()
        self.function_03_layout.setObjectName("function_03_layout")
        self.function_03 = QtWidgets.QGroupBox(parent=self.horizontalLayoutWidget)
        self.function_03.setObjectName("function_03")
        self.function_03_layout.addWidget(self.function_03)
        self.right_layout.addLayout(self.function_03_layout)
        self.function_01_layout = QtWidgets.QVBoxLayout()
        self.function_01_layout.setObjectName("function_01_layout")
        self.function_01 = QtWidgets.QGroupBox(parent=self.horizontalLayoutWidget)
        self.function_01.setObjectName("function_01")
        self.function_01_layout.addWidget(self.function_01)
        self.right_layout.addLayout(self.function_01_layout)
        self.function_02_layout = QtWidgets.QVBoxLayout()
        self.function_02_layout.setObjectName("function_02_layout")
        self.function_02 = QtWidgets.QGroupBox(parent=self.horizontalLayoutWidget)
        self.function_02.setObjectName("function_02")
        self.function_02_layout.addWidget(self.function_02)
        self.right_layout.addLayout(self.function_02_layout)
        self.function_11_layout = QtWidgets.QVBoxLayout()
        self.function_11_layout.setObjectName("function_11_layout")
        self.function_11 = QtWidgets.QGroupBox(parent=self.horizontalLayoutWidget)
        self.function_11.setObjectName("function_11")
        self.function_11_layout.addWidget(self.function_11)
        self.right_layout.addLayout(self.function_11_layout)
        self.right_layout.setStretch(1, 2)
        self.right_layout.setStretch(2, 2)
        self.right_layout.setStretch(3, 2)
        self.right_layout.setStretch(4, 2)
        self.horizontalLayout.addLayout(self.right_layout)
        self.left_layout = QtWidgets.QVBoxLayout()
        self.left_layout.setContentsMargins(-1, -1, -1, 50)
        self.left_layout.setObjectName("left_layout")
        self.function_04_layout = QtWidgets.QVBoxLayout()
        self.function_04_layout.setObjectName("function_04_layout")
        self.function_04 = QtWidgets.QGroupBox(parent=self.horizontalLayoutWidget)
        self.function_04.setObjectName("function_04")
        self.function_04_layout.addWidget(self.function_04)
        self.left_layout.addLayout(self.function_04_layout)
        self.verticalLayout_3 = QtWidgets.QVBoxLayout()
        self.verticalLayout_3.setContentsMargins(-1, 0, -1, -1)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.horizontalLayout_6 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.nowdata_trend_label = QtWidgets.QLabel(parent=self.horizontalLayoutWidget)
        self.nowdata_trend_label.setObjectName("nowdata_trend_label")
        self.horizontalLayout_6.addWidget(self.nowdata_trend_label)
        self.export_alldata_btn = QtWidgets.QPushButton(parent=self.horizontalLayoutWidget)
        self.export_alldata_btn.setObjectName("export_alldata_btn")
        self.horizontalLayout_6.addWidget(self.export_alldata_btn)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self.horizontalLayout_6.addItem(spacerItem)
        self.verticalLayout_3.addLayout(self.horizontalLayout_6)
        self.now_data_layout = QtWidgets.QHBoxLayout()
        self.now_data_layout.setObjectName("now_data_layout")
        self.verticalLayout_3.addLayout(self.now_data_layout)
        self.verticalLayout_3.setStretch(1, 6)
        self.left_layout.addLayout(self.verticalLayout_3)
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setContentsMargins(-1, 0, -1, -1)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.label = QtWidgets.QLabel(parent=self.horizontalLayoutWidget)
        self.label.setObjectName("label")
        self.horizontalLayout_3.addWidget(self.label)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        self.detaildata_layout = QtWidgets.QVBoxLayout()
        self.detaildata_layout.setObjectName("detaildata_layout")
        self.verticalLayout.addLayout(self.detaildata_layout)
        self.verticalLayout.setStretch(1, 6)
        self.left_layout.addLayout(self.verticalLayout)
        self.left_layout.setStretch(0, 1)
        self.left_layout.setStretch(1, 2)
        self.left_layout.setStretch(2, 2)
        self.horizontalLayout.addLayout(self.left_layout)
        self.horizontalLayout.setStretch(1, 8)
        tab_5_window.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(parent=tab_5_window)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1083, 22))
        self.menubar.setObjectName("menubar")
        tab_5_window.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(parent=tab_5_window)
        self.statusbar.setObjectName("statusbar")
        tab_5_window.setStatusBar(self.statusbar)

        self.retranslateUi(tab_5_window)
        QtCore.QMetaObject.connectSlotsByName(tab_5_window)

    def retranslateUi(self, tab_5_window):
        _translate = QtCore.QCoreApplication.translate
        tab_5_window.setWindowTitle(_translate("tab_5_window", "MainWindow"))
        self.start.setText(_translate("tab_5_window", "开始获取信息"))
        self.stop.setText(_translate("tab_5_window", "停止获取信息"))
        self.refresh.setText(_translate("tab_5_window", "刷新全部信息"))
        self.function_03.setTitle(_translate("tab_5_window", "传感器配置信息"))
        self.function_01.setTitle(_translate("tab_5_window", "输出端口状态信息"))
        self.function_02.setTitle(_translate("tab_5_window", "传感器状态信息"))
        self.function_11.setTitle(_translate("tab_5_window", "模块id信息"))
        self.function_04.setTitle(_translate("tab_5_window", "数据信息"))
        self.nowdata_trend_label.setText(_translate("tab_5_window", "当前趋势"))
        self.export_alldata_btn.setText(_translate("tab_5_window", "导出"))
        self.label.setText(_translate("tab_5_window", "详细数据："))
