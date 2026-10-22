# FM-1 Flasher

A portable CircuitPython device that stores M-VAVE FM-1 alt firmwares on a microSD card and installs them over USB MIDI SysEx, with no computer needed. Plug the FM-1 into the flasher, pick a firmware on the touchscreen, and tap Install.

**Status:** early development. See [PLAN.md](PLAN.md) for the roadmap and [fm1-firmware-flasher-brief.md](fm1-firmware-flasher-brief.md) for the protocol notes.

## Hardware

- Adafruit Feather RP2040 USB Host
- Adafruit TFT FeatherWing V2 3.5" 480x320 capacitive touch (PID 5872)

## License

GPL-3.0. The update protocol is ported from M-VAVE's `WebUpdate.js` (GPL-3.0-only WITH GPL-3.0-linking-exception). Each firmware keeps its own license.

Flashing firmware carries a risk of leaving the FM-1 unbootable. Keep both devices powered during an install, and have the rescue tools listed in the plan available.
