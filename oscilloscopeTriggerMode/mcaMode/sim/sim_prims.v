// Modelos de SIMULAÇÃO das primitivas Xilinx usadas (não vão para a síntese).
`timescale 1ns/1ps
module BUFG(input I, output O); assign O = I; endmodule

module IBUF(input I, output O); assign O = I; endmodule

module PLLE2_BASE #(
    parameter BANDWIDTH = "OPTIMIZED", parameter STARTUP_WAIT = "FALSE", parameter real REF_JITTER1 = 0.01,
    parameter integer CLKFBOUT_MULT = 5, parameter real CLKFBOUT_PHASE = 0.0, parameter real CLKIN1_PERIOD = 10.0,
    parameter integer DIVCLK_DIVIDE = 1,
    parameter integer CLKOUT0_DIVIDE = 1, parameter real CLKOUT0_PHASE = 0.0, parameter real CLKOUT0_DUTY_CYCLE = 0.5,
    parameter integer CLKOUT1_DIVIDE = 1, parameter real CLKOUT1_PHASE = 0.0, parameter real CLKOUT1_DUTY_CYCLE = 0.5,
    parameter integer CLKOUT2_DIVIDE = 1, parameter real CLKOUT2_PHASE = 0.0, parameter real CLKOUT2_DUTY_CYCLE = 0.5
)(output reg CLKOUT0, output reg CLKOUT1, output reg CLKOUT2, output CLKOUT3, output CLKOUT4, output CLKOUT5,
  output CLKFBOUT, output reg LOCKED, input CLKIN1, input PWRDWN, input RST, input CLKFBIN);
    assign CLKFBOUT = CLKIN1;
    assign CLKOUT3 = 1'b0; assign CLKOUT4 = 1'b0; assign CLKOUT5 = 1'b0;
    real tvco, p0, p1, p2;
    initial begin
        CLKOUT0 = 0; CLKOUT1 = 0; CLKOUT2 = 0; LOCKED = 0;
        tvco = CLKIN1_PERIOD * DIVCLK_DIVIDE / CLKFBOUT_MULT;
        p0 = tvco * CLKOUT0_DIVIDE; p1 = tvco * CLKOUT1_DIVIDE; p2 = tvco * CLKOUT2_DIVIDE;
        repeat (6) @(posedge CLKIN1);
        fork
            begin #(p0 * CLKOUT0_PHASE / 360.0); forever begin CLKOUT0 = 1; #(p0/2); CLKOUT0 = 0; #(p0/2); end end
            begin #(p1 * CLKOUT1_PHASE / 360.0); forever begin CLKOUT1 = 1; #(p1/2); CLKOUT1 = 0; #(p1/2); end end
            begin #(p2 * CLKOUT2_PHASE / 360.0); forever begin CLKOUT2 = 1; #(p2/2); CLKOUT2 = 0; #(p2/2); end end
            begin #200; LOCKED = 1; end
        join
    end
endmodule

module ODDR #(parameter DDR_CLK_EDGE = "SAME_EDGE", parameter INIT = 1'b0, parameter SRTYPE = "SYNC")
    (output reg Q, input C, input CE, input D1, input D2, input R, input S);
    reg d2r; initial begin Q = INIT; d2r = INIT; end
    always @(posedge C) begin Q <= D1; d2r <= D2; end
    always @(negedge C) Q <= d2r;
endmodule

module IDDR #(parameter DDR_CLK_EDGE = "SAME_EDGE", parameter INIT_Q1 = 1'b0, parameter INIT_Q2 = 1'b0, parameter SRTYPE = "SYNC")
    (output reg Q1, output reg Q2, input C, input CE, input D, input R, input S);
    reg q2n; initial begin Q1 = 0; Q2 = 0; q2n = 0; end
    always @(negedge C) q2n <= D;
    always @(posedge C) begin Q1 <= D; Q2 <= q2n; end   // SAME_EDGE: Q2 = amostra da descida anterior
endmodule
