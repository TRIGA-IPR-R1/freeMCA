// SPDX-License-Identifier: GPL-3.0-or-later
//
// 25 MHz da placa -> 50 MHz (aquisição) e 125 MHz (RGMII).
// Mesma configuração do pll_25to125 do oscilloscopeMode (VCO em 1000 MHz, 125 MHz em
// CLKOUT0), com uma segunda saída de 50 MHz em CLKOUT1.

`default_nettype none

module mca_pll (
    input  wire clkin,
    output wire clk50,
    output wire clk125,
    output wire locked
);
    wire clkfb;
    wire clkin_u;
    wire clk125_u;
    wire clk50_u;

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
        .CLKOUT1_DIVIDE     (20),
        .CLKOUT1_DUTY_CYCLE (0.5),
        .CLKOUT1_PHASE      (0.0),
        .DIVCLK_DIVIDE      (1),
        .REF_JITTER1        (0.01),
        .STARTUP_WAIT       ("FALSE")
    ) pll (
        .CLKIN1   (clkin_u),
        .CLKFBIN  (clkfb),
        .CLKFBOUT (clkfb),
        .CLKOUT0  (clk125_u),
        .CLKOUT1  (clk50_u),
        .CLKOUT2  (),
        .CLKOUT3  (),
        .CLKOUT4  (),
        .CLKOUT5  (),
        .LOCKED   (locked),
        .PWRDWN   (1'b0),
        .RST      (1'b0)
    );

    BUFG bufg_125 (
        .I (clk125_u),
        .O (clk125)
    );

    BUFG bufg_50 (
        .I (clk50_u),
        .O (clk50)
    );
endmodule

`default_nettype wire
