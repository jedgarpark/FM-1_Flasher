# SPDX-License-Identifier: GPL-3.0-only
"""FM-1 Flasher: the touch UI on the TFT FeatherWing V2 3.5".

Copy to CIRCUITPY as code.py, with lib/fm1ui, the fm1 libraries, fonts/ and
the display, touch, text and font libraries (see PLAN.md, Phase 4).
Firmware comes from /sd/firmware (tools/make_sd.py), or /firmware on CIRCUITPY.
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
D.host_setup(spi)
sd = D.mount_sd(spi)
root = D.firmware_root(sd)
state = D.DeviceState("/sd/flasher.json" if sd else "/flasher.json")
pending = D.pending_install()

if root is None:
    import displayio
    D.display_redo(display)  # after a power-on only
    g = displayio.Group()
    g.append(ui.rect(0, 0, 480, 320, ui.BG))
    g.append(ui.text(ui.NAME, "No firmware found", ui.FG, 240, 140, (0.5, 0.5)))
    g.append(ui.text(ui.BODY, "Put the card from tools/make_sd.py in the wing's slot.", ui.DIM, 240, 170, (0.5, 0.5)))
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
app = A.App(display, D.Touch(), root, state, D.Probe(), D.Installer())
print("free RAM:", gc.mem_free())
D.display_redo(display)  # after a power-on only
app.run()
