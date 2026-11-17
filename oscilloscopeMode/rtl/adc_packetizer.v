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

// Packs ADC samples into UDP payloads:
//   magic u16 = 0xADC0 | seq u32 | n u16 | flags u16 | packed samples
// Little-endian bitstream, ADC_BITS per sample (14-bit: 4 samples = 7 bytes).
// flags bit0 = FIFO overflow since previous packet
// flags bit1 = packed (ADC_BITS != 16)
// flags bit2 = offset binary (AD9248 direct code)
module adc_packetizer #(
    parameter SAMPLES_PER_PKT = 720,
    parameter FIFO_DEPTH      = 2048,
    parameter ADC_BITS        = 14,
    parameter OFFSET_BIN      = 1
) (
    input  wire        clk,
    input  wire        rst,

    input  wire [15:0] adc_data,
    input  wire        adc_valid,
    output wire        adc_ready,
    output wire        overflow,

    output reg         start,
    output wire [15:0] payload_len,
    input  wire        tx_busy,

    output reg  [7:0]  tdata,
    output reg         tvalid,
    input  wire        tready,
    output reg         tlast,
    output reg         pkt_pulse
);
    localparam ST_FILL = 2'd0;
    localparam ST_HDR  = 2'd1;
    localparam ST_DATA = 2'd2;

    localparam [15:0] MAGIC = 16'hADC0;
    localparam HDR_BYTES = 10;
    localparam DATA_BYTES = (SAMPLES_PER_PKT * ADC_BITS) / 8;
    localparam PACKED = (ADC_BITS != 16);
    localparam AW = $clog2(FIFO_DEPTH+1);

    wire             fifo_full, fifo_empty;
    wire [15:0]      fifo_dout;
    wire [AW-1:0]    fifo_count;
    wire             fifo_rd;
    reg              ovf_sticky;
    reg              ovf_pkt;

    assign adc_ready   = !fifo_full;
    assign overflow    = ovf_sticky;
    assign payload_len = HDR_BYTES + DATA_BYTES[15:0];

    sync_fifo #(
        .WIDTH(16),
        .DEPTH(FIFO_DEPTH)
    ) u_fifo (
        .clk   (clk),
        .rst   (rst),
        .wr_en (adc_valid && adc_ready),
        .din   (adc_data),
        .full  (fifo_full),
        .rd_en (fifo_rd),
        .dout  (fifo_dout),
        .empty (fifo_empty),
        .count (fifo_count)
    );

    always @(posedge clk) begin
        if (rst)
            ovf_sticky <= 1'b0;
        else if (adc_valid && fifo_full)
            ovf_sticky <= 1'b1;
        else if (start)
            ovf_sticky <= 1'b0;
    end

    reg [1:0]  state;
    reg [3:0]  hdr_idx;
    reg [15:0] byte_idx;
    reg [15:0] samples_used;
    reg [31:0] pack_acc;
    reg [4:0]  pack_bits;
    reg [31:0] seq;

    wire [4:0]  bits_left = pack_bits - 5'd8;
    wire [31:0] shifted   = {8'b0, pack_acc[31:8]};
    wire [31:0] injected  = shifted | ({{(32 - ADC_BITS){1'b0}}, fifo_dout[ADC_BITS-1:0]} << bits_left);
    wire        need_samp = (bits_left < 5'd8) && (samples_used < SAMPLES_PER_PKT);
    wire [31:0] next_acc  = need_samp ? injected : shifted;
    wire [4:0]  next_bits = need_samp ? (bits_left + ADC_BITS[4:0]) : bits_left;
    wire        last_byte = (byte_idx == DATA_BYTES[15:0] - 16'd1);

    // Combinational pop: dout is used this cycle, new word appears next cycle.
    assign fifo_rd =
        (state == ST_HDR && tready && hdr_idx == HDR_BYTES - 1) ||
        (state == ST_DATA && tready && !last_byte && need_samp);

    always @(posedge clk) begin
        if (rst) begin
            state        <= ST_FILL;
            start        <= 1'b0;
            tvalid       <= 1'b0;
            tdata        <= 8'h00;
            tlast        <= 1'b0;
            pkt_pulse    <= 1'b0;
            hdr_idx      <= 0;
            byte_idx     <= 0;
            samples_used <= 0;
            pack_acc     <= 0;
            pack_bits    <= 0;
            seq          <= 0;
            ovf_pkt      <= 1'b0;
        end else begin
            start     <= 1'b0;
            pkt_pulse <= 1'b0;
            tlast     <= 1'b0;

            case (state)
                ST_FILL: begin
                    tvalid <= 1'b0;
                    if (!tx_busy && fifo_count >= SAMPLES_PER_PKT) begin
                        ovf_pkt   <= ovf_sticky;
                        start     <= 1'b1;
                        pkt_pulse <= 1'b1;
                        hdr_idx   <= 0;
                        tvalid    <= 1'b1;
                        tdata     <= MAGIC[7:0];
                        state     <= ST_HDR;
                    end
                end

                ST_HDR: begin
                    tvalid <= 1'b1;
                    if (tready) begin
                        if (hdr_idx == HDR_BYTES - 1) begin
                            pack_acc     <= {{(32 - ADC_BITS){1'b0}}, fifo_dout[ADC_BITS-1:0]};
                            pack_bits    <= ADC_BITS[4:0];
                            samples_used <= 16'd1;
                            byte_idx     <= 0;
                            tdata        <= fifo_dout[7:0];
                            tlast        <= (DATA_BYTES == 1);
                            state        <= ST_DATA;
                        end else begin
                            hdr_idx <= hdr_idx + 1'b1;
                            case (hdr_idx + 1'b1)
                                1: tdata <= MAGIC[15:8];
                                2: tdata <= seq[7:0];
                                3: tdata <= seq[15:8];
                                4: tdata <= seq[23:16];
                                5: tdata <= seq[31:24];
                                6: tdata <= SAMPLES_PER_PKT[7:0];
                                7: tdata <= SAMPLES_PER_PKT[15:8];
                                8: tdata <= {5'b0, OFFSET_BIN[0], PACKED[0], ovf_pkt};
                                default: tdata <= 8'h00;
                            endcase
                        end
                    end
                end

                ST_DATA: begin
                    tvalid <= 1'b1;
                    tlast  <= last_byte;
                    if (tready) begin
                        if (last_byte) begin
                            tvalid <= 1'b0;
                            tlast  <= 1'b0;
                            seq    <= seq + 1'b1;
                            state  <= ST_FILL;
                        end else begin
                            pack_acc     <= next_acc;
                            pack_bits    <= next_bits;
                            tdata        <= next_acc[7:0];
                            byte_idx     <= byte_idx + 1'b1;
                            tlast        <= (byte_idx + 16'd1 == DATA_BYTES[15:0] - 16'd1);
                            if (need_samp)
                                samples_used <= samples_used + 16'd1;
                        end
                    end
                end

                default: state <= ST_FILL;
            endcase
        end
    end
endmodule

`default_nettype wire
