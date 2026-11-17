// SPDX-License-Identifier: GPL-3.0-or-later
//
// Copyright (C) 2026 Daniel Batista, Thalles Campagnani
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

// Oscilloscope UDP stream — edit these to match the PC.
// FPGA sends to DST_IP:DST_PORT. Dest MAC defaults to broadcast so ARP
// is not required on the first bring-up.

`ifndef UDP_SCOPE_CONFIG_VH
`define UDP_SCOPE_CONFIG_VH

`define SRC_MAC        48'h02_12_34_56_78_9a
`define DST_MAC        48'hff_ff_ff_ff_ff_ff
`define SRC_IP         {8'd192, 8'd168, 8'd1, 8'd50}
`define DST_IP         {8'd192, 8'd168, 8'd1, 8'd100}
`define SRC_PORT_A     16'd5000
`define DST_PORT_A     16'd5000
`define SRC_PORT_B     16'd5001
`define DST_PORT_B     16'd5001

// Dual AD9248 @ 31.25 MSPS (125 MHz / 4), 14-bit packed offset-binary.
// Both channels share PHY0: Ch A UDP 5000, Ch B UDP 5001 (~928 Mbps total).
// One 1G cable. 720 samp * 14-bit = 1260 B data + 10 B hdr.
`define SAMPLES_PER_PKT 16'd720
`define ADC_BITS        5'd14

`endif
