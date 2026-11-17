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

"""UDP oscilloscope payload codec.

Header (little-endian):
  magic u16 = 0xADC0 | seq u32 | n u16 | flags u16
  flags bit0 = FIFO overflow
  flags bit1 = packed (ADC_BITS != 16). Bit width = 8 * payload / n.
  flags bit2 = offset binary (AD9248 "direct code"); else two's complement.
"""

from __future__ import annotations

import struct

import numpy as np

MAGIC = 0xADC0
FLAG_OVF = 1
FLAG_PACKED = 2
FLAG_OFFSET = 4
FLAG_PACK14 = FLAG_PACKED
HDR = struct.Struct("<H I H H")
HDR_LEN = HDR.size


def unpack_packed(buf: bytes | memoryview, n: int, bits: int, offset: bool) -> np.ndarray:
    """Little-endian packed samples (same bitstream as the FPGA)."""
    out = np.empty(n, dtype=np.int16)
    acc = 0
    nbits = 0
    i = 0
    mask = (1 << bits) - 1
    sign = 1 << (bits - 1)
    ext = 1 << bits
    mv = memoryview(buf)
    for k in range(n):
        while nbits < bits:
            acc |= mv[i] << nbits
            nbits += 8
            i += 1
        s = acc & mask
        acc >>= bits
        nbits -= bits
        if offset:
            out[k] = s - sign
        else:
            if s >= sign:
                s -= ext
            out[k] = s
    return out


def unpack_samples(data: bytes) -> tuple[int, int, int, np.ndarray] | None:
    if len(data) < HDR_LEN:
        return None
    magic, seq, n, flags = HDR.unpack_from(data, 0)
    if magic != MAGIC or n <= 0:
        return None
    payload = data[HDR_LEN:]
    if flags & FLAG_PACKED:
        bits = (len(payload) * 8) // n
        if bits < 1 or bits > 16:
            return None
        need = (n * bits + 7) // 8
        if len(payload) < need:
            return None
        samp = unpack_packed(payload[:need], n, bits, bool(flags & FLAG_OFFSET))
    else:
        need = n * 2
        if len(payload) < need:
            return None
        samp = np.frombuffer(payload, dtype="<i2", count=n).copy()
    return seq, n, flags, samp
