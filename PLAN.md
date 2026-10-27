# FM-1 Flasher: plan

See `fm1-firmware-flasher-brief.md` for the protocol and package-format details this plan builds on.

Guiding idea: prove the protocol from a computer first, so USB-host problems and protocol problems are never debugged at the same time.

## Hardware

- **Adafruit Feather RP2040 USB Host** (USB-C for CIRCUITPY, USB-A host via PIO USB).
- **TFT FeatherWing V2 3.5" 480x320, capacitive touch** ([PID 5872](https://www.adafruit.com/product/5872)). HX8357 display, capacitive touch controller, and microSD on shared SPI. Pin and controller details are confirmed in Phase 2.
- An M-VAVE FM-1 we're willing to flash. Before any write, we have the recovery path ready (see "Recovery" below).
- Later: Fruit Jam port. Optional: 2.4" FeatherWing support behind the same display abstraction.

## Phase 0 findings (2026-10-22)

- **Two install routes.** `WebUpdate.js` covers only FM1 Open firmwares: the `FM1_OFFICIAL_OPEN`, `FM1_COMMUNITY_n`, and `FM-1_8nnnnnn` identities, which have a `build_id` and support cmd 49 and cmd 50. All 84 firmwares in the Firmware Hub catalogue are `FM-1_<n>` firmwares that the hub installs another way. Felucca, SLOOP, and their forks don't answer cmd 49, publish no `build_id`, and ship their own loader. That loader reports a hard-coded `ota-FM-1_9xx`, not `ota-FM1C_…`. The flasher implements both routes. `meta.json` `kind` is `open`, `stock`, or `community`.
- **The community route is the hub's.** Send the kick, wait 2 s, then serve stage 1 with 10 ms between blocks. Wait 3 s, then wait for an `ota-FM-1_9xx` loader. Firmwares the hub lists with `loader: "mvave"`, such as Bubba, use the vendor `ota-FM-1_015` instead. Then serve stage 2 and verify the identity only, because these firmwares have no build hash. The device resumes only into the loader the package expects, since another firmware's loader may lay out flash differently. Leaving stock V15 still needs the extra confirmation.
- **Trimmed packages.** Felucca-family packages trim the 32-byte alignment padding from the trailing `ota.bin`, so its `stored` length runs past the end of the file, and `WebUpdate.js` rejects them. `inspect(strict=False)` accepts exactly that case. All 84 hub packages parse, and all 84 complete a simulated install.
- **Hub catalogue.** https://thefirmwarehub.com/catalog.json is updated nightly and is CORS-open. Entries have `id`, `name`, `author`, `version`, `product`, `pkg`, `size`, `sha256`, `source`/`release`, `loader`, and `kind` (a genre). They have no license, `build_id`, or `loader_sha256`; `make_sd.py` computes `loader_sha256`.
- **USB (measured 2026-10-22).** Stock V15 is VID 0x4C4A (JieLi) / PID 0xC755, product "FM-1", full speed; on macOS its MIDI port is "USB Composite Device". It answers cmd 17 with `FM-1_015` and doesn't answer cmd 49.
- **USB (from source).** The Felucca/SLOOP app is 1209:0001 and their loader is 1209:**0002**, so the PID changes when the device re-enumerates. Stock V15 and vendor-loader VID/PIDs are unknown; Phase 1 reads them from the real device.
- **Progress.** Measured against the bytes each stage reads (header, table, and loader or flash entry), not the whole image, so the bar doesn't stall near 86%.
- **Recovery.** In the hub's error text: hold OCT− while powering on to start the update loader manually. The rescue key `F0 22 24 35 7D F7` drops the device into the ROM UBOOT bootloader.

## Phase 0: Desk work on CPython, no hardware (done)

1. Clone `m-vave/fm1_open` at `4c7496daac04a95ff10d1afdcc8f9ead2dbabc41` into `ref/` (gitignored) and read all of `sdk/WebUpdate.js`, especially retries, receive-queue behavior, and the checks in `connect()` and `prepare()`.
2. `lib/fm1proto.py`: one module that runs on both CPython and CircuitPython. Contains `crc16`, `decode_header`, `pack7`/`unpack7`, frame build and parse, `inspect_package`, the image-to-file offset mapping, and a streaming `PackageReader` that caches only `image[0:940]`.
3. Unit tests against `FM-1_015.fwsc` and a couple of community packages.
4. `tools/fake_fm1.py`: a simulator that issues read requests and finish markers, so the serve loop is tested without a device.
5. `tools/make_sd.py`: parses each package and writes `meta.json` (product, build_id, family, bytes, sha256, loader_sha256, kind, source_url, license).
6. Research: where `build_id` comes from for community firmwares, and how the hub's and Felucca's installer JS differ from `WebUpdate.js`.

## Phase 1: Reference flasher on desktop

- `tools/flash_cli.py` (`python-rtmidi` or `mido`) runs the full install sequence against the real FM-1. This proves the protocol, mode selection, and re-enumeration timing on hardware that's easy to debug.
- Before flashing: record the device's identity and its USB VID/PID in app mode and loader mode, and log every read request's address and length. The simulator's read pattern (header, table, then loader or flash entry) is a guess.
- First flash: stock V15 to a community firmware, then back to stock (voice-bank restore).

### First real install: stock V15 to SLOOP 2.8, 2026-10-22

- Took 43 s with `flash_cli.py install sd_out/firmware/sloop --force`: about 3 s for stage 1, 3 s to restart, 34 s for stage 2, and 3 s to verify. The log is `logs/install-20261022-214440-FM-1_900.jsonl`.
- The loader re-enumerated as `ota-FM-1_900` and macOS/rtmidi saw it right away. The SLOOP app's MIDI port is named "Felucca".
- Read pattern: stage 1 sends 23 requests (0x0–0x600, one block at 0x4400, then the loader entry); stage 2 sends 1180 requests covering 0x0–0x93400 in order. Request sizes are 512, 32, the loader's tail, and 8 for the finish. The simulator now plays this pattern.

### Back to stock: SLOOP 2.8 to V15, 2026-10-22

- Took 33 s with `flash_cli.py install sd_out/firmware/stock-v15 --force` on the legacy route with hub timing. The vendor loader re-enumerated as `ota-FM-1_015` and was found in under 1 s, on a port name our filter already matched. The 36 factory voice-bank writes were all acknowledged in 0.6 s. The log is `logs/install-20261022-214957-FM-1_015.jsonl`.
- Read patterns differ by updater. SLOOP's stage 1 for the V15 package read 0x0–0x4400 and the vendor loader (0xA5F00–0xAAD01). The vendor loader's stage 2 read 0x0–0x600, then 0x4400–0x93400, skipping image 0x600–0x4400. Image address = flash address + 0x400 (the flash entry's offset), so loaders never request the boot head (flash 0x0000–0x3FFF). They write only the app area, as the rescue tools assume.
- **Phase 1 is complete:** both directions work on real hardware.

### Rescue path: tested 2026-10-22

- **A Raspberry Pi Pico (RP2040) works as an FM-1 Transporter from macOS.** Build kurogedelic/FM-1-transporter @ `a632d92` with `-DPICO_BOARD=pico` (pico-sdk 2.2.0, Arm GNU Toolchain 15.3), embedding jl-uboot-tool @ `adb3f18` `wl82loader.bin` (sha256 `d41da612…`). Wiring: GP0 to D+, GP1 to D−, GND to GND, with 5 V not connected. Drive it with MvaveFM1Unbricker @ `707470a` `fm1_transporter_recover.py` (`info`, `dump`, and `recover PACKAGE`). The sources are in `ref/` (gitignored).
- **First run.** `info` can fail once with `uboot=0` because the status reply arrives during the Transporter's 6 s pulse phase. Run it again without power-cycling.
- **Baseline dump** (stock V15, 2026-10-22): `ref/flash-dumps/fm1-transporter-dump-20261022-213229.bin`, sha256 `8a4d2330…`. The head and app match V15 exactly. Felucca settings objects left by earlier firmwares are at 0xFC000–0xFE000.
- **The plain-cable tools** (`fm1_rescue.py`, `fm1_unbrick.py`) need SCSI pass-through, so they run on Linux or Windows only, not macOS.

## Phase 2: Hardware spikes on the Feather

- Check whether the USB-A host port gets 5 V on LiPo. If it doesn't, add a 5 V boost converter.
- Check for conflicts between the PIO USB pins and the FeatherWing's TFT CS, DC, SD CS, and touch pins.
- Check whether CircuitPython has `hashlib` with sha256.
- Milestone: send cmd 17 to the FM-1 with `usb.core` and print the identity. Try `adafruit_usb_host_midi` first, and fall back to hand-built USB-MIDI 1.0 packets if long SysEx breaks.

### Phase 2 findings (2026-10-22)

- **`hashlib`:** CircuitPython 11.0.0-alpha.0 on the Feather RP2040 USB Host has it, but only as `hashlib.new("sha256")`. `fm1proto.sha256()` handles both forms.
- **5 V on the USB-A port:** with the Feather on USB power, the FM-1 shows its charging icon, so 5 V reaches it. CircuitPython's board setup claims `USB_HOST_5V_POWER` ("in use"). Battery operation is still untested.
- **Blocker: stock V15 never enumerates on the Feather.** Its configuration descriptor is 293 bytes (5 interfaces: UAC1 audio control, iso out, iso in, and MIDI streaming on interface 4 with bulk 0x84/0x04, 64 B). CircuitPython sets `CFG_TUH_ENUMERATION_BUFSIZE` to 284 + 4 = 288 (`supervisor/shared/usb/tusb_config.h`), and TinyUSB aborts enumeration when `wTotalLength` exceeds it. The fix is a larger buffer. That define is `#ifndef`-guarded, so a board build can override it. Felucca-family firmwares are MIDI-only and should fit, but stock V15 is the main starting point, so the flasher needs the fix.
- **Actual blocker (2026-10-25): the Feather's PIO USB host never sees the FM-1 attach.** I captured TinyUSB host logs (CircuitPython 10.3.1 with `CIRCUITPY_DEBUG_TINYUSB=2` and the console UART on TX, read by the Pico on GP5). A Keychron K8 keyboard on the same port gives a full "Device Attach … Enumeration complete: success = 1". The FM-1 (stock V15, on, charging from the port's 5 V) produces no attach event in either USB-C orientation, before or after replugging. So the FM-1 never pulls D+ high for this host, and the descriptor size never comes into play. Hypothesis: the FM-1's chip treats the port as a charger, not a host, perhaps because the PIO host relies on the RP2040's internal pull-downs rather than standard 15 kΩ ones. Next steps: measure D+ with a multimeter, try external 15 kΩ pull-downs, or use a MAX3421E USB Host FeatherWing.
- **CC fixer and clock tests (2026-10-25):**
  - With an Adafruit USB-C CC fixer inline at the FM-1 (125 MHz build), the FM-1 attached three times. Each time enumeration failed: the 8-byte device descriptor sometimes read correctly, but zero-length status stages and Set Address failed.
  - A 120 MHz build (whole-number Pico-PIO-USB clock dividers), with the 512-byte buffer and logging, enumerates the keyboard perfectly. So neither the buffer nor the clock breaks the host. With the CC fixer, the FM-1 then gave no attach in three replugs.
  - Conclusion: whether the FM-1 attaches depends on the FM-1's USB-C power and termination, not on the host software. It is inconsistent on the Feather's USB-A port, and reliable on the Mac.
  - Also learned: CircuitPython runs the Feather at 125 MHz by default (an SDK default), so Pico-PIO-USB's clock dividers are fractional there. Prefer 120 MHz for robustness.
- **Descriptor size (still needed later):** the 293-byte descriptor exceeds the 288-byte default. The 512-byte build's keyboard result is unreliable (the Feather crashed off USB during that run) and needs retesting.
- **Root cause found (2026-10-26): the FM-1 needs a second enumeration attempt after hot-plug.** This replaces the charger-detection and USB-C power theories above. The evidence, from a second Pico (CircuitPython 10.3.1 with debug logging, the TinyUSB log looped back from GP12 to GP5, and D+/D− sampled through `memorymap`):
  - **The FM-1 runs a role-detect loop after hot-plug** (`device/fm1_lines.py`, plain inputs with pull-downs, no host): D+ up (J) for 2.05 s, then D− up (K) for 0.02–0.5 s, then SE0 for about 1.2 s, repeating about every 3.6 s with no end. Once a host has enumerated it, it holds J steadily, even after the host goes away.
  - **A bus reset during the J phase makes it a device, but it can't answer that first enumeration.** With stock timing, it ACKs the first SETUP and then never returns the descriptor data. With 200 ms of reset recovery, it doesn't even ACK the SETUP. After that one failed attempt, it holds J and waits as a normal device.
  - **TinyUSB never retries a failed enumeration,** so the port stays stuck until the next unplug. A fresh host, after an RP2040 reset, finds the FM-1 already waiting and enumerates it on the first try. That's why only "reset with the FM-1 plugged in" ever worked.
  - **The earlier "no attach at all" results came from Pico-PIO-USB.** Its disconnect check only runs while the bus is active. A device that vanishes while the port waits for its bus reset left the port marked "connected" forever, so later hot-plugs were never reported. The K phase can look like a low-speed device attaching, which is one way to get into that state.
  - **VBUS is not involved.** Cycling the host's 5 V never helps: the FM-1 is battery powered and keeps its state. The Pico gets VBUS from the Mac, so its resets don't cycle VBUS at all.
  - **Long attach debounces are harmful.** A 2 s debounce (tried after a suggestion to lengthen waits) lands right where the FM-1 leaves its 2.05 s J phase.
- **Fix: 5 of 5 hot-plugs mounted and answered `FM-1_015`** (Pico, `build-pico-v4-debug`, 15 kΩ pull-downs fitted). Every time, attempt 1 failed and the retry 300 ms later succeeded. The patches are in `patches/`:
  - `tinyusb-enum-retry.diff`: retry a failed root-port enumeration up to 3 times, 300 ms apart, while the device is still connected. This is the essential fix.
  - `pico-pio-usb-fm1.diff`:
    - Debounce disconnect over 20 SE0 frames. Without it, the FM-1 was dropped right after a bus reset on Feather resets.
    - Run a disconnect check while the port waits for its reset (the stuck-"connected" bug).
    - Raise the full-speed reply timeout from 3 µs to 20 µs, which the first full FM-1 enumeration needed.
  - `feather-enum-bufsize.diff`: `CFG_TUH_ENUMERATION_BUFSIZE=512` for the 293-byte descriptor.
  - Also: run at 120 MHz (`-DSYS_CLK_HZ=120000000 -DPLL_SYS_VCO_FREQ_HZ=1440000000 -DPLL_SYS_POSTDIV1=6 -DPLL_SYS_POSTDIV2=2`).
  - **No external pull-downs needed:** with the 15 kΩ resistors removed, 5 of 5 hot-plugs still mounted (same retry pattern).
  - Still to check: the Feather itself (`build-feather-fm1`: non-debug, 512 buffer, 120 MHz, both patches), and which patches are strictly needed.
- **USB-MIDI transport:** `adafruit_usb_host_midi` has no `write()` and loses SysEx boundaries, so `lib/fm1usb.py` implements USB-MIDI 1.0 SysEx packetizing and reassembly on `usb.core`.

## Phase 3: Install path on device

- cmd 49, then arm, then the stage 1 serve loop streamed from SD, then re-enumeration (release, poll, reclaim, re-probe), then stage 2, then verify. Uses the same `fm1proto.py` that was tested against the simulator.

## Phase 4: UI

- Firmware list, details screen, and Install, with an extra confirmation for legacy routes.
- Progress bar driven by read-request addresses. Show "Restarting…" during re-enumeration.
- "Back to official V15".
- Display and touch go behind a small abstraction.

## Phase 5: Hardening, then extras

- Timeouts, duplicate finish requests, resume when the FM-1 is already in loader mode, and a low-battery warning.
- Then: V15 factory voice-bank restore (cmds 33/34), then a Fruit Jam port.

## Recovery

Before the first real flash in Phase 1:
- Have `fm1_rescue.py` (https://thefirmwarehub.com/rescue/fm1_rescue.py) ready on a Linux machine, or have MvaveFM1Unbricker / Transporter (RP2040) available.
- Know how to put the FM-1 into the ROM bootloader ("UBOOT1.00", USB mass storage).
- Keep a copy of stock `FM-1_015.fwsc`.
- Record the FM-1's current identity (cmd 17) before flashing.

## Layout

```
lib/fm1proto.py      # protocol + package parsing (CPython and CircuitPython)
lib/fm1update.py     # install state machine over a transport (CPython and CircuitPython)
lib/fm1usb.py        # USB-MIDI host transport (CircuitPython)
lib/ui/              # display/touch abstraction and screens
code.py              # device entry point
tools/               # make_sd.py, flash_cli.py, fake_fm1.py (simulated FM-1)
tests/               # CPython unit tests
ref/                 # upstream reference clones (gitignored)
```

## Workflow

- `main` stays working. Each feature gets a branch (for example `phase0-proto`), merged by PR.
- License: GPL-3.0, because the protocol logic is ported from `WebUpdate.js` (GPL-3.0-only WITH GPL-3.0-linking-exception).
