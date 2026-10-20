# MS-CAN sniffer — 2011 Ford Fusion body bus

![ESP32](https://img.shields.io/badge/ESP32-E7352C?style=flat-square) ![CAN bus](https://img.shields.io/badge/CAN_bus-2D2D2D?style=flat-square) ![C](https://img.shields.io/badge/C-A8B9CC?style=flat-square)


Listen-only CAN sniffer for the ESP32-S3 that logs every frame on the car's
**MS-CAN body bus (125 kbps, OBD2 pins 3/11)** — the bus carrying climate
control, locks, windows, etc. It never transmits, so it cannot disturb the car.

The point: capture traffic, press a climate button, capture again, diff the
two logs. The new/changed message is your button — replay it later to control
the function from the ESP32.

- **Board:** Elecrow CrowPanel 5.0" (ESP32-S3-WROOM-1-N4R8)
- **Toolchain:** ESP-IDF v5.4.4, target `esp32s3`
- **CAN:** S3 built-in TWAI in `TWAI_MODE_LISTEN_ONLY` + SN65HVD230 transceiver

## Wiring

OBD2 pigtail (16-pin male, bare-wire). Looking at the front of the male plug,
wide side up: top row = pins 1–8 left to right, bottom row = 9–16.

| OBD2 pin | Goes to |
|---|---|
| 3 (MS-CAN-H, top row 3rd from left) | SN65HVD230 `CANH` |
| 11 (MS-CAN-L, bottom row 3rd from left) | SN65HVD230 `CANL` |
| 4 / 5 (GND) | ESP32 `GND`, transceiver `GND` |

Transceiver module:

| Module pin | Goes to |
|---|---|
| `VCC` | ESP32 `3V3` (3.3 V module — not 5 V) |
| `GND` | ESP32 `GND` |
| `TXD` | ESP32 `IO19` (J4 pad 7 — unused in listen-only, required by the driver) |
| `RXD` | ESP32 `IO20` (J4 pad 8) |
| `CANH` / `CANL` | OBD2 pins 3 / 11 (twist the pair) |

**Remove the 120 Ω termination jumper** on the transceiver — the car bus is
already terminated. GPIO43 is left alone so the USB serial console keeps
working.

**Sanity check before plugging into the car:** car OFF, measure resistance
between OBD2 pins 3 and 11 — expect ~60 Ω (two 120 Ω terminators in parallel).
0 Ω or open = wrong pins, stop and recheck.

Power the CrowPanel over USB-C from your laptop (that same cable carries the
logs).

## Flash

Prebuilt: `ms-can-sniffer.bin` (flash at 0x0), or build it yourself:

```bash
. ~/esp/esp-idf/export.sh
cd esp32-ms-can-sniffer
idf.py set-target esp32s3
idf.py build
```

Flash with `idf.py -p /dev/ttyACM0 flash`, or use
[Adafruit's web flasher](https://adafruit.github.io/Adafruit_WebSerial_ESPTool/)
in Chrome: ESP32-S3, file at offset 0x0. (Hold BOOT + tap RESET if it won't
connect.)

## Sniffing workflow

1. Flash, open a serial monitor at **115200**.
2. Plug the pigtail into the car, **ignition ON** (body modules sleep with
   key off). You should see frames streaming plus a stats line every 5 s.
   `NEW` marks the first time an ID appears.
3. Save ~10 s of traffic → `baseline.log`.
4. Press **one** climate button (e.g. A/C), save ~10 s → `ac.log`.
5. Diff: `./can_diff.py baseline.log ac.log` (or `python3 can_diff.py ...`).
   It ignores timestamps, lists IDs whose data bytes changed (with a per-byte
   breakdown of what flipped) and IDs that only appear in the action capture,
   and names the key 2011 Fusion IDs from the DBC roadmap. A brand-new ID, or
   an ID whose data bytes change with the button, is your target message.
6. Repeat per button (fan +/-, temp +/-, recirc, defrost...). One button per
   capture keeps the diffs clean.

To sniff the **HS-CAN powertrain bus** instead (500 kbps, pins 6/14), change
`CAN_BITRATE_KBPS` to 500 in `main/sniffer.c` and move CANH/CANL to pins 6/14.

## From sniffing to control

Replaying a captured frame needs the TWAI driver in normal mode
(`TWAI_MODE_NORMAL` instead of `TWAI_MODE_LISTEN_ONLY`) plus
`twai_transmit()`. Notes from experience with Ford body buses:

- HVAC messages are usually simple: same ID, one or two bytes change.
- Some modules expect the message repeated (e.g. every 100–500 ms) or they
  time out and revert.
- If a function ignores your replay, it may need ignition-on state or a
  diagnostic session — that's the next layer to investigate per function.
- Stay off safety buses (ABS/airbag/steering). Climate, locks, windows and
  lights are the safe playground.

---

### 👤 About the author

**Prashant Shrestha** — Cybersecurity Specialist (CDI College, in progress) · 11+ years across SOC analysis, penetration testing & network security · Mississauga, ON 🇨🇦

🔗 [LinkedIn](https://www.linkedin.com/in/cto-prashant/) · 💻 [GitHub](https://github.com/prashantshrestha01)

*Building in public — every project here is my own lab work.*
