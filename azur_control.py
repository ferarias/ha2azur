#!/usr/bin/env python3
"""Send Azur 640R serial-control commands via a Home Assistant Connect AUX-2.

The AUX-2 exposes the receiver's RS-232 port as a serial passthrough over
ESPHome's native API (port 6053). This script opens that passthrough with
serialx and talks the same framing as a local serial port: 9600 baud, 8N1,
no handshaking.

Command format (Azur 640R Serial Control Protocol V1.13):
    #<group>,<number>[,<data>]<CR>

Replies echo back as #<reply_group>,<number>[,<data>]<CR>, where reply_group
is the command group + 5 (so group 1 commands get group 6 replies, etc.),
except group 11 which is always an error reply. The serial line has shown
occasional single-bit corruption, so replies are validated against this
shape and the command is retried on a malformed or unexpected reply.

Examples:
    python azur_control.py 1,01,1 --host aux2.local        # power on
    python azur_control.py 1,02 --host aux2.local          # volume up
    python azur_control.py -i --host aux2.local            # interactive mode
"""
import argparse
import asyncio
import getpass
import re

import serialx

DEFAULT_PORT_NAME = "RS-232 Port 1"
DEFAULT_RETRIES = 8
RETRY_DELAY = 0.3

ERROR_GROUP = 11
REPLY_GROUP_OFFSET = 5
REPLY_RE = re.compile(r"^#(\d{1,2}),")


class ReplyError(Exception):
    """Raised when a reply is malformed or doesn't match the sent command."""


async def _read_reply(reader: asyncio.StreamReader, timeout: float) -> str:
    buf = await asyncio.wait_for(reader.readuntil(b"\r"), timeout)
    return buf.decode("ascii", errors="replace").strip()


def _validate_reply(command: str, reply: str) -> None:
    match = REPLY_RE.match(reply)
    if not match:
        raise ReplyError(f"malformed reply: {reply!r}")

    reply_group = int(match.group(1))
    if reply_group == ERROR_GROUP:
        raise ReplyError(f"device reported an error: {reply!r}")

    command_group = int(command.split(",", 1)[0])
    expected_group = command_group + REPLY_GROUP_OFFSET
    if reply_group != expected_group:
        raise ReplyError(f"expected reply group {expected_group}, got {reply_group}: {reply!r}")


async def send_command(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    command: str,
    timeout: float,
    retries: int = DEFAULT_RETRIES,
) -> str:
    """Send one command (without the leading '#' or trailing CR), validate, and return the reply.

    Retries on a timeout, malformed reply, or reply that doesn't match the command sent.
    Raises the last error if every attempt fails.
    """
    payload = f"#{command}\r".encode("ascii")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        writer.write(payload)
        await writer.drain()
        try:
            reply = await _read_reply(reader, timeout)
            if not reply:
                raise ReplyError("empty reply")
            _validate_reply(command, reply)
            return reply
        except (asyncio.TimeoutError, ReplyError) as exc:
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(RETRY_DELAY)

    raise last_error if last_error is not None else ReplyError("no reply")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", help="command as group,number[,data] e.g. 1,02")
    parser.add_argument("--host", help="AUX-2 hostname or IP (prompted if omitted)")
    parser.add_argument("--port-name", default=DEFAULT_PORT_NAME, help=f"ESPHome serial port name (default {DEFAULT_PORT_NAME!r})")
    parser.add_argument("--key", help="ESPHome API encryption key (prompted if omitted and not --no-key)")
    parser.add_argument("--no-key", action="store_true", help="skip the encryption key prompt (unencrypted API)")
    parser.add_argument("-i", "--interactive", action="store_true", help="read commands from stdin until EOF/quit")
    parser.add_argument("--timeout", type=float, default=3.0, help="reply timeout in seconds (default 3)")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help=f"attempts per command (default {DEFAULT_RETRIES})")
    args = parser.parse_args()

    if not args.command and not args.interactive:
        parser.error("provide a command or use -i for interactive mode")

    host = args.host or input("IP o nombre del AUX-2: ").strip()
    key = args.key
    if key is None and not args.no_key:
        key = getpass.getpass("Clave de cifrado ESPHome (Enter si no utiliza cifrado): ").strip()

    options = {}
    if key:
        options["key"] = key

    url = f"esphome://{host}:6053/?port_name={args.port_name.replace(' ', '+')}"

    reader, writer = await serialx.open_serial_connection(
        url=url,
        baudrate=9600,
        bytesize=8,
        parity="N",
        stopbits=1,
        **options,
    )

    try:
        if args.interactive:
            print(f"Connected to {host} ({args.port_name}). Enter commands like '1,02' (empty line or 'quit' to exit).")
            loop = asyncio.get_event_loop()
            while True:
                line = await loop.run_in_executor(None, input, "> ")
                command = line.strip()
                if not command or command.lower() == "quit":
                    break
                try:
                    print(await send_command(reader, writer, command, args.timeout, retries=args.retries))
                except (asyncio.TimeoutError, ReplyError) as exc:
                    print(f"(failed after {args.retries} attempt(s): {exc})")
        else:
            try:
                print(await send_command(reader, writer, args.command, args.timeout, retries=args.retries))
            except (asyncio.TimeoutError, ReplyError) as exc:
                print(f"(failed after {args.retries} attempt(s): {exc})")
                return 1
    finally:
        writer.close()
        await writer.wait_closed()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
