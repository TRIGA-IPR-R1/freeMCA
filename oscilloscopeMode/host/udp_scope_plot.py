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

"""Live plot of AD9248 dual-channel UDP streams.

  Ch A  UDP 5000,  Ch B  UDP 5001  (both on PHY0, one cable)
  14-bit packed offset-binary @ 31.25 MSPS each.

  python3 host/udp_scope_plot.py
  python3 host/udp_scope_plot.py --port 5000          # one channel
  python3 host/udp_scope_plot.py --port 5000 5001
"""

from __future__ import annotations

import argparse
import collections
import socket
import threading
import time

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

from adc_codec import FLAG_OVF, HDR, MAGIC, unpack_samples

COLORS = ("#1f77b4", "#ff7f0e")


def bind_sock(bind: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)
    sock.bind((bind, port))
    return sock


def main() -> None:
    p = argparse.ArgumentParser(description="Live plot of UDP ADC samples")
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--port", type=int, nargs="+", default=[5000, 5001])
    p.add_argument(
        "--hold",
        type=int,
        default=8,
        help="consecutive packets in the window (720 samples each)",
    )
    p.add_argument("--interval", type=int, default=50, help="draw period in ms")
    args = p.parse_args()
    hold = max(1, args.hold)
    ports = args.port
    n0 = 720
    n_plot = n0 * hold
    stop = threading.Event()
    lock = threading.Lock()

    socks = [bind_sock(args.bind, port) for port in ports]
    print(f"listening UDP {args.bind}:{ports}")
    for sock in socks:
        sock.settimeout(0.2)

    channels = []
    for sock, port in zip(socks, ports):
        ch = {
            "sock": sock,
            "port": port,
            "buf": collections.deque(maxlen=hold),
            "stats": {
                "seq": 0,
                "addr": ("", 0),
                "flags": 0,
                "pkts": 0,
                "samples": 0,
                "dropped": 0,
                "t0": time.monotonic(),
                "seq0": 0,
            },
        }
        channels.append(ch)

        def rx_loop(ch=ch) -> None:
            last_seq = None
            sock = ch["sock"]
            while not stop.is_set():
                try:
                    pkt, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if len(pkt) < HDR.size:
                    continue
                magic, seq, n, flags = HDR.unpack_from(pkt, 0)
                if magic != MAGIC:
                    continue
                miss = 0
                if last_seq is not None:
                    miss = (seq - last_seq - 1) & 0xFFFFFFFF
                    if miss > 0x7FFFFFFF:
                        miss = 0
                last_seq = seq
                with lock:
                    if miss:
                        ch["buf"].clear()
                    ch["buf"].append(pkt)
                    st = ch["stats"]
                    st["seq"] = seq
                    st["addr"] = addr
                    st["flags"] = flags
                    st["pkts"] += 1
                    st["samples"] += n
                    st["dropped"] += miss

        threading.Thread(target=rx_loop, name=f"udp-rx-{port}", daemon=True).start()

    xs = np.arange(n_plot)
    fig, axes = plt.subplots(len(channels), 1, sharex=True, squeeze=False)
    lines = []
    texts = []
    for i, (ax, ch) in enumerate(zip(axes[:, 0], channels)):
        y0 = np.zeros(n_plot, dtype=np.int16)
        (line,) = ax.plot(xs, y0, lw=0.8, color=COLORS[i % 2])
        ax.set_xlim(0, n_plot - 1)
        ax.set_ylim(-8192, 8191)
        ax.set_ylabel(f"ch {'AB'[i] if i < 2 else i}  (14-bit)")
        ax.grid(True, alpha=0.3)
        text = ax.text(
            0.02, 0.95, "", transform=ax.transAxes, va="top", family="monospace", fontsize=9
        )
        lines.append(line)
        texts.append(text)
    axes[-1, 0].set_xlabel("sample (consecutive)")
    fig.suptitle("AD9248 UDP")

    def update(_frame):
        artists = []
        with lock:
            snaps = []
            for ch in channels:
                st = ch["stats"]
                now = time.monotonic()
                dt = now - st["t0"]
                snap = dict(st)
                snap["dt"] = dt
                snap["batch"] = list(ch["buf"])
                if dt >= 1.0:
                    st["t0"] = now
                    st["seq0"] = st["seq"]
                    st["pkts"] = 0
                    st["samples"] = 0
                    st["dropped"] = 0
                snaps.append(snap)
        for line, text, ax, snap, ch in zip(lines, texts, axes[:, 0], snaps, channels):
            chunks = []
            for pkt in snap["batch"]:
                parsed = unpack_samples(pkt)
                if parsed is not None:
                    chunks.append(parsed[3])
            if chunks:
                cat = np.concatenate(chunks)
                y = np.zeros(n_plot, dtype=np.int16)
                y[-cat.size :] = cat[-n_plot:]
                line.set_data(xs, y)
            dt = snap["dt"] if snap["dt"] > 0 else 1e-9
            seq_span = (snap["seq"] - snap["seq0"]) & 0xFFFFFFFF
            fpga = seq_span * n0 / dt / 1e6
            rx_msps = snap["samples"] / dt / 1e6
            ovf = " OVF" if snap["flags"] & FLAG_OVF else ""
            ax.set_title(f"UDP {ch['port']}  seq={snap['seq']}{ovf}")
            text.set_text(
                f"FPGA {fpga:.3f} MSPS   rx {rx_msps:.3f}  "
                f"pkts={snap['pkts']}  drop={snap['dropped']}"
            )
            artists.extend((line, text))
        return artists

    ani = FuncAnimation(fig, update, interval=args.interval, blit=False, cache_frame_data=False)
    fig._ani = ani
    print(f"n={n0}  window={n_plot} samples/ch  ports={ports}")
    try:
        plt.show()
    finally:
        stop.set()
        for sock in socks:
            sock.close()


if __name__ == "__main__":
    main()
