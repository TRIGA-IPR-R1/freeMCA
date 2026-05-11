# -------------------------------------------------------------------------
# Clock e LED (Mantendo o que já funciona no seu hardware)
# -------------------------------------------------------------------------
set_property PACKAGE_PIN K4 [get_ports clk_25mhz]
set_property IOSTANDARD LVCMOS33 [get_ports clk_25mhz]

set_property PACKAGE_PIN A18 [get_ports led]
set_property IOSTANDARD LVCMOS33 [get_ports led]

# -------------------------------------------------------------------------
# Saída de Clock para o ADC (J15)
# -------------------------------------------------------------------------
set_property PACKAGE_PIN N22 [get_ports A_clk_out]
set_property IOSTANDARD LVCMOS33 [get_ports A_clk_out]
set_property PACKAGE_PIN Y21 [get_ports B_clk_out]
set_property IOSTANDARD LVCMOS33 [get_ports B_clk_out]
set_property SLEW FAST [get_ports A_clk_out]
set_property SLEW FAST [get_ports B_clk_out]
# -------------------------------------------------------------------------
#Pinos de Teste
# -------------------------------------------------------------------------

set_property PACKAGE_PIN P5 [get_ports pino_A]
set_property IOSTANDARD LVCMOS33 [get_ports pino_A]
set_property PACKAGE_PIN T6 [get_ports pino_B]
set_property IOSTANDARD LVCMOS33 [get_ports pino_B]
set_property PACKAGE_PIN U7 [get_ports pino_C]
set_property IOSTANDARD LVCMOS33 [get_ports pino_C]
set_property PACKAGE_PIN U6 [get_ports pino_D]
set_property IOSTANDARD LVCMOS33 [get_ports pino_D]
set_property PACKAGE_PIN U5 [get_ports pino_E]
set_property IOSTANDARD LVCMOS33 [get_ports pino_E]

# -------------------------------------------------------------------------
# Mapeamento ADC 14-Bits (Definição explícita para openXC7)
# -------------------------------------------------------------------------
set_property PACKAGE_PIN T18 [get_ports {adc_bits[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[0]}]

set_property PACKAGE_PIN U17 [get_ports {adc_bits[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[1]}]

set_property PACKAGE_PIN U18 [get_ports {adc_bits[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[2]}]

set_property PACKAGE_PIN R17 [get_ports {adc_bits[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[3]}]

set_property PACKAGE_PIN N18 [get_ports {adc_bits[4]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[4]}]

set_property PACKAGE_PIN R18 [get_ports {adc_bits[5]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[5]}]

set_property PACKAGE_PIN N19 [get_ports {adc_bits[6]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[6]}]

set_property PACKAGE_PIN R19 [get_ports {adc_bits[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[7]}]

set_property PACKAGE_PIN M16 [get_ports {adc_bits[8]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[8]}]

set_property PACKAGE_PIN N15 [get_ports {adc_bits[9]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[9]}]

set_property PACKAGE_PIN L15 [get_ports {adc_bits[10]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[10]}]

set_property PACKAGE_PIN K14 [get_ports {adc_bits[11]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[11]}]

set_property PACKAGE_PIN L16 [get_ports {adc_bits[12]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[12]}]

set_property PACKAGE_PIN M15 [get_ports {adc_bits[13]}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_bits[13]}]

# Adicione o IOSTANDARD também para o dummy_bot se estiver usando
set_property PACKAGE_PIN AA8 [get_ports A_out_range]
set_property IOSTANDARD LVCMOS33 [get_ports A_out_range]
set_property PACKAGE_PIN AB21 [get_ports B_out_range]
set_property IOSTANDARD LVCMOS33 [get_ports B_out_range]
