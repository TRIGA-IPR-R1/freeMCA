// SPDX-License-Identifier: GPL-3.0-or-later
//
// Blocos auxiliares do mca_top.v: gerador de bytes dos pacotes do MCA e UART.

`default_nettype none

// =============================================================================
// pkt_byte - entrega o byte 'idx' do pacote, 3 ciclos depois do pedido
//   idx < cab_len : byte do cabeçalho (cab, byte 0 = bits 207..200)
//   senão         : amostras do buffer circular, a partir de rd_inicio (alto, baixo)
// =============================================================================
module pkt_byte (
    input  wire         clk,
    input  wire [10:0]  idx,
    input  wire [207:0] cab,
    input  wire [4:0]   cab_len,
    input  wire [9:0]   rd_inicio,
    output reg  [9:0]   ram_addr,
    input  wire [13:0]  ram_q,        // ram[ram_addr], um ciclo depois (leitura síncrona fora daqui)
    output reg  [7:0]   saida
);
    reg  [10:0] idx_r = 11'd0, idx_r2 = 11'd0;
    wire [10:0] rel   = idx    - {6'd0, cab_len};
    wire [10:0] rel2  = idx_r2 - {6'd0, cab_len};
    wire [4:0]  pos_c = 5'd25 - idx_r2[4:0];
    wire [7:0]  cab_b = cab[{pos_c, 3'b000} +: 8];

    initial begin ram_addr = 10'd0; saida = 8'd0; end

    always @(posedge clk) begin
        idx_r    <= idx;
        ram_addr <= rd_inicio + rel[10:1];
        idx_r2   <= idx_r;
        if (idx_r2 < {6'd0, cab_len}) saida <= cab_b;
        else if (!rel2[0])            saida <= {2'b00, ram_q[13:8]};
        else                          saida <= ram_q[7:0];
    end
endmodule

// =============================================================================
// UART RX (2.000.000 bps @ 50 MHz, 8N1) - amostra no meio de cada bit
// =============================================================================
module uart_rx (
    input  wire       clk,
    input  wire       rx_pin,
    output reg  [7:0] dado,
    output reg        valido
);
    localparam integer CPB = 25;                 // ciclos por bit
    reg [2:0] sinc = 3'b111;
    reg [1:0] est  = 2'd0;
    reg [5:0] cnt  = 6'd0;
    reg [2:0] nbit = 3'd0;
    reg [7:0] sr   = 8'd0;
    wire      rx   = sinc[2];
    initial begin dado = 8'd0; valido = 1'b0; end

    always @(posedge clk) begin
        sinc   <= {sinc[1:0], rx_pin};
        valido <= 1'b0;
        case (est)
            2'd0: begin                                   // repouso: espera o bit de partida
                cnt <= 6'd0;
                if (!rx) est <= 2'd1;
            end
            2'd1: begin                                   // meio do bit de partida
                if (cnt == CPB / 2 - 1) begin
                    cnt  <= 6'd0;
                    nbit <= 3'd0;
                    est  <= rx ? 2'd0 : 2'd2;             // ruído curto: descarta
                end else cnt <= cnt + 1'b1;
            end
            2'd2: begin                                   // 8 bits de dados, LSB primeiro
                if (cnt == CPB - 1) begin
                    cnt  <= 6'd0;
                    sr   <= {rx, sr[7:1]};
                    nbit <= nbit + 1'b1;
                    if (nbit == 3'd7) est <= 2'd3;
                end else cnt <= cnt + 1'b1;
            end
            default: begin                                // bit de parada
                if (cnt == CPB - 1) begin
                    if (rx) begin dado <= sr; valido <= 1'b1; end
                    est <= 2'd0;
                end else cnt <= cnt + 1'b1;
            end
        endcase
    end
endmodule

// =============================================================================
// UART TX (2.000.000 bps @ 50 MHz)
// =============================================================================
module uart_tx (
    input  wire       clk,
    input  wire       tx_start,
    input  wire [7:0] tx_data,
    output reg        tx_pin,
    output reg        tx_busy
);
    localparam CYCLES_PER_BIT = 25;
    reg [9:0]  shift_reg;
    reg [3:0]  bit_idx;
    reg [15:0] clk_count;
    reg        state;
    initial begin tx_pin = 1'b1; tx_busy = 1'b0; state = 1'b0; end
    always @(posedge clk) begin
        case (state)
            1'b0: begin
                tx_pin <= 1'b1;
                if (tx_start) begin
                    shift_reg <= {1'b1, tx_data, 1'b0};
                    bit_idx   <= 0;
                    clk_count <= 0;
                    tx_busy   <= 1'b1;
                    state     <= 1'b1;
                end else begin
                    tx_busy <= 1'b0;
                end
            end
            1'b1: begin
                tx_pin <= shift_reg[0];
                if (clk_count < CYCLES_PER_BIT - 1) begin
                    clk_count <= clk_count + 1'b1;
                end else begin
                    clk_count <= 0;
                    shift_reg <= {1'b1, shift_reg[9:1]};
                    bit_idx   <= bit_idx + 1'b1;
                    if (bit_idx == 9) begin
                        tx_busy <= 1'b0;
                        state   <= 1'b0;
                    end
                end
            end
        endcase
    end
endmodule

`default_nettype wire
