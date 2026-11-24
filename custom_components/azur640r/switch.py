"""Switch platform for the Azur 640R integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
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
    """Set up the Azur 640R switch entities from a config entry."""
    client = config_entry.runtime_data
    async_add_entities(
        [
            Azur640RSwitch(
                client,
                config_entry,
                translation_key="subwoofer",
                get_value=lambda state: state.sub_on,
                turn_on=client.sub_on,
                turn_off=client.sub_off,
            ),
            Azur640RSwitch(
                client,
                config_entry,
                translation_key="stereo_plus_sw",
                get_value=lambda state: state.stereo_plus_sw,
                turn_on=lambda: client.set_stereo_plus_sw(enabled=True),
                turn_off=lambda: client.set_stereo_plus_sw(enabled=False),
            ),
            Azur640RSwitch(
                client,
                config_entry,
                translation_key="tuner_mono",
                get_value=lambda state: state.tuner_mono,
                turn_on=lambda: client.set_tuner_mono(mono=True),
                turn_off=lambda: client.set_tuner_mono(mono=False),
            ),
        ]
    )


class Azur640RSwitch(SwitchEntity):
    """A boolean amplifier/tuner setting, exposed as an HA switch."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True

    def __init__(
        self,
        client: AzurClient,
        config_entry: Azur640RConfigEntry,
        *,
        translation_key: str,
        get_value: Callable[[AzurState], bool | None],
        turn_on: Callable[[], Awaitable[None]],
        turn_off: Callable[[], Awaitable[None]],
    ) -> None:
        self._client = client
        self._get_value = get_value
        self._turn_on = turn_on
        self._turn_off = turn_off
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{config_entry.entry_id}_{translation_key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, config_entry.entry_id)})
        self._async_update_from_state(client.state)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.subscribe(self._async_on_state_update))

    @callback
    def _async_on_state_update(self, state: AzurState | None) -> None:
        if state is None:
            self._attr_available = False
        else:
            self._attr_available = True
            self._async_update_from_state(state)
        self.async_write_ha_state()

    @callback
    def _async_update_from_state(self, state: AzurState) -> None:
        self._attr_is_on = self._get_value(state)

    async def async_turn_on(self, **kwargs) -> None:
        await self._turn_on()

    async def async_turn_off(self, **kwargs) -> None:
        await self._turn_off()
