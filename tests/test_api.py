from hypothesis_auto import auto_pytest_magic

from streamdeck_ui_hass import api
from homeassistant import HomeAssistant

server = api.StreamDeckServer(HomeAssistant())

auto_pytest_magic(server.set_button_command)
auto_pytest_magic(server.get_button_command)
auto_pytest_magic(server.set_button_switch_page)
auto_pytest_magic(server.get_button_switch_page)
auto_pytest_magic(server.set_button_keys)
auto_pytest_magic(server.get_button_keys)
auto_pytest_magic(server.set_button_write)
auto_pytest_magic(server.get_button_write)
auto_pytest_magic(server.set_button_hass_entity)
auto_pytest_magic(server.get_button_hass_entity)
auto_pytest_magic(server.set_button_hass_service)
auto_pytest_magic(server.get_button_hass_service)
auto_pytest_magic(server.set_hass_url)
auto_pytest_magic(server.get_hass_url)
auto_pytest_magic(server.set_hass_token)
auto_pytest_magic(server.get_hass_token)
auto_pytest_magic(server.set_hass_port)
auto_pytest_magic(server.get_hass_port)
auto_pytest_magic(server.set_hass_ssl)
auto_pytest_magic(server.get_hass_ssl)
auto_pytest_magic(server.set_brightness, auto_allow_exceptions_=(KeyError,))
auto_pytest_magic(server.get_brightness)
auto_pytest_magic(server.change_brightness, auto_allow_exceptions_=(KeyError,))
auto_pytest_magic(server.get_page)
