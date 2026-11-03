# SPDX-License-Identifier: GPL-3.0-only
"""FM-1 Flasher: the touch UI on the TFT FeatherWing V2 3.5".

Copy to CIRCUITPY as code.py, with lib/fm1ui, the fm1 libraries, fonts/ and
the display, touch, text and font libraries (see PLAN.md, Phase 4).
Firmware comes from /sd/firmware (tools/make_sd.py), or /firmware on CIRCUITPY.
On boards with WiFi (the Metro ESP32-P4) the list offers Update firmwares, and a
card without firmware starts there.
"""
import gc
import sys

import fm1ui.console

fm1ui.console.show()  # first, before the slow imports: what the restart is for
# Then drop it, so its code doesn't stay in RAM. None first: a deleted dict
# entry's value stays in the table, where the GC still finds it (DEVNOTES §6.11).
sys.modules["fm1ui.console"] = fm1ui.console = None
del sys.modules["fm1ui.console"], fm1ui.console

from fm1ui import device as D  # noqa: E402
from fm1ui import ui  # noqa: E402

display, spi = D.display_setup()
D.splash(display)  # after a start, not a reload
D.host_setup(spi)
sd = D.mount_sd(spi)
root = D.firmware_root(sd)
state = D.DeviceState("/sd/flasher.json" if sd else "/flasher.json")
pending = D.pending_install()

fill = False
if root is None and sd and D.Network is not None:
    # An empty card on a board with WiFi: fill it from the hub.
    import fm1catalog
    fm1catalog.mkdirs("/sd/firmware")
    fm1catalog.write_index("/sd/firmware")
    root, fill = "/sd/firmware", True

if root is None:
    import displayio
    D.display_redo(display)  # after a start, not a reload
    w, h = display.width, display.height
    g = displayio.Group()
    g.append(ui.rect(0, 0, w, h, ui.BG))
    g.append(ui.text(ui.NAME, "No firmware found", ui.FG, w // 2, h // 2 - 20, (0.5, 0.5)))
    hint = "Put a card from tools/make_sd.py in the slot." if sd or D.Network is None else "Put a microSD card in the slot."
    g.append(ui.text(ui.BODY, hint, ui.DIM, w // 2, h // 2 + 10, (0.5, 0.5)))
    display.root_group = g
    display.refresh()
    while True:
        pass

from fm1ui import app as A  # noqa: E402

gc.collect()
if pending:
    # Fresh heap: no FM-1 probe and no list screen until the install is done.
    app = A.App(display, D.Touch(), root, state, None, D.Installer(), pictures=False)
    entry = app.entry(pending)
    if entry:
        D.run(app, entry)
        while True:
            app.step()
app = A.App(display, D.Touch(), root, state, D.Probe(), D.Installer(),
            updater=D.Network() if D.Network is not None else None)
print("free RAM:", gc.mem_free())
D.display_redo(display)  # after a start, not a reload
home = None  # the list; with Settings > Scroll pages on the Metro, the one that scrolls
if D.Network is not None:
    from fm1ui import layout
    if layout.L.SCROLL:
        from fm1ui import flat
        home = flat.list_screen(app)
if fill:
    from fm1ui import screens as S
    from fm1ui.update import UpdateScreen
    home = home or S.ListScreen(app)
    app.stack.append(home)  # under it: where Back and OK go
    app.run(UpdateScreen(app))
app.run(home)
