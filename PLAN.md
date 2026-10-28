# FM-1 Flasher: plan

See `fm1-firmware-flasher-brief.md` for the protocol and package format, and
**`DEVNOTES.md` for the history: what we tried, what we learned, and the
evidence**. This file is the plan and the current status.

Guiding idea: prove the protocol from a computer first, so USB-host problems and protocol problems are never debugged at the same time.

## Hardware

- **Adafruit Feather RP2040 USB Host.** The CircuitPython build must include the TinyUSB enumeration retry and the 512-byte enumeration buffer (`patches/`).
- **USB host for the FM-1**, one of:
  - **The Feather's built-in PIO USB-A port with a long cable** (2 m tested, Adafruit 6279), on CircuitPython 11 with `cp11-feather-pio.diff` and `pico-pio-usb-cp11-idle-disconnect.diff`. A short cable leaves the FM-1 silent, stuck in USB host role (DEVNOTES §6.6–6.7).
  - **A USB-A jack pigtail on D11/D12** (Adafruit 4449, 30 cm), with `cp11-feather-pigtail.diff` instead. Frees the built-in socket.
  - **Adafruit USB Host FeatherWing, MAX3421E ([PID 5858](https://www.adafruit.com/product/5858))**, on CS D10, IRQ D9 and `board.SPI()` (DEVNOTES §4.8). Fine with short cables, but clashes with the TFT FeatherWing.
- **TFT FeatherWing V2 3.5" 480x320, capacitive touch ([PID 5872](https://www.adafruit.com/product/5872)):** HX8357 display, touch, and microSD. Its TFT CS (D9) and DC (D10) clash with the MAX3421E wing, but not with the PIO port or the pigtail.
- An M-VAVE FM-1. Before any write, the recovery path is ready (see "Recovery").
- Later: Fruit Jam port. Optional: 2.4" FeatherWing support behind the same display abstraction.

## Status

| Phase | Status |
|---|---|
| 0: protocol, parser, simulator, SD prep (CPython) | Done (DEVNOTES §2) |
| 1: desktop flasher on real hardware | Done: V15 ↔ SLOOP both ways, rescue path tested (§3) |
| 2: hardware spikes on the Feather | Done: FM-1 enumeration fixed, MAX3421E chosen, long SysEx verified (§4–5) |
| 3: install path on device | Working from the REPL: V15 → SLOOP 70 s, SLOOP → V15 + voices 73 s, V15 → ChoralRoot 69 s (§6). Open items below |
| 4: UI | Not started |
| 5: hardening, extras | Not started |

## Phase 0: Desk work on CPython, no hardware (done)

`lib/fm1proto.py` (framing, package parsing, streaming reads), `lib/fm1update.py` (install state machine), `tools/fake_fm1.py` (simulator), `tools/make_sd.py` (firmware folders + `meta.json`), and `tests/`. Both install routes, `open`/`stock` and `community`, are implemented; `meta.json` `kind` is `open`, `stock` or `community`.

## Phase 1: Reference flasher on desktop (done)

`tools/flash_cli.py` (python-rtmidi): `ports`, `probe`, and `install DIR` with `--dry-run`/`--force`/`--yes` and a JSONL request log in `logs/`. It installed stock V15 → SLOOP 2.8 in 43 s and SLOOP → V15 with the factory voice restore in 33 s.

## Phase 2: Hardware spikes on the Feather (done)

- **USB host:** the MAX3421E wing with patched CircuitPython 10.3.1, or **on CircuitPython 11 the built-in PIO port** with the 512-byte buffer, 120 MHz and the Pico-PIO-USB disconnect check (`patches/README.md`). TinyUSB on 11 retries enumeration itself. On the PIO port the FM-1 needs a long cable (2 m tested) or the 30 cm D11/D12 pigtail: with a short cable it goes silent in USB host role (DEVNOTES §6.6–6.7). Full installs worked both ways.
- **`fm1usb`:** USB-MIDI SysEx over `usb.core`, since `adafruit_usb_host_midi` can't write SysEx.
- **Long SysEx:** verified with the stress test.
- **`hashlib`:** sha256 is available only as `hashlib.new("sha256")`, which `fm1proto` handles.
- **Not yet checked:**
  - **Battery operation.** With USB connected, the LiPo is switched out of the boost input, so only a battery-only test is meaningful.
  - **Pin conflicts with the TFT FeatherWing.**

## Phase 3: Install path on device

Today, `device/fm1_install.py` runs from the REPL after `device/fm1_max_setup.py`:
1. verify the package
2. dry run
3. `run(folder, go=True)`

It uses 64-byte paced writes with adaptive slow-down, and prints a ring of recent messages on failure.

Open items:
- [ ] Read packages from microSD instead of CIRCUITPY.
- [ ] Verify the package sha256 once, when it's copied or prepared, and cache the result. That saves 8–12 s per install.
- [ ] Handle a missing FM-1. If none appears within ~10 s, at the start or after each self-reboot during an install, prompt the user (check the cable, power-cycle) instead of timing out.
- [x] Retry the V15 voice restore once when V15 re-enumerates after its first boot (DEVNOTES §6.7).
- [ ] CircuitPython 11 `hashlib` can give wrong digests on a fragmented heap (DEVNOTES §6.7). Until it's fixed, soft-reset before an install; then file it upstream with a repro.
- [ ] Optionally start slowed for community firmware and loaders, to avoid the ~3 s loader retry when a reply is lost.
- [ ] Fix the `RealCommunityPackages` test's folder layout (`FM1_TEST_PKGS`).
- [ ] Update the upstream issue draft in `docs/`: the enumeration retry (TinyUSB) and the buffer size (CircuitPython). Post only after review.

## Phase 4: UI

- Firmware list, details screen, and Install, with an extra confirmation for legacy routes.
- Progress bar driven by read-request addresses. Show "Restarting…" during re-enumeration, and the power-cycle prompt when the FM-1 doesn't reappear.
- "Back to official V15".
- Display and touch go behind a small abstraction.
- Prerequisite with the MAX3421E wing only: resolve its D9/D10 pin clash with the TFT FeatherWing.

## Phase 5: Hardening, then extras

- Low-battery warning, battery-only operation, and longer soak tests across more catalogue firmwares.
- Then a Fruit Jam port.

## Recovery

- **A failed install before the loader writes** (as seen twice in Phase 3): power-cycle the FM-1. The previous firmware boots.
- **Manual loader:** hold OCT− while powering on.
- **Rescue key:** `F0 22 24 35 7D F7` drops into the ROM UBOOT bootloader ("UBOOT1.00", USB mass storage).
- **Pico FM-1 Transporter:**
  - Build kurogedelic/FM-1-transporter @ `a632d92` with jl-uboot-tool `wl82loader.bin`, and drive it with MvaveFM1Unbricker `fm1_transporter_recover.py` (`info`, `dump`, `recover PACKAGE`).
  - Wiring: GP0 to D+, GP1 to D−, GND, no VBUS.
  - The UF2 is `ref/FM-1-transporter/build-pico/fm1_transporter.uf2`. Tested from macOS (DEVNOTES §3).
- **Plain-cable rescue tools** (`fm1_rescue.py`, `fm1_unbrick.py`) need SCSI pass-through, so Linux or Windows only.
- **Baseline flash dump:** `ref/flash-dumps/fm1-transporter-dump-20261022-213229.bin` (sha256 `8a4d2330…`). Keep a copy of stock `FM-1_015.fwsc`.

## Layout

```
lib/fm1proto.py      # protocol + package parsing (CPython and CircuitPython)
lib/fm1update.py     # install state machine over a transport (CPython and CircuitPython)
lib/fm1usb.py        # USB-MIDI host transport (CircuitPython)
device/              # on-device scripts: installer, MAX3421E setup, diagnostics
tools/               # make_sd.py, flash_cli.py, fake_fm1.py (simulated FM-1), usb_descriptors.py
tests/               # CPython unit tests
patches/             # CircuitPython / TinyUSB / Pico-PIO-USB patches (see patches/README.md)
docs/                # upstream issue drafts
ref/                 # upstream clones, builds, flash dumps (gitignored)
```

Planned: `lib/ui/` (display/touch abstraction and screens) and `code.py` (device entry point).

## Workflow

- `main` stays working. Each feature gets a branch (for example `phase0-proto`), merged by PR.
- License: GPL-3.0, because the protocol logic is ported from `WebUpdate.js` (GPL-3.0-only WITH GPL-3.0-linking-exception).
