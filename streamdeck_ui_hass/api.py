"""Defines the Python API for interacting with the StreamDeck Configuration UI"""
import json
import os
import threading
from functools import partial
from typing import Dict, List, Optional, Tuple, Union, cast

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap
from StreamDeck.Devices import StreamDeck
from StreamDeck.Transport.Transport import TransportError

from config import CONFIG_FILE_VERSION, DEFAULT_FONT, STATE_FILE
from dimmer import Dimmer
from display.display_grid import DisplayGrid
from display.filter import Filter
from display.image_filter import ImageFilter
from display.pulse_filter import PulseFilter
from display.text_filter import TextFilter
from stream_deck_monitor import StreamDeckMonitor


class KeySignalEmitter(QObject):
    key_pressed = Signal(str, int, bool)


class StreamDeckSignalEmitter(QObject):
    attached = Signal(dict)
    "A signal that is raised whenever a new StreamDeck is attached."
    detached = Signal(str)
    "A signal that is raised whenever a StreamDeck is detached. "
    cpu_changed = Signal(str, int)


class StreamDeckServer:
    """A StreamDeckServer represents the core server logic for interacting and
    managing multiple Stream Decks.
    """

    def __init__(self) -> None:
        self.decks: Dict[str, StreamDeck.StreamDeck] = {}
        "Lookup with serial number -> StreamDeck"

        self.deck_ids: Dict[str, str] = {}
        "Lookup with device.id -> serial number"

        self.state: Dict[str, str | bool | Dict[str, Union[int, str, Dict[int, Dict[int, Dict[str, str]]]]]] = {}
        "The data structure holding configuration for all Stream Decks"

        # REVIEW: Should we use the same lock as the display? What exactly
        # are we protecting? The UI is signaled via message passing.
        self.key_event_lock = threading.Lock()
        "Lock to serialize key press events"

        self.display_handlers: Dict[str, DisplayGrid] = {}
        "Lookup with a display handler for each Stream Deck"

        self.lock: threading.Lock = threading.Lock()
        "Lock to coordinate polling, updates etc to Stream Decks"

        self.dimmers: Dict[str, Dimmer] = {}
        "Lookup with the dimmer for each Stream Deck"

        # REVIEW: Should we just create one signal emitter for
        # plug events and key signals?
        self.streamdeck_keys = KeySignalEmitter()
        "Use the connect method on the key_pressed signal to subscribe"

        self.plugevents = StreamDeckSignalEmitter()
        "Use the connect method on the attached and detached methods to subscribe"

        self.monitor: Optional[StreamDeckMonitor] = None
        "Monitors for Stream Deck(s) attached to the computer"

        self.hass = None

        self.button_clicked = False

    def set_hass(self, hass):
        self.hass = hass

    def stop_dimmer(self, serial_number: str) -> None:
        """Stops the dimmer for the given Stream Deck

        :param serial_number: The Stream Deck serial number.
        :type serial_number: str
        """
        self.dimmers[serial_number].stop()

    def reset_dimmer(self, serial_number: str) -> bool:
        """Resets the dimmer for the given Stream Deck. This means the display
        will not be dimmed and the timer starts. Reloads configuration.

        Args:
            serial_number (str): The Stream Deck serial number
        Returns:
            bool: Returns True if the dimmer had to be reset (i.e. woken up), False otherwise.
        """
        self.dimmers[serial_number].brightness = self.get_brightness(serial_number)
        self.dimmers[serial_number].brightness_dimmed = self.get_brightness_dimmed(serial_number)
        return self.dimmers[serial_number].reset()

    def toggle_dimmers(self):
        """If at least one Deck is still "on", all will be dimmed off. Otherwise
        toggles displays on.
        """
        at_least_one: bool = False
        for _serial_number, dimmer in self.dimmers.items():
            if not dimmer.dimmed:
                at_least_one = True
                break

        for _serial_number, dimmer in self.dimmers.items():
            if at_least_one:
                dimmer.dim()
            else:
                dimmer.dim(True)

    def cpu_usage_callback(self, serial_number: str, cpu_usage: int):
        """An internal method that takes emits a signal on a QObject.

        :param serial_number: The Stream Deck serial number
        :type serial_number: str
        :param cpu_usage: The current CPU usage
        :type cpu_usage: int
        """
        self.plugevents.cpu_changed.emit(serial_number, cpu_usage)

    def _key_change_callback(self, deck_id: str, _deck: StreamDeck.StreamDeck, key: int, state: bool) -> None:
        """Callback whenever a key is pressed.

        Stream Deck key events fire on a background thread. Emit a signal
        to bring it back to UI thread, so we can use Qt objects for timers etc.
        Since multiple keys could fire simultaniously, we need to protect
        shared state with a lock
        """
        with self.key_event_lock:
            displayhandler = self.display_handlers[deck_id]
            displayhandler.set_keypress(key, state)
            self.streamdeck_keys.key_pressed.emit(deck_id, key, state)

    def get_display_timeout(self, deck_id: str) -> int:
        """Returns the amount of time in seconds before the display gets dimmed."""
        return cast(int, self.state.get("decks", {}).get(deck_id, {}).get("display_timeout", 0))

    def set_display_timeout(self, deck_id: str, timeout: int) -> None:
        """Sets the amount of time in seconds before the display gets dimmed."""
        self.state.setdefault("decks", {}).setdefault(deck_id, {})["display_timeout"] = timeout
        self.dimmers[deck_id].timeout = timeout
        self._save_state()

    def _save_state(self):
        self.export_config(STATE_FILE)

    def open_config(self, config_file: str):
        with open(config_file) as state_file:
            config = json.loads(state_file.read())
            file_version = config.get("streamdeck_ui_version", 0)
            if file_version != CONFIG_FILE_VERSION:
                raise ValueError(
                    "Incompatible version of config file found: " f"{file_version} does not match required version " f"{CONFIG_FILE_VERSION}.")

            self.state = {"decks": {}}

            for deck_id, deck in config["state"].get("decks", {}).items():
                deck["buttons"] = {int(page_id): {int(button_id): button for button_id, button in buttons.items()} for
                                   page_id, buttons in deck.get("buttons", {}).items()}

                self.state["decks"][deck_id] = deck

            hass_url = config["state"].get("hass_url", "")
            hass_token = config["state"].get("hass_token", "")
            hass_port = config["state"].get("hass_port", "")
            hass_ssl = config["state"].get("hass_ssl", True)

            self.hass.set_url(hass_url)
            self.hass.set_token(hass_token)
            self.hass.set_port(hass_port)
            self.hass.set_ssl(hass_ssl)

            self.state["hass_url"] = hass_url
            self.state["hass_token"] = hass_token
            self.state["hass_port"] = hass_port
            self.state["hass_ssl"] = hass_ssl

            self.hass.connect()

    def import_config(self, config_file: str) -> None:
        self.stop()
        self.open_config(config_file)
        self._save_state()
        self.start()

    def export_config(self, output_file: str) -> None:
        try:
            with open(output_file + ".tmp", "w") as state_file:
                state_file.write(
                    json.dumps({"streamdeck_ui_version": CONFIG_FILE_VERSION, "state": self.state}, indent=4,
                               separators=(",", ": ")))
        except Exception as error:
            print(f"The configuration file '{output_file}' was not updated. Error: {error}")
            raise
        else:
            os.replace(output_file + ".tmp", os.path.realpath(output_file))

    def attached(self, streamdeck_id: str, streamdeck: StreamDeck):
        streamdeck.open()
        streamdeck.reset()
        serial_number = streamdeck.get_serial_number()

        # Store mapping from device id -> serial number
        # The detached event only knows about the id that got detached
        self.deck_ids[streamdeck_id] = serial_number
        self.decks[serial_number] = streamdeck
        self.initialize_state(serial_number, streamdeck.key_count())
        streamdeck.set_key_callback(partial(self._key_change_callback, serial_number))
        self.update_streamdeck_filters(serial_number)

        self.dimmers[serial_number] = Dimmer(
            self.get_display_timeout(serial_number),
            self.get_brightness(serial_number),
            self.get_brightness_dimmed(serial_number),
            lambda brightness: self.decks[serial_number].set_brightness(brightness),
        )
        self.dimmers[serial_number].reset()

        self.plugevents.attached.emit(
            {"id": streamdeck_id, "serial_number": serial_number, "type": streamdeck.deck_type(),
             "layout": streamdeck.key_layout()})

    def initialize_state(self, serial_number: str, buttons: int):
        """Initializes the state for the given serial number. This allocates
        buttons and pages based on the layout.

        :param serial_number: The Stream Deck serial number
        :type serial_number: str
        :param layout: The button layout for this Stream Deck
        :type layout: Tuple[int, int]
        """
        for page in range(10):
            for button in range(buttons):
                self._button_state(serial_number, page, button)

    def detached(self, id: str):
        serial_number = self.deck_ids.get(id, None)
        if serial_number:
            self.cleanup(id, serial_number)
            self.plugevents.detached.emit(serial_number)

    def cleanup(self, id: str, serial_number: str):
        display_grid = self.display_handlers[serial_number]
        display_grid.stop()
        del self.display_handlers[serial_number]

        dimmer = self.dimmers[serial_number]
        dimmer.stop()
        del self.dimmers[serial_number]

        streamdeck = self.decks[serial_number]
        try:
            if streamdeck.connected():
                streamdeck.set_brightness(50)
                streamdeck.reset()
                streamdeck.close()
        except TransportError:
            pass

        del self.decks[serial_number]
        del self.deck_ids[id]

    def start(self):
        if not self.monitor:
            self.monitor = StreamDeckMonitor(self.lock, self.attached, self.detached)
        self.monitor.start()

    def stop(self):
        self.monitor.stop()
        self.hass.disconnect()

    def get_deck(self, deck_id: str) -> Dict[str, Dict[str, Union[str, Tuple[int, int]]]]:
        """Returns a dictionary with some Stream Deck properties

        :param deck_id: The Stream Deck serial number
        :type deck_id: str
        :return: A dictionary with 'type' and 'layout' as keys
        :rtype: Dict[str, Dict[str, Union[str, Tuple[int, int]]]]
        """
        return {"type": self.decks[deck_id].deck_type(), "layout": self.decks[deck_id].key_layout()}

    def _button_state(self, deck_id: str, page: int, button: int) -> dict:
        buttons = self.state.setdefault("decks", {}).setdefault(deck_id, {}).setdefault("buttons", {})
        buttons_state = buttons.setdefault(page, {})  # type: ignore
        return buttons_state.setdefault(button, {})  # type: ignore

    def swap_buttons(self, deck_id: str, page: int, source_button: int, target_button: int) -> None:
        """Swaps the properties of the source and target buttons"""
        temp = cast(dict, self.state["decks"][deck_id]["buttons"])[page][source_button]
        cast(dict, self.state["decks"][deck_id]["buttons"])[page][source_button] = \
            cast(dict, self.state["decks"][deck_id]["buttons"])[page][target_button]
        cast(dict, self.state["decks"][deck_id]["buttons"])[page][target_button] = temp
        self._save_state()

        # Update rendering for these two images
        self.update_button_filters(deck_id, page, source_button)
        self.update_button_filters(deck_id, page, target_button)
        self.synchronize_display_filter(deck_id)

    def set_button_text(self, deck_id: str, page: int, button: int, text: str) -> None:
        """Set the text associated with a button"""
        if self.get_button_text(deck_id, page, button) != text:
            self._button_state(deck_id, page, button)["text"] = text
            self._save_state()
            self.update_button_filters(deck_id, page, button)
            self.synchronize_display_filter(deck_id)

    def get_button_text(self, deck_id: str, page: int, button: int) -> str:
        """Returns the text set for the specified button"""
        return self._button_state(deck_id, page, button).get("text", "")

    def set_button_icon(self, deck_id: str, page: int, button: int, icon: str) -> None:
        """Sets the icon associated with a button"""

        if self.get_button_icon(deck_id, page, button) != icon:
            self._button_state(deck_id, page, button)["icon"] = icon
            self._save_state()
            self.update_button_filters(deck_id, page, button)
            self.synchronize_display_filter(deck_id)

    def get_text_vertical_align(self, serial_number: str, page: int, button: int) -> str:
        """Gets the vertical text alignment. Values are bottom, middle-bottom, middle, middle-top, top

        :param serial_number: The Stream Deck serial number.
        :type serial_number: str
        :param page: The page the button is on
        :type page: int
        :param button: The button index
        :type button: int
        :return: The vertical alignment setting
        :rtype: str
        """
        return self._button_state(serial_number, page, button).get("text_vertical_align", "")

    def set_text_vertical_align(self, deck_id: str, page: int, button: int, alignment: str) -> None:
        """Gets the vertical text alignment. Values are top, middle, bottom

        :param deck_id: The Stream Deck serial number.
        :type deck_id: str
        :param page: The page the button is on
        :type page: int
        :param button: The button index
        :type button: int
        :return: The vertical alignment setting
        :rtype: str
        """
        if self.get_text_vertical_align(deck_id, page, button) != alignment:
            self._button_state(deck_id, page, button)["text_vertical_align"] = alignment
            self._save_state()
            self.update_button_filters(deck_id, page, button)
            self.synchronize_display_filter(deck_id)

    def get_button_icon_pixmap(self, deck_id: str, page: int, button: int) -> Optional[QPixmap]:
        """Returns the QPixmap value for the given button (streamdeck, page, button)

        :param deck_id: The Stream Deck serial number
        :type deck_id: str
        :param page: The page index
        :type page: int
        :param button: The button index
        :type button: int
        :return: A QPixmap object containing the image currently on the button
        :rtype: Optional[QPixmap]
        """

        deck = self.display_handlers.get(deck_id, None)

        if not deck:
            return None

        qt_image = ImageQt(deck.get_image(page, button))
        qt_image = qt_image.convertToFormat(QImage.Format.Format_ARGB32)
        return QPixmap(qt_image)

    def get_button_icon(self, deck_id: str, page: int, button: int) -> str:
        """Returns the icon path for the specified button"""
        return self._button_state(deck_id, page, button).get("icon", "")

    def set_button_change_brightness(self, deck_id: str, page: int, button: int, amount: int) -> None:
        """Sets the brightness changing associated with a button"""
        if self.get_button_change_brightness(deck_id, page, button) != amount:
            self._button_state(deck_id, page, button)["brightness_change"] = amount
            self._save_state()

    def get_button_change_brightness(self, deck_id: str, page: int, button: int) -> int:
        """Returns the brightness change set for a particular button"""
        return self._button_state(deck_id, page, button).get("brightness_change", 0)

    def set_button_command(self, deck_id: str, page: int, button: int, command: str) -> None:
        """Sets the command associated with the button"""
        if self.get_button_command(deck_id, page, button) != command:
            self._button_state(deck_id, page, button)["command"] = command
            self._save_state()

    def get_button_command(self, deck_id: str, page: int, button: int) -> str:
        """Returns the command set for the specified button"""
        return self._button_state(deck_id, page, button).get("command", "")

    def set_button_hass_domain(self, deck_id: str, page: int, button: int, hass_domain: str) -> None:
        if self.button_clicked:
            # Don't save change when a button was clicked
            return

        """Sets the Home Assistant domain associated with the button"""
        old = self.get_button_hass_domain(deck_id, page, button)

        if old != hass_domain:
            self._button_state(deck_id, page, button)["hass_domain"] = hass_domain
            self._save_state()
            self.update_button_filters(deck_id, page, button)
            self.synchronize_display_filter(deck_id)

    def get_button_hass_domain(self, deck_id: str, page: int, button: int) -> str:
        """Returns the Home Assistant domain set for the specified button"""
        return self._button_state(deck_id, page, button).get("hass_domain", "")

    def set_button_hass_entity(self, deck_id: str, page: int, button: int, hass_entity: str) -> None:
        if self.button_clicked:
            # Don't save change when a button was clicked
            return

        """Sets the Home Assistant entity associated with the button"""
        old = self.get_button_hass_entity(deck_id, page, button)

        if old != hass_entity:
            self._button_state(deck_id, page, button)["hass_entity"] = hass_entity

            if old:
                self.hass.remove_tracked_entity(old, deck_id, page, button)

            self.hass.add_tracked_entity(hass_entity, deck_id, page, button)
            self._save_state()

            if hass_entity:
                state = self.hass.get_state(hass_entity)
                domain = hass_entity.split(".")[0]

                if self.hass.is_button_icon(state, domain):
                    self.set_button_icon(deck_id, page, button,
                                         self.hass.get_icon(hass_entity,
                                                            self.get_button_hass_service(deck_id, page, button), state))
                else:
                    self.set_button_text(deck_id, page, button, state)
            else:
                self.set_button_icon(deck_id, page, button, "")
                self.set_button_text(deck_id, page, button, "")
                self.hass._main_window.ui.hass_service.setCurrentIndex(0)

            self.update_button_filters(deck_id, page, button)
            self.synchronize_display_filter(deck_id)

    def get_button_hass_entity(self, deck_id: str, page: int, button: int) -> str:
        """Returns the Home Assistant entity set for the specified button"""
        return self._button_state(deck_id, page, button).get("hass_entity", "")

    def set_button_hass_service(self, deck_id: str, page: int, button: int, hass_service: str) -> None:
        if self.button_clicked:
            # Don't save change when a button was clicked
            return

        """Sets the Home Assistant service associated with the button"""
        old = self.get_button_hass_service(deck_id, page, button)

        if old != hass_service:
            self._button_state(deck_id, page, button)["hass_service"] = hass_service
            self._save_state()

            hass_entity = self.get_button_hass_entity(deck_id, page, button)
            state = self.hass.get_state(hass_entity)
            domain = hass_entity.split(".")[0]

            if self.hass.is_button_icon(state, domain):
                self.set_button_icon(deck_id, page, button,
                                     self.hass.get_icon(hass_entity,
                                                        self.get_button_hass_service(deck_id, page, button), state))
            else:
                self.set_button_text(deck_id, page, button, state)

    def get_button_hass_service(self, deck_id: str, page: int, button: int) -> str:
        """Returns the Home Assistant service set for the specified button"""
        return self._button_state(deck_id, page, button).get("hass_service", "")

    def set_button_switch_page(self, deck_id: str, page: int, button: int, switch_page: int) -> None:
        """Sets the page switch associated with the button"""
        if self.get_button_switch_page(deck_id, page, button) != switch_page:
            self._button_state(deck_id, page, button)["switch_page"] = switch_page
            self._save_state()

    def get_button_switch_page(self, deck_id: str, page: int, button: int) -> int:
        """Returns the page switch set for the specified button. 0 implies no page switch."""
        return self._button_state(deck_id, page, button).get("switch_page", 0)

    def set_button_keys(self, deck_id: str, page: int, button: int, keys: str) -> None:
        """Sets the keys associated with the button"""
        if self.get_button_keys(deck_id, page, button) != keys:
            self._button_state(deck_id, page, button)["keys"] = keys
            self._save_state()

    def get_button_keys(self, deck_id: str, page: int, button: int) -> str:
        """Returns the keys set for the specified button"""
        return self._button_state(deck_id, page, button).get("keys", "")

    def set_button_write(self, deck_id: str, page: int, button: int, write: str) -> None:
        """Sets the text meant to be written when button is pressed"""
        if self.get_button_write(deck_id, page, button) != write:
            self._button_state(deck_id, page, button)["write"] = write
            self._save_state()

    def get_button_write(self, deck_id: str, page: int, button: int) -> str:
        """Returns the text to be produced when the specified button is pressed"""
        return self._button_state(deck_id, page, button).get("write", "")

    def set_brightness(self, deck_id: str, brightness: int) -> None:
        """Sets the brightness for every button on the deck"""
        if self.get_brightness(deck_id) != brightness:
            self.decks[deck_id].set_brightness(brightness)
            self.state.setdefault("decks", {}).setdefault(deck_id, {})["brightness"] = brightness
            self._save_state()

    def get_brightness(self, deck_id: str) -> int:
        """Gets the brightness that is set for the specified stream deck"""
        return self.state.get("decks", {}).get(deck_id, {}).get("brightness", 100)  # type: ignore

    def get_brightness_dimmed(self, deck_id: str) -> int:
        """Gets the percentage value of the full brightness that is used when dimming the specified
        stream deck"""
        return self.state.get("decks", {}).get(deck_id, {}).get("brightness_dimmed", 0)  # type: ignore

    def set_brightness_dimmed(self, deck_id: str, brightness_dimmed: int) -> None:
        """Sets the percentage value that will be used for dimming the full brightness"""
        self.state.setdefault("decks", {}).setdefault(deck_id, {})["brightness_dimmed"] = brightness_dimmed
        self._save_state()

    def get_hass_url(self) -> str:
        return self.state.get("hass_url", "")  # type: ignore

    def set_hass_url(self, hass_url: str) -> None:
        self.state["hass_url"] = hass_url
        self._save_state()
        self.hass.set_url(hass_url)

    def get_hass_token(self) -> str:
        return self.state.get("hass_token", "")  # type: ignore

    def set_hass_token(self, hass_token: str) -> None:
        self.state["hass_token"] = hass_token
        self._save_state()
        self.hass.set_token(hass_token)

    def get_hass_port(self) -> str:
        return self.state.get("hass_port", "")  # type: ignore

    def set_hass_port(self, hass_port: str) -> None:
        self.state["hass_port"] = hass_port
        self._save_state()
        self.hass.set_port(hass_port)

    def get_hass_ssl(self) -> bool:
        return self.state.get("hass_ssl", True)  # type: ignore

    def set_hass_ssl(self, hass_ssl: bool) -> None:
        self.state["hass_ssl"] = hass_ssl
        self._save_state()
        self.hass.set_ssl(hass_ssl)

    def change_brightness(self, deck_id: str, amount: int = 1) -> None:
        """Change the brightness of the deck by the specified amount"""
        brightness = max(min(self.get_brightness(deck_id) + amount, 100), 0)
        self.set_brightness(deck_id, brightness)
        self.dimmers[deck_id].brightness = brightness
        self.dimmers[deck_id].reset()

    def get_page(self, deck_id: str) -> int:
        """Gets the current page shown on the stream deck"""
        return self.state.get("decks", {}).get(deck_id, {}).get("page", 0)  # type: ignore

    def set_page(self, deck_id: str, page: int) -> None:
        """Sets the current page shown on the stream deck"""
        if self.get_page(deck_id) != page:
            self.state.setdefault("decks", {}).setdefault(deck_id, {})["page"] = page
            self._save_state()

        display_handler = self.display_handlers[deck_id]

        # Let the display know to process new set of pipelines
        display_handler.set_page(page)
        # Wait for at least one cycle
        self.synchronize_display_filter(deck_id)

    def update_streamdeck_filters(self, serial_number: str):
        """Updates the filters for all the StreamDeck buttons.

        :param serial_number: The StreamDeck serial number.
        :type serial_number: str
        """

        for deck_id, deck_state in self.state.get("decks", {}).items():
            deck = self.decks.get(deck_id, None)

            # Deck is not attached right now
            if deck is None:
                continue

            # REVIEW: Is there a better way to enumerate
            if deck_id != serial_number:
                continue

            # FIXME: Debug this - linter says there should not be a length. Issue is the way
            # the type hinting is defined causes it to believe there *may* not be a list
            pages = len(deck_state["buttons"])  # type: ignore

            display_handler = self.display_handlers.get(serial_number,
                                                        DisplayGrid(self.lock, deck, pages, self.cpu_usage_callback))
            display_handler.set_page(self.get_page(deck_id))
            self.display_handlers[serial_number] = display_handler

            for page, buttons in deck_state.get("buttons", {}).items():  # type: ignore
                for button in buttons:
                    self.update_button_filters(serial_number, page, button)

            display_handler.start()

    def update_button_filters(self, serial_number: str, page: int, button: int):
        """Sets the filters for a given button. Any previous filters are replaced.

        :param serial_number: The StreamDeck serial number
        :type serial_number: str
        :param page: The page number
        :type page: int
        :param button: The button to update
        :type button: int
        :param size: The size of the image. This will be refactored out. defaults to (72, 72)
        :type size: tuple, optional
        """
        display_handler = self.display_handlers.get(serial_number, None)

        if not display_handler:
            return

        button_settings = self._button_state(serial_number, page, button)
        filters: List[Filter] = []

        icon = button_settings.get("icon")
        if icon:
            # Now we have deck, page and buttons
            filters.append(ImageFilter(icon))

        if button_settings.get("pulse"):
            filters.append(PulseFilter())

        text = button_settings.get("text")
        font = button_settings.get("font", DEFAULT_FONT)
        vertical_align = button_settings.get("text_vertical_align", "")

        if text:
            if icon:
                font_size = 14
            elif len(text) < 4:
                font_size = 40
            elif len(text) < 5:
                font_size = 33
            elif len(text) < 6:
                font_size = 26
            else:
                font_size = 14

            filters.append(TextFilter(text, font, "middle", font_size))

        display_handler.replace(page, button, filters)

    def synchronize_display_filter(self, deck_id: str) -> None:
        handler = self.display_handlers.get(deck_id, None)

        if handler:
            handler.synchronize()
