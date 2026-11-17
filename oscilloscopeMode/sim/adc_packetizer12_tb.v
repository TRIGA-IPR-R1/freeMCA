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
`timescale 1ns/1ps

module adc_packetizer12_tb;
    reg clk = 0;
    always #4 clk = ~clk;

    reg rst = 1;
    reg [15:0] adc_data = 0;
    reg adc_valid = 0;
    wire adc_ready, overflow, start, tx_busy, tvalid, tready, tlast, pkt_pulse;
    wire [15:0] payload_len;
    wire [7:0] tdata;

    assign tx_busy = 1'b0;
    assign tready  = tvalid;

    adc_packetizer #(
        .SAMPLES_PER_PKT(16),
        .FIFO_DEPTH(64),
        .ADC_BITS(12),
        .OFFSET_BIN(1)
    ) uut (
        .clk(clk), .rst(rst),
        .adc_data(adc_data), .adc_valid(adc_valid), .adc_ready(adc_ready),
        .overflow(overflow),
        .start(start), .payload_len(payload_len), .tx_busy(tx_busy),
        .tdata(tdata), .tvalid(tvalid), .tready(tready), .tlast(tlast),
        .pkt_pulse(pkt_pulse)
    );

    integer i, n_pay;
    integer fd;
    initial begin
        fd = $fopen("pack12.hex", "w");
        repeat (5) @(posedge clk);
        rst = 0;
        for (i = 0; i < 16; i = i + 1) begin
            @(posedge clk);
            while (!adc_ready) @(posedge clk);
            adc_data  = {4'b0, i[11:0]};
            adc_valid = 1'b1;
            @(posedge clk);
            adc_valid = 1'b0;
        end
        n_pay = 0;
        while (n_pay < 10 + (16 * 12) / 8) begin
            @(posedge clk);
            if (tvalid && tready) begin
                $fwrite(fd, "%02x\n", tdata);
                n_pay = n_pay + 1;
            end
        end
        $fclose(fd);
        $display("payload_len=%0d bytes_logged=%0d", payload_len, n_pay);
        $finish;
    end
endmodule
