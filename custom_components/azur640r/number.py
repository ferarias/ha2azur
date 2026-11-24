"""Number platform for the Azur 640R integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up the Azur 640R number entities from a config entry."""
    client = config_entry.runtime_data
    async_add_entities(
        [
            Azur640RNumber(
                client,
                config_entry,
                translation_key="bass",
                native_min_value=-10,
                native_max_value=10,
                native_step=2,  # verified against real hardware: 2dB per
                # step (11 positions, -10..10), not 1dB despite the doc's
                # "-10 to 10" range wording -- see `AzurClient.set_bass`.
                get_value=lambda state: state.bass_db,
                set_value=client.set_bass,
            ),
            Azur640RNumber(
                client,
                config_entry,
                translation_key="treble",
                native_min_value=-10,
                native_max_value=10,
                native_step=2,  # see the `bass` entity above
                get_value=lambda state: state.treble_db,
                set_value=client.set_treble,
            ),
            Azur640RNumber(
                client,
                config_entry,
                translation_key="lfe_trim",
                native_min_value=-10,
                native_max_value=0,
                get_value=lambda state: state.lfe_trim_db,
                set_value=client.set_lfe_trim,
            ),
        ]
    )


class Azur640RNumber(NumberEntity):
    """A single-dB-step amplifier setting, exposed as an HA number slider."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "dB"

    def __init__(
        self,
        client: AzurClient,
        config_entry: Azur640RConfigEntry,
        *,
        translation_key: str,
        native_min_value: float,
        native_max_value: float,
        get_value: Callable[[AzurState], int | None],
        set_value: Callable[[int], Awaitable[None]],
        native_step: float = 1,
    ) -> None:
        self._client = client
        self._get_value = get_value
        self._set_value = set_value
        self._attr_translation_key = translation_key
        self._attr_native_min_value = native_min_value
        self._attr_native_max_value = native_max_value
        self._attr_native_step = native_step
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
        self._attr_native_value = self._get_value(state)

    async def async_set_native_value(self, value: float) -> None:
        await self._set_value(int(value))
