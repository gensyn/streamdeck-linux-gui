"""Defines the Python API for interacting with the StreamDeck Configuration UI"""
import json
import os
import threading
import time
from functools import partial
from io import BytesIO
from typing import Dict, Optional, Tuple, Union, cast, List
from warnings import warn

from PIL.ImageQt import ImageQt
from PySide2.QtCore import QObject, Signal
from PySide2.QtGui import QImage, QPixmap
from StreamDeck import DeviceManager
from StreamDeck.Devices import StreamDeck
from StreamDeck.ImageHelpers import PILHelper

from streamdeck_ui.config import CONFIG_FILE_VERSION, DEFAULT_FONT, STATE_FILE
from streamdeck_ui.display.display_grid import DisplayGrid
from streamdeck_ui.display.filter import Filter
from streamdeck_ui.display.image_filter import ImageFilter
from streamdeck_ui.display.pulse_filter import PulseFilter
from streamdeck_ui.display.text_filter import TextFilter
from streamdeck_ui.stream_deck_monitor import StreamDeckMonitor

# Cache consists of a tuple. The native streamdeck image and the QPixmap for screen rendering
image_cache: Dict[str, Tuple[BytesIO, QPixmap]] = {}
decks: Dict[str, StreamDeck.StreamDeck] = {}

# Keep track of device.id -> Serial Number
deck_ids: Dict[str, str] = {}

state: Dict[str, Dict[str, Union[int, str, Dict[int, Dict[int, Dict[str, str]]]]]] = {}
# FIXME: Should the lock move to the display manager, including other display operations
streamdecks_lock = threading.Lock()
key_event_lock = threading.Lock()

display_handlers: Dict[str, DisplayGrid] = {}


class KeySignalEmitter(QObject):
    key_pressed = Signal(str, int, bool)


# TODO: Review if this will work for multiple streamdecks
streamdeck_keys = KeySignalEmitter()


class StreamDeckSignalEmitter(QObject):
    attached = Signal(dict)
    "A signal that is raised whenever a new StreamDeck is attached."
    detatched = Signal(str)
    "A signal that is raised whenever a StreamDeck is detatched. "


plugevents = StreamDeckSignalEmitter()


def _key_change_callback(deck_id: str, _deck: StreamDeck.StreamDeck, key: int, state: bool) -> None:
    """Callback whenever a key is pressed. This is method runs the various actions defined
    for the key being pressed, sequentially."""
    # Stream Desk key events fire on a background thread. Emit a signal
    # to bring it back to UI thread, so we can use Qt objects for timers etc.
    # Since multiple keys could fire simultaniously, we need to protect
    # shared state with a lock
    with key_event_lock:
        streamdeck_keys.key_pressed.emit(deck_id, key, state)


def get_display_timeout(deck_id: str) -> int:
    """Returns the amount of time in seconds before the display gets dimmed."""
    return cast(int, state.get(deck_id, {}).get("display_timeout", 0))


def set_display_timeout(deck_id: str, timeout: int) -> None:
    """Sets the amount of time in seconds before the display gets dimmed."""
    state.setdefault(deck_id, {})["display_timeout"] = timeout
    _save_state()


def _save_state():
    export_config(STATE_FILE)


def _open_config(config_file: str):
    global state

    with open(config_file) as state_file:
        config = json.loads(state_file.read())
        file_version = config.get("streamdeck_ui_version", 0)
        if file_version != CONFIG_FILE_VERSION:
            raise ValueError("Incompatible version of config file found: " f"{file_version} does not match required version " f"{CONFIG_FILE_VERSION}.")

        state = {}
        for deck_id, deck in config["state"].items():
            deck["buttons"] = {int(page_id): {int(button_id): button for button_id, button in buttons.items()} for page_id, buttons in deck.get("buttons", {}).items()}
            state[deck_id] = deck


def import_config(config_file: str) -> None:
    _open_config(config_file)
    render()
    _save_state()


def export_config(output_file: str) -> None:
    try:
        with open(output_file + ".tmp", "w") as state_file:
            state_file.write(
                json.dumps(
                    {"streamdeck_ui_version": CONFIG_FILE_VERSION, "state": state},
                    indent=4,
                    separators=(",", ": "),
                )
            )
    except Exception as error:
        print(f"The configuration file '{output_file}' was not updated. Error: {error}")
        raise
    else:
        os.replace(output_file + ".tmp", os.path.realpath(output_file))


monitor : StreamDeckMonitor


def attached(streamdeck_id: str, streamdeck: StreamDeck):
    streamdeck.open()
    streamdeck.reset()
    serial_number = streamdeck.get_serial_number()

    # Store mapping from device id -> serial number
    # The detatched event only knows about the id that got detatched
    deck_ids[streamdeck_id] = serial_number
    decks[serial_number] = streamdeck
    streamdeck.set_key_callback(partial(_key_change_callback, serial_number))
    update_streamdeck_filters(serial_number)
    plugevents.attached.emit({"id": streamdeck_id, "serial_number": serial_number, "type": streamdeck.deck_type(), "layout": streamdeck.key_layout()})


def detatched(id: str):
    serial_number = deck_ids.get(id, None)
    if serial_number:
        plugevents.detatched.emit(serial_number)


def start():
    global monitor
    monitor = StreamDeckMonitor(attached, detatched)
    monitor.start()


def stop():
    global monitor
    monitor.stop()

    for _, display_grid in display_handlers.items():
        display_grid.stop()

    for _, deck in decks.items():
        if deck.connected():
            deck.set_brightness(50)
            deck.reset()
            deck.close()


# FIXME: This needs to be deprecated
def ensure_decks_connected() -> None:
    """Reconnects to any decks that lost connection. If they did, re-renders them."""
    for deck_serial, deck in decks.copy().items():
        if not deck.connected():
            for new_deck in DeviceManager.DeviceManager().enumerate():
                try:
                    new_deck.open()
                    new_deck_serial = new_deck.get_serial_number()
                except Exception as error:
                    warn(f"A {error} error occurred when trying to reconnect to {deck_serial}")
                    new_deck_serial = None

                if new_deck_serial == deck_serial:
                    deck.close()
                    new_deck.reset()
                    new_deck.set_key_callback(partial(_key_change_callback, new_deck_serial))
                    decks[new_deck_serial] = new_deck
                    render()


def get_deck(deck_id: str) -> Dict[str, Dict[str, Union[str, Tuple[int, int]]]]:
    return {"type": decks[deck_id].deck_type(), "layout": decks[deck_id].key_layout()}


def _button_state(deck_id: str, page: int, button: int) -> dict:
    buttons = state.setdefault(deck_id, {}).setdefault("buttons", {})
    buttons_state = buttons.setdefault(page, {})  # type: ignore
    return buttons_state.setdefault(button, {})  # type: ignore


def swap_buttons(deck_id: str, page: int, source_button: int, target_button: int) -> None:
    """Swaps the properties of the source and target buttons"""
    temp = cast(dict, state[deck_id]["buttons"])[page][source_button]
    cast(dict, state[deck_id]["buttons"])[page][source_button] = cast(dict, state[deck_id]["buttons"])[page][target_button]
    cast(dict, state[deck_id]["buttons"])[page][target_button] = temp

    # Clear the cache so images will be recreated on render
    image_cache.pop(f"{deck_id}.{page}.{source_button}", None)
    image_cache.pop(f"{deck_id}.{page}.{target_button}", None)

    _save_state()
    render()


def set_button_text(deck_id: str, page: int, button: int, text: str) -> None:
    """Set the text associated with a button"""
    if get_button_text(deck_id, page, button) != text:
        _button_state(deck_id, page, button)["text"] = text
        image_cache.pop(f"{deck_id}.{page}.{button}", None)

        # FIXME: Load only new pipeline for key
        # FIXME: Refresh screen display button
        update_button_filters(deck_id, page, button)
        #render()
        _save_state()


def get_button_text(deck_id: str, page: int, button: int) -> str:
    """Returns the text set for the specified button"""
    return _button_state(deck_id, page, button).get("text", "")


def set_button_icon(deck_id: str, page: int, button: int, icon: str) -> None:
    """Sets the icon associated with a button"""

    # FIXME: This isn't right - it's supposed to compare if the icon changed, 
    # but the api returns a QBitMap. Apples to Oranges.
    if get_button_icon(deck_id, page, button) != icon:
        _button_state(deck_id, page, button)["icon"] = icon
        image_cache.pop(f"{deck_id}.{page}.{button}", None)

        # Can we update just the one?
        update_button_filters(deck_id, page, button)
        #render()

        _save_state()


def get_button_icon(deck_id: str, page: int, button: int) -> Optional[QPixmap]:
    """Returns the icon set for a particular button"""

    # TODO: Refine this logic - for now - anytime someone ask for a button
    # update the button image cache
    # render()
    # key = f"{deck_id}.{page}.{button}"
    # if key not in image_cache:
    #     return None
    # return image_cache[key][1]

    pil_image = display_handlers[deck_id].get_image(page, button)
    if pil_image:
        qt_image = ImageQt(pil_image)
        qt_image = qt_image.convertToFormat(QImage.Format_ARGB32)
        return QPixmap(qt_image)
    return None


def set_button_change_brightness(deck_id: str, page: int, button: int, amount: int) -> None:
    """Sets the brightness changing associated with a button"""
    if get_button_change_brightness(deck_id, page, button) != amount:
        _button_state(deck_id, page, button)["brightness_change"] = amount
        render()
        _save_state()


def get_button_change_brightness(deck_id: str, page: int, button: int) -> int:
    """Returns the brightness change set for a particular button"""
    return _button_state(deck_id, page, button).get("brightness_change", 0)


def set_button_command(deck_id: str, page: int, button: int, command: str) -> None:
    """Sets the command associated with the button"""
    if get_button_command(deck_id, page, button) != command:
        _button_state(deck_id, page, button)["command"] = command
        _save_state()


def get_button_command(deck_id: str, page: int, button: int) -> str:
    """Returns the command set for the specified button"""
    return _button_state(deck_id, page, button).get("command", "")


def set_button_switch_page(deck_id: str, page: int, button: int, switch_page: int) -> None:
    """Sets the page switch associated with the button"""
    if get_button_switch_page(deck_id, page, button) != switch_page:
        _button_state(deck_id, page, button)["switch_page"] = switch_page
        _save_state()


def get_button_switch_page(deck_id: str, page: int, button: int) -> int:
    """Returns the page switch set for the specified button. 0 implies no page switch."""
    return _button_state(deck_id, page, button).get("switch_page", 0)


def set_button_keys(deck_id: str, page: int, button: int, keys: str) -> None:
    """Sets the keys associated with the button"""
    if get_button_keys(deck_id, page, button) != keys:
        _button_state(deck_id, page, button)["keys"] = keys
        _save_state()


def get_button_keys(deck_id: str, page: int, button: int) -> str:
    """Returns the keys set for the specified button"""
    return _button_state(deck_id, page, button).get("keys", "")


def set_button_write(deck_id: str, page: int, button: int, write: str) -> None:
    """Sets the text meant to be written when button is pressed"""
    if get_button_write(deck_id, page, button) != write:
        _button_state(deck_id, page, button)["write"] = write
        _save_state()


def get_button_write(deck_id: str, page: int, button: int) -> str:
    """Returns the text to be produced when the specified button is pressed"""
    return _button_state(deck_id, page, button).get("write", "")


def set_brightness(deck_id: str, brightness: int) -> None:
    """Sets the brightness for every button on the deck"""
    if get_brightness(deck_id) != brightness:
        decks[deck_id].set_brightness(brightness)
        state.setdefault(deck_id, {})["brightness"] = brightness
        _save_state()


def get_brightness(deck_id: str) -> int:
    """Gets the brightness that is set for the specified stream deck"""
    return state.get(deck_id, {}).get("brightness", 100)  # type: ignore


def get_brightness_dimmed(deck_id: str) -> int:
    """Gets the percentage value of the full brightness that is used when dimming the specified
    stream deck"""
    return state.get(deck_id, {}).get("brightness_dimmed", 0)  # type: ignore


def set_brightness_dimmed(deck_id: str, brightness_dimmed: int) -> None:
    """Sets the percentage value that will be used for dimming the full brightness"""
    state.setdefault(deck_id, {})["brightness_dimmed"] = brightness_dimmed
    _save_state()


def change_brightness(deck_id: str, amount: int = 1) -> None:
    """Change the brightness of the deck by the specified amount"""
    set_brightness(deck_id, max(min(get_brightness(deck_id) + amount, 100), 0))


def get_page(deck_id: str) -> int:
    """Gets the current page shown on the stream deck"""
    return state.get(deck_id, {}).get("page", 0)  # type: ignore


def set_page(deck_id: str, page: int) -> None:
    """Sets the current page shown on the stream deck"""
    if get_page(deck_id) != page:
        state.setdefault(deck_id, {})["page"] = page

        display_handlers[deck_id].set_page(page)
        render()
        _save_state()


def update_streamdeck_filters(serial_number: str):
    """Updates the filters for all the StreamDeck buttons.

    :param serial_number: The StreamDeck serial number.
    :type serial_number: str
    """

    for deck_id, deck_state in state.items():

        deck = decks.get(deck_id, None)

        # Deck is not attached right now
        if deck is None:
            continue

        # TODO: Debug this - says there should not be a length
        pages = len(deck_state["buttons"])

        display_handler = display_handlers.get(serial_number, DisplayGrid(deck, pages))
        display_handler.set_page(get_page(deck_id))
        display_handlers[serial_number] = display_handler

        for page, buttons in deck_state.get("buttons", {}).items():
            for button in buttons:
                update_button_filters(serial_number, page, button)

        display_handler.start()


def update_button_filters(serial_number: str, page: int, button: int):
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
    display_handler = display_handlers[serial_number]
    button_settings = _button_state(serial_number, page, button)
    filters: List[Filter] = []

    icon = button_settings.get("icon")
    if icon:
        # Now we have deck, page and buttons
        filters.append(ImageFilter(icon))

    if button_settings.get("pulse"):
        filters.append(PulseFilter())

    text = button_settings.get("text")
    font = button_settings.get("font", DEFAULT_FONT)

    if text:
        filters.append(TextFilter(text, font))

    display_handler.replace(page, button, filters)


# FIXME: Remove all references?
def render() -> None:
    """renders all decks"""
    return
    global display_handler

    for deck_id, deck_state in state.items():
        deck = decks.get(deck_id, None)
        if not deck:
            warn(f"{deck_id} has settings specified but is not seen. Likely unplugged!")
            continue

        # Lookup which page is active for this deck
        page = get_page(deck_id)
        for button_id, _ in deck_state.get("buttons", {}).get(page, {}).items():  # type: ignore
            key = f"{deck_id}.{page}.{button_id}"
            if key in image_cache:
                image = image_cache[key][0]
            else:

                # TODO: Do we need this cache at all anymore? Decide how to update
                # UI from display engine (keep in sync, show static?)
                pil_image = display_handlers[deck_id].get_image(page, button_id)
                if pil_image:
                    image = PILHelper.to_native_format(deck, pil_image.convert("RGB"))

                    qt_image = ImageQt(pil_image)
                    qt_image = qt_image.convertToFormat(QImage.Format_ARGB32)
                    pixmap = QPixmap(qt_image)
                    image_cache[key] = (image, pixmap)


if os.path.isfile(STATE_FILE):
    _open_config(STATE_FILE)
