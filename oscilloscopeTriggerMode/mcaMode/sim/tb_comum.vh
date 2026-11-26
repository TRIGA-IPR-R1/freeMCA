// Trechos comuns dos testbenches: relógio, ADC simulado, captura da UART e do RGMII.
    reg clk25 = 0; always #20 clk25 = ~clk25;
    `include "estimulo.vh"
    // ---- ADC: nova amostra 7 ns depois de cada subida do clock do ADC ----
    wire adc_clk; reg [13:0] adc_bits = 14'd7000; integer k_; real v_, x_; integer ruido = 1;
    always @(posedge adc_clk) begin
        v_ = BASE;
        for (k_ = 0; k_ < NP; k_ = k_ + 1) begin
            x_ = ($realtime - t0[k_]) / TAU;
`ifdef PRE_EXP
            // pré-amplificador: sobe com TR e decai com TAU (amplitude 'amp' da exponencial ideal)
            if (x_ > 0) v_ = v_ + POL_TB * amp[k_] * ($exp(-x_) - $exp(-x_ * TAU / TR));
`else
            if (x_ > 0) v_ = v_ + POL_TB * amp[k_] * x_ * $exp(1.0 - x_);
`endif
        end
        if (ruido) v_ = v_ + ($random % 3);
        if (v_ > 16383) v_ = 16383; if (v_ < 0) v_ = 0;
        #7 adc_bits = $rtoi(v_ + 0.5);
    end
    // ---- UART TX do FPGA -> arquivo (2 Mbaud = 500 ns/bit) ----
    wire uart_tx; integer fu, bi_; reg [7:0] ub_;
    initial fu = $fopen("uart.hex", "w");
    always @(negedge uart_tx) begin
        #750; for (bi_ = 0; bi_ < 8; bi_ = bi_ + 1) begin ub_[bi_] = uart_tx; #500; end
        if (uart_tx !== 1'b1) $display("ERRO: stop bit da UART em %t", $time);
        $fwrite(fu, "%02x\n", ub_);
    end
