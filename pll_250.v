module pll250 (
    input  wire        clk_25mhz,
    input  wire [13:0] adc_bits,    // Barramento DDR de 14 bits vindo do ADC
    output wire        A_clk_out,   // Clock de amostragem para o ADC
    output wire        B_clk_out,   // Clock espelho

    // Pinos de Validação Cumulativa (Thresholds monitorando o CANAL A/B)

    output reg         pino_A,      // >= -0.5V
    output reg         pino_B,      // >= -0.25V
    output reg         pino_C,      // >= 0V  (Meio da Escala)
    output reg         pino_D,      // >= +0.25V
    output reg         pino_E,      // >= +0.5V

    // Pinos de Saturação (Out of Range) mapeados no XDC
    output wire        A_out_range, 
    output wire        B_out_range, 

    output wire        led          // Heartbeat LED
);

    // =========================================================================
    // 1. GERAÇÃO DE CLOCK 
    // =========================================================================
    wire clk_12, pll_locked, clkfb, clk_unbuf;

    PLLE2_BASE #(
        .CLKFBOUT_MULT(52),       // 25 * 50 = 1250 MHz (VCO na zona segura)
        .CLKIN1_PERIOD(40.0),     // 25 MHz de entrada
        .CLKOUT0_DIVIDE(50),     // 1250 / 50 = 25 MHz
        .DIVCLK_DIVIDE(1)
    ) pll_inst (
        .CLKOUT0(clk_unbuf), .CLKFBOUT(clkfb), .LOCKED(pll_locked), 
        .CLKIN1(clk_25mhz), .PWRDWN(1'b0), .RST(1'b0), .CLKFBIN(clkfb)
    );
    BUFG bufg_inst (.I(clk_unbuf), .O(clk_12));

    // Fornece o clock base para o ADC operar
    assign A_clk_out = clk_12;
    assign B_clk_out = clk_12;


    // =========================================================================
    // 2. CAPTURA DDR (Demultiplexação do Canal A e B)
    // =========================================================================
    wire [13:0] canal_a_dados;
    wire [13:0] canal_b_dados;

    genvar i;
    generate
        for (i = 0; i < 14; i = i + 1) begin : demux_ddr
            IDDR #(
                // "SAME_EDGE" exigido para compatibilidade com a síntese do openXC7
                .DDR_CLK_EDGE("SAME_EDGE"), 
                .INIT_Q1(1'b0),
                .INIT_Q2(1'b0),
                .SRTYPE("SYNC")
            ) iddr_inst (
                .Q1(canal_b_dados[i]), // Borda de subida (Canal B)
                .Q2(canal_a_dados[i]), // Borda de descida (Canal A)
                .C(clk_12),            // Clock de referência
                .CE(1'b1),             // Clock Enable sempre ativo
                .D(adc_bits[i]),       // Pino físico que vem do ADC
                .R(1'b0),              // Reset
                .S(1'b0)               // Set
            );
        end
    endgenerate


// =========================================================================
// =========================================================================
    // LÓGICA DE GATILHOS (Micro-Escala: -0.5V a +0.5V)
    // =========================================================================
    always @(posedge clk_12) begin
        if (pll_locked) begin
            pino_A <= (canal_b_dados >= 14'd7373);  // >= -0.50V
            pino_B <= (canal_b_dados >= 14'd7782);  // >= -0.25V
            pino_C <= (canal_b_dados >= 14'd8192);  // >=  0.00V
            pino_D <= (canal_b_dados >= 14'd8602);  // >= +0.25V
            pino_E <= (canal_b_dados >= 14'd9011);  // >= +0.50V
        end else begin
            {pino_A, pino_B, pino_C, pino_D, pino_E} <= 5'b00000;
        end
    end
    

    // =========================================================================
    // 4. INDICADORES DE SATURAÇÃO (Out of Range)
    // =========================================================================
    // Sinaliza se algum dos canais encostar nas extremidades lógicas de +/- 5V
    assign A_out_range = (canal_a_dados == 14'd16383) | (canal_a_dados == 14'd0);
    assign B_out_range = (canal_b_dados == 14'd16383) | (canal_b_dados == 14'd0);


    // =========================================================================
    // 5. HEARTBEAT LED (Sistema Operante)
    // =========================================================================
    // Em 12MHz, o bit 26 resulta em ~5.5s ligado e ~5.5s desligado.
    reg [26:0] r_count = 0;
    always @(posedge clk_12) begin
        r_count <= r_count + 1;
    end
    assign led = r_count[26];

endmodule