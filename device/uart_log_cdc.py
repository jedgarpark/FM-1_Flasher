# SPDX-License-Identifier: GPL-3.0-only
"""Read another board's TinyUSB debug log on UART1 RX (GP5, 115200) and copy it to
the usb_cdc data port. Needs usb_cdc.enable(console=True, data=True) in boot.py."""
import board
import busio
import usb_cdc

uart = busio.UART(None, board.GP5, baudrate=115200, receiver_buffer_size=16384)
print("uart_log_cdc: GP5 -> usb_cdc.data")
while True:
    n = uart.in_waiting
    if n:
        usb_cdc.data.write(uart.read(n))
