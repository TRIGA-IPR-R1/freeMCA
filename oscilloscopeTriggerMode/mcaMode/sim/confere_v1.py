import sys, json, numpy as np
sys.path.insert(0, "../host")
from mca_comum import Decodificador, decodificar_cfg
def le_hex(nome): return bytes(int(l, 16) for l in open(nome) if l.strip() and not l.startswith("--"))
def confere(dados, gab, dt_ns=160.0, rotulo=""):
    dec = Decodificador(); ev = dec.alimentar(dados, final=True)
    print(f"{rotulo}: {len(dados)} bytes -> {len(ev)} eventos; inválidos {dec.invalidos}, descartados {dec.descartados}")
    ok = len(ev) == len(gab["pulsos"])
    for (cfg, ts, viva, am), (t0, amp) in zip(ev, gab["pulsos"]):
        am = np.asarray(am, float); base = am[:30].mean(); pico = am.max() - base
        t_trig = ts * dt_ns          # ns desde o lock do PLL (~440 ns após t=0)
        print(f"  cfg={decodificar_cfg(cfg)} ts={ts} ({t_trig/1e3:.1f} us; pulso em {t0/1e3:.1f}) viva={viva} base={base:.1f} pico={pico:.1f} (esperado ~{amp}) idx_max={am.argmax()}")
        ok &= abs(pico - amp) < 0.03 * amp + 6 and -1000 < t_trig - t0 < 3000 and abs(base - gab["base"]) < 3
    print("  RESULTADO:", "OK" if ok else "FALHOU"); return ok
if __name__ == "__main__":
    sys.exit(0 if confere(le_hex("uart.hex"), json.load(open("estimulo.json")), rotulo="UART v1") else 1)
