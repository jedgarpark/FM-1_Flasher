# CircuitPython patches for the FM-1 flasher

All against **CircuitPython 10.3.1** unless the table says otherwise. Apply each from the path it was made in
(`git apply` from the CircuitPython root, or from the submodule for
`tinyusb-*` and `pico-pio-usb-*`). See `DEVNOTES.md` §4–5 for the evidence
behind each verdict.

| Patch | Applies in | What it does | Needed? |
|---|---|---|---|
| `tinyusb-enum-retry.diff` | `lib/tinyusb` | Retries a failed root-port enumeration (up to 10 attempts, 500 ms apart) while the device is still connected. The FM-1 always fails its first enumeration after a bus reset. | **Yes**, on any host controller |
| `tinyusb-enum-retry-stats.diff` | `lib/tinyusb` | The same retry, plus a weak `fm1_stats[]` counter array for `device/fm1_stats.py` | Test builds only |
| `feather-enum-bufsize.diff` | CircuitPython root | `CFG_TUH_ENUMERATION_BUFSIZE=512` for the Feather RP2040 USB Host (the FM-1's descriptor is 293 bytes, the default is 288) | **Yes** |
| `feather-max3421e.diff` | CircuitPython root | Feather RP2040 USB Host build for the MAX3421E FeatherWing: `CIRCUITPY_MAX3421E = 1`, `CIRCUITPY_USB_HOST = 0`, `board.c` guard, 512 buffer, 120 MHz | **Yes**, for the recommended hardware |
| `cp11-feather-pio.diff` | CircuitPython root (**11.0.0-alpha.2**) | The Feather's built-in PIO port on CircuitPython 11: `CFG_TUH_ENUMERATION_BUFSIZE=512` and 120 MHz. Nothing else is needed. | **Yes**, for CircuitPython 11 on the PIO port |
| `pico-pio-usb-fm1.diff` | `ports/raspberrypi/lib/Pico-PIO-USB` | Disconnect check while waiting for reset; 20-frame disconnect debounce; full-speed reply timeout 3 → 20 µs | Only for the built-in PIO port. Keep the first two; the timeout change isn't needed |
| `pico-pio-usb-fm1-stats.diff` | `ports/raspberrypi/lib/Pico-PIO-USB` | The same, plus counters (RX waits, absorbed glitches, disconnects) | Test builds only |

**On CircuitPython 11** (11.0.0-alpha.2 and `main` as of 2026-10-27), TinyUSB
already retries a failed enumeration, so the `tinyusb-*` patches aren't needed.
The PIO port needs only `CFG_TUH_ENUMERATION_BUFSIZE=512` and 120 MHz. Those
are the same lines as `feather-enum-bufsize.diff` plus the clock flags below,
added to the board's `mpconfigboard.mk`.

The 120 MHz clock (`-DSYS_CLK_HZ=120000000 -DPLL_SYS_VCO_FREQ_HZ=1440000000
-DPLL_SYS_POSTDIV1=6 -DPLL_SYS_POSTDIV2=2`) gives Pico-PIO-USB integer clock
dividers. It's **required** on the PIO port: at the default 125 MHz about 30 %
of USB writes to the FM-1 failed.

Long TinyUSB enumeration waits were tried and made things worse. They are not
in any patch here.
