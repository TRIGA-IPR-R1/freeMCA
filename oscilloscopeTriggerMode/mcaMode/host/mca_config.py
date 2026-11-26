#!/usr/bin/env python3
"""
mca_config.py - Envia comandos ao firmware configurável (mca_ad9245_cfg.v ou mcaMode/rtl/mca_top.v)
pela UART e mostra o status.

Os comandos sempre vão pela serial (mesmo quando os dados saem por UDP). Cada comando é
confirmado pelo pacote de status que o FPGA devolve.

Exemplos:
  python mca_config.py --porta /dev/ttyUSB0                      # só mostra a configuração atual
  python mca_config.py --porta /dev/ttyUSB0 limiar=30 log2_media=3
  python mca_config.py --porta /dev/ttyUSB0 modo=picos saida=udp
  python mca_config.py --porta /dev/ttyUSB0 n_pre=100 n_pos=300 modo=formas saida=uart
  python mca_config.py --porta /dev/ttyUSB0 log2_media=0 modo=continuo   # só no mca_top.v
  python mca_config.py --porta /dev/ttyUSB0 log2_media=2 trapezio=2,1,50 filtro=sim modo=picos

Parâmetros:
  limiar=4..8000       limiar de trigger acima da linha de base (LSB; 82 ~ 50 mV)
  confirma=1..15       amostras seguidas acima do limiar para disparar
  log2_media=0..4      média de 1,2,4,8,16 amostras do ADC (passo de 40,80,160,320,640 ns)
  polaridade=pos|neg   sentido do pulso
  modo=formas|picos|continuo   forma inteira, só a medida do pico, ou fluxo corrido de
                       amostras sem trigger (continuo: só no mca_top.v, sempre por UDP)
  n_pre=8..600         amostras antes do trigger           (n_pre + n_pos <= 699)
  n_pos=8..690         amostras depois do trigger = janela em que o pico é procurado
  saida=uart|udp       por onde saem os dados
  ativo=0|1            pausa / retoma a aquisição
  zera_tempo           zera timestamp e tempo vivo

Filtro trapezoidal de Jordanov-Knoll (só no mca_top.v; vale no modo picos):
  trapezio=SUBIDA,TOPO,TAU   em microssegundos: subida e topo plano do trapézio e a constante de
                       decaimento do pré-amplificador. Calcula e envia trap_k, trap_m, trap_pz e
                       trap_sh para o passo em uso (log2_media é aplicado antes, se vier junto).
  filtro=sim|nao       liga/desliga a medida da altura pelo trapézio
  trap_k, trap_m, trap_pz, trap_sh   os registradores, se quiser ajustar um a um
Para medir o tau do seu pré: capture formas com janela longa e rode
  python espectrometria_mca.py --arquivo X --metodo trap   (o tau estimado aparece na tela)

Ao mudar a janela, mande primeiro o valor que diminui (a soma não pode passar de 699).
Precisa do mca_comum.py na mesma pasta.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mca_comum import (NOMES_MODO, REGISTRADORES, Decodificador, decodificar_cfg, escala_trapezio, montar_comando,
                       parametros_trapezio, tau_do_pz)

APELIDOS = dict(pos=0, neg=1, formas=0, forma=0, picos=1, pico=1, continuo=2, fluxo=2, osciloscopio=2,
                uart=0, udp=1, sim=1, nao=0, on=1, off=0)
NOMES_REG = {num: nome for nome, (num, _, _) in REGISTRADORES.items()}


def interpretar(textos):
    """['limiar=30', 'modo=picos', 'zera_tempo'] -> [(nome, valor), ...]; levanta ValueError."""
    saida = []
    for t in textos:
        nome, _, valor = t.partition("=")
        nome = nome.strip().lower()
        if nome == "trapezio":
            try:
                sub, topo, tau = (float(x.replace(",", ".")) for x in valor.split(","))
            except ValueError:
                raise ValueError("use trapezio=SUBIDA,TOPO,TAU em us (ex.: trapezio=2,1,50)")
            if min(sub, topo, tau) <= 0:
                raise ValueError("trapezio: subida, topo e tau têm de ser positivos")
            saida.append(("trapezio", (sub, topo, tau)))
            continue
        if nome not in REGISTRADORES:
            raise ValueError(f"parâmetro desconhecido: {nome} (opções: {', '.join(REGISTRADORES)})")
        _, vmin, vmax = REGISTRADORES[nome]
        valor = valor.strip().lower()
        v = APELIDOS[valor] if valor in APELIDOS else int(valor or 0)
        if not vmin <= v <= vmax and vmax > 0:
            raise ValueError(f"{nome}={v} fora da faixa {vmin}..{vmax}")
        saida.append((nome, v))
    # o passo de amostragem decide k e m do trapézio: log2_media vai antes de tudo
    return sorted(saida, key=lambda c: c[0] != "log2_media")


def texto_status(st, cfg=None):
    c = decodificar_cfg(cfg) if cfg is not None else None
    L = [f"limiar={st['limiar']} LSB | confirma={st['confirma']} | modo={NOMES_MODO[min(st['modo'], 2)]} | "
         f"saída={'UDP' if st['saida'] else 'UART'} | {'ativo' if st['ativo'] else 'PAUSADO'}",
         f"janela: {st['n_pre']} antes + trigger + {st['n_pos']} depois"]
    if c:
        nam = st["n_pre"] + 1 + st["n_pos"]
        if st["modo"] == 2:
            L.append(f"fluxo contínuo por UDP a {1 / c['dt_us']:.4g} MSPS (sem trigger)")
        L.append(f"passo {c['dt_us'] * 1000:.0f} ns (log2_media={c['log2_media']}) -> janela de {nam * c['dt_us']:.1f} us | "
                 f"polaridade {'+' if c['polaridade'] > 0 else '-'} | firmware v{st['versao_fw']}")
    if "filtro" in st:
        k, m = st["trap_k"], st["trap_m"]
        t = (f"filtro trapezoidal {'LIGADO' if st['filtro'] else 'desligado'}: subida {k} am., topo {m} am., "
             f"polo-zero {st['trap_pz']}, deslocamento {st['trap_sh']} -> {escala_trapezio(st):.3f} contagens/LSB")
        if c:
            t += (f"\n    = subida {k * c['dt_us']:.2f} us, topo {m * c['dt_us']:.2f} us, "
                  f"tau {tau_do_pz(st['trap_pz'], c['dt_us']):.1f} us")
        L.append(t)
        if st["filtro"] and st["modo"] != 1:
            L.append("AVISO: o filtro só é usado no modo picos.")
        if st["filtro"] and st["n_pos"] < k + m + 4:
            L.append(f"AVISO: n_pos={st['n_pos']} é curto para o trapézio; use n_pos >= {k + m + 4} "
                     f"(senão o topo cai fora da janela e o evento vem com a flag 'pico no fim').")
    return "\n".join("  " + x for x in L)


def enviar(ser, comandos, dec=None, espera_s=1.0, verboso=True):
    """Envia cada (nome, valor) e espera o status correspondente. Devolve (status, cfg) final.
    Levanta RuntimeError se o FPGA não responder ou recusar."""
    dec = dec or Decodificador()
    ultimo = (None, None)
    for nome, valor in comandos:
        if nome == "trapezio":
            if ultimo[1] is None:                       # passo atual: pede o status
                ultimo = enviar(ser, [("status", 0)], dec, espera_s, verboso=False)
            if "filtro" not in ultimo[0]:
                raise RuntimeError("este firmware não tem o filtro trapezoidal (use o mcaMode/rtl/mca_top.v)")
            dt = decodificar_cfg(ultimo[1])["dt_us"]
            try:
                regs = parametros_trapezio(*valor, dt)
            except ValueError as e:
                raise RuntimeError(f"trapezio: {e}")
            if verboso:
                print(f"  trapézio para passo de {dt * 1000:.0f} ns: k={regs['trap_k']} m={regs['trap_m']} "
                      f"pz={regs['trap_pz']} sh={regs['trap_sh']}")
            ultimo = enviar(ser, list(regs.items()), dec, espera_s, verboso)
            continue
        num = REGISTRADORES[nome][0]
        ser.write(montar_comando(num, valor))
        ser.flush()
        fim = time.time() + espera_s
        resp = None
        while time.time() < fim and resp is None:
            dados = ser.read(max(1, getattr(ser, "in_waiting", 1)))
            for pk in dec.alimentar(dados, final=not dados, tudo=True):
                if pk[0] == "status" and pk[2]["reg"] == num and pk[2]["ack"] != 2:
                    resp = pk
        if resp is None:
            raise RuntimeError(f"sem resposta ao comando {nome}={valor} (firmware certo? RX ligado? porta e baud?)")
        if resp[2]["ack"] != 1:
            raise RuntimeError(f"o FPGA recusou {nome}={valor} (fora da faixa, n_pre + n_pos > 699, ou "
                               f"firmware sem esse recurso)")
        if verboso:
            print(f"  ok: {nome}" + (f" = {valor}" if REGISTRADORES[nome][2] else ""))
        ultimo = (resp[2], resp[1])
    return ultimo


def main():
    ap = argparse.ArgumentParser(description="Configura o firmware do MCA (mca_ad9245_cfg.v ou mca_top.v) pela UART",
                                 epilog="Veja a lista de parâmetros no início deste arquivo.")
    ap.add_argument("--porta", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=2_000_000)
    ap.add_argument("comandos", nargs="*", help="pares nome=valor, na ordem em que serão enviados")
    args = ap.parse_args()
    try:
        cmds = interpretar(args.comandos)
    except ValueError as e:
        sys.exit(f"[ERRO] {e}")
    try:
        import serial
    except ImportError:
        sys.exit("[ERRO] pyserial não instalado (pip install pyserial).")
    with serial.Serial(args.porta, args.baud, timeout=0.05) as ser:
        ser.reset_input_buffer()
        try:
            st, cfg = enviar(ser, cmds + [("status", 0)])
        except RuntimeError as e:
            sys.exit(f"[ERRO] {e}")
    print("Configuração no FPGA:")
    print(texto_status(st, cfg))


if __name__ == "__main__":
    main()
