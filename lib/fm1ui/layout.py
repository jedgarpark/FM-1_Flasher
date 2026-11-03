# SPDX-License-Identifier: GPL-3.0-only
"""Screen layouts: every size and position the screens use, per display.

L is the layout in use. use(width, height) picks one when the App starts;
screens read L's attributes when they build, so nothing is cached at import.
Rects are (x, y, w, h). Each layout is a function, so only the one in use is
ever built (v1's RAM is tight, DEVNOTES 6.11).

_big() is v1's 480x320 (TFT FeatherWing V2 3.5"), _small() the 320x240 2.8" TFT
Touch Shield on the Metro ESP32-P4 (docs/PLAN-v2.md).
"""


class Layout:
    def set(self, values):
        for k, v in values.items():
            setattr(self, k, v)


def _big():
    return dict(
    W=480, H=320,
    # list: header
    TITLE_AT=(12, 18),  # "FM-1 Flasher", or None
    TAG_BTN=(124, 5, 96, 26),
    FAV_TAB=(226, 5, 64, 26),
    FM1_RIGHT=468,  # the FM-1 status's right end
    HEADER_Y=18,
    CONNECT_BTN=(322, 5, 150, 26),
    TABS_ZONE=(110, 290),  # x range where header taps go to the two tabs
    CONNECT_ZONE_X=300,  # header taps from here go to Connect FM-1
    # list: cards
    COLS=3, ROWS=2,  # six cards: the picture pool is ui.SLOTS = 6
    CARD_W=151, CARD_H=118, GAP=6,
    GRID_X=7, GRID_Y=40,
    THUMB=80,  # card picture size: TILE, or TILE // 2
    CARD_THUMB_Y=8,
    CARD_NAME_Y=90,
    CARD_VERSION_Y=106,  # or None: no version line on the card
    BAND_FULL=False,  # INSTALLED band across the card, not just the picture
    EMPTY_Y=160,
    # list: text rows
    ROW_W=230, ROW_H=28, ROW_PITCH=30,
    LIST_ROWS=8,  # two columns
    ROW_HEART_DY=9,
    # list: footer
    PREV=(7, 286, 64, 32),
    NEXT=(409, 286, 64, 32),
    VIEW=(80, 286, 72, 32),  # the grid/list toggle
    VIEW_ICON_DY=10,
    PAGE_Y=296,
    PAGE_X=None,  # "Page N of M" centre; None: the screen's
    UPDATE_BTN=None,  # Update firmwares (boards with WiFi), or None
    DATE_Y=311,  # catalogue date, or None
    FOOTER_LEFT_X=160,  # footer taps left of this: prev arrow or view toggle
    NEXT_ZONE_W=140,  # footer taps this close to the right edge: next arrow
    # details
    BACK_BTN=(8, 8, 84, 30),
    HEART_BTN=(424, 8, 48, 30),
    HEART_AT=(442, 18),
    PIC=("large.bmp", 160),
    PIC_AT=(12, 48),
    DETAIL_X=186,
    NAME_W_PAD=60,  # name ellipsized to W - DETAIL_X - this
    DESC_BOTTOM=276,  # description lines end above this
    PIC_BOTTOM=212,  # below this, description lines use the full width
    DESC_LEFT=12,
    DESC_LAST_W=300,  # last full-width line's width, before ellipsis
    INSTALL_BTN=(316, 282, 156, 34),
    NOTE_AT=(12, 299),
    NOTE_W=None,  # wrap the bar's note to this width, or None
    # confirm
    CONFIRM_PANEL=(30, 30, 420, 260),
    CONFIRM_TITLE_AT=(50, 52),
    CONFIRM_W=380,
    CONFIRM_TEXT_Y=92,
    CONFIRM_LINES=7,
    CANCEL_BTN=(50, 234, 170, 40),
    GO_BTN=(260, 234, 170, 40),
    # progress
    PROGRESS_TITLE_Y=50,
    PROGRESS_TITLE_W=440,
    PROGRESS_SUB_Y=84,
    BAR=(40, 156, 400, 26),
    PROGRESS_NOTE_Y=232,
    OK_BTN=(170, 266, 140, 40),
)


def _small():
    return dict(
    W=320, H=240,
    TITLE_AT=None,
    TAG_BTN=(6, 5, 84, 26),
    FAV_TAB=(96, 5, 56, 26),
    FM1_RIGHT=312,
    HEADER_Y=18,
    CONNECT_BTN=(176, 5, 138, 26),
    TABS_ZONE=(0, 160),
    CONNECT_ZONE_X=164,
    COLS=3, ROWS=2,
    CARD_W=100, CARD_H=82, GAP=4,
    GRID_X=6, GRID_Y=36,
    THUMB=40,
    CARD_THUMB_Y=8,
    CARD_NAME_Y=52,
    CARD_VERSION_Y=68,
    BAND_FULL=True,
    EMPTY_Y=110,
    ROW_W=152, ROW_H=26, ROW_PITCH=28,
    LIST_ROWS=6,
    ROW_HEART_DY=8,
    PREV=(6, 208, 52, 28),
    NEXT=(262, 208, 52, 28),
    VIEW=(64, 208, 60, 28),
    VIEW_ICON_DY=8,
    PAGE_Y=222,
    PAGE_X=193,  # between the view toggle and the next arrow (without Update)
    UPDATE_BTN=(140, 208, 72, 28),
    DATE_Y=None,
    FOOTER_LEFT_X=132,
    NEXT_ZONE_W=100,
    BACK_BTN=(6, 6, 64, 26),
    HEART_BTN=(270, 6, 44, 26),
    HEART_AT=(285, 13),
    PIC=("thumb.bmp", 80),
    PIC_AT=(8, 38),
    DETAIL_X=98,
    NAME_W_PAD=8,
    DESC_BOTTOM=198,
    PIC_BOTTOM=124,
    DESC_LEFT=8,
    DESC_LAST_W=200,
    INSTALL_BTN=(196, 204, 118, 30),
    NOTE_AT=(8, 212),
    NOTE_W=180,
    CONFIRM_PANEL=(6, 6, 308, 228),
    CONFIRM_TITLE_AT=(18, 22),
    CONFIRM_W=284,
    CONFIRM_TEXT_Y=56,
    CONFIRM_LINES=6,
    CANCEL_BTN=(18, 182, 132, 40),
    GO_BTN=(170, 182, 132, 40),
    PROGRESS_TITLE_Y=24,
    PROGRESS_TITLE_W=300,
    PROGRESS_SUB_Y=54,
    BAR=(16, 100, 288, 24),
    PROGRESS_NOTE_Y=160,
    OK_BTN=(100, 198, 120, 34),
)


L = Layout()
L.set(_big())


def use(width, height):
    """Make L the layout for a width x height display: 320x240 gets the
    small one, anything else v1's."""
    L.set(_small() if (width, height) == (320, 240) else _big())
