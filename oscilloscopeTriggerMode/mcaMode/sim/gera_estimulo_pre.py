"""Estímulo de pré-amplificador para o teste do filtro trapezoidal (usar com -DPRE_EXP):
pulsos com subida de 0,1 us e cauda de 20 us, um deles sobre a cauda de outro."""
import json
base, tau_ns, tr_ns = 7000, 20000.0, 100.0
amps = [300, 5000, 150, 1200, 2500, 640, 800, 4000]
pulsos = [(2500000 + 500000 * i, a) for i, a in enumerate(amps)]
pulsos += [(6500000, 3000), (6578000, 500)]            # o segundo cai sobre a cauda do primeiro (~60 LSB)
pulsos += [(7700000 + 500000 * i, a) for i, a in enumerate([300, 5000, 1200, 2500])]   # com o filtro desligado
with open("estimulo.vh", "w") as f:
    f.write(f"localparam integer NP = {len(pulsos)};\nlocalparam integer BASE = {base};\n"
            f"localparam real TAU = {tau_ns};\nlocalparam real TR = {tr_ns};\n")
    f.write("real t0 [0:NP-1]; real amp [0:NP-1];\ninitial begin\n")
    for k, (a, b) in enumerate(pulsos):
        f.write(f"  t0[{k}] = {a}.0; amp[{k}] = {b}.0;\n")
    f.write("end\n")
json.dump(dict(base=base, tau_ns=tau_ns, tr_ns=tr_ns, pulsos=pulsos, fim_ns=9.7e6), open("estimulo.json", "w"))
print(len(pulsos), "pulsos de pré-amplificador (tau 20 us)")
