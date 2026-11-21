#!/usr/bin/env python3
"""Send Azur 640R serial-control commands over the USR-TCP232-302 Ethernet bridge.

The USR-TCP232-302 is configured as a transparent TCP Server, so this script
just opens a plain TCP socket to it; every byte sent/received passes straight
through to the receiver's RS-232 port (9600 baud, 8N1, no handshaking).

Command format (Azur 640R Serial Control Protocol V1.13):
    #<group>,<number>[,<data>]<CR>

Replies echo back as #<reply_group>,<number>[,<data>]<CR>, where reply_group
is the command group + 5 (so group 1 commands get group 6 replies, etc.),
except group 11 which is always an error reply. The serial line has shown
occasional single-bit corruption, so replies are validated against this
shape and the command is retried on a malformed or unexpected reply.

Examples:
    python azur_control.py 1,01,1        # power on
    python azur_control.py 1,02          # volume up
    python azur_control.py 2,01,07       # select CD input
    python azur_control.py -i            # interactive mode

See parameters.md for this adapter's actual configuration (local port, etc).
"""
import argparse
import re
import socket
import sys
import time

DEFAULT_HOST = "192.168.10.149"
DEFAULT_PORT = 4001  # must match the adapter's "Local Port Number" in TCP Server mode (see parameters.md)
DEFAULT_RETRIES = 3
RETRY_DELAY = 0.3

ERROR_GROUP = 11
REPLY_GROUP_OFFSET = 5
REPLY_RE = re.compile(r"^#(\d{1,2}),")


class ReplyError(Exception):
    """Raised when a reply is malformed or doesn't match the sent command."""


def _read_reply(sock: socket.socket) -> str:
    """Read bytes until a CR terminator (or the socket times out)."""
    buf = bytearray()
    while b"\r" not in buf:
        chunk = sock.recv(256)
        if not chunk:
            break
        buf.extend(chunk)
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


def send_command(sock: socket.socket, command: str, retries: int = DEFAULT_RETRIES) -> str:
    """Send one command (without the leading '#' or trailing CR), validate, and return the reply.

    Retries on a timeout, malformed reply, or reply that doesn't match the command sent.
    Raises the last error if every attempt fails.
    """
    payload = f"#{command}\r".encode("ascii")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        sock.sendall(payload)
        try:
            reply = _read_reply(sock)
            if not reply:
                raise ReplyError("empty reply")
            _validate_reply(command, reply)
            return reply
        except (socket.timeout, ReplyError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(RETRY_DELAY)

    raise last_error if last_error is not None else ReplyError("no reply")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", help="command as group,number[,data] e.g. 1,02")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"adapter IP (default {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"adapter TCP port (default {DEFAULT_PORT})")
    parser.add_argument("-i", "--interactive", action="store_true", help="read commands from stdin until EOF/quit")
    parser.add_argument("--timeout", type=float, default=3.0, help="socket timeout in seconds (default 3)")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help=f"attempts per command (default {DEFAULT_RETRIES})")
    args = parser.parse_args()

    if not args.command and not args.interactive:
        parser.error("provide a command or use -i for interactive mode")

    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sock.settimeout(args.timeout)
        if args.interactive:
            print(f"Connected to {args.host}:{args.port}. Enter commands like '1,02' (empty line or 'quit' to exit).")
            for line in sys.stdin:
                command = line.strip()
                if not command or command.lower() == "quit":
                    break
                try:
                    print(send_command(sock, command, retries=args.retries))
                except (socket.timeout, ReplyError) as exc:
                    print(f"(failed after {args.retries} attempt(s): {exc})")
        else:
            try:
                print(send_command(sock, args.command, retries=args.retries))
            except (socket.timeout, ReplyError) as exc:
                print(f"(failed after {args.retries} attempt(s): {exc})")
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
