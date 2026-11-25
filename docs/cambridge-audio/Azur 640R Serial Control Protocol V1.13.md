# Azur 640R Serial Control Protocol V1.13

> **Source:** Derived from the Cambridge Audio *Azur 640R Serial Control Protocol V1.13* specification, with
 known typographical errata fixed and real-hardware behavior documented in [Verified Hardware Behavior](#verified-hardware-behavior).

---

## 1.1 RS232 Protocol

The protocol is accessed via `COM1` (the rear panel RS232C port).

### Frame Format

| Field | Header | Command Group | Separator | Command Number | Separator | Command Data | Footer |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Value** | `#` | `1` to `11` | `,` | `01` to `19` | `,` | `XXXX` | `CR` |
| **Byte Count** | `1` | `1` *(1–2 for `10`–`11`)* | `1` | `2` | `1` | `XX` *(variable)* | `1` |

*(When a command or reply carries no data, the second `,` separator and `Command Data` field are omitted: `#<group>,<number>\r`.)*

### Protocol Notes

1. All data consists of ASCII bytes.
2. Settings for the RS232 comm port are **`9600,N,8,1`** with **no handshaking**.
3. `CR` is carriage return, ASCII value `13` decimal (`0x0D`, `\r`).

---

## 1.2 Command Groups

Commands are split into the following groups:

| Command Group | Description |
| :---: | :--- |
| `1` | Amplifier Commands |
| `2` | Source Commands |
| `3` | Tuner Commands |
| `4` | Audio Processing Commands |
| `5` | Version Commands |
| `6` | Replies from Amplifier Commands |
| `7` | Replies from Source Commands |
| `8` | Replies from Tuner Commands |
| `9` | Replies from Audio Processing Commands |
| `10` | Replies from Version Commands |
| `11` | Error Messages |

---

## 1.3 Commands and Messages

### 1.3.1 Group 1 - Amplifier Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Power State | `0` - Standby, `1` - On | `#1,01,0\r` - Put 640R in standby |
| `02` | Volume Up | No Data | `#1,02\r` - Volume up |
| `03` | Volume Down | No Data | `#1,03\r` - Volume down |
| `04` | Bass Up | No Data | `#1,04\r` - Bass up |
| `05` | Bass Down | No Data | `#1,05\r` - Bass down |
| `06` | Treble Up | No Data | `#1,06\r` - Treble up |
| `07` | Treble Down | No Data | `#1,07\r` - Treble down |
| `08` | Sub On | No Data | `#1,08\r` - Subwoofer on |
| `09` | Sub Off | No Data | `#1,09\r` - Subwoofer off |
| `10` | Set LFE trim | `00` = 0 dB, `01` = -1 dB, …, `10` = -10 dB *(unsigned magnitude)* | `#1,10,03\r` - LFE trim set to -3 dB |
| `11` | Mute State | `00` - Off, `01` - On | `#1,11,00\r` - 640R mute off |
| `12` | Dynamic Range Set | `0` - 0/4, `1` - 1/4, `2` - 2/4, `3` - 3/4, `4` - 4/4 | `#1,12,02\r` - Set dynamic range limit to 2/4 |
| `13` | OSD On | No Data | `#1,13\r` - OSD On |
| `14` | OSD Off | No Data | `#1,14\r` - OSD Off |
| `15` | OSD Up | No Data | `#1,15\r` - OSD up |
| `16` | OSD Down | No Data | `#1,16\r` - OSD down |
| `17` | OSD Left | No Data | `#1,17\r` - OSD Left |
| `18` | OSD Right | No Data | `#1,18\r` - OSD Right |
| `19` | OSD Enter | No Data | `#1,19\r` - OSD Enter |

---

### 1.3.2 Group 2 - Source Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Input Select | `00` - Tuner, `01` - DVD, `02` - Video 1, `03` - Video 2, `04` - Video 3, `05` - Rec 1, `06` - Aux, `07` - CD, `08` - Rec 2, `09` - Reserved (`####`), `10` - 7.1 Direct In | `#2,01,02\r` - Select Video 1 |
| `02` | Input Select Up | No Data | `#2,02\r` - Next input up |
| `03` | Input Select Down | No Data | `#2,03\r` - Next input down |
| `04` | Set input mode | `00` - Analogue, `01` - Digital | `#2,04,01\r` - Digital source selected |
| `05` | Set Video Source | `0` - S-Video, `1` - Component, `2` - Composite | `#2,05,01\r` - Component video source |

> **Note:** Group 2 `Input Select` (`#2,01`) command codes differ from Group 7 (`#7,01`) reply codes on the hardware — `Tuner` is `00` when sending and `09` in the reply, and `09` is reserved on send. See [1.3.7 Group 7 - Replies from Source Commands](#137-group-7---replies-from-source-commands).

---

### 1.3.3 Group 3 – Tuner Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Tuner Stereo/Mono | `0` - Stereo, `1` - Mono | `#3,01,01\r` - Tuner in mono |
| `02` | Frequency Up | No Data | `#3,02\r` - Frequency up |
| `03` | Frequency down | No Data | `#3,03\r` - Frequency down |
| `04` | Up | No Data | `#3,04\r` - Tuner up |
| `05` | Down | No Data | `#3,05\r` - Tuner down |
| `06` | Tuner Mode | `1` - Frequency up/down, `2` - Search up/down, `3` - Preset up/down | `#3,06,03\r` - Tuner up/down control presets |
| `07` | Tuner Search Stop | No Data | `#3,07\r` - Tuner search stop |
| `08` | Tuner Auto Search | No Data | `#3,08\r` - Tuner auto search |
| `09` | Tuner Band | `0` - FM, `1` - AM | `#3,09,01\r` - Tuner in AM mode |
| `10` | Tuner PTY select | `1` - News, `2` - Affairs, `3` - Info, `4` - Sport, `5` - Educate, `6` - Drama, `7` - Culture, `8` - Science, `9` - Varied, `10` - Pop, `11` - Rock, `12` - MOR, `13` - Light, `14` - Classics, `15` - Other | `#3,10,11\r` - PTY Rock selected |
| `11` | Store Station | `1` - preset 1, `2` - preset 2, …, `15` - preset 15 | `#3,11,12\r` - Store current frequency in preset 12 |
| `12` | Get Preset | `1` - preset 1, `2` - preset 2, …, `15` - preset 15 *(action: tunes to preset)* | `#3,12,6\r` - Set tuner to preset 6 |
| `13` | Tuner Display mode | `1` - Frequency, `2` - Program name, `3` - Program Type, `4` - Clock time, `5` - Radiotext | `#3,13,04\r` - Display in clock time mode |
| `14` | Get Frequency | No Data | `#3,14\r` |
| `15` | Get Station name | No Data | `#3,15\r` |
| `16` | Get PTY | No Data | `#3,16\r` |
| `17` | Stop PTY Select | No Data | `#3,17\r` |

---

### 1.3.4 Group 4 - Audio Processing Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Set Audio to Stereo | `00` - Stereo, `01` - Stereo + SW | `#4,01,01\r` - Audio set to stereo mode plus sub |
| `02` | Set PLII/Neo/DSP | No Data | `#4,02\r` - Cycles to next mode (same as pressing the PLII/Neo/DSP button) |
| `03` | DD/DTS | No Data | `#4,03\r` - Cycles to next mode (same as pressing the DD/DTS button) |
| `04` | Get current PLII/Neo/DSP mode | No Data | `#4,04\r` |
| `05` | Get current DD/DTS mode | No Data | `#4,05\r` |

---

### 1.3.5 Group 5 - Version Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Get Main Software Version | No Data | `#5,01\r` - Get software version |
| `02` | Get Protocol Version | No Data | `#5,02\r` - Get protocol version |

---

### 1.3.6 Group 6 - Replies from Amplifier Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Power State | `0` - Standby, `1` - On | `#6,01,0\r` - 640R in standby |
| `02` | Volume Up | `-90` to `00` (where `-90` = mute, `00` = max volume) | `#6,02,-16\r` - Vol = -16 dB |
| `03` | Volume Down | `-90` to `00` (where `-90` = mute, `00` = max volume) | `#6,03,-16\r` - Vol = -16 dB |
| `04` | Bass Up | `-10` to `10` *(2 dB steps; positive values may carry `+`)* | `#6,04,-6\r` - Bass = -6 dB |
| `05` | Bass Down | `-10` to `10` *(2 dB steps; positive values may carry `+`)* | `#6,05,-6\r` - Bass = -6 dB |
| `06` | Treble Up | `-10` to `10` *(2 dB steps; positive values may carry `+`)* | `#6,06,-7\r` - Treble = -7 dB |
| `07` | Treble Down | `-10` to `10` *(2 dB steps; positive values may carry `+`)* | `#6,07,-7\r` - Treble = -7 dB |
| `08` | Sub On | No Data | `#6,08\r` - Subwoofer on |
| `09` | Sub Off | No Data | `#6,09\r` - Subwoofer off |
| `10` | Set LFE trim | `00` = 0 dB, `01` = -1 dB, …, `10` = -10 dB *(unsigned magnitude)* | `#6,10,03\r` - LFE trim set to -3 dB |
| `11` | Mute State | `0` - Off, `1` - On | `#6,11,00\r` - 640R mute off |
| `12` | Dynamic Range Set | `0` - 0/4, `1` - 1/4, `2` - 2/4, `3` - 3/4, `4` - 4/4 | `#6,12,02\r` - Set dynamic range limit to 2/4 |
| `13` | OSD On | No Data | `#6,13\r` - OSD On |
| `14` | OSD Off | No Data | `#6,14\r` - OSD Off |
| `15` | OSD Up | No Data | `#6,15\r` - OSD up |
| `16` | OSD Down | No Data | `#6,16\r` - OSD down |
| `17` | OSD Left | No Data | `#6,17\r` - OSD Left |
| `18` | OSD Right | No Data | `#6,18\r` - OSD Right |
| `19` | OSD Enter | No Data | `#6,19\r` - OSD Enter |

---

### 1.3.7 Group 7 - Replies from Source Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Input Select | `01` - DVD, `02` - Video 1, `03` - Video 2, `04` - Video 3, `05` - Rec 1, `06` - Aux, `07` - CD, `08` - Rec 2, `09` - Tuner, `10` - 7.1 Direct In | `#7,01,02\r` - Video 1 selected |
| `02` | Input Select Up | No Data | `#7,02\r` - Next input up |
| `03` | Input Select Down | No Data | `#7,03\r` - Next input down |
| `04` | Set input mode | `0` - Analogue, `1` - Digital | `#7,04,01\r` - Digital input selected |
| `05` | Set Video Source | `0` - S-Video, `1` - Component, `2` - Composite | `#7,05,02\r` - Composite video source selected |

---

### 1.3.8 Group 8 - Replies from Tuner Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Tuner Stereo/Mono | `0` - Stereo, `1` - Mono | `#8,01,01\r` - Tuner in mono |
| `02` | Frequency Up | No Data | `#8,02\r` - Frequency up |
| `03` | Frequency down | No Data | `#8,03\r` - Frequency down |
| `04` | Up | `1` - command complete, `2` - tuner searching | `#8,04,02\r` - Tuner searching |
| `05` | Down | `1` - command complete, `2` - tuner searching | `#8,05,01\r` - Tuner down executed |
| `06` | Tuner Mode | `1` - Frequency up/down, `2` - Search up/down, `3` - Preset up/down | `#8,06,03\r` - Tuner up/down control presets |
| `07` | Tuner Search Stop | `xxxxx` *(5 digits: FM = implied 2 decimals MHz; AM = whole kHz)* | `#8,07,09525\r` - Current frequency is 95.25 MHz |
| `08` | Tuner Auto Search | No Data | `#8,08\r` - Tuner auto search |
| `09` | Tuner Band | `0` - FM, `1` - AM | `#8,09,01\r` - Tuner in AM mode |
| `10` | Tuner PTY select | `1` - News, `2` - Affairs, `3` - Info, `4` - Sport, `5` - Educate, `6` - Drama, `7` - Culture, `8` - Science, `9` - Varied, `10` - Pop, `11` - Rock, `12` - MOR, `13` - Light, `14` - Classics, `15` - Other, `16` - Searching in progress, `17` - Search failed | `#8,10,11\r` - PTY Rock selected |
| `11` | Store Station | `1` - preset 1, `2` - preset 2, …, `15` - preset 15 | `#8,11,12\r` - Store current frequency in preset 12 |
| `12` | Get Preset | `1` - preset 1, `2` - preset 2, …, `15` - preset 15 | `#8,12,6\r` - Set tuner to preset 6 |
| `13` | Tuner Display mode | `1` - Frequency, `2` - Program name, `3` - Program Type, `4` - Clock time, `5` - Radiotext | `#8,13,04\r` - Display in clock time mode |
| `14` | Get Frequency | `xxxxx` *(5 digits: FM = implied 2 decimals MHz; AM = whole kHz)* | `#8,14,09525\r` - Current frequency is 95.25 MHz |
| `15` | Get station name | `xxxxxxxx` | `#8,15,Radio666\r` - Current station name is Radio666. If no RDS station name available, returns a string of stars (`********`) |
| `16` | Get PTY | `0` - No PTY, `1` - News, `2` - Affairs, `3` - Info, `4` - Sport, `5` - Educate, `6` - Drama, `7` - Culture, `8` - Science, `9` - Varied, `10` - Pop, `11` - Rock, `12` - MOR, `13` - Light, `14` - Classics, `15` - Other | `#8,16,11\r` - Current PTY is Rock Music |
| `17` | Stop PTY Select | No Data | `#8,17\r` |

---

### 1.3.9 Group 9 - Replies from Audio Processing Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Set Audio to Stereo | `00` - Stereo, `01` - Stereo + SW | `#9,01,01\r` - Audio set to stereo mode plus sub |
| `02` | Set PLII/Neo/DSP | `xxxxxxxx` | `#9,02,PCM + PLIIx Movie\r` - Describes the mode it's just switched to, exactly as on front panel |
| `03` | DD/DTS | `xxxxxxxx` | `#9,03,Dolby Digital (2/0)\r` - Describes the mode it's just switched to, exactly as displayed on the front panel |
| `04` | Get current PLII/Neo/DSP mode | `xxxxxxxx` | `#9,04,PCM + PLIIx Movie\r` - Describes the current mode |
| `05` | Get current DD/DTS mode | `xxxxxxxx` | `#9,05,Dolby Digital (2/0)\r` - Describes the current mode |

---

### 1.3.10 Group 10 - Replies from Version Commands

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Get Main Software Version | `X.X` | `#10,01,1.2\r` - Software is version 1.2 |
| `02` | Protocol Version | `X.X` | `#10,02,1.6\r` - Protocol is version 1.6 |

---

### 1.3.11 Group 11 - Error Messages

| Command Number | Command Description | Command Data | Example |
| :---: | :--- | :--- | :--- |
| `01` | Command Group Unknown | No Data | `#11,01\r` - Command group error |
| `02` | Command Number in Group Unknown | No Data | `#11,02\r` - Command number error |
| `03` | Command Data Error | No Data | `#11,03\r` - Command data error |

---

## Verified Hardware Behavior

The following behaviors were observed against a real Azur 640R (see [client.py](../../custom_components/azur640r/client.py)):

- **Input Select code mismatch & zero-padding (`#2,01` vs. `#7,01`):** Sending `#2,01` uses `00` for Tuner and `01`–`08`, `10` for the remaining inputs (`09` is reserved/`####`), while the `#7,01` reply reports `09` for Tuner and `01`–`08`, `10` for the rest. Replies are zero-padded (e.g. `01`, `06`), though parsers should accept unpadded integers as well.
- **Sign-padded numeric fields (`- 2`, `+2`):** Numeric replies can use a fixed-width sign-padded field where whitespace appears between the sign and digit (e.g., `"- 2"` for `-2`), and positive Bass/Treble values carry a literal `+` sign. Strip all internal whitespace before parsing numeric fields (never on free-text fields like station name).
- **Bass & Treble step size (`1,04`–`1,07`):** Although documented as `-10` to `10`, each step moves by `2 dB` (`11` discrete steps: `-10, -8, …, +8, +10`).
- **DD/DTS query reply number (`4,05`):** Sending `#4,05\r` (*Get current DD/DTS mode*) consistently replies with command number `03` (`#9,03,...`) rather than `05`.
- **FM vs. AM frequency encoding (`3,07` / `3,14`):** FM returns 5 digits with an implied 2-digit decimal (`09525` -> `95.25 MHz`), whereas AM returns 5-digit whole kHz (`00522` -> `522 kHz`).
- **PTY Select (`3,10`) reply semantics:** The `#8,10` reply is a search status (`1`–`15` = matching station found, `16` = searching in progress, `17` = search failed) rather than an echo of the requested PTY.
- **Get Preset (`3,12`) semantics:** Despite its name, `#3,12,<n>\r` is an action that tunes the receiver to preset `<n>`, not a read-only query.

---

## Errata Corrected from Original V1.13 PDF

Compared to the raw 2007 Cambridge Audio V1.13 PDF/TXT, this document fixes the following typographical and formatting errors:

- **Section numbering:** Renumbered `1.4` (`1.4.1`–`1.4.11`) to `1.3` (`1.3.1`–`1.3.11`) to remove the missing `1.3` gap.
- **Group 8 duplicate row `14`:** Removed the erroneous first `14 | Tuner Display mode` copy-paste row.
- **Group 10 (`02`) example:** Corrected `#10,03,1.6\r` to `#10,02,1.6\r`.
- **Group 11 (`01`–`03`) examples:** Corrected `#5,01,\r`–`#5,03,\r` to `#11,01\r`–`#11,03\r`.
- **Group 1 (`10`) & Group 6 (`10`) LFE trim:** Corrected `-10 = -10dB` to `10 = -10 dB` (unsigned magnitude on the wire).
- **Group 8 (`07`, `14`) frequency format:** Corrected `xxx.xx` to `xxxxx` to match actual 5-digit wire payloads (`09525`).
- **Group 6 (`02`, `03`) syntax:** Closed the missing parenthesis in `(where -90 = mute, 00 = max volume)`.
- **Wire example hygiene:** Removed stray trailing commas on no-data examples (`#4,04,\r`, `#5,01,\r`, `#5,02,\r`), removed stray spaces after commas (`#1,10, 03\r`, `#1,12, 02\r`, `#3,13, 04\r`, `#6,10, 03\r`, `#6,12, 02\r`, `#8,13, 04\r`, and `#9,02`–`#9,05`), zero-padded `#7,01,02\r`, and fixed `availible` -> `available`.

---

## Manufacturer & Copyright Notice

> Information in this document has been carefully checked for accuracy; however, Cambridge Audio's policy is one of continuous improvement, therefore design and specifications are subject to change without prior notice. If you notice any errors please feel free to email us at: support@cambridgeaudio.com. This document contains proprietary information protected by copyright. All rights are reserved. No part of this document may be reproduced by any mechanical, electronic or other means, in any form, without prior written permission of the manufacturer. © Copyright Cambridge Audio Ltd 2007

- **Address:** Gallery Court, Hankey Place, London SE1 4BB England
- **Tel:** +44 (0)20 7940 2200
- **Fax:** +44 (0)20 7940 2233
- **Web:** [www.cambridge-audio.com](https://www.cambridge-audio.com)
