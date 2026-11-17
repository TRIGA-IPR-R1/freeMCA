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

// 25 MHz board clock -> 125 MHz RGMII. ADC clocks are divided in fabric
// from this 125 MHz so the PLL stays in the same config that already
// brought the 1G link up.
module pll_25to125 (
    input  wire clkin,
    output wire clkout,
    output wire locked
);
    wire clkfb;
    wire clkout_u;
    wire clkin_u;

    IBUF ibuf_clk (
        .I (clkin),
        .O (clkin_u)
    );

    PLLE2_BASE #(
        .BANDWIDTH          ("OPTIMIZED"),
        .CLKFBOUT_MULT      (40),
        .CLKFBOUT_PHASE     (0.0),
        .CLKIN1_PERIOD      (40.0),
        .CLKOUT0_DIVIDE     (8),
        .CLKOUT0_DUTY_CYCLE (0.5),
        .CLKOUT0_PHASE      (0.0),
        .DIVCLK_DIVIDE      (1),
        .REF_JITTER1        (0.01),
        .STARTUP_WAIT       ("FALSE")
    ) pll (
        .CLKIN1   (clkin_u),
        .CLKFBIN  (clkfb),
        .CLKFBOUT (clkfb),
        .CLKOUT0  (clkout_u),
        .CLKOUT1  (),
        .CLKOUT2  (),
        .CLKOUT3  (),
        .CLKOUT4  (),
        .CLKOUT5  (),
        .LOCKED   (locked),
        .PWRDWN   (1'b0),
        .RST      (1'b0)
    );

    BUFG bufg_clk (
        .I (clkout_u),
        .O (clkout)
    );
endmodule

`default_nettype wire
