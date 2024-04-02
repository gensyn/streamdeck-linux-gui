from streamdeck_ui.homeassistant import HomeAssistant


def test_homeassistant_setters():
    hass = HomeAssistant()

    assert hass._api is None
    assert hass._main_window is None
    assert hass._url == ""
    assert hass._token == ""
    assert hass._port == ""
    assert hass._ssl is True

    hass.set_api("api")
    hass.set_main_window("main_window")
    hass.set_url("url")
    hass.set_token("token")
    hass.set_port("port")
    hass.set_ssl(False)

    assert hass._api == "api"
    assert hass._main_window == "main_window"
    assert hass._url == "url"
    assert hass._token == "token"
    assert hass._port == "port"
    assert hass._ssl is False
