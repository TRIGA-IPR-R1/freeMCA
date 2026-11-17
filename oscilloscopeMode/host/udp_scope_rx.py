#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright (C) 2026 Daniel Batista, Thalles Campagnani
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Receive the Colorlight i9plus oscilloscope UDP stream.

FPGA defaults (rtl/config.vh):
  board  192.168.1.50   MAC 02:12:34:56:78:9a
  PC     192.168.1.100  dest MAC broadcast
  UDP    ch A port 5000, ch B port 5001 (both on PHY0)
  AD9248 14-bit packed offset-binary @ 31.25 MSPS/ch

On the PC:
  python3 host/udp_scope_rx.py --port 5000
  python3 host/udp_scope_rx.py --port 5001
"""

from __future__ import annotations

import argparse
import socket
import time

from adc_codec import FLAG_OFFSET, FLAG_OVF, FLAG_PACKED, MAGIC, unpack_samples


def main() -> None:
    p = argparse.ArgumentParser(description="UDP ADC oscilloscope receiver")
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--print-every", type=float, default=1.0)
    args = p.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)
    sock.bind((args.bind, args.port))
    sock.settimeout(1.0)
    print(f"listening UDP {args.bind}:{args.port}  (magic 0x{MAGIC:04x})")

    last_seq = None
    pkts = 0
    samples = 0
    gaps = 0
    ovf = 0
    t0 = time.monotonic()

    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        parsed = unpack_samples(data)
        if parsed is None:
            continue
        seq, n, flags, samp = parsed
        if last_seq is not None and seq != (last_seq + 1) & 0xFFFFFFFF:
            gaps += 1
        last_seq = seq
        pkts += 1
        samples += n
        if flags & FLAG_OVF:
            ovf += 1

        now = time.monotonic()
        dt = now - t0
        if dt >= args.print_every:
            msps = samples / dt / 1e6
            bits = "packed" if flags & FLAG_PACKED else "i16"
            coding = "offset" if flags & FLAG_OFFSET else "twos"
            print(
                f"{addr[0]}:{args.port} seq={seq} n={n} {bits}/{coding}  "
                f"{msps:.3f} MSPS  pkts={pkts} gaps={gaps} overflow_pkts={ovf}  "
                f"sample[0]={samp[0]} sample[-1]={samp[-1]}"
            )
            pkts = 0
            samples = 0
            gaps = 0
            ovf = 0
            t0 = now


if __name__ == "__main__":
    main()
