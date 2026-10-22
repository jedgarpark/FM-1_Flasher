# FM-1 Flasher

A portable CircuitPython device that stores M-VAVE FM-1 alt firmwares on a microSD card and installs them over USB MIDI SysEx, with no computer needed. Plug the FM-1 into the flasher, pick a firmware on the touchscreen, and tap Install.

**Status:** early development. See [PLAN.md](PLAN.md) for the roadmap and [fm1-firmware-flasher-brief.md](fm1-firmware-flasher-brief.md) for the protocol notes.

## Hardware

- Adafruit Feather RP2040 USB Host
- Adafruit TFT FeatherWing V2 3.5" 480x320 capacitive touch (PID 5872)

## Development

```sh
git clone https://github.com/m-vave/fm1_open ref/fm1_open    # reference updater and stock V15 (gitignored)
git -C ref/fm1_open checkout 4c7496daac04a95ff10d1afdcc8f9ead2dbabc41
python3 -m unittest discover -s tests                         # protocol, package, and simulated install tests
FM1_TEST_PKGS=path/to/fwsc/folder python3 -m unittest discover -s tests   # also run real packages
node tests/make_golden.mjs                                    # regenerate golden vectors from WebUpdate.js
```

### Preparing an SD card

```sh
tools/make_sd.py --out /Volumes/SDCARD --fwsc ref/fm1_open/sdk/firmware/FM-1_015.fwsc \
    --name "M-VAVE V15 (stock)" --author M-VAVE --slug stock-v15
tools/make_sd.py --out /Volumes/SDCARD --catalog sloop felucca   # from the FM-1 Firmware Hub; omit ids for all
```

Each firmware goes in `firmware/<slug>/` as the `.fwsc` and a `meta.json`. Every package is checked the same way the device checks it.

## License

GPL-3.0. The update protocol is ported from M-VAVE's `WebUpdate.js` (GPL-3.0-only WITH GPL-3.0-linking-exception). Each firmware keeps its own license.

Flashing firmware carries a risk of leaving the FM-1 unbootable. Keep both devices powered during an install, and have the rescue tools listed in the plan available.
