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

// GMII (8-bit, 125 MHz) -> RGMII (4-bit DDR). TX_ER is tied 0.
module rgmii_tx #(
    // 1 = 100 Mbps: TXC is 25 MHz, both DDR edges carry the same nibble.
    // The MAC must hold each GMII byte for two clocks (low then high nibble).
    parameter NIBBLE_MODE = 0
) (
    input  wire       clk125,
    input  wire [7:0] gmii_d,
    input  wire       gmii_en,
    output wire       rgmii_txc,
    output wire [3:0] rgmii_txd,
    output wire       rgmii_tx_ctl
);
    reg        phase;
    wire [3:0] nibble = NIBBLE_MODE ? (phase ? gmii_d[7:4] : gmii_d[3:0]) : gmii_d[3:0];
    wire [3:0] nibble_d2 = NIBBLE_MODE ? nibble : gmii_d[7:4];

    always @(posedge clk125) begin
        if (!gmii_en)
            phase <= 1'b0;
        else
            phase <= ~phase;
    end
    ODDR #(
        .DDR_CLK_EDGE("SAME_EDGE"),
        .INIT(1'b0),
        .SRTYPE("SYNC")
    ) oddr_clk (
        .Q  (rgmii_txc),
        .C  (clk125),
        .CE (1'b1),
        .D1 (1'b1),
        .D2 (1'b0),
        .R  (1'b0),
        .S  (1'b0)
    );

    ODDR #(
        .DDR_CLK_EDGE("SAME_EDGE"),
        .INIT(1'b0),
        .SRTYPE("SYNC")
    ) oddr_ctl (
        .Q  (rgmii_tx_ctl),
        .C  (clk125),
        .CE (1'b1),
        .D1 (gmii_en),
        .D2 (gmii_en),
        .R  (1'b0),
        .S  (1'b0)
    );

    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : g_txd
            ODDR #(
                .DDR_CLK_EDGE("SAME_EDGE"),
                .INIT(1'b0),
                .SRTYPE("SYNC")
            ) oddr_d (
                .Q  (rgmii_txd[i]),
                .C  (clk125),
                .CE (1'b1),
                .D1 (nibble[i]),
                .D2 (nibble_d2[i]),
                .R  (1'b0),
                .S  (1'b0)
            );
        end
    endgenerate
endmodule

`default_nettype wire
