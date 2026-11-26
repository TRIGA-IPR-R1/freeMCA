// SPDX-License-Identifier: GPL-3.0-or-later
//
// Rede do modo MCA. Mesmos nomes e valores do oscilloscopeMode/rtl/config.vh:
// a FPGA envia para DST_IP:DST_PORT_A; o MAC de destino é broadcast, então não
// precisa de ARP. No PC: sudo ip addr add 192.168.1.100/24 dev <iface>

`ifndef MCA_CONFIG_VH
`define MCA_CONFIG_VH

`define SRC_MAC        48'h02_12_34_56_78_9a
`define DST_MAC        48'hff_ff_ff_ff_ff_ff
`define SRC_IP         {8'd192, 8'd168, 8'd1, 8'd50}
`define DST_IP         {8'd192, 8'd168, 8'd1, 8'd100}
`define SRC_PORT_A     16'd5000
`define DST_PORT_A     16'd5000

// Fluxo contínuo (MODO 2): AD9245, 14 bits empacotados, offset binary.
// 720 amostras x 14 bits = 1260 bytes de dados + 10 de cabeçalho por datagrama.
`define SAMPLES_PER_PKT 16'd720
`define ADC_BITS        5'd14

`endif
