# FM-1 Flasher: plan

See `fm1-firmware-flasher-brief.md` for the protocol and package-format details this plan builds on.

Guiding idea: prove the protocol from a computer first, so USB-host problems and protocol problems are never debugged at the same time.

## Hardware

- **Adafruit Feather RP2040 USB Host** (USB-C for CIRCUITPY, USB-A host via PIO USB).
- **TFT FeatherWing V2 3.5" 480x320, capacitive touch** ([PID 5872](https://www.adafruit.com/product/5872)). HX8357 display, capacitive touch controller, and microSD on shared SPI. Pin and controller details are confirmed in Phase 2.
- An M-VAVE FM-1 we're willing to flash. Before any write, we have the recovery path ready (see "Recovery" below).
- Later: Fruit Jam port. Optional: 2.4" FeatherWing support behind the same display abstraction.

## Phase 0: Desk work on CPython, no hardware

1. Clone `m-vave/fm1_open` at `4c7496daac04a95ff10d1afdcc8f9ead2dbabc41` into `ref/` (gitignored) and read all of `sdk/WebUpdate.js`, especially retries, receive-queue behavior, and the checks in `connect()` and `prepare()`.
2. `lib/fm1proto.py`: one module that runs on both CPython and CircuitPython. Contains `crc16`, `decode_header`, `pack7`/`unpack7`, frame build and parse, `inspect_package`, the image-to-file offset mapping, and a streaming `PackageReader` that caches only `image[0:940]`.
3. Unit tests against `FM-1_015.fwsc` and a couple of community packages.
4. `tools/fake_fm1.py`: a simulator that issues read requests and finish markers, so the serve loop is tested without a device.
5. `tools/make_sd.py`: parses each package and writes `meta.json` (product, build_id, family, bytes, sha256, loader_sha256, kind, source_url, license).
6. Research: where `build_id` comes from for community firmwares, and how the hub's and Felucca's installer JS differ from `WebUpdate.js`.

## Phase 1: Reference flasher on desktop

- `tools/flash_cli.py` (`python-rtmidi` or `mido`) runs the full install sequence against the real FM-1. This proves the protocol, mode selection, and re-enumeration timing on hardware that's easy to debug.

## Phase 2: Hardware spikes on the Feather

- Check whether the USB-A host port gets 5 V on LiPo. If it doesn't, add a 5 V boost converter.
- Check for conflicts between the PIO USB pins and the FeatherWing's TFT CS, DC, SD CS, and touch pins.
- Check whether CircuitPython has `hashlib` with sha256.
- Milestone: send cmd 17 to the FM-1 with `usb.core` and print the identity. Try `adafruit_usb_host_midi` first, and fall back to hand-built USB-MIDI 1.0 packets if long SysEx breaks.

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
lib/fm1usb.py        # USB-MIDI host transport (CircuitPython)
lib/ui/              # display/touch abstraction and screens
code.py              # device entry point
tools/               # make_sd.py, flash_cli.py, fake_fm1.py
tests/               # CPython unit tests
ref/                 # upstream reference clones (gitignored)
```

## Workflow

- `main` stays working. Each feature gets a branch (for example `phase0-proto`), merged by PR.
- License: GPL-3.0, because the protocol logic is ported from `WebUpdate.js` (GPL-3.0-only WITH GPL-3.0-linking-exception).
