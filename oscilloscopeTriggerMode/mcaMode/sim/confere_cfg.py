"""Confere a simulação do mca_ad9245_cfg.v: uart.hex + eth.hex contra trig.txt e estimulo.json."""
import sys, json
import numpy as np
sys.path.insert(0, "../host"); sys.path.insert(0, ".")
from mca_comum import Decodificador, decodificar_cfg
from confere_eth import quadros, abre
from confere_v1 import le_hex
gab = json.load(open("estimulo.json")); pulsos = gab["pulsos"]; tau = gab["tau_ns"]
trig = [l.split() for l in open("trig.txt")]
trig = [dict(t=float(a[0]), modo=int(a[1]), saida=int(a[2]), l2=int(a[3]), pol=int(a[4]), npre=int(a[5]),
             npos=int(a[6]), lim=int(a[7])) for a in trig]
dec = Decodificador(); uart = dec.alimentar(le_hex("uart.hex"), final=True, tudo=True)
erros = []
if dec.invalidos or dec.descartados: erros.append(f"UART: inválidos {dec.invalidos}, descartados {dec.descartados}")
udp = []
for i, f in enumerate(quadros()):
    try:
        d = Decodificador(); p = d.alimentar(abre(f), final=True, tudo=True)
        if len(p) != 1 or d.invalidos or d.descartados: erros.append(f"datagrama {i}: {len(p)} pacotes")
        udp += p
    except AssertionError as e:
        erros.append(f"quadro {i}: {e}")
st_u = [p for p in uart if p[0] == "status"]; st_e = [p for p in udp if p[0] == "status"]
ev_u = [p for p in uart if p[0] != "status"]; ev_e = [p for p in udp if p[0] != "status"]
print(f"UART: {len(uart)} pacotes ({len(st_u)} status) | UDP: {len(udp)} datagramas ({len(st_e)} status) | triggers: {len(trig)}")
for p in st_u: print("  status UART:", p[2])
tr_u = [t for t in trig if t["saida"] == 0]; tr_e = [t for t in trig if t["saida"] == 1]
# o último trigger pode não ter terminado de enviar quando a simulação acaba
for nome, ev, tr in (("UART", ev_u, tr_u), ("UDP", ev_e, tr_e)):
    if not (len(tr) - 1 <= len(ev) <= len(tr)): erros.append(f"{nome}: {len(ev)} eventos para {len(tr)} triggers")
    for p, t in zip(ev, tr):
        cfg = decodificar_cfg(p[1]); dt = cfg["dt_us"] * 1e3
        k = max(i for i, (t0, a) in enumerate(pulsos) if t0 <= t["t"]); t0, amp = pulsos[k]
        esperado = "pico" if t["modo"] else "forma"
        msg = f"{nome} t={t['t']/1e6:7.3f} ms pulso {k:2d} amp {amp:4d} {esperado:5s} l2={t['l2']} pol={t['pol']} jan={t['npre']}+1+{t['npos']} lim={t['lim']}"
        if p[0] != esperado or cfg["log2_media"] != t["l2"] or (cfg["polaridade"] < 0) != bool(t["pol"]) or cfg["versao"] != 2:
            erros.append(msg + f" -> tipo/cfg errado ({p[0]}, {cfg})"); continue
        sinal = -1 if t["pol"] else 1
        if p[0] == "forma":
            am = np.asarray(p[4], float); nam = t["npre"] + 1 + t["npos"]
            base = am[: t["npre"] - 10].mean(); pico = (sinal * (am - base)).max()
            ok = (len(am) == nam and p[5] == t["npre"] and abs(pico - amp) < 0.03 * amp + 6 and abs(base - gab["base"]) < 3
                  and sinal * (am[t["npre"]] - base) >= t["lim"] - 3 and sinal * (am[t["npre"] - 3] - base) < t["lim"] + 3)
            msg += f" | n={len(am)} npre={p[5]} base={base:.1f} pico={pico:.1f} trig={sinal*(am[p[5]]-base):.0f}"
        else:
            m = p[4]; pico = m["pico4"] / 4
            area_esp = amp * np.e * tau / dt
            ok = (abs(pico - amp) < 0.03 * amp + 6 and abs(m["base"] - gab["base"]) < 3 and m["flags"] == 0
                  and abs(m["area"] - area_esp) < 0.12 * area_esp + 60 and 0 < m["tpico"] * dt < 2 * tau)
            msg += f" | pico={pico:.2f} base={m['base']} area={m['area']} (~{area_esp:.0f}) tpico={m['tpico']} flags={m['flags']}"
        if amp + 5 < t["lim"]: ok = False; msg += " | DISPAROU ABAIXO DO LIMIAR"
        print(("  ok   " if ok else "  ERRO ") + msg)
        if not ok: erros.append(msg)
json.dump(dict(st_u=[p[2] for p in st_u], st_e=[p[2] for p in st_e], n_ev_u=len(ev_u), n_ev_e=len(ev_e),
               ts=[p[2] for p in ev_u + ev_e]), open("resultado_cfg.json", "w"))
print("ERROS:" if erros else "SEM ERROS", *erros, sep="\n  ")
sys.exit(1 if erros else 0)
