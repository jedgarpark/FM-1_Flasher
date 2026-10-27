# SPDX-License-Identifier: GPL-3.0-only
"""UART-to-USB log reader for a Pico: `import uart_log` from the REPL.
Reads UART1 RX on GP5 at 115200 and echoes it to the USB console."""
import board
import busio

uart = busio.UART(None, board.GP5, baudrate=115200, receiver_buffer_size=16384, timeout=0)
print("uart_log: listening on GP5")
while True:
    data = uart.read(512)
    if data:
        print("".join(chr(b) if b in (10, 13) or 32 <= b < 127 else "." for b in data), end="")
