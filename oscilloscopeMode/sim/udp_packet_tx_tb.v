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

module udp_packet_tx_tb;
    reg clk = 0;
    always #4 clk = ~clk; // 125 MHz

    reg rst = 1;
    reg start = 0;
    reg [15:0] payload_len = 16'd14; // 10 header + 2 samples
    reg [7:0] tdata = 0;
    reg tvalid = 0;
    reg tlast = 0;
    wire tready, busy;
    wire [7:0] gmii_d;
    wire gmii_en;

    udp_packet_tx uut (
        .clk(clk), .rst(rst),
        .start(start), .payload_len(payload_len), .busy(busy),
        .tdata(tdata), .tvalid(tvalid), .tready(tready), .tlast(tlast),
        .gmii_d(gmii_d), .gmii_en(gmii_en)
    );

    integer fd;
    integer i;
    reg [7:0] payload [0:13];

    initial begin
        payload[0]  = 8'hc0; payload[1]  = 8'had;
        payload[2]  = 8'h00; payload[3]  = 8'h00; payload[4] = 8'h00; payload[5] = 8'h00;
        payload[6]  = 8'h02; payload[7]  = 8'h00;
        payload[8]  = 8'h00; payload[9]  = 8'h00;
        payload[10] = 8'h00; payload[11] = 8'h00;
        payload[12] = 8'h01; payload[13] = 8'h00;

        fd = $fopen("gmii.hex", "w");
        repeat (10) @(posedge clk);
        rst = 0;
        repeat (5) @(posedge clk);

        @(posedge clk);
        start <= 1;
        @(posedge clk);
        start <= 0;

        i = 0;
        tvalid <= 1;
        tdata  <= payload[0];
        tlast  <= 0;
        while (i < 14) begin
            @(posedge clk);
            if (tready) begin
                i = i + 1;
                if (i < 14) begin
                    tdata <= payload[i];
                    tlast <= (i == 13);
                end else begin
                    tvalid <= 0;
                    tlast  <= 0;
                end
            end
        end

        wait (!busy);
        repeat (20) @(posedge clk);
        $fclose(fd);
        $finish;
    end

    always @(posedge clk) begin
        if (!rst && gmii_en)
            $fwrite(fd, "%02x\n", gmii_d);
    end
endmodule
