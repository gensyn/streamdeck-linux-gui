#!usr/bin/python3

import os
import signal
import sys
from functools import partial

import pkg_resources
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from api import StreamDeckServer
from config import STATE_FILE, LOGO
from gui import StreamDeckUi, streamdeck_cpu_changed
from homeassistant import HomeAssistant
from semaphore import Semaphore, SemaphoreAcquireError


def main():
    show_ui = True

    if "-h" in sys.argv or "--help" in sys.argv:
        print(f"Usage: {os.path.basename(sys.argv[0])}")
        print("Flags:")
        print("  -h, --help\tShow this message")
        print("  -n, --no-ui\tRun the program without showing a UI")
        exit(0)
    elif "-n" in sys.argv or "--no-ui" in sys.argv:
        show_ui = False

    try:
        version = pkg_resources.get_distribution("streamdeck-ui-hass").version
    except pkg_resources.DistributionNotFound:
        version = "devel"

    try:
        with Semaphore("/tmp/streamdeck_ui_hass.lock"):  # nosec - this file is only observed with advisory lock
            hass = HomeAssistant()
            api = StreamDeckServer()
            gui = StreamDeckUi(api)
            api.set_hass(hass)
            hass.set_api(api)

            if os.path.isfile(STATE_FILE):
                api.open_config(STATE_FILE)

            # The QApplication object holds the Qt event loop and you need one of these
            # for your application
            app = QApplication(sys.argv)
            app.setApplicationName("Streamdeck UI Hass")
            app.setApplicationVersion(version)
            logo = QIcon(LOGO)
            app.setWindowIcon(logo)
            main_window = gui.create_main_window(logo, app, api, hass)
            ui = main_window.ui
            tray = gui.create_tray(logo, app, main_window)

            hass.set_main_window(main_window)

            api.streamdeck_keys.key_pressed.connect(partial(gui.handle_keypress, ui))

            ui.device_list.currentIndexChanged.connect(partial(gui.build_device, ui))
            ui.pages.currentChanged.connect(partial(gui.change_page, ui))
            ui.hass_domain.currentIndexChanged.connect(partial(gui.change_hass_domain, ui))

            api.plugevents.attached.connect(partial(gui.streamdeck_attached, ui))
            api.plugevents.detached.connect(partial(gui.streamdeck_detached, ui))
            api.plugevents.cpu_changed.connect(partial(streamdeck_cpu_changed, ui))

            api.start()

            # Configure signal hanlders
            # https://stackoverflow.com/a/4939113/192815
            timer = QTimer()
            timer.start(500)
            timer.timeout.connect(lambda: None)  # type: ignore [attr-defined] # Let interpreter run to handle signal

            # Handle SIGTERM so we release semaphore and shutdown API gracefully
            signal.signal(signal.SIGTERM, partial(gui.sigterm_handler, api, app))

            # Handle <ctrl+c>
            signal.signal(signal.SIGINT, partial(gui.sigterm_handler, api, app))

            tray.show()

            if show_ui:
                main_window.show()

            app.exec()
            api.stop()
            sys.exit()
    except SemaphoreAcquireError:
        # The semaphore already exists, so another instance is running
        sys.exit()


if __name__ == '__main__':
    sys.exit(main())
