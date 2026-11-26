# =========================================================================
# mca_top.xdc - Restrições do modo MCA (mcaMode/rtl/mca_top.v)
# Colorlight i9plus-v6.1 (XC7A50T-FGG484) + módulo KeYi AD9245
#
# Mesmo arquivo do mca_ad9245.xdc, com três acréscimos:
#   - Ethernet RGMII nos dois PHYs B50612D (U5 e U9), só transmissão
#   - pinos de gerência dos PHYs (reset, MDC, MDIO), comuns aos dois
#   - pino RX da UART de comandos (T4, vizinho do TX em V5 no conector)
# Pinos de rede conferidos no pinout da placa (wuxx/Colorlight-FPGA-Projects)
# e na plataforma colorlight_i9plus do litex-boards.
# =========================================================================

# =========================================================================
# REGRAS DE TEMPORIZAÇÃO (TIMING CONSTRAINTS)
# =========================================================================
create_clock -period 40.000 -name clk_25mhz_pin -waveform {0.000 20.000} [get_ports clk_25mhz]

# =========================================================================
# Clock e LED
# =========================================================================
set_property PACKAGE_PIN K4 [get_ports clk_25mhz]
set_property IOSTANDARD LVCMOS33 [get_ports clk_25mhz]

set_property PACKAGE_PIN A18 [get_ports led]
set_property IOSTANDARD LVCMOS33 [get_ports led]

# =========================================================================
# Saída de Clock para o ADC (J15)
# =========================================================================
set_property PACKAGE_PIN U18 [get_ports A_clk_out]
set_property IOSTANDARD LVCMOS33 [get_ports A_clk_out]
set_property SLEW SLOW [get_ports A_clk_out]
# =========================================================================
# Pinos de Teste (Limiares Visuais)
# =========================================================================
set_property PACKAGE_PIN P5 [get_ports pino_A]
set_property IOSTANDARD LVCMOS33 [get_ports pino_A]
set_property SLEW FAST [get_ports pino_A]

set_property PACKAGE_PIN T6 [get_ports pino_B]
set_property IOSTANDARD LVCMOS33 [get_ports pino_B]
set_property SLEW FAST [get_ports pino_B]

set_property PACKAGE_PIN U7 [get_ports pino_C]
set_property IOSTANDARD LVCMOS33 [get_ports pino_C]
set_property SLEW FAST [get_ports pino_C]

set_property PACKAGE_PIN U6 [get_ports pino_D]
set_property IOSTANDARD LVCMOS33 [get_ports pino_D]
set_property SLEW FAST [get_ports pino_D]

set_property PACKAGE_PIN U5 [get_ports pino_E]
set_property IOSTANDARD LVCMOS33 [get_ports pino_E]
set_property SLEW FAST [get_ports pino_E]

# =========================================================================
# Mapeamento ADC 14-Bits
# =========================================================================
set_property PACKAGE_PIN R17 [get_ports {adc_bits[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[0]}]

set_property PACKAGE_PIN N18 [get_ports {adc_bits[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[1]}]

set_property PACKAGE_PIN Y21 [get_ports {adc_bits[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[2]}]

set_property PACKAGE_PIN N19 [get_ports {adc_bits[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[3]}]

set_property PACKAGE_PIN R19 [get_ports {adc_bits[4]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[4]}]

set_property PACKAGE_PIN M16 [get_ports {adc_bits[5]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[5]}]

set_property PACKAGE_PIN N15 [get_ports {adc_bits[6]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[6]}]

set_property PACKAGE_PIN L15 [get_ports {adc_bits[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[7]}]

set_property PACKAGE_PIN K14 [get_ports {adc_bits[8]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[8]}]

set_property PACKAGE_PIN L16 [get_ports {adc_bits[9]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[9]}]

set_property PACKAGE_PIN M15 [get_ports {adc_bits[10]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[10]}]

set_property PACKAGE_PIN AA8 [get_ports {adc_bits[11]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[11]}]

set_property PACKAGE_PIN N22 [get_ports {adc_bits[12]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[12]}]

set_property PACKAGE_PIN J14 [get_ports {adc_bits[13]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[13]}]

# =========================================================================
# Indicador de Saturação (Canal A)
# =========================================================================
set_property PACKAGE_PIN J15 [get_ports A_out_range]
set_property IOSTANDARD LVCMOS33 [get_ports A_out_range]

# =========================================================================
# Pino TX (Comunicação com o módulo USB-TTL)
# =========================================================================
set_property PACKAGE_PIN V5 [get_ports pino_uart_tx_fisico]
set_property IOSTANDARD LVCMOS33 [get_ports pino_uart_tx_fisico]
set_property SLEW FAST [get_ports pino_uart_tx_fisico]

# =========================================================================
# Pino RX (Comandos vindos do módulo USB-TTL)
# T4 = pino 51 do conector, ao lado do V5 (pino 52, TX). Ligar ao TX do
# adaptador USB-TTL. É o mesmo RX da serial padrão da placa no LiteX.
# =========================================================================
set_property PACKAGE_PIN T4 [get_ports pino_uart_rx_fisico]
set_property IOSTANDARD LVCMOS33 [get_ports pino_uart_rx_fisico]

# =========================================================================
# Ethernet RGMII - PHY 0 (U5, B50612D) - só transmissão, 125 MHz DDR
# =========================================================================
set_property PACKAGE_PIN A1 [get_ports eth_txc]
set_property IOSTANDARD LVCMOS33 [get_ports eth_txc]
set_property SLEW FAST [get_ports eth_txc]

set_property PACKAGE_PIN D1 [get_ports eth_tx_ctl]
set_property IOSTANDARD LVCMOS33 [get_ports eth_tx_ctl]
set_property SLEW FAST [get_ports eth_tx_ctl]

set_property PACKAGE_PIN B2 [get_ports {eth_txd[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {eth_txd[0]}]
set_property SLEW FAST [get_ports {eth_txd[0]}]

set_property PACKAGE_PIN B1 [get_ports {eth_txd[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {eth_txd[1]}]
set_property SLEW FAST [get_ports {eth_txd[1]}]

set_property PACKAGE_PIN C2 [get_ports {eth_txd[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {eth_txd[2]}]
set_property SLEW FAST [get_ports {eth_txd[2]}]

set_property PACKAGE_PIN D2 [get_ports {eth_txd[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {eth_txd[3]}]
set_property SLEW FAST [get_ports {eth_txd[3]}]

# =========================================================================
# Ethernet RGMII - PHY 1 (U9, B50612D) - mesmo tráfego do PHY 0
# =========================================================================
set_property PACKAGE_PIN M6 [get_ports eth1_txc]
set_property IOSTANDARD LVCMOS33 [get_ports eth1_txc]
set_property SLEW FAST [get_ports eth1_txc]

set_property PACKAGE_PIN N5 [get_ports eth1_tx_ctl]
set_property IOSTANDARD LVCMOS33 [get_ports eth1_tx_ctl]
set_property SLEW FAST [get_ports eth1_tx_ctl]

set_property PACKAGE_PIN M5 [get_ports {eth1_txd[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {eth1_txd[0]}]
set_property SLEW FAST [get_ports {eth1_txd[0]}]

set_property PACKAGE_PIN M2 [get_ports {eth1_txd[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {eth1_txd[1]}]
set_property SLEW FAST [get_ports {eth1_txd[1]}]

set_property PACKAGE_PIN N4 [get_ports {eth1_txd[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {eth1_txd[2]}]
set_property SLEW FAST [get_ports {eth1_txd[2]}]

set_property PACKAGE_PIN P4 [get_ports {eth1_txd[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {eth1_txd[3]}]
set_property SLEW FAST [get_ports {eth1_txd[3]}]

# =========================================================================
# Gerência dos PHYs (comum ao U5 e ao U9)
# eth_rst_n: o firmware segura os PHYs em reset por 10 ms após o PLL travar.
# MDC fica em 0 e MDIO em alta impedância: os PHYs usam a configuração de
# fábrica (autonegociação, RGMII com atraso interno no TX).
# =========================================================================
set_property PACKAGE_PIN H2 [get_ports eth_rst_n]
set_property IOSTANDARD LVCMOS33 [get_ports eth_rst_n]

set_property PACKAGE_PIN G1 [get_ports eth_mdc]
set_property IOSTANDARD LVCMOS33 [get_ports eth_mdc]

set_property PACKAGE_PIN G2 [get_ports eth_mdio]
set_property IOSTANDARD LVCMOS33 [get_ports eth_mdio]
