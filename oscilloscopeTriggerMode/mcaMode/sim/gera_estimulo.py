"""Gera estimulo.vh (lista de pulsos para o testbench) e estimulo.json (gabarito)."""
import json, sys, random
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
esp_us = float(sys.argv[3]) if len(sys.argv) > 3 else 3000.0   # espaçamento médio
base = 7000; tau_ns = float(sys.argv[4]) if len(sys.argv) > 4 else 1500.0   # 4o argumento: constante de tempo (ns)
tr_ns = 100.0                                                    # subida do pré (só com -DPRE_EXP)
t = 400e3; pulsos = []
for k in range(n):
    amp = random.choice([150, 300, 600, 1200, 2500, 5000]) + random.randint(0, 40)
    pulsos.append((round(t), amp)); t += esp_us * 1e3 * random.uniform(0.7, 1.3)
with open("estimulo.vh", "w") as f:
    f.write(f"localparam integer NP = {n};\nlocalparam integer BASE = {base};\nlocalparam real TAU = {tau_ns};\nlocalparam real TR = {tr_ns};\n")
    f.write("real t0 [0:NP-1]; real amp [0:NP-1];\ninitial begin\n")
    for k, (a, b) in enumerate(pulsos): f.write(f"  t0[{k}] = {a}.0; amp[{k}] = {b}.0;\n")
    f.write("end\n")
json.dump(dict(base=base, tau_ns=tau_ns, tr_ns=tr_ns, pulsos=pulsos, fim_ns=t), open("estimulo.json", "w"))
print(f"{n} pulsos até {t / 1e6:.1f} ms")
