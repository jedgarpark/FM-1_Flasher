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
