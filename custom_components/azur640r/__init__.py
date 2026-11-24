"""The Azur 640R integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .client import AzurAuthError, AzurConnectionError, AzurClient, AzurState, DEFAULT_PORT_NAME
from .const import CONF_KEY, CONF_PORT_NAME, DOMAIN, LOGGER, Azur640RConfigEntry

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.REMOTE,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: Azur640RConfigEntry) -> bool:
    """Set up the Azur 640R from a config entry."""
    client = AzurClient(
        entry.data[CONF_HOST],
        port_name=entry.data.get(CONF_PORT_NAME, DEFAULT_PORT_NAME),
        key=entry.data.get(CONF_KEY),
    )

    try:
        await client.connect()
    except AzurAuthError as err:
        if client.connected:
            await client.disconnect()
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="invalid_auth",
            translation_placeholders={"host": entry.data[CONF_HOST]},
        ) from err
    except (ConnectionError, OSError, TimeoutError, AzurConnectionError) as err:
        if client.connected:
            await client.disconnect()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": entry.data[CONF_HOST]},
        ) from err

    try:
        await client.get_software_version()
    except Exception:  # noqa: BLE001
        LOGGER.debug("Could not fetch Azur 640R software version at setup", exc_info=True)

    try:
        await client.get_protocol_version()
    except Exception:  # noqa: BLE001
        LOGGER.debug("Could not fetch Azur 640R protocol version at setup", exc_info=True)

    entry.runtime_data = client

    @callback
    def _on_disconnect(state: AzurState | None) -> None:
        if state is None and entry.state is ConfigEntryState.LOADED:
            LOGGER.warning("Azur 640R disconnected, reloading config entry")
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(client.subscribe(_on_disconnect))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Azur640RConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.disconnect()
    return unloaded
