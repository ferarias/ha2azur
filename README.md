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

## FAQ

### Where do I get the ESPHome API encryption key?

For the Connect AUX-2, the key we need is the one Home Assistant uses to connect to it (not your Home Assistant password). Connect AUX-2 stores its own encryption key; **DO NOT** generate another nor reset your device to get it.

#### Obtain the Connect AUX-2's serial port

1. Browse to Settings → Connectivity → Serial.
2. Look for the ports of Connect AUX-2 of type «Serial proxies».
3. Locate the one for the port you have connected your Azur 640R (1 or 2).
4. Click on the (i) icon «Port Information» and copy the «Device». Something like `esphome-hass://...`. If it does not show up, click «Update.
5. The identifier of the ESPHome integration is the string between `/esphome` and `?`. Eg:  
   If it is `esphome-hass://esphome/ABCDEFGHIJKLMNOPQRSTUVWXYZ?port_name=RS-232+Port+1"`, then
   * ESPHome Identifier: `ABCDEFGHIJKLMNOPQRSTUVWXYZ`
   * Port name: `RS-232 Port 1`


#### Obtain ESPHome API encryption key

If you have access to config files (eg., via Studio Code Server, SMB, terminal or SSH) you can check this file:

```text
/config/.storage/core.config_entries
```

**WARNING**: this is an internal HA file: just read, do not modify anything.

1. Find the string of the previously obtained ESPHome identifier, e.g.: `ABCDEFGHIJKLMNOPQRSTUVWXYZ`
2. At that same entry, under ``data``, find a field named:

```json
"noise_psk": "..."
```

That value is the ESPHome encryption key. **DO NOT** share this value.

## Contributing / releases

Work happens on feature branches merged into `main` via pull request — `main` is protected and always reflects the latest released state. CI (`.github/workflows/validate.yml`) runs [hassfest](https://github.com/home-assistant/actions) and the [HACS validation action](https://github.com/hacs/action) on every PR and push to `main`.

Commit messages (or at least PR titles, if you squash-merge) must follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `docs:`, …) — [release-please](https://github.com/googleapis/release-please) uses them to decide the next version. Once commits land on `main`, release-please opens/updates a "release PR" bumping `custom_components/azur640r/manifest.json`'s `version`; merging *that* PR tags and publishes a GitHub Release, which is what HACS then shows as the integration's version (instead of a raw commit hash).

