"""Button platform for the Azur 640R integration -- one-shot actions that
have no persistent on/off/selected state of their own."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import AzurClient
from .const import DOMAIN, Azur640RConfigEntry

PARALLEL_UPDATES = 1

# These change the tuned frequency/station, so the read-only tuner sensors
# (frequency/station name/PTY) need a best-effort background re-query after
# them -- there's no push, so nothing else will ever refresh them.
_TUNER_STEP_ACTIONS = {
    "tuner_frequency_up",
    "tuner_frequency_down",
    "tuner_up",
    "tuner_down",
    "tuner_search_stop",
    "tuner_auto_search",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: Azur640RConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Azur 640R button entities from a config entry."""
    client = config_entry.runtime_data
    actions: list[tuple[str, Callable[[], Awaitable[None]]]] = [
        ("cycle_surround_mode", client.cycle_surround_mode),
        ("cycle_dd_dts_mode", client.cycle_dd_dts_mode),
        ("input_select_up", client.input_select_up),
        ("input_select_down", client.input_select_down),
        ("tuner_frequency_up", client.tuner_frequency_up),
        ("tuner_frequency_down", client.tuner_frequency_down),
        ("tuner_up", client.tuner_up),
        ("tuner_down", client.tuner_down),
        ("tuner_search_stop", client.tuner_search_stop),
        ("tuner_auto_search", client.tuner_auto_search),
        ("tuner_stop_pty_select", client.tuner_stop_pty_select),
    ]
    async_add_entities(
        Azur640RButton(
            client,
            config_entry,
            translation_key=key,
            action=action,
            refresh_tuner_info=key in _TUNER_STEP_ACTIONS,
        )
        for key, action in actions
    )


class Azur640RButton(ButtonEntity):
    """A single fire-and-forget protocol command."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        client: AzurClient,
        config_entry: Azur640RConfigEntry,
        *,
        translation_key: str,
        action: Callable[[], Awaitable[None]],
        refresh_tuner_info: bool = False,
    ) -> None:
        self._client = client
        self._action = action
        self._refresh_tuner_info = refresh_tuner_info
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{config_entry.entry_id}_{translation_key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, config_entry.entry_id)})

    async def async_press(self) -> None:
        await self._action()
        if self._refresh_tuner_info:
            self.hass.async_create_background_task(
                self._client.refresh_tuner_info(), f"azur640r_refresh_tuner_{self.unique_id}"
            )
