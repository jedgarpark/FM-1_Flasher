# FM-1 Flasher

A portable CircuitPython device that stores M-VAVE FM-1 alt firmwares on a microSD card and installs them over USB MIDI SysEx, with no computer needed. Plug the FM-1 into the flasher, pick a firmware on the touchscreen, and tap Install.

**Status:** works end to end on the touchscreen. Browse the firmwares on the card as picture cards or a two-column text list, mark favourites, open a firmware's details, and install it. Installs take about 70 s (V15 → SLOOP 70 s, SLOOP → V15 with factory voices 73 s, V15 → ChoralRoot 69 s).

- [PLAN.md](PLAN.md): roadmap and current status.
- [DEVNOTES.md](DEVNOTES.md): what we tried and learned, with evidence.
- [fm1-firmware-flasher-brief.md](fm1-firmware-flasher-brief.md): protocol notes.
- [patches/README.md](patches/README.md): the CircuitPython patches the device needs.

## Hardware

- Adafruit Feather RP2040 USB Host, running CircuitPython 11.0.0-alpha.2 built with the patches in `patches/`
- The FM-1 plugs into the Feather's built-in USB-A (PIO) port through a long USB cable (2 m tested, Adafruit 6279). With a short cable the FM-1 stays silent.
- Adafruit TFT FeatherWing V2 3.5" 480x320 capacitive touch (PID 5872): the display, touch, and the microSD card that holds the firmwares

The Adafruit USB Host FeatherWing with MAX3421E (PID 5858) also works as the USB host, on CircuitPython 10.3.1, but its D9/D10 clash with the TFT FeatherWing. See [PLAN.md](PLAN.md) for the alternatives.

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

### Refreshing the firmware list from the FM-1 Firmware Hub

The flasher never goes online. To pick up new firmwares, or new versions, from [thefirmwarehub.com](https://thefirmwarehub.com/), refresh the card from a computer:

1. Power off the flasher and take the microSD card out of the TFT FeatherWing.
2. Put the card in a card reader on the computer. On a Mac it mounts as `/Volumes/<name>`, for example `/Volumes/FMFLASH`.
3. Install Pillow once, for the card pictures: `python3 -m pip install Pillow`.
4. Run:

   ```sh
   tools/make_sd.py --out /Volumes/FMFLASH --catalog
   ```

   With no ids, this fetches every firmware in the catalogue plus M-VAVE V15. Packages already on the card are kept when their SHA-256 still matches the catalogue, so only new or changed ones download. Each download is checked against the catalogue's SHA-256 and size, then with the device's full package checks. The run ends with `index: N firmwares` and exits with an error if any package was rejected.
5. Eject the card, put it back in the flasher, and power it on. The list screen shows the new firmwares and the catalogue's date.

Notes:
- **Removed firmwares stay on the card.** A firmware the hub drops isn't removed. The list shows every folder in `firmware/`, so delete the folder by hand, then rerun the command (or any `make_sd.py` run) to rebuild `firmware/index.txt`.
- **Favourites survive.** They're kept with the install record in `flasher.json` at the card's root, which `make_sd.py` never touches.
- **Don't write to the card while it's in the flasher.** With the flasher plugged into the computer, the card also appears as a drive (FMFLASH). Writing to it there while the flasher is running hasn't been tested and could corrupt the card. Eject that drive before an install.

## License

GPL-3.0. The update protocol is ported from M-VAVE's `WebUpdate.js` (GPL-3.0-only WITH GPL-3.0-linking-exception). Each firmware keeps its own license.

Flashing firmware carries a risk of leaving the FM-1 unbootable. Keep both devices powered during an install, and have the rescue tools listed in the plan available.
