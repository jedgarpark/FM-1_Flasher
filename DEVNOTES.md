# FM-1 Flasher: development notes

How we got here: what we tried, what we expected, what happened, and what we
concluded, dead ends included. `PLAN.md` has the plan and the current status;
this file has the story and the evidence. Dates are 2026.

**Contents**
1. [Where things stand](#1-where-things-stand)
2. [Protocol work (Phase 0, Oct 22)](#2-protocol-work-phase-0-oct-22)
3. [Desktop flasher and rescue path (Phase 1, Oct 22)](#3-desktop-flasher-and-rescue-path-phase-1-oct-22)
4. [Getting the FM-1 to enumerate on the Feather (Phase 2, Oct 22–26)](#4-getting-the-fm-1-to-enumerate-on-the-feather-phase-2-oct-2226)
5. [Patch verdicts](#5-patch-verdicts)
6. [Installing from the Feather (Phase 3, Oct 26–27)](#6-installing-from-the-feather-phase-3-oct-2627)
7. [Tools and techniques worth reusing](#7-tools-and-techniques-worth-reusing)
8. [Superseded conclusions](#8-superseded-conclusions)
9. [Open questions](#9-open-questions)

---

## 1. Where things stand

- A Feather RP2040 USB Host with the **MAX3421E USB Host FeatherWing** installs
  FM-1 firmware with no computer involved. Each run took about 70 s and lost no replies:
  - stock V15 → SLOOP 2.8: 70 s
  - SLOOP → V15 with factory voices: 73 s
  - V15 → ChoralRoot 0.27: 69 s

  The Mac's desktop flasher does the same in 33–43 s.
- It needs a **custom CircuitPython 10.3.1** with two changes, a TinyUSB
  enumeration retry and a 512-byte enumeration buffer (`patches/`, see
  [§5](#5-patch-verdicts)).
- The Feather's **built-in USB-A host port** (PIO-USB) also works with those
  changes, but it is unreliable with the FM-1: 70–80 % of attaches succeed, and
  the FM-1 sometimes goes silent until it is power-cycled.
- Not started: the touchscreen UI (Phase 4). That needs the MAX3421E wing's
  D9/D10 to be moved, because the TFT FeatherWing uses the same pins.

---

## 2. Protocol work (Phase 0, Oct 22)

**Sources.** `m-vave/fm1_open` @ `4c7496da` (`sdk/WebUpdate.js`), the Firmware
Hub catalogue (`https://thefirmwarehub.com/catalog.json`) and its installer.

**What we learned:**
- **SysEx framing:** `F0`, then a 7-bit-packed stream of
  `00 59 cmd len_lo len_hi 0 payload… checksum`, then `F7`. The checksum is
  `~sum(payload) & 0xFF`.
- **Commands:** 17 identity, 49 capability, 50 arm, 48 read request/reply,
  33/34 factory bank begin/write, 0 ack.
- **The update is request-driven.** After a kick (`F0 22 24 35 7F F7`) the
  device asks for package bytes by address. The host only answers, and a
  stage ends at the finish addresses 0xE0000000 and 0xF0000000.
- **Two install routes:**
  - **Open/stock** (`WebUpdate.js`): tagged, legacy, migration and loader
    modes; arm and capability where the firmware supports them.
  - **Community** (Firmware Hub, Felucca family):
    - wait 2 s after the kick, 10 ms between blocks, 3 s before looking for
      the restarted device
    - the loader identity is hard-coded `ota-FM-1_9xx`
    - verify by identity only, since there is no build hash

  Hub timing applies whenever either the package or the running firmware is a
  community one.
- **Trimmed packages.** Felucca-family packages drop the 32-byte alignment
  padding from `ota.bin`, so its stored length runs past the end of the file,
  and `WebUpdate.js` rejects them. `inspect(strict=False)` accepts exactly that
  case. All 84 catalogue packages at the time parse and complete a simulated
  install.
- **Progress.** The web updater's bar stalls near 86 %. Measuring against the
  blocks each stage actually reads fixes it.
- **Catalogue.** It's updated nightly and CORS-open. Entries carry `id`,
  `name`, `author`, `version`, `product`, `pkg`, `size`, `sha256`,
  `source`/`release`, `loader` and `kind` (a genre). They carry no license,
  `build_id` or `loader_sha256`; `make_sd.py` computes the loader hash.
  Firmwares listed with `loader: "mvave"` (e.g. Bubba) use the vendor
  `ota-FM-1_015` loader instead of `ota-FM-1_9xx`.

**Built:**
- `lib/fm1proto.py`: framing, package parsing and streaming reads.
- `lib/fm1update.py`: the install state machine over any transport.
- `tools/fake_fm1.py`: the simulator.
- `tools/make_sd.py`: prepares and verifies firmware folders.
- `tests/test_fm1.py`.

---

## 3. Desktop flasher and rescue path (Phase 1, Oct 22)

`tools/flash_cli.py` (python-rtmidi) proved the protocol on real hardware
before any CircuitPython work:

**Stock V15 → SLOOP 2.8 in 43 s.**
- Stage 1 sent 23 requests: 0x0–0x600, one block at 0x4400, then the loader.
- The loader came up as `ota-FM-1_900`.
- Stage 2 sent 1180 in-order 512-byte requests.
- The simulator now plays this exact pattern.

**SLOOP → V15 in 33 s,** plus 36 factory voice-bank writes in 0.6 s.
- The vendor loader `ota-FM-1_015` skips image 0x600–0x4400.
- Image address = flash address + 0x400, and loaders never touch the boot
  head.

**USB IDs:**

| Firmware | VID:PID | Product name |
|---|---|---|
| Stock V15 | 4C4A:C755 | "FM-1" |
| Felucca/SLOOP app | 1209:0001 | "Felucca" |
| Felucca/SLOOP loader | 1209:0002 | "Felucca Update" |

**Rescue.** A Raspberry Pi Pico running kurogedelic's FM-1 Transporter
(`a632d92`, with jl-uboot-tool's `wl82loader.bin`), driven by MvaveFM1Unbricker's
`fm1_transporter_recover.py`, read the whole flash from macOS.
- **Wiring:** GP0 to D+, GP1 to D−, GND to GND, no VBUS.
- **Baseline dump:** `ref/flash-dumps/` (sha256 `8a4d2330…`).
- **Quirk:** the first `info` can report `uboot=0`; run it again.

---

## 4. Getting the FM-1 to enumerate on the Feather (Phase 2, Oct 22–26)

This took most of the effort. The order below is the order things happened.

### 4.1 The descriptor is too big (Oct 22)

The first probe from the Feather (CircuitPython 11.0.0-alpha) never saw the
FM-1 in `usb.core.find()`. A pyusb dump on the Mac
(`tools/usb_descriptors.py`) showed why it might not:
- **Stock V15's configuration descriptor is 293 bytes:** 5 interfaces, made up
  of UAC1 audio control, iso out, iso in, and MIDI streaming on interface 4
  with bulk 0x84/0x04.
- **CircuitPython's limit:** it sets `CFG_TUH_ENUMERATION_BUFSIZE` to 288
  (`supervisor/shared/usb/tusb_config.h`), and TinyUSB aborts enumeration when
  `wTotalLength` is larger.

So we built 10.3.1 with `-DCFG_TUH_ENUMERATION_BUFSIZE=512`. That fix is real
and still required, but it wasn't the blocker yet.

Along the way:
- `adafruit_usb_host_midi` has no `write()` and loses SysEx boundaries, so
  `lib/fm1usb.py` does USB-MIDI 1.0 SysEx packetizing and reassembly on
  `usb.core`.
- `hashlib` on CircuitPython only has the `hashlib.new("sha256")` form.

### 4.2 "It never attaches" (Oct 25)

We got TinyUSB debug logs out of the Feather (`CIRCUITPY_DEBUG_TINYUSB=2`, the
console UART on TX, read by the Pico on GP5 with `device/uart_log.py`).
- **A Keychron keyboard** on the same port gave a full "Device Attach …
  Enumeration complete: success = 1".
- **The FM-1** gave **no attach event at all**, in either USB-C orientation,
  before or after replugging.

Things tried and what we thought at the time:

| Try | Result | What we concluded then |
|---|---|---|
| Multimeter on D+/D− | 0.3 V on both with the FM-1 plugged in, 0 V without | FM-1 thinks it's on a charger? |
| Adafruit USB-C CC fixer at the FM-1 | Attached 3 times; enumeration failed each time (status stages, Set Address) | Attach depends on USB-C termination |
| 120 MHz build | Keyboard perfect, FM-1 still no attach | Clock isn't the problem |
| Pico-PIO-USB reply timeout 3 µs → 20 µs | One full FM-1 enumeration (293-byte descriptor read) | Timeout too tight? (later disproved, §5) |

The clock row is a real finding even though it wasn't the cause.
CircuitPython runs the Feather at 125 MHz (an SDK default), which makes
Pico-PIO-USB's clock dividers fractional. 120 MHz gives whole-number dividers.

Most of the "concluded then" column turned out to be wrong; see [§8](#8-superseded-conclusions).

### 4.3 The long-wait experiment

**The suggestion:** give the reply wait a couple of seconds. We built a Feather
firmware with long TinyUSB enumeration waits:

| Wait | Stock | Long build |
|---|---|---|
| Debounce after attach | 150 ms | 2000 ms |
| Root port reset | 50 ms | 100 ms |
| After reset ends | 2 ms | 50 ms |
| Reset recovery | 10 ms | 500 ms |
| Set Address recovery | 2 ms | 100 ms |

**Results:**
- **First boot with the FM-1 plugged in:** it attached and answered identity
  `FM-1_015` in 34 ms, the first SysEx round trip from the Feather. It didn't
  answer cmd 49, which is normal for stock.
- **Replugs:** in a 3-minute test, one detach and then nothing. No re-attach.
- **Feather resets with the FM-1 plugged in:** the log showed Device Attach →
  2000 ms → reset → Device Removed, about 8 times in a row.
- **Adding a 20-frame disconnect debounce in Pico-PIO-USB:** resets then
  enumerated 2 of 3 times, but hot-plugs still produced zero attach events.
- **Cycling the host 5 V through GPIO18 (2 s and 5 s off):** no effect. That
  test may not have removed power at all; see §4.7.

### 4.4 Ruling out the pull-downs

A second Pico ran the same firmware with **15 kΩ pull-downs** on D+/D− and
VBUS taken straight from the Mac.
- **Hot-plugs:** zero attaches.
- **Pico resets with the FM-1 plugged in:** 2 of 3 enumerated, the same pattern
  as the Feather.

So the pull-downs weren't the cause, and "reset with it plugged in works,
hot-plug doesn't" held on both boards.

### 4.5 Watching the lines: the FM-1's role-detect loop

With **no USB host running**, `device/fm1_lines.py` read GP0/GP1 as plain
inputs with pull-downs and logged every change while the FM-1 was hot-plugged.
After a hot-plug the FM-1 cycles forever, about every 3.6 s:

| Phase | Lines | Duration |
|---|---|---|
| J | D+ up (full-speed device) | **2.05 s, every cycle** |
| K | D− up | 0.02–0.5 s |
| SE0 | both low | ~1.2 s |

It presents as a device for 2.05 s, then probably checks whether it should be
the host (JieLi chips do OTG). **Once a host has enumerated it, it holds J
steadily,** even after the host goes away. That is why "reset with it plugged
in" worked: the FM-1 was already sitting in device mode.

This explained everything up to that point:
- **The 2 s debounce** expired exactly as the FM-1 left its 2.05 s J phase.
  Lengthening the wait made things worse.
- **The K phase looks like a low-speed device attaching.** Pico-PIO-USB
  "connected" to it. When the lines then went idle, nothing checked for a
  disconnect while the port waited for its bus reset (the disconnect check only
  runs while the bus is active), so the port stayed marked connected and never
  reported another attach. Those were the "no attach event at all" runs.

### 4.6 Root cause and fix

With stock timing plus a disconnect check while waiting for reset, hot-plugs
produced attach events every time, and the log showed the real failure.
**After the first bus reset in its J phase, the FM-1 switches into device mode
but can't answer that first enumeration:**

| Reset recovery | What the FM-1 does |
|---|---|
| 10 ms (stock) | ACKs the SETUP for Get Device Descriptor, never returns the data |
| 200 ms | Doesn't even ACK the SETUP |

After that one failed attempt it holds J and waits as a normal device. Reading
the raw GPIO input register through `memorymap` while the host was running
confirmed steady J. **TinyUSB never retries a failed enumeration**, so the port
stays stuck until the next unplug.

**Fix:** retry a failed root-port enumeration while the device is still
connected (`patches/tinyusb-enum-retry.diff`).

| Board | Hot-plugs mounted |
|---|---|
| Pico, with the 15 kΩ pull-downs | 5 of 5 |
| Pico, pull-downs removed | 5 of 5 |

Every time, attempt 1 failed and the retry succeeded.

### 4.7 The Feather's built-in port: the "silent" FM-1

The same firmware on the unmodified Feather:
- **Hot-plugs:** about 7 of 10 mounted over two runs, each through one retry.
  The rest were a **different failure**. The FM-1 went silent: both lines held
  SE0 indefinitely, with no role-detect loop and no attach. That's the 0.3 V
  state from §4.2.
- **Replugging at the FM-1's USB-C end instead of the Feather's USB-A end:**
  about as bad.
- **Power-cycling the FM-1 with the cable seated:** 8 of 10 mounted. The other 2
  went silent, and a later power cycle brought it back.
- **Recovery from silent:**
  - Turning the FM-1 off and on works. A plain replug sometimes does too.
  - Cycling GPIO18 (the boost enable) doesn't.

**The Feather schematic** (adafruit/Adafruit-Feather-RP2040-USB-Host-PCB):
- **USB-A VBUS** comes from a **TPS61023 boost** (EN on GPIO18, 100k pull-up).
  Its input is the higher of USB 5 V through a Schottky diode or the LiPo.
- **Between the boost and the jack:** 44 µF, then an unrated 0805 **fuse**.
- **D+/D−:** GPIO16/17 through 22 Ω. No pull-downs, no ESD protection.

If the TPS61023 has no output disconnect (unverified), disabling it leaves
about VIN minus a diode drop on VBUS. In that case our "VBUS off" tests never
actually removed power from the FM-1.

### 4.8 The MAX3421E wing settles it

The Adafruit USB Host FeatherWing (MAX3421E, product 5858) has a real
full-speed transceiver, 15 kΩ host pull-downs built in, and its own 5 V boost.
We stacked it on the same Feather (CS D10, IRQ D9) with a build that enables
`max3421e` and disables the PIO host (`patches/feather-max3421e.diff`).

**15 of 15 attaches** (10 power cycles and 5 hot-plugs), each about 6 s after
the FM-1 came back, with no silent state. Every attach still needed the
enumeration retry, so that is FM-1 behaviour, not PIO-USB behaviour.

**The SysEx stress test** (`device/fm1_sysex_stress.py`, long messages under
manufacturer 0x7D, which the FM-1 ignores, with identity checks between
batches):

| | PIO port | MAX3421E |
|---|---|---|
| Identity latency (avg) | 10.4 ms | 12.8 ms |
| 603-byte messages | 21.3 KB/s | 29.5 KB/s |
| Install-like stream | 24.3 ms/msg | 20.6 ms/msg |
| Errors | 0 | 0 |

**Conclusion:** the silent state comes from the built-in port's electrical
side, most likely its power path or termination. The FM-1's firmware and our
timing aren't the cause. **The flasher uses the MAX3421E wing.**

---

## 5. Patch verdicts

`device/fm1_stats.py` reads counters that an instrumented build keeps in RAM
(`patches/*-stats.diff`). It covered the stress test, hot-plugs and power
cycles on the Feather, about 17,400 transactions.

| Change | Where | Verdict | Evidence |
|---|---|---|---|
| Root-port enumeration retry | TinyUSB `usbh.c` | **Required** | 11/11 attaches failed once, then succeeded on retry (and 15/15 on MAX3421E) |
| `CFG_TUH_ENUMERATION_BUFSIZE=512` | board `mpconfigboard.mk` | **Required** | 293-byte descriptor > 288 default |
| Disconnect check while waiting for reset | Pico-PIO-USB | Keep (PIO only) | Never fired in the instrumented runs; guards the stuck-"connected" race from §4.5 |
| 20-frame disconnect debounce | Pico-PIO-USB | Keep (PIO only) | Absorbed one 1-frame SE0 glitch on a live connection |
| FS reply timeout 3 → 20 µs | Pico-PIO-USB | **Not needed** | Longest wait 1 µs; none over 3 µs |
| 120 MHz system clock | board CFLAGS | Untested without | Integer PIO-USB dividers; kept as a precaution |
| Long enumeration waits | TinyUSB `usbh.c` | **Harmful**, reverted | 2 s debounce misses the J window; 200 ms recovery stops the SETUP ACK |

None of this has been posted upstream yet. The draft in `docs/` covers only
the buffer size. The retry is the finding most worth proposing to TinyUSB.

---

## 6. Installing from the Feather (Phase 3, Oct 26–27)

`device/fm1_install.py` runs `fm1update` on the device:
- **The flow:** verify the package sha256, dry run (identity and capability
  only), then install with `go=True`.
- **Package location:** `CIRCUITPY/firmware/<slug>/` for now; SD later.

### 6.1 The loader that wouldn't take our replies

**First attempt, V15 → SLOOP:**
- Stage 1, served by the stock app, worked.
- In SLOOP's loader (`1209:0002`) the install stalled after 3 requests.
  "Device stopped requesting data" came after 180 s.
- **Power-cycling the FM-1 brought back stock V15.** The loader hadn't written
  anything yet, and that was true for both failed attempts.

To see what happened, `fm1_install` now keeps a RAM ring of the last 80 SysEx
messages and prints it on failure, so logging doesn't change the timing.
- The loader asked for block 0 and we replied (605 bytes of SysEx, 808 bytes
  of USB-MIDI, sent as one bulk write of 13 packets).
- It **asked for the same block again** 3 s later, then 5 s after that, then
  gave up.
- One-packet messages, identity and the kick, got through fine.
- The Mac sends the identical bytes successfully.

**Fix:** send each reply as 64-byte writes. With a 1 ms gap the install
succeeded at the first try (109 s).

Our best guess at the cause: the loader NAKs while busy, and the MAX3421E
driver's NAK-then-resend handling on OUT loses data. That's unproven.

### 6.2 Back to V15: two bugs only the device could find

- **Transient read errors.** With SLOOP running, its sequencer streams MIDI
  notes over USB, and a bulk IN read on the MAX3421E occasionally fails once
  with `USBError`. The transport took the first one as an unplug. It now needs
  3 in a row.
- **MemoryError in the voice restore.** The firmware install had already
  succeeded, but `Package.factory_bank()` grew a bytearray to 16 KB and copied
  it twice, which failed on a heap fragmented by the long install. It now
  allocates once (output identical, sha256 `ecad0b86…`), and
  `restore_factory()` runs `gc.collect()` first. A later full install with the
  restore inside it worked.

### 6.3 Lost replies: slow down instead of re-sending

The serve loop always re-sent repeated requests, but identical bursts kept
getting lost. Now:
- **Detection:** a repeat arriving **≥ 1 s after our reply** (`lost_reply`)
  counts as a lost reply. Quick repeats are part of normal read plans; the
  stock app asks for 0x800 three times within ~100 ms.
- **Response:** the link slows down (`Link.slow_down()` →
  `USBMidiTransport.slow_down()`): 64-byte writes with a 1 ms gap, then the gap
  doubles up to 8 ms.
- **Carry-over:** `Updater.slow_level` reapplies the setting to new links, so
  it survives re-enumeration into the loader.
- **Simulator:** it now models lossy links and the loader's
  retry-twice-then-silence, with 4 tests.

On hardware this recovered one lost reply in each direction:
- In SLOOP's loader at 0x200.
- In the SLOOP *app* at 0x0, so busy community firmware loses bursts too, not
  only loaders.

### 6.4 Speed: most of the time was Python, not USB

Measured on the Feather for one 512-byte reply:

| Step | Before | After |
|---|---|---|
| `frame` + `pack7` | 16.9 ms | 9.3 ms (7-byte groups with fixed shifts, one buffer) |
| `encode_sysex` | 10.1 ms | 7.0 ms (indexed stores, no slices) |
| Send, one write | 13.2 ms | — |
| Send, 64-byte writes, no gap | 16.9 ms | **new default** |
| Send, 64-byte writes, 1 ms gap | 30.1 ms | (adaptive fallback) |

Both rewrites are byte-identical to the old code at every length.

The serve loop now builds the reply first and sleeps only what's left of the
hub's 10 ms pacing. The minimum gap is unchanged, but building the reply
already uses it up.

With 64-byte writes and no gap as the default:

| Install | Before | After | Lost replies |
|---|---|---|---|
| V15 → SLOOP 2.8 | 114 s | 70 s | 0 |
| SLOOP → V15 + voices | 119 s | 73 s | 0 |
| V15 → ChoralRoot 0.27 | — | 69 s | 0 |

ChoralRoot (from the catalogue through `make_sd.py --catalog choralroot`) ships
its own loader build (sha256 `ab3242c8…`, against SLOOP's `7024be59…`). It also
reports as `ota-FM-1_900`.

---

## 7. Tools and techniques worth reusing

- **TinyUSB host logs from CircuitPython:**
  - Build with `CIRCUITPY_DEBUG_TINYUSB 2` and `CIRCUITPY_CONSOLE_UART_TX/RX` in
    `mpconfigboard.h`, plus `CORE1_CHECK_ROOTS=` on the make line. Debug builds
    fail the core1 flash check otherwise.
  - Read the log with a second board: `device/uart_log.py`, or
    `device/uart_log_cdc.py`, which copies it to `usb_cdc.data`.
  - Don't `print()` a log that arrives on the same board's console UART. It
    echoes back into itself.
- **Line state without claiming the pins.** In `memorymap.AddressRange(start=0xD0000004, length=4)`,
  read with `bytes(r[0:4])` (IO registers need aligned 4-byte access).
  Pico-PIO-USB inverts its pad inputs, so `1` means low.
- **RAM counters read from Python.** Put a `volatile uint32_t` array with a
  magic word in the C code, find its address with `arm-none-eabi-nm`, and read
  it through `memorymap` (`device/fm1_stats.py`).
- **Line watcher** (`device/fm1_lines.py`): plain GPIO inputs with pull-downs,
  logging J, K and SE0 changes while a device is plugged in. This is what
  found the role-detect loop.
- **Replug and power-cycle harness** (`device/fm1_replug.py`): logs each
  attach and detach with an identity probe. `fm1_replug_log.py` adds the
  TinyUSB log and line samples.
- **SysEx stress test** (`device/fm1_sysex_stress.py`): long host-to-device
  messages the device ignores (manufacturer 0x7D), with identity checks in
  between.
- **Lossy-link simulator** (`tools/fake_fm1.py`):
  - `lossy_over` and `lossy_modes` drop long host messages until the
    transport slows down.
  - `retry_ms` and `retries` model the loader's repeat-then-silence.
- **CircuitPython build recipe:**
  - `make -C ports/raspberrypi BOARD=… BUILD=build-<name> -j10` with the cp
    venv on PATH.
  - Apply `patches/` to a 10.3.1 checkout.
  - 120 MHz: `-DSYS_CLK_HZ=120000000 -DPLL_SYS_VCO_FREQ_HZ=1440000000 -DPLL_SYS_POSTDIV1=6 -DPLL_SYS_POSTDIV2=2`.

---

## 8. Superseded conclusions

These appeared in `PLAN.md` or in our reasoning at the time, and are wrong:

| Earlier claim | What's actually true |
|---|---|
| The descriptor size was the blocker (Oct 22) | Needed, but the FM-1 wasn't even attaching yet |
| The FM-1 treats the port as a charger because of weak pull-downs (Oct 25) | 15 kΩ pull-downs changed nothing; the FM-1 runs a role-detect loop |
| Attach depends on USB-C power/termination, not host software (Oct 25) | It was TinyUSB not retrying, plus a Pico-PIO-USB stuck-connected bug |
| Longer waits help | The 2 s debounce made it worse; longer reset recovery made it worse |
| The 20 µs reply timeout was needed | The FM-1 answers within 1 µs |
| Cycling the host 5 V doesn't wake a silent FM-1 | Probably untested: the boost may not cut VBUS when disabled |
| VBUS is not involved at all | The built-in port (boost + fuse) has the silent state; the Pico on Mac 5 V and the MAX3421E don't. The power path is a suspect, though unproven |

---

## 9. Open questions

- **What causes the silent state** on the Feather's built-in port? Suspects:
  - the TPS61023 boost and fuse during the FM-1's current surge at plug-in
  - the 22 Ω/no-pull-down termination

  No measurement yet. A LiPo won't help while USB is connected, because Q3
  switches the battery out of VHI.
- **Does the TPS61023 disconnect its output when disabled?** It decides whether
  the GPIO18 tests meant anything.
- **Why does the MAX3421E lose multi-packet OUT bursts** to the FM-1's loaders
  and the busy SLOOP app, when the Mac doesn't? The NAK-handling theory is
  unproven.
- **Is 120 MHz needed** on the PIO port? No drop-one build was run.
- **Battery operation** of the whole flasher: untested.
- **Phase 4 hardware:** the MAX3421E wing (CS D10, IRQ D9) and the 3.5" TFT
  FeatherWing (TFT CS D9, DC D10) clash. One board needs rework.
