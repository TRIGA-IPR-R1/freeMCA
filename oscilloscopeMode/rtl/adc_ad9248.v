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

// Dual AD9248 on a shared 14-bit DDR bus (D0=LSB .. D13=MSB).
// FPGA drives CLK_A and CLK_B 180 deg apart (vendor mux mode).
// Capture follows the kit driver: IDDR rising = CH B, falling = CH A,
// on a PLL clock delayed ~6.73 ns from the ADC output clocks.
module adc_ad9248 #(
    parameter SWAP_AB = 0
) (
    input  wire        clk_sys,
    input  wire        clk_adc,
    input  wire        clk_cap,
    input  wire        rst,

    input  wire [13:0] adc_d,
    output wire        adc_clk_a,
    output wire        adc_clk_b,

    output reg  [15:0] cha_data,
    output reg         cha_valid,
    input  wire        cha_ready,

    output reg  [15:0] chb_data,
    output reg         chb_valid,
    input  wire        chb_ready
);
    ODDR #(
        .DDR_CLK_EDGE("SAME_EDGE"),
        .INIT(1'b0),
        .SRTYPE("SYNC")
    ) oddr_clk_a (
        .Q  (adc_clk_a),
        .C  (clk_adc),
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
    ) oddr_clk_b (
        .Q  (adc_clk_b),
        .C  (clk_adc),
        .CE (1'b1),
        .D1 (1'b0),
        .D2 (1'b1),
        .R  (1'b0),
        .S  (1'b0)
    );

    wire [13:0] q_rise;
    wire [13:0] q_fall;

    genvar i;
    generate
        for (i = 0; i < 14; i = i + 1) begin : g_iddr
            IDDR #(
                .DDR_CLK_EDGE("SAME_EDGE"),
                .INIT_Q1(1'b0),
                .INIT_Q2(1'b0),
                .SRTYPE("SYNC")
            ) iddr_d (
                .Q1 (q_rise[i]),
                .Q2 (q_fall[i]),
                .C  (clk_cap),
                .CE (1'b1),
                .D  (adc_d[i]),
                .R  (1'b0),
                .S  (1'b0)
            );
        end
    endgenerate

    wire [13:0] raw_a = SWAP_AB ? q_rise : q_fall;
    wire [13:0] raw_b = SWAP_AB ? q_fall : q_rise;

    reg [2:0] rst_cap_s;
    always @(posedge clk_cap)
        rst_cap_s <= {rst_cap_s[1:0], rst};
    wire rst_cap = rst_cap_s[2];

    // 2-deep ping-pong CDC clk_cap (31.25 MHz) -> clk_sys (125 MHz).
    reg [13:0] mem_a [0:1];
    reg [13:0] mem_b [0:1];
    reg        wptr;

    always @(posedge clk_cap) begin
        if (rst_cap) begin
            wptr <= 1'b0;
        end else begin
            mem_a[wptr] <= raw_a;
            mem_b[wptr] <= raw_b;
            wptr        <= ~wptr;
        end
    end

    reg [2:0] wsync;
    reg       wseen;
    always @(posedge clk_sys) begin
        if (rst) begin
            wsync     <= 3'b000;
            wseen     <= 1'b0;
            cha_data  <= 16'd0;
            chb_data  <= 16'd0;
            cha_valid <= 1'b0;
            chb_valid <= 1'b0;
        end else begin
            wsync <= {wsync[1:0], wptr};
            if (cha_valid && cha_ready)
                cha_valid <= 1'b0;
            if (chb_valid && chb_ready)
                chb_valid <= 1'b0;
            if (wsync[2] != wseen) begin
                wseen     <= wsync[2];
                cha_data  <= {2'b0, mem_a[~wsync[2]]};
                chb_data  <= {2'b0, mem_b[~wsync[2]]};
                cha_valid <= 1'b1;
                chb_valid <= 1'b1;
            end
        end
    end
endmodule

`default_nettype wire
