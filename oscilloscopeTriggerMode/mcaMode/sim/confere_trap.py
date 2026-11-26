"""Confere a simulação do filtro trapezoidal no mca_top (modo picos, pulsos de pré-amplificador):
a altura medida pelo trapézio tem de reproduzir a amplitude de cada pulso, inclusive a do pulso
que cai sobre a cauda de outro."""
import sys, json
import numpy as np
sys.path.insert(0, "../host"); sys.path.insert(0, ".")
from mca_comum import Decodificador, FLAG_TRAPEZIO, escala_trapezio
from confere_eth import quadros, abre
from confere_v1 import le_hex
gab = json.load(open("estimulo.json")); pulsos = gab["pulsos"]
trig = [float(l.split()[0]) for l in open("trig.txt")]
dec = Decodificador(); pk = dec.alimentar(le_hex("uart.hex"), final=True, tudo=True)
erros = []
if dec.invalidos or dec.descartados: erros.append("UART com bytes inválidos")
st = [p[2] for p in pk if p[0] == "status"]
print("status final:", {k: st[-1][k] for k in ("versao_fw", "modo", "filtro", "trap_k", "trap_m", "trap_pz", "trap_sh")})
com_filtro = [s for s in st if s.get("filtro")][-1]
esc = escala_trapezio(com_filtro)
print(f"escala do trapézio: {esc:.4f} contagens por LSB")
ev = [p for p in pk if p[0] == "pico"]
for f in quadros():
    ev += [p for p in Decodificador().alimentar(abre(f), final=True, tudo=True) if p[0] == "pico"]
ev.sort(key=lambda p: p[2])                              # ordem de timestamp = ordem dos triggers
if len(ev) != len(trig): erros.append(f"{len(ev)} picos para {len(trig)} triggers")
n_trap = n_bruto = 0
for p, t in zip(ev, trig):
    k = max(i for i, (t0, a) in enumerate(pulsos) if t0 <= t); t0, amp = pulsos[k]
    m = p[4]
    if m["flags"] & FLAG_TRAPEZIO:
        h = m["pico4"] / esc; n_trap += 1
        ok = abs(h - amp) < 0.015 * amp + 3 and com_filtro["trap_k"] - 2 <= m["tpico"] <= com_filtro["trap_k"] + com_filtro["trap_m"] + 4
        nome = "trapézio"
    else:
        h = m["pico4"] / 4; n_bruto += 1
        ok = 0.90 * amp < h < 1.0 * amp + 3                # pico bruto: abaixo da amplitude (subida finita)
        nome = "pico 1-2-1"
    print(("  ok   " if ok else "  ERRO ") + f"t={t/1e6:6.3f} ms pulso {k:2d} amplitude {amp:4d} | {nome:10s} altura {h:8.2f} "
          f"({100 * (h / amp - 1):+5.2f} %) tpico {m['tpico']:3d} flags {m['flags'] & 15}")
    if not ok: erros.append(f"pulso {k}")
if n_trap < 8 or n_bruto < 3: erros.append(f"poucos eventos: {n_trap} com filtro, {n_bruto} sem")
print("ERROS:" if erros else "SEM ERROS", *erros, sep="\n  ")
sys.exit(1 if erros else 0)
