"""Confere o fluxo contínuo da simulação do mca_top: eth.hex contra fluxo.txt (amostras que
entraram no fluxo, registradas pelo testbench). Cada trecho (seq a partir de 0) tem de reproduzir,
amostra por amostra, um trecho corrido do gabarito, sem overflow e sem saltos de seq."""
import sys
import numpy as np
sys.path.insert(0, "../host"); sys.path.insert(0, ".")
from mca_comum import Decodificador, cab_fluxo, desempacotar_fluxo, eh_fluxo, FLUXO_EMPACOTADO, FLUXO_OFFSET
from confere_eth import quadros, abre

gab, atual = [], None                     # trechos do gabarito (um por entrada no modo contínuo)
for l in open("fluxo.txt"):
    if l.startswith("#"):
        atual = []; gab.append(atual)
    elif l.strip():
        atual.append(int(l))
gab = [np.array(g) for g in gab]
erros, trechos, outros = [], [], []
for i, f in enumerate(quadros()):
    try:
        d = abre(f)
    except AssertionError as e:
        erros.append(f"quadro {i}: {e}"); continue
    if eh_fluxo(d):
        seq, n, flags = cab_fluxo(d)
        if n != 720 or flags != (FLUXO_EMPACOTADO | FLUXO_OFFSET) or len(d) != 10 + 1260:
            erros.append(f"quadro {i}: cabeçalho de fluxo inesperado seq={seq} n={n} flags={flags} len={len(d)}")
        if seq == 0:
            trechos.append([])
        elif not trechos or seq != trechos[-1][-1][0] + 1:
            erros.append(f"quadro {i}: salto de seq ({seq})")
        trechos[-1].append((seq, desempacotar_fluxo(d[10:], n, flags)[0]))
    else:
        p = Decodificador().alimentar(d, final=True, tudo=True)
        outros.append(p[0][0] if len(p) == 1 else "?")
print(f"{sum(len(t) for t in trechos)} datagramas de fluxo em {len(trechos)} trechos; outros datagramas: {outros}")
if len(trechos) != len(gab):
    erros.append(f"{len(trechos)} trechos no fluxo, {len(gab)} no gabarito")
for k, (t, g) in enumerate(zip(trechos, gab)):
    am = np.concatenate([x[1] for x in t])
    # as primeiras amostras podem cair antes de a fila sair do reset: procura o alinhamento
    for o in range(0, 40):
        if len(g) >= o + len(am) and np.array_equal(g[o:o + len(am)], am):
            print(f"  trecho {k}: {len(t)} pacotes, {len(am)} amostras idênticas ao gabarito (começa na amostra {o}); "
                  f"mín {am.min()} máx {am.max()}; ficaram {len(g) - o - len(am)} amostras na fila/no fim")
            break
    else:
        erros.append(f"trecho {k}: amostras não batem com o gabarito")
print("ERROS:" if erros else "SEM ERROS", *erros, sep="\n  ")
sys.exit(1 if erros else 0)
