import os

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QProgressBar, QTabWidget, \
    QGroupBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QPlainTextEdit, \
    QMenuBar, QMenu, QStatusBar, QGridLayout
from streamdeck_ui_hass.homeassistant import HomeAssistant

from streamdeck_ui_hass.config import PROJECT_PATH

WIDTH = 1200
HEIGHT = 500
DEVICE_LIST_WIDTH = 400

PAGE_COUNT = 10

KEYS = [
    "", "F11", "alt+F4", "ctrl+w", "cmd+left", "alt+plus", "alt+delay+F3", "backspace", "right", "page_up",
    "media_volume_up", "media_volume_down", "media_volume_mute", "media_previous", "media_next", "media_play_pause"
]


class UiMainWindow(object):

    def __init__(self, main_window, hass: HomeAssistant):
        self.main_window = main_window
        self._hass: HomeAssistant = hass

        self.main_window.resize(WIDTH, HEIGHT)
        self.main_window.setWindowTitle("Stream Deck UI")

        main_widget = QWidget(main_window)

        self.device_list: QComboBox = QComboBox(main_widget)

        gear_icon = QIcon()
        gear_icon.addFile(os.path.join(PROJECT_PATH, "icons/gear.png"), QSize(), QIcon.Normal, QIcon.Off)

        self.settings_button: QPushButton = QPushButton(main_widget)
        self.settings_button.setMaximumSize(QSize(25, 25))
        self.settings_button.setIcon(gear_icon)

        self.cpu_usage: QProgressBar = QProgressBar(main_widget)
        self.cpu_usage.setMaximumSize(QSize(25, 25))
        self.cpu_usage.setMaximum(130)
        self.cpu_usage.setValue(0)
        self.cpu_usage.setOrientation(Qt.Vertical)
        self.cpu_usage.setFormat("")

        device_layout = QHBoxLayout()
        device_layout.addWidget(self.device_list)
        device_layout.addWidget(self.settings_button)
        device_layout.addWidget(self.cpu_usage)

        self.pages: QTabWidget = QTabWidget(main_widget)

        for i in range(1, PAGE_COUNT + 1):
            self.add_page(i)

        self.pages.setCurrentIndex(0)

        left_vertical_layout = QVBoxLayout()
        left_vertical_layout.addLayout(device_layout)
        left_vertical_layout.addWidget(self.pages)

        self.groupBox: QGroupBox = QGroupBox(main_widget)
        self.groupBox.setTitle("Configure Button")

        self.label_image: QLabel = QLabel(self.groupBox)
        self.label_image.setText("Image:")

        self.image_button: QPushButton = QPushButton(self.groupBox)
        self.image_button.setText("Image...")

        remove_icon = QIcon()
        remove_icon.addFile(os.path.join(PROJECT_PATH, "icons/cross.png"), QSize(), QIcon.Normal, QIcon.Off)

        self.remove_image_button: QPushButton = QPushButton(self.groupBox)
        self.remove_image_button.setToolTip("Remove the image from the button")
        self.remove_image_button.setMaximumSize(QSize(25, 25))
        self.remove_image_button.setIcon(remove_icon)

        image_layout = QHBoxLayout()
        image_layout.setSpacing(6)
        image_layout.addWidget(self.image_button)
        image_layout.addWidget(self.remove_image_button)

        self.label_label: QLabel = QLabel(self.groupBox)
        self.label_label.setText("Label:")

        self.label: QLineEdit = QLineEdit(self.groupBox)

        align_icon = QIcon()
        align_icon.addFile(os.path.join(PROJECT_PATH, "icons/vertical-align.png"), QSize(), QIcon.Normal, QIcon.Off)

        self.label_button = QPushButton(self.groupBox)
        self.label_button.setToolTip("Text vertical alignment")
        self.label_button.setMaximumSize(QSize(25, 25))
        self.label_button.setIcon(align_icon)

        label_layout = QHBoxLayout()
        label_layout.addWidget(self.label)
        label_layout.addWidget(self.label_button)

        self.label_command: QLabel = QLabel(self.groupBox)
        self.label_command.setText("Command:")

        self.command: QLineEdit = QLineEdit(self.groupBox)

        self.label_press_keys: QLabel = QLabel(self.groupBox)
        self.label_press_keys.setText("Press Keys:")

        self.keys: QComboBox = QComboBox(self.groupBox)

        for key in KEYS:
            self.keys.addItem(key)

        self.keys.setEditable(True)

        self.label_switch_page: QLabel = QLabel(self.groupBox)
        self.label_switch_page.setText("Switch Page:")

        self.switch_page: QSpinBox = QSpinBox(self.groupBox)
        self.switch_page.setMinimum(0)
        self.switch_page.setMaximum(10)
        self.switch_page.setValue(0)

        self.label_brightness: QLabel = QLabel(self.groupBox)
        self.label_brightness.setText("Brightness +/-:")

        self.change_brightness: QSpinBox = QSpinBox(self.groupBox)
        self.change_brightness.setMinimum(-99)

        self.label_write_text: QLabel = QLabel(self.groupBox)
        self.label_write_text.setText("Write Text:")

        self.write: QPlainTextEdit = QPlainTextEdit(self.groupBox)

        self.label_hass_domain: QLabel = QLabel(self.groupBox)
        self.label_hass_domain.setText("HASS Domain:")

        self.hass_domain: QComboBox = QComboBox(self.groupBox)
        self.hass_domain.setEditable(False)

        self.label_hass_entity: QLabel = QLabel(self.groupBox)
        self.label_hass_entity.setText("HASS Entity:")

        self.hass_entity: QComboBox = QComboBox(self.groupBox)
        self.hass_entity.setEditable(False)

        self.label_hass_service: QLabel = QLabel(self.groupBox)
        self.label_hass_service.setText("HASS Service:")

        self.hass_service: QComboBox = QComboBox(self.groupBox)
        self.hass_service.setEditable(False)

        self.load_hass_domains()
        self.load_hass_entities()
        self.load_hass_services()

        form_layout = QFormLayout(self.groupBox)
        form_layout.setWidget(0, QFormLayout.LabelRole, self.label_image)
        form_layout.setLayout(0, QFormLayout.FieldRole, image_layout)
        form_layout.setWidget(1, QFormLayout.LabelRole, self.label_label)
        form_layout.setLayout(1, QFormLayout.FieldRole, label_layout)
        form_layout.setWidget(2, QFormLayout.LabelRole, self.label_command)
        form_layout.setWidget(2, QFormLayout.FieldRole, self.command)
        form_layout.setWidget(3, QFormLayout.LabelRole, self.label_press_keys)
        form_layout.setWidget(3, QFormLayout.FieldRole, self.keys)
        form_layout.setWidget(4, QFormLayout.LabelRole, self.label_switch_page)
        form_layout.setWidget(4, QFormLayout.FieldRole, self.switch_page)
        form_layout.setWidget(5, QFormLayout.LabelRole, self.label_brightness)
        form_layout.setWidget(5, QFormLayout.FieldRole, self.change_brightness)
        form_layout.setWidget(6, QFormLayout.LabelRole, self.label_write_text)
        form_layout.setWidget(6, QFormLayout.FieldRole, self.write)
        form_layout.setWidget(7, QFormLayout.LabelRole, self.label_hass_domain)
        form_layout.setWidget(7, QFormLayout.FieldRole, self.hass_domain)
        form_layout.setWidget(8, QFormLayout.LabelRole, self.label_hass_entity)
        form_layout.setWidget(8, QFormLayout.FieldRole, self.hass_entity)
        form_layout.setWidget(9, QFormLayout.LabelRole, self.label_hass_service)
        form_layout.setWidget(9, QFormLayout.FieldRole, self.hass_service)

        main_widget_layout = QHBoxLayout(main_widget)
        main_widget_layout.addLayout(left_vertical_layout)
        main_widget_layout.addWidget(self.groupBox)

        self.action_import: QAction = self.create_action("Import")
        self.action_export: QAction = self.create_action("Export")
        self.action_exit: QAction = self.create_action("Exit")

        self.menu_file: QMenu = QMenu()
        self.menu_file.setTitle("File")
        self.menu_file.addAction(self.action_import)
        self.menu_file.addAction(self.action_export)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_exit)

        self.action_home_assistant_settings: QAction = self.create_action("Home Assistant")

        self.menu_settings: QMenu = QMenu()
        self.menu_settings.setTitle("Settings")
        self.menu_settings.addAction(self.action_home_assistant_settings)

        self.action_documentation: QAction = self.create_action("Documentation")
        self.action_github: QAction = self.create_action("Github")
        self.action_about: QAction = self.create_action("About...")

        self.menu_help: QMenu = QMenu()
        self.menu_help.setTitle("Help")
        self.menu_help.addAction(self.action_documentation)
        self.menu_help.addAction(self.action_github)
        self.menu_help.addSeparator()
        self.menu_help.addAction(self.action_about)

        self.menubar: QMenuBar = QMenuBar(main_window)
        self.menubar.addAction(self.menu_file.menuAction())
        self.menubar.addAction(self.menu_settings.menuAction())
        self.menubar.addAction(self.menu_help.menuAction())

        self.label_statusbar: QLabel = QLabel(main_window)

        self.statusbar: QStatusBar = QStatusBar(main_window)
        self.statusbar.addPermanentWidget(self.label_statusbar, 9999)

        if hass.is_connected():
            self.label_statusbar.setText("Connected to Home Assistant")

        main_window.setCentralWidget(main_widget)
        main_window.setMenuBar(self.menubar)
        main_window.setStatusBar(self.statusbar)

        QWidget.setTabOrder(self.device_list, self.settings_button)
        QWidget.setTabOrder(self.settings_button, self.pages)
        QWidget.setTabOrder(self.pages, self.image_button)
        QWidget.setTabOrder(self.image_button, self.remove_image_button)
        QWidget.setTabOrder(self.remove_image_button, self.label)
        QWidget.setTabOrder(self.label, self.label_button)
        QWidget.setTabOrder(self.label_button, self.command)
        QWidget.setTabOrder(self.command, self.keys)
        QWidget.setTabOrder(self.keys, self.switch_page)
        QWidget.setTabOrder(self.switch_page, self.change_brightness)
        QWidget.setTabOrder(self.change_brightness, self.write)
        QWidget.setTabOrder(self.write, self.hass_domain)
        QWidget.setTabOrder(self.hass_domain, self.hass_entity)
        QWidget.setTabOrder(self.hass_entity, self.hass_service)
        QWidget.setTabOrder(self.hass_service, self.device_list)

    def load_hass_domains(self):
        self.hass_domain.clear()
        self.hass_domain.addItem("")

        domains = sorted(self._hass.get_domains())

        for domain in domains:
            self.hass_domain.addItem(domain)

        self.hass_entity.clear()
        self.hass_entity.setEnabled(False)

        self.hass_service.clear()
        self.hass_service.setEnabled(False)

    def load_hass_entities(self):
        self.hass_entity.setEnabled(True)
        self.hass_entity.clear()
        self.hass_entity.addItem("")

        entities = sorted(self._hass.get_entities(self.hass_domain.currentText()))

        for entity in entities:
            self.hass_entity.addItem(entity)

    def load_hass_services(self):
        self.hass_service.setEnabled(True)
        self.hass_service.clear()
        self.hass_service.addItem("")

        services = self._hass.get_services(self.hass_domain.currentText())

        for service in services:
            self.hass_service.addItem(service)

    def reset_button_configuration(self, hass_connected: bool = False):
        """Clears the configuration for a button and disables editing of them. This is done when
        there is no key selected or if there are no devices connected.
        """
        self.label.clear()
        self.command.clear()
        self.hass_entity.clear()
        self.hass_service.clear()
        self.keys.clearEditText()
        self.write.clear()
        self.change_brightness.setValue(0)
        self.switch_page.setValue(0)
        self.enable_button_configuration(False)

    def enable_button_configuration(self, enabled: bool):
        self.label.setEnabled(enabled)
        self.command.setEnabled(enabled)
        self.hass_domain.setEnabled(enabled)
        self.hass_entity.setEnabled(enabled and bool(self.hass_domain.currentText()))
        self.hass_service.setEnabled(enabled and bool(self.hass_domain.currentText()))
        self.keys.setEnabled(enabled)
        self.write.setEnabled(enabled)
        self.change_brightness.setEnabled(enabled)
        self.switch_page.setEnabled(enabled)
        self.image_button.setEnabled(enabled)
        self.remove_image_button.setEnabled(enabled)
        self.label_button.setEnabled(enabled)

        pynput_supported = self.main_window.is_pynput_supported()

        self.label_press_keys.setVisible(pynput_supported)
        self.keys.setVisible(pynput_supported)
        self.label_write_text.setVisible(pynput_supported)
        self.write.setVisible(pynput_supported)

        self.enable_hass_configuration()

    @Slot(bool)
    def enable_hass_configuration(self, hass_connected: bool = False):
        self.label_hass_domain.setVisible(hass_connected)
        self.hass_domain.setVisible(hass_connected)
        self.label_hass_entity.setVisible(hass_connected)
        self.hass_entity.setVisible(hass_connected)
        self.label_hass_service.setVisible(hass_connected)
        self.hass_service.setVisible(hass_connected)

    def create_action(self, text: str):
        action = QAction(self.main_window)
        action.setText(text)

        return action

    def add_page(self, number: int):
        name = f'{"Page " if number == 1 else ""}{number}'

        page = QWidget(self.main_window)
        QGridLayout(page)
        self.pages.addTab(page, name)

    def get_deck_id(self):
        return self.device_list.itemData(self.device_list.currentIndex())

    def get_page(self):
        return self.pages.currentIndex()
