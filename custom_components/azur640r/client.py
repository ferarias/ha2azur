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


def _clean_mode(data: str | None) -> str | None:
    text = (data or "").strip()
    if not text or text.upper() == "MODE UNAVAILABLE":
        return None
    return text


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

        retries = IDEMPOTENT_RETRIES if idempotent else 1
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
