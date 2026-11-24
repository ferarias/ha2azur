"""Sensor platform for the Azur 640R integration -- read-only values that
are only known after the matching query/action has run at least once (the
protocol has no polling/push, so these start unknown)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
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
    """Set up the Azur 640R sensor entities from a config entry."""
    client = config_entry.runtime_data
    async_add_entities(
        [
            Azur640RSensor(
                client,
                config_entry,
                translation_key="tuner_frequency",
                get_value=lambda state: state.tuner_frequency,
            ),
            Azur640RSensor(
                client,
                config_entry,
                translation_key="tuner_station_name",
                get_value=lambda state: state.tuner_station_name,
            ),
            Azur640RSensor(
                client,
                config_entry,
                translation_key="tuner_pty_current",
                get_value=lambda state: (
                    state.tuner_pty_current.value if state.tuner_pty_current else None
                ),
            ),
            Azur640RSensor(
                client,
                config_entry,
                translation_key="protocol_version",
                get_value=lambda state: state.protocol_version,
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        ]
    )


class Azur640RSensor(SensorEntity):
    """A read-only, push-only (never polled) receiver value."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        client: AzurClient,
        config_entry: Azur640RConfigEntry,
        *,
        translation_key: str,
        get_value: Callable[[AzurState], str | None],
        entity_category: EntityCategory | None = None,
    ) -> None:
        self._client = client
        self._get_value = get_value
        self._attr_translation_key = translation_key
        self._attr_entity_category = entity_category
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
