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

module sync_fifo #(
    parameter WIDTH = 16,
    parameter DEPTH = 512
) (
    input  wire                     clk,
    input  wire                     rst,
    input  wire                     wr_en,
    input  wire [WIDTH-1:0]         din,
    output wire                     full,
    input  wire                     rd_en,
    output wire [WIDTH-1:0]         dout,
    output wire                     empty,
    output wire [$clog2(DEPTH+1)-1:0] count
);
    localparam AW = $clog2(DEPTH);

    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [AW-1:0]    wr_ptr;
    reg [AW-1:0]    rd_ptr;
    reg [AW:0]      used;

    assign count = used;
    assign empty = (used == 0);
    assign full  = (used == DEPTH);
    assign dout  = mem[rd_ptr];

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 0;
            rd_ptr <= 0;
            used   <= 0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr] <= din;
                wr_ptr      <= wr_ptr + 1'b1;
            end
            if (rd_en && !empty)
                rd_ptr <= rd_ptr + 1'b1;

            case ({wr_en && !full, rd_en && !empty})
                2'b10: used <= used + 1'b1;
                2'b01: used <= used - 1'b1;
                default: ;
            endcase
        end
    end
endmodule

`default_nettype wire
