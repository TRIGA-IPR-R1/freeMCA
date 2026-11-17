# Modo osciloscópio

O **oscilloscopeMode** é o modo de aquisição em forma de onda do freeMCA: a FPGA lê o ADC e manda as amostras cruas pela Ethernet, sem histogramar. Serve para conferir o front-end (ganho, offset, saturação, jitter de clock) antes do modo MCA.

Alvo atual: **Colorlight i9plus-v6.1** (XC7A50T) + módulo **KeYi AD9248** (2 canais, 14 bits, até 65 MSPS).

## Estrutura de arquivos

```
oscilloscopeMode/
  README.md     este texto
  rtl/          gateware (Verilog) sintetizado na FPGA
  host/         programas no PC que recebem e desenham o stream UDP
  sim/          testbenches iverilog do empacotamento e do MAC UDP
  info/         pinouts e jumpers (não é código)
```

| Pasta | Significado do nome | O que entra |
|---|---|---|
| **rtl** | *Register-Transfer Level* — descrição do hardware em Verilog | Top, ADC, packetizer, UDP/RGMII, PLL, `config.vh` |
| **host** | Máquina anfitriã (o PC), em oposição à FPGA | `udp_scope_rx.py`, `udp_scope_plot.py`, `adc_codec.py` |
| **sim** | Simulação, sem placa | TBs, `Makefile`, checkers Python do payload |
| **info** | Notas de conexão / pinagem | ExtBoard↔AD9248 e ExtBoard↔PMOD Ethernet |

Convenção: **rtl** = o que vira bitstream; **host** = o que roda no computador; **sim** = prova o rtl sem silício; **info** = fios e pinos.

## O que a FPGA faz

1. Gera os clocks do ADC (**ACL** e **BCL**, 31.25 MHz, 180°).
2. Captura o barramento DDR de 14 bits (D0 = LSB … D13 = MSB). No kit, borda de subida = canal B, descida = canal A. Código offset-binary (“direct code”).
3. Empacota 720 amostras/pacote em 14 bits little-endian (4 amostras = 7 bytes).
4. Envia **canal A na UDP 5000** e **canal B na UDP 5001**, no mesmo cabo 1G (os dois PHYs repetem o mesmo tráfego).

Dois canais a 14 bits packed a 65 MSPS não cabem em um link de 1G (~1.85 Gbps). Por isso cada canal roda a **31.25 MSPS** (~928 Mbps no total).

## Rede

| | FPGA | PC |
|---|---|---|
| IP | 192.168.1.50 | 192.168.1.100 |
| MAC destino | broadcast | — |
| UDP | 5000 (A), 5001 (B) | bind `0.0.0.0` |

MAC/IP/portas: `rtl/config.vh`. O cabo precisa negociar **1 Gbps**; em 100 Mbps o MAC RGMII da FPGA não entrega pacotes.

No PC, a partir desta pasta:

```bash
sudo ip addr add 192.168.1.100/24 dev <iface>
python3 host/udp_scope_plot.py              # A e B
python3 host/udp_scope_rx.py --port 5000    # só A
python3 host/udp_scope_rx.py --port 5001    # só B
```

Espera ~31.25 MSPS em cada porta, `packed/offset`, overflow 0.

## Payload UDP

Little-endian:

```
magic u16 = 0xADC0 | seq u32 | n u16 | flags u16 | amostras packed
```

- `n` = 720
- flags bit0 = overflow da FIFO
- flags bit1 = packed (largura = 8 × bytes_úteis / n → 14)
- flags bit2 = offset binary

Codec: `host/adc_codec.py`.

## Hardware

Pinout ExtBoard ↔ AD9248: [`info/connection_adc_14bits_65msps_dual_AD9248.txt`](info/connection_adc_14bits_65msps_dual_AD9248.txt).

Jumpers ExtBoard ↔ PMOD Ethernet: [`info/connection_PMOD_ethernet.txt`](info/connection_PMOD_ethernet.txt).

O módulo ADC usa **5 V** no pino 5V. ACL/BCL são **saídas da FPGA**. D0/D1 existem neste módulo (no AD9238 de 12 bits esses pinos são NC).

LED D2 da i9plus: piscada lenta = ok; mais rápida = overflow ou overrange (OTR).

## RTL

| Arquivo | Função |
|---|---|
| `rtl/udp_scope_top.v` | Top: PLL 125 MHz, divisor 31.25 MHz, dois packetizers, árbitro GMII, RGMII nos dois PHYs |
| `rtl/adc_ad9248.v` | Clocks ODDR + captura IDDR + CDC |
| `rtl/adc_packetizer.v` | Header + pack 14 bits |
| `rtl/udp_packet_tx.v` | Ethernet II + IPv4 + UDP |
| `rtl/rgmii_tx.v` | GMII 8 bits @ 125 MHz → RGMII DDR |
| `rtl/pll_25to125.v` | 25 MHz da placa → 125 MHz |

Síntese: Yosys + nextpnr-xilinx (openXC7), programação SRAM com `openFPGALoader -c ch347_jtag` (não grava SPI a menos que se peça).

Simulação do empacotamento/UDP: `make -C sim` (iverilog).

## Licença

GPLv3 ou posterior. Copyright (C) 2026 Daniel Batista, Thalles Campagnani.
