#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright (C) 2026 Daniel Batista, Thalles Campagnani
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Record one UDP ADC channel via the C++ library.

    python3 host/record_csv.py --port 5000 --out chA.csv --samples 1000000
    python3 host/record_csv.py --port 5000 --format int16 --out chA.bin --samples 31250000
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from udp_scope_lib import UdpScope


def main() -> None:
    p = argparse.ArgumentParser(description="UDP ADC capture to CSV (C++)")
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--rate", type=float, default=31.25e6, help="sample rate in Hz")
    p.add_argument("--bits", type=int, default=14)
    p.add_argument("--v-range", type=float, default=5.0, help="+/- full scale in volts")
    p.add_argument(
        "--format",
        choices=("csv", "int16", "i16", "raw"),
        default="csv",
        help="csv: t_s,v text; int16: little-endian signed codes (12/14-bit unpacked)",
    )
    p.add_argument("--out", default=None, help="output path (default capture.csv / capture.bin)")
    p.add_argument("--samples", type=int, default=1_000_000, help="0 = until Ctrl+C")
    args = p.parse_args()

    fmt = "int16" if args.format in ("int16", "i16", "raw") else "csv"
    out = args.out or ("capture.bin" if fmt == "int16" else "capture.csv")

    cap = UdpScope()
    cap.bind = args.bind
    cap.port = args.port
    cap.sample_rate = args.rate
    cap.bits = args.bits
    cap.v_range = args.v_range
    cap.format = fmt
    cap.out_path = out
    cap.max_samples = args.samples

    def handle_sigint(_sig, _frame):
        cap.stop()

    signal.signal(signal.SIGINT, handle_sigint)
    print(
        f"UDP {cap.bind}:{cap.port}  {cap.sample_rate:g} Hz  "
        f"+/-{cap.v_range:g} V  {cap.format} -> {cap.out_path}"
    )
    cap.run()
    print(
        f"wrote {cap.out_path}  samples={cap.samples_written}  "
        f"pkts={cap.packets}  gaps={cap.gaps}"
    )


if __name__ == "__main__":
    main()
