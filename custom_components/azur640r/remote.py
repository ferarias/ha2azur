"""Remote platform for the Azur 640R integration -- OSD navigation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable

from homeassistant.components.remote import RemoteEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import AzurClient, AzurState
from .const import DOMAIN, Azur640RConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: Azur640RConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Azur 640R OSD remote from a config entry."""
    client = config_entry.runtime_data
    async_add_entities([Azur640ROsdRemote(client, config_entry)])


class Azur640ROsdRemote(RemoteEntity):
    """Navigates the receiver's on-screen display menu."""

    _attr_has_entity_name = True
    _attr_translation_key = "osd"
    _attr_should_poll = False
    _attr_assumed_state = True

    _COMMANDS: dict[str, Callable[[AzurClient], Awaitable[None]]] = {
        "up": AzurClient.osd_up,
        "down": AzurClient.osd_down,
        "left": AzurClient.osd_left,
        "right": AzurClient.osd_right,
        "enter": AzurClient.osd_enter,
    }

    def __init__(self, client: AzurClient, config_entry: Azur640RConfigEntry) -> None:
        self._client = client
        self._attr_unique_id = f"{config_entry.entry_id}_osd"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, config_entry.entry_id)})
        self._attr_is_on = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.subscribe(self._async_on_state_update))

    @callback
    def _async_on_state_update(self, state: AzurState | None) -> None:
        self._attr_available = state is not None
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._client.osd_on()
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.osd_off()
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_send_command(self, command: Iterable[str], **kwargs) -> None:
        """Honors the standard `num_repeats`/`delay_secs` service fields
        (e.g. "press up 3 times, 0.4s apart") -- without this, "num_repeats:
        3" would silently press each command only once."""
        num_repeats = kwargs.get("num_repeats", 1)
        delay_secs = kwargs.get("delay_secs", 0.4)
        commands = list(command)
        handlers = []
        for single_command in commands:
            handler = self._COMMANDS.get(single_command)
            if handler is None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_osd_command",
                    translation_placeholders={"command": single_command},
                )
            handlers.append(handler)

        for repeat in range(num_repeats):
            for handler in handlers:
                await handler(self._client)
            if repeat < num_repeats - 1 and delay_secs:
                await asyncio.sleep(delay_secs)
