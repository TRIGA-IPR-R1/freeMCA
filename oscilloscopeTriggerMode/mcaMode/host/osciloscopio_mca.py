#!/usr/bin/env python3
"""
osciloscopio_mca.py - Visualização ao vivo dos pulsos capturados pelo MCA (mca_ad9245.v).

Mostra:
  * forma de onda do último evento + persistência dos anteriores (estilo osciloscópio)
  * linha de base, limiar de trigger e instante do trigger
  * histograma das alturas (mesmo critério do leitor/MCA)
  * taxa recebida, taxa real (tempo vivo), linha de base absoluta, ruído

Teclas:  espaço = pausa | a = absoluto/relativo à base | c = limpa histograma/persistência
         l = histograma log/linear | s = salva PNG + eventos em tela (.npy) | q = sair

Uso:
  python osciloscopio_mca.py --porta /dev/ttyUSB0
  python osciloscopio_mca.py --reproduzir captura.bin            # sem hardware (velocidade real)
  python osciloscopio_mca.py --reproduzir captura.bin --salvar_quadro tela.png   # gera uma imagem e sai

Precisa do mca_comum.py na mesma pasta (mesmo decodificador e mesmo cálculo de altura,
com filtro de mediana contra espículas). O tempo por amostra e a polaridade vêm do pacote.
Não grava a captura: para isso use o leitor_adc.py (os dois não podem abrir a porta ao mesmo tempo).
"""
import argparse
import collections
import sys
import threading
import time

import numpy as np

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # acha o leitor_adc.py ao lado
from mca_comum import (CAB_FLUXO, COD_MAX, COD_ZERO, N_AMOSTRAS, N_PRE, PORTA_UDP, ContadorFluxo, Decodificador,
                       Desembrulhador, abrir_udp, altura_pico_lsb, cab_fluxo, decodificar_cfg,
                       desempacotar_fluxo, eh_fluxo, janelas, ler_udp)


class Fonte(threading.Thread):
    """Lê a serial (ou um .bin) numa thread e entrega pacotes decodificados."""

    def __init__(self, args):
        super().__init__(daemon=True)
        self.args = args
        self.dec = Decodificador()
        self.un_ts, self.un_viva = Desembrulhador(), Desembrulhador()
        self.fila = collections.deque(maxlen=5000)
        self.lock = threading.Lock()
        self.n = 0
        self.primeiro = None          # (ts, viva) do primeiro evento
        self.ultimo = None
        self.cfg = None               # dict de decodificar_cfg do último pacote
        self.erro = None
        self.fim = False
        self.n_pre = N_PRE
        # fluxo contínuo (formato do freeMCA): últimos pacotes seguidos e estatística do número de sequência
        self.fl_buf = collections.deque(maxlen=max(1, args.pacotes_tela))
        self.fl_cont = ContadorFluxo()
        self.fl = dict(t_ult=0.0, n=0, flags=0, seq=0, seq0=None, t0=time.time(), amostras=0, perd0=0)

    def run(self):
        try:
            if self.args.reproduzir:
                self._reproduzir()
            elif self.args.udp:
                self._udp()
            else:
                self._serial()
        except Exception as e:      # mostra o erro na tela em vez de morrer calado
            self.erro = str(e)
        self.fim = True

    def _entregar(self, pacotes):
        with self.lock:
            for cfg, ts, viva, amostras in pacotes:
                c = decodificar_cfg(cfg)
                if self.cfg is not None and c != self.cfg:     # trocou o bitstream
                    self.primeiro = None
                    self.un_ts, self.un_viva = Desembrulhador(), Desembrulhador()
                self.cfg = c
                ts, viva = self.un_ts(ts), self.un_viva(viva)
                if self.primeiro is None:
                    self.primeiro = (ts, viva)
                self.ultimo = (ts, viva)
                self.fila.append(amostras)
                self.n += 1
            self.n_pre = self.dec.n_pre

    def _serial(self):
        import serial
        with serial.Serial(self.args.porta, self.args.baud, timeout=0.05) as ser:
            ser.reset_input_buffer()
            while True:
                dados = ser.read(max(1, ser.in_waiting))
                if dados:
                    self._entregar(self.dec.alimentar(dados))

    def _udp(self):
        sk = abrir_udp(self.args.udp)
        while True:
            for d in ler_udp(sk):
                if eh_fluxo(d):
                    self._fluxo(d)
                else:
                    self._entregar(self.dec.alimentar(d, final=True))

    def _fluxo(self, d):
        seq, n, flags = cab_fluxo(d)
        with self.lock:
            if self.fl_cont.ver(seq, flags):          # faltou pacote (ou recomeçou): a tela só mostra trechos corridos
                self.fl_buf.clear()
            self.fl_buf.append(d)
            f = self.fl
            if f["seq0"] is None:
                f["seq0"], f["t0"] = seq, time.time()
            f.update(t_ult=time.time(), n=n, flags=flags, seq=seq)
            f["amostras"] += n

    def pegar_fluxo(self):
        """-> (lista de datagramas seguidos, estatística do último intervalo) ou None se não há fluxo."""
        with self.lock:
            f = self.fl
            agora = time.time()
            if agora - f["t_ult"] > 1.5:
                return None
            dt = max(agora - f["t0"], 1e-9)
            c = self.fl_cont
            snap = dict(n=f["n"], flags=f["flags"], seq=f["seq"], pacotes=c.pacotes, perdidos=c.perdidos,
                        overflow=c.overflow, reinicios=c.reinicios, dt=dt,
                        fpga_msps=((f["seq"] - f["seq0"]) & 0xFFFFFFFF) * f["n"] / dt / 1e6,
                        rx_msps=f["amostras"] / dt / 1e6, perdidos_int=c.perdidos - f["perd0"])
            if dt >= 1.0:
                f.update(seq0=f["seq"], t0=agora, amostras=0, perd0=c.perdidos)
                self.fl_snap = snap
            return list(self.fl_buf), getattr(self, "fl_snap", snap)

    def _reproduzir(self):
        with open(self.args.reproduzir, "rb") as f:
            dados = f.read()
        pacotes = self.dec.alimentar(dados, final=True)
        if not pacotes:
            raise RuntimeError("nenhum pacote válido no arquivo")
        ts0 = pacotes[0][1]
        tick_s = decodificar_cfg(pacotes[0][0])["dt_us"] * 1e-6
        t0 = time.time()
        for i, pk in enumerate(pacotes):
            if not self.args.rapido:                      # respeita o tempo real da captura
                atraso = (pk[1] - ts0) * tick_s - (time.time() - t0)
                if atraso > 0:
                    time.sleep(min(atraso, 0.5))
            self._entregar([pk])

    def pegar(self):
        with self.lock:
            novos = list(self.fila)
            self.fila.clear()
            return novos, self.n, self.primeiro, self.ultimo, self.cfg, self.n_pre


def main():
    ap = argparse.ArgumentParser(description="Osciloscópio ao vivo do MCA")
    ap.add_argument("--porta", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=2_000_000)
    ap.add_argument("--udp", nargs="?", type=int, const=PORTA_UDP, default=0, metavar="PORTA",
                    help=f"recebe por UDP em vez da serial (porta padrão {PORTA_UDP})")
    ap.add_argument("--pacotes_tela", type=int, default=8,
                    help="fluxo contínuo: pacotes seguidos mostrados na tela (720 amostras cada)")
    ap.add_argument("--reproduzir", help="arquivo .bin bruto (leitor_adc.py --salvar_bruto ou sim_fpga.py)")
    ap.add_argument("--rapido", action="store_true", help="na reprodução, não espera o tempo real")
    ap.add_argument("--lsb_por_v", type=float, default=1638.0)
    ap.add_argument("--limiar_lsb", type=float, default=82.0, help="o mesmo LIMIAR_LSB do firmware")
    ap.add_argument("--persistencia", type=int, default=30, help="nº de eventos anteriores em tela")
    ap.add_argument("--hist_max_v", type=float, default=5.0, help="fim do eixo do histograma (V)")
    ap.add_argument("--hist_bins", type=int, default=500)
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--salvar_quadro", help="gera uma imagem após alguns segundos e sai (sem janela)")
    ap.add_argument("--segundos", type=float, default=3.0, help="tempo antes de salvar o quadro")
    args = ap.parse_args()

    import matplotlib
    if args.salvar_quadro:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    fonte = Fonte(args)
    fonte.start()

    k = args.lsb_por_v
    dt0 = 0.16
    t_us = (np.arange(N_AMOSTRAS) - N_PRE) * dt0
    bordas = np.linspace(0, args.hist_max_v, args.hist_bins + 1)
    centros = 0.5 * (bordas[1:] + bordas[:-1])

    est = dict(pausado=False, absoluto=False, log=True, hist=np.zeros(args.hist_bins, np.int64),
               pers=collections.deque(maxlen=args.persistencia), ultimo=None, base=None,
               ruido=None, t_ini=time.time(), n_ant=0, t_ant=time.time(), taxa_rx=0.0,
               dt=None, pol=1, t_us=t_us, n_base=N_PRE - 8, n_am=N_AMOSTRAS, n_pre=N_PRE)

    fig = plt.figure(figsize=(13, 8))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.35, 1])
    ax_w = fig.add_subplot(gs[0, :])
    ax_h = fig.add_subplot(gs[1, :2])
    ax_t = fig.add_subplot(gs[1, 2])
    ax_t.axis("off")

    linhas_pers = [ax_w.plot([], [], color="#7f77b8", lw=0.7, alpha=0.25)[0]
                   for _ in range(args.persistencia)]
    (linha_ult,) = ax_w.plot([], [], color="#2a1f8f", lw=1.6, label="último evento")
    linha_base = ax_w.axhline(0, color="#3a7d44", lw=1, ls="--", label="linha de base")
    linha_lim = ax_w.axhline(0, color="#d1495b", lw=1, ls=":", label="limiar de trigger")
    ax_w.axvline(0, color="#d1495b", lw=0.8, alpha=0.6)
    faixa_base = ax_w.axvspan(t_us[0], t_us[N_PRE - 8], color="#3a7d44", alpha=0.06, label="janela da base")
    ax_w.set_xlim(t_us[0], t_us[-1])
    ax_w.set_xlabel("Tempo em relação ao trigger (µs)")
    ax_w.grid(True, ls=":", alpha=0.6)
    legenda = ax_w.legend(loc="upper right", fontsize=9)

    (linha_hist,) = ax_h.step(centros, est["hist"], where="mid", color="#4b3f9e", lw=0.9)
    ax_h.set_xlim(0, args.hist_max_v)
    ax_h.set_xlabel("Amplitude (V)  [pico - base, suavizado 3 pts]")
    ax_h.set_ylabel("Contagens")
    ax_h.grid(True, ls=":", alpha=0.6)
    texto = ax_t.text(0.0, 1.0, "", va="top", family="monospace", fontsize=10)
    fig.tight_layout()

    def ajustar_tempo(cfg, n_am, n_pre):
        if cfg is None:
            return
        if (cfg["dt_us"], cfg["polaridade"], n_am, n_pre) == (est["dt"], est["pol"], est["n_am"], est["n_pre"]):
            return
        if n_am != est["n_am"]:                       # janela mudou: as formas antigas não servem
            est["pers"].clear()
            est["ultimo"] = None
        est["dt"], est["pol"], est["n_am"], est["n_pre"] = cfg["dt_us"], cfg["polaridade"], n_am, n_pre
        est["n_base"] = janelas(est["dt"], n=n_am, n_pre=n_pre)[0]
        est["t_us"] = (np.arange(n_am) - n_pre) * est["dt"]
        ax_w.set_xlim(est["t_us"][0], est["t_us"][-1])
        x0, x1 = est["t_us"][0], est["t_us"][est["n_base"]]
        if hasattr(faixa_base, "set_width"):          # matplotlib >= 3.9 (Rectangle)
            faixa_base.set_x(x0)
            faixa_base.set_width(x1 - x0)
        else:                                          # versões antigas (Polygon)
            faixa_base.set_xy([[x0, 0], [x0, 1], [x1, 1], [x1, 0], [x0, 0]])

    def processar(novos):
        if est["dt"] is None:
            return
        nb = est["n_base"]
        novos = [a for a in novos if len(a) == est["n_am"]]
        for amostras in novos:
            h_v = altura_pico_lsb(amostras, est["dt"], est["pol"], limiar=args.limiar_lsb,
                                  n=est["n_am"], n_pre=est["n_pre"]) / k
            idx = np.searchsorted(bordas, h_v) - 1
            if 0 <= idx < args.hist_bins:
                est["hist"][idx] += 1
        for amostras in novos[-args.persistencia:]:
            est["pers"].append(amostras.astype(np.float64))
        if novos:
            x = novos[-1].astype(np.float64)
            est["ultimo"] = x
            est["base"] = x[:nb].mean()
            est["ruido"] = x[:nb].std()

    def desenhar_fluxo(dgs, st):
        """Fluxo contínuo (MODO 2 do mca_top ou oscilloscopeMode): amostras seguidas, sem trigger."""
        if not dgs:
            return
        tam = len(dgs[0])
        dgs = [d for d in dgs if len(d) == tam]
        bloco = np.frombuffer(b"".join(dgs), dtype=np.uint8).reshape(len(dgs), tam)
        cod = desempacotar_fluxo(bloco[:, CAB_FLUXO:], st["n"], st["flags"]).reshape(-1).astype(np.float64)
        cfg = decodificar_cfg(fonte.dec.cfg_status) if fonte.dec.cfg_status is not None else None
        if cfg:                                         # passo conhecido pelo status do FPGA
            x = np.arange(cod.size) * cfg["dt_us"]
            ax_w.set_xlabel(f"Tempo (µs) — {1 / cfg['dt_us']:.4g} MSPS, fluxo contínuo sem trigger")
        else:
            x = np.arange(cod.size)
            ax_w.set_xlabel("Amostra (seguidas) — fluxo contínuo sem trigger")
        y = (cod - COD_ZERO) / k
        for ln in linhas_pers:
            ln.set_data([], [])
        linha_ult.set_data(x, y)
        linha_base.set_visible(False)
        linha_lim.set_visible(False)
        faixa_base.set_visible(False)
        legenda.set_visible(False)
        ax_w.set_ylabel("Tensão absoluta na entrada do ADC (V)")
        ax_w.set_xlim(x[0], x[-1] if x[-1] > x[0] else x[0] + 1)
        marg = 0.08 * max(y.max() - y.min(), 0.01)
        ax_w.set_ylim(y.min() - marg, y.max() + marg)
        # distribuição das amostras em torno da mediana: ruído e offset do front-end
        med = np.median(cod)
        d = cod - med
        lim = max(8.0, np.percentile(np.abs(d), 99.5) * 1.5)
        h, b = np.histogram(d, bins=101, range=(-lim, lim))
        linha_hist.set_data(0.5 * (b[1:] + b[:-1]), h)
        ax_h.set_xlim(-lim, lim)
        ax_h.set_xlabel("Amostra − mediana (LSB)")
        ax_h.relim()
        ax_h.set_yscale("log" if est["log"] else "linear")
        ax_h.set_ylim(0.8 if est["log"] else 0, max(10, h.max() * 1.5))
        satur = int(((cod <= 0) | (cod >= COD_MAX)).sum())
        L = ["FLUXO CONTÍNUO (freeMCA)",
             f"FPGA:     {st['fpga_msps']:8.3f} MSPS",
             f"Recebido: {st['rx_msps']:8.3f} MSPS",
             f"Pacotes: {st['pacotes']}  (seq {st['seq']})",
             f"Perdidos: {st['perdidos']}" + (f"  (+{st['perdidos_int']})" if st["perdidos_int"] else ""),
             f"Overflow na FPGA: {st['overflow']}" + ("  <<" if st["flags"] & 1 else ""),
             "",
             f"Média: {(cod.mean() - COD_ZERO) / k:+.4f} V",
             f"RMS:   {d.std():.2f} LSB ({1000 * d.std() / k:.2f} mV)",
             f"Mín/máx: {(cod.min() - COD_ZERO) / k:+.3f} / {(cod.max() - COD_ZERO) / k:+.3f} V",
             f"Saturadas: {satur}" + ("  << ADC NO LIMITE" if satur else ""),
             f"Tela: {len(dgs)} pacotes, {cod.size} amostras",
             "", "espaço pausa | l log | s salva | q sai"]
        if cfg is None:
            L.insert(3, "(taxa nominal desconhecida: sem status)")
        texto.set_text("\n".join(L))
        est["fluxo_ult"] = cod

    def desenhar(_quadro=None):
        if est["pausado"]:
            return []
        fluxo = fonte.pegar_fluxo()
        if fluxo is not None:
            est["em_fluxo"] = True
            desenhar_fluxo(*fluxo)
            return []
        if est.get("em_fluxo"):                        # saiu do fluxo: volta a tela de eventos
            est["em_fluxo"] = False
            linha_base.set_visible(True)
            linha_lim.set_visible(True)
            faixa_base.set_visible(True)
            legenda.set_visible(True)
            linha_hist.set_data(centros, est["hist"])
            ax_h.set_xlim(0, args.hist_max_v)
            ax_h.set_xlabel("Amplitude (V)  [pico - base, suavizado 3 pts]")
            ax_w.set_xlabel("Tempo em relação ao trigger (µs)")
            ax_w.set_xlim(est["t_us"][0], est["t_us"][-1])
        novos, n, prim, ult, cfg, n_pre = fonte.pegar()
        ajustar_tempo(cfg, len(novos[-1]) if novos else est["n_am"], n_pre)
        processar(novos)
        t_us, pol, nb = est["t_us"], est["pol"], est["n_base"]
        agora = time.time()
        if agora - est["t_ant"] >= 1.0:
            est["taxa_rx"] = (n - est["n_ant"]) / (agora - est["t_ant"])
            est["n_ant"], est["t_ant"] = n, agora

        if est["ultimo"] is not None:
            base = est["base"]
            if est["absoluto"]:
                conv = lambda v: (v - COD_ZERO) / k
                ax_w.set_ylabel("Tensão absoluta na entrada do ADC (V)")
                linha_base.set_ydata([conv(base)] * 2)
                linha_lim.set_ydata([conv(base + args.limiar_lsb)] * 2)
            else:
                ax_w.set_ylabel("Tensão - linha de base (V)" + ("" if pol > 0 else "  [invertida]"))
                linha_base.set_ydata([0, 0])
                linha_lim.set_ydata([args.limiar_lsb / k] * 2)
            pers = list(est["pers"])
            ys_all = []
            for ln, x in zip(linhas_pers, pers[:-1]):
                y = (x - COD_ZERO) / k if est["absoluto"] else pol * (x - x[:nb].mean()) / k
                ln.set_data(t_us, y)
                ys_all.append(y)
            for ln in linhas_pers[len(pers) - 1:]:
                ln.set_data([], [])
            x = est["ultimo"]
            y = (x - COD_ZERO) / k if est["absoluto"] else pol * (x - base) / k
            linha_ult.set_data(t_us, y)
            ys_all.append(y)
            ys = np.concatenate(ys_all)
            ref = linha_lim.get_ydata()[0]
            lo, hi = min(ys.min(), ref), max(ys.max(), ref)
            marg = 0.08 * max(hi - lo, 0.05)
            ax_w.set_ylim(lo - marg, hi + marg)

        hist = est["hist"]
        linha_hist.set_ydata(hist)
        ax_h.relim()                                   # limites de dados atualizados (evita aviso do log)
        if est["log"] and hist.max() > 0:
            ax_h.set_yscale("log")
            ax_h.set_ylim(0.8, max(10, hist.max() * 1.5))
        else:
            ax_h.set_yscale("linear")
            ax_h.set_ylim(0, max(10, hist.max() * 1.1))

        L = [f"Eventos: {n}", f"Recebendo: {est['taxa_rx']:7.1f} ev/s"]
        if prim and ult and ult[1] > prim[1] and est["dt"]:
            viva_s = (ult[1] - prim[1]) * est["dt"] * 1e-6
            real_s = (ult[0] - prim[0]) * est["dt"] * 1e-6
            L += [f"Taxa real: {(n - 1) / viva_s:8.1f} cps",
                  f"Tempo vivo: {100 * viva_s / max(real_s, 1e-9):5.1f} %"]
        if est["base"] is not None:
            L += ["", f"Base abs.: {(est['base'] - COD_ZERO) / k:+.4f} V",
                  f"Ruído base: {est['ruido']:.1f} LSB ({1000 * est['ruido'] / k:.2f} mV)",
                  f"Limiar: {args.limiar_lsb:.0f} LSB ({1000 * args.limiar_lsb / k:.0f} mV)",
                  f"dt: {est['dt'] * 1000:.0f} ns | pol: {'+' if est['pol'] > 0 else '-'}"]
        if fonte.dec.n_picos:
            L += ["", f"Pacotes de pico: {fonte.dec.n_picos}", "(modo picos: sem formas)"]
        L += ["", f"Inválidos: {fonte.dec.invalidos}",
              f"Bytes descartados: {fonte.dec.descartados}"]
        if fonte.erro:
            L += ["", "ERRO:", fonte.erro[:40]]
        elif fonte.fim and args.reproduzir:
            L += ["", "(fim da reprodução)"]
        L += ["", "espaço pausa | a abs/rel", "c limpa | l log | s salva | q sai"]
        texto.set_text("\n".join(L))
        return []

    def tecla(ev):
        if ev.key == " ":
            est["pausado"] = not est["pausado"]
        elif ev.key == "a":
            est["absoluto"] = not est["absoluto"]
        elif ev.key == "c":
            est["hist"][:] = 0
            est["pers"].clear()
        elif ev.key == "l":
            est["log"] = not est["log"]
        elif ev.key == "s":
            nome = time.strftime("osc_%Y%m%d_%H%M%S")
            fig.savefig(nome + ".png", dpi=150)
            if est.get("em_fluxo") and est.get("fluxo_ult") is not None:
                np.save(nome + "_fluxo.npy", est["fluxo_ult"].astype(np.uint16))
            elif est["pers"]:
                np.save(nome + "_eventos.npy", np.array(est["pers"], dtype=np.uint16))
            print(f"salvo: {nome}.png")
        elif ev.key == "q":
            plt.close(fig)
        fig.canvas.draw_idle()

    if args.salvar_quadro:
        t_lim = time.time() + args.segundos
        while time.time() < t_lim and not (fonte.fim and not fonte.fila and not args.udp):
            time.sleep(0.1)
        desenhar()
        fig.savefig(args.salvar_quadro, dpi=150)
        print(f"Quadro salvo em {args.salvar_quadro} ({fonte.n} eventos)")
        return

    fig.canvas.mpl_connect("key_press_event", tecla)
    anim = FuncAnimation(fig, desenhar, interval=1000 / args.fps, cache_frame_data=False)
    fig._anim = anim                       # mantém referência viva
    plt.show()


if __name__ == "__main__":
    main()
