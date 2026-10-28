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
- The Feather's **built-in USB-A host port** (PIO-USB) works too, on a
  custom CircuitPython 11 (512-byte buffer, 120 MHz, Pico-PIO-USB disconnect
  check), **if the FM-1's cable is long enough**. With a 2 m cable: 10 of 10
  power cycles and two full installs. With a short cable the FM-1 goes
  silent: it switches to USB host role
  ([§6.6](#66-what-the-silent-state-is-oct-27),
  [§6.7](#67-cable-length-decides-it-oct-27)). A 30 cm USB-A pigtail on D11/D12
  works the same way, which leaves D9/D10 free.
- Not started: the touchscreen UI (Phase 4). With the MAX3421E wing, its
  D9/D10 must be moved, because the TFT FeatherWing uses the same pins; the
  PIO port avoids that.

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
- **Cycling the host 5 V through GPIO18 (2 s and 5 s off):** no effect. VBUS
  really was off: the TPS61023 boost turns its output fully off when EN is
  below 0.4 V (§4.7).

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

**The VBUS tests were valid.** The TPS61023 datasheet says the output is
turned fully off when EN is below 0.4 V. GPIO18 driven low holds EN near 0 V
against the 100k pull-up, so the GPIO18 tests removed VBUS for 2–5 s.
- **A silent FM-1 stays silent** with VBUS removed and restored.
- **A working FM-1 stays on the bus** through it: the host still saw it 0.4 s
  after power returned, and it answered identity.

The FM-1 runs on its battery, so losing VBUS doesn't reset its USB state. Only
its own power switch does.

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
| Root-port enumeration retry | TinyUSB `usbh.c` | **Required on 10.3.1; built in on 11** | 11/11 attaches failed once, then succeeded on retry (and 15/15 on MAX3421E). CircuitPython 11's TinyUSB has its own retry (`CFG_TUH_ENUM_ATTEMPT_MAX` = 2) |
| `CFG_TUH_ENUMERATION_BUFSIZE=512` | board `mpconfigboard.mk` | **Required** | 293-byte descriptor > 288 default |
| Disconnect check while waiting for reset | Pico-PIO-USB | **Required** (PIO only), on 10.3.1 and 11 | Guards the stuck-"connected" race from §4.5. On CircuitPython 11 without it, the port never enumerated a role-detecting FM-1; with it, 4 firings in one 2 m-cable run (§6.7) |
| 20-frame disconnect debounce | Pico-PIO-USB | Keep (PIO only) | Absorbed one 1-frame SE0 glitch on a live connection |
| FS reply timeout 3 → 20 µs | Pico-PIO-USB | **Not needed** | Longest wait 1 µs; none over 3 µs |
| 120 MHz system clock | board CFLAGS | **Required** on the PIO port | At the stock 125 MHz, ~30 % of OUT writes fail on CircuitPython 11; 0/100 at 120 MHz (§6.5) |
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

### 6.5 CircuitPython 11 on the built-in port (Oct 27)

We retested on **CircuitPython 11.0.0-alpha.2**, the latest release. Its TinyUSB
(`efab607`) and Pico-PIO-USB (`9e502a5`) match `main` on that day. The FM-1 was on
the Feather's own USB-A port.

**What changed upstream:**
- **TinyUSB now retries enumeration itself.** In `usbh: add control
  transfer timeout and enumeration retry (#3862)`, a failed enumeration
  transfer tears down and restarts from a fresh port reset after the 150 ms
  debounce. `CFG_TUH_ENUM_ATTEMPT_MAX` defaults to 2 (one retry). That is
  exactly what the FM-1 needs, so **our retry patch isn't needed on 11**.
- **The enumeration buffer is still 288 bytes,** so 512 is still required. Stock
  V15 (293-byte descriptor) enumerated with it.
- **Pico-PIO-USB still has no disconnect check while waiting for reset.**
  Nothing in these tests needed it, but §6.7 did: it's still required.

**Results with only the 512-byte change, at the stock 125 MHz:**
- Power cycles and hot-plugs (FM-1 running ChoralRoot): about 12 of 15 mounted,
  similar to patched 10.3.1. The rest were the silent state.
- **Installs fail.** The first 605-byte reply errors out of `device.write()`.
  A write test against the FM-1 (messages it ignores) failed about 30 % of the
  time at every length, even single 16-byte packets, and the failures landed on
  random 64-byte pieces.

**At 120 MHz: 100 of 100 writes succeeded** at every length.
- At 125 MHz Pico-PIO-USB's 48 MHz bit clock needs a fractional divider
  (≈2.60). Enough packets go bad that a 13-packet reply rarely survives.
- **So 120 MHz is required** on the PIO port. §5 had it as "untested
  without"; 10.3.1 only worked because all our builds already ran at 120 MHz.

**ChoralRoot → V15 at 120 MHz:**
- Stage 1, served by ChoralRoot's updater: done, 76 requests.
- Stock loader: all 1244 requests with no lost replies. The write phase took
  47 s, faster than through the MAX3421E (53 s).
- The FM-1 then restarted into V15 and **came back silent**, so the install
  timed out waiting before the voice restore. The screen confirmed V15.
- **Two FM-1 power cycles didn't recover it** (lines at SE0). **A Feather reset
  with the FM-1 left plugged in did:** it enumerated as `4C4A` "FM-1" right
  away. The voice restore then ran on its own in 5.1 s.

So **host-side re-initialization can clear the silent state**, where VBUS
cycling can't. That looked like a lead on its cause, and a possible recovery
that doesn't need the user. §6.6 shows it doesn't hold up.

**ChoralRoot handles a failed update cleanly.** When the first attempt died in
stage 1, it showed an "update failed" screen and returned to normal play by
itself (reported by John). The earlier assumption that it was stuck waiting
was wrong.

**Device code hardened along the way:**
- `USBMidiTransport.send` retries a failed write up to 3 times. It resends the
  whole message, and the leading F0 restarts the device's parser.
- `finder()` tries each device twice before skipping it.
- `fm1_install` prints its message ring for any exception.
- `fm1_replug.py` recognises the Felucca-family `1209:xxxx` IDs.

### 6.6 What the silent state is (Oct 27)

**Trying to wake it from software** (`device/fm1_wake.py`), without a reset,
when an FM-1 came back silent after a power cycle:

| Nudge | Woke it? |
|---|---|
| Float D+/D− (pull-downs off) for 50 ms, 500 ms and 2 s | No |
| Pull D+ up (internal pull-up), D− floating, 100 ms | No |
| Pull D+ up, D− pulled down, 500 ms | No |
| VBUS off (GPIO18 low) plus lines floating, 2 s | No |
| FM-1 power cycles | 0 of 10 |
| `microcontroller.reset()` | 2 of 2 |

**A/B test of the host side.** Two debug builds of 11.0.0-alpha.2 (512-byte
buffer, 120 MHz, TinyUSB log level 2 on the console UART, read by a Pico) with
counters in Pico-PIO-USB (`patches/pico-pio-usb-cp11-stats.diff`):
- **A:** stock Pico-PIO-USB.
- **B:** plus the disconnect check while waiting for reset (`FM1_IDLE_DISCONNECT=1`).

`device/fm1_cycle_watch.py` logged every attach, detach and SILENT with the counters.

| | A | B |
|---|---|---|
| Start | Attached | Silent, even after reflashing the Feather |
| Power cycles | 10: silent from the first, never came back | About 10: never attached |
| Pico-PIO-USB connects | 0 | 0 |
| TinyUSB log | One "Device Removed", then nothing | Nothing |
| Lines | SE0 throughout | SE0 throughout |

TinyUSB never saw an attach, so nothing was enumerated, retried or failed.
Pico-PIO-USB correctly reported an empty port, so B's check had nothing to act
on. **Neither is the cause.** Two Feather resets (one through the UF2
bootloader, one plain) didn't wake it either this time, so the 2 of 2 above
was luck.

**Narrowing it down,** with the FM-1 silent:

| Test | Result |
|---|---|
| Unplug the cable at the Feather for 5 s, replug | Still silent |
| Lines for 10 s after that replug | Solid SE0, no role-detect loop (§4.5) |
| FM-1 charging icon | On, so VBUS reaches it |
| Same cable into the Mac | Enumerates at once as `4C4A:C755` "FM-1" |
| Straight back into the Feather | Silent again |
| RP2040 internal pull-up on D+, FM-1 connected | D+ stays low |
| Same, nothing connected | D+ goes high; D− likewise |

**Conclusion: a silent FM-1 is in USB *host* role.** Something on the FM-1's
side pulls D+ down harder than the RP2040's ~50 kΩ pull-up. A device would
have a 1.5 kΩ pull-up on D+ instead; a host has ~15 kΩ pull-downs. So the
FM-1 sits waiting for a device, and the Feather's pins, socket, cable and host
stack are all fine. The J/K/SE0 loop of §4.5 is its dual-role (OTG) detection;
silent is that detection settling on "host". A standard host (Mac, MAX3421E)
gets it back into device mode.

**Why only the built-in port?** Unproven. The likely difference is
termination: the port has no 15 kΩ pull-downs, only the RP2040's weak internal
ones. But the Pico runs in §4.4/4.6 with and without 15 kΩ pull-downs never
went silent either, so that isn't the whole story; the Feather's power path is
still a suspect too. A possible fix for the built-in port, **untested**: 15 kΩ
from D+ and D− to ground on the Feather.

**For the flasher:** no host software fix exists; it's the FM-1's role
decision. The MAX3421E wing stays the hardware (§4.8). (§6.7: a longer cable
avoids it.)

### 6.7 Cable length decides it (Oct 27)

**Setup.** CircuitPython 11.0.0-alpha.2 with the 512-byte buffer, 120 MHz and
the Pico-PIO-USB disconnect check (`patches/pico-pio-usb-cp11-idle-disconnect.diff`).
For other pins, the board doesn't claim GPIO16/17 at boot and the script
calls `usb_host.Port(board.D11, board.D12)` (`patches/cp11-feather-pigtail.diff`).
`device/fm1_cycle_watch.py` takes `FM1_DP` for the pin. The FM-1 was power-cycled
with its cable seated, as in §6.6.

**A USB-A jack pigtail on D11/D12** (Adafruit 4449: a 30 cm, 28 AWG cable with
a jack on one end and jumper sockets on the other, no parts):

| Power | Series resistors | FM-1 firmware | Power cycles back | Silent |
|---|---|---|---|---|
| Mac 5 V (Feather USB pin) | none | V15 | 15 of 15 | 0 |
| Boost, through a USB-A plug breakout (Adafruit 3628) in the Feather's socket | none | V15 | 13 of 13 | 0 |
| Boost | 22 Ω | SLOOP | 5 of 5 | 0 |
| Boost | 22 Ω | V15 | 14 of 14 | 0 |

Installs over the pigtail: V15 → SLOOP in 72 s, and SLOOP → V15 in 69 s.
The V15 voice restore had to be rerun separately, see below.

Without the disconnect check, on boost power, the FM-1 ran its role-detect
loop while the port sat "connected" from the first K phase and never
enumerated it (§4.5). **So CircuitPython 11 still needs the disconnect check**
on the PIO port, contrary to §6.5. In the long-cable run below it fired 4 times.

**The built-in socket, with a second Feather** (a different board, same build
but with the host port on GPIO16/17). All with the same FM-1 on V15:

| Into the USB-A socket | Result |
|---|---|
| The usual short cable (with a ferrite bead), direct | Silent; D+ held low |
| A known-good short cable, direct, from a state cleared on the Mac | Silent at once |
| The same, with the socket's shell clipped to GND | Silent |
| Bead cable → 4449 jack → jumpers → 3628 plug → socket | 10 of 10, then 5 of 5 with the good cable |
| **A 2 m cable (Adafruit 6279), direct** | **10 of 10** |

A third, plain cable turned out to be charge-only: the Mac didn't see the FM-1
through it either. Its runs are left out.

Over the 2 m cable on the built-in port: V15 → ChoralRoot 0.27 in 71 s, and
ChoralRoot → V15 in 69 s.

**What this rules out:**
- the individual board (two Feathers behave alike)
- the boost and fuse (fine through the pigtail and the 2 m cable)
- the socket, its traces, GPIO16/17 and the 22 Ω resistors (fine through the
  chain and the 2 m cable)
- the 22 Ω resistors on their own (fine on the pigtail)
- the cable's shield: the socket's shell lugs (MT1/MT2) are unconnected in
  the board file, but grounding the shell didn't help
- the FM-1 firmware (V15 and SLOOP both fine)

What's left is **length**: every PIO-port setup that worked had at least ~30 cm
more cable between the socket and the FM-1, and every short direct cable failed.
That changes capacitance and inductance on all four lines, the data pair and
VBUS/GND alike. Which one matters, and how, is unmeasured. Two things don't
fit yet:
- the MAX3421E wing was fine with the short bead cable (§4.8)
- on earlier days that bead cable worked 7–8 times in 10 on this port (§4.7),
  where today it never did

**Cable readings** (TREEDIX cable tester, end to end):

| Cable | CC1 | CC2 | VBUS–GND | Shell–GND | On the PIO port |
|---|---|---|---|---|---|
| Short, ferrite bead | 56k up | open | ~0.2 Ω | short | Silent, stays silent |
| Short, yellow (charge-only) | 56k up | open | ~0.2 Ω | short | (no data) |
| Blue 1 m (Adafruit, 1 m version of 6279) | 56k up | 56k up | 0.36 Ω | open | Went silent once, then recovered on a later power cycle (two detaches logged) |
| Blue 2 m (Adafruit 6279) | 56k up | 56k up | 1.3 Ω | open | 10 of 10 |

The blue cables put the 56k Rp on both CC lines, so the FM-1 sees it in
either orientation. That suggested a CC-orientation cause: the FM-1 sensing
one CC pin and falling back to D+/D− role detection without Rp. **Ruled out:**
- the bead cable went silent on the Feather with the USB-C end either way round;
- on the Mac it enumerated either way round;
- the 1 m blue cable, with the same CC wiring as the 2 m, still went silent.

The shield doesn't track success either: the bead cable ties it to GND, the
blue cables leave it open.

So the effect grows with cable length and resistance: short cables stay silent,
1 m recovers, 2 m and the +30 cm chain never go silent. A silent FM-1 on the
Mac also came back only after a USB-C replug, not on its own.

**V15 re-enumerates once after its first boot.** In both V15 installs (pigtail
and 2 m cable), the FM-1 came back as `FM-1_015`, answered the installer's
identity check, then dropped off the bus about 4 s later. The voice restore's
first query failed with a `USBError`. Run separately, the restore took 1.8 s.
`Updater` now retries the restore once after waiting for V15 to come back
(`_restore_after_boot`), with a simulator test (`reenum_after_boot`). On the
device (2 m cable): SLOOP → V15 with voices in one run, 82 s; V15 was found
again 7 s after it dropped, and the restore took 1.8 s.

**CircuitPython 11's `hashlib` gave wrong SHA-256 digests** on a fragmented
heap. The package check failed with "invalid factory voice data" although the
same file and code passed on the Mac. Repeated runs of `prepare` failed after
the first; once, a `gc.collect()` between two `update()` calls gave a wrong
digest. After a soft reset, 24 of 24 cases passed. 11.0.0-alpha.2 moved
`hashlib` to mbedtls 4.2's PSA API, and `shared-module/hashlib/Hash.c` ignores
the return codes of `psa_hash_update` and `psa_hash_clone`, so a failure would
be silent. Workaround: soft-reset before an install. Needs a proper repro
before an upstream issue.

### 6.8 The TFT FeatherWing next to the PIO host (Oct 27)

The TFT FeatherWing V2 3.5" (5872) on Feather 2, with the FM-1 on the 2 m
cable and the built-in PIO port. `device/tft_check.py` drew colour bars,
mirrored the console and read touches; nothing it uses (SPI, D5, D6, D9, D10,
I2C) touches GPIO16–18.

- **Display:** HX8357 at 480x320 on `board.SPI()`, CS D9, DC D10, 24 MHz.
- **Touch:** FT5336 at I2C 0x38. Points come back in the panel's native
  portrait frame (x up to ~320, y up to ~480), so landscape needs a swap and
  flip.
- **RAM:** about 128 KB free with the display up, 122 KB after an install.
- **Installs with the console on the screen:** V15 → ChoralRoot in 85 s
  (71 s without the display) and ChoralRoot → V15 with voices in 103 s
  (82 s), both with no resends or slow-downs. V15 re-enumerated after its first
  boot and `_restore_after_boot` handled it. The extra time is the console
  scrolling: the voice restore, which prints a line per step, took 6.6 s
  instead of 1.8 s. A real UI that redraws a progress bar should cost less.

### 6.9 First install from the touch UI (Oct 28)

Feather 2, TFT FeatherWing, 2 m cable, built-in PIO port. The UI starts an
install by saving the slug in NVM and soft-reloading, so the install runs on
a fresh heap. Three failures before V15 → SLOOP worked (84.4 s, no resends):

- **After a soft reload the FM-1 misses the first query or two.** It isn't
  reset by the reload and stays enumerated. The installer's two identity
  tries ran out: "no FM-1 answered". Watching from the REPL: no answer to
  the first two queries, then every one answers.
- **Reopening the endpoints each try never gets an answer.** A wait loop
  that opened a transport, queried, then released it (`deinit()`) got no
  reply in 15 s. Without a reload, fresh transports answer at once, even
  after `deinit()`. Unproven guess: a data-toggle mismatch that each reopen
  restores. The fix keeps one transport for the whole wait (answered on
  query 3) and hands it to the installer.
- **A garbage-collected `usb.core.Device` closes the endpoints it opened,**
  and endpoints belong to the device address, not the object
  (`shared-module/usb/core/Device.c`, `__del__` → `tuh_edpt_close`). Device
  objects dropped by an earlier probe were collected 2 s into staging and
  closed endpoint 0x04 under the installer: Pico-PIO-USB printed
  `no endpoint 0x04` and the reply write failed with `USBError`. The
  transport's `close()` now calls `device.deinit()`, and nothing drops a
  Device it has used without closing it.

Then SLOOP → V15 with factory voices, 84.5 s, no resends. SLOOP answered
the first identity query after the reload, so the missed queries may be
V15's.

Also seen:
- **"invalid factory voice data" in the package check: `hashlib` returned an
  all-zero digest.** First seen on the first SLOOP → V15 attempt. Once the
  three checks behind that message said which one failed, two MONK-1 → V15
  attempts in a row both failed the voice bank's **SHA-256**, with ~53 KB
  free. The bank's CRC had passed just before, and so had the whole-file and
  loader SHA-256s. Recomputing didn't help: three tries in a row gave
  `0000…0000`. So the hash failed outright and `hashlib` reported no error
  (`shared-module/hashlib/Hash.c` ignores the PSA return codes, §6.7).
  The bank was hashed as one 16 KB `update()`. The other hashes go 2–4 KB at a
  time and never failed. Feeding the bank 1 KB at a time, MONK-1 → V15 passed
  first try (97.2 s, voices restored), with the same free RAM. Likely cause,
  not confirmed in the source: mbedtls's PSA layer copies each update's input
  to a temporary buffer, and a 16 KB block doesn't fit a fragmented heap. That
  also fits the REPL passing with 74 KB free. All three SHA-256 checks now
  recompute after a mismatch (`check_sha256`: a wrong digest can't match by
  chance), and the log says "failed" for an all-zero digest. For an upstream
  issue: a 16 KB `update()` on a fragmented heap → silent all-zero digest.
- **The package check takes 11–30 s.** Slow checks went with the failures,
  but the passing V15 run above also took 26.8 s, so slowness alone isn't
  the fault. Not explained.
- **White screen:** once after replugging the FM-1 during a failed install.
  The code was still running (Ctrl-C found it polling touch). Not explained.
- **Serial input stops if Ctrl-C arrives during a soft reboot.** Sending
  Ctrl-D, then Ctrl-C ~0.6 s later, left `code.py` and the UI running but
  the console accepting no input (writes time out). CIRCUITPY was still
  readable. Only a reset cleared it. This happened twice, both from my
  scripted keys, and it explains the earlier "unresponsive Feather". Wait
  for `code.py` to start before sending Ctrl-C.
- **Unreadable disk prompt:** after a hard reset the Mac called the SD card's
  drive unreadable (Eject is safe). Probably shown over USB before `code.py`
  mounts the card.

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
| The GPIO18 tests may not have removed VBUS, because the boost might not disconnect its output | It does disconnect (EN < 0.4 V turns the output fully off), so the tests were valid: removing VBUS for 2–5 s doesn't wake a silent FM-1 |
| VBUS is not involved at all | Removing VBUS from a silent FM-1 doesn't help, but only the built-in port (boost + fuse) produces the silent state; the Pico on Mac 5 V and the MAX3421E don't. Conditions at plug-in or power-on are still a suspect, though unproven |
| A host reset clears the silent state; the host side is stuck (§6.5) | The host is fine: the silent FM-1 is in USB host role with D+ pulled down. Feather resets work only sometimes (§6.6) |
| The silent state comes from the port's power path or termination (§4.8) | It's the FM-1 choosing host role (§6.6), and on the PIO port it happens with short cables. The boost, the 22 Ω resistors and the board are cleared (§6.7) |
| CircuitPython 11 doesn't need the Pico-PIO-USB disconnect check (§6.5) | It does: without it the port can stay "connected" to a role-detecting FM-1 and never enumerate it (§6.7) |
| Grounding the cable shield at the host end prevents the silent state (Oct 27 hypothesis) | It didn't; the cable's length is what mattered (§6.7) |

---

## 9. Open questions

- **Why does a short cable make the FM-1 pick host role** on the PIO port,
  when ~30 cm more avoids it (§6.7)? Is it the data lines or VBUS/GND? Why
  is the MAX3421E fine with a short cable, and why did the same short cable
  work 7–8 times in 10 on earlier days? It scales with length (§6.7: 0.2 Ω
  fails, 0.36 Ω recovers, 1.3 Ω never fails). Next: a short cable with ~1 Ω
  in series in VBUS only, to separate power from the data lines.
- **CircuitPython 11 `hashlib`** wrong digests on a fragmented heap (§6.7):
  needs a standalone repro for an upstream issue.
- **Why does the MAX3421E lose multi-packet OUT bursts** to the FM-1's loaders
  and the busy SLOOP app, when the Mac doesn't? The NAK-handling theory is
  unproven.
- **What gets a host-role FM-1 back into device mode?** The Mac does it at
  once; a Feather reset only sometimes, and FM-1 power cycles not at all.
- **Battery operation** of the whole flasher: untested.
- **Phase 4 hardware:** the MAX3421E wing (CS D10, IRQ D9) and the 3.5" TFT
  FeatherWing (TFT CS D9, DC D10) clash. One board needs rework.
