import asyncio
import json
import os
from asyncio import Task
from logging import getLogger
from threading import Thread

import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from streamdeck_ui.config import PROJECT_PATH

_LOGGER = getLogger(__name__)

HASS_WEBSOCKET_API = "/api/websocket?latest"

FIELD_EVENT = "event"

MDI_SVG_JSON = "mdi/mdi-svg.json"
ENTITY_ID = "entity_id"
ID = "id"

FIELD_TYPE = "type"
FIELD_SUCCESS = "success"

ICON_SCALE = 0.66

COLOR_ON = "#eeff1b"
COLOR_OFF = "#bebebe"

MDI_TRANSFORM = 'fill="<color>" transform="translate(4.5, 5) scale(<scale>)"'

MDI_DEFAULT_PATH = "M7,2V13H10V22L17,10H13L17,2H7Z"

BUTTON_ENCODE_SYMBOL = "-"

RECV_LOOP_TIMEOUT = 300


class HomeAssistant:

    def __init__(self):
        self._api = None
        self._main_window = None
        self._websocket = None
        self._entity_change_trigger_websocket = None
        self._message_id: int = 0
        self._loop = None
        self._recv_task: Task
        self._domains = []
        self._entities = {}
        self._services = {}
        self._url: str = ""
        self._port: str = ""
        self._token: str = ""
        self._ssl: bool = True
        self._event_loop_thread = None

        filename = os.path.join(PROJECT_PATH, MDI_SVG_JSON)
        self._mdi_icons = json.loads(open(filename, "r").read())

    def set_api(self, api):
        self._api = api

    def set_main_window(self, main_window):
        self._main_window = main_window

    def set_url(self, url: str):
        if "//" in url:
            self._url = url.split("//")[1]
        else:
            self._url = url

    def set_token(self, token: str):
        self._token = token

    def set_port(self, port: str):
        self._port = port

    def set_ssl(self, ssl: bool):
        self._ssl = ssl

    def connect(self) -> bool:
        if self.is_connected():
            # already connected
            return True

        if not self._url or not self._token or not self._port or not self._ssl:
            return False

        if not self._loop or not self._loop.is_running():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            self._event_loop_thread = Thread(target=self._loop.run_forever)
            self._event_loop_thread.daemon = True
            self._event_loop_thread.start()

        # without result() connection might not have been established before first call to websocket
        return asyncio.run_coroutine_threadsafe(self._async_connect(), self._loop).result()

    async def _async_connect(self) -> bool:
        if await self._async_is_connected():
            # already connected
            return True

        if self._websocket and not self._websocket.closed:
            # close existing websocket
            await self._websocket.close()

        if self._entity_change_trigger_websocket and not self._entity_change_trigger_websocket.closed:
            # close existing websocket
            await self._entity_change_trigger_websocket.close()

        self._websocket = await self._async_auth()

        if not self._websocket:
            if self._main_window:
                self._main_window.hass_connection_changed.emit(False)

            return False

        self._entity_change_trigger_websocket = await self._async_auth()

        is_connected: bool = await self._async_is_connected()

        if is_connected:
            asyncio.create_task(self._async_run_recv_loop())

            # listen for events for entities associated with buttons and update icons
            for deck_id, deck in self._api.state.items():
                for page_id, page in deck.buttons.items():
                    for multi_button_id, multi_button in page.items():
                        for button_id, button in multi_button.states.items():
                            if button.hass_entity:
                                entity_id = button.hass_entity
                                await self._async_add_tracked_entity(entity_id, deck_id, page_id, multi_button_id)

                                domain = entity_id.split(".")[0]

                                entity_settings = self._entities.get(domain).get(entity_id)

                                if not entity_settings:
                                    # Entität existiert nicht (mehr)
                                    continue

                                buttons = entity_settings.get("buttons")

                                for button_string in buttons:
                                    deck_id, page, button = _decode_deck_id_page_button(button_string)

                                    service = self._api.get_button_hass_service(deck_id, page, button)

                                    state = await self._async_get_state(entity_id)

                                    domain = entity_id.split(".")[0]

                                    if self.is_button_icon(state, domain):
                                        icon = await self._async_get_icon(entity_id, service, state)

                                        self._api.set_button_icon(deck_id, page, button, icon)
                                    else:
                                        self._api.set_button_text(deck_id, page, button, state)

        if self._main_window:
            self._main_window.hass_connection_changed.emit(is_connected)

        return is_connected

    def disconnect(self) -> None:
        if self._websocket and not self._websocket.closed:
            asyncio.run_coroutine_threadsafe(self._websocket.close(), self._loop).result()

        # if self._entity_change_trigger_websocket and not self._entity_change_trigger_websocket.closed:
        #    asyncio.run_coroutine_threadsafe(self._entity_change_trigger_websocket.close(), self._loop).result()

        if self._loop and not self._loop.is_running():
            self._loop.close()

    async def _async_auth(self):
        websocket = None

        try:
            websocket = await websockets.connect(
                f'{"wss://" if self._ssl else "ws://"}{self._url}:{self._port}{HASS_WEBSOCKET_API}')

            auth_required = await asyncio.wait_for(websocket.recv(), timeout=5)
            auth_required = _get_field_from_message(auth_required, FIELD_TYPE)

            if not auth_required:
                _LOGGER.error("Could not auth with Home Assistant")
                return

            await websocket.send(json.dumps({FIELD_TYPE: "auth", "access_token": self._token}))

            auth_ok = await asyncio.wait_for(websocket.recv(), timeout=5)
            auth_ok = _get_field_from_message(auth_ok, FIELD_TYPE)

            if not auth_ok or "auth_ok" != auth_ok:
                _LOGGER.error("Could not auth with Home Assistant")
                return
        except websockets.ConnectionClosed:
            pass
        except ConnectionRefusedError as e:
            _LOGGER.error(
                f'Could not connect to {"wss://" if self._ssl else "ws://"}{self._url}:{self._port}/api/websocket?latest. Make sure'
                f" 'websocket_api' is enabled in your Home Assistant configuration.")
            pass
        except Exception:
            _LOGGER.error(
                f'Could not connect to {"wss://" if self._ssl else "ws://"}{self._url}:{self._port}/api/websocket?latest. Make sure'
                f" 'websocket_api' is enabled in your Home Assistant configuration.")

        return websocket

    async def _async_run_recv_loop(self):
        while not self._entity_change_trigger_websocket.closed:
            try:
                message = await self._entity_change_trigger_websocket.recv()
            except (ConnectionClosedOK, ConnectionClosedError):
                _LOGGER.info("Connection closed; quitting recv() loop.")
                break

            message_type = _get_field_from_message(message, FIELD_TYPE)

            if FIELD_EVENT == message_type:
                new_state = json.loads(message).get(FIELD_EVENT, {}).get("variables", {}).get("trigger", {}).get(
                    "to_state", {})

                entity_id = new_state.get(ENTITY_ID)

                domain = entity_id.split(".")[0]

                entity_settings = self._entities.get(domain).get(entity_id)

                buttons = entity_settings.get("buttons")

                for button_string in buttons:
                    deck_id, page, button = _decode_deck_id_page_button(button_string)

                    service = self._api.get_button_hass_service(deck_id, page, button)

                    state = new_state.get("state")

                    domain = entity_id.split(".")[0]

                    if self.is_button_icon(state, domain):
                        icon = await self._async_get_icon(entity_id, service, new_state.get("state"))

                        self._api.set_button_icon(deck_id, page, button, icon)
                    else:
                        self._api.set_button_text(deck_id, page, button, state)

                    if self._main_window and self._api.display_handlers.get(deck_id, False):
                        self._main_window.redraw_buttons()

        await self._websocket.close()
        self._loop.stop()

    def get_icon(self, entity_id: str, service: str, state: str = "") -> str:
        if not self.connect():
            return ""

        return asyncio.run_coroutine_threadsafe(self._async_get_icon(entity_id, service, state),
                                                self._loop).result()

    async def _async_get_icon(self, entity_id: str, service: str, state: str) -> str:
        if not entity_id:
            return ""

        domain = entity_id.split(".")[0]

        if "media_player" == domain:
            # use icons for service instead of entity
            if "media_play_pause" == service:
                if "playing" == state:
                    icon_name = "pause"
                else:
                    icon_name = "play"
            elif "media_stop" == service:
                icon_name = "stop"
            elif "volume_up" == service:
                icon_name = "volume-plus"
            elif "volume_down" == service:
                icon_name = "entity_id, volume-minus"
            elif "media_next_track" == service:
                icon_name = "skip-next"
            elif "media_previous_track" == service:
                icon_name = "skip-previous"
            else:
                _LOGGER.warning(f"Icon not found for domain {domain} and service {service}")
                icon_name = "alert-circle"

            icon = self._get_icon_svg(entity_id, icon_name)

            color = COLOR_ON
        else:
            # use icon of entity
            domain = entity_id.split(".")[0]

            entity = self._entities.get(domain).get(entity_id)

            icon_text = entity.get("icon", "None")
            icon = self._get_icon_svg(entity_id, icon_text)

            color = COLOR_ON if "on" == state else COLOR_OFF

        return icon.replace("<path", f"<path {MDI_TRANSFORM}").replace("<scale>", str(ICON_SCALE)).replace("<color>",
                                                                                                           color)

    def get_state(self, entity_id: str) -> str:
        if not self.connect():
            return ""

        return asyncio.run_coroutine_threadsafe(self._async_get_state(entity_id),
                                                self._loop).result()

    async def _async_get_state(self, entity_id: str) -> str:
        message = self.create_message("get_states")

        message_id: int = message[ID]

        await self._websocket.send(json.dumps(message))

        response = await self._wait_for_response(message_id)

        success = _get_field_from_message(response, FIELD_SUCCESS)

        if not success:
            _LOGGER.error(f"Error retrieving state for {entity_id}.")
            return "off"

        for entity in _get_field_from_message(response, "result"):
            if entity.get(ENTITY_ID, "") == entity_id:
                return entity.get("state", "off")

        return "off"

    def get_domains(self) -> list:
        if not self.connect():
            return []

        return asyncio.run_coroutine_threadsafe(self._async_get_domains(), self._loop).result()

    async def _async_get_domains(self) -> list:
        if self._domains:
            return self._domains

        await self._load_domains_and_entities()

        return self._domains

    def get_entities(self, domain: str) -> list:
        if not self.connect():
            return []

        return asyncio.run_coroutine_threadsafe(self._async_get_entities(domain), self._loop).result()

    async def _async_get_entities(self, domain: str) -> list:
        if not domain:
            return []

        if self._entities:
            return list(self._entities.get(domain, {}).keys())

        await self._load_domains_and_entities()

        return list(self._entities.get(domain, {}).keys())

    async def _load_domains_and_entities(self) -> None:
        message = self.create_message("get_states")

        message_id: int = message[ID]

        await self._websocket.send(json.dumps(message))

        response = await self._wait_for_response(message_id)

        success = _get_field_from_message(response, FIELD_SUCCESS)

        self._domains = []
        self._entities = {}

        if not success:
            _LOGGER.error("Error retrieving domains and entities.")
            return

        for entity in _get_field_from_message(response, "result"):
            entity_id = entity.get(ENTITY_ID)

            domain = entity_id.split(".")[0]

            if domain not in self._domains:
                self._domains.append(domain)

            if domain not in self._entities:
                self._entities[domain] = {}

            self._entities[domain][entity_id] = {
                "state": entity.get("state", "off"),
                "icon": entity.get("attributes", {}).get("icon", ""),
                "buttons": [],
                "subscription_id": -1
            }

    def get_services(self, domain: str) -> list:
        if not self.connect():
            return []

        return asyncio.run_coroutine_threadsafe(self._async_get_services(domain), self._loop).result()

    async def _async_get_services(self, domain: str) -> list:
        if not domain:
            return []

        if self._services:
            return self._services.get(domain, [])

        message = self.create_message("get_services")

        message_id: int = message[ID]

        await self._websocket.send(json.dumps(message))

        response = await self._wait_for_response(message_id)

        success = _get_field_from_message(response, FIELD_SUCCESS)

        self._services = {}

        if not success:
            _LOGGER.error("Error retrieving services.")
            return []

        for remote_domain in _get_field_from_message(response, "result"):
            self._services[remote_domain] = list(
                _get_field_from_message(response, "result").get(remote_domain, {}).keys())

        return self._services.get(domain, [])

    def call_service(self, entity_id: str, service: str) -> None:
        if not self.connect():
            return

        asyncio.run_coroutine_threadsafe(self._async_call_service(entity_id, service), self._loop).result()

    async def _async_call_service(self, entity_id: str, service: str) -> None:
        domain = entity_id.split(".")[0]

        message = self.create_message("call_service")
        message["domain"] = domain
        message["service"] = service
        message["target"] = {
            ENTITY_ID: entity_id
        }

        message_id: int = message[ID]

        await self._websocket.send(json.dumps(message))

        response = await self._wait_for_response(message_id)

        success = _get_field_from_message(response, FIELD_SUCCESS)

        if not success:
            _LOGGER.error(f"Error toggling entity: {entity_id}.")

    def create_message(self, message_type: str) -> dict:
        self._message_id += 1
        return {ID: self._message_id, FIELD_TYPE: message_type}

    def add_tracked_entity(self, entity_id: str, deck_id: str, page: int, button: int) -> None:
        if not self.connect():
            return

        asyncio.run_coroutine_threadsafe(self._async_add_tracked_entity(entity_id, deck_id, page, button),
                                         self._loop).result()

    async def _async_add_tracked_entity(self, entity_id: str, deck_id: str, page: int, button: int) -> None:
        if not entity_id:
            return

        domain = entity_id.split(".")[0]

        if not self._entities:
            await self._load_domains_and_entities()

        entity_settings = self._entities.get(domain).get(entity_id)

        if not entity_settings:
            # Entität existiert nicht (mehr)
            return

        button_string = _encode_deck_id_page_button(deck_id, page, button)

        if button_string in entity_settings.get("buttons"):
            # button already registered
            return

        entity_settings.get("buttons").append(button_string)

        if entity_settings.get("subscription_id") > -1:
            # already subscribed to entity events
            return

        message = self.create_message("subscribe_trigger")
        message["trigger"] = {"platform": "state", ENTITY_ID: entity_id}

        message_id = message.get(ID)

        await self._entity_change_trigger_websocket.send(json.dumps(message))

        # response = await self._wait_for_response(message_id)
        #
        # success = _get_field_from_message(response, FIELD_SUCCESS)
        #
        # if not success:
        #     _LOGGER.error(f"Error subscribing to trigger: {entity_id}.")
        #     return

        entity_settings["subscription_id"] = message_id

    def remove_tracked_entity(self, entity_id: str, deck_id: str, page: int, button: int) -> None:
        if not self.connect():
            return

        asyncio.run_coroutine_threadsafe(self._async_remove_tracked_entity(entity_id, deck_id, page, button),
                                         self._loop).result()

    async def _async_remove_tracked_entity(self, entity_id: str, deck_id: str, page: int, button: int) -> None:
        domain = entity_id.split(".")[0]

        entity_settings = self._entities.get(domain).get(entity_id)

        button_string = _encode_deck_id_page_button(deck_id, page, button)

        if button_string in entity_settings.get("buttons"):
            entity_settings.get("buttons").remove(button_string)

        if len(entity_settings.get("buttons")) > 0:
            # the entity is still attached to another button, so keep the trigger subscription
            return

        message = self.create_message("unsubscribe_events")
        message["subscription_id"] = entity_settings["subscription_id"]

        message_id = message.get(ID)

        await self._entity_change_trigger_websocket.send(json.dumps(message))

        # response = await self._wait_for_response(message_id)
        #
        # success = _get_field_from_message(response, FIELD_SUCCESS)
        #
        # if not success:
        #     _LOGGER.error(f"Error unsubscribing from trigger: {entity_id}.")
        #     return

        entity_settings["subscription_id"] = -1

    def is_connected(self) -> bool:
        if not self._loop or not self._loop.is_running():
            return False

        if not self._websocket or self._websocket.closed or not self._entity_change_trigger_websocket or self._entity_change_trigger_websocket.closed:
            return False

        return asyncio.run_coroutine_threadsafe(self._async_is_connected(), self._loop).result()

    async def _async_is_connected(self) -> bool:
        if not self._websocket or self._websocket.closed or not self._entity_change_trigger_websocket or self._entity_change_trigger_websocket.closed:
            return False

        a = await is_websocket_alive(self._websocket)
        b = await is_websocket_alive(self._entity_change_trigger_websocket)
        return a and b

    def _get_icon_svg(self, entity_id: str, name: str) -> str:
        if "mdi:" in name:
            name = name.replace("mdi:", "")

        path = self._mdi_icons.get(name, "")

        if not path:
            path = MDI_DEFAULT_PATH

        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><title>{name}</title><path d="{path}" /></svg>'

    async def _wait_for_response(self, message_id: int) -> str:
        while True:
            response = await asyncio.wait_for(self._websocket.recv(), timeout=5)
            response_id = _get_field_from_message(response, ID)

            if message_id == response_id:
                break

        return response

    def is_button_icon(self, state: str, domain: str) -> bool:
        return state in ["on", "off"] or domain in ["media_player"]


def _encode_deck_id_page_button(deck_id: str, page: int, button: int) -> str:
    return f"{deck_id}{BUTTON_ENCODE_SYMBOL}{page}{BUTTON_ENCODE_SYMBOL}{button}"


def _decode_deck_id_page_button(encoded: str):
    values = encoded.split(BUTTON_ENCODE_SYMBOL)
    return values[0], int(values[1]), int(values[2])


def _get_field_from_message(message: str, field: str):
    try:
        parsed = json.loads(message)

        return parsed.get(field, "")
    except json.JSONDecodeError:
        _LOGGER.error(f"Could not parse {message}")
        return ""


async def is_websocket_alive(websocket):
    try:
        pong_waiter = websocket.ping()
        await asyncio.wait_for(pong_waiter, timeout=1)
        return True
    except TimeoutError:
        # The connection is closed or the ping wasn't answered in time
        return False
