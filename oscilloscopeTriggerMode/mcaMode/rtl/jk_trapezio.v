// SPDX-License-Identifier: GPL-3.0-or-later
//
// jk_trapezio.v - filtro trapezoidal recursivo de Jordanov-Knoll (NIM A 345, 1994)
// -----------------------------------------------------------------------------
// Faz o papel do amplificador formatador: recebe o sinal do pré-amplificador
// (subida rápida, cauda exponencial de constante tau) e entrega um trapézio cuja
// altura é proporcional à carga do pulso, com subida de k amostras e topo plano
// de m = l - k amostras. A correção de polo-zero cancela a cauda, então pulsos
// sobre a cauda de outros voltam à mesma linha de base.
//
//   b(n) = v(n) - v(n-k)
//   d(n) = b(n) - b(n-l)                      l = k + m
//   p(n) = p(n-1) + d(n)
//   r(n) = 4 p(n) + PZ4 d(n)                  PZ4 = 4 M,  M = 1 / (exp(dt/tau) - 1)
//   s(n) = s(n-1) + r(n)
//
// Tudo em inteiros, sem arredondamento: s é exato e não deriva. Para um pulso de
// amplitude A (em LSB) o topo fica A x k x (PZ4 + 4) acima da linha de base de s.
// O ganho em DC é finito (4 k l), então um nível constante B na entrada aparece
// como a constante 4 k l B na saída: quem usa mede a altura em relação à linha de
// base do próprio s (ver mca_top.v).
//
// rst apaga a história: é como se a entrada tivesse sido zero até ali. As saídas
// só valem depois de k + l amostras (pronto = 1).
//
// Uma amostra por 'tick'; pode haver um tick a cada 2 ciclos de clk. A saída
// correspondente sai 6 ciclos depois, com 'valido' = 1 por um ciclo.
// Larguras: v 14 bits; k 2..255; l até 510; PZ4 até 65535; s 48 bits com sinal
// (o pior caso, |s| < 2^40, cabe com folga).

`default_nettype none

module jk_trapezio (
    input  wire               clk,
    input  wire               rst,
    input  wire               tick,
    input  wire [13:0]        v,
    input  wire [7:0]         k,
    input  wire [8:0]         l,
    input  wire [15:0]        pz4,
    output reg  signed [47:0] s,
    output reg                valido,
    output wire               pronto
);
    // linhas de atraso (leitura síncrona)
    (* ram_style = "block" *) reg [13:0]        ram1 [0:255];
    (* ram_style = "block" *) reg signed [15:0] ram2 [0:511];

    reg [7:0]  wp1 = 8'd0;
    reg [8:0]  wp2 = 9'd0;
    reg [9:0]  n_ini = 10'd0;          // amostras desde o rst (satura em 1023)

    reg [13:0]        q1 = 14'd0;
    reg signed [15:0] q2 = 16'sd0;

    reg               e1 = 1'b0, e2 = 1'b0, e3 = 1'b0, e4 = 1'b0, e5 = 1'b0;
    reg               sem1 = 1'b0;                  // v(n-k) ainda não existe
    reg               sem2_0 = 1'b0, sem2_1 = 1'b0, sem2_2 = 1'b0;   // b(n-l) ainda não existe
    reg [13:0]        v0 = 14'd0;
    reg signed [15:0] b  = 16'sd0, b1 = 16'sd0;
    reg signed [16:0] d  = 17'sd0;
    reg signed [23:0] p  = 24'sd0;
    reg signed [33:0] prod = 34'sd0;

    wire [7:0] ra1 = wp1 - k;
    wire [8:0] ra2 = wp2 - l;

    wire signed [15:0] v0_s  = {2'b00, v0};
    wire signed [15:0] tap1  = sem1   ? 16'sd0 : $signed({2'b00, q1});
    wire signed [15:0] tap2  = sem2_2 ? 16'sd0 : q2;
    wire signed [17:0] pz4_s = {2'b00, pz4};

    assign pronto = (n_ini > {1'b0, l} + {2'b00, k});

    initial begin s = 48'sd0; valido = 1'b0; end

    always @(posedge clk) begin
        if (tick) ram1[wp1] <= v;
        q1 <= ram1[ra1];
        if (e2) ram2[wp2] <= b;
        q2 <= ram2[ra2];
    end

    always @(posedge clk) begin
        valido <= 1'b0;
        if (rst) begin
            n_ini <= 10'd0;
            e1 <= 1'b0; e2 <= 1'b0; e3 <= 1'b0; e4 <= 1'b0; e5 <= 1'b0;
            p  <= 24'sd0;
            s  <= 48'sd0;
        end else begin
            // estágio 0: amostra entra na primeira linha de atraso
            e1 <= tick;
            if (tick) begin
                v0     <= v;
                wp1    <= wp1 + 1'b1;
                sem1   <= (n_ini < {2'b00, k});
                sem2_0 <= (n_ini < {1'b0, l});
                if (n_ini != 10'd1023) n_ini <= n_ini + 1'b1;
            end
            // estágio 1: b(n) = v(n) - v(n-k)
            e2 <= e1;
            if (e1) begin
                b      <= v0_s - tap1;
                sem2_1 <= sem2_0;
            end
            // estágio 2: b entra na segunda linha de atraso
            e3 <= e2;
            if (e2) begin
                wp2    <= wp2 + 1'b1;
                b1     <= b;
                sem2_2 <= sem2_1;
            end
            // estágio 3: d(n) = b(n) - b(n-l)
            e4 <= e3;
            if (e3) d <= b1 - tap2;
            // estágio 4: p(n) e o produto do polo-zero
            e5 <= e4;
            if (e4) begin
                p    <= p + d;
                prod <= pz4_s * d;
            end
            // estágio 5: s(n) = s(n-1) + 4 p(n) + PZ4 d(n)
            if (e5) begin
                s      <= s + {{22{p[23]}}, p, 2'b00} + {{14{prod[33]}}, prod};
                valido <= 1'b1;
            end
        end
    end
endmodule

`default_nettype wire
