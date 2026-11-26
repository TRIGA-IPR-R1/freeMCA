#!/usr/bin/env python3
"""
espectrometria_mca.py - Espectro de altura de pulso a partir das capturas do MCA.

Entrada:
  <prefixo>.dat + <prefixo>.json   (leitor_adc.py novo; recomendado)
  arquivo .csv antigo              (colunas 'Canal_A_Dec' ou 'Canal_A (V)', use --amostras_evento)

Processamento por evento:
  1. linha de base = média do pré-trigger (até --base_ate_us antes do trigger); rejeita se
     o pré-trigger não estiver limpo (desvio padrão alto ou pulso dentro dele)
  2. pulso = polaridade x (amostras - base); espículas estreitas (< ~0,6 us) são detectadas
     contra uma mediana móvel de ~1,2 us e só essas amostras são substituídas
  3. altura:  'pico' = máximo do pulso suavizado (3 pontos) com interpolação parabólica
              'area' = integral numa janela curta (no modo bipolar, só o lóbulo positivo)
              'trap' = filtro trapezoidal de Jordanov-Knoll com polo-zero; para a saída DIRETA
                       do pré-amplificador (subida rápida + cauda exponencial), não para a saída
                       de um amplificador formatador (571/572/590)
  4. rejeita pile-up (segundo pulso na janela) e saturação
Histograma em faixa FIXA, ajuste gaussiano + fundo linear nos picos,
taxa real pelo tempo vivo medido no FPGA.

Exemplos:
  python espectrometria_mca.py --arquivo th_longa --bins 2048 --log --fit
  python espectrometria_mca.py --arquivo th_longa --picos 0.24 0.58 0.91 --range 0 2.5
  python espectrometria_mca.py --arquivo antigo.csv --amostras_evento 200 --lsb_por_v 1638
  python espectrometria_mca.py --arquivo th_bipolar --modo bi            # saída bipolar do amplificador
  python espectrometria_mca.py --arquivo th_lento --base_ate_us 6 --janela_us 40   # shaping longo
  python espectrometria_mca.py --arquivo cs_pre --metodo trap --trap_subida_us 2 --trap_topo_us 1
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mca_comum import (COD_MAX, COD_ZERO, DTYPE_PICO, FLAG_PILEUP, FLAG_SATUROU, FLAG_TRAPEZIO, estimar_tau_us, janelas, jordanov, remover_espiculas,
                       suaviza3)


# =============================================================================
# Leitura
# =============================================================================
def abrir_entrada(caminho, args):
    """Devolve (gerador de blocos (amostras uint16 [n, N], ts ou None), meta)."""
    base, ext = os.path.splitext(caminho)
    if ext.lower() == ".csv":
        return _blocos_csv(caminho, args), dict(n_amostras=args.amostras_evento,
                                                 n_pre=args.n_pre if args.n_pre else 49,
                                                 dt_us=0.2, lsb_por_v=None, tick_s=200e-9,
                                                 polaridade=1)
    if ext.lower() in ("", ".dat", ".json"):
        caminho_dat, caminho_json = base + ".dat", base + ".json"
    else:
        sys.exit(f"[ERRO] extensão não reconhecida: {ext}")
    if not os.path.exists(caminho_dat):
        sys.exit(f"[ERRO] não achei {caminho_dat}")
    meta = {}
    if os.path.exists(caminho_json):
        with open(caminho_json) as fj:
            meta = json.load(fj)
    picos = str(meta.get("formato", "")).startswith("mca_picos")
    N = int(meta.get("n_amostras") or 200)
    dtype = DTYPE_PICO if picos else np.dtype([("ts", "<u8"), ("viva", "<u8"), ("amostras", "<u2", (N,))])
    mm = np.memmap(caminho_dat, dtype=dtype, mode="r")
    meta["_picos"] = picos
    if not meta.get("n_pre"):
        meta["n_pre"] = 49
    meta.setdefault("n_pre", 49)
    if not meta.get("dt_us"):
        meta["dt_us"] = 0.2                       # arquivos do formato v1
    meta["tick_s"] = meta["dt_us"] * 1e-6
    if not meta.get("polaridade"):
        meta["polaridade"] = 1
    meta["n_amostras"] = N
    meta["_memmap"] = mm
    return (_blocos_picos(mm, args.bloco) if picos else _blocos_dat(mm, args.bloco)), meta


def _blocos_picos(mm, bloco):
    """Arquivo do modo 'picos' do mca_ad9245_cfg.v: o bloco é o próprio registro."""
    for i in range(0, len(mm), max(bloco, 100000)):
        r = np.asarray(mm[i:i + max(bloco, 100000)])
        yield r, r["ts"]


def _blocos_dat(mm, bloco):
    for i in range(0, len(mm), bloco):
        r = mm[i:i + bloco]
        yield np.asarray(r["amostras"]), np.asarray(r["ts"])


def _blocos_csv(caminho, args):
    import pandas as pd
    N = args.amostras_evento
    linhas_bloco = N * max(1, args.bloco // 4)
    resto = None
    for df in pd.read_csv(caminho, sep=";", chunksize=linhas_bloco):
        if "Canal_A_Dec" in df.columns:
            v = df["Canal_A_Dec"].to_numpy(np.int64)
        elif "Canal_A (V)" in df.columns:
            v = np.round(df["Canal_A (V)"].to_numpy() * 1638.0 + COD_ZERO).astype(np.int64)
        else:
            sys.exit(f"[ERRO] colunas: {list(df.columns)}")
        if resto is not None:
            v = np.concatenate([resto, v])
        n = len(v) // N
        resto = v[n * N:]
        if n:
            yield v[:n * N].reshape(n, N).astype(np.uint16), None


# =============================================================================
# Processamento de um bloco de eventos
# =============================================================================
def processar_picos(r, p):
    """Registros já medidos no FPGA (modo picos). Mesma saída de processar_bloco."""
    n = len(r)
    nada = np.zeros(n, dtype=bool)
    # escala do campo pico4: 4 contagens/LSB (pico 1-2-1) ou a do filtro trapezoidal
    esc = np.where(r["flags"] & FLAG_TRAPEZIO, p.get("escala_trap", 4.0), 4.0)
    if p["metodo"] == "area":
        altura = r["area"].astype(np.float64) * p["dt_us"]
    else:
        altura = r["pico4"].astype(np.float64) / esc
    rej_pile = (r["flags"] & FLAG_PILEUP) != 0 if p["rejeitar_pileup"] else nada
    rej_sat = (r["flags"] & FLAG_SATUROU) != 0
    rej_vazio = r["pico4"] < esc * 0.8 * p["limiar_lsb"]
    return dict(altura=altura, rej_base=nada, rej_pile=rej_pile, rej_sat=rej_sat, rej_espic=nada,
                rej_vazio=rej_vazio, espic=nada, base=r["base"].astype(np.float32))


def processar_bloco(a, p):
    """a: (n, N) códigos. Devolve dict com altura (LSB ou LSB.us) e máscaras de rejeição."""
    if p.get("picos"):
        return processar_picos(a, p)
    x = a.astype(np.float32)
    n_base, ini, fim = p["n_base"], p["ini"], p["fim"]
    pre = x[:, :n_base]
    base = pre.mean(axis=1)
    std_base = pre.std(axis=1)
    y = p["pol"] * (x - base[:, None])

    # espículas: amostras que fogem da mediana larga (~1,2 us) são substituídas por ela
    n_espic = np.zeros(len(a), dtype=bool)
    if p["filtro_espiculas"]:
        y, esp = remover_espiculas(y, p["dt_us"], p["limiar_lsb"])
        n_espic = esp[:, ini:fim].any(axis=1)
    s = suaviza3(y)
    lim = p["limiar_lsb"]

    rej_base = (std_base > p["max_std_base"]) | (np.abs(s[:, 2:n_base - 1]).max(axis=1) > lim)
    rej_sat = ((a[:, ini:fim] >= COD_MAX) | (a[:, ini:fim] == 0)).any(axis=1)
    rej_espic = n_espic & p["rejeitar_espiculas"]

    trap = None
    if p["metodo"] == "trap":
        if p["tau_us"] is None:                   # estima no primeiro bloco, com eventos limpos
            limpos = ~rej_base & (s[:, ini:fim].max(axis=1) > 3 * lim)
            tau = estimar_tau_us(y[limpos][:20000], p["dt_us"], ini) if limpos.sum() >= 20 else None
            if tau is None:
                sys.exit("\n[ERRO] não consegui estimar a cauda dos pulsos; informe --tau_us.")
            p["tau_us"] = tau
            print(f"\n  tau estimado da cauda: {tau:.2f} us (use --tau_us para fixar)")
        trap = jordanov(y, p["trap_k"], p["trap_m"], p["tau_us"], p["dt_us"])
        fim_t = p["fim_trap"]
        # sinal para o pile-up: trapézio curto (triângulo) -> um pico estreito por pulso,
        # mesmo quando o segundo pulso cai na cauda do primeiro
        s_pile, fim_pile = jordanov(y, p["trap_kr"], 0, p["tau_us"], p["dt_us"]), fim_t
    else:
        s_pile, fim_pile = s, x.shape[1]

    # pile-up: subidas acima do limiar (com histerese) da janela até o fim
    rej_pile = np.zeros(len(a), dtype=bool)
    if p["rejeitar_pileup"]:
        acima = np.zeros(len(a), dtype=bool)
        subidas = np.zeros(len(a), dtype=np.int16)
        for k in range(ini, fim_pile):
            novo = (s_pile[:, k] >= lim) | (acima & (s_pile[:, k] > lim / 2))
            subidas += (novo & ~acima)
            acima = novo
        rej_pile = subidas > 1

    janela = s[:, ini:fim]
    r = np.arange(len(a))
    k = janela.argmax(axis=1)
    y0 = janela[r, k]
    km = np.clip(k - 1, 0, janela.shape[1] - 1)
    kp = np.clip(k + 1, 0, janela.shape[1] - 1)
    ym_, yp_ = janela[r, km], janela[r, kp]
    den = ym_ - 2 * y0 + yp_
    ok = (den < 0) & (k > 0) & (k < janela.shape[1] - 1)
    delta = np.where(ok, 0.5 * (ym_ - yp_) / np.where(ok, den, 1), 0.0)
    h_pico = y0 - 0.25 * (ym_ - yp_) * delta
    # disparo sem pulso real (ex.: espícula que a mediana removeu): pico filtrado abaixo do limiar
    rej_vazio = h_pico < 0.8 * lim
    if p["metodo"] == "pico":
        altura = h_pico
    elif p["metodo"] == "trap":
        altura = trap[:, ini:fim_t].max(axis=1)           # topo do trapézio
    elif p["modo"] == "bi":
        # bipolar: integra só o lóbulo positivo (do início da janela até cruzar zero após o pico)
        idx = np.arange(janela.shape[1])[None, :]
        depois = (idx > k[:, None]) & (janela <= 0)
        fim_lobo = np.where(depois.any(axis=1), depois.argmax(axis=1), janela.shape[1])
        dentro = idx < fim_lobo[:, None]
        altura = (y[:, ini:fim] * dentro).sum(axis=1) * p["dt_us"]
    else:
        altura = y[:, ini:fim].sum(axis=1) * p["dt_us"]

    return dict(altura=altura.astype(np.float64), rej_base=rej_base, rej_pile=rej_pile,
                rej_sat=rej_sat, rej_espic=rej_espic, rej_vazio=rej_vazio, espic=n_espic, base=base)


# =============================================================================
# Ajuste de picos
# =============================================================================
def gauss_fundo(x, a, mu, sig, b0, b1):
    return a * np.exp(-0.5 * ((x - mu) / sig) ** 2) + b0 + b1 * (x - mu)


def ajustar_pico(centros, cont, x0, sig0, larg_bin):
    from scipy.optimize import curve_fit
    sel = np.abs(centros - x0) <= max(4 * sig0, 6 * larg_bin)
    if sel.sum() < 8:
        return None
    xs, ys = centros[sel], cont[sel].astype(float)
    b0 = float(min(ys[:3].mean(), ys[-3:].mean()))
    p0 = [max(ys.max() - b0, 1.0), xs[np.argmax(ys)], sig0, b0, 0.0]
    lim_inf = [0, xs[0], larg_bin * 0.5, -np.inf, -np.inf]
    lim_sup = [np.inf, xs[-1], 4 * sig0 + 10 * larg_bin, np.inf, np.inf]
    try:
        popt, pcov = curve_fit(gauss_fundo, xs, ys, p0=p0, bounds=(lim_inf, lim_sup),
                               sigma=np.sqrt(np.maximum(ys, 1.0)), absolute_sigma=True, maxfev=20000)
    except Exception:
        return None
    perr = np.sqrt(np.diag(pcov))
    a, mu, sig = popt[:3]
    if not (xs[0] < mu < xs[-1]):
        return None
    fwhm = 2.3548 * abs(sig)
    return dict(mu=mu, mu_err=perr[1], sig=abs(sig), fwhm=fwhm,
                res=100 * fwhm / mu if mu > 0 else np.nan,
                area=a * abs(sig) * np.sqrt(2 * np.pi) / larg_bin, popt=popt, xs=xs)


def achar_picos(centros, cont, n_max=12):
    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import find_peaks
    h = gaussian_filter1d(cont.astype(float), 2)
    pk, prop = find_peaks(h, prominence=1)
    if len(pk) == 0:
        return []
    prom = prop["prominences"]
    signif = prom / np.sqrt(np.maximum(h[pk], 1.0))
    ok = (signif > 4) & (h[pk] > 10)
    pk, signif = pk[ok], signif[ok]
    ordem = np.argsort(signif)[::-1][:n_max]
    return sorted(centros[pk[ordem]].tolist())


# =============================================================================
def main():
    ap = argparse.ArgumentParser(description="MCA - espectro de altura de pulso")
    ap.add_argument("--arquivo", required=True, help="prefixo/arquivo .dat (com .json) ou .csv antigo")
    ap.add_argument("--escala_trap", type=float, default=0.0,
                    help="modo picos com o filtro da FPGA: contagens de pico4 por LSB (normalmente lida do .json)")
    ap.add_argument("--metodo", choices=["pico", "area", "trap"], default="pico",
                    help="trap = filtro trapezoidal (Jordanov-Knoll) para a saída direta do pré")
    ap.add_argument("--trap_subida_us", type=float, default=2.0, help="trap: subida do trapézio (us)")
    ap.add_argument("--trap_topo_us", type=float, default=1.0,
                    help="trap: topo plano (us); maior que o tempo de subida do pulso do pré")
    ap.add_argument("--tau_us", default="auto",
                    help="trap: constante de decaimento do pré (us), 'inf' ou 'auto' (estima dos pulsos)")
    ap.add_argument("--modo", choices=["uni", "bi"], default="uni",
                    help="saída do amplificador: unipolar ou bipolar (bi: área só do lóbulo positivo)")
    ap.add_argument("--polaridade", choices=["auto", "pos", "neg"], default="auto",
                    help="auto = a do firmware (registrada no .json)")
    ap.add_argument("--bins", type=int, default=1024)
    ap.add_argument("--range", type=float, nargs=2, default=None, metavar=("MIN", "MAX"),
                    help="faixa FIXA do histograma (na unidade de saída). Padrão: 0 até o p99,95 x 1,05")
    ap.add_argument("--unidade", choices=["V", "lsb"], default="V")
    ap.add_argument("--lsb_por_v", type=float, default=None, help="padrão: valor do .json ou 1638")
    ap.add_argument("--janela_us", type=float, default=10.0,
                    help="janela de busca do pico / integração após o trigger (us)")
    ap.add_argument("--base_ate_us", type=float, default=1.3,
                    help="a linha de base usa o pré-trigger até este tempo antes do trigger (us)")
    ap.add_argument("--pre_janela_us", type=float, default=0.8,
                    help="a janela do pulso começa este tempo antes do trigger (us)")
    ap.add_argument("--sem_filtro_espiculas", action="store_true",
                    help="desliga a remoção de espículas")
    ap.add_argument("--rejeitar_espiculas", action="store_true",
                    help="descarta eventos com espícula (padrão: corrige pela mediana e conta)")
    ap.add_argument("--max_std_base", type=float, default=8.0, help="desvio padrão máx. do pré-trigger (LSB)")
    ap.add_argument("--limiar_lsb", type=float, default=82.0,
                    help="limiar p/ detectar pulso no pré-trigger e pile-up (LSB); ~ o do FPGA")
    ap.add_argument("--sem_rejeicao_pileup", action="store_true")
    ap.add_argument("--fit", action="store_true", help="acha e ajusta picos automaticamente")
    ap.add_argument("--picos", type=float, nargs="*", default=[], help="posições aproximadas a ajustar")
    ap.add_argument("--log", action="store_true", help="eixo de contagens em escala log")
    ap.add_argument("--amostras_evento", type=int, default=200, help="só p/ CSV antigo")
    ap.add_argument("--n_pre", type=int, default=0, help="amostras de pré-trigger (padrão do arquivo: 49)")
    ap.add_argument("--max_eventos", type=int, default=0, help="processa só os N primeiros (0 = todos)")
    ap.add_argument("--bloco", type=int, default=200_000)
    ap.add_argument("--saida", default=None, help="prefixo dos arquivos de saída")
    ap.add_argument("--sem_mostrar", action="store_true")
    args = ap.parse_args()

    blocos, meta = abrir_entrada(args.arquivo, args)
    n_pre = args.n_pre or int(meta["n_pre"])
    lsb_por_v = args.lsb_por_v or meta.get("lsb_por_v") or 1638.0
    dt_us = float(meta["dt_us"])
    pol = {"pos": 1, "neg": -1}.get(args.polaridade, int(meta.get("polaridade") or 1))
    n_base, ini, fim = janelas(dt_us, args.base_ate_us, args.pre_janela_us, args.janela_us,
                               n=int(meta["n_amostras"]), n_pre=n_pre)
    p = dict(n_base=n_base, ini=ini, fim=fim, pol=pol, modo=args.modo,
             limiar_lsb=args.limiar_lsb, max_std_base=args.max_std_base, metodo=args.metodo,
             rejeitar_pileup=not args.sem_rejeicao_pileup, dt_us=dt_us,
             filtro_espiculas=not args.sem_filtro_espiculas, rejeitar_espiculas=args.rejeitar_espiculas)

    p["picos"] = bool(meta.get("_picos"))
    if p["picos"]:
        if args.metodo == "trap":
            sys.exit("[ERRO] arquivo do modo 'picos': só há a medida feita no FPGA (use --metodo pico ou area).")
        print("Arquivo do modo 'picos': altura e área medidas no FPGA; as opções de janela, base e "
              "espículas não se aplicam.")
        if meta.get("filtro_trapezio"):
            tz = meta.get("trapezio") or {}
            if args.escala_trap:
                p["escala_trap"] = args.escala_trap
            elif "escala" in tz:
                p["escala_trap"] = tz["escala"]
            else:
                sys.exit("[ERRO] alturas do filtro trapezoidal sem a escala no .json; informe --escala_trap "
                         "(mca_config.py mostra o valor em 'contagens/LSB').")
            print(f"Altura pelo filtro trapezoidal da FPGA: subida {tz.get('subida_us', '?')} us, topo "
                  f"{tz.get('topo_us', '?')} us, tau {tz.get('tau_us', '?')} us; escala {p['escala_trap']:.4f} "
                  f"contagens/LSB")
    if args.metodo == "trap":
        N = int(meta["n_amostras"])
        p["trap_k"] = max(1, int(round(args.trap_subida_us / dt_us)))
        p["trap_m"] = max(1, int(round(args.trap_topo_us / dt_us)))
        p["trap_kr"] = max(2, int(round(0.5 / dt_us)))
        p["tau_us"] = None if args.tau_us == "auto" else float(args.tau_us)
        fim_ideal = n_pre + p["trap_k"] + p["trap_m"] + 4
        p["fim_trap"] = min(N, fim_ideal)
        if fim_ideal > N:
            sys.exit(f"[ERRO] trapézio não cabe no registro: subida + topo = "
                     f"{(p['trap_k'] + p['trap_m']) * dt_us:.1f} us, mas só há {(N - n_pre) * dt_us:.1f} us "
                     f"após o trigger. Reduza --trap_subida_us/--trap_topo_us ou aumente LOG2_MEDIA.")
        print(f"Trapézio: subida {p['trap_k'] * dt_us:.2f} us ({p['trap_k']} am.) | topo "
              f"{p['trap_m'] * dt_us:.2f} us ({p['trap_m']} am.) | tau {args.tau_us}")
    print(f"Arquivo: {args.arquivo} | método {args.metodo} | modo {args.modo} | "
          f"polaridade {'+' if pol > 0 else '-'} | dt {dt_us * 1000:.0f} ns | {lsb_por_v:.0f} LSB/V")
    print(f"Janelas: base = amostras [0,{n_base}) | pulso = [{ini},{fim}) "
          f"({(ini - n_pre) * dt_us:+.1f} a {(fim - n_pre) * dt_us:+.1f} us do trigger)")

    alturas, n_tot = [], 0
    n_rbase = n_pile = n_sat = n_esp = n_esp_rej = n_vazio = 0
    ts_ini = ts_fim = None
    bases = []
    for a, ts in blocos:
        if args.max_eventos and n_tot >= args.max_eventos:
            break
        if args.max_eventos:
            a = a[:args.max_eventos - n_tot]
            ts = ts[:len(a)] if ts is not None else None
        r = processar_bloco(a, p)
        bom = ~(r["rej_base"] | r["rej_pile"] | r["rej_sat"] | r["rej_espic"] | r["rej_vazio"])
        alturas.append(r["altura"][bom])
        bases.append(r["base"][::50])
        n_rbase += int(r["rej_base"].sum())
        n_pile += int((r["rej_pile"] & ~r["rej_base"]).sum())
        n_sat += int((r["rej_sat"] & ~r["rej_base"] & ~r["rej_pile"]).sum())
        n_esp += int(r["espic"].sum())
        n_vazio += int((r["rej_vazio"] & ~r["rej_base"]).sum())
        n_esp_rej += int((r["rej_espic"] & ~r["rej_base"] & ~r["rej_pile"] & ~r["rej_sat"]).sum())
        if ts is not None and len(ts):
            ts_ini = ts[0] if ts_ini is None else ts_ini
            ts_fim = ts[-1]
        n_tot += len(a)
        sys.stdout.write(f"\r  processados: {n_tot}")
        sys.stdout.flush()
    print()
    if n_tot == 0:
        sys.exit("[ERRO] nenhum evento.")

    alt = np.concatenate(alturas)
    if args.unidade == "V":
        alt = alt / lsb_por_v
        un = "V.us" if args.metodo == "area" else "V"
    else:
        un = "LSB.us" if args.metodo == "area" else "LSB"
    alt = alt[alt > 0]

    # ---- tempos e taxas ----
    mm = meta.get("_memmap")
    viva_s = real_s = None
    if mm is not None and len(mm) > 1:
        n_usado = min(n_tot, len(mm))
        viva_s = (int(mm["viva"][n_usado - 1]) - int(mm["viva"][0])) * meta["tick_s"]
        real_s = (int(mm["ts"][n_usado - 1]) - int(mm["ts"][0])) * meta["tick_s"]

    base_v = (np.concatenate(bases) - COD_ZERO) / lsb_por_v
    print("=" * 78)
    print(f"Eventos lidos: {n_tot} | válidos: {len(alt)} ({100 * len(alt) / n_tot:.1f}%)")
    print(f"Rejeitados: pré-trigger sujo {n_rbase} | pile-up {n_pile} | saturação {n_sat}"
          f" | disparo sem pulso {n_vazio}"
          + (f" | espículas {n_esp_rej}" if args.rejeitar_espiculas else ""))
    if n_rbase > 0.1 * n_tot:
        print(f"  >> ATENÇÃO: {100 * n_rbase / n_tot:.0f}% com pré-trigger sujo. Se os pulsos forem lentos "
              f"(shaping longo), a subida começa antes do trigger: aumente --base_ate_us "
              f"(ex. 2-3x o tempo de shaping) e --janela_us.")
    if p["filtro_espiculas"]:
        print(f"Eventos com espícula na janela: {n_esp} ({100 * n_esp / n_tot:.2f}%)"
              + ("" if args.rejeitar_espiculas else " -> corrigidos pela mediana"))
    print(f"Linha de base (absoluta): média {base_v.mean():+.4f} V, variação p1-p99 "
          f"{np.percentile(base_v, 1):+.4f} a {np.percentile(base_v, 99):+.4f} V")
    if viva_s:
        print(f"Tempo real {real_s:.1f} s | tempo vivo {viva_s:.1f} s ({100 * viva_s / real_s:.1f}%) | "
              f"taxa de trigger real {n_tot / viva_s:.1f} cps")

    # ---- histograma (faixa fixa) ----
    if args.range:
        faixa = tuple(args.range)
    else:
        faixa = (0.0, float(np.percentile(alt, 99.95) * 1.05))
    cont, bordas = np.histogram(alt, bins=args.bins, range=faixa)
    centros = 0.5 * (bordas[1:] + bordas[:-1])
    larg = bordas[1] - bordas[0]
    fora = int((alt > faixa[1]).sum())
    print(f"Histograma: {args.bins} canais em [{faixa[0]:.4g}, {faixa[1]:.4g}] {un} "
          f"({larg:.4g} {un}/canal) | acima da faixa: {fora}")

    # ---- picos ----
    alvos = list(args.picos)
    if args.fit:
        auto = achar_picos(centros, cont)
        # um "pico" colado no limiar é só o corte do trigger sobre um contínuo: não ajusta
        corte = 0.0
        if args.metodo != "area":
            corte = 1.4 * args.limiar_lsb / (lsb_por_v if args.unidade == "V" else 1.0)
        for x in auto:
            if x < corte:
                print(f"  (máximo em {x:.4g} {un} ignorado: está a menos de 1,4x do limiar de trigger; "
                      f"é o corte do limiar, não uma linha. Use --picos para forçar o ajuste.)")
            elif all(abs(x - y) > 5 * larg for y in alvos):
                alvos.append(x)
    ajustes = []
    for x0 in sorted(alvos):
        sig0 = max(0.03 * x0, 2 * larg)               # ~7 % FWHM como chute (NaI)
        r = ajustar_pico(centros, cont, x0, sig0, larg)
        if r:
            ajustes.append(r)
    if ajustes:
        print("-" * 78)
        print(f"{'centroide':>14} {'±':>8} {'FWHM':>10} {'R (%)':>7} {'área líquida':>14}")
        for r in ajustes:
            print(f"{r['mu']:14.5f} {r['mu_err']:8.5f} {r['fwhm']:10.5f} {r['res']:7.2f} {r['area']:14.0f}")
    print("=" * 78)

    # ---- saídas ----
    pref = args.saida or os.path.splitext(args.arquivo)[0] + f"_{args.metodo}_{args.bins}"
    np.savetxt(pref + "_espectro.csv", np.column_stack([np.arange(args.bins), centros, cont]),
               delimiter=";", header=f"canal;centro_{un};contagens", comments="", fmt=["%d", "%.6g", "%d"])
    with open(pref + "_resumo.txt", "w") as f:
        if args.metodo == "trap":
            f.write(f"trap_subida_us={p['trap_k'] * dt_us:.3f}\ntrap_topo_us={p['trap_m'] * dt_us:.3f}\n"
                    f"tau_us={p['tau_us']}\n")
        f.write(f"arquivo={args.arquivo}\nmetodo={args.metodo}\njanela_us={args.janela_us}\n"
                f"lsb_por_v={lsb_por_v}\neventos={n_tot}\nvalidos={len(alt)}\n"
                f"rej_base={n_rbase}\nrej_pileup={n_pile}\nrej_saturacao={n_sat}\n"
                f"espiculas={n_esp}\nrej_espiculas={n_esp_rej}\nrej_sem_pulso={n_vazio}\nmodo={args.modo}\npolaridade={pol}\n"
                f"dt_us={dt_us}\n")
        if viva_s:
            f.write(f"tempo_real_s={real_s:.3f}\ntempo_vivo_s={viva_s:.3f}\ntaxa_cps={n_tot / viva_s:.3f}\n")
        for r in ajustes:
            f.write(f"pico mu={r['mu']:.6g} err={r['mu_err']:.3g} fwhm={r['fwhm']:.6g} "
                    f"R%={r['res']:.3f} area={r['area']:.1f}\n")

    import matplotlib
    if args.sem_mostrar:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(13, 6.5))
    ax.step(centros, cont, where="mid", color="#4b3f9e", lw=0.8, label=f"Espectro ({args.bins} canais)")
    ax.fill_between(centros, cont, step="mid", color="#4b3f9e", alpha=0.25)
    cores = ["#d1495b", "#e08e0b", "#2e86ab", "#3a7d44", "#7a3e9d", "#222222"]
    for i, r in enumerate(ajustes):
        xs = np.linspace(r["xs"][0], r["xs"][-1], 300)
        ax.plot(xs, gauss_fundo(xs, *r["popt"]), color=cores[i % len(cores)], lw=1.8,
                label=f"{r['mu']:.4g} {un}  (R = {r['res']:.1f} %)")
    if args.log:
        ax.set_yscale("log")
        ax.set_ylim(bottom=0.8)
    ax.set_xlim(faixa)
    titulo = f"Espectro de altura de pulso - método {args.metodo}"
    if viva_s:
        titulo += f"  |  tempo vivo {viva_s / 3600:.2f} h, {n_tot / viva_s:.0f} cps"
    ax.set_title(titulo, fontsize=13)
    ax.set_xlabel(("Integral" if args.metodo == "area" else "Amplitude") + f" ({un})", fontsize=12)
    ax.set_ylabel("Contagens", fontsize=12)
    ax.grid(True, ls=":", alpha=0.6)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(pref + "_espectro.png", dpi=200)
    print(f"Saídas: {pref}_espectro.png | {pref}_espectro.csv | {pref}_resumo.txt")
    if not args.sem_mostrar:
        plt.show()


if __name__ == "__main__":
    main()
