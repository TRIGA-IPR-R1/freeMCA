#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright (C) 2026 Daniel Batista, Thalles Campagnani
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Python front-end for the C++ UDP oscilloscope capture library.

Configure attributes, then call run(). Example:

    from udp_scope_lib import UdpScope
    cap = UdpScope()
    cap.port = 5000
    cap.sample_rate = 31.25e6
    cap.v_range = 5.0
    cap.format = "int16"       # or "csv"
    cap.out_path = "chA.bin"
    cap.max_samples = 1_000_000
    cap.run()
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


def _load_lib() -> ctypes.CDLL:
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "lib" / "libudp_scope.so",
        here / "libudp_scope.so",
        Path("libudp_scope.so"),
    ]
    for path in candidates:
        if path.is_file():
            return ctypes.CDLL(str(path))
    raise FileNotFoundError(
        "libudp_scope.so not found. Build with: make -C oscilloscopeMode/lib"
    )


class UdpScope:
    """Configure from Python; C++ captures to CSV (volts) or raw little-endian int16."""

    def __init__(self) -> None:
        self._lib = _load_lib()
        self._lib.udp_scope_create.restype = ctypes.c_void_p
        self._lib.udp_scope_destroy.argtypes = [ctypes.c_void_p]
        self._lib.udp_scope_set_bind.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self._lib.udp_scope_set_port.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._lib.udp_scope_set_sample_rate.argtypes = [ctypes.c_void_p, ctypes.c_double]
        self._lib.udp_scope_set_bits.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._lib.udp_scope_set_v_range.argtypes = [ctypes.c_void_p, ctypes.c_double]
        self._lib.udp_scope_set_out_path.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self._lib.udp_scope_set_csv_path.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self._lib.udp_scope_set_format.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self._lib.udp_scope_set_max_samples.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        self._lib.udp_scope_request_stop.argtypes = [ctypes.c_void_p]
        self._lib.udp_scope_run.argtypes = [ctypes.c_void_p]
        self._lib.udp_scope_run.restype = ctypes.c_int
        self._lib.udp_scope_samples_written.argtypes = [ctypes.c_void_p]
        self._lib.udp_scope_samples_written.restype = ctypes.c_uint64
        self._lib.udp_scope_packets.argtypes = [ctypes.c_void_p]
        self._lib.udp_scope_packets.restype = ctypes.c_uint64
        self._lib.udp_scope_gaps.argtypes = [ctypes.c_void_p]
        self._lib.udp_scope_gaps.restype = ctypes.c_uint64
        self._lib.udp_scope_last_error.argtypes = [ctypes.c_void_p]
        self._lib.udp_scope_last_error.restype = ctypes.c_char_p

        self.bind = "0.0.0.0"
        self.port = 5000
        self.sample_rate = 31.25e6
        self.bits = 14
        self.v_range = 5.0
        self.format = "csv"  # "csv" or "int16"
        self.out_path = "capture.csv"
        self.max_samples = 0  # 0 = until Ctrl+C
        self.samples_written = 0
        self.packets = 0
        self.gaps = 0
        self._h = None

    def _apply(self, h) -> None:
        lib = self._lib
        lib.udp_scope_set_bind(h, self.bind.encode())
        lib.udp_scope_set_port(h, int(self.port))
        lib.udp_scope_set_sample_rate(h, float(self.sample_rate))
        lib.udp_scope_set_bits(h, int(self.bits))
        lib.udp_scope_set_v_range(h, float(self.v_range))
        lib.udp_scope_set_format(h, str(self.format).encode())
        lib.udp_scope_set_out_path(h, os.fspath(self.out_path).encode())
        lib.udp_scope_set_max_samples(h, int(self.max_samples))

    @property
    def csv_path(self) -> str:
        return self.out_path

    @csv_path.setter
    def csv_path(self, path) -> None:
        self.out_path = path

    def run(self) -> None:
        h = self._lib.udp_scope_create()
        if not h:
            raise RuntimeError("udp_scope_create failed")
        self._h = h
        try:
            self._apply(h)
            rc = self._lib.udp_scope_run(h)
            self.samples_written = int(self._lib.udp_scope_samples_written(h))
            self.packets = int(self._lib.udp_scope_packets(h))
            self.gaps = int(self._lib.udp_scope_gaps(h))
            if rc != 0:
                err = self._lib.udp_scope_last_error(h) or b""
                raise RuntimeError(err.decode(errors="replace") or f"run failed ({rc})")
        finally:
            self._lib.udp_scope_destroy(h)
            self._h = None

    def stop(self) -> None:
        if self._h:
            self._lib.udp_scope_request_stop(self._h)
