"""Select platform for the Azur 640R integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.select import SelectEntity
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import voluptuous as vol

from .client import (
    AzurClient,
    AzurState,
    ProgramType,
    TunerBand,
    TunerDisplayMode,
    TunerMode,
    VideoSourceType,
)
from .const import DOMAIN, Azur640RConfigEntry

PARALLEL_UPDATES = 1

DYNAMIC_RANGE_TO_HA: dict[int, str] = {
    0: "off",
    1: "quarter",
    2: "half",
    3: "three_quarters",
    4: "full",
}
HA_TO_DYNAMIC_RANGE: dict[str, int] = {v: k for k, v in DYNAMIC_RANGE_TO_HA.items()}

INPUT_MODE_TO_HA: dict[bool, str] = {False: "analogue", True: "digital"}
HA_TO_INPUT_MODE: dict[str, bool] = {v: k for k, v in INPUT_MODE_TO_HA.items()}

TUNER_PRESET_OPTIONS = [str(n) for n in range(1, 16)]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: Azur640RConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Azur 640R select entities from a config entry."""
    client = config_entry.runtime_data
    async_add_entities(
        [
            Azur640RSelect(
                client,
                config_entry,
                translation_key="dynamic_range",
                options=list(DYNAMIC_RANGE_TO_HA.values()),
                get_option=lambda state: (
                    None
                    if state.dynamic_range is None
                    else DYNAMIC_RANGE_TO_HA[state.dynamic_range]
                ),
                set_option=lambda option: client.set_dynamic_range(
                    HA_TO_DYNAMIC_RANGE[option]
                ),
            ),
            Azur640RSelect(
                client,
                config_entry,
                translation_key="input_mode",
                options=list(INPUT_MODE_TO_HA.values()),
                get_option=lambda state: (
                    None
                    if state.input_mode_digital is None
                    else INPUT_MODE_TO_HA[state.input_mode_digital]
                ),
                set_option=lambda option: client.set_input_mode(
                    digital=HA_TO_INPUT_MODE[option]
                ),
            ),
            Azur640RSelect(
                client,
                config_entry,
                translation_key="video_source_type",
                options=[kind.value for kind in VideoSourceType],
                get_option=lambda state: (
                    state.video_source_type.value if state.video_source_type else None
                ),
                set_option=lambda option: client.set_video_source_type(
                    VideoSourceType(option)
                ),
            ),
            Azur640RSelect(
                client,
                config_entry,
                translation_key="tuner_band",
                options=[band.value for band in TunerBand],
                get_option=lambda state: (
                    state.tuner_band.value if state.tuner_band else None
                ),
                set_option=lambda option: client.set_tuner_band(TunerBand(option)),
                refresh_tuner_info=True,
            ),
            Azur640RSelect(
                client,
                config_entry,
                translation_key="tuner_mode",
                options=[mode.value for mode in TunerMode],
                get_option=lambda state: (
                    state.tuner_mode.value if state.tuner_mode else None
                ),
                set_option=lambda option: client.set_tuner_mode(TunerMode(option)),
            ),
            Azur640RSelect(
                client,
                config_entry,
                translation_key="tuner_display_mode",
                options=[mode.value for mode in TunerDisplayMode],
                get_option=lambda state: (
                    state.tuner_display_mode.value if state.tuner_display_mode else None
                ),
                set_option=lambda option: client.set_tuner_display_mode(
                    TunerDisplayMode(option)
                ),
            ),
            Azur640RSelect(
                client,
                config_entry,
                translation_key="tuner_pty_select",
                options=[pty.value for pty in ProgramType],
                get_option=lambda state: (
                    state.tuner_pty_select.value if state.tuner_pty_select else None
                ),
                set_option=lambda option: client.set_tuner_pty_select(
                    ProgramType(option)
                ),
            ),
            Azur640RSelect(
                client,
                config_entry,
                translation_key="tuner_preset",
                options=TUNER_PRESET_OPTIONS,
                get_option=lambda state: None,  # noqa: ARG005 -- no "current preset" query exists
                set_option=lambda option: client.select_tuner_preset(int(option)),
                refresh_tuner_info=True,
            ),
        ]
    )

    # Entity service, targeted at the "Tuner Preset" entity: storing a
    # preset needs its own slot number, separate from (and usually unrelated
    # to) whichever preset that entity last tuned to.
    entity_platform.async_get_current_platform().async_register_entity_service(
        "store_preset",
        {vol.Required("preset"): vol.All(int, vol.Range(min=1, max=15))},
        "async_store_preset",
    )


class Azur640RSelect(SelectEntity):
    """A single-choice amplifier/tuner setting, exposed as an HA select."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True

    def __init__(
        self,
        client: AzurClient,
        config_entry: Azur640RConfigEntry,
        *,
        translation_key: str,
        options: list[str],
        get_option: Callable[[AzurState], str | None],
        set_option: Callable[[str], Awaitable[None]],
        refresh_tuner_info: bool = False,
    ) -> None:
        self._client = client
        self._get_option = get_option
        self._set_option = set_option
        self._refresh_tuner_info = refresh_tuner_info
        self._attr_translation_key = translation_key
        self._attr_options = options
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
        self._attr_current_option = self._get_option(state)

    async def async_select_option(self, option: str) -> None:
        await self._set_option(option)
        if self._refresh_tuner_info:
            self.hass.async_create_background_task(
                self._client.refresh_tuner_info(), f"azur640r_refresh_tuner_{self.unique_id}"
            )

    async def async_store_preset(self, preset: int) -> None:
        """Entity service: store the current frequency into preset `preset`."""
        await self._client.store_tuner_preset(preset)
