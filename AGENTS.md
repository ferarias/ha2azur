# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project goal

Connect to and control a Cambridge Audio Azur 640R AV receiver over its RS-232 serial port, so the receiver can be integrated with a home automation system (per the repo name, `ha2azur` — likely Home Assistant).

## Current state

`azur_control.py` sends Azur 640R serial-control-protocol commands and validates/retries on replies. The receiver's RS-232 port is reached via a Home Assistant Connect AUX-2, which exposes it as a serial passthrough over ESPHome's native API (port 6053); the script uses `serialx.open_serial_connection()` with an `esphome://` URL to talk to it, rather than a raw TCP socket.

An earlier iteration of this project used a USR-TCP232-302 serial-to-Ethernet adapter (see `pusr/` below) talked to directly over a plain TCP socket at its configured local port. That approach has been superseded by the AUX-2/ESPHome transport, but the adapter's docs remain for reference since the underlying RS-232 settings (9600 8N1) are unchanged.

## Reference documentation layout

- `PLAN.md` — one-paragraph statement of project intent.
- `azur640r/` — Cambridge Audio documentation for the receiver itself (user manual, including its RS-232 command set/protocol).
- `pusr/` — documentation for the PUSR USR-TCP232-302 serial-to-Ethernet adapter (datasheet, spec, quick start, user manual); kept for reference from the prior transport, not used by the current script.

Before changing the serial command logic, consult `azur640r/azur_640r.pdf` and the user manual for the RS-232 command protocol.
