module pll250 (
    input  wire clk_25mhz, // 25MHz input (Pino K4)
input  wire rst,       // Reset para reiniciar o trem de pulsos
output reg  J15,         // Trem de pulsos de 4ns (Pino J15)
output wire led
);

wire clkfb;
wire clk_250mhz_unbuf;
wire clk_250mhz;
wire pll_locked;

// -------------------------------------------------------------------------
// 1. PLL: Multiplica 25MHz para 250MHz
// -------------------------------------------------------------------------
PLLE2_BASE #(
    .BANDWIDTH("OPTIMIZED"),
             .CLKFBOUT_MULT(40),       // 25 MHz * 40 = 1000 MHz VCO
             .CLKFBOUT_PHASE(0.0),
             .CLKIN1_PERIOD(40.0),     // 25 MHz = 40.0 ns de período
             .CLKOUT0_DIVIDE(4),       // 1000 MHz / 4 = 250 MHz na saída
             .CLKOUT0_DUTY_CYCLE(0.5),
             .CLKOUT0_PHASE(0.0),
             .DIVCLK_DIVIDE(1),
             .REF_JITTER1(0.01),
             .STARTUP_WAIT("FALSE")
) pll_inst (
    .CLKOUT0(clk_250mhz_unbuf),
            .CLKOUT1(), .CLKOUT2(), .CLKOUT3(), .CLKOUT4(), .CLKOUT5(),
            .CLKFBOUT(clkfb),
            .LOCKED(pll_locked),
            .CLKIN1(clk_25mhz),
            .PWRDWN(1'b0),
                    .RST(rst),
                    .CLKFBIN(clkfb)
            );

            BUFG bufg_inst (
                .I(clk_250mhz_unbuf),
                    .O(clk_250mhz)
            );

            // -------------------------------------------------------------------------
            // 2. Lógica do Trem de Pulsos Contínuo
            // -------------------------------------------------------------------------

            // Parâmetro para definir o intervalo entre os pulsos de 4ns.
            // O clock roda a 250MHz (4ns por ciclo).
            // Para um intervalo de 1 microssegundo (1000ns), precisamos contar 250 ciclos.
            // 250 ciclos = Conta de 0 até 249.
            localparam MAX_COUNT = 8'd249;

            reg [7:0] counter = 8'd0;

            always @(posedge clk_25mhz or posedge rst) begin
            if (rst) begin
                counter <= 8'd0;
            J15      <= 1'b0;
            end else if (pll_locked) begin
            // O PLL estabilizou, inicia a contagem
            if (counter == MAX_COUNT) begin
                counter <= 8'd0;
            J15      <= 1'b1; // Dispara o pulso alto (vai durar exatamente 4ns)
            end else begin
            counter <= counter + 8'd1;
            J15      <= 1'b0; // Mantém o sinal baixo durante a contagem
            end
            end
            end

            reg [28:0] r_count = 0;

            always @(posedge clk_25mhz) begin
            if (r_count > 53687090) begin
                r_count <= 29'd0;
            end else begin
            r_count <= r_count + 1;
            end
            end

            assign led = !r_count[29];


            endmodule
