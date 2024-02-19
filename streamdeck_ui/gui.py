"""Defines the QT powered interface for configuring Stream Decks"""
import os
import shlex
import signal
import sys
import time
from functools import partial
from subprocess import Popen  # nosec - Need to allow users to specify arbitrary commands
from typing import Dict, Optional

import pkg_resources
from PySide6 import QtWidgets
from PySide6.QtCore import QMimeData, QSignalBlocker, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QDrag, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMainWindow, QMenu, QMessageBox, QSizePolicy, \
    QSystemTrayIcon

from api import StreamDeckServer
from homeassistant import HomeAssistant
from ui.ui_hass_settings import UiHassSettings
from ui.ui_main import UiMainWindow
from ui.ui_settings import UiSettingsDialog

pynput_supported: bool = True
try:
    from pynput import keyboard
    from pynput.keyboard import Controller, Key
except ImportError as pynput_error:
    pynput_supported = False
    print("---------------")
    print("*** Warning ***")
    print("---------------")
    print("Virtual keyboard functionality has been disabled.")
    print("You can still run Stream Deck UI, however you will not be able to emulate key presses or text typing.")
    print("The most likely reason you are seeing this message is because you don't have an X server running")
    print("and your operating system uses Wayland.")
    print("")
    print(f"For troubleshooting purposes, the actual error is: \n{pynput_error}")

BUTTON_STYLE = """
    QToolButton {
    margin: 2px;
    border: 2px solid #444444;
    border-radius: 8px;
    background-color: #000000;
    border-style: outset;}
    QToolButton:checked {
    margin: 2px;
    border: 2px solid #cccccc;
    border-radius: 8px;
    background-color: #000000;
    border-style: outset;}
"""

BUTTON_DRAG_STYLE = """
    QToolButton {
    margin: 2px;
    border: 2px solid #999999;
    border-radius: 8px;
    background-color: #000000;
    border-style: outset;}
"""

selected_button: Optional[QtWidgets.QToolButton] = None
"A reference to the currently selected button"

text_update_timer: Optional[QTimer] = None
"Timer used to delay updates to the button text"

dimmer_options = {"Never": 0, "10 Seconds": 10, "1 Minute": 60, "5 Minutes": 300, "10 Minutes": 600, "15 Minutes": 900,
                  "30 Minutes": 1800, "1 Hour": 3600, "5 Hours": 7200, "10 Hours": 36000}
last_image_dir = ""


class DraggableButton(QtWidgets.QToolButton):
    """A QToolButton that supports drag and drop and swaps the button properties on drop"""

    def __init__(self, parent, ui, api: StreamDeckServer):
        super(DraggableButton, self).__init__(parent)

        self.setAcceptDrops(True)
        self.ui = ui
        self.api = api

    def mouseMoveEvent(self, e):  # noqa: N802 - Part of QT signature.
        if e.buttons() != Qt.LeftButton:
            return

        self.api.reset_dimmer(self.ui.get_deck_id())

        mime_data = QMimeData()
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.MoveAction)

    def dropEvent(self, e):  # noqa: N802 - Part of QT signature.
        global selected_button

        self.setStyleSheet(BUTTON_STYLE)
        serial_number = self.ui.get_deck_id()
        page = self.ui.get_page()

        if e.source():
            # Ignore drag and drop on yourself
            if e.source().index == self.index:
                return

            self.api.swap_buttons(serial_number, page, e.source().index, self.index)
            # In the case that we've dragged the currently selected button, we have to
            # check the target button instead so it appears that it followed the drag/drop
            if e.source().isChecked():
                e.source().setChecked(False)
                self.setChecked(True)
                selected_button = self
        else:
            # Handle drag and drop from outside the application
            if e.mimeData().hasUrls:
                file_name = e.mimeData().urls()[0].toLocalFile()
                self.api.set_button_icon(serial_number, page, self.index, file_name)

        if e.source():
            icon = self.api.get_button_icon_pixmap(serial_number, page, e.source().index)
            if icon:
                e.source().setIcon(icon)

        icon = self.api.get_button_icon_pixmap(serial_number, page, self.index)
        if icon:
            self.setIcon(icon)

    def dragEnterEvent(self, e):  # noqa: N802 - Part of QT signature.
        if type(self) is DraggableButton:
            e.setAccepted(True)
            self.setStyleSheet(BUTTON_DRAG_STYLE)
        else:
            e.setAccepted(False)

    def dragLeaveEvent(self, e):  # noqa: N802 - Part of QT signature.
        self.setStyleSheet(BUTTON_STYLE)


class MainWindow(QMainWindow):
    """Represents the main streamdeck-ui configuration Window. A QMainWindow
    object provides a lot of standard main window features out the box.

    The QtCreator UI designer allows you to create a UI quickly. It compiles
    into a class called Ui_MainWindow() and everything comes together by
    calling the setupUi() method and passing a reference to the QMainWindow.

    :param QMainWindow: The parent QMainWindow object
    :type QMainWindow: [type]
    """

    ui: UiMainWindow
    hass_connection_changed = Signal(bool)
    "A reference to all the UI objects for the main window"

    def __init__(self, api: StreamDeckServer, hass: HomeAssistant):
        super(MainWindow, self).__init__()
        self.api = api
        self.ui = UiMainWindow(self, hass)
        self.window_shown: bool = True
        self.hass_connection_changed.connect(self.ui.enable_hass_configuration)

    def closeEvent(self, event) -> None:  # noqa: N802 - Part of QT signature.
        self.window_shown = False
        self.hide()
        event.ignore()

    def systray_clicked(self, status=None) -> None:
        if status is QtWidgets.QSystemTrayIcon.ActivationReason.Context:
            return
        if self.window_shown:
            self.hide()
            self.window_shown = False
            return

        self.bring_to_top()

    def bring_to_top(self):
        self.show()
        self.activateWindow()
        self.raise_()
        self.window_shown = True

    def about_dialog(self):
        title = "About StreamDeck UI"
        description = "A Linux compatible UI for the Elgato Stream Deck."
        app = QApplication.instance()
        body = [description, "Version {}\n".format(app.applicationVersion())]
        dependencies = ("streamdeck", "pyside6", "pillow", "pynput")
        for dep in dependencies:
            try:
                dist = pkg_resources.get_distribution(dep)
                body.append("{} {}".format(dep, dist.version))
            except pkg_resources.DistributionNotFound:
                pass
        QtWidgets.QMessageBox.about(self, title, "\n".join(body))

    def redraw_buttons(self):
        redraw_buttons(self.ui, self.api)

    def is_pynput_supported(self):
        return pynput_supported


class StreamDeckUi:

    def __init__(self, api: StreamDeckServer):
        self.api = api

    def handle_keypress(self, ui, deck_id: str, key: int, state: bool) -> None:
        # TODO: Handle both key down and key up events in future.
        if state:
            if self.api.reset_dimmer(deck_id):
                return

            if pynput_supported:
                kb = Controller()
            page = self.api.get_page(deck_id)

            command = self.api.get_button_command(deck_id, page, key)
            if command:
                try:
                    Popen(shlex.split(command))
                except Exception as error:
                    print(f"The command '{command}' failed: {error}")

            if pynput_supported:
                keys = self.api.get_button_keys(deck_id, page, key)
                if keys:
                    keys = keys.strip().replace(" ", "")
                    for section in keys.split(","):
                        # Since + and , are used to delimit our section and keys to press,
                        # they need to be substituted with keywords.
                        section_keys = [_replace_special_keys(key_name) for key_name in section.split("+")]

                        # Translate string to enum, or just the string itself if not found
                        section_keys = [getattr(Key, key_name.lower(), key_name) for key_name in section_keys]

                        for key_name in section_keys:
                            if isinstance(key_name, str) and key_name.startswith("delay"):
                                sleep_time_arg = key_name.split("delay", 1)[1]
                                if sleep_time_arg:
                                    try:
                                        sleep_time = float(sleep_time_arg)
                                    except Exception:
                                        print(f"Could not convert sleep time to float '{sleep_time_arg}'")
                                        sleep_time = 0
                                else:
                                    # default if not specified
                                    sleep_time = 0.5

                                if sleep_time:
                                    try:
                                        time.sleep(sleep_time)
                                    except Exception:
                                        print(f"Could not sleep with provided sleep time '{sleep_time}'")
                            else:
                                try:
                                    if isinstance(key_name, str) and key_name.lower().startswith("0x"):
                                        kb.press(keyboard.KeyCode(int(key_name, 16)))
                                    else:
                                        kb.press(key_name)

                                except Exception:
                                    print(f"Could not press key '{key_name}'")

                        for key_name in section_keys:
                            if not (isinstance(key_name, str) and key_name.startswith("delay")):
                                try:
                                    if isinstance(key_name, str) and key_name.lower().startswith("0x"):
                                        kb.release(keyboard.KeyCode(int(key_name, 16)))
                                    else:
                                        kb.release(key_name)
                                except Exception:
                                    print(f"Could not release key '{key_name}'")

            if pynput_supported:
                write = self.api.get_button_write(deck_id, page, key)
                if write:
                    try:
                        kb.type(write)
                    except Exception as error:
                        print(f"Could not complete the write command: {error}")

            brightness_change = self.api.get_button_change_brightness(deck_id, page, key)
            if brightness_change:
                try:
                    self.api.change_brightness(deck_id, brightness_change)
                except Exception as error:
                    print(f"Could not change brightness: {error}")

            switch_page = self.api.get_button_switch_page(deck_id, page, key)
            if switch_page:
                self.api.set_page(deck_id, switch_page - 1)
                if ui.get_deck_id() == deck_id:
                    ui.pages.setCurrentIndex(switch_page - 1)

            hass_entity = self.api.get_button_hass_entity(deck_id, page, key)
            hass_service = self.api.get_button_hass_service(deck_id, page, key)
            if hass_entity and hass_service:
                self.api.hass.call_service(hass_entity, hass_service)

    def update_button_text(self, ui, text: str) -> None:
        if selected_button:
            deck_id = ui.get_deck_id()
            if deck_id:
                # There may be no decks attached
                self.api.set_button_text(deck_id, ui.get_page(), selected_button.index,
                                         text)  # type: ignore # Index property added
                icon = self.api.get_button_icon_pixmap(deck_id, ui.get_page(),
                                                       selected_button.index)  # type: ignore # Index property added
                if icon:
                    selected_button.setIcon(icon)

    def update_button_command(self, ui, command: str) -> None:
        if selected_button:
            deck_id = ui.get_deck_id()
            self.api.set_button_command(deck_id, ui.get_page(), selected_button.index,
                                        command)  # type: ignore # Index property added

    def update_button_hass_domain(self, ui, hass_domain: str) -> None:
        if selected_button:
            deck_id = ui.get_deck_id()
            self.api.set_button_hass_domain(deck_id, ui.get_page(), selected_button.index, hass_domain)
            redraw_buttons(ui, self.api)
            ui.load_hass_entities()
            ui.load_hass_services()

    def update_button_hass_entity(self, ui, hass_entity: str) -> None:
        if selected_button:
            deck_id = ui.get_deck_id()
            self.api.set_button_hass_entity(deck_id, ui.get_page(), selected_button.index, hass_entity)
            redraw_buttons(ui, self.api)

    def update_button_hass_service(self, ui, hass_service: str) -> None:
        if selected_button:
            deck_id = ui.get_deck_id()
            self.api.set_button_hass_service(deck_id, ui.get_page(), selected_button.index, hass_service)
            redraw_buttons(ui, self.api)

    def update_button_write(self, ui) -> None:
        if selected_button:
            deck_id = ui.get_deck_id()
            self.api.set_button_write(deck_id, ui.get_page(), selected_button.index,
                                      ui.write.toPlainText())  # type: ignore # Index property added

    def update_change_brightness(self, ui, amount: int) -> None:
        if selected_button:
            deck_id = ui.get_deck_id()
            self.api.set_button_change_brightness(deck_id, ui.get_page(), selected_button.index,
                                                  amount)  # type: ignore # Index property added

    def update_switch_page(self, ui, page: int) -> None:
        if selected_button:
            deck_id = ui.get_deck_id()
            self.api.set_button_switch_page(deck_id, ui.get_page(), selected_button.index,
                                            page)  # type: ignore # Index property added

    def change_page(self, ui, page: int) -> None:
        global selected_button

        """Change the Stream Deck to the desired page and update
        the on-screen buttons.
    
        :param ui: Reference to the ui
        :type ui: _type_
        :param page: The page number to switch to
        :type page: int
        """
        if selected_button:
            selected_button.setChecked(False)
            selected_button = None

        deck_id = ui.get_deck_id()
        if deck_id:
            self.api.set_page(deck_id, page)
            redraw_buttons(ui, self.api)
            self.api.reset_dimmer(deck_id)

        ui.reset_button_configuration()

    def change_hass_domain(self, ui, domain_index=None):
        ui.load_hass_entities()
        ui.load_hass_services()

    def select_image(self, window) -> None:
        global last_image_dir
        deck_id = window.ui.get_deck_id()
        image_file = self.api.get_button_icon(deck_id, window.ui.get_page(),
                                              selected_button.index)  # type: ignore # Index property added
        if not image_file:
            if not last_image_dir:
                image_file = os.path.expanduser("~")
            else:
                image_file = last_image_dir
        file_name = \
            QFileDialog.getOpenFileName(window, "Open Image", image_file,
                                        "Image Files (*.png *.jpg *.bmp *.svg *.gif)")[0]
        if file_name:
            last_image_dir = os.path.dirname(file_name)
            deck_id = window.ui.get_deck_id()
            self.api.set_button_icon(deck_id, window.ui.get_page(), selected_button.index,
                                     file_name)  # type: ignore # Index property added
            window.redraw_buttons()

    def align_text_vertical(self, window) -> None:
        serial_number = window.ui.get_deck_id()
        position = self.api.get_text_vertical_align(serial_number, window.ui.get_page(),
                                                    selected_button.index)  # type: ignore # Index property added
        if position == "bottom" or position == "":
            position = "middle-bottom"
        elif position == "middle-bottom":
            position = "middle"
        elif position == "middle":
            position = "middle-top"
        elif position == "middle-top":
            position = "top"
        else:
            position = ""

        self.api.set_text_vertical_align(serial_number, window.ui.get_page(), selected_button.index,
                                         position)  # type: ignore # Index property added
        window.redraw_buttons()

    def remove_image(self, window) -> None:
        deck_id = window.ui.get_deck_id()
        image = self.api.get_button_icon(deck_id, window.ui.get_page(),
                                         selected_button.index)  # type: ignore # Index property added
        if image:
            confirm = QMessageBox(window)
            confirm.setWindowTitle("Remove image")
            confirm.setText("Are you sure you want to remove the image for this button?")
            confirm.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            confirm.setIcon(QMessageBox.Icon.Question)
            button = confirm.exec()
            if button == QMessageBox.StandardButton.Yes:
                self.api.set_button_icon(deck_id, window.ui.get_page(), selected_button.index,
                                         "")  # type: ignore # Index property added
                window.redraw_buttons()

    def set_brightness(self, ui, value: int) -> None:
        deck_id = ui.get_deck_id()
        self.api.set_brightness(deck_id, value)

    def set_brightness_dimmed(self, ui, value: int) -> None:
        deck_id = ui.get_deck_id()
        self.api.set_brightness_dimmed(deck_id, value)
        self.api.reset_dimmer(deck_id)

    def set_hass_url(self, value: str) -> None:
        self.api.set_hass_url(value)

    def set_hass_token(self, value: str) -> None:
        self.api.set_hass_token(value)

    def set_hass_port(self, value: str) -> None:
        self.api.set_hass_port(value)

    def set_hass_ssl(self, value: bool) -> None:
        self.api.set_hass_ssl(value)

    def button_clicked(self, ui, clicked_button, buttons) -> None:
        self.api.button_clicked = True

        global selected_button
        selected_button = clicked_button
        for button in buttons:
            if button == clicked_button:
                continue

            button.setChecked(False)

        deck_id = ui.get_deck_id()
        button_id = selected_button.index  # type: ignore # Index property added
        if selected_button.isChecked():  # type: ignore # False positive mypy
            ui.enable_button_configuration(True)
            ui.label.setText(self.api.get_button_text(deck_id, ui.get_page(), button_id))
            ui.command.setText(self.api.get_button_command(deck_id, ui.get_page(), button_id))

            hass_domain_text = self.api.get_button_hass_domain(deck_id, ui.get_page(), button_id)
            for i in range(ui.hass_domain.count()):
                if hass_domain_text == ui.hass_domain.itemText(i):
                    ui.hass_domain.setCurrentIndex(i)
                    break

            hass_entity_text = self.api.get_button_hass_entity(deck_id, ui.get_page(), button_id)
            for i in range(ui.hass_entity.count()):
                if hass_entity_text == ui.hass_entity.itemText(i):
                    ui.hass_entity.setCurrentIndex(i)
                    break

            hass_service_text = self.api.get_button_hass_service(deck_id, ui.get_page(), button_id)
            for i in range(ui.hass_service.count()):
                if hass_service_text == ui.hass_service.itemText(i):
                    ui.hass_service.setCurrentIndex(i)
                    break

            ui.keys.setCurrentText(self.api.get_button_keys(deck_id, ui.get_page(), button_id))
            ui.write.setPlainText(self.api.get_button_write(deck_id, ui.get_page(), button_id))
            ui.change_brightness.setValue(self.api.get_button_change_brightness(deck_id, ui.get_page(), button_id))
            ui.switch_page.setValue(self.api.get_button_switch_page(deck_id, ui.get_page(), button_id))
            self.api.reset_dimmer(deck_id)
        else:
            selected_button = None
            ui.reset_button_configuration()

        self.api.button_clicked = False

    def build_buttons(self, ui: UiMainWindow, tab) -> None:
        global selected_button

        if hasattr(tab, "deck_buttons"):
            buttons = tab.findChildren(QtWidgets.QToolButton)
            for button in buttons:
                button.hide()
                # Mark them as hidden. They will be GC'd later
                button.deleteLater()

            tab.deck_buttons.hide()
            tab.deck_buttons.deleteLater()
            # Remove the inner page
            del tab.children()[0]
            # Remove the property
            del tab.deck_buttons

        selected_button = None
        # When rebuilding any selection is cleared

        deck_id = ui.get_deck_id()

        if not deck_id:
            return
        deck = self.api.get_deck(deck_id)

        # Create a new base_widget with tab as it's parent
        # This is effectively a "blank tab"
        base_widget = QtWidgets.QWidget(tab)

        # Add an inner page (QtQidget) to the page
        tab.children()[0].addWidget(base_widget)

        # Set a property - this allows us to check later
        # if we've already created the buttons
        tab.deck_buttons = base_widget

        row_layout = QtWidgets.QVBoxLayout(base_widget)
        index = 0
        buttons = []
        for _row in range(deck["layout"][0]):  # type: ignore
            column_layout = QtWidgets.QHBoxLayout()
            row_layout.addLayout(column_layout)

            for _column in range(deck["layout"][1]):  # type: ignore
                button = DraggableButton(base_widget, ui, self.api)
                button.setCheckable(True)
                button.index = index
                button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setIconSize(QSize(80, 80))
                button.setStyleSheet(BUTTON_STYLE)
                buttons.append(button)
                column_layout.addWidget(button)
                index += 1

            column_layout.addStretch(1)
        row_layout.addStretch(1)

        # Note that the button click event captures the ui variable, the current button
        #  and all the other buttons
        for button in buttons:
            button.clicked.connect(lambda button=button, buttons=buttons: self.button_clicked(ui, button, buttons))

    def export_config(self, window) -> None:
        file_name = \
            QFileDialog.getSaveFileName(window, "Export Config", os.path.expanduser("~/streamdeck_ui_hass_export.json"),
                                        "JSON (*.json)")[0]
        if not file_name:
            return

        self.api.export_config(file_name)

    def import_config(self, window) -> None:
        file_name = \
            QFileDialog.getOpenFileName(window, "Import Config", os.path.expanduser("~"), "Config Files (*.json)")[
                0]
        if not file_name:
            return

        self.api.import_config(file_name)
        window.redraw_buttons()

    def build_device(self, ui, _device_index=None) -> None:
        """This method builds the device configuration user interface.
        It is called if you switch to a different Stream Deck,
        a Stream Deck is added or when the last one is removed.
        It must deal with the case where there is no Stream Deck as
        a result.

        :param ui: A reference to the ui
        :type ui: _type_
        :param _device_index: Not used, defaults to None
        :type _device_index: _type_, optional
        """
        style = ""
        if ui.device_list.count() > 0:
            style = "background-color: black"

        for page_id in range(ui.pages.count()):
            page = ui.pages.widget(page_id)
            page.setStyleSheet(style)
            self.build_buttons(ui, page)

        if ui.device_list.count() > 0:
            ui.settings_button.setEnabled(True)
            # Set the active page for this device
            ui.pages.setCurrentIndex(self.api.get_page(ui.get_deck_id()))

            # Draw the buttons for the active page
            redraw_buttons(ui, self.api)
        else:
            ui.settings_button.setEnabled(False)
            ui.reset_button_configuration()

    def change_brightness(self, deck_id: str, brightness: int):
        """Changes the brightness of the given streamdeck, but does not save
        the state."""
        self.api.decks[deck_id].set_brightness(brightness)

    def show_hass_settings(self, window: MainWindow) -> None:
        """Shows the settings dialog and allows the user the change deck specific
        settings. Settings are not saved until OK is clicked."""
        hass_settings = SettingsDialog(window, UiHassSettings)

        old_url = self.api.get_hass_url()
        hass_settings.ui.url.setText(old_url)

        old_token = self.api.get_hass_token()
        hass_settings.ui.token.setText(old_token)

        old_port = self.api.get_hass_port()
        hass_settings.ui.port.setText(old_port)

        old_ssl = self.api.get_hass_ssl()
        hass_settings.ui.ssl.setChecked(old_ssl)

        if hass_settings.exec():
            url = hass_settings.ui.url.text()
            self.api.hass.set_url(url)
            self.set_hass_url(url)

            token = hass_settings.ui.token.text()
            self.api.hass.set_token(token)
            self.set_hass_token(token)

            port = hass_settings.ui.port.text()
            self.api.hass.set_port(port)
            self.set_hass_port(port)

            ssl = hass_settings.ui.ssl.isChecked()
            self.api.hass.set_ssl(ssl)
            self.set_hass_ssl(ssl)

            if old_url != url or old_token != token or old_port != port or old_ssl != ssl:
                self.api.hass.disconnect()
                self.api.hass.connect()

    def show_settings(self, window: MainWindow) -> None:
        """Shows the settings dialog and allows the user the change deck specific
        settings. Settings are not saved until OK is clicked."""
        ui = window.ui
        deck_id = ui.get_deck_id()
        settings = SettingsDialog(window, UiSettingsDialog)
        self.api.stop_dimmer(deck_id)

        for label, value in dimmer_options.items():
            settings.ui.dim.addItem(f"{label}", userData=value)

        existing_timeout = self.api.get_display_timeout(deck_id)
        existing_index = next((i for i, (k, v) in enumerate(dimmer_options.items()) if v == existing_timeout), None)

        if existing_index is None:
            settings.ui.dim.addItem(f"Custom: {existing_timeout}s", userData=existing_timeout)
            existing_index = settings.ui.dim.count() - 1
            settings.ui.dim.setCurrentIndex(existing_index)
        else:
            settings.ui.dim.setCurrentIndex(existing_index)

        existing_brightness_dimmed = self.api.get_brightness_dimmed(deck_id)
        settings.ui.brightness_dimmed.setValue(existing_brightness_dimmed)

        settings.ui.label_streamdeck.setText(deck_id)
        settings.ui.brightness.setValue(self.api.get_brightness(deck_id))
        settings.ui.brightness.valueChanged.connect(partial(self.change_brightness, deck_id))
        settings.ui.dim.currentIndexChanged.connect(partial(disable_dim_settings, settings))
        if settings.exec():
            # Commit changes
            if existing_index != settings.ui.dim.currentIndex():
                # dimmers[deck_id].timeout = settings.ui.dim.currentData()
                self.api.set_display_timeout(deck_id, settings.ui.dim.currentData())
            self.set_brightness(window.ui, settings.ui.brightness.value())
            self.set_brightness_dimmed(window.ui, settings.ui.brightness_dimmed.value())
        else:
            # User cancelled, reset to original brightness
            self.change_brightness(deck_id, self.api.get_brightness(deck_id))

        self.api.reset_dimmer(deck_id)

    def toggle_dim_all(self) -> None:
        self.api.toggle_dimmers()

    def queue_update_button_text(self, ui, text: str) -> None:
        """Instead of directly updating the text (label) associated with
        the button, add a small delay. If this is called before the
        timer fires, delay it again. Effectively this creates an update
        queue. It makes the textbox more response, as rendering the button
        and saving to the API each time can feel somewhat slow.
    
        :param ui: Reference to the ui
        :type ui: _type_
        :param text: The new text value
        :type text: str
        """
        global text_update_timer

        if text_update_timer:
            text_update_timer.stop()

        text_update_timer = QTimer()
        text_update_timer.setSingleShot(True)
        text_update_timer.timeout.connect(partial(self.update_button_text, ui, text))  # type: ignore [attr-defined]
        text_update_timer.start(500)

    def streamdeck_attached(self, ui, deck: Dict):
        serial_number = deck["serial_number"]
        blocker = QSignalBlocker(ui.device_list)
        try:
            ui.device_list.addItem(f"{deck['type']} - {serial_number}", userData=serial_number)
        finally:
            blocker.unblock()
        self.build_device(ui)

    def streamdeck_detached(self, ui, serial_number):
        index = ui.device_list.findData(serial_number)
        if index != -1:
            # Should not be (how can you remove a device that was never attached?)
            # Check anyways
            blocker = QSignalBlocker(ui.device_list)
            try:
                ui.device_list.removeItem(index)
            finally:
                blocker.unblock()
            self.build_device(ui)

    def create_main_window(self, logo: QIcon, app: QApplication, api: StreamDeckServer,
                           hass: HomeAssistant) -> MainWindow:
        """Creates the main application window and configures slots and signals
    
        :param logo: The icon displayed in the main application window
        :type logo: QIcon
        :param app: The QApplication that started it all
        :type app: QApplication
        :return: Returns the MainWindow instance
        :rtype: MainWindow
        """
        main_window = MainWindow(api, hass)
        ui = main_window.ui
        ui.label.textChanged.connect(partial(self.queue_update_button_text, ui))
        ui.command.textChanged.connect(partial(self.update_button_command, ui))
        ui.hass_domain.currentTextChanged.connect(partial(self.update_button_hass_domain, ui))
        ui.hass_entity.currentTextChanged.connect(partial(self.update_button_hass_entity, ui))
        ui.hass_service.currentTextChanged.connect(partial(self.update_button_hass_service, ui))
        ui.keys.currentTextChanged.connect(partial(update_button_keys, ui))
        ui.write.textChanged.connect(partial(self.update_button_write, ui))
        ui.change_brightness.valueChanged.connect(partial(self.update_change_brightness, ui))
        ui.switch_page.valueChanged.connect(partial(self.update_switch_page, ui))
        ui.image_button.clicked.connect(partial(self.select_image, main_window))
        ui.label_button.clicked.connect(partial(self.align_text_vertical, main_window))
        ui.remove_image_button.clicked.connect(partial(self.remove_image, main_window))
        ui.settings_button.clicked.connect(partial(self.show_settings, main_window))
        ui.action_export.triggered.connect(partial(self.export_config, main_window))
        ui.action_import.triggered.connect(partial(self.import_config, main_window))
        ui.action_home_assistant_settings.triggered.connect(partial(self.show_hass_settings, main_window))
        ui.action_exit.triggered.connect(app.exit)
        ui.action_about.triggered.connect(main_window.about_dialog)
        ui.action_documentation.triggered.connect(browse_documentation)
        ui.action_github.triggered.connect(browse_github)
        ui.settings_button.setEnabled(False)
        ui.enable_button_configuration(False)
        return main_window

    def create_tray(self, logo: QIcon, app: QApplication, main_window: MainWindow) -> QSystemTrayIcon:
        """Creates a system tray with the provided icon and parent. The main
        window passed will be activated when clicked.
    
        :param logo: The icon to show in the system tray
        :type logo: QIcon
        :param app: The parent object the tray is bound to
        :type app: QApplication
        :param main_window: The window what will be activated by the tray
        :type main_window: QMainWindow
        :return: Returns the QSystemTrayIcon instance
        :rtype: QSystemTrayIcon
        """
        tray = QSystemTrayIcon(logo, app)
        tray.activated.connect(main_window.systray_clicked)  # type: ignore [attr-defined]

        menu = QMenu()
        action_dim = QAction("Dim display (toggle)", main_window)
        action_dim.triggered.connect(self.toggle_dim_all)  # type: ignore [attr-defined]
        action_configure = QAction("Configure...", main_window)
        action_configure.triggered.connect(main_window.bring_to_top)  # type: ignore [attr-defined]
        menu.addAction(action_dim)
        menu.addAction(action_configure)
        menu.addSeparator()
        action_exit = QAction("Exit", main_window)
        action_exit.triggered.connect(app.exit)  # type: ignore [attr-defined]
        menu.addAction(action_exit)
        tray.setContextMenu(menu)

        return tray

    def sigterm_handler(self, api, app, signal_value, frame):
        api.stop()
        app.quit()
        if signal_value == signal.SIGTERM:
            # Indicate to systemd that it was a clean termination
            print("Exiting normally")
            sys.exit()
        else:
            # Terminations for other reasons are treated as an error condition
            sys.exit(1)


def redraw_buttons(ui: UiMainWindow, api: StreamDeckServer) -> None:
    deck_id = ui.get_deck_id()
    current_tab = ui.pages.currentWidget()
    buttons = current_tab.findChildren(QtWidgets.QToolButton)
    for button in buttons:
        if not button.isHidden():
            # When rebuilding the buttons, we hide the old ones
            # and mark for deletion. They still hang around so
            # ignore them here
            icon = api.get_button_icon_pixmap(deck_id, ui.get_page(), button.index)
            if icon:
                button.setIcon(icon)


def _replace_special_keys(key):
    """Replaces special keywords the user can use with their character equivalent."""
    if key.lower() == "plus":
        return "+"
    if key.lower() == "comma":
        return ","
    if key.lower().startswith("delay"):
        return key.lower()
    return key


def update_button_keys(ui, keys: str) -> None:
    if selected_button:
        deck_id = ui.get_deck_id()
        api.set_button_keys(deck_id, ui.get_page(), selected_button.index, keys)  # type: ignore # Index property added


def browse_documentation():
    url = QUrl("https://timothycrosley.github.io/streamdeck-ui/")
    QDesktopServices.openUrl(url)


def browse_github():
    url = QUrl("https://github.com/timothycrosley/streamdeck-ui")
    QDesktopServices.openUrl(url)


class SettingsDialog(QDialog):

    def __init__(self, parent, dialog):
        super().__init__(parent)
        self.ui: dialog = dialog(self)
        self.show()


def disable_dim_settings(settings: SettingsDialog, _index: int) -> None:
    disable = dimmer_options.get(settings.ui.dim.currentText()) == 0
    settings.ui.brightness_dimmed.setDisabled(disable)
    settings.ui.label_brightness_dimmed.setDisabled(disable)


def streamdeck_cpu_changed(ui, serial_number: str, cpu: int):
    if cpu > 100:
        cpu = 100
    if ui.get_deck_id() == serial_number:
        ui.cpu_usage.setValue(cpu)
        ui.cpu_usage.setToolTip(f"Rendering CPU usage: {cpu}%")
        ui.cpu_usage.update()
