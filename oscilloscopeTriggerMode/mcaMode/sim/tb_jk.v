`timescale 1ns/1ps
// Testbench só do jk_trapezio: entrada pseudoaleatória (mais degraus e um nível DC), comparada
// depois, amostra por amostra, com o modelo inteiro em Python (confere_jk.py).
module tb_jk;
    reg clk = 0; always #10 clk = ~clk;
    reg rst = 1, tick = 0; reg [13:0] v = 0;
    wire signed [47:0] s; wire valido, pronto;
    jk_trapezio dut (.clk(clk), .rst(rst), .tick(tick), .v(v), .k(`K), .l(`K + `M), .pz4(`PZ4),
                     .s(s), .valido(valido), .pronto(pronto));
    integer fv, fs, n;
    initial begin
        fv = $fopen("jk_v.txt", "w"); fs = $fopen("jk_s.txt", "w");
        repeat (5) @(posedge clk); rst <= 0;
        for (n = 0; n < `NAM; n = n + 1) begin
            @(posedge clk);
            v <= (n < 40) ? 14'd7000 : (n % 700 < 350) ? (7000 + ($random & 14'h3FF)) : ($random & 14'h3FFF);
            if (n == 5000) v <= 14'd16383;
            tick <= 1;
            @(posedge clk); tick <= 0;
            repeat (`PASSO - 2) @(posedge clk);
        end
        repeat (20) @(posedge clk);
        $fclose(fv); $fclose(fs); $finish;
    end
    always @(posedge clk) begin
        if (tick) $fwrite(fv, "%0d\n", v);
        if (valido) $fwrite(fs, "%0d %0d\n", s, pronto);
    end
endmodule
