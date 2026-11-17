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

// Placeholder ADC: free-running two's-complement ramp at clk * NUM/DEN.
// BITS-wide counter, sign-extended into 16-bit samples for the UDP payload.
// Replace this module with the real converter; keep the same handshake.
module adc_ramp #(
    parameter NUM  = 4,
    parameter DEN  = 5,
    parameter BITS = 12
) (
    input  wire        clk,
    input  wire        rst,
    output reg  [15:0] adc_data,
    output reg         adc_valid,
    input  wire        adc_ready
);
    reg [16:0]      acc;
    reg [BITS-1:0]  cnt;

    wire [BITS-1:0] cnt_nxt = cnt + 1'b1;
    wire [15:0]     sample  = {{(16 - BITS){cnt_nxt[BITS-1]}}, cnt_nxt};

    always @(posedge clk) begin
        if (rst) begin
            acc       <= 0;
            cnt       <= 0;
            adc_data  <= 0;
            adc_valid <= 1'b0;
        end else begin
            if (adc_valid && adc_ready)
                adc_valid <= 1'b0;

            if (acc + NUM >= DEN) begin
                acc <= acc + NUM - DEN;
                if (!adc_valid || adc_ready) begin
                    cnt       <= cnt_nxt;
                    adc_data  <= sample;
                    adc_valid <= 1'b1;
                end
            end else begin
                acc <= acc + NUM;
            end
        end
    end
endmodule

`default_nettype wire
