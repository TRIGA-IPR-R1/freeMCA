    // ---- RGMII TX -> arquivo (amostra 2 ns depois de cada borda do TXC, como o atraso interno do PHY) ----
    wire eth_txc, eth_tx_ctl, eth_rst_n; wire [3:0] eth_txd; integer fe; reg [3:0] lo_; reg ctl_r_ = 0, ctl_f_ = 0;
    initial fe = $fopen("eth.hex", "w");
    always @(posedge eth_txc) begin #2; lo_ = eth_txd; ctl_r_ = eth_tx_ctl; end
    always @(negedge eth_txc) begin #2;
        if (ctl_r_ !== eth_tx_ctl) $display("ERRO: TX_CTL difere entre as bordas (TX_ER) em %t", $time);
        if (ctl_r_) begin
            if (!eth_rst_n) $display("ERRO: quadro com o PHY em reset em %t", $time);
            $fwrite(fe, "%02x\n", {eth_txd, lo_});
        end else if (ctl_f_) $fwrite(fe, "--\n");
        ctl_f_ = ctl_r_;
    end
