"""Media player platform for the Azur 640R integration."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import AzurClient, AzurState, InputSource
from .const import DOMAIN, Azur640RConfigEntry

PARALLEL_UPDATES = 1

SOURCE_TO_HA: dict[InputSource, str] = {
    InputSource.TUNER: "tuner",
    InputSource.DVD: "dvd",
    InputSource.VIDEO1: "video1",
    InputSource.VIDEO2: "video2",
    InputSource.VIDEO3: "video3",
    InputSource.REC1: "rec1",
    InputSource.AUX: "aux",
    InputSource.CD: "cd",
    InputSource.REC2: "rec2",
    InputSource.DIRECT_7_1: "direct_7_1",
}
HA_TO_SOURCE: dict[str, InputSource] = {v: k for k, v in SOURCE_TO_HA.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: Azur640RConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Azur 640R media player from a config entry."""
    client = config_entry.runtime_data
    async_add_entities([Azur640RMediaPlayer(client, config_entry)])


class Azur640RMediaPlayer(MediaPlayerEntity):
    """Representation of a Cambridge Audio Azur 640R."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "receiver"
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_source_list = [SOURCE_TO_HA[source] for source in InputSource]
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, client: AzurClient, config_entry: Azur640RConfigEntry) -> None:
        self._client = client
        self._attr_unique_id = config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            manufacturer="Cambridge Audio",
            model="Azur 640R",
            sw_version=client.state.sw_version,
        )
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
        self._attr_state = (
            None
            if state.power is None
            else MediaPlayerState.ON
            if state.power
            else MediaPlayerState.OFF
        )
        self._attr_volume_level = (
            None if state.volume_db is None else (state.volume_db + 90) / 90
        )
        self._attr_is_volume_muted = state.muted
        self._attr_source = SOURCE_TO_HA.get(state.source) if state.source else None
        self._attr_extra_state_attributes = {
            key: value
            for key, value in {
                "surround_mode": state.surround_mode,
                "dd_dts_mode": state.dd_dts_mode,
            }.items()
            if value is not None
        }

    def _async_refresh_modes_in_background(self) -> None:
        """Best-effort, non-blocking refresh of the read-only mode
        attributes. Never runs inline in a service-call path -- a slow or
        failing mode query must never block or fail a user-visible action,
        and there's no polling primitive to refresh these on a timer."""

        async def _refresh() -> None:
            try:
                await self._client.get_surround_mode()
            except Exception:  # noqa: BLE001
                pass
            try:
                await self._client.get_dd_dts_mode()
            except Exception:  # noqa: BLE001
                pass

        self.hass.async_create_background_task(
            _refresh(), f"azur640r_refresh_modes_{self.unique_id}"
        )

    async def async_turn_on(self) -> None:
        await self._client.power_on()
        self._async_refresh_modes_in_background()

    async def async_turn_off(self) -> None:
        await self._client.power_standby()

    async def async_volume_up(self) -> None:
        await self._client.volume_up()

    async def async_volume_down(self) -> None:
        await self._client.volume_down()

    async def async_mute_volume(self, mute: bool) -> None:
        if mute:
            await self._client.mute_on()
        else:
            await self._client.mute_off()

    async def async_select_source(self, source: str) -> None:
        input_source = HA_TO_SOURCE.get(source)
        if input_source is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_source",
                translation_placeholders={"source": source},
            )
        await self._client.select_source(input_source)
        self._async_refresh_modes_in_background()
