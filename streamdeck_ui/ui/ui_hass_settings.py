from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QCheckBox, QDialogButtonBox, \
    QVBoxLayout


class UiHassSettings(object):

    def __init__(self, settings_dialog):
        icon = QIcon()
        icon.addFile(u"icons/gear.png", QSize(), QIcon.Normal, QIcon.Off)

        settings_dialog.setWindowModality(Qt.ApplicationModal)
        settings_dialog.resize(452, 156)
        settings_dialog.setWindowIcon(icon)
        settings_dialog.setWindowTitle("Home Assistant Settings")

        label_url = QLabel(settings_dialog)
        label_url.setText("URL:")

        self.url = QLineEdit(settings_dialog)

        label_token = QLabel(settings_dialog)
        label_token.setText("Token:")

        self.token = QLineEdit(settings_dialog)

        label_port = QLabel(settings_dialog)
        label_port.setText("Port:")

        self.port = QLineEdit(settings_dialog)
        self.port.setMaximumSize(100, 30)

        label_ssl = QLabel(settings_dialog)
        label_ssl.setText("SSL:")

        self.ssl = QCheckBox(settings_dialog)
        self.ssl.setChecked(True)

        port_ssl_layout = QHBoxLayout()
        port_ssl_layout.addWidget(self.port)
        port_ssl_layout.addWidget(label_ssl)
        port_ssl_layout.addWidget(self.ssl)
        port_ssl_layout.addStretch()

        form_layout = QFormLayout()
        form_layout.setWidget(0, QFormLayout.LabelRole, label_url)
        form_layout.setWidget(0, QFormLayout.FieldRole, self.url)
        form_layout.setWidget(1, QFormLayout.LabelRole, label_token)
        form_layout.setWidget(1, QFormLayout.FieldRole, self.token)
        form_layout.setWidget(2, QFormLayout.LabelRole, label_port)
        form_layout.setLayout(2, QFormLayout.FieldRole, port_ssl_layout)

        QWidget.setTabOrder(self.url, self.token)
        QWidget.setTabOrder(self.token, self.port)
        QWidget.setTabOrder(self.port, self.ssl)
        QWidget.setTabOrder(self.ssl, self.url)

        button_box = QDialogButtonBox(settings_dialog)
        button_box.setOrientation(Qt.Horizontal)
        button_box.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        button_box.setCenterButtons(False)
        button_box.accepted.connect(settings_dialog.accept)
        button_box.rejected.connect(settings_dialog.reject)

        main_layout = QVBoxLayout(settings_dialog)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(button_box)
