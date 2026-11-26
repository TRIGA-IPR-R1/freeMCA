"""Compara a saída do jk_trapezio simulado (jk_s.txt) com o modelo inteiro em Python."""
import sys
import numpy as np
sys.path.insert(0, "../host")
from mca_comum import jordanov_fpga
k, m, pz4 = (int(x) for x in sys.argv[1:4])
v = np.loadtxt("jk_v.txt", dtype=np.int64)
sp = np.loadtxt("jk_s.txt", dtype=np.int64)
s, pronto = sp[:, 0], sp[:, 1]
ref = jordanov_fpga(v, k, m, pz4)
prim = int(np.argmax(pronto))            # 'pronto' sobe depois de k + l amostras (a saída sai alguns ciclos depois)
ok = len(s) == len(v) and np.array_equal(s, ref) and 2 * k + m - 4 <= prim <= 2 * k + m + 1 and pronto[prim:].all()
print(f"k={k} m={m} pz4={pz4}: {len(s)} amostras, |s| máx 2^{np.log2(np.abs(s).max()):.1f} ->", "IDÊNTICO ao modelo" if ok else "DIFERENTE")
if not ok:
    dif = np.where(s[:min(len(s), len(ref))] != ref[:min(len(s), len(ref))])[0]
    print("  primeira diferença na amostra", dif[:1], "| tamanhos", len(s), len(v))
sys.exit(0 if ok else 1)
