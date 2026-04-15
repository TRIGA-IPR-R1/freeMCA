# -------------------------------------------------------------------------
# Clock da placa (25MHz no Pino K4)
# -------------------------------------------------------------------------
set_property PACKAGE_PIN K4 [get_ports clk_25mhz]
set_property IOSTANDARD LVCMOS33 [get_ports clk_25mhz]
create_clock -period 40.000 -name sys_clk_pin -waveform {0.000 20.000} [get_ports clk_25mhz]

# -------------------------------------------------------------------------
# Saída do Trem de Pulsos (Pino J15)
# -------------------------------------------------------------------------
set_property PACKAGE_PIN J15 [get_ports J15]
set_property IOSTANDARD LVCMOS33 [get_ports J15]

# Imprescindível para garantir a subida/descida abrupta do pulso de 4ns
set_property SLEW FAST [get_ports J15]
set_property DRIVE 16 [get_ports J15]

# -------------------------------------------------------------------------
# Pino de Reset
# -------------------------------------------------------------------------
set_property PACKAGE_PIN U1 [get_ports rst]
set_property IOSTANDARD LVCMOS33 [get_ports rst]

# -------------------------------------------------------------------------
# Pino do LED
# -------------------------------------------------------------------------
set_property LOC A18 [get_ports led]
set_property IOSTANDARD LVCMOS33 [get_ports {led}]
