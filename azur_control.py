#!/usr/bin/env python3
"""Send Azur 640R serial-control commands over the USR-TCP232-302 Ethernet bridge.

The USR-TCP232-302 is configured as a transparent TCP Server, so this script
just opens a plain TCP socket to it; every byte sent/received passes straight
through to the receiver's RS-232 port (9600 baud, 8N1, no handshaking).

Command format (Azur 640R Serial Control Protocol V1.13):
    #<group>,<number>[,<data>]<CR>

Examples:
    python azur_control.py 1,01,1        # power on
    python azur_control.py 1,02          # volume up
    python azur_control.py 2,01,07       # select CD input
    python azur_control.py -i            # interactive mode

See parameters.md for this adapter's actual configuration (local port, etc).
"""
import argparse
import socket
import sys

DEFAULT_HOST = "192.168.10.149"
DEFAULT_PORT = 4001  # must match the adapter's "Local Port Number" in TCP Server mode (see parameters.md)


def send_command(sock: socket.socket, command: str) -> str:
    """Send one command (without the leading '#' or trailing CR) and return the reply."""
    payload = f"#{command}\r".encode("ascii")
    sock.sendall(payload)
    reply = sock.recv(256)
    return reply.decode("ascii", errors="replace").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", help="command as group,number[,data] e.g. 1,02")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"adapter IP (default {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"adapter TCP port (default {DEFAULT_PORT})")
    parser.add_argument("-i", "--interactive", action="store_true", help="read commands from stdin until EOF/quit")
    parser.add_argument("--timeout", type=float, default=3.0, help="socket timeout in seconds (default 3)")
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
                    print(send_command(sock, command))
                except socket.timeout:
                    print("(no reply)")
        else:
            try:
                print(send_command(sock, args.command))
            except socket.timeout:
                print("(no reply)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
