# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright (C) 2026 Daniel Batista, Thalles Campagnani
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

THIS_MK := $(abspath $(lastword $(MAKEFILE_LIST)))
SIM_DIR := $(abspath $(dir $(THIS_MK)))
TOOLS_ROOT ?= $(abspath $(SIM_DIR)/../../tools)
include $(TOOLS_ROOT)/tools.mk

RTL = $(SIM_DIR)/../rtl

.PHONY: all clean

all:
	iverilog -g2005 -I$(RTL) -o $(SIM_DIR)/udp_packet_tx_tb.vvp \
		$(RTL)/crc32_eth.v $(RTL)/udp_packet_tx.v $(SIM_DIR)/udp_packet_tx_tb.v
	cd $(SIM_DIR) && vvp $(SIM_DIR)/udp_packet_tx_tb.vvp
	python3 $(SIM_DIR)/check_packet.py
	iverilog -g2005 -I$(RTL) -o $(SIM_DIR)/adc_packetizer_tb.vvp \
		$(RTL)/sync_fifo.v $(RTL)/adc_packetizer.v $(SIM_DIR)/adc_packetizer_tb.v
	cd $(SIM_DIR) && vvp $(SIM_DIR)/adc_packetizer_tb.vvp
	python3 $(SIM_DIR)/check_pack14.py
	iverilog -g2005 -I$(RTL) -o $(SIM_DIR)/adc_packetizer12_tb.vvp \
		$(RTL)/sync_fifo.v $(RTL)/adc_packetizer.v $(SIM_DIR)/adc_packetizer12_tb.v
	cd $(SIM_DIR) && vvp $(SIM_DIR)/adc_packetizer12_tb.vvp
	python3 $(SIM_DIR)/check_pack12.py

clean:
	rm -f $(SIM_DIR)/*.vvp $(SIM_DIR)/gmii.hex $(SIM_DIR)/pack12.hex $(SIM_DIR)/pack14.hex
