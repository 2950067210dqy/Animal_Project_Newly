# Form implementation generated from reading ui file 'tab7_window.ui'
#
# Created by: PyQt6 UI code generator 6.9.1
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_tab7_window(object):
    def setupUi(self, tab7_window):
        tab7_window.setObjectName("tab7_window")
        tab7_window.resize(911, 584)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(tab7_window.sizePolicy().hasHeightForWidth())
        tab7_window.setSizePolicy(sizePolicy)
        self.centralwidget = QtWidgets.QWidget(parent=tab7_window)
        self.centralwidget.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.centralwidget.sizePolicy().hasHeightForWidth())
        self.centralwidget.setSizePolicy(sizePolicy)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayoutWidget_3 = QtWidgets.QWidget(parent=self.centralwidget)
        self.verticalLayoutWidget_3.setGeometry(QtCore.QRect(7, 7, 901, 541))
        self.verticalLayoutWidget_3.setObjectName("verticalLayoutWidget_3")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.verticalLayoutWidget_3)
        self.verticalLayout_2.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinAndMaxSize)
        self.verticalLayout_2.setContentsMargins(5, 5, 5, 5)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMaximumSize)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_3 = QtWidgets.QLabel(parent=self.verticalLayoutWidget_3)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout.addWidget(self.label_3)
        self.tab_7_port_combox = QtWidgets.QComboBox(parent=self.verticalLayoutWidget_3)
        self.tab_7_port_combox.setMinimumSize(QtCore.QSize(250, 0))
        self.tab_7_port_combox.setObjectName("tab_7_port_combox")
        self.horizontalLayout.addWidget(self.tab_7_port_combox)
        self.tab_7_refresh_port_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget_3)
        self.tab_7_refresh_port_btn.setMinimumSize(QtCore.QSize(0, 50))
        self.tab_7_refresh_port_btn.setObjectName("tab_7_refresh_port_btn")
        self.horizontalLayout.addWidget(self.tab_7_refresh_port_btn)
        self.label = QtWidgets.QLabel(parent=self.verticalLayoutWidget_3)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.config_name_label = QtWidgets.QLabel(parent=self.verticalLayoutWidget_3)
        self.config_name_label.setObjectName("config_name_label")
        self.horizontalLayout.addWidget(self.config_name_label)
        self.load_config_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget_3)
        self.load_config_btn.setObjectName("load_config_btn")
        self.horizontalLayout.addWidget(self.load_config_btn)
        self.save_config_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget_3)
        self.save_config_btn.setObjectName("save_config_btn")
        self.horizontalLayout.addWidget(self.save_config_btn)
        self.default_config_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget_3)
        self.default_config_btn.setObjectName("default_config_btn")
        self.horizontalLayout.addWidget(self.default_config_btn)
        self.verticalLayout_2.addLayout(self.horizontalLayout)
        self.content_layout = QtWidgets.QVBoxLayout()
        self.content_layout.setObjectName("content_layout")
        self.verticalLayout_2.addLayout(self.content_layout)
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.start_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget_3)
        self.start_btn.setObjectName("start_btn")
        self.horizontalLayout_2.addWidget(self.start_btn)
        self.stop_btn = QtWidgets.QPushButton(parent=self.verticalLayoutWidget_3)
        self.stop_btn.setObjectName("stop_btn")
        self.horizontalLayout_2.addWidget(self.stop_btn)
        spacerItem1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem1)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.verticalLayout_3 = QtWidgets.QVBoxLayout()
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.label_4 = QtWidgets.QLabel(parent=self.verticalLayoutWidget_3)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_4.sizePolicy().hasHeightForWidth())
        self.label_4.setSizePolicy(sizePolicy)
        self.label_4.setObjectName("label_4")
        self.verticalLayout_3.addWidget(self.label_4)
        self.tab_7_responselist = QtWidgets.QListWidget(parent=self.verticalLayoutWidget_3)
        self.tab_7_responselist.setObjectName("tab_7_responselist")
        self.verticalLayout_3.addWidget(self.tab_7_responselist)
        self.verticalLayout_3.setStretch(1, 1)
        self.verticalLayout.addLayout(self.verticalLayout_3)
        self.verticalLayout.setStretch(1, 1)
        self.verticalLayout_2.addLayout(self.verticalLayout)
        self.verticalLayout_2.setStretch(1, 3)
        tab7_window.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(parent=tab7_window)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 911, 22))
        self.menubar.setDefaultUp(False)
        self.menubar.setNativeMenuBar(True)
        self.menubar.setObjectName("menubar")
        tab7_window.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(parent=tab7_window)
        self.statusbar.setObjectName("statusbar")
        tab7_window.setStatusBar(self.statusbar)

        self.retranslateUi(tab7_window)
        QtCore.QMetaObject.connectSlotsByName(tab7_window)

    def retranslateUi(self, tab7_window):
        _translate = QtCore.QCoreApplication.translate
        tab7_window.setWindowTitle(_translate("tab7_window", "MainWindow"))
        self.label_3.setText(_translate("tab7_window", "串口："))
        self.tab_7_refresh_port_btn.setText(_translate("tab7_window", "刷新串口"))
        self.label.setText(_translate("tab7_window", "当前配置文件："))
        self.config_name_label.setText(_translate("tab7_window", "default.json"))
        self.load_config_btn.setText(_translate("tab7_window", "加载配置文件"))
        self.save_config_btn.setText(_translate("tab7_window", "保存配置文件"))
        self.default_config_btn.setText(_translate("tab7_window", "默认配置文件"))
        self.start_btn.setText(_translate("tab7_window", "开始实验"))
        self.stop_btn.setText(_translate("tab7_window", "停止实验"))
        self.label_4.setText(_translate("tab7_window", "响应信息"))
