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

import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "host"))
from adc_codec import FLAG_OFFSET, FLAG_PACKED, MAGIC, unpack_samples

hex_path = pathlib.Path(__file__).with_name("pack12.hex")
raw = bytes(int(line, 16) for line in hex_path.read_text().splitlines() if line.strip())
magic, seq, n, flags = struct.unpack_from("<HIHH", raw, 0)
assert magic == MAGIC, hex(magic)
assert n == 16
assert flags & FLAG_PACKED
assert flags & FLAG_OFFSET
parsed = unpack_samples(raw)
assert parsed is not None
_, _, _, samp = parsed
expect = list(range(16))
got = [int(x) + 2048 for x in samp]  # offset-binary 0..15 -> centered -2048..-2033
if got != expect:
    print("FAIL", got, expect)
    sys.exit(1)
print(f"12-bit pack OK  n={n} flags=0x{flags:04x} samples={got}")
