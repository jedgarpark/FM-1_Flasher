# SPDX-License-Identifier: GPL-3.0-only
"""Settings, from the gear on the list (boards with WiFi, the Metro ESP32-P4).

For now it shows the WiFi network from settings.toml and whether the board is
on it; entering WiFi details on the screen comes here later (docs/PLAN-v2.md).
v1 never imports this.
"""
import displayio

from fm1ui import catalog as C
from fm1ui import ui
from fm1ui.layout import L
from fm1ui.screens import Screen


class SettingsScreen(Screen):

    def build(self):
        W, H = L.W, L.H
        g = displayio.Group()
        g.append(ui.rect(0, 0, W, H, ui.BG))
        self.back = ui.Button("Back", *L.BACK_BTN)
        g.append(self.back.group)
        g.append(ui.text(ui.TITLE, "Settings", ui.FG, W // 2, L.SETTINGS_TITLE_Y, (0.5, 0.5)))

        status = getattr(self.app.updater, "status", None)
        ssid, ip = status() if status else (None, None)
        x, y = L.DESC_LEFT + 4, L.SETTINGS_TEXT_Y
        g.append(ui.text(ui.NAME, "WiFi", ui.FG, x, y, (0, 0)))
        y += 26
        fit = lambda s: C.ellipsize(s, lambda t: ui.width(ui.BODY, t), W - 2 * x)  # noqa: E731
        if ssid:
            g.append(ui.text(ui.BODY, fit("Network: " + ssid), ui.TEXT, x, y, (0, 0)))
            y += 22
            state, color = ("Connected, " + ip, ui.OK) if ip else ("Not connected", ui.WARN)
            g.append(ui.text(ui.BODY, state, color, x, y, (0, 0)))
        else:
            g.append(ui.text(ui.BODY, "No network set up.", ui.WARN, x, y, (0, 0)))
        y += 30
        for line in ("Set CIRCUITPY_WIFI_SSID and", "CIRCUITPY_WIFI_PASSWORD in", "settings.toml on CIRCUITPY."):
            g.append(ui.text(ui.BODY, line, ui.DIM, x, y, (0, 0)))
            y += 20
        self.group = g
        return g

    def target(self, x, y):
        return self.back.group if self.back.hit(x, y) else None

    def tap(self, x, y):
        if self.back.hit(x, y):
            self.app.pop()

    def swipe(self, dx):
        if dx > 0:
            self.app.pop()
