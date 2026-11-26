# SPDX-License-Identifier: GPL-3.0-or-later
#
# Simulação do modo MCA com iverilog. Usa, sem alterar, os módulos de ../../oscilloscopeMode/rtl.
#   make jk         só o filtro jk_trapezio, comparado bit a bit com o modelo em Python (~10 s)
#   make trapezio   modo picos com o filtro, pulsos de pré-amplificador (tau 20 us)   (~1 min)
#   make fluxo      fluxo contínuo (MODO 2): confere amostra por amostra         (~1 min)
#   make completo   formas, picos, janela, limiar, comandos inválidos, UART e UDP (~4 min)
#   make            todos

THIS_MK := $(abspath $(lastword $(MAKEFILE_LIST)))
SIM_DIR := $(abspath $(dir $(THIS_MK)))
TOOLS_ROOT ?= $(abspath $(SIM_DIR)/../../tools)
-include $(TOOLS_ROOT)/tools.mk

IVERILOG ?= iverilog
VVP      ?= vvp
RTL      = $(SIM_DIR)/../rtl
OSC_RTL ?= $(SIM_DIR)/../../oscilloscopeMode/rtl

FONTES = $(SIM_DIR)/tb_mca.v $(RTL)/mca_top.v $(RTL)/mca_pkt.v $(RTL)/mca_pll.v $(RTL)/jk_trapezio.v \
         $(OSC_RTL)/adc_packetizer.v $(OSC_RTL)/sync_fifo.v $(OSC_RTL)/udp_packet_tx.v \
         $(OSC_RTL)/crc32_eth.v $(OSC_RTL)/rgmii_tx.v $(SIM_DIR)/sim_prims.v

.PHONY: all jk trapezio fluxo completo clean

all: jk trapezio fluxo completo

# k m pz4 e espaçamento entre amostras (ciclos): inclui os extremos k=2/255, m=1/255, pz4=4/65535
JK_CASOS = "12 6 1248 2" "2 1 4 2" "255 255 65535 2" "40 13 500 8" "100 200 20000 3"
jk:
	cd $(SIM_DIR) && for c in $(JK_CASOS); do set -- $$c; \
	  $(IVERILOG) -g2005 -DK=8\'d$$1 -DM=9\'d$$2 -DPZ4=16\'d$$3 -DPASSO=$$4 -DNAM=9000 -o jk.vvp tb_jk.v $(RTL)/jk_trapezio.v && \
	  $(VVP) jk.vvp > /dev/null && python3 confere_jk.py $$1 $$2 $$3 || exit 1; done

trapezio:
	cd $(SIM_DIR) && python3 gera_estimulo_pre.py && cp roteiro_trapezio.vh roteiro.vh
	cd $(SIM_DIR) && $(IVERILOG) -g2005 -I$(RTL) -DPRE_EXP -DFIM_NS=9700000 -o mca.vvp $(FONTES)
	cd $(SIM_DIR) && $(VVP) mca.vvp
	cd $(SIM_DIR) && python3 confere_trap.py

fluxo:
	cd $(SIM_DIR) && python3 gera_estimulo.py 3 22 300 && cp roteiro_fluxo.vh roteiro.vh
	cd $(SIM_DIR) && $(IVERILOG) -g2005 -I$(RTL) -DFIM_NS=10500000 -o mca.vvp $(FONTES)
	cd $(SIM_DIR) && $(VVP) mca.vvp
	cd $(SIM_DIR) && python3 confere_fluxo.py

completo:
	cd $(SIM_DIR) && python3 gera_estimulo.py 7 60 700 && cp roteiro_completo.vh roteiro.vh
	cd $(SIM_DIR) && $(IVERILOG) -g2005 -I$(RTL) -DFIM_NS=41000000 -o mca.vvp $(FONTES)
	cd $(SIM_DIR) && $(VVP) mca.vvp
	cd $(SIM_DIR) && python3 confere_cfg.py

clean:
	cd $(SIM_DIR) && rm -f mca.vvp jk.vvp jk_v.txt jk_s.txt uart.hex eth.hex trig.txt fluxo.txt estimulo.vh estimulo.json roteiro.vh resultado_cfg.json
