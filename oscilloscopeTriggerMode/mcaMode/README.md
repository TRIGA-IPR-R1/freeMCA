# Modo MCA

O **mcaMode** é o modo de aquisição por trigger do freeMCA: a FPGA acompanha a linha de base, dispara em cada pulso e envia a forma do pulso ou só a medida do pico. A medida do pico pode ser feita por um filtro trapezoidal de Jordanov-Knoll, que substitui o amplificador formatador NIM quando o ADC está ligado direto no pré-amplificador. Os parâmetros mudam em funcionamento, por comandos na UART. Inclui também o fluxo contínuo do [oscilloscopeMode](../oscilloscopeMode), no mesmo formato, para conferir o front-end sem trocar de bitstream.

Alvo atual: **Colorlight i9plus-v6.1** (XC7A50T) + módulo **KeYi AD9245** (1 canal, 14 bits, usado a 25 MSPS).

> **Estado:** tudo o que está aqui foi simulado com iverilog (`make -C sim`), mas ainda **não foi sintetizado nem testado na placa**.

## Estrutura de arquivos

```
mcaMode/
  README.md     este texto
  mca_top.xdc   pinos e restrições da placa (ADC, UART, LEDs, os dois PHYs Ethernet)
  rtl/          gateware (Verilog)
  host/         programas no PC: aquisição, osciloscópio, espectro, configuração
  sim/          testbench iverilog do top completo e conferidores em Python
```

## O que vem do oscilloscopeMode

Usados **sem alteração**, direto de `../oscilloscopeMode/rtl/`:

| Arquivo | Uso aqui |
|---|---|
| `adc_packetizer.v` + `sync_fifo.v` | Fluxo contínuo: fila, número de sequência, flag de overflow, 14 bits empacotados |
| `udp_packet_tx.v` + `crc32_eth.v` | Único MAC, para o fluxo e para os pacotes do MCA |
| `rgmii_tx.v` | Saída RGMII, com o mesmo tráfego nos dois PHYs |

Também seguem o oscilloscopeMode: `config.vh` (mesmos nomes e endereços), o PLL com VCO em 1000 MHz e 125 MHz em `CLKOUT0`, o reset do PHY, o código do LED e o formato do datagrama de fluxo (`magic 0xADC0 | seq | n | flags | amostras`). Os programas `host/udp_scope_rx.py` e `udp_scope_plot.py` do oscilloscopeMode recebem o fluxo deste modo sem mudança.

## Arquivos novos em `rtl/`

| Arquivo | Função |
|---|---|
| `mca_top.v` | Top: captura do AD9245, média, linha de base, trigger, medida do pico, comandos, envio |
| `mca_pkt.v` | Gerador de bytes dos pacotes do MCA, UART TX e UART RX |
| `jk_trapezio.v` | Filtro trapezoidal de Jordanov-Knoll com correção de polo-zero |
| `mca_pll.v` | 25 MHz → 50 MHz (aquisição) e 125 MHz (rede) |
| `config.vh` | MAC, IP e porta; amostras por datagrama do fluxo |

A aquisição roda em 50 MHz com o ADC a 25 MHz, exatamente como no firmware validado no teste de rampa; só a rede roda em 125 MHz.

## Síntese

```bash
make            # mca_top.bit (Yosys + nextpnr-xilinx + prjxray, fluxo openXC7)
make prog       # carrega na SRAM (openFPGALoader -c ch347_jtag)
```

O `Makefile` já lista todas as fontes, incluindo as que vêm de `../oscilloscopeMode/rtl`, e passa `-I rtl` para o `config.vh` daqui. Os caminhos das ferramentas têm valores padrão do instalador do openXC7; se os seus forem outros, passe na linha de comando (`make CHIPDB=... PRJXRAY_DB=...`).

Se preferir usar um Makefile próprio, a síntese precisa de **todos** estes arquivos (faltando qualquer um, o Yosys para com "module ... is not part of the design"):

```
rtl/mca_top.v rtl/mca_pkt.v rtl/mca_pll.v rtl/jk_trapezio.v
../oscilloscopeMode/rtl/adc_packetizer.v ../oscilloscopeMode/rtl/sync_fifo.v
../oscilloscopeMode/rtl/udp_packet_tx.v  ../oscilloscopeMode/rtl/crc32_eth.v
../oscilloscopeMode/rtl/rgmii_tx.v
```

com `-Irtl` na leitura e `mca_top.xdc` no nextpnr.

## Modos

| MODO | Nome | O que sai |
|---|---|---|
| 0 | formas | Cada trigger envia `N_PRE + 1 + N_POS` amostras (padrão 49 + 1 + 150) |
| 1 | picos | Cada trigger envia 26 bytes: tempo, altura, base, área, posição do pico, flags |
| 2 | contínuo | Sem trigger: fluxo corrido a 25 MSPS / 2^LOG2_MEDIA, 720 amostras por datagrama, sempre por UDP |

Formas e picos saem pela UART (2 Mbaud) ou por UDP, conforme `SAIDA`. No modo picos a altura é medida de um de dois jeitos:

- **`FILTRO = 0`**: máximo do sinal com filtro 1-2-1, sobre uma linha de base congelada 32 a 63 amostras antes do trigger. É o certo quando há um amplificador formatador (571, 572A, 590A) antes do ADC.
- **`FILTRO = 1`**: topo do filtro trapezoidal (abaixo). É o certo quando o ADC recebe direto a saída do pré-amplificador.

## Filtro trapezoidal (Jordanov-Knoll)

O `rtl/jk_trapezio.v` faz digitalmente o que o amplificador formatador faz: transforma o pulso do pré-amplificador (subida rápida, cauda exponencial de constante τ) num trapézio com subida de `TRAP_K` amostras e topo plano de `TRAP_M` amostras, cuja altura é proporcional à carga. A correção de polo-zero cancela a cauda, então um pulso que chega sobre a cauda de outro é medido sem erro.

```
b(n) = v(n) − v(n−k)          d(n) = b(n) − b(n−l),  l = k + m
p(n) = p(n−1) + d(n)          s(n) = s(n−1) + 4 p(n) + PZ4 d(n),  PZ4 = 4 / (exp(dt/τ) − 1)
```

Tudo em inteiros, sem arredondamento, então `s` não deriva. O filtro roda continuamente sobre as amostras médias (passo `2^LOG2_MEDIA × 40 ns`). A altura enviada é o máximo de `s` na janela pós-trigger menos a linha de base de `s` (média de 1024 amostras, atualizada só com a entrada quieta), deslocado de `TRAP_SH` bits:

```
PICO4 = altura × TRAP_K × (TRAP_PZ + 4) / 2^TRAP_SH        (2 a 4 contagens por LSB)
```

Como escolher:

| Parâmetro | Regra prática |
|---|---|
| Subida (`TRAP_K`) | Faz o papel do shaping time: 1–2 µs para NaI, 3–6 µs para CsI(Tl). Mais longo = menos ruído, mais empilhamento |
| Topo (`TRAP_M`) | Maior que o tempo de subida do pulso no pré (senão há déficit balístico): ~0,5–1 µs para NaI, 2–3 µs para CsI(Tl) |
| Polo-zero (`TRAP_PZ`) | τ do pré. Meça capturando formas com janela longa e rodando `espectrometria_mca.py --metodo trap` (o τ estimado aparece na tela) |
| `N_POS` | Pelo menos `TRAP_K + TRAP_M + 4`, para o topo cair dentro da janela |

O `mca_config.py` calcula tudo em microssegundos: `trapezio=SUBIDA,TOPO,TAU`. O leitor grava a escala no `.json` e o `espectrometria_mca.py` a aplica, então os espectros saem em LSB equivalentes de qualquer jeito. Os eventos medidos pelo filtro têm o bit 4 das flags ligado.

Limitação: o trigger continua no sinal bruto (limiar acima da linha de base acompanhada). Com o pré direto e taxa alta, as caudas longas se somam e o limiar efetivo varia; um trigger por filtro rápido (trapézio curto) é o próximo passo.

## Comandos (UART, 2 Mbaud 8N1)

`0xA5 0x5A REG VALOR_ALTO VALOR_BAIXO CHK`, com `CHK = REG ^ VALOR_ALTO ^ VALOR_BAIXO ^ 0xFF`.

| REG | Nome | Faixa | Significado |
|---|---|---|---|
| 0 | LIMIAR | 4–8000 | Limiar de trigger acima da linha de base (LSB) |
| 1 | CONFIRMA | 1–15 | Amostras seguidas acima do limiar para disparar |
| 2 | LOG2_MEDIA | 0–4 | Média de 1, 2, 4, 8 ou 16 amostras do ADC |
| 3 | POLARIDADE | 0–1 | 0 = pulsos positivos, 1 = negativos |
| 4 | MODO | 0–2 | formas, picos, contínuo |
| 5 | N_PRE | 8–600 | Amostras antes do trigger (N_PRE + N_POS ≤ 699) |
| 6 | N_POS | 8–690 | Amostras depois do trigger = janela de busca do pico |
| 7 | SAIDA | 0–1 | 0 = UART, 1 = UDP |
| 8 | ATIVO | 0–1 | 0 = pausa a aquisição por trigger |
| 9 | STATUS | — | Só pede o status |
| 10 | ZERA_TEMPO | — | Zera timestamp e tempo vivo |
| 11 | FILTRO | 0–1 | 1 = no modo picos, altura pelo filtro trapezoidal |
| 12 | TRAP_K | 2–255 | Subida do trapézio (amostras) |
| 13 | TRAP_M | 1–255 | Topo plano (amostras) |
| 14 | TRAP_PZ | 4–65535 | Polo-zero: 4 / (exp(dt/τ) − 1) |
| 15 | TRAP_SH | 0–31 | Deslocamento à direita do resultado |

Todo comando é respondido com um pacote de status pela UART (e por UDP se `SAIDA = 1` ou `MODO = 2`). Valor fora da faixa não altera nada e volta com `ack = 0`.

## Pacotes

Pacotes do MCA: `0xFF 0xFF CFG TIPO ...`, com `CFG = {0, 3'd2, POLARIDADE, LOG2_MEDIA}` e campos numéricos em bytes de 7 bits.

```
TIPO 0 forma : NAM(2) NPRE(2) timestamp(5) tempo_vivo(5) + NAM x {alto, baixo}
TIPO 1 pico  : timestamp(5) tempo_vivo(5) PICO4(3) BASE(2) AREA(4) TPICO(2) FLAGS(1)
TIPO 2 status: VERSAO LIMIAR(2) CONFIRMA MODO SAIDA ATIVO NPRE(2) NPOS(2) ACK REG
               FILTRO TRAP_K(2) TRAP_M(2) TRAP_PZ(3) TRAP_SH            (26 bytes, versão 3)
```

Flags do pico: bit0 saturou, bit1 empilhamento, bit2 ainda acima de limiar/2 no fim da janela, bit3 pico na última amostra, bit4 altura medida pelo filtro trapezoidal.

Fluxo contínuo (little-endian), igual ao oscilloscopeMode:

```
magic u16 = 0xADC0 | seq u32 | n u16 = 720 | flags u16 | 1260 bytes (14 bits empacotados)
```

flags: bit0 overflow da fila, bit1 empacotado, bit2 offset binary. `seq` recomeça em zero a cada entrada no modo contínuo.

No UDP tudo vai para a mesma porta; um datagrama é de fluxo se começa por `C0 AD` e do MCA se começa por `FF FF`.

## Rede

| | FPGA | PC |
|---|---|---|
| IP | 192.168.1.50 | 192.168.1.100 |
| MAC destino | broadcast | — |
| UDP | 5000 | bind `0.0.0.0` |

O cabo precisa negociar **1 Gbps**. No PC: `sudo ip addr add 192.168.1.100/24 dev <iface>`.

## Programas (`host/`)

```bash
# configuração e status
python3 host/mca_config.py --porta /dev/ttyUSB0
python3 host/mca_config.py --porta /dev/ttyUSB0 limiar=30 log2_media=3 modo=picos saida=udp

# osciloscópio: mostra formas por trigger ou o fluxo contínuo, conforme o que chegar
python3 host/osciloscopio_mca.py --udp
python3 host/mca_config.py --porta /dev/ttyUSB0 log2_media=0 modo=continuo

# aquisição (o formato do arquivo segue o primeiro pacote recebido)
python3 host/leitor_adc.py --udp --saida cs_picos --tempo_max_h 1
python3 host/leitor_adc.py --udp --config log2_media=2 modo=continuo --saida ruido --tempo_max_s 2

# espectro (formas ou picos)
python3 host/espectrometria_mca.py --arquivo cs_picos --fit

# pré-amplificador direto no ADC, sem NIM: filtro trapezoidal na FPGA
python3 host/mca_config.py --porta /dev/ttyUSB0 log2_media=2 n_pre=49 n_pos=150 modo=formas
python3 host/leitor_adc.py --porta /dev/ttyUSB0 --saida pre_formas --eventos 2000
python3 host/espectrometria_mca.py --arquivo pre_formas --metodo trap          # mostra o tau do pré
python3 host/leitor_adc.py --udp --config trapezio=2,1,50 filtro=sim modo=picos saida=udp --saida cs_trap
python3 host/espectrometria_mca.py --arquivo cs_trap --fit
```

No fluxo contínuo o osciloscópio mostra as amostras seguidas, a taxa da FPGA (pelo `seq`) e a recebida, pacotes perdidos, overflow, média, RMS e amostras saturadas. O leitor grava as amostras corridas em `uint16` (código do ADC, 8192 = 0 V) e anota no `.json` a taxa, a posição de cada lacuna e os pacotes com overflow.

Os mesmos programas leem os firmwares anteriores (UART de 413 bytes, `mca_ad9245_udp.v`, `mca_ad9245_cfg.v`) e o fluxo do oscilloscopeMode (`--udp 5000` ou `--udp 5001`).

A 25 MSPS o fluxo são ~44 MB/s e ~35 mil datagramas/s; o leitor em Python pode perder pacotes nessa taxa (aparecem como lacunas). Para gravar sem perdas, use `log2_media` maior.

## Hardware

Restrições em [`mca_top.xdc`](mca_top.xdc): o `.xdc` do AD9245 sem nenhuma mudança, mais a rede e a UART de comandos, no mesmo formato.

| Sinal | Pino | Observação |
|---|---|---|
| `pino_uart_tx_fisico` | V5 | Conector, pino 52 → RX do adaptador USB-TTL |
| `pino_uart_rx_fisico` | T4 | Conector, pino 51 → TX do adaptador USB-TTL (novo) |
| PHY 0 (U5): `eth_txc`, `eth_tx_ctl`, `eth_txd[0..3]` | A1, D1, B2 B1 C2 D2 | RGMII, SLEW FAST |
| PHY 1 (U9): `eth1_txc`, `eth1_tx_ctl`, `eth1_txd[0..3]` | M6, N5, M5 M2 N4 P4 | RGMII, SLEW FAST |
| `eth_rst_n`, `eth_mdc`, `eth_mdio` | H2, G1, G2 | Comuns aos dois PHYs |

Pinos de rede conferidos no pinout da placa (wuxx/Colorlight-FPGA-Projects) e na plataforma `colorlight_i9plus` do litex-boards. Os pinos de recepção dos PHYs não são usados.

LED D2: piscada lenta = ok; média = o ADC saturou há pouco; rápida = overflow da fila do fluxo.

## Simulação

```bash
make -C sim jk         # o filtro sozinho, bit a bit contra o modelo em Python, 5 configurações
make -C sim trapezio   # modo picos com o filtro, pulsos de pré-amplificador (inclusive um sobre a cauda de outro)
make -C sim fluxo      # fluxo contínuo conferido amostra por amostra
make -C sim completo   # formas, picos, janela, limiar, comandos, UART e UDP
```

O testbench simula o ADC, envia comandos pela UART e captura a UART e o RGMII. Os conferidores verificam FCS, checksum IP e comprimentos de cada quadro, comparam altura, base e janela de cada evento com o pulso injetado, e comparam o fluxo com as amostras registradas dentro da FPGA simulada. `sim_prims.v` são modelos simples de `PLLE2_BASE`, `IBUF`, `BUFG`, `ODDR` e `IDDR`, só para simulação.

## Licença

GPLv3 ou posterior, como o restante do freeMCA.
