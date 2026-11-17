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

import binascii
import pathlib
import struct
import sys

hex_path = pathlib.Path(__file__).with_name("gmii.hex")
raw = bytes(int(line, 16) for line in hex_path.read_text().splitlines() if line.strip())

# strip preamble (55..55 d5)
i = 0
while i < len(raw) and raw[i] == 0x55:
    i += 1
assert raw[i] == 0xD5, f"no SFD at {i}"
frame = raw[i + 1 :]
assert len(frame) >= 18
body, fcs = frame[:-4], frame[-4:]
crc = binascii.crc32(body) & 0xFFFFFFFF
got = int.from_bytes(fcs, "little")
print(f"bytes={len(raw)} frame={len(frame)} crc={crc:08x} fcs={got:08x}")
if crc != got:
    print("CRC FAIL")
    sys.exit(1)

ethertype = struct.unpack_from("!H", body, 12)[0]
assert ethertype == 0x0800
ihl = body[14] & 0x0F
assert ihl == 5
total_len = struct.unpack_from("!H", body, 16)[0]
proto = body[23]
assert proto == 17
udp_len = struct.unpack_from("!H", body, 38)[0]
payload = body[42 : 42 + (udp_len - 8)]
magic, seq, n, flags = struct.unpack_from("<HIHH", payload, 0)
print(f"IPv4 total_len={total_len} UDP len={udp_len} magic=0x{magic:04x} seq={seq} n={n}")
assert magic == 0xADC0
print("OK")
