from PySide6.QtCore import (QCoreApplication, QMetaObject, QSize, Qt)
from PySide6.QtGui import (QIcon)
from PySide6.QtWidgets import (QComboBox, QDialogButtonBox, QFormLayout, QLabel, QSizePolicy,
                               QSlider, QVBoxLayout, QLineEdit, QCheckBox)


class UiSettingsDialog(object):

    def __init__(self, settings_dialog):
        icon = QIcon()
        icon.addFile(u"icons/gear.png", QSize(), QIcon.Normal, QIcon.Off)

        settings_dialog.setWindowModality(Qt.ApplicationModal)
        settings_dialog.resize(452, 156)
        settings_dialog.setWindowIcon(icon)
        settings_dialog.setWindowTitle("Stream Deck Settings")

        self.verticalLayout = QVBoxLayout(settings_dialog)
        self.verticalLayout.setContentsMargins(9, -1, -1, -1)
        self.verticalLayout_2 = QVBoxLayout()
        self.formLayout = QFormLayout()
        self.formLayout.setHorizontalSpacing(30)
        self.formLayout.setVerticalSpacing(6)
        self.label = QLabel(settings_dialog)
        self.label.setText("Stream Deck:")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label)

        self.label_streamdeck = QLabel(settings_dialog)
        self.label_streamdeck.setText("")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.label_streamdeck)

        self.label_brightness = QLabel(settings_dialog)
        self.label_brightness.setText("Brightness:")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.label_brightness)

        self.brightness = QSlider(settings_dialog)
        self.brightness.setOrientation(Qt.Horizontal)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.brightness)

        self.label_dim = QLabel(settings_dialog)
        self.label_dim.setText("Auto dim after:")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_dim)

        self.dim = QComboBox(settings_dialog)
        self.dim.setCurrentText("")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.dim)

        self.label_brightness_dimmed = QLabel(settings_dialog)
        self.label_brightness_dimmed.setText("Dim to %:")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.label_brightness_dimmed)

        self.brightness_dimmed = QSlider(settings_dialog)
        self.brightness_dimmed.setOrientation(Qt.Horizontal)

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.brightness_dimmed)

        self.verticalLayout_2.addLayout(self.formLayout)

        self.verticalLayout.addLayout(self.verticalLayout_2)

        self.buttonBox = QDialogButtonBox(settings_dialog)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.verticalLayout.addWidget(self.buttonBox)

        self.buttonBox.accepted.connect(settings_dialog.accept)
        self.buttonBox.rejected.connect(settings_dialog.reject)
