# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project goal

Connect to and control a Cambridge Audio Azur 640R AV receiver over its RS-232 serial port, via a USR-TCP232-302 serial-to-Ethernet adapter, so the receiver can be integrated with a home automation system (per the repo name, `ha2azur` — likely Home Assistant).

## Current state

This repository currently holds no source code — only planning notes and reference documentation. There is no build, lint, or test tooling yet. When implementation starts, update this file with the actual commands and architecture.

## Reference documentation layout

- `PLAN.md` — one-paragraph statement of project intent.
- `azur640r/` — Cambridge Audio documentation for the receiver itself (user manual, including its RS-232 command set/protocol).
- `pusr/` — documentation for the PUSR USR-TCP232-302 serial-to-Ethernet adapter (datasheet, spec, quick start, user manual) that bridges the receiver's RS-232 port to the network.

Before implementing serial communication with the receiver, consult `azur640r/azur_640r.pdf` and the user manual for the RS-232 command protocol, and the `pusr/` manuals for how the adapter exposes the serial port over TCP/IP (default port, baud rate configuration, transparent transmission mode, etc.).
