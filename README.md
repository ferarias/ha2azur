# ha2azur

The goal of this project is to integrate a Cambridge Audio Azur 640R AV receiver with Home Assistant by using its RS-232 connector.

The receiver is reached via a Home Assistant Connect AUX-2, which exposes its RS-232 port as a serial passthrough over ESPHome's native API.

## Home Assistant integration

`custom_components/azur640r/` is a HACS-style custom integration providing a `media_player` entity for the receiver.

**Install**: copy (or symlink) `custom_components/azur640r/` into your Home Assistant config's `custom_components/` directory, restart HA, then add the integration from Settings → Devices & Services.

**Config fields**: AUX-2 host/IP, the ESPHome serial port name (defaults to `RS-232 Port 1`), and the ESPHome API encryption key (leave blank if the AUX-2 isn't encrypted).

**Known limitations**:
- No reflection of changes made from the receiver's physical remote or front panel — the protocol is strictly command/reply, with no unsolicited state push.
- No absolute volume set, only relative up/down — the protocol has no "set volume to X dB" command.
- No tuner control (frequency/preset) or OSD menu navigation in this version.
- `surround_mode`/`dd_dts_mode` attributes are refreshed in the background after power-on/source-select and can lag briefly.

A standalone smoke-test script, `scripts/smoke_client.py`, exercises the underlying protocol/transport client directly against the real receiver without needing Home Assistant — see its docstring for usage.

### Devices documentation

- [azur640r](docs/azur640r/): documentation for the AV Receiver Azur 640R itself from Cambridge Audio
- [pusr](docs/pusr/): documentation for the Serial to Ethernet USR-TCP232-302 from PUSR

### Serial communication parameters

Baud Rate：9600bps
Data Size：8bit
Parity：NONE
Stop Bits：1 bit
Local Port Number：4001
Remote Port Number：8234
Work Mode：TCP Server
Remote Server Addr：192.168.0.201
Client Overrun Mechanism：KEEP
Client Access Quantity：1