# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settings.ui'
##
## Created by: Qt User Interface Compiler version 6.5.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QLabel, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget, QLineEdit, QCheckBox)
from . import resources_rc

class Ui_SettingsDialog(object):
    def setupUi(self, SettingsDialog):
        if not SettingsDialog.objectName():
            SettingsDialog.setObjectName(u"SettingsDialog")
        SettingsDialog.setWindowModality(Qt.ApplicationModal)
        SettingsDialog.resize(452, 156)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(SettingsDialog.sizePolicy().hasHeightForWidth())
        SettingsDialog.setSizePolicy(sizePolicy)
        icon = QIcon()
        icon.addFile(u":/icons/icons/gear.png", QSize(), QIcon.Normal, QIcon.Off)
        SettingsDialog.setWindowIcon(icon)
        self.verticalLayout = QVBoxLayout(SettingsDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(9, -1, -1, -1)
        self.verticalLayout_2 = QVBoxLayout()
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setHorizontalSpacing(30)
        self.formLayout.setVerticalSpacing(6)
        self.label = QLabel(SettingsDialog)
        self.label.setObjectName(u"label")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label)

        self.label_streamdeck = QLabel(SettingsDialog)
        self.label_streamdeck.setObjectName(u"label_streamdeck")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.label_streamdeck)

        self.label_brightness = QLabel(SettingsDialog)
        self.label_brightness.setObjectName(u"label_brightness")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.label_brightness)

        self.brightness = QSlider(SettingsDialog)
        self.brightness.setObjectName(u"brightness")
        self.brightness.setOrientation(Qt.Horizontal)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.brightness)

        self.label_dim = QLabel(SettingsDialog)
        self.label_dim.setObjectName(u"label_dim")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_dim)

        self.dim = QComboBox(SettingsDialog)
        self.dim.setObjectName(u"dim")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.dim)

        self.label_brightness_dimmed = QLabel(SettingsDialog)
        self.label_brightness_dimmed.setObjectName(u"label_brightness_dimmed")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.label_brightness_dimmed)

        self.brightness_dimmed = QSlider(SettingsDialog)
        self.brightness_dimmed.setObjectName(u"brightness_dimmed")
        self.brightness_dimmed.setOrientation(Qt.Horizontal)

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.brightness_dimmed)

        self.label_url = QLabel(SettingsDialog)
        self.label_url.setObjectName(u"label_url")

        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.label_url)

        self.url = QLineEdit(SettingsDialog)
        self.url.setObjectName(u"url")

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.url)

        self.label_token = QLabel(SettingsDialog)
        self.label_token.setObjectName(u"label_token")

        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.label_token)

        self.token = QLineEdit(SettingsDialog)
        self.token.setObjectName(u"token")

        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.token)

        self.label_port = QLabel(SettingsDialog)
        self.label_port.setObjectName(u"label_port")

        self.formLayout.setWidget(6, QFormLayout.LabelRole, self.label_port)

        self.port = QLineEdit(SettingsDialog)
        self.port.setObjectName(u"port")

        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.port)

        self.label_ssl = QLabel(SettingsDialog)
        self.label_ssl.setObjectName(u"label_ssl")

        self.formLayout.setWidget(7, QFormLayout.LabelRole, self.label_ssl)

        self.ssl = QCheckBox(SettingsDialog)
        self.ssl.setObjectName(u"ssl")

        self.formLayout.setWidget(7, QFormLayout.FieldRole, self.ssl)

        self.verticalLayout_2.addLayout(self.formLayout)

        self.verticalLayout.addLayout(self.verticalLayout_2)

        self.buttonBox = QDialogButtonBox(SettingsDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(SettingsDialog)
        self.buttonBox.accepted.connect(SettingsDialog.accept)
        self.buttonBox.rejected.connect(SettingsDialog.reject)

        QMetaObject.connectSlotsByName(SettingsDialog)
    # setupUi

    def retranslateUi(self, SettingsDialog):
        SettingsDialog.setWindowTitle(QCoreApplication.translate("SettingsDialog", u"Stream Deck Settings", None))
        self.label.setText(QCoreApplication.translate("SettingsDialog", u"Stream Deck:", None))
        self.label_streamdeck.setText("")
        self.label_brightness.setText(QCoreApplication.translate("SettingsDialog", u"Brightness:", None))
        self.label_dim.setText(QCoreApplication.translate("SettingsDialog", u"Auto dim after:", None))
        self.dim.setCurrentText("")
        self.label_brightness_dimmed.setText(QCoreApplication.translate("SettingsDialog", u"Dim to %:", None))
        self.label_url.setText(QCoreApplication.translate("SettingsDialog", "HASS URL: ", None))
        self.label_token.setText(QCoreApplication.translate("SettingsDialog", "HASS Token: ", None))
        self.label_port.setText(QCoreApplication.translate("SettingsDialog", "HASS Port: ", None))
        self.label_ssl.setText(QCoreApplication.translate("SettingsDialog", "HASS SSL: ", None))
    # retranslateUi

