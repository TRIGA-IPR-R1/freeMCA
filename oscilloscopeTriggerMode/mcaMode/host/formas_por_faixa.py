#!/usr/bin/env python3
"""
formas_por_faixa.py - Mostra a forma dos pulsos que caem em cada faixa do espectro.

Para cada faixa de amplitude (V) mostra: a forma média normalizada, exemplos de pulsos e
números que denunciam problemas:
  * tempo do pico após o trigger      -> janela de análise curta demais?
  * largura do topo (> 95 % do máximo) -> topo plano = saturação/corte
  * fração rejeitada por pré-trigger sujo e o ruído da linha de base

Uso:
  python formas_por_faixa.py --arquivo Th_1_milhao_eventos --faixas 0.09:0.11 0.16:0.18 0.30:0.34 0.82:0.87
  (aceita as mesmas opções de janela do espectrometria_mca.py: --janela_us, --base_ate_us ...)
Precisa do mca_comum.py e do espectrometria_mca.py na mesma pasta.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mca_comum import COD_ZERO, janelas, remover_espiculas
from espectrometria_mca import processar_bloco


def main():
    ap = argparse.ArgumentParser(description="Forma dos pulsos por faixa de amplitude")
    ap.add_argument("--arquivo", required=True, help="prefixo do .dat/.json")
    ap.add_argument("--faixas", nargs="+", required=True, help="faixas em V, ex. 0.16:0.18 0.82:0.87")
    ap.add_argument("--janela_us", type=float, default=10.0)
    ap.add_argument("--base_ate_us", type=float, default=1.3)
    ap.add_argument("--pre_janela_us", type=float, default=0.8)
    ap.add_argument("--max_std_base", type=float, default=8.0)
    ap.add_argument("--limiar_lsb", type=float, default=82.0)
    ap.add_argument("--max_eventos", type=int, default=300_000, help="eventos analisados (do início)")
    ap.add_argument("--exemplos", type=int, default=15)
    ap.add_argument("--sem_mostrar", action="store_true")
    a = ap.parse_args()

    base = os.path.splitext(a.arquivo)[0]
    with open(base + ".json") as f:
        meta = json.load(f)
    dt = float(meta.get("dt_us") or 0.2)
    pol = int(meta.get("polaridade") or 1)
    k = float(meta.get("lsb_por_v") or 1638.0)
    N = int(meta["n_amostras"])
    N_PRE = int(meta.get("n_pre") or 49)
    if str(meta.get("formato", "")).startswith("mca_picos"):
        sys.exit("[ERRO] este arquivo é do modo 'picos' (não tem as formas dos pulsos).")
    dtype = np.dtype([("ts", "<u8"), ("viva", "<u8"), ("amostras", "<u2", (N,))])
    mm = np.memmap(base + ".dat", dtype=dtype, mode="r")
    n = min(len(mm), a.max_eventos)
    amostras = np.asarray(mm["amostras"][:n])

    n_base, ini, fim = janelas(dt, a.base_ate_us, a.pre_janela_us, a.janela_us, n=N, n_pre=N_PRE)
    p = dict(n_base=n_base, ini=ini, fim=fim, pol=pol, modo="uni", limiar_lsb=a.limiar_lsb,
             max_std_base=a.max_std_base, metodo="pico", rejeitar_pileup=True, dt_us=dt,
             filtro_espiculas=True, rejeitar_espiculas=False)
    alt, rbase, rpile, base_v, std_base = [], [], [], [], []
    for i in range(0, n, 50_000):
        bl = amostras[i:i + 50_000]
        r = processar_bloco(bl, p)
        alt.append(r["altura"] / k)
        rbase.append(r["rej_base"])
        rpile.append(r["rej_pile"])
        base_v.append(r["base"])
        std_base.append(bl[:, :n_base].std(axis=1))
    alt, rbase, rpile = np.concatenate(alt), np.concatenate(rbase), np.concatenate(rpile)
    base_v, std_base = np.concatenate(base_v), np.concatenate(std_base)

    t = (np.arange(N) - N_PRE) * dt
    print(f"{n} eventos | dt {dt * 1000:.0f} ns | janela do pulso até +{(fim - N_PRE) * dt:.1f} us | "
          f"base até {(n_base - N_PRE) * dt:+.1f} us")
    print(f"Ruído da base (todos): mediana {np.median(std_base):.1f} LSB | p90 {np.percentile(std_base, 90):.1f} LSB"
          f" | corte usado {a.max_std_base} LSB -> rejeita {100 * rbase.mean():.1f}%")
    print("-" * 104)
    print(f"{'faixa (V)':>13} {'eventos':>8} {'rej.base':>9} {'pile-up':>8} {'pico após trig.':>16} "
          f"{'topo >95%':>11} {'chega ao fim':>13}")

    import matplotlib
    if a.sem_mostrar:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    nf = len(a.faixas)
    fig, ax = plt.subplots(2, nf, figsize=(4.2 * nf, 7.5), squeeze=False)
    for j, fx in enumerate(a.faixas):
        lo, hi = (float(v) for v in fx.split(":"))
        sel_todos = (alt >= lo) & (alt < hi)
        sel = sel_todos & ~rbase & ~rpile
        if sel.sum() == 0:
            print(f"{fx:>13} {0:>8}")
            continue
        x = amostras[sel].astype(np.float64)
        y = pol * (x - x[:, :n_base].mean(axis=1, keepdims=True))
        y, _ = remover_espiculas(y, dt, a.limiar_lsb)
        mx = y.max(axis=1, keepdims=True)
        yn = y / np.where(mx > 0, mx, 1)
        kpk = y.argmax(axis=1)
        topo = (yn > 0.95).sum(axis=1) * dt
        chega_fim = np.mean(kpk >= fim - 1)              # máximo encostado no fim da janela/registro
        print(f"{fx:>13} {sel_todos.sum():>8} {100 * rbase[sel_todos].mean():>8.1f}% "
              f"{100 * rpile[sel_todos].mean():>7.1f}% {np.median(t[kpk]):>13.1f} us "
              f"{np.median(topo):>8.2f} us {100 * chega_fim:>11.1f}%")
        a0, a1 = ax[0, j], ax[1, j]
        a0.plot(t, np.median(yn, axis=0), color="#2a1f8f", lw=2, label="mediana normalizada")
        a0.fill_between(t, np.percentile(yn, 10, axis=0), np.percentile(yn, 90, axis=0),
                        color="#7f77b8", alpha=0.3, label="10-90 %")
        a0.axvline(0, color="#d1495b", lw=0.8)
        a0.axvspan(t[ini], t[fim - 1], color="#e08e0b", alpha=0.08, label="janela do pico")
        a0.set_title(f"{lo:.3f}-{hi:.3f} V  ({sel.sum()} ev.)", fontsize=10)
        a0.set_xlabel("us após o trigger")
        a0.grid(ls=":", alpha=0.5)
        for e in range(min(a.exemplos, len(y))):
            a1.plot(t, y[e] / k, lw=0.7, alpha=0.7)
        a1.axvline(0, color="#d1495b", lw=0.8)
        a1.set_xlabel("us após o trigger")
        a1.grid(ls=":", alpha=0.5)
        if j == 0:
            a0.set_ylabel("forma normalizada")
            a1.set_ylabel("V (relativo à base)")
            a0.legend(fontsize=8)
    print("-" * 104)
    print("Topo plano bem mais largo nas faixas altas = corte. Pico perto do fim da janela = janela curta.")
    # rejeição por pré-trigger sujo: causa
    rej = rbase
    if rej.any():
        print(f"Pré-trigger sujo: ruído mediano dos rejeitados {np.median(std_base[rej]):.1f} LSB "
              f"vs aceitos {np.median(std_base[~rej]):.1f} LSB")
    fig.suptitle(f"Forma dos pulsos por faixa - {os.path.basename(base)}", fontsize=12)
    fig.tight_layout()
    nome = base + "_formas.png"
    fig.savefig(nome, dpi=150)
    print(f"Figura: {nome}")
    if not a.sem_mostrar:
        plt.show()


if __name__ == "__main__":
    main()
