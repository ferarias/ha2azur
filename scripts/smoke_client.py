#!/usr/bin/env python3
"""Exercise custom_components/azur640r/client.py directly against the real
Azur 640R, without any Home Assistant involved. Cheapest possible feedback
loop for changes to the protocol/transport client.

Examples:
    python scripts/smoke_client.py 1,01,1 --host 192.168.10.102 --key-file .secret
    python scripts/smoke_client.py -i --host 192.168.10.102 --key-file .secret
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "azur640r"))

from client import (  # noqa: E402
    AzurClient,
    AzurError,
    DEFAULT_PORT_NAME,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", help="raw command as group,number[,data] e.g. 1,02")
    parser.add_argument("--host", required=True, help="AUX-2 hostname or IP")
    parser.add_argument("--port-name", default=DEFAULT_PORT_NAME, help=f"ESPHome serial port name (default {DEFAULT_PORT_NAME!r})")
    parser.add_argument("--key", help="ESPHome API encryption key")
    parser.add_argument("--key-file", help="read the encryption key from this file instead of --key")
    parser.add_argument("-i", "--interactive", action="store_true", help="read commands from stdin until EOF/quit")
    parser.add_argument("--timeout", type=float, default=3.0, help="reply timeout in seconds (default 3)")
    args = parser.parse_args()

    if not args.command and not args.interactive:
        parser.error("provide a command or use -i for interactive mode")

    key = args.key
    if key is None and args.key_file:
        key = Path(args.key_file).read_text(encoding="utf-8").strip()

    client = AzurClient(args.host, port_name=args.port_name, key=key)
    await client.connect()

    try:
        if args.interactive:
            print(f"Connected to {args.host} ({args.port_name}). Enter raw commands like '1,02' (empty line or 'quit' to exit).")
            loop = asyncio.get_event_loop()
            while True:
                line = await loop.run_in_executor(None, input, "> ")
                command = line.strip()
                if not command or command.lower() == "quit":
                    break
                try:
                    print(await client.async_send_command(command, timeout=args.timeout))
                except AzurError as exc:
                    print(f"(failed: {exc})")
        else:
            try:
                print(await client.async_send_command(args.command, timeout=args.timeout))
            except AzurError as exc:
                print(f"(failed: {exc})")
                return 1
    finally:
        await client.disconnect()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
