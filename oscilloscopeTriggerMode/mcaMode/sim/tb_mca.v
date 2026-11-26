`timescale 1ns/1ps
// Testbench do mca_top: ADC simulado, comandos pela UART, captura da UART e do RGMII (PHY 0),
// e gabaritos: trig.txt (triggers) e fluxo.txt (amostras que entraram no fluxo contínuo).
module tb;
`ifdef POL_NEG
    localparam real POL_TB = -1.0;
`else
    localparam real POL_TB = 1.0;
`endif
    `include "tb_comum.vh"
    `include "tb_eth.vh"
    reg uart_rx = 1'b1;
    wire eth1_txc, eth1_tx_ctl, eth_mdc, eth_mdio; wire [3:0] eth1_txd;
    mca_top #(.PHY_RESET_CYCLES(21'd200)) dut (
        .clk_25mhz(clk25), .adc_bits(adc_bits), .A_clk_out(adc_clk),
        .pino_uart_tx_fisico(uart_tx), .pino_uart_rx_fisico(uart_rx),
        .eth_rst_n(eth_rst_n), .eth_txc(eth_txc), .eth_tx_ctl(eth_tx_ctl), .eth_txd(eth_txd),
        .eth1_txc(eth1_txc), .eth1_tx_ctl(eth1_tx_ctl), .eth1_txd(eth1_txd),
        .eth_mdc(eth_mdc), .eth_mdio(eth_mdio));
    // os dois PHYs têm de levar exatamente o mesmo tráfego
    always @(eth_txc or eth_txd or eth_tx_ctl or eth1_txc or eth1_txd or eth1_tx_ctl) #0.1
        if ({eth_txc, eth_txd, eth_tx_ctl} !== {eth1_txc, eth1_txd, eth1_tx_ctl}) $display("ERRO: PHY1 difere do PHY0 em %t", $time);
    // o gerador de bytes do MCA supõe que o MAC lê o primeiro byte 51 ciclos depois do start
    always @(posedge dut.clk_125)
        if (dut.m_ativo && dut.mac_tready && dut.m_cnt < 12'd51) $display("ERRO: MAC pediu dado antes do previsto (m_cnt=%0d) em %t", dut.m_cnt, $time);
        else if (dut.m_ativo && dut.m_cnt == 12'd51 && !dut.mac_tready) $display("ERRO: MAC não pediu dado no ciclo 51 em %t", $time);
    // ---- comandos pela UART (2 Mbaud) ----
    task manda_byte(input [7:0] b); integer n; begin
        uart_rx = 0; #500; for (n = 0; n < 8; n = n + 1) begin uart_rx = b[n]; #500; end uart_rx = 1; #500;
    end endtask
    task comando(input [7:0] r, input [15:0] v); begin
        manda_byte(8'hA5); manda_byte(8'h5A); manda_byte(r); manda_byte(v[15:8]); manda_byte(v[7:0]);
        manda_byte(r ^ v[15:8] ^ v[7:0] ^ 8'hFF);
        $display("comando reg %0d = %0d em %0t", r, v, $time);
    end endtask
    // ---- gabaritos ----
    integer ft, fx; reg [3:0] est_ant = 0; reg cont_ant = 0;
    initial begin ft = $fopen("trig.txt", "w"); fx = $fopen("fluxo.txt", "w"); end
    always @(posedge dut.clk_sys) begin
        est_ant <= dut.estado; cont_ant <= dut.modo_cont;
        if (dut.estado == 4'd1 && est_ant == 4'd0)
            $fwrite(ft, "%0.1f %0d %0d %0d %0d %0d %0d %0d\n", $realtime, dut.r_modo, dut.r_saida, dut.r_l2,
                    dut.r_pol, dut.r_npre, dut.r_npos, dut.r_lim);
        if (dut.modo_cont && !cont_ant) $fwrite(fx, "# %0.1f\n", $realtime);
        if (dut.tick_5msps && dut.modo_cont) $fwrite(fx, "%0d\n", dut.canal_a_dec);
    end
    initial begin
        `include "roteiro.vh"
    end
    initial begin
        #(`FIM_NS); $fclose(fu); $fclose(fe); $fclose(ft); $fclose(fx); $finish;
    end
endmodule
