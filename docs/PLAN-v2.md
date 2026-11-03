# FM-1 Flasher v2: plan (Metro ESP32-P4)

A second flasher on an Adafruit Metro ESP32-P4 with the 2.8" TFT Touch
Shield, which downloads firmwares from thefirmwarehub.com itself over WiFi.
The v1 Feather RP2350 flasher (PLAN.md) stays as it is; both live in this
repo.

## Hardware

**Metro ESP32-P4 "Hydra" (Adafruit 6536).**
- ESP32-P4 "v1" (not P4X): two 360 MHz RISC-V cores, 16 MB flash, 16 MB PSRAM.
- WiFi: ESP32-C6 coprocessor over SDIO (ESP-Hosted); CircuitPython
  `wifi`, `socketpool`, `ssl`.
- USB-A host: the P4's high-speed USB 2.0 controller (TinyUSB instance 1),
  software-controlled 5 V (`board.USB_HOST_POWER`) with a boost converter
  for battery use.
- microSD on the board: 4-bit SDIO (`sdioio`, `board.SD_*`, card detect
  `board.SD_CD`), on pins of its own.
- SPI on a separate 6-pin header (`board.SPI()`: GPIO15/16/17), not D11-D13.
  I2C on SDA/SCL (GPIO33/32).
- Barrel jack, USB-C, or a LiPo with charging; `board.VOLTAGE_MONITOR`.
- CircuitPython support since 11.0.0-alpha.2 (adafruit/circuitpython#11643).
  The port is alpha.

**2.8" TFT Touch Shield, capacitive (Adafruit 1947).**
- ILI9341, 320x240, SPI: CS D10, DC D9. SPI comes from the ICSP 2x3 header
  by default, which should mate with the Metro's 6-pin SPI header.
- Touch: FT6206 on I2C at 0x38 (`adafruit_focaltouch`). Newer shields may
  have a CST026; check which one this shield has.
- Backlight always on unless the "Pin 5" jumper is soldered (then D5).
- Its own SD slot (CS D4) isn't used: the Metro's SDIO slot is better.

## What v2 fixes

| v1 (Feather RP2350) | v2 (Metro ESP32-P4) |
|---|---|
| PIO-USB or MAX3421E host; V15 trouble on short cables | Native USB host controller |
| SD card shares SPI with the display and host chip; stale sectors, a wiped card (DEVNOTES §6.16-6.18) | SD card on its own SDIO bus |
| ~337 KB RAM: packed fonts, an 80 px picture pool, soft reload before installs (§6.11) | 16 MB PSRAM |
| Refreshing the card needs a computer and `make_sd.py` | Update firmwares from the hub on the device |

## Risks

1. **Enumeration buffer.** The Metro P4 build uses the 288-byte default
   `CFG_TUH_ENUMERATION_BUFSIZE`, so stock firmware shouldn't mount the FM-1
   (293-byte configuration descriptor). A per-board setting, as Fruit Jam
   has (4096), is an easier upstream ask than the global default (#11697).
2. **Enumeration retry.** v1 needed a TinyUSB enumeration retry. It may have
   been a PIO-USB timing problem that the native controller doesn't have.
3. **Alpha port:** WiFi over the coprocessor, high-speed host and `sdioio`
   are new on this chip.
4. **Card pictures:** the hub's are PNGs, and CircuitPython has no built-in
   PNG decoder. `adafruit_imageload` decodes PNG in Python; maybe too slow
   for ~150. Options: decode on first view and cache a BMP, or ask the hub
   for small BMPs or JPEGs (`jpegio` is built in).
5. **Physical fit:** whether the Metro's microSD slot can be reached with
   the shield on, whether the shield's ICSP socket mates with the Metro's
   SPI header, and whether the USB-A port and barrel jack clear the shield.
6. **Screen:** 320x240 is two-thirds of v1's 480x320 each way; the layouts
   need rework. Full-screen refreshes should be faster (half the pixels).

## Phase 0: Spikes (go/no-go, REPL scripts, no UI)

Bench setup: the Metro came without TinyUF2 (double-click reset did
nothing). BOOT + Reset gives the ROM loader (no drive); TinyUF2 0.36.0's
`combined.bin` was written at 0x0 with `esptool`, then a plain Reset gives
METROP4BOOT. This board's chip reports revision v0.1, which TinyUF2 and
CircuitPython accept.

- [x] Display and touch (`device/metro_spike_display.py`): `board.SPI()`
      through the ICSP header with no jumpers (CS D10, DC D9, 40 MHz); a
      full-screen refresh takes 65 ms. Touch is an FT6206 (`adafruit_focaltouch`,
      0x38, chip ID 0x06) reporting portrait: screen x = 319 - raw y,
      screen y = raw x.
- [ ] USB host: the port works (a keyboard enumerated in 0.6 s), but on the
      stock build the FM-1 doesn't enumerate in 20 s, as expected with the
      288-byte buffer. Next: a build with a 512-byte buffer
      (`ref/cp-metro-p4`, branch `fm1-metro-p4`); identity query; a V15 → SLOOP → V15 round trip
      with `fm1usb`/`fm1update` on short and long cables, timed against
      v1's ~70 s.
- [x] SD card (`device/metro_spike_net.py`): the board doesn't mount it;
      `sdioio.SDCard` (4-bit, 40 MHz) plus `storage.mount` does. 1 MB writes
      at 1.6-1.75 MB/s, reads at 6.9-7.7 MB/s. The full package checks on
      SLOOP (610 KB) take 2.3 s. Card detect (`board.SD_CD`) reads low with
      a card in.
- [x] WiFi (`device/metro_spike_net.py`): `catalog.json` (148 firmwares,
      290 KB) in 3.6 s; SLOOP 2.8.4 streamed to the card at 0.21 MB/s with a
      matching SHA-256 (a full card, ~90 MB, would take ~7 min); 15 MB free
      RAM. The hub's picture (480x480 full-colour PNG, 4 KB) takes 9.3 s to
      decode with `adafruit_imageload`: too slow to do all ~150 at once
      (~23 min). Decode on first view and cache, or ask the hub for small
      BMPs. One hard fault into safe mode right after WiFi credentials were
      first added to `settings.toml`; it didn't recur after a reset.

## Phase 1: Port

- [ ] Split the board-specific parts of `lib/fm1ui/device.py` into one
      module per board; `fm1proto`, `fm1update` and `fm1usb` unchanged.
- [ ] Layout sizes in one place, so the screens work at 320x240;
      `ui_sim.py` at that size.
- [ ] Relax the RAM workarounds on this board only.
- [ ] `deploy.py --board metro-p4`; a 320x240 splash.

## Phase 2: Update firmwares on the device

- [ ] Move the catalogue logic out of `make_sd.py` into a shared
      `fm1catalog.py` for CPython and CircuitPython, with swappable fetch
      and file access (also usable by a web page later).
- [ ] An Update firmwares screen: WiFi, a plan ("12 new, 3 updated,
      2 removed, 8 MB"), downloads with progress, SHA-256 against the
      catalogue plus the full package checks, pictures, `index.txt`, and
      removal of firmwares the hub dropped (by `catalog_id` only).
- [ ] Resumable: write to a temporary name, then rename, so a power cut
      leaves a working card.
- [ ] WiFi credentials from `settings.toml` at first; on-screen entry later.
      Offer to fill an empty card at first start.

## Phase 3: Battery and release

- [ ] Low-battery warning from `VOLTAGE_MONITOR`; installs on battery
      through the host port's boost.
- [ ] Soak tests across many firmwares, a Learn Guide section, a release.

## Upstream and the hub

- [ ] After the USB host spike: ask for a Metro P4 board-level enumeration
      buffer (512, or 4096 like Fruit Jam), so v2 runs on stock CircuitPython.
- [ ] Tell the hub's maintainer that flashers will download from the hub
      directly, and ask about the pictures (PNG CORS/BMP/JPEG).
