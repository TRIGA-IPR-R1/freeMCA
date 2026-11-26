# SPDX-License-Identifier: GPL-3.0-or-later
#
# Síntese do modo MCA (openXC7: Yosys + nextpnr-xilinx + prjxray), Colorlight i9plus-v6.1.
#
#   make            gera mca_top.bit
#   make prog       carrega na SRAM da FPGA (openFPGALoader, cabo CH347)
#   make clean
#
# O topo usa módulos do oscilloscopeMode (rede e fluxo); eles entram na lista de fontes
# abaixo, direto de ../oscilloscopeMode/rtl, sem cópia.
#
# Caminhos das ferramentas: os valores padrão são os do instalador do openXC7. Se o seu
# Makefile antigo usa outros, passe na linha de comando (make CHIPDB=... PRJXRAY_DB=...)
# ou copie de lá os valores destas variáveis.

TOP      = mca_top
PART     = xc7a50tfgg484-1
FAMILY   = artix7
XDC      = mca_top.xdc

MCA_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
RTL      = $(MCA_DIR)/rtl
OSC_RTL ?= $(MCA_DIR)/../oscilloscopeMode/rtl

# ---- todas as fontes do projeto (a ordem não importa) ----
FONTES = $(RTL)/mca_top.v \
         $(RTL)/mca_pkt.v \
         $(RTL)/mca_pll.v \
         $(RTL)/jk_trapezio.v \
         $(OSC_RTL)/adc_packetizer.v \
         $(OSC_RTL)/sync_fifo.v \
         $(OSC_RTL)/udp_packet_tx.v \
         $(OSC_RTL)/crc32_eth.v \
         $(OSC_RTL)/rgmii_tx.v

# ---- ferramentas ----
YOSYS        ?= yosys
NEXTPNR      ?= nextpnr-xilinx
FASM2FRAMES  ?= fasm2frames
FRAMES2BIT   ?= xc7frames2bit
LOADER       ?= openFPGALoader
OPENXC7      ?= /snap/openxc7/current
CHIPDB       ?= $(MCA_DIR)/chipdb
PRJXRAY_DB   ?= $(OPENXC7)/opt/nextpnr-xilinx/external/prjxray-db
BBA          ?= $(OPENXC7)/opt/nextpnr-xilinx/python/bbaexport.py
BBASM        ?= bbasm
CABO         ?= ch347_jtag

.PHONY: all prog clean

all: $(TOP).bit

# -I$(RTL): o `include "config.vh"` do mca_top.v tem de achar o config.vh do mcaMode
$(TOP).json: $(FONTES)
	$(YOSYS) -p "read_verilog -I$(RTL) $(FONTES); synth_xilinx -flatten -abc9 -arch xc7 -top $(TOP); write_json $@"

$(CHIPDB)/$(PART).bin:
	mkdir -p $(CHIPDB)
	python3 $(BBA) --device $(PART) --bba $(CHIPDB)/$(PART).bba
	$(BBASM) -l --le $(CHIPDB)/$(PART).bba $@
	rm -f $(CHIPDB)/$(PART).bba

$(TOP).fasm: $(TOP).json $(XDC) $(CHIPDB)/$(PART).bin
	$(NEXTPNR) --chipdb $(CHIPDB)/$(PART).bin --xdc $(XDC) --json $< --fasm $@

$(TOP).frames: $(TOP).fasm
	$(FASM2FRAMES) --part $(PART) --db-root $(PRJXRAY_DB)/$(FAMILY) $< > $@

$(TOP).bit: $(TOP).frames
	$(FRAMES2BIT) --part_file $(PRJXRAY_DB)/$(FAMILY)/$(PART)/part.yaml --part_name $(PART) \
	    --frm_file $< --output_file $@

prog: $(TOP).bit
	$(LOADER) -c $(CABO) $<

clean:
	rm -f $(TOP).json $(TOP).fasm $(TOP).frames $(TOP).bit
