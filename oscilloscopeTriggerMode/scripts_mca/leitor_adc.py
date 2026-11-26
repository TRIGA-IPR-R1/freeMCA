#!/usr/bin/env python3
"""
leitor_adc.py - Aquisição do MCA pela UART ou por UDP.

Serve para todos os firmwares:
  mca_ad9245.v          UART, formas de 200 amostras
  mca_ad9245_udp.v      UDP,  formas de 200 amostras            (--udp)
  mca_ad9245_cfg.v      UART ou UDP, formas de tamanho variável ou só picos
  mcaMode/rtl/mca_top.v o mesmo, mais o fluxo contínuo do freeMCA (modo=continuo, por UDP)
  oscilloscopeMode      fluxo contínuo do freeMCA (--udp 5000 ou 5001)

Saída:
  <saida>.dat   registros fixos (numpy.memmap); ts/viva em ticks de amostra (dt_us no .json)
                  formas: ts (uint64), viva (uint64), amostras (n x uint16)
                  picos:  ts, viva, pico4 (uint16, 4 x altura), base (uint16), area (int32),
                          tpico (uint16), flags (uint8). Com o filtro trapezoidal do mca_top.v,
                          pico4 = altura x escala; a escala (contagens por LSB) vai no .json,
                          em "trapezio", e o espectrometria_mca.py já a aplica
                  fluxo:  amostras corridas em uint16 (código do ADC, 8192 = 0 V); o .json traz a
                          taxa, os pacotes perdidos (lacunas, com a posição) e os de overflow
  <saida>.json  metadados: formato, dt_us, polaridade, escala, contagens, tempos
  <saida>.bin   fluxo bruto recebido (opcional, --salvar_bruto)

Uso:
  python leitor_adc.py --porta /dev/ttyUSB0 --saida th_longa --eventos 10000000
  python leitor_adc.py --udp --saida cs_udp --tempo_max_h 1
  python leitor_adc.py --udp --config limiar=30 modo=picos saida=udp --saida cs_picos
  python leitor_adc.py --udp --config log2_media=2 modo=continuo --saida ruido --tempo_max_s 2
  python leitor_adc.py --reproduzir captura.bin --saida teste      # sem hardware

--config manda os comandos pela serial (--porta) antes de começar; só vale para o
mca_ad9245_cfg.v. O arquivo fica com o formato do primeiro evento recebido; eventos com
outra configuração (mudança no meio da captura) são ignorados e contados.

Precisa do mca_comum.py (e do mca_config.py para --config) na mesma pasta.
Ctrl+C encerra deixando os arquivos consistentes.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mca_comum import (CAB_FLUXO, COD_ZERO, DTYPE_PICO, FLAG_TRAPEZIO, FLUXO_EMPACOTADO, FLUXO_OFFSET, PORTA_UDP,
                       T_ADC_US, escala_trapezio, tau_do_pz,
                       ContadorFluxo, Decodificador, Desembrulhador, abrir_udp, altura_pico_lsb, cab_fluxo,
                       decodificar_cfg, desempacotar_fluxo, dtype_reg, eh_fluxo, ler_udp)


class Painel:
    def __init__(self, alvo, lsb_por_v):
        self.alvo = alvo
        self.lsb_por_v = lsb_por_v
        self.bordas = np.linspace(0.1, 2.5, 25)
        self.cont = np.zeros(24, dtype=np.int64)
        self.acima = 0
        self.linhas = 0

    def adicionar(self, altura_lsb):
        v = altura_lsb / self.lsb_por_v
        if v >= 2.5:
            self.acima += 1
        elif v >= 0.1:
            self.cont[min(int((v - 0.1) / 0.1), 23)] += 1

    def mostrar(self, n, t_real, ts_s, viva_s, dec, info):
        if self.linhas:
            sys.stdout.write(f"\033[{self.linhas}A")
        pct = 100.0 * n / max(1, self.alvo)
        cheio = int(30 * min(1.0, n / max(1, self.alvo)))
        barra = "█" * cheio + "░" * (30 - cheio)
        taxa_ent = n / viva_s if viva_s > 0 else 0.0
        frac_viva = viva_s / ts_s if ts_s > 0 else 0.0
        h, m, s = int(t_real // 3600), int(t_real % 3600 // 60), int(t_real % 60)
        L = [f"[{barra}] {n}/{self.alvo} ({pct:6.2f}%)  {h:02d}:{m:02d}:{s:02d}  {info}      ",
             f"Taxa: {n / max(t_real, 1e-9):7.1f} ev/s gravados | {taxa_ent:8.1f} cps reais (tempo vivo "
             f"{100 * frac_viva:5.1f}%) | inválidos {dec.invalidos}      ",
             "-" * 86,
             "CONTAGENS POR FAIXA DE AMPLITUDE (pico - linha de base, com filtro de espículas):"]
        for row in range(6):
            cols = []
            for col in range(4):
                k = row + 6 * col
                cols.append(f"[{self.bordas[k]:3.1f}-{self.bordas[k + 1]:3.1f} V]: {self.cont[k]:<8d}")
            L.append(" | ".join(cols))
        L.append(f"> 2,5 V: {self.acima:<10d}" + " " * 60)
        L.append("-" * 86)
        sys.stdout.write("\n".join(L) + "\n")
        sys.stdout.flush()
        self.linhas = len(L)


def main():
    ap = argparse.ArgumentParser(description="Aquisição do MCA (AD9245) pela UART ou por UDP")
    ap.add_argument("--porta", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=2_000_000)
    ap.add_argument("--udp", nargs="?", type=int, const=PORTA_UDP, default=0, metavar="PORTA",
                    help=f"recebe por UDP em vez da serial (porta padrão {PORTA_UDP})")
    ap.add_argument("--config", nargs="+", default=[], metavar="NOME=VALOR",
                    help="comandos para o mca_ad9245_cfg.v, enviados pela serial antes de começar "
                         "(ex.: limiar=30 modo=picos saida=udp); veja mca_config.py")
    ap.add_argument("--saida", required=True, help="prefixo dos arquivos de saída")
    ap.add_argument("--eventos", type=int, default=10_000_000, help="alvo de eventos")
    ap.add_argument("--tempo_max_h", type=float, default=0.0, help="limite de tempo (h); 0 = sem limite")
    ap.add_argument("--tempo_max_s", type=float, default=0.0, help="limite de tempo (s); 0 = sem limite")
    ap.add_argument("--amostras", type=int, default=0,
                    help="fluxo contínuo: número de amostras a gravar (sem este e sem limite de tempo: 10 milhões)")
    ap.add_argument("--lsb_por_v", type=float, default=1638.0,
                    help="escala na entrada do ADC (calibre com DC conhecido)")
    ap.add_argument("--salvar_bruto", action="store_true", help="grava também o fluxo bruto recebido")
    ap.add_argument("--reproduzir", help="lê um fluxo bruto .bin em vez da serial/UDP (teste)")
    ap.add_argument("--descricao", default="", help="texto livre gravado no .json (fonte, HV, ganho...)")
    ap.add_argument("--sobrescrever", action="store_true",
                    help="permite gravar por cima de uma captura existente com o mesmo --saida")
    args = ap.parse_args()

    existentes = [args.saida + e for e in (".dat", ".json") if os.path.exists(args.saida + e)]
    if existentes and not args.sobrescrever:
        sys.exit(f"[ERRO] já existe {', '.join(existentes)}. Use outro --saida "
                 f"(ou --sobrescrever para apagar a captura anterior).")

    comandos = []
    if args.config:
        from mca_config import enviar, interpretar, texto_status
        try:
            comandos = interpretar(args.config)
        except ValueError as e:
            sys.exit(f"[ERRO] --config: {e}")
        if args.reproduzir:
            sys.exit("[ERRO] --config não faz sentido com --reproduzir.")

    meta = dict(formato=None, n_amostras=None, n_pre=None, cod_zero=COD_ZERO,
                lsb_por_v=args.lsb_por_v, registro=None, bytes_registro=None, descricao=args.descricao,
                origem="arquivo" if args.reproduzir else (f"udp:{args.udp}" if args.udp else args.porta),
                inicio=time.strftime("%Y-%m-%d %H:%M:%S"), dt_us=None, tick_s=None,
                polaridade=None, log2_media=None, eventos=0, duracao_s=0.0, ts_ultimo_s=0.0,
                tempo_vivo_s=0.0, pacotes_invalidos=0, bytes_descartados=0, concluido=False)

    def salvar_meta():
        with open(args.saida + ".json", "w") as fj:
            json.dump(meta, fj, indent=2, ensure_ascii=False)

    dec = Decodificador()
    un_ts, un_viva = Desembrulhador(), Desembrulhador()
    painel = Painel(args.eventos, args.lsb_por_v)
    est = dict(n=0, n_lote=0, ts0=None, viva0=None, ts_s=0.0, viva_s=0.0, chave=None, info="aguardando eventos",
               t_pc=None, ts_ant=None, ignorados=0, lote=None)
    limite_s = args.tempo_max_h * 3600 + args.tempo_max_s if (args.tempo_max_h > 0 or args.tempo_max_s > 0) else float("inf")
    alvo_fluxo = args.amostras or (10_000_000 if limite_s == float("inf") else 0)
    fl = dict(ativo=False, cont=ContadorFluxo(), amostras=0, lacunas=[], n=None, flags=None, t_ini=None,
              cfg=None, fim=False)

    # ---- origem dos bytes ----
    ser = sk = arq = None
    if args.reproduzir:
        arq = open(args.reproduzir, "rb")
        print(f"Reproduzindo {args.reproduzir} -> {args.saida}.dat")
    if not args.reproduzir and (not args.udp or comandos):
        try:
            import serial
        except ImportError:
            sys.exit("[ERRO] pyserial não instalado (pip install pyserial).")
        ser = serial.Serial(args.porta, args.baud, timeout=0.1)
        ser.reset_input_buffer()
    if args.udp and not args.reproduzir:
        sk = abrir_udp(args.udp)
    if comandos:
        try:
            st, cfg_st = enviar(ser, comandos + [("status", 0)], dec=None if args.udp else dec)
        except RuntimeError as e:
            sys.exit(f"[ERRO] {e}")
        print("Configuração no FPGA:\n" + texto_status(st, cfg_st))
        meta["status_fpga"] = st
        fl["cfg"] = cfg_st
        if st["modo"] == 2 and not args.udp:
            sys.exit("[ERRO] o modo contínuo só sai por UDP: acrescente --udp.")
        if st["modo"] != 2 and bool(st["saida"]) != bool(args.udp):
            sys.exit(f"[ERRO] o FPGA está enviando por {'UDP' if st['saida'] else 'UART'}, mas o leitor vai ler "
                     f"{'UDP' if args.udp else 'a serial'}. Acrescente saida={'udp' if args.udp else 'uart'} ao --config.")
    if args.udp and ser is not None:
        ser.close()
        ser = None
    if sk is not None:
        print(f"[UDP porta {args.udp}] -> {args.saida}.dat  (Ctrl+C encerra)")
    elif ser is not None:
        print(f"[{args.porta}] {args.baud} baud -> {args.saida}.dat  (Ctrl+C encerra)")
    print(f"Escala: {args.lsb_por_v:.0f} LSB/V\n")

    salvar_meta()
    fdat = open(args.saida + ".dat", "wb")
    fbin = open(args.saida + ".bin", "wb") if (args.salvar_bruto and not args.reproduzir) else None
    t0 = time.time()
    t_painel = 0.0

    def ler():
        """Devolve (bytes para o decodificador, cada pedaço é um pacote inteiro?, datagramas de fluxo)."""
        if arq is not None:
            return arq.read(1 << 16), False, []
        if sk is not None:
            dgs = ler_udp(sk)
            fluxo = [d for d in dgs if eh_fluxo(d)]
            return b"".join(d for d in dgs if not eh_fluxo(d)), True, fluxo
        return ser.read(max(1, ser.in_waiting)), False, []

    def processar_fluxo(dgs):
        """Datagramas do fluxo contínuo (formato do freeMCA): grava as amostras corridas."""
        if est["chave"] is not None and not fl["ativo"]:
            est["ignorados"] += len(dgs)          # o arquivo já é de eventos
            return
        if not fl["ativo"]:
            seq, n, flags = cab_fluxo(dgs[0])
            fl.update(ativo=True, n=n, flags=flags & (FLUXO_EMPACOTADO | FLUXO_OFFSET), t_ini=time.time())
            est["chave"] = ("fluxo",)
            meta.update(formato="mca_fluxo_v1", registro="uint16 corrido: código do ADC (8192 = 0 V)",
                        bytes_registro=2, amostras_por_pacote=n)
            salvar_meta()
        tam = len(dgs[0])
        iguais = [d for d in dgs if len(d) == tam and cab_fluxo(d)[1] == fl["n"]
                  and cab_fluxo(d)[2] & (FLUXO_EMPACOTADO | FLUXO_OFFSET) == fl["flags"]]
        est["ignorados"] += len(dgs) - len(iguais)
        if not iguais:
            return
        for d in iguais:
            seq, _, flags = cab_fluxo(d)
            falta = fl["cont"].ver(seq, flags)
            if falta and len(fl["lacunas"]) < 1000:      # posição (em amostras gravadas) de cada descontinuidade
                fl["lacunas"].append([fl["amostras"], falta])
            fl["amostras"] += fl["n"]
        bloco = np.frombuffer(b"".join(iguais), dtype=np.uint8).reshape(len(iguais), tam)
        am = desempacotar_fluxo(bloco[:, CAB_FLUXO:], fl["n"], fl["flags"])
        if alvo_fluxo and fl["amostras"] >= alvo_fluxo:
            sobra = fl["amostras"] - alvo_fluxo
            am = am.reshape(-1)[:am.size - sobra]
            fl["amostras"] = alvo_fluxo
            fl["fim"] = True
        fdat.write(am.tobytes())

    def linha_fluxo(t_real):
        c = fl["cont"]
        dur = max(time.time() - (fl["t_ini"] or time.time()), 1e-9)
        sys.stdout.write(f"\rfluxo: {fl['amostras'] / 1e6:9.3f} M amostras | {fl['amostras'] / dur / 1e6:7.3f} MSPS recebidos | "
                         f"pacotes {c.pacotes} | perdidos {c.perdidos} | overflow {c.overflow}   ")
        sys.stdout.flush()

    def descarregar():
        if est["n_lote"]:
            fdat.write(est["lote"][:est["n_lote"]].tobytes())
            fdat.flush()
            est["n_lote"] = 0

    def definir_formato(pk):
        """O primeiro evento decide o formato do arquivo."""
        c = decodificar_cfg(pk[1])
        est["c"] = c
        meta.update(dt_us=c["dt_us"], tick_s=c["dt_us"] * 1e-6, polaridade=c["polaridade"],
                    log2_media=c["log2_media"], protocolo=c["versao"])
        pol = "+" if c["polaridade"] > 0 else "-"
        if pk[0] == "forma":
            n, n_pre = len(pk[4]), pk[5]
            dt = dtype_reg(n)
            meta.update(formato="mca_ad9245_v2", n_amostras=n, n_pre=n_pre,
                        registro=f"ts:<u8, viva:<u8, amostras:<u2[{n}]")
            est["info"] = (f"formas: dt={c['dt_us'] * 1000:.0f} ns, {n} amostras ({c['dt_us'] * n:.0f} us), "
                           f"trigger na {n_pre}, pol={pol}")
        else:
            dt = DTYPE_PICO
            st = dec.status or {}
            st = meta.get("status_fpga") or st
            trap = bool(pk[4]["flags"] & FLAG_TRAPEZIO)
            meta.update(formato="mca_picos_v1", n_pre=st.get("n_pre"), n_pos=st.get("n_pos"),
                        filtro_trapezio=trap,
                        registro="ts:<u8, viva:<u8, pico4:<u2, base:<u2, area:<i4, tpico:<u2, flags:u1")
            est["info"] = f"picos: dt={c['dt_us'] * 1000:.0f} ns, pol={pol}"
            if trap:
                est["info"] += ", altura pelo filtro trapezoidal"
                anotar_trapezio(st)
        meta["bytes_registro"] = dt.itemsize
        est["lote"] = np.zeros(2000, dtype=dt)
        salvar_meta()

    def anotar_trapezio(st):
        """Guarda no .json os parâmetros do trapézio (vêm do pacote de status)."""
        if st and "trap_k" in st and est.get("c"):
            dt = est["c"]["dt_us"]
            meta["trapezio"] = dict(k=st["trap_k"], m=st["trap_m"], pz=st["trap_pz"], sh=st["trap_sh"],
                                    subida_us=st["trap_k"] * dt, topo_us=st["trap_m"] * dt,
                                    tau_us=round(float(tau_do_pz(st["trap_pz"], dt)), 3),
                                    escala=escala_trapezio(st))

    def processar(pacotes, t_pc=None):
        """t_pc: relógio do PC na chegada do lote (None na reprodução). Só serve para contar
        voltas inteiras do contador de 32 bits quando passa mais de uma volta sem eventos."""
        for pk in pacotes:
            if pk[0] == "status":
                meta["status_fpga"] = pk[2]
                continue
            if est["n"] >= args.eventos:
                break
            if pk[0] == "forma":
                chave = (pk[0], pk[1], len(pk[4]), pk[5])
            else:                                         # pico: com e sem trapézio não se misturam
                chave = (pk[0], pk[1], pk[4]["flags"] & FLAG_TRAPEZIO, 0)
            if est["chave"] is None:
                est["chave"] = chave
                definir_formato(pk)
            elif chave != est["chave"]:
                est["ignorados"] += 1        # configuração mudou no meio da captura
                continue
            c = est["c"]
            ts, viva = pk[2], pk[3]
            esperado = None
            if t_pc is not None and est["t_pc"] is not None:
                esperado = (t_pc - est["t_pc"]) / (c["dt_us"] * 1e-6)
            ts_u = un_ts(ts, esperado)
            # entre dois pacotes o tempo vivo avança o mesmo que o timestamp menos o tempo morto
            viva_u = un_viva(viva, None if est["ts_ant"] is None else ts_u - est["ts_ant"])
            est["t_pc"], est["ts_ant"] = t_pc, ts_u
            if est["ts0"] is None:
                est["ts0"], est["viva0"] = ts_u, viva_u
            if pk[0] == "forma":
                est["lote"][est["n_lote"]] = (ts_u, viva_u, pk[4])
                painel.adicionar(altura_pico_lsb(pk[4], c["dt_us"], c["polaridade"], n=len(pk[4]), n_pre=pk[5]))
            else:
                m = pk[4]
                est["lote"][est["n_lote"]] = (ts_u, viva_u, m["pico4"], m["base"], m["area"], m["tpico"], m["flags"])
                painel.adicionar(m["pico4"] / 4.0)
            est["n_lote"] += 1
            est["n"] += 1
            est["ts_s"] = (ts_u - est["ts0"]) * c["dt_us"] * 1e-6
            est["viva_s"] = (viva_u - est["viva0"]) * c["dt_us"] * 1e-6
            if est["n_lote"] == est["lote"].size:
                descarregar()

    motivo = "alvo atingido"
    try:
        while est["n"] < args.eventos and not fl["fim"]:
            if time.time() - t0 > limite_s:
                motivo = "tempo máximo"
                break
            dados, inteiros, dg_fluxo = ler()
            agora = time.time()
            if dg_fluxo:
                processar_fluxo(dg_fluxo)
            if not dados and dg_fluxo:
                pass
            elif not dados:
                if args.reproduzir:
                    processar(dec.alimentar(b"", final=True, tudo=True))
                    motivo = "fim do arquivo"
                    break
                # silêncio (timeout): libera o último pacote completo, que normalmente espera o
                # cabeçalho do seguinte, para ele ser gravado e datado na hora certa
                processar(dec.alimentar(b"", final=True, tudo=True), agora)
            else:
                if fbin:
                    fbin.write(dados)
                processar(dec.alimentar(dados, final=inteiros, tudo=True), None if args.reproduzir else agora)
            if agora - t_painel > 0.5:
                if fl["ativo"]:
                    linha_fluxo(agora - t0)
                else:
                    painel.mostrar(est["n"], agora - t0, est["ts_s"], est["viva_s"], dec, est["info"])
                t_painel = agora
    except KeyboardInterrupt:
        motivo = "interrompido pelo usuário"
    finally:
        descarregar()
        fdat.close()
        if fbin:
            fbin.close()
        for f in (arq, ser, sk):
            if f is not None:
                f.close()
        dur = time.time() - t0
        n, ts_s, viva_s = est["n"], est["ts_s"], est["viva_s"]
        if fl["ativo"]:
            linha_fluxo(dur)
            c = fl["cont"]
            cfg_fl = fl["cfg"] if fl["cfg"] is not None else dec.cfg_status
            dur_fl = max(time.time() - fl["t_ini"], 1e-9)
            if cfg_fl is not None:                       # passo informado pelo status do FPGA
                dt_us, estimado = decodificar_cfg(cfg_fl)["dt_us"], False
            else:                                        # sem status: taxa medida, arredondada a 25 MSPS / 2^k
                taxa = (c.pacotes + c.perdidos) * fl["n"] / dur_fl / 1e6
                k = min(range(5), key=lambda i: abs(np.log(max(taxa, 1e-3) / (25.0 / (1 << i)))))
                dt_us, estimado = (1 << k) * T_ADC_US, True
            meta.update(amostras=fl["amostras"], dt_us=dt_us, tick_s=dt_us * 1e-6, taxa_msps=1.0 / dt_us,
                        dt_estimado=estimado, taxa_recebida_msps=round(fl["amostras"] / dur_fl / 1e6, 4),
                        pacotes=c.pacotes, pacotes_perdidos=c.perdidos, lacunas=fl["lacunas"],
                        pacotes_com_overflow=c.overflow, reinicios_do_fluxo=c.reinicios)
            if alvo_fluxo and fl["fim"]:
                motivo = "número de amostras atingido"
        else:
            painel.mostrar(n, dur, ts_s, viva_s, dec, est["info"])
        if meta.get("filtro_trapezio"):
            if "trapezio" not in meta:
                anotar_trapezio(meta.get("status_fpga"))
            if "trapezio" not in meta:
                print("\nAVISO: eventos medidos pelo filtro trapezoidal, mas nenhum status do FPGA chegou, então a "
                      "escala não foi gravada. Na próxima vez use --config status (ou outros comandos); "
                      "na análise, informe --escala_trap.")
        meta.update(eventos=n, duracao_s=round(dur, 3), ts_ultimo_s=ts_s, tempo_vivo_s=viva_s,
                    pacotes_invalidos=dec.invalidos, bytes_descartados=dec.descartados,
                    eventos_ignorados=est["ignorados"],
                    fim=time.strftime("%Y-%m-%d %H:%M:%S"), motivo=motivo, concluido=True)
        salvar_meta()
        if fl["ativo"]:
            c = fl["cont"]
            print(f"\n[{motivo.upper()}] {fl['amostras']} amostras ({fl['amostras'] * meta['dt_us'] / 1e6:.3f} s de sinal a "
                  f"{meta['taxa_msps']:.4g} MSPS{', taxa estimada' if meta['dt_estimado'] else ''})")
            if c.perdidos or c.overflow or c.reinicios:
                print(f"AVISO: {c.perdidos} pacotes perdidos em {c.lacunas} lacunas, {c.overflow} com overflow na FPGA, "
                      f"{c.reinicios} reinícios do fluxo. As posições estão em 'lacunas' no .json.")
        else:
            print(f"\n[{motivo.upper()}] {n} eventos em {dur / 3600:.2f} h")
        if est["ignorados"]:
            print(f"AVISO: {est['ignorados']} eventos ignorados por terem outra configuração "
                  f"(formato, janela ou passo mudou durante a captura).")
        if n == 0 and sk is not None and not fl["ativo"]:
            print("Nenhum datagrama chegou. Confira: enlace de 1 Gbit/s, IP do PC na rede 192.168.1.x, "
                  f"firewall liberando a porta UDP {args.udp}, e saida=udp no firmware configurável.")
        if viva_s > 0:
            print(f"Tempo vivo: {viva_s:.1f} s de {ts_s:.1f} s ({100 * viva_s / max(ts_s, 1e-9):.1f}%)"
                  f" -> taxa real {n / viva_s:.1f} cps")
        print(f"Arquivos: {args.saida}.dat, {args.saida}.json" + (f", {args.saida}.bin" if fbin else ""))


if __name__ == "__main__":
    main()
