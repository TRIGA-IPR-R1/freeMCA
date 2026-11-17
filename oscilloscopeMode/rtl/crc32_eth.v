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

`default_nettype none

// Ethernet CRC-32 (reflected poly 0xEDB88320). One byte per call.
module crc32_eth (
    input  wire [31:0] crc_in,
    input  wire [7:0]  data,
    output wire [31:0] crc_out
);
    integer k;
    reg [31:0] c;
    reg [7:0]  d;

    always @* begin
        c = crc_in;
        d = data;
        for (k = 0; k < 8; k = k + 1) begin
            if (c[0] ^ d[k])
                c = (c >> 1) ^ 32'hEDB88320;
            else
                c = (c >> 1);
        end
    end

    assign crc_out = c;
endmodule

`default_nettype wire
