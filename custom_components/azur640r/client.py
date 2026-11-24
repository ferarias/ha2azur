"""Async client for a Cambridge Audio Azur 640R reached via a Home Assistant
Connect AUX-2's ESPHome native API serial passthrough.

No ``homeassistant`` imports on purpose: this module is usable standalone
(see ``scripts/smoke_client.py``) and testable without a Home Assistant
installation.

Protocol: Azur 640R Serial Control Protocol V1.13.
    #<group>,<number>[,<data>]<CR>
Replies echo back as #<reply_group>,<number>[,<data>]<CR>, where reply_group
is the command group + 5, except group 11 which is a fixed error-reply group
with no correlation to the command that triggered it.

Group 2's "Input Select" command and its group-7 reply use *different*
numeric codes for the same source (Tuner is command-code 00 but reply-code
9, and every other source shifts by one) -- modelled below as two separate
lookup tables, never derived from one another.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import aioesphomeapi
import serialx

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT_NAME = "RS-232 Port 1"
DEFAULT_ESPHOME_PORT = 6053

ERROR_GROUP = 11
REPLY_GROUP_OFFSET = 5

DEFAULT_TIMEOUT = 3.0
IDEMPOTENT_RETRIES = 8
RETRY_DELAY = 0.3

REPLY_RE = re.compile(r"^#(\d{1,2}),(\d{1,2})(?:,(.*))?$")

# Commands whose reply data has a known fixed shape, keyed by "group,number"
# exactly as sent. Anything not listed here accepts any data (free text,
# dynamic enumerations, etc).
FIXED_DATA_PATTERNS: dict[str, re.Pattern[str]] = {
    "1,01": re.compile(r"[01]"),          # power: 0=standby, 1=on
    "1,11": re.compile(r"0?[01]"),        # mute: 0/00=off, 1/01=on
    "1,02": re.compile(r"-?\d{1,2}"),     # volume up -> resulting dB
    "1,03": re.compile(r"-?\d{1,2}"),     # volume down -> resulting dB
    "1,04": re.compile(r"-?\d{1,2}"),     # bass up -> resulting dB
    "1,05": re.compile(r"-?\d{1,2}"),     # bass down -> resulting dB
    "1,06": re.compile(r"-?\d{1,2}"),     # treble up -> resulting dB
    "1,07": re.compile(r"-?\d{1,2}"),     # treble down -> resulting dB
    "1,10": re.compile(r"\d{1,2}"),       # LFE trim: 0..10 (magnitude of -dB)
    "1,12": re.compile(r"0?[0-4]"),        # dynamic range: 0..4
    "2,04": re.compile(r"0?[01]"),        # input mode: 0=analogue, 1=digital
    "2,05": re.compile(r"0?[0-2]"),        # video source: 0=S-Video,1=Component,2=Composite
    "3,01": re.compile(r"0?[01]"),        # tuner stereo/mono
    "3,06": re.compile(r"0?[1-3]"),        # tuner mode
    "3,09": re.compile(r"0?[01]"),        # tuner band: 0=FM, 1=AM
    "3,10": re.compile(r"\d{1,2}"),       # tuner PTY select: 1..15
    "3,13": re.compile(r"0?[1-5]"),       # tuner display mode: 1..5
    "3,16": re.compile(r"\d{1,2}"),       # tuner current PTY: 0..15
    "4,01": re.compile(r"0?[01]"),        # stereo (+SW)
}


class AzurError(Exception):
    """Base error for this client."""


class AzurConnectionError(AzurError):
    """Raised on a transport-level failure (connect, disconnect mid-command)."""


class AzurAuthError(AzurConnectionError):
    """Raised when the ESPHome API encryption key is wrong or missing.

    Verified against real hardware: a wrong key raises aioesphomeapi's
    InvalidEncryptionKeyAPIError/InvalidAuthAPIError with a message like
    "Invalid encryption key: received_name=..., received_mac=..." -- device
    identity metadata, never the key itself.
    """


class AzurProtocolError(AzurError):
    """Raised when a reply is malformed, or doesn't match the command sent."""


class AzurDeviceError(AzurProtocolError):
    """Raised when the device itself rejected the command (group 11 reply)."""


class InputSource(Enum):
    """Selectable Azur 640R input sources.

    Command code 09 ("####"/reserved in the protocol doc) has no member here
    and must never be offered as selectable.
    """

    TUNER = "tuner"
    DVD = "dvd"
    VIDEO1 = "video1"
    VIDEO2 = "video2"
    VIDEO3 = "video3"
    REC1 = "rec1"
    AUX = "aux"
    CD = "cd"
    REC2 = "rec2"
    DIRECT_7_1 = "direct_7_1"


# Group 2, command 01 "Input Select": command-code -> InputSource.
SOURCE_COMMAND_CODE: dict[str, InputSource] = {
    "00": InputSource.TUNER,
    "01": InputSource.DVD,
    "02": InputSource.VIDEO1,
    "03": InputSource.VIDEO2,
    "04": InputSource.VIDEO3,
    "05": InputSource.REC1,
    "06": InputSource.AUX,
    "07": InputSource.CD,
    "08": InputSource.REC2,
    "10": InputSource.DIRECT_7_1,
}

# Group 7, reply to command 01: reply-code -> InputSource. Deliberately a
# SEPARATE table -- Tuner moves from command-code 00 to reply-code 9, and
# every other source shifts by one. Do not try to derive one from the other.
SOURCE_REPLY_CODE: dict[str, InputSource] = {
    "1": InputSource.DVD,
    "2": InputSource.VIDEO1,
    "3": InputSource.VIDEO2,
    "4": InputSource.VIDEO3,
    "5": InputSource.REC1,
    "6": InputSource.AUX,
    "7": InputSource.CD,
    "8": InputSource.REC2,
    "9": InputSource.TUNER,
    "10": InputSource.DIRECT_7_1,
}

SOURCE_TO_COMMAND_CODE: dict[InputSource, str] = {
    v: k for k, v in SOURCE_COMMAND_CODE.items()
}


class VideoSourceType(Enum):
    """Group 2, command 05 "Set Video Source"."""

    S_VIDEO = "s_video"
    COMPONENT = "component"
    COMPOSITE = "composite"


VIDEO_SOURCE_TYPE_CODE: dict[int, VideoSourceType] = {
    0: VideoSourceType.S_VIDEO,
    1: VideoSourceType.COMPONENT,
    2: VideoSourceType.COMPOSITE,
}
VIDEO_SOURCE_TYPE_TO_CODE: dict[VideoSourceType, int] = {
    v: k for k, v in VIDEO_SOURCE_TYPE_CODE.items()
}


class TunerBand(Enum):
    """Group 3, command 09 "Tuner Band"."""

    FM = "fm"
    AM = "am"


TUNER_BAND_CODE: dict[int, TunerBand] = {0: TunerBand.FM, 1: TunerBand.AM}
TUNER_BAND_TO_CODE: dict[TunerBand, int] = {v: k for k, v in TUNER_BAND_CODE.items()}


class TunerMode(Enum):
    """Group 3, command 06 "Tuner Mode" -- what commands 04/05 ("Up"/"Down") do."""

    FREQUENCY = "frequency"
    SEARCH = "search"
    PRESET = "preset"


TUNER_MODE_CODE: dict[int, TunerMode] = {
    1: TunerMode.FREQUENCY,
    2: TunerMode.SEARCH,
    3: TunerMode.PRESET,
}
TUNER_MODE_TO_CODE: dict[TunerMode, int] = {v: k for k, v in TUNER_MODE_CODE.items()}


class TunerDisplayMode(Enum):
    """Group 3, command 13 "Tuner Display mode"."""

    FREQUENCY = "frequency"
    PROGRAM_NAME = "program_name"
    PROGRAM_TYPE = "program_type"
    CLOCK_TIME = "clock_time"
    RADIOTEXT = "radiotext"


TUNER_DISPLAY_MODE_CODE: dict[int, TunerDisplayMode] = {
    1: TunerDisplayMode.FREQUENCY,
    2: TunerDisplayMode.PROGRAM_NAME,
    3: TunerDisplayMode.PROGRAM_TYPE,
    4: TunerDisplayMode.CLOCK_TIME,
    5: TunerDisplayMode.RADIOTEXT,
}
TUNER_DISPLAY_MODE_TO_CODE: dict[TunerDisplayMode, int] = {
    v: k for k, v in TUNER_DISPLAY_MODE_CODE.items()
}


class ProgramType(Enum):
    """RDS Program Type (PTY), shared by the "select a PTY to search for"
    (group 3, command 10; codes 1-15) and "get the currently playing
    program's PTY" (group 8, command 16; codes 0-15, 0 = no PTY) commands."""

    NEWS = "news"
    AFFAIRS = "affairs"
    INFO = "info"
    SPORT = "sport"
    EDUCATE = "educate"
    DRAMA = "drama"
    CULTURE = "culture"
    SCIENCE = "science"
    VARIED = "varied"
    POP = "pop"
    ROCK = "rock"
    MOR = "mor"
    LIGHT = "light"
    CLASSICS = "classics"
    OTHER = "other"


# Codes 1-15 are shared by both the "select" and "current" commands; code 0
# ("No PTY") only ever appears in a "current PTY" reply, never selectable.
PROGRAM_TYPE_CODE: dict[int, ProgramType] = {
    1: ProgramType.NEWS,
    2: ProgramType.AFFAIRS,
    3: ProgramType.INFO,
    4: ProgramType.SPORT,
    5: ProgramType.EDUCATE,
    6: ProgramType.DRAMA,
    7: ProgramType.CULTURE,
    8: ProgramType.SCIENCE,
    9: ProgramType.VARIED,
    10: ProgramType.POP,
    11: ProgramType.ROCK,
    12: ProgramType.MOR,
    13: ProgramType.LIGHT,
    14: ProgramType.CLASSICS,
    15: ProgramType.OTHER,
}
PROGRAM_TYPE_TO_CODE: dict[ProgramType, int] = {
    v: k for k, v in PROGRAM_TYPE_CODE.items()
}


@dataclass
class AzurState:
    """Last known receiver state. Every field starts unknown and is only
    ever set from a validated reply -- never guessed/synthesized, since the
    protocol is strictly command/reply with no unsolicited push."""

    power: bool | None = None
    volume_db: int | None = None  # -90 (mute) .. 0 (max); only known after a step
    muted: bool | None = None
    source: InputSource | None = None
    surround_mode: str | None = None
    dd_dts_mode: str | None = None
    sw_version: str | None = None
    protocol_version: str | None = None

    # Amplifier (group 1)
    bass_db: int | None = None  # -10..10; only known after a step
    treble_db: int | None = None  # -10..10; only known after a step
    sub_on: bool | None = None  # assumed-state: reply carries no data
    lfe_trim_db: int | None = None  # -10..0
    dynamic_range: int | None = None  # 0..4 (quarters, 0=off, 4=full)

    # Source (group 2)
    input_mode_digital: bool | None = None
    video_source_type: VideoSourceType | None = None

    # Audio processing (group 4)
    stereo_plus_sw: bool | None = None

    # Tuner (group 3)
    tuner_mono: bool | None = None
    tuner_band: TunerBand | None = None
    tuner_mode: TunerMode | None = None
    tuner_pty_select: ProgramType | None = None
    tuner_display_mode: TunerDisplayMode | None = None
    tuner_frequency: str | None = None  # "xxx.xx" MHz/kHz, as echoed by the device
    tuner_station_name: str | None = None
    tuner_pty_current: ProgramType | None = None  # None also means "no PTY"


def _clean_mode(data: str | None) -> str | None:
    text = (data or "").strip()
    if not text or text.upper() == "MODE UNAVAILABLE":
        return None
    return text


def _code_lookup(table: dict[int, Any], raw: str | None) -> Any | None:
    """Look up a reply's numeric code in an int-keyed table. Handles the
    protocol's inconsistent zero-padding (e.g. "2" and "02" both mean 2)."""
    text = (raw or "").strip()
    if not text.isdigit():
        return None
    return table.get(int(text))


def _format_frequency(raw: str | None) -> str | None:
    """The device echoes frequency as plain digits with an implied 2-digit
    decimal part (e.g. "09525" -> "95.25" MHz) -- never a literal '.'."""
    digits = (raw or "").strip()
    if not digits.isdigit():
        return digits or None
    whole, frac = digits[:-2].lstrip("0") or "0", digits[-2:].rjust(2, "0")
    return f"{whole}.{frac}"


class AzurClient:
    """Talks to the Azur 640R over the AUX-2's ESPHome serial passthrough."""

    def __init__(
        self,
        host: str,
        *,
        port_name: str = DEFAULT_PORT_NAME,
        key: str | None = None,
        esphome_port: int = DEFAULT_ESPHOME_PORT,
    ) -> None:
        self._host = host
        self._port_name = port_name
        self._key = key or None
        self._esphome_port = esphome_port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._state = AzurState()
        self._connected = False
        self._listeners: list[Callable[[AzurState | None], None]] = []

    @property
    def state(self) -> AzurState:
        return self._state

    @property
    def connected(self) -> bool:
        return self._connected

    def subscribe(self, callback: Callable[[AzurState | None], None]) -> Callable[[], None]:
        """Register a callback for state changes (``None`` means disconnected)."""
        self._listeners.append(callback)

        def _unsubscribe() -> None:
            self._listeners.remove(callback)

        return _unsubscribe

    def _notify(self, state: AzurState | None) -> None:
        for callback in list(self._listeners):
            try:
                callback(state)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unhandled error in Azur 640R state listener")

    async def connect(self) -> None:
        """Open the ESPHome serial passthrough. Never includes the raw
        underlying exception text in the raised error -- it could embed the
        encryption key -- only the host/port name we already know."""
        url = f"esphome://{self._host}:{self._esphome_port}/?port_name={self._port_name.replace(' ', '+')}"
        options: dict[str, Any] = {}
        if self._key:
            options["key"] = self._key

        try:
            self._reader, self._writer = await serialx.open_serial_connection(
                url=url,
                baudrate=9600,
                bytesize=8,
                parity="N",
                stopbits=1,
                **options,
            )
        except Exception as exc:  # noqa: BLE001
            # serialx wraps esphome/aioesphomeapi errors in its own SerialException,
            # with the real error (if any) as __cause__ -- verified against real
            # hardware that a wrong key surfaces here as InvalidEncryptionKeyAPIError
            # / InvalidAuthAPIError.
            cause = exc.__cause__ or exc
            _LOGGER.debug("Connect to %s failed: %s", self._host, type(cause).__name__)
            if isinstance(cause, (aioesphomeapi.InvalidEncryptionKeyAPIError, aioesphomeapi.InvalidAuthAPIError)):
                raise AzurAuthError(f"Invalid ESPHome API key for {self._host}") from None
            raise AzurConnectionError(f"Error connecting to {self._host}") from None

        self._connected = True

    async def disconnect(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        self._reader = None
        self._writer = None
        was_connected = self._connected
        self._connected = False
        if was_connected:
            self._notify(None)

    async def _handle_disconnect(self) -> None:
        if self._writer is not None:
            self._writer.close()
        self._reader = None
        self._writer = None
        self._connected = False
        self._notify(None)

    async def _drain_stale(self) -> None:
        """Discard any bytes left over from a previous malformed/late reply
        so the next read can't be confused by stale data."""
        assert self._reader is not None
        while True:
            try:
                chunk = await asyncio.wait_for(self._reader.read(256), 0.01)
            except TimeoutError:
                return
            if not chunk:
                return

    async def _read_reply(self) -> str:
        assert self._reader is not None
        buf = await self._reader.readuntil(b"\r")
        return buf.decode("ascii", errors="replace").strip()

    @staticmethod
    def _validate_reply(
        expected_group: int,
        data_pattern: re.Pattern[str] | None,
        reply: str,
    ) -> None:
        match = REPLY_RE.match(reply)
        if not match:
            raise AzurProtocolError(f"malformed reply: {reply!r}")

        reply_group = int(match.group(1))
        data = match.group(3)

        if reply_group == ERROR_GROUP:
            raise AzurDeviceError(f"device rejected command: {reply!r}")
        if reply_group != expected_group:
            raise AzurProtocolError(
                f"expected reply group {expected_group}, got {reply_group}: {reply!r}"
            )
        # Deliberately NOT validating reply_number against command_number: verified
        # against real hardware that "Get current DD/DTS mode" (4,05) consistently
        # replies with reply-number 03 (the DD/DTS cycle command's own number), not
        # 05 as the protocol doc implies -- a real firmware quirk, not line noise
        # (it was reproducible across all retry attempts). Group + data-shape
        # validation below is enough to reject stale/corrupted replies.
        if data_pattern is not None and not data_pattern.fullmatch((data or "").strip()):
            raise AzurProtocolError(f"unexpected reply data: {reply!r}")

    async def async_send_command(
        self,
        command: str,
        *,
        idempotent: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str:
        """Send one "group,number[,data]" command and return the validated
        reply (without the leading '#' or trailing CR already stripped off).

        Idempotent commands (power, mute, source select, queries) are safe
        to retry blindly on a timeout or a malformed/mismatched reply.
        Non-idempotent commands (volume up/down) are only retried when the
        device itself explicitly rejected the command (a group-11 reply) --
        any ambiguous timeout or malformed reply is raised immediately
        instead of risking a blind retry double-stepping the volume.
        """
        if self._reader is None or self._writer is None or not self._connected:
            raise AzurConnectionError(f"not connected to {self._host}")

        parts = command.split(",")
        command_group = int(parts[0])
        command_number = parts[1]
        expected_group = command_group + REPLY_GROUP_OFFSET
        data_pattern = FIXED_DATA_PATTERNS.get(f"{parts[0]},{command_number}")
        payload = f"#{command}\r".encode("ascii")

        # Non-idempotent commands still get a few attempts -- but only an
        # explicit group-11 rejection carries on to a retry (the
        # AzurDeviceError branch below never `break`s); an ambiguous
        # timeout/malformed reply still aborts immediately via that branch's
        # own `if not idempotent: break`.
        retries = IDEMPOTENT_RETRIES if idempotent else 3
        last_error: Exception | None = None

        async with self._lock:
            for attempt in range(1, retries + 1):
                await self._drain_stale()
                self._writer.write(payload)
                await self._writer.drain()

                try:
                    reply = await asyncio.wait_for(self._read_reply(), timeout)
                    self._validate_reply(expected_group, data_pattern, reply)
                except AzurDeviceError as exc:
                    last_error = exc
                except (TimeoutError, AzurProtocolError, asyncio.LimitOverrunError) as exc:
                    last_error = exc
                    if not idempotent:
                        break
                except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
                    await self._handle_disconnect()
                    raise AzurConnectionError(f"connection to {self._host} lost") from None
                else:
                    return reply

                if attempt < retries:
                    await asyncio.sleep(RETRY_DELAY)

        assert last_error is not None
        raise last_error

    async def _send(
        self,
        command: str,
        *,
        idempotent: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str | None:
        reply = await self.async_send_command(command, idempotent=idempotent, timeout=timeout)
        match = REPLY_RE.match(reply)
        assert match is not None  # already validated by async_send_command
        return match.group(3)

    async def power_on(self) -> None:
        data = await self._send("1,01,1")
        self._state.power = (data or "").strip().endswith("1")
        self._notify(self._state)

    async def power_standby(self) -> None:
        data = await self._send("1,01,0")
        self._state.power = (data or "").strip().endswith("1")
        self._notify(self._state)

    async def volume_up(self) -> None:
        data = await self._send("1,02", idempotent=False)
        self._state.volume_db = int((data or "").strip())
        self._notify(self._state)

    async def volume_down(self) -> None:
        data = await self._send("1,03", idempotent=False)
        self._state.volume_db = int((data or "").strip())
        self._notify(self._state)

    async def mute_on(self) -> None:
        data = await self._send("1,11,01")
        self._state.muted = (data or "").strip().endswith("1")
        self._notify(self._state)

    async def mute_off(self) -> None:
        data = await self._send("1,11,00")
        self._state.muted = (data or "").strip().endswith("1")
        self._notify(self._state)

    async def select_source(self, source: InputSource) -> None:
        command_code = SOURCE_TO_COMMAND_CODE[source]
        data = await self._send(f"2,01,{command_code}")
        reply_source = SOURCE_REPLY_CODE.get((data or "").strip())
        self._state.source = reply_source if reply_source is not None else source
        self._notify(self._state)

    async def get_software_version(self) -> str | None:
        data = await self._send("5,01")
        version = (data or "").strip() or None
        self._state.sw_version = version
        self._notify(self._state)
        return version

    async def get_surround_mode(self) -> str | None:
        data = await self._send("4,04")
        mode = _clean_mode(data)
        self._state.surround_mode = mode
        self._notify(self._state)
        return mode

    async def get_dd_dts_mode(self) -> str | None:
        data = await self._send("4,05")
        mode = _clean_mode(data)
        self._state.dd_dts_mode = mode
        self._notify(self._state)
        return mode

    async def get_protocol_version(self) -> str | None:
        data = await self._send("5,02")
        version = (data or "").strip() or None
        self._state.protocol_version = version
        self._notify(self._state)
        return version

    # -- Group 1: remaining Amplifier commands ------------------------------

    async def bass_up(self) -> None:
        data = await self._send("1,04", idempotent=False)
        self._state.bass_db = int((data or "").strip())
        self._notify(self._state)

    async def bass_down(self) -> None:
        data = await self._send("1,05", idempotent=False)
        self._state.bass_db = int((data or "").strip())
        self._notify(self._state)

    async def set_bass(self, target_db: int) -> None:
        """Emulate an absolute set: the protocol only has step up/down, but
        each step reply echoes the resulting dB, so this walks toward the
        target one step at a time and stops early if a step doesn't move
        (the device clamped at its -10/10 limit)."""
        target_db = max(-10, min(10, target_db))
        while self._state.bass_db != target_db:
            before = self._state.bass_db
            if before is not None and target_db > before:
                await self.bass_up()
            else:
                await self.bass_down()
            if self._state.bass_db == before:
                break

    async def treble_up(self) -> None:
        data = await self._send("1,06", idempotent=False)
        self._state.treble_db = int((data or "").strip())
        self._notify(self._state)

    async def treble_down(self) -> None:
        data = await self._send("1,07", idempotent=False)
        self._state.treble_db = int((data or "").strip())
        self._notify(self._state)

    async def set_treble(self, target_db: int) -> None:
        """Same step-walking emulation as `set_bass`."""
        target_db = max(-10, min(10, target_db))
        while self._state.treble_db != target_db:
            before = self._state.treble_db
            if before is not None and target_db > before:
                await self.treble_up()
            else:
                await self.treble_down()
            if self._state.treble_db == before:
                break

    async def sub_on(self) -> None:
        await self._send("1,08")
        self._state.sub_on = True
        self._notify(self._state)

    async def sub_off(self) -> None:
        await self._send("1,09")
        self._state.sub_on = False
        self._notify(self._state)

    async def set_lfe_trim(self, trim_db: int) -> None:
        """`trim_db` is -10..0; the protocol encodes it as a 0..10 magnitude."""
        magnitude = abs(max(-10, min(0, trim_db)))
        data = await self._send(f"1,10,{magnitude:02d}")
        self._state.lfe_trim_db = -int((data or "0").strip())
        self._notify(self._state)

    async def set_dynamic_range(self, level: int) -> None:
        """`level` is 0..4 (quarters: 0=off/full range, 4=full compression)."""
        level = max(0, min(4, level))
        data = await self._send(f"1,12,{level:02d}")
        self._state.dynamic_range = int((data or "0").strip())
        self._notify(self._state)

    async def osd_on(self) -> None:
        await self._send("1,13")

    async def osd_off(self) -> None:
        await self._send("1,14")

    async def osd_up(self) -> None:
        await self._send("1,15", idempotent=False)

    async def osd_down(self) -> None:
        await self._send("1,16", idempotent=False)

    async def osd_left(self) -> None:
        await self._send("1,17", idempotent=False)

    async def osd_right(self) -> None:
        await self._send("1,18", idempotent=False)

    async def osd_enter(self) -> None:
        await self._send("1,19", idempotent=False)

    # -- Group 2: remaining Source commands ----------------------------------

    async def input_select_up(self) -> None:
        """No reply data -- unlike `select_source`, this cannot update
        `state.source`, which is left stale after this call."""
        await self._send("2,02", idempotent=False)

    async def input_select_down(self) -> None:
        await self._send("2,03", idempotent=False)

    async def set_input_mode(self, *, digital: bool) -> None:
        data = await self._send(f"2,04,{'01' if digital else '00'}")
        self._state.input_mode_digital = (data or "").strip().endswith("1")
        self._notify(self._state)

    async def set_video_source_type(self, kind: VideoSourceType) -> None:
        data = await self._send(f"2,05,{VIDEO_SOURCE_TYPE_TO_CODE[kind]:02d}")
        self._state.video_source_type = _code_lookup(VIDEO_SOURCE_TYPE_CODE, data)
        self._notify(self._state)

    # -- Group 4: remaining Audio Processing commands ------------------------

    async def set_stereo_plus_sw(self, *, enabled: bool) -> None:
        data = await self._send(f"4,01,{'01' if enabled else '00'}")
        self._state.stereo_plus_sw = (data or "").strip().endswith("1")
        self._notify(self._state)

    async def cycle_surround_mode(self) -> None:
        data = await self._send("4,02", idempotent=False)
        self._state.surround_mode = _clean_mode(data)
        self._notify(self._state)

    async def cycle_dd_dts_mode(self) -> None:
        data = await self._send("4,03", idempotent=False)
        self._state.dd_dts_mode = _clean_mode(data)
        self._notify(self._state)

    # -- Group 3: Tuner commands ---------------------------------------------

    async def set_tuner_mono(self, *, mono: bool) -> None:
        data = await self._send(f"3,01,{'01' if mono else '00'}")
        self._state.tuner_mono = (data or "").strip().endswith("1")
        self._notify(self._state)

    async def tuner_frequency_up(self) -> None:
        await self._send("3,02", idempotent=False)

    async def tuner_frequency_down(self) -> None:
        await self._send("3,03", idempotent=False)

    async def tuner_up(self) -> None:
        """Behavior depends on the current `tuner_mode` (frequency step,
        search, or preset step)."""
        await self._send("3,04", idempotent=False)

    async def tuner_down(self) -> None:
        await self._send("3,05", idempotent=False)

    async def set_tuner_mode(self, mode: TunerMode) -> None:
        data = await self._send(f"3,06,{TUNER_MODE_TO_CODE[mode]:02d}")
        self._state.tuner_mode = _code_lookup(TUNER_MODE_CODE, data)
        self._notify(self._state)

    async def tuner_search_stop(self) -> str | None:
        """Reply carries the frequency the search stopped on."""
        data = await self._send("3,07")
        frequency = _format_frequency(data) if data else None
        self._state.tuner_frequency = frequency
        self._notify(self._state)
        return frequency

    async def tuner_auto_search(self) -> None:
        await self._send("3,08", idempotent=False)

    async def set_tuner_band(self, band: TunerBand) -> None:
        data = await self._send(f"3,09,{TUNER_BAND_TO_CODE[band]:02d}")
        self._state.tuner_band = _code_lookup(TUNER_BAND_CODE, data)
        self._notify(self._state)

    async def set_tuner_pty_select(self, pty: ProgramType) -> None:
        data = await self._send(f"3,10,{PROGRAM_TYPE_TO_CODE[pty]:02d}")
        self._state.tuner_pty_select = _code_lookup(PROGRAM_TYPE_CODE, data)
        self._notify(self._state)

    async def store_tuner_preset(self, preset: int) -> None:
        """Store the current frequency into preset slot `preset` (1-15)."""
        await self._send(f"3,11,{preset:02d}")

    async def select_tuner_preset(self, preset: int) -> None:
        """Tune to preset slot `preset` (1-15). Named "Get Preset" in the
        protocol doc, but it's an action ("tune to"), not a query."""
        await self._send(f"3,12,{preset:02d}")

    async def set_tuner_display_mode(self, mode: TunerDisplayMode) -> None:
        data = await self._send(f"3,13,{TUNER_DISPLAY_MODE_TO_CODE[mode]:02d}")
        self._state.tuner_display_mode = _code_lookup(TUNER_DISPLAY_MODE_CODE, data)
        self._notify(self._state)

    async def get_tuner_frequency(self) -> str | None:
        data = await self._send("3,14")
        frequency = _format_frequency(data) if data else None
        self._state.tuner_frequency = frequency
        self._notify(self._state)
        return frequency

    async def get_tuner_station_name(self) -> str | None:
        raw = await self._send("3,15")
        data = (raw or "").strip()
        name = None if not data or set(data) == {"*"} else data
        self._state.tuner_station_name = name
        self._notify(self._state)
        return name

    async def get_tuner_pty(self) -> ProgramType | None:
        data = await self._send("3,16")
        pty = _code_lookup(PROGRAM_TYPE_CODE, data)  # 0 -> None (no PTY)
        self._state.tuner_pty_current = pty
        self._notify(self._state)
        return pty

    async def tuner_stop_pty_select(self) -> None:
        await self._send("3,17")

    async def refresh_tuner_info(self) -> None:
        """Best-effort refresh of the three read-only tuner queries (there's
        no push for them, so something has to actively re-query after a
        band/frequency/preset change). Each query is independent -- one
        failing (e.g. a query sent mid-search) must not stop the others."""
        for query in (self.get_tuner_frequency, self.get_tuner_station_name, self.get_tuner_pty):
            try:
                await query()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Tuner info refresh: %s failed", query.__name__, exc_info=True)
