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

// TX-only Ethernet II + IPv4 + UDP. One GMII byte per clock at 125 MHz.
// `start` + `payload_len` begin a frame; payload bytes follow on AXI-Stream.
module udp_packet_tx #(
    parameter [47:0] SRC_MAC  = 48'h02123456789a,
    parameter [47:0] DST_MAC  = 48'hffffffffffff,
    parameter [31:0] SRC_IP   = {8'd192, 8'd168, 8'd1, 8'd50},
    parameter [31:0] DST_IP   = {8'd192, 8'd168, 8'd1, 8'd100},
    parameter [15:0] SRC_PORT = 16'd5000,
    parameter [15:0] DST_PORT = 16'd5000,
    // 1 = 100 Mbps RGMII: each GMII byte is held two 25 MHz clocks.
    parameter         NIBBLE_MODE = 0
) (
    input  wire       clk,
    input  wire       rst,

    input  wire       start,
    input  wire [15:0] payload_len,
    output reg        busy,

    input  wire [7:0] tdata,
    input  wire       tvalid,
    output wire       tready,
    input  wire       tlast,

    output reg  [7:0] gmii_d,
    output reg        gmii_en
);
    localparam ST_IDLE     = 3'd0;
    localparam ST_PREAMBLE = 3'd1;
    localparam ST_HEADER   = 3'd2;
    localparam ST_PAYLOAD  = 3'd3;
    localparam ST_PAD      = 3'd4;
    localparam ST_FCS      = 3'd5;
    localparam ST_IFG      = 3'd6;

    localparam HDR_LEN = 6'd42; // dest MAC .. UDP checksum

    reg [2:0]  state;
    reg [15:0] len_latched;
    reg [15:0] payload_sent;
    reg [5:0]  byte_idx;
    reg [3:0]  pad_left;
    reg [31:0] crc;

    wire [31:0] crc_next;
    crc32_eth u_crc (
        .crc_in  (crc),
        .data    (gmii_d),
        .crc_out (crc_next)
    );

    wire [15:0] ip_len  = 16'd28 + len_latched;
    wire [15:0] udp_len = 16'd8  + len_latched;

    // IPv4 header checksum (checksum field = 0).
    wire [31:0] csum_acc =
        32'h4500 + ip_len + 32'h0000 + 32'h4000 + 32'h4011 +
        SRC_IP[31:16] + SRC_IP[15:0] + DST_IP[31:16] + DST_IP[15:0];
    wire [31:0] csum_fold = csum_acc[15:0] + csum_acc[31:16];
    wire [15:0] ip_csum   = ~(csum_fold[15:0] + csum_fold[16]);

    wire [8*HDR_LEN-1:0] hdr = {
        DST_MAC,
        SRC_MAC,
        16'h0800,
        8'h45, 8'h00, ip_len,
        16'h0000,
        16'h4000,
        8'h40, 8'h11, ip_csum,
        SRC_IP,
        DST_IP,
        SRC_PORT,
        DST_PORT,
        udp_len,
        16'h0000
    };

    wire [7:0] hdr_byte = hdr[8*(HDR_LEN-1-byte_idx) +: 8];

    // Ethernet payload (ethertype body) must be >= 46 bytes.
    wire [15:0] l3_len      = 16'd28 + len_latched;
    wire [3:0]  pad_needed  = (l3_len < 16'd46) ? (46 - l3_len[5:0]) : 4'd0;

    // In 100 Mbps nibble mode the FSM steps on phase==1 (second half of byte).
    reg phase;
    wire step = (NIBBLE_MODE == 0) || phase;

    assign tready = (state == ST_PAYLOAD) && ((NIBBLE_MODE == 0) || (phase == 1'b0));

    // gmii_d is registered in the same cycle we decide the byte, so CRC
    // of the *current* output byte is applied on the following edge.
    reg crc_en;
    reg crc_init;

    always @(posedge clk) begin
        if (rst) begin
            state        <= ST_IDLE;
            busy         <= 1'b0;
            gmii_d       <= 8'h00;
            gmii_en      <= 1'b0;
            byte_idx     <= 0;
            payload_sent <= 0;
            pad_left     <= 0;
            len_latched  <= 0;
            crc          <= 32'hffffffff;
            crc_en       <= 1'b0;
            crc_init     <= 1'b0;
            phase        <= 1'b0;
        end else begin
            crc_en   <= 1'b0;
            crc_init <= 1'b0;
            if (crc_init)
                crc <= 32'hffffffff;
            else if (crc_en)
                crc <= crc_next;

            if (NIBBLE_MODE && state != ST_IDLE && !step) begin
                phase <= 1'b1;
            end else begin
            if (NIBBLE_MODE)
                phase <= 1'b0;

            case (state)
                ST_IDLE: begin
                    gmii_en <= 1'b0;
                    gmii_d  <= 8'h00;
                    busy    <= 1'b0;
                    if (start && payload_len != 0) begin
                        busy        <= 1'b1;
                        len_latched <= payload_len;
                        byte_idx    <= 0;
                        crc_init    <= 1'b1;
                        state       <= ST_PREAMBLE;
                    end
                end

                ST_PREAMBLE: begin
                    gmii_en <= 1'b1;
                    if (byte_idx < 7) begin
                        gmii_d   <= 8'h55;
                        byte_idx <= byte_idx + 1'b1;
                    end else begin
                        gmii_d   <= 8'hd5;
                        byte_idx <= 0;
                        state    <= ST_HEADER;
                    end
                end

                ST_HEADER: begin
                    gmii_en <= 1'b1;
                    gmii_d  <= hdr_byte;
                    crc_en  <= 1'b1;
                    if (byte_idx == HDR_LEN - 1) begin
                        byte_idx     <= 0;
                        payload_sent <= 0;
                        state        <= ST_PAYLOAD;
                    end else begin
                        byte_idx <= byte_idx + 1'b1;
                    end
                end

                ST_PAYLOAD: begin
                    // Payload must not stall: the packetizer keeps tvalid high.
                    gmii_en <= 1'b1;
                    gmii_d  <= tvalid ? tdata : 8'h00;
                    crc_en  <= 1'b1;
                    payload_sent <= payload_sent + 1'b1;
                    if ((payload_sent + 1'b1) >= len_latched || tlast) begin
                        if (pad_needed != 0) begin
                            pad_left <= pad_needed;
                            state    <= ST_PAD;
                        end else begin
                            byte_idx <= 0;
                            state    <= ST_FCS;
                        end
                    end
                end

                ST_PAD: begin
                    gmii_en <= 1'b1;
                    gmii_d  <= 8'h00;
                    crc_en  <= 1'b1;
                    if (pad_left == 1) begin
                        byte_idx <= 0;
                        state    <= ST_FCS;
                    end else begin
                        pad_left <= pad_left - 1'b1;
                    end
                end

                ST_FCS: begin
                    gmii_en <= 1'b1;
                    crc_en  <= 1'b0;
                    // First FCS cycle: crc_next still covers the last payload/pad
                    // byte sitting in gmii_d from the previous cycle.
                    if (byte_idx == 0) begin
                        gmii_d <= ~crc_next[7:0];
                        crc    <= crc_next;
                    end else begin
                        case (byte_idx)
                            1: gmii_d <= ~crc[15:8];
                            2: gmii_d <= ~crc[23:16];
                            default: gmii_d <= ~crc[31:24];
                        endcase
                    end
                    if (byte_idx == 3) begin
                        byte_idx <= 0;
                        state    <= ST_IFG;
                    end else begin
                        byte_idx <= byte_idx + 1'b1;
                    end
                end

                ST_IFG: begin
                    gmii_en <= 1'b0;
                    gmii_d  <= 8'h00;
                    if (byte_idx == 11)
                        state <= ST_IDLE;
                    else
                        byte_idx <= byte_idx + 1'b1;
                end

                default: state <= ST_IDLE;
            endcase
            end
        end
    end
endmodule

`default_nettype wire
