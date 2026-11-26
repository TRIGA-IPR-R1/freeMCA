// SPDX-License-Identifier: GPL-3.0-or-later
//
// mca_top.v - modo MCA do freeMCA (Colorlight i9plus-v6.1 + KeYi AD9245)
// -----------------------------------------------------------------------------
// É o mca_ad9245_cfg.v (aquisição configurável por comando) com a parte de rede
// trocada pelos módulos do oscilloscopeMode e com um terceiro modo de envio:
//
//   MODO 0  formas    cada trigger envia a forma do pulso
//   MODO 1  picos     cada trigger envia só a medida do pico; com FILTRO = 1 a
//                     altura vem do filtro trapezoidal de Jordanov-Knoll
//                     (jk_trapezio.v), que substitui o amplificador formatador
//                     quando o ADC está ligado direto no pré-amplificador
//   MODO 2  contínuo  sem trigger: fluxo corrido de amostras, no formato do
//                     oscilloscopeMode (magic 0xADC0, seq, n, flags, 14 bits
//                     empacotados, 720 amostras por datagrama), sempre por UDP.
//                     A taxa é 25 MSPS / 2^LOG2_MEDIA.
//
// Vêm do oscilloscopeMode, sem alteração: adc_packetizer + sync_fifo (fila, número
// de sequência, flag de overflow, empacotamento), udp_packet_tx + crc32_eth (MAC)
// e rgmii_tx (saída DDR), nos dois PHYs. Endereços de rede em config.vh.
// Os pacotes do MCA (formas, picos, status) usam o mesmo MAC e a mesma porta UDP;
// distinguem-se do fluxo pelos dois primeiros bytes (FF FF contra C0 AD).
//
// Relógios: clk_sys = 50 MHz (ADC a 25 MHz e toda a aquisição, como validado no
// teste de rampa) e clk_125 = 125 MHz (rede). O PLL usa o mesmo VCO (1000 MHz)
// do oscilloscopeMode.
//
// COMANDO pela UART (6 bytes):  0xA5 0x5A  REG  VALOR_ALTO  VALOR_BAIXO  CHK
//                               CHK = REG ^ VALOR_ALTO ^ VALOR_BAIXO ^ 0xFF
//   REG  nome         faixa      significado
//    0   LIMIAR       4..8000    limiar de trigger acima da linha de base (LSB)
//    1   CONFIRMA     1..15      amostras seguidas acima do limiar para disparar
//    2   LOG2_MEDIA   0..4       média de 1,2,4,8,16 amostras do ADC (tick = 2^n x 40 ns)
//    3   POLARIDADE   0..1       0 = pulsos positivos, 1 = negativos
//    4   MODO         0..2       0 = formas, 1 = picos, 2 = contínuo
//    5   N_PRE        8..600     amostras antes do trigger   (N_PRE + N_POS <= 699)
//    6   N_POS        8..690     amostras depois do trigger = janela de busca do pico
//    7   SAIDA        0..1       0 = UART, 1 = UDP (formas e picos; o contínuo é sempre UDP)
//    8   ATIVO        0..1       0 = pausa a aquisição por trigger
//    9   STATUS       -          só pede o pacote de status
//   10   ZERA_TEMPO   -          zera timestamp e tempo vivo
//   11   FILTRO       0..1       1 = no modo picos, altura medida pelo filtro trapezoidal
//   12   TRAP_K       2..255     subida do trapézio (amostras)
//   13   TRAP_M       1..255     topo plano (amostras); maior que a subida do pulso do pré
//   14   TRAP_PZ      4..65535   polo-zero: 4 / (exp(dt/tau) - 1), tau = decaimento do pré
//   15   TRAP_SH      0..31      deslocamento à direita do resultado, para caber em 16 bits
// Todo comando é respondido com um pacote de STATUS pela UART (e por UDP se
// SAIDA = 1 ou MODO = 2). Comando fora da faixa não altera nada (ack = 0).
//
// PACOTES DO MCA (protocolo 2): 0xFF 0xFF CFG TIPO ..., com
//   CFG = {0, 3'd2, POLARIDADE, LOG2_MEDIA[2:0]}; campos em bytes de 7 bits.
//   TIPO 0 - forma:  NAM(2) NPRE(2) timestamp(5) tempo_vivo(5) + NAM x {hi, lo}
//   TIPO 1 - pico:   timestamp(5) tempo_vivo(5) PICO4(3) BASE(2) AREA(4) TPICO(2) FLAGS(1)
//                    FLAGS = bit0 saturou | bit1 empilhamento | bit2 ainda acima de
//                    limiar/2 no fim | bit3 pico na última amostra | bit4 medido
//                    pelo filtro trapezoidal
//                    Sem filtro: PICO4 = 4 x altura (filtro 1-2-1).
//                    Com filtro: PICO4 = (topo do trapézio - linha de base do trapézio)
//                    >> TRAP_SH, ou seja, altura x TRAP_K x (TRAP_PZ + 4) / 2^TRAP_SH.
//   TIPO 2 - status: VERSAO LIMIAR(2) CONFIRMA MODO SAIDA ATIVO NPRE(2) NPOS(2) ACK REG
//                    FILTRO TRAP_K(2) TRAP_M(2) TRAP_PZ(3) TRAP_SH        (26 bytes)
//
// LED: piscada lenta = ok; média = o ADC saturou há pouco; rápida = overflow da
// fila do fluxo contínuo.
// =============================================================================
`default_nettype none
`include "config.vh"

module mca_top #(
    parameter [1:0]   FASE_ADC   = 2'd1,  // instante de amostragem (teste de rampa: todas OK)
    // ---- estado ao ligar (depois muda por comando) ----
    parameter integer LOG2_MEDIA = 2,
    parameter integer POLARIDADE = 0,
    parameter integer CONFIRMA   = 3,
    parameter integer LIMIAR_LSB = 82,
    parameter integer N_PRE      = 49,
    parameter integer N_POS      = 150,
    parameter integer MODO       = 0,     // 0 = formas, 1 = picos, 2 = contínuo
    parameter integer SAIDA      = 0,     // 0 = UART, 1 = UDP
    parameter integer FILTRO     = 0,     // 1 = altura pelo filtro trapezoidal (modo picos)
    parameter integer TRAP_K     = 12,    // subida: 12 amostras (1,9 us a 160 ns)
    parameter integer TRAP_M     = 6,     // topo: 6 amostras (1 us)
    parameter integer TRAP_PZ    = 1248,  // tau = 50 us a 160 ns
    parameter integer TRAP_SH    = 12,    // ceil(log2(TRAP_K x (TRAP_PZ + 4) / 4))
    parameter [20:0]  PHY_RESET_CYCLES = 21'd1_250_000   // 10 ms a 125 MHz
)(
    input  wire        clk_25mhz,
    input  wire [13:0] adc_bits,
    output wire        A_clk_out,

    output wire        pino_uart_tx_fisico,
    input  wire        pino_uart_rx_fisico,

    output reg         pino_A,
    output reg         pino_B,
    output reg         pino_C,
    output reg         pino_D,
    output reg         pino_E,

    output wire        A_out_range,
    output wire        led,

    // ---- RGMII: o mesmo tráfego sai nos dois PHYs, como no oscilloscopeMode ----
    output wire        eth_rst_n,
    output wire        eth_txc,
    output wire        eth_tx_ctl,
    output wire [3:0]  eth_txd,
    output wire        eth1_txc,
    output wire        eth1_tx_ctl,
    output wire [3:0]  eth1_txd,
    output wire        eth_mdc,
    inout  wire        eth_mdio
);

    localparam [7:0] VERSAO_FW = 8'd3;

    // =========================================================================
    // 0. REGISTRADORES DE CONFIGURAÇÃO
    // =========================================================================
    reg [13:0] r_lim   = LIMIAR_LSB;
    reg [3:0]  r_conf  = CONFIRMA;
    reg [2:0]  r_l2    = LOG2_MEDIA;
    reg        r_pol   = (POLARIDADE != 0);
    reg [1:0]  r_modo  = MODO;
    wire       modo_cont = (r_modo == 2'd2);
    reg [9:0]  r_npre  = N_PRE;
    reg [9:0]  r_npos  = N_POS;
    reg        r_saida = (SAIDA != 0);
    reg        r_ativo = 1'b1;
    reg        r_filtro = (FILTRO != 0);
    reg [7:0]  r_tk    = TRAP_K;
    reg [7:0]  r_tm    = TRAP_M;
    reg [15:0] r_tpz   = TRAP_PZ;
    reg [4:0]  r_tsh   = TRAP_SH;

    // =========================================================================
    // 1. PLL: 25 MHz -> 50 MHz (clk_sys) e 125 MHz (rede)
    // =========================================================================
    wire clk_sys, clk_125, pll_locked;

    mca_pll u_pll (.clkin(clk_25mhz), .clk50(clk_sys), .clk125(clk_125), .locked(pll_locked));

    // =========================================================================
    // 2. CLOCK DO ADC (25 MHz) - parte junto com o divisor (fase determinística)
    // =========================================================================
    reg adc_clk_toggle = 1'b0;
    always @(posedge clk_sys) begin
        if (!pll_locked) adc_clk_toggle <= 1'b0;
        else             adc_clk_toggle <= ~adc_clk_toggle;
    end

    ODDR #(
        .DDR_CLK_EDGE("SAME_EDGE"), .INIT(1'b0), .SRTYPE("SYNC")
    ) oddr_adc_clk (
        .Q(A_clk_out), .C(clk_sys), .CE(1'b1),
        .D1(adc_clk_toggle), .D2(adc_clk_toggle), .R(1'b0), .S(1'b0)
    );

    // =========================================================================
    // 3. CAPTURA (mesma estrutura validada no teste de rampa, fase fixa)
    // =========================================================================
    wire [13:0] q_sub, q_desc;

    genvar i;
    generate
        for (i = 0; i < 14; i = i + 1) begin : captura_ddr
            IDDR #(
                .DDR_CLK_EDGE("SAME_EDGE"),
                .INIT_Q1(1'b0), .INIT_Q2(1'b0), .SRTYPE("SYNC")
            ) iddr_inst (
                .Q1(q_sub[i]), .Q2(q_desc[i]),
                .C(clk_sys), .CE(1'b1), .D(adc_bits[i]), .R(1'b0), .S(1'b0)
            );
        end
    endgenerate

    reg [13:0] q_sub_d  = 14'd0;
    reg [13:0] q_desc_d = 14'd0;
    always @(posedge clk_sys) begin
        q_sub_d  <= q_sub;
        q_desc_d <= q_desc;
    end

    reg [13:0] amostra_sel;
    always @(*) begin
        case (FASE_ADC)
            2'd0:    amostra_sel = q_sub_d;
            2'd1:    amostra_sel = q_desc_d;
            2'd2:    amostra_sel = q_sub;
            default: amostra_sel = q_desc;
        endcase
    end

    // =========================================================================
    // 4. DECIMAÇÃO COM MÉDIA DE N = 2^l2 AMOSTRAS DO ADC (l2 muda por comando)
    //    Igual ao firmware fixo: soma nos ciclos ímpares do divisor de período
    //    2N. O novo l2 só entra no fim de um período, para a paridade do divisor
    //    (a fase de amostragem validada) nunca mudar.
    // =========================================================================
    reg [2:0]  l2_at     = LOG2_MEDIA;      // l2 em uso no período atual
    reg [2:0]  l2_soma   = LOG2_MEDIA;      // l2 com que 'soma' foi acumulada
    reg [5:0]  dec_div   = 6'd0;
    reg [17:0] acc       = 18'd0;
    reg [17:0] soma      = 18'd0;
    reg        tick_soma = 1'b0;

    wire [5:0] ultimo = (6'd2 << l2_at) - 6'd1;

    always @(posedge clk_sys) begin
        tick_soma <= 1'b0;
        if (!pll_locked) begin
            dec_div <= 6'd0;
            acc     <= 18'd0;
        end else begin
            dec_div <= (dec_div == ultimo) ? 6'd0 : dec_div + 1'b1;
            if (dec_div[0]) begin
                if (dec_div == ultimo) begin
                    soma      <= acc + {4'b0000, amostra_sel};
                    l2_soma   <= l2_at;
                    acc       <= 18'd0;
                    tick_soma <= 1'b1;
                    l2_at     <= r_l2;
                end else begin
                    acc <= acc + {4'b0000, amostra_sel};
                end
            end
        end
    end

    // média com arredondamento: (soma + N/2) >> l2
    wire [17:0] meio       = (18'd1 << l2_soma) >> 1;
    wire [17:0] soma_arred = soma + meio;
    wire [17:0] media      = soma_arred >> l2_soma;

    reg [13:0] canal_a_dec = 14'd8192;
    reg        tick_5msps  = 1'b0;          // nome mantido; a taxa real é 25 MHz / N
    always @(posedge clk_sys) begin
        tick_5msps <= tick_soma;
        if (tick_soma)
            canal_a_dec <= media[13:0];
    end

    // =========================================================================
    // 5. LINHA DE BASE E TRIGGER (como no firmware fixo, com limiar e polaridade
    //    vindos dos registradores)
    // =========================================================================
    reg [19:0] base_fp   = 20'd0;     // base * 64 (média exponencial de 64 amostras)
    reg        base_ok   = 1'b0;
    reg [11:0] fora_cnt  = 12'd0;
    reg        base_zera = 1'b0;      // pulso: recomeça a linha de base (após comando)

    // cópias atrasadas da base para o modo pico: snap1 tem entre 32 e 63 amostras
    // de idade, então não inclui a subida do pulso que disparou
    reg [19:0] snap0 = 20'd0, snap1 = 20'd0;
    reg [4:0]  snap_cnt = 5'd0;

    wire signed [15:0] x_s        = {2'b00, canal_a_dec};
    wire signed [15:0] base_s     = {2'b00, base_fp[19:6]};
    wire signed [15:0] desvio_bru = x_s - base_s;
    wire signed [15:0] desvio     = r_pol ? -desvio_bru : desvio_bru;
    wire signed [15:0] LIM        = {2'b00, r_lim};

    wire em_banda = (desvio < LIM) && (desvio > -LIM);

    reg  [3:0] acima_cnt = 4'd0;              // amostras seguidas acima, ANTES da atual
    wire       acima     = (desvio >= LIM);
    wire       cruzou    = acima && (acima_cnt == r_conf - 4'd1);

    always @(posedge clk_sys) begin
        if (!pll_locked)
            acima_cnt <= 4'd0;
        else if (tick_5msps)
            acima_cnt <= acima ? ((acima_cnt == 4'd15) ? 4'd15 : acima_cnt + 1'b1) : 4'd0;
    end

    always @(posedge clk_sys) begin
        if (!pll_locked || base_zera) begin
            base_ok  <= 1'b0;
            fora_cnt <= 12'd0;
        end else if (tick_5msps) begin
            snap_cnt <= snap_cnt + 1'b1;
            if (!base_ok) begin
                base_fp  <= {canal_a_dec, 6'd0};
                snap0    <= {canal_a_dec, 6'd0};
                snap1    <= {canal_a_dec, 6'd0};
                base_ok  <= 1'b1;
                fora_cnt <= 12'd0;
            end else begin
                if (snap_cnt == 5'd31) begin
                    snap1 <= snap0;
                    snap0 <= base_fp;
                end
                if (em_banda) begin
                    base_fp  <= base_fp - (base_fp >> 6) + {6'd0, canal_a_dec};
                    fora_cnt <= 12'd0;
                end else if (fora_cnt == 12'hFFF) begin
                    base_fp  <= {canal_a_dec, 6'd0};
                    fora_cnt <= 12'd0;
                end else begin
                    fora_cnt <= fora_cnt + 1'b1;
                end
            end
        end
    end

    // =========================================================================
    // 6. LEDS / SATURAÇÃO / PISCA
    // =========================================================================
    always @(posedge clk_sys) begin
        if (pll_locked) begin
            pino_A <= (canal_a_dec >= 14'd7373);
            pino_B <= (canal_a_dec >= 14'd7782);
            pino_C <= (canal_a_dec >= 14'd8192);
            pino_D <= (canal_a_dec >= 14'd8602);
            pino_E <= (canal_a_dec >= 14'd9011);
        end else begin
            {pino_A, pino_B, pino_C, pino_D, pino_E} <= 5'b00000;
        end
    end

    assign A_out_range = (canal_a_dec == 14'd16383) | (canal_a_dec == 14'd0);

    // LED como no oscilloscopeMode: lento = ok, médio = saturou há pouco, rápido = overflow do fluxo
    reg [25:0] r_count = 26'd0;
    reg [23:0] sat_cnt = 24'd0;                 // ~0,3 s depois da última amostra saturada
    wire       fluxo_ovf;
    always @(posedge clk_sys) begin
        r_count <= r_count + 1'b1;
        if (A_out_range)          sat_cnt <= 24'hFFFFFF;
        else if (sat_cnt != 24'd0) sat_cnt <= sat_cnt - 1'b1;
    end
    assign led = fluxo_ovf ? r_count[22] : ((sat_cnt != 24'd0) ? r_count[23] : r_count[25]);

    // =========================================================================
    // 7. UART: transmissor (dados) e receptor (comandos)
    // =========================================================================
    wire       uart_tx_busy;
    reg        uart_tx_start = 1'b0;
    reg  [7:0] uart_tx_data  = 8'd0;

    uart_tx uart_inst (
        .clk(clk_sys), .tx_start(uart_tx_start), .tx_data(uart_tx_data),
        .tx_pin(pino_uart_tx_fisico), .tx_busy(uart_tx_busy)
    );

    wire [7:0] rx_dado;
    wire       rx_valido;
    uart_rx uart_rx_inst (.clk(clk_sys), .rx_pin(pino_uart_rx_fisico), .dado(rx_dado), .valido(rx_valido));

    // interpretador: 0xA5 0x5A REG VH VL CHK
    reg [2:0]  cmd_est  = 3'd0;
    reg [7:0]  cmd_reg  = 8'd0, cmd_vh = 8'd0, cmd_vl = 8'd0;
    reg        cmd_novo = 1'b0;                 // pulso: cmd_reg / cmd_val válidos
    wire [15:0] cmd_val = {cmd_vh, cmd_vl};

    always @(posedge clk_sys) begin
        cmd_novo <= 1'b0;
        if (rx_valido) begin
            case (cmd_est)
                3'd0: cmd_est <= (rx_dado == 8'hA5) ? 3'd1 : 3'd0;
                3'd1: cmd_est <= (rx_dado == 8'h5A) ? 3'd2 : (rx_dado == 8'hA5) ? 3'd1 : 3'd0;
                3'd2: begin cmd_reg <= rx_dado; cmd_est <= 3'd3; end
                3'd3: begin cmd_vh  <= rx_dado; cmd_est <= 3'd4; end
                3'd4: begin cmd_vl  <= rx_dado; cmd_est <= 3'd5; end
                default: begin
                    if (rx_dado == (cmd_reg ^ cmd_vh ^ cmd_vl ^ 8'hFF)) cmd_novo <= 1'b1;
                    cmd_est <= 3'd0;
                end
            endcase
        end
    end

    // validação (combinacional sobre o comando recebido)
    wire [10:0] soma_pre = {1'b0, cmd_val[9:0]} + {1'b0, r_npos};
    wire [10:0] soma_pos = {1'b0, r_npre} + {1'b0, cmd_val[9:0]};
    reg         cmd_ok;
    always @(*) begin
        case (cmd_reg)
            8'd0:  cmd_ok = (cmd_val >= 16'd4) && (cmd_val <= 16'd8000);
            8'd1:  cmd_ok = (cmd_val >= 16'd1) && (cmd_val <= 16'd15);
            8'd2:  cmd_ok = (cmd_val <= 16'd4);
            8'd3, 8'd7, 8'd8: cmd_ok = (cmd_val <= 16'd1);
            8'd4:  cmd_ok = (cmd_val <= 16'd2);
            8'd5:  cmd_ok = (cmd_val >= 16'd8) && (cmd_val <= 16'd600) && (soma_pre <= 11'd699);
            8'd6:  cmd_ok = (cmd_val >= 16'd8) && (cmd_val <= 16'd690) && (soma_pos <= 11'd699);
            8'd9, 8'd10: cmd_ok = 1'b1;
            8'd11: cmd_ok = (cmd_val <= 16'd1);
            8'd12: cmd_ok = (cmd_val >= 16'd2) && (cmd_val <= 16'd255);
            8'd13: cmd_ok = (cmd_val >= 16'd1) && (cmd_val <= 16'd255);
            8'd14: cmd_ok = (cmd_val >= 16'd4);
            8'd15: cmd_ok = (cmd_val <= 16'd31);
            default: cmd_ok = 1'b0;
        endcase
    end

    // =========================================================================
    // 8. TEMPO: timestamp e tempo vivo (ticks de amostra = 2^l2 x 40 ns)
    // =========================================================================
    reg [10:0] warmup_cnt = 11'd0;
    reg [31:0] ts_cnt     = 32'd0;
    reg [31:0] viva_cnt   = 32'd0;
    reg        zera_tempo = 1'b0;
    wire [10:0] warmup_alvo = {1'b0, r_npre} + 11'd11;    // pré-trigger todo novo, com folga
    wire        tz_bl_ok;                          // linha de base do trapézio já medida (seção 9)
    wire        armado = base_ok && r_ativo && !modo_cont && (!r_filtro || tz_bl_ok) && (warmup_cnt >= warmup_alvo);

    // =========================================================================
    // 9. CAPTURA, MEDIDA DO PICO E ENVIO
    // =========================================================================
    // duas cópias do buffer circular (1024 posições): uma lida pela UART (clk_sys),
    // outra pela rede (clk_125)
    (* ram_style = "block" *) reg [13:0] ram_u [0:1023];
    (* ram_style = "block" *) reg [13:0] ram_e [0:1023];

    reg [9:0]  write_addr = 10'd0;
    reg [9:0]  post_count = 10'd0;
    reg [9:0]  rd_inicio  = 10'd0;
    reg [31:0] ts_trig    = 32'd0;
    reg [31:0] viva_trig  = 32'd0;

    wire [10:0] nam = {1'b0, r_npre} + {1'b0, r_npos} + 11'd1;     // amostras por evento

    // ---- medida do pico (modo 1) ----
    reg [13:0] x1 = 14'd0, x2 = 14'd0;                 // duas amostras anteriores
    wire [15:0] s121 = {2'b00, canal_a_dec} + {1'b0, x1, 1'b0} + {2'b00, x2};   // 4 x média 1-2-1

    reg  [19:0] base_cap = 20'd0;                       // base congelada no trigger (x64)
    reg         capturando = 1'b0;
    wire [19:0] base_uso = capturando ? base_cap : snap1;

    wire signed [17:0] s121_s  = {2'b00, s121};
    wire signed [17:0] base4_s = {2'b00, base_uso[19:4]};
    wire signed [17:0] d4      = r_pol ? (base4_s - s121_s) : (s121_s - base4_s);
    wire signed [15:0] base1_s = {2'b00, base_uso[19:6]};
    wire signed [15:0] d1      = r_pol ? (base1_s - x_s) : (x_s - base1_s);
    wire signed [15:0] LIM_MEIO = {3'b000, r_lim[13:1]};
    wire               satura   = (canal_a_dec == 14'd0) || (canal_a_dec == 14'd16383);

    reg signed [17:0] pk_max  = 18'sd0;
    reg        [9:0]  pk_t    = 10'd0;
    reg signed [27:0] pk_area = 28'sd0;
    reg signed [15:0] pk_vale = 16'sd0;                  // menor valor desde o último máximo
    reg               pk_sat  = 1'b0, pk_pile = 1'b0, pk_alto = 1'b0;
    wire signed [15:0] sobe   = d1 - pk_vale;

    wire [15:0] pico4 = pk_max[17] ? 16'd0 : pk_max[15:0];

    // ---- filtro trapezoidal de Jordanov-Knoll (FILTRO = 1) ----
    // Roda sempre, sobre as amostras decimadas. A altura do pulso é o máximo de s na janela
    // de captura menos a linha de base de s, que é uma média longa (1024 amostras) atualizada
    // só quando a entrada está quieta há mais tempo que a duração do trapézio (2k + m).
    wire [8:0]         tz_l = {1'b0, r_tk} + {1'b0, r_tm};
    wire signed [47:0] tz_s;
    wire               tz_valido, tz_pronto;
    wire               tz_rst = !pll_locked || base_zera;      // qualquer comando recomeça o filtro

    jk_trapezio u_jk (
        .clk(clk_sys), .rst(tz_rst), .tick(tick_5msps), .v(canal_a_dec),
        .k(r_tk), .l(tz_l), .pz4(r_tpz), .s(tz_s), .valido(tz_valido), .pronto(tz_pronto)
    );

    reg  [9:0]         tz_quieto = 10'd0;                       // amostras seguidas dentro da banda
    wire [10:0]        tz_alvo   = {2'b00, r_tk, 1'b0} + {3'b000, r_tm} + 11'd8;   // 2k + m + 8
    reg  signed [47:0] tz_bl     = 48'sd0;
    reg                tz_bl_ok_r = 1'b0;
    assign tz_bl_ok = tz_bl_ok_r;
    wire signed [47:0] tz_dif0   = tz_s - tz_bl;
    wire signed [47:0] tz_passo  = tz_dif0 >>> 10;
    wire signed [47:0] tz_dif    = r_pol ? -tz_dif0 : tz_dif0;  // pulso sempre positivo

    always @(posedge clk_sys) begin
        if (tz_rst) begin
            tz_quieto  <= 10'd0;
            tz_bl_ok_r <= 1'b0;
        end else begin
            if (tick_5msps) begin
                if (base_ok && em_banda) begin
                    if (tz_quieto != 10'd1023) tz_quieto <= tz_quieto + 1'b1;
                end else begin
                    tz_quieto <= 10'd0;
                end
            end
            if (tz_valido && tz_pronto && ({1'b0, tz_quieto} >= tz_alvo)) begin
                if (!tz_bl_ok_r) begin
                    tz_bl      <= tz_s;
                    tz_bl_ok_r <= 1'b1;
                end else begin
                    tz_bl <= tz_bl + tz_passo;
                end
            end
        end
    end

    reg  signed [47:0] tz_max = 48'sd0;                         // maior (s - base) da janela
    reg  [9:0]         tz_t   = 10'd0;
    wire signed [47:0] tz_esc = tz_max >>> r_tsh;
    wire [15:0]        tz_pico = tz_max[47] ? 16'd0 : ((|tz_esc[46:16]) ? 16'hFFFF : tz_esc[15:0]);

    wire [15:0] pico_env  = r_filtro ? tz_pico : pico4;
    wire [9:0]  tpico_env = r_filtro ? tz_t : pk_t;
    wire [4:0]  flags = {r_filtro, (tpico_env == r_npos), pk_alto, pk_pile, pk_sat};

    // ---- pacote em montagem ----
    reg  [1:0]  pk_tipo  = 2'd2;        // 0 forma, 1 pico, 2 status
    reg         via_udp  = 1'b0;
    reg         st_uart  = 1'b1;        // status pendente pela UART (um ao ligar)
    reg         st_udp   = (SAIDA != 0) || (MODO == 2);
    reg  [1:0]  st_ack   = 2'd2;
    reg  [6:0]  st_reg   = 7'd0;
    reg         cmd_pend = 1'b0;

    wire [7:0]  byte_cfg = {1'b0, 3'd2, r_pol, r_l2};
    wire [69:0] tempos   = {3'b000, ts_trig, 3'b000, viva_trig};
    wire [79:0] tempos_b = {1'b0, tempos[69:63], 1'b0, tempos[62:56], 1'b0, tempos[55:49], 1'b0, tempos[48:42],
                            1'b0, tempos[41:35], 1'b0, tempos[34:28], 1'b0, tempos[27:21], 1'b0, tempos[20:14],
                            1'b0, tempos[13:7],  1'b0, tempos[6:0]};

    // cabeçalhos alinhados à esquerda em 26 bytes (o byte 0 é o mais significativo)
    wire [207:0] cab_forma = {16'hFFFF, byte_cfg, 8'd0,
                              4'd0, nam[10:7], 1'b0, nam[6:0],
                              5'd0, r_npre[9:7], 1'b0, r_npre[6:0],
                              tempos_b, 64'd0};
    wire [207:0] cab_pico  = {16'hFFFF, byte_cfg, 8'd1, tempos_b,
                              6'd0, pico_env[15:14], 1'b0, pico_env[13:7], 1'b0, pico_env[6:0],
                              1'b0, base_cap[19:13], 1'b0, base_cap[12:6],
                              1'b0, pk_area[27:21], 1'b0, pk_area[20:14], 1'b0, pk_area[13:7], 1'b0, pk_area[6:0],
                              5'd0, tpico_env[9:7], 1'b0, tpico_env[6:0],
                              3'd0, flags};
    wire [207:0] cab_stat  = {16'hFFFF, byte_cfg, 8'd2, VERSAO_FW,
                              1'b0, r_lim[13:7], 1'b0, r_lim[6:0],
                              4'd0, r_conf, 6'd0, r_modo, 7'd0, r_saida, 7'd0, r_ativo,
                              5'd0, r_npre[9:7], 1'b0, r_npre[6:0],
                              5'd0, r_npos[9:7], 1'b0, r_npos[6:0],
                              6'd0, st_ack, 1'b0, st_reg,
                              7'd0, r_filtro,
                              7'd0, r_tk[7], 1'b0, r_tk[6:0],
                              7'd0, r_tm[7], 1'b0, r_tm[6:0],
                              6'd0, r_tpz[15:14], 1'b0, r_tpz[13:7], 1'b0, r_tpz[6:0],
                              3'd0, r_tsh};

    wire [207:0] cab_bits = (pk_tipo == 2'd0) ? cab_forma : (pk_tipo == 2'd1) ? cab_pico : cab_stat;
    wire [4:0]   cab_len  = (pk_tipo == 2'd0) ? 5'd18 : 5'd26;
    wire [10:0]  pk_len   = (pk_tipo == 2'd0) ? ({6'd0, cab_len} + {nam[9:0], 1'b0}) : {6'd0, cab_len};

    // ---- gerador de bytes para a UART (clk_sys) ----
    reg  [10:0] u_idx = 11'd0;
    wire [9:0]  u_addr;
    reg  [13:0] u_q = 14'd0;
    wire [7:0]  u_byte;
    pkt_byte gera_u (.clk(clk_sys), .idx(u_idx), .cab(cab_bits), .cab_len(cab_len), .rd_inicio(rd_inicio),
                     .ram_addr(u_addr), .ram_q(u_q), .saida(u_byte));

    // ---- máquina principal ----
    localparam [3:0] IDLE     = 4'd0,
                     CAPT     = 4'd1,
                     INICIA   = 4'd2,
                     U_PEDE   = 4'd3,     // UART: espera o gerador entregar o byte u_idx
                     U_ENVIA  = 4'd4,
                     U_ESPERA = 4'd5,
                     E_ENVIA  = 4'd6,     // rede: espera o quadro terminar
                     E_SOLTA  = 4'd7,
                     FIM      = 4'd8;

    reg [3:0] estado = IDLE;

    always @(posedge clk_sys) begin
        if ((estado == IDLE || estado == CAPT) && tick_5msps) begin
            ram_u[write_addr] <= canal_a_dec;
            ram_e[write_addr] <= canal_a_dec;
        end
        u_q <= ram_u[u_addr];
    end
    reg [1:0] u_lat  = 2'd0;
    reg       eth_req = 1'b0;

    wire      eth_ack;
    reg [1:0] ack_sync = 2'b00;
    always @(posedge clk_sys) ack_sync <= {ack_sync[0], eth_ack};
    wire      ack_s = ack_sync[1];

    always @(posedge clk_sys) begin
        if (!pll_locked || zera_tempo) begin
            ts_cnt   <= 32'd0;
            viva_cnt <= 32'd0;
        end else if (tick_5msps) begin
            ts_cnt <= ts_cnt + 1'b1;
            if (estado == IDLE && armado)
                viva_cnt <= viva_cnt + 1'b1;
        end
    end

    always @(posedge clk_sys) begin
        if (tick_5msps) begin
            x1 <= canal_a_dec;
            x2 <= x1;
        end
    end

    always @(posedge clk_sys) begin
        base_zera  <= 1'b0;
        zera_tempo <= 1'b0;
        if (cmd_novo) cmd_pend <= 1'b1;

        case (estado)
            IDLE: begin
                uart_tx_start <= 1'b0;
                capturando    <= 1'b0;
                if (cmd_pend && !cmd_novo) begin
                    // ---- aplica o comando (fora de qualquer captura) ----
                    cmd_pend <= 1'b0;
                    st_reg   <= cmd_reg[6:0];
                    st_ack   <= cmd_ok ? 2'd1 : 2'd0;
                    st_uart  <= 1'b1;
                    st_udp   <= ((cmd_ok && cmd_reg == 8'd7) ? cmd_val[0] : r_saida)
                              || (((cmd_ok && cmd_reg == 8'd4) ? cmd_val[1:0] : r_modo) == 2'd2);
                    if (cmd_ok) begin
                        case (cmd_reg)
                            8'd0: r_lim   <= cmd_val[13:0];
                            8'd1: r_conf  <= cmd_val[3:0];
                            8'd2: r_l2    <= cmd_val[2:0];
                            8'd3: r_pol   <= cmd_val[0];
                            8'd4: r_modo  <= cmd_val[1:0];
                            8'd5: r_npre  <= cmd_val[9:0];
                            8'd6: r_npos  <= cmd_val[9:0];
                            8'd7: r_saida <= cmd_val[0];
                            8'd8: r_ativo <= cmd_val[0];
                            8'd10: zera_tempo <= 1'b1;
                            8'd11: r_filtro <= cmd_val[0];
                            8'd12: r_tk     <= cmd_val[7:0];
                            8'd13: r_tm     <= cmd_val[7:0];
                            8'd14: r_tpz    <= cmd_val;
                            8'd15: r_tsh    <= cmd_val[4:0];
                            default: ;
                        endcase
                        if (cmd_reg != 8'd9) begin         // tudo recomeça limpo
                            base_zera  <= 1'b1;
                            warmup_cnt <= 11'd0;
                        end
                    end
                end else if ((st_uart || st_udp) && pll_locked) begin
                    // ---- pacote de status ----
                    pk_tipo <= 2'd2;
                    via_udp <= !st_uart;
                    if (st_uart) st_uart <= 1'b0; else st_udp <= 1'b0;
                    estado  <= INICIA;
                end else if (tick_5msps && pll_locked) begin
                    write_addr <= write_addr + 1'b1;
                    if (warmup_cnt < warmup_alvo) begin
                        warmup_cnt <= warmup_cnt + 1'b1;
                    end else if (base_ok && r_ativo && !modo_cont && (!r_filtro || tz_bl_ok) && cruzou) begin
                        ts_trig    <= ts_cnt;
                        viva_trig  <= viva_cnt;
                        post_count <= 10'd1;
                        // medida do pico começa na amostra do trigger
                        base_cap   <= snap1;
                        capturando <= 1'b1;
                        pk_max     <= d4;
                        pk_t       <= 10'd0;
                        pk_area    <= {{12{d1[15]}}, d1};
                        pk_sat     <= satura;
                        pk_pile    <= 1'b0;
                        pk_alto    <= 1'b1;
                        pk_vale    <= d1;
                        tz_max     <= {1'b1, 47'd0};       // menor valor possível
                        tz_t       <= 10'd0;
                        estado     <= CAPT;
                    end
                end
            end

            CAPT: begin
                if (tz_valido && (tz_dif > tz_max)) begin      // topo do trapézio
                    tz_max <= tz_dif;
                    tz_t   <= post_count;
                end
                if (tick_5msps) begin
                    write_addr <= write_addr + 1'b1;
                    if (d4 > pk_max) begin                  // novo máximo
                        pk_max  <= d4;
                        pk_t    <= post_count;
                        pk_vale <= d1;
                    end else if (d1 < pk_vale) begin        // descendo
                        pk_vale <= d1;
                    end else if (sobe >= LIM) begin         // voltou a subir um limiar: outro pulso
                        pk_pile <= 1'b1;
                    end
                    pk_area <= pk_area + {{12{d1[15]}}, d1};
                    pk_sat  <= pk_sat | satura;
                    pk_alto <= (d1 >= LIM_MEIO);
                    if (post_count == r_npos) begin
                        // última amostra do evento, escrita em write_addr; a primeira está nam-1 antes
                        rd_inicio <= write_addr - nam[9:0] + 10'd1;
                        pk_tipo   <= {1'b0, r_modo[0]};
                        via_udp   <= r_saida;
                        estado    <= INICIA;
                    end else begin
                        post_count <= post_count + 1'b1;
                    end
                end
            end

            INICIA: begin
                if (via_udp) begin
                    eth_req <= 1'b1;
                    estado  <= E_ENVIA;
                end else begin
                    u_idx  <= 11'd0;
                    u_lat  <= 2'd0;
                    estado <= U_PEDE;
                end
            end

            U_PEDE: begin                       // 3 ciclos de latência do gerador
                u_lat <= u_lat + 1'b1;
                if (u_lat == 2'd3) begin
                    uart_tx_data <= u_byte;
                    estado       <= U_ENVIA;
                end
            end

            U_ENVIA: begin
                if (!uart_tx_busy && !uart_tx_start) begin
                    uart_tx_start <= 1'b1;
                end else if (uart_tx_busy) begin
                    uart_tx_start <= 1'b0;
                    estado        <= U_ESPERA;
                end
            end

            U_ESPERA: begin
                uart_tx_start <= 1'b0;
                if (!uart_tx_busy) begin
                    if (u_idx == pk_len - 11'd1) begin
                        estado <= FIM;
                    end else begin
                        u_idx  <= u_idx + 1'b1;
                        u_lat  <= 2'd0;
                        estado <= U_PEDE;
                    end
                end
            end

            E_ENVIA: begin
                if (ack_s) begin
                    eth_req <= 1'b0;
                    estado  <= E_SOLTA;
                end
            end

            E_SOLTA: begin
                if (!ack_s) estado <= FIM;
            end

            FIM: begin
                warmup_cnt <= 11'd0;            // o buffer ficou parado: pré-trigger recomeça
                estado     <= IDLE;
            end

            default: estado <= IDLE;
        endcase
    end

    // =========================================================================
    // 10. FLUXO CONTÍNUO (MODO 2): cada amostra decimada cruza para o domínio de
    //     125 MHz e entra no adc_packetizer do oscilloscopeMode.
    // =========================================================================
    reg        fl_tgl  = 1'b0;
    reg [13:0] fl_dado = 14'd0;
    always @(posedge clk_sys) begin
        if (tick_5msps && modo_cont) begin
            fl_dado <= canal_a_dec;           // fica parado até a próxima amostra (>= 40 ns)
            fl_tgl  <= ~fl_tgl;
        end
    end

    // ---- reset e PHY, como no udp_scope_top ----
    reg [2:0] rst_sync = 3'b111;
    always @(posedge clk_125 or negedge pll_locked) begin
        if (!pll_locked) rst_sync <= 3'b111;
        else             rst_sync <= {rst_sync[1:0], 1'b0};
    end
    wire rst125 = rst_sync[2];

    reg [20:0] phy_cnt  = 21'd0;
    reg        phy_done = 1'b0;
    always @(posedge clk_125) begin
        if (rst125) begin
            phy_cnt  <= 21'd0;
            phy_done <= 1'b0;
        end else if (!phy_done) begin
            phy_cnt <= phy_cnt + 1'b1;
            if (phy_cnt == PHY_RESET_CYCLES) phy_done <= 1'b1;
        end
    end
    assign eth_rst_n = phy_done;
    assign eth_mdc   = 1'b0;
    assign eth_mdio  = 1'bz;
    wire rst_app = rst125 || !phy_done;

    reg [2:0] fl_tgl_s  = 3'b000;
    reg [2:0] fl_modo_s = 3'b000;
    always @(posedge clk_125) begin
        fl_tgl_s  <= {fl_tgl_s[1:0], fl_tgl};
        fl_modo_s <= {fl_modo_s[1:0], modo_cont};
    end
    wire fl_valido = fl_tgl_s[2] ^ fl_tgl_s[1];       // fl_dado já está estável há 2 ciclos
    wire fl_ligado = fl_modo_s[2];

    reg         m_start = 1'b0;       // pulso de start do MAC para um pacote do MCA (seção 11)
    reg         m_ativo = 1'b0;       // quadro do MCA em andamento
    wire        m_sel   = m_start || m_ativo;

    wire        fl_start, fl_tvalid, fl_tlast, fl_pronto, fl_pulso;
    wire [15:0] fl_len;
    wire [7:0]  fl_tdata;
    wire        mac_busy, mac_tready;
    wire        fl_tx_busy;

    adc_packetizer #(
        .SAMPLES_PER_PKT (`SAMPLES_PER_PKT),
        .FIFO_DEPTH      (2048),
        .ADC_BITS        (`ADC_BITS),
        .OFFSET_BIN      (1)
    ) u_pack (
        .clk         (clk_125),
        .rst         (rst_app || !fl_ligado),         // fora do modo contínuo a fila fica vazia
        .adc_data    ({2'b00, fl_dado}),
        .adc_valid   (fl_valido),
        .adc_ready   (fl_pronto),
        .overflow    (fluxo_ovf),
        .start       (fl_start),
        .payload_len (fl_len),
        .tx_busy     (fl_tx_busy),
        .tdata       (fl_tdata),
        .tvalid      (fl_tvalid),
        .tready      (mac_tready && !m_sel),
        .tlast       (fl_tlast),
        .pkt_pulse   (fl_pulso)
    );

    // =========================================================================
    // 11. PACOTES DO MCA NA REDE (clk_125). cab_bits, pk_len e rd_inicio ficam
    //     parados enquanto eth_req = 1, então são lidos direto neste domínio.
    //     O udp_packet_tx consome um byte por ciclo, sem pausa, e o primeiro byte
    //     de dados é lido 51 ciclos depois do start; o gerador pkt_byte leva
    //     3 ciclos, então o índice pedido é (ciclos desde o start) - 48.
    // =========================================================================
    reg [2:0] req_sync = 3'b000;
    always @(posedge clk_125) req_sync <= {req_sync[1:0], eth_req};
    wire      req_s = req_sync[1];

    reg         ack_r    = 1'b0;
    reg         m_quer_d = 1'b0;
    reg  [11:0] m_cnt    = 12'd0;     // ciclos desde o start
    wire        m_quer   = req_s && !ack_r;
    assign eth_ack    = ack_r;
    // o fluxo só começa um pacote se o MCA não pediu a vez
    assign fl_tx_busy = mac_busy || m_quer || m_sel;

    always @(posedge clk_125) begin
        m_start  <= 1'b0;
        m_quer_d <= m_quer;
        if (rst_app) begin
            ack_r   <= 1'b0;
            m_ativo <= 1'b0;
            m_cnt   <= 12'd0;
        end else begin
            if (!req_s) ack_r <= 1'b0;
            if (!m_ativo) begin
                m_cnt <= 12'd0;
                // pedido visto há pelo menos um ciclo (o fluxo já o enxergou) e MAC livre
                if (m_quer && m_quer_d && !mac_busy && !fl_start && !m_start) begin
                    m_start <= 1'b1;
                    m_ativo <= 1'b1;
                end
            end else begin
                m_cnt <= m_cnt + 1'b1;
                if (m_cnt > 12'd4 && !mac_busy) begin      // quadro e intervalo terminados
                    m_ativo <= 1'b0;
                    ack_r   <= 1'b1;
                end
            end
        end
    end

    wire [10:0] pl_idx = m_cnt[10:0] - 11'd48;
    wire [7:0]  pl_byte;
    wire [9:0]  e_addr;
    reg  [13:0] e_q = 14'd0;
    always @(posedge clk_125) e_q <= ram_e[e_addr];
    pkt_byte gera_e (.clk(clk_125), .idx(pl_idx), .cab(cab_bits), .cab_len(cab_len), .rd_inicio(rd_inicio),
                     .ram_addr(e_addr), .ram_q(e_q), .saida(pl_byte));

    // ---- um só MAC para o fluxo e para os pacotes do MCA ----
    wire [7:0] gmii_d;
    wire       gmii_en;

    udp_packet_tx #(
        .SRC_MAC     (`SRC_MAC),
        .DST_MAC     (`DST_MAC),
        .SRC_IP      (`SRC_IP),
        .DST_IP      (`DST_IP),
        .SRC_PORT    (`SRC_PORT_A),
        .DST_PORT    (`DST_PORT_A),
        .NIBBLE_MODE (0)
    ) u_udp (
        .clk         (clk_125),
        .rst         (rst_app),
        .start       (m_start || fl_start),
        .payload_len (m_sel ? {5'd0, pk_len} : fl_len),
        .busy        (mac_busy),
        .tdata       (m_sel ? pl_byte : fl_tdata),
        .tvalid      (m_sel ? 1'b1 : fl_tvalid),
        .tready      (mac_tready),
        .tlast       (m_sel ? 1'b0 : fl_tlast),
        .gmii_d      (gmii_d),
        .gmii_en     (gmii_en)
    );

    rgmii_tx #(.NIBBLE_MODE(0)) u_rgmii0 (
        .clk125(clk_125), .gmii_d(gmii_d), .gmii_en(gmii_en),
        .rgmii_txc(eth_txc), .rgmii_txd(eth_txd), .rgmii_tx_ctl(eth_tx_ctl)
    );
    rgmii_tx #(.NIBBLE_MODE(0)) u_rgmii1 (
        .clk125(clk_125), .gmii_d(gmii_d), .gmii_en(gmii_en),
        .rgmii_txc(eth1_txc), .rgmii_txd(eth1_txd), .rgmii_tx_ctl(eth1_tx_ctl)
    );
endmodule

`default_nettype wire
