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
`include "config.vh"

module udp_scope_top (
    input  wire       clk25,
    output wire       led,
    output wire       eth_rst_n,
    output wire       eth_txc,
    output wire       eth_tx_ctl,
    output wire [3:0] eth_txd,
    output wire       eth1_txc,
    output wire       eth1_tx_ctl,
    output wire [3:0] eth1_txd,
    output wire       eth_mdc,
    inout  wire       eth_mdio,

    output wire       adc_clk_a,
    output wire       adc_clk_b,
    input  wire [13:0] adc_d,
    input  wire       adc_otr_a,
    input  wire       adc_otr_b
);
    wire clk_sys;
    wire clk_adc;
    wire pll_locked;

    pll_25to125 u_pll (
        .clkin  (clk25),
        .clkout (clk_sys),
        .locked (pll_locked)
    );

    reg [2:0] rst_sync = 3'b111;
    always @(posedge clk_sys or negedge pll_locked) begin
        if (!pll_locked)
            rst_sync <= 3'b111;
        else
            rst_sync <= {rst_sync[1:0], 1'b0};
    end
    wire rst = rst_sync[2];

    localparam PHY_RESET_CYCLES = 21'd1_250_000;
    reg [20:0] phy_cnt = 0;
    reg        phy_done = 1'b0;
    always @(posedge clk_sys) begin
        if (rst) begin
            phy_cnt  <= 0;
            phy_done <= 1'b0;
        end else if (!phy_done) begin
            phy_cnt <= phy_cnt + 1'b1;
            if (phy_cnt == PHY_RESET_CYCLES)
                phy_done <= 1'b1;
        end
    end
    assign eth_rst_n = phy_done;
    assign eth_mdc   = 1'b0;
    assign eth_mdio  = 1'bz;

    wire rst_app = rst || !phy_done;

    // 125 MHz / 4 = 31.25 MHz ADC clocks (PLL stays 125 MHz only).
    reg [1:0] adc_div;
    always @(posedge clk_sys) begin
        if (rst)
            adc_div <= 2'd0;
        else
            adc_div <= adc_div + 1'b1;
    end
    wire clk_adc_u = adc_div[1];
    BUFG bufg_adc (
        .I (clk_adc_u),
        .O (clk_adc)
    );

    wire [15:0] cha_data, chb_data;
    wire        cha_valid, chb_valid, cha_ready, chb_ready;

    adc_ad9248 u_adc (
        .clk_sys   (clk_sys),
        .clk_adc   (clk_adc),
        .clk_cap   (clk_adc),
        .rst       (rst_app),
        .adc_d     (adc_d),
        .adc_clk_a (adc_clk_a),
        .adc_clk_b (adc_clk_b),
        .cha_data  (cha_data),
        .cha_valid (cha_valid),
        .cha_ready (cha_ready),
        .chb_data  (chb_data),
        .chb_valid (chb_valid),
        .chb_ready (chb_ready)
    );

    wire        start_a, busy_a, tvalid_a, tready_a, tlast_a, pulse_a, ovf_a;
    wire        start_b, busy_b, tvalid_b, tready_b, tlast_b, pulse_b, ovf_b;
    wire [15:0] plen_a, plen_b;
    wire [7:0]  tdata_a, tdata_b;

    adc_packetizer #(
        .SAMPLES_PER_PKT (`SAMPLES_PER_PKT),
        .FIFO_DEPTH      (2048),
        .ADC_BITS        (`ADC_BITS),
        .OFFSET_BIN      (1)
    ) u_pack_a (
        .clk         (clk_sys),
        .rst         (rst_app),
        .adc_data    (cha_data),
        .adc_valid   (cha_valid),
        .adc_ready   (cha_ready),
        .overflow    (ovf_a),
        .start       (start_a),
        .payload_len (plen_a),
        .tx_busy     (busy_a),
        .tdata       (tdata_a),
        .tvalid      (tvalid_a),
        .tready      (tready_a),
        .tlast       (tlast_a),
        .pkt_pulse   (pulse_a)
    );

    adc_packetizer #(
        .SAMPLES_PER_PKT (`SAMPLES_PER_PKT),
        .FIFO_DEPTH      (2048),
        .ADC_BITS        (`ADC_BITS),
        .OFFSET_BIN      (1)
    ) u_pack_b (
        .clk         (clk_sys),
        .rst         (rst_app),
        .adc_data    (chb_data),
        .adc_valid   (chb_valid),
        .adc_ready   (chb_ready),
        .overflow    (ovf_b),
        .start       (start_b),
        .payload_len (plen_b),
        .tx_busy     (busy_b),
        .tdata       (tdata_b),
        .tvalid      (tvalid_b),
        .tready      (tready_b),
        .tlast       (tlast_b),
        .pkt_pulse   (pulse_b)
    );

    wire [7:0] gmii_a_d, gmii_b_d;
    wire       gmii_a_en, gmii_b_en;

    wire mac_busy_a, mac_busy_b;
    wire link_busy = mac_busy_a | mac_busy_b;
    reg  last_was_a;
    always @(posedge clk_sys) begin
        if (rst_app)
            last_was_a <= 1'b0;
        else if (start_a)
            last_was_a <= 1'b1;
        else if (start_b)
            last_was_a <= 1'b0;
    end
    assign busy_a = link_busy | last_was_a;
    assign busy_b = link_busy | ~last_was_a;

    udp_packet_tx #(
        .SRC_MAC      (`SRC_MAC),
        .DST_MAC      (`DST_MAC),
        .SRC_IP       (`SRC_IP),
        .DST_IP       (`DST_IP),
        .SRC_PORT     (`SRC_PORT_A),
        .DST_PORT     (`DST_PORT_A),
        .NIBBLE_MODE  (0)
    ) u_udp_a (
        .clk         (clk_sys),
        .rst         (rst_app),
        .start       (start_a),
        .payload_len (plen_a),
        .busy        (mac_busy_a),
        .tdata       (tdata_a),
        .tvalid      (tvalid_a),
        .tready      (tready_a),
        .tlast       (tlast_a),
        .gmii_d      (gmii_a_d),
        .gmii_en     (gmii_a_en)
    );

    udp_packet_tx #(
        .SRC_MAC      (`SRC_MAC),
        .DST_MAC      (`DST_MAC),
        .SRC_IP       (`SRC_IP),
        .DST_IP       (`DST_IP),
        .SRC_PORT     (`SRC_PORT_B),
        .DST_PORT     (`DST_PORT_B),
        .NIBBLE_MODE  (0)
    ) u_udp_b (
        .clk         (clk_sys),
        .rst         (rst_app),
        .start       (start_b),
        .payload_len (plen_b),
        .busy        (mac_busy_b),
        .tdata       (tdata_b),
        .tvalid      (tvalid_b),
        .tready      (tready_b),
        .tlast       (tlast_b),
        .gmii_d      (gmii_b_d),
        .gmii_en     (gmii_b_en)
    );

    wire [7:0] gmii_d  = gmii_a_en ? gmii_a_d : gmii_b_d;
    wire       gmii_en = gmii_a_en | gmii_b_en;

    rgmii_tx #(.NIBBLE_MODE(0)) u_rgmii0 (
        .clk125      (clk_sys),
        .gmii_d      (gmii_d),
        .gmii_en     (gmii_en),
        .rgmii_txc   (eth_txc),
        .rgmii_txd   (eth_txd),
        .rgmii_tx_ctl(eth_tx_ctl)
    );

    rgmii_tx #(.NIBBLE_MODE(0)) u_rgmii1 (
        .clk125      (clk_sys),
        .gmii_d      (gmii_d),
        .gmii_en     (gmii_en),
        .rgmii_txc   (eth1_txc),
        .rgmii_txd   (eth1_txd),
        .rgmii_tx_ctl(eth1_tx_ctl)
    );

    reg [26:0] hb;
    always @(posedge clk_sys) begin
        if (rst)
            hb <= 0;
        else
            hb <= hb + 1'b1;
    end
    wire ovf = ovf_a | ovf_b;
    wire otr = adc_otr_a | adc_otr_b;
    assign led = ovf ? hb[23] : (otr ? hb[24] : hb[26]);
endmodule

`default_nettype wire
