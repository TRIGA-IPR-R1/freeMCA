"""
mca_comum.py - Formato dos pacotes do MCA e funções compartilhadas por leitor_adc.py,
osciloscopio_mca.py, espectrometria_mca.py e mca_config.py (deixe na mesma pasta).

Protocolo 1 (mca_ad9245.v e mca_ad9245_udp.v), 413 bytes fixos:
  FF FF | CFG | timestamp (5 x 7 bits) | tempo vivo (5 x 7 bits) | 200 x {00 D13..D8, D7..D0}

Protocolo 2 (mca_ad9245_cfg.v), FF FF | CFG | TIPO | ...:
  TIPO 0 forma : NAM(2) NPRE(2) timestamp(5) tempo vivo(5) + NAM x {alto, baixo}
  TIPO 1 pico  : timestamp(5) tempo vivo(5) PICO4(3) BASE(2) AREA(4) TPICO(2) FLAGS(1)
  TIPO 2 status: VERSAO LIMIAR(2) CONFIRMA MODO SAIDA ATIVO NPRE(2) NPOS(2) ACK REG
                 e, a partir da versão 3 (mca_top.v com filtro trapezoidal):
                 FILTRO TRAP_K(2) TRAP_M(2) TRAP_PZ(3) TRAP_SH

CFG = {0, protocolo(3), polaridade(1), log2_media(3)}   ->  dt = 2^log2_media x 40 ns
Pela rede (UDP) cada datagrama traz um pacote; basta entregar os datagramas, em ordem,
ao mesmo Decodificador.

Fluxo contínuo (mcaMode/rtl/mca_top.v em MODO 2 e oscilloscopeMode do freeMCA), só por UDP,
little-endian:  magic u16 = 0xADC0 | seq u32 | n u16 | flags u16 | amostras empacotadas
  flags: bit0 = overflow da fila na FPGA, bit1 = empacotado (largura = 8 x bytes / n),
         bit2 = offset binary. É o mesmo formato do oscilloscopeMode/host/adc_codec.py.
Um datagrama é de fluxo se começa por C0 AD; os pacotes do MCA começam por FF FF.
"""
import numpy as np

N_AMOSTRAS = 200                   # protocolo 1 (fixo)
N_PRE = 49                         # trigger no índice 49
COD_ZERO = 8192
COD_MAX = 16383
CABECALHO = b"\xff\xff"
TAM_PACOTE = 2 + 1 + 10 + 2 * N_AMOSTRAS          # 413
T_ADC_US = 0.04                                   # ADC a 25 MSPS
PORTA_UDP = 5000

TAM_CAB_FORMA, TAM_PICO, TAM_STATUS, TAM_STATUS_V3 = 18, 26, 17, 26
NAM_MIN, NAM_MAX = 17, 700

DTYPE_REG = np.dtype([("ts", "<u8"), ("viva", "<u8"), ("amostras", "<u2", (N_AMOSTRAS,))])
DTYPE_PICO = np.dtype([("ts", "<u8"), ("viva", "<u8"), ("pico4", "<u2"), ("base", "<u2"),
                       ("area", "<i4"), ("tpico", "<u2"), ("flags", "u1")])
FLAG_SATUROU, FLAG_PILEUP, FLAG_ALTO_NO_FIM, FLAG_PICO_NO_FIM, FLAG_TRAPEZIO = 1, 2, 4, 8, 16

# registradores do mca_ad9245_cfg.v: nome -> (número, mínimo, máximo)
REGISTRADORES = dict(limiar=(0, 4, 8000), confirma=(1, 1, 15), log2_media=(2, 0, 4), polaridade=(3, 0, 1),
                     modo=(4, 0, 2), n_pre=(5, 8, 600), n_pos=(6, 8, 690), saida=(7, 0, 1), ativo=(8, 0, 1),
                     status=(9, 0, 0), zera_tempo=(10, 0, 0),
                     filtro=(11, 0, 1), trap_k=(12, 2, 255), trap_m=(13, 1, 255), trap_pz=(14, 4, 65535),
                     trap_sh=(15, 0, 31))


def abrir_udp(porta=PORTA_UDP, timeout=0.1):
    """Socket UDP que recebe os datagramas do FPGA (enviados em broadcast)."""
    import socket
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sk.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 << 20)  # absorve rajadas (como no freeMCA)
    except OSError:
        pass
    sk.bind(("", porta))
    sk.settimeout(timeout)
    return sk


def ler_udp(sk, timeout=0.1, max_datagramas=2000):
    """Lista de datagramas disponíveis (espera até 'timeout' pelo primeiro)."""
    import socket
    saida = []
    try:
        sk.settimeout(timeout)
        saida.append(sk.recv(2048))
        sk.setblocking(False)
        while len(saida) < max_datagramas:
            saida.append(sk.recv(2048))
    except (BlockingIOError, socket.timeout, TimeoutError):
        pass
    return saida


# ---------------------------------------------------------------------------------------------
# Fluxo contínuo (formato do oscilloscopeMode do freeMCA)
# ---------------------------------------------------------------------------------------------
MAGIC_FLUXO = 0xADC0
INICIO_FLUXO = b"\xc0\xad"
CAB_FLUXO = 10                       # magic(2) seq(4) n(2) flags(2)
FLUXO_OVF, FLUXO_EMPACOTADO, FLUXO_OFFSET = 1, 2, 4
NOMES_MODO = ("formas", "picos", "contínuo")


def eh_fluxo(datagrama):
    return len(datagrama) > CAB_FLUXO and datagrama[:2] == INICIO_FLUXO


def cab_fluxo(datagrama):
    """-> (seq, n, flags) do cabeçalho de um datagrama de fluxo."""
    return (int.from_bytes(datagrama[2:6], "little"), int.from_bytes(datagrama[6:8], "little"),
            int.from_bytes(datagrama[8:10], "little"))


def desempacotar_fluxo(dados, n, flags):
    """Amostras de um ou mais datagramas iguais (mesmo n e flags), sem os cabeçalhos.
    dados: bytes ou array uint8 de forma (m, bytes_por_datagrama). Devolve uint16 (m, n) com os
    CÓDIGOS do ADC em offset binary (8192 = 0 V em 14 bits), como no resto destes programas."""
    d = np.frombuffer(dados, dtype=np.uint8) if isinstance(dados, (bytes, bytearray, memoryview)) else dados
    d = d.reshape(-1, d.shape[-1]) if d.ndim > 1 else d.reshape(1, -1)
    m, nb = d.shape
    if not flags & FLUXO_EMPACOTADO:
        v = d[:, :2 * n].copy().view("<i2").astype(np.int32)
        bits = 16
    else:
        bits = (nb * 8) // n
        if bits == 14 and n % 4 == 0 and nb >= n * 7 // 4:      # caso comum: 4 amostras em 7 bytes
            b = d[:, :n * 7 // 4].reshape(m, n // 4, 7).astype(np.uint16)
            v = np.empty((m, n // 4, 4), dtype=np.int32)
            v[..., 0] = b[..., 0] | ((b[..., 1] & 0x3F) << 8)
            v[..., 1] = (b[..., 1] >> 6) | (b[..., 2] << 2) | ((b[..., 3] & 0x0F) << 10)
            v[..., 2] = (b[..., 3] >> 4) | (b[..., 4] << 4) | ((b[..., 5] & 0x03) << 12)
            v[..., 3] = (b[..., 5] >> 2) | (b[..., 6] << 6)
            v = v.reshape(m, n)
        else:                                                    # largura qualquer (1 a 16 bits)
            if not 1 <= bits <= 16:
                raise ValueError(f"largura de amostra inválida: {bits} bits")
            bitsl = np.unpackbits(d[:, :(n * bits + 7) // 8], axis=1, bitorder="little")[:, :n * bits]
            pesos = (1 << np.arange(bits)).astype(np.int32)
            v = (bitsl.reshape(m, n, bits).astype(np.int32) * pesos).sum(axis=2)
    if not flags & FLUXO_OFFSET:                                 # complemento de dois -> offset binary
        v = (v + (1 << (bits - 1))) & ((1 << bits) - 1)
    return v.astype(np.uint16)


class ContadorFluxo:
    """Acompanha o número de sequência do fluxo: pacotes, perdidos (lacunas) e overflow."""

    def __init__(self):
        self.ult = None
        self.pacotes = self.perdidos = self.lacunas = self.overflow = self.reinicios = 0

    def ver(self, seq, flags):
        """Devolve quantos pacotes faltaram antes deste (0 = contínuo; -1 = o fluxo recomeçou)."""
        falta = 0
        if self.ult is not None:
            falta = (seq - self.ult - 1) & 0xFFFFFFFF
            if falta > 0x7FFFFFFF:            # seq voltou: a FPGA reiniciou o fluxo
                self.reinicios += 1
                falta = -1
            elif falta:
                self.perdidos += falta
                self.lacunas += 1
        self.ult = seq
        self.pacotes += 1
        if flags & FLUXO_OVF:
            self.overflow += 1
        return falta


def dtype_reg(n):
    """Registro do arquivo .dat para eventos de n amostras."""
    return np.dtype([("ts", "<u8"), ("viva", "<u8"), ("amostras", "<u2", (int(n),))])


def montar_comando(reg, valor=0):
    """6 bytes do comando para o mca_ad9245_cfg.v. reg: número ou nome em REGISTRADORES."""
    if isinstance(reg, str):
        reg = REGISTRADORES[reg][0]
    vh, vl = (int(valor) >> 8) & 0xFF, int(valor) & 0xFF
    return bytes([0xA5, 0x5A, reg, vh, vl, reg ^ vh ^ vl ^ 0xFF])


def decodificar_cfg(cfg):
    """-> dict(versao, polaridade (+1/-1), log2_media, dt_us)"""
    l2 = cfg & 0x7
    return dict(versao=(cfg >> 4) & 0x7, polaridade=-1 if (cfg >> 3) & 1 else 1,
                log2_media=l2, dt_us=(1 << l2) * T_ADC_US)


def _campo7(b, bits=32):
    v = 0
    for x in b:
        v = (v << 7) | (x & 0x7F)
    return v & ((1 << bits) - 1)


class Decodificador:
    """Separa pacotes do fluxo de bytes (UART ou datagramas UDP em sequência); robusto a
    bytes perdidos e lixo. Entende os protocolos 1 e 2.

    alimentar() devolve a lista de formas de pulso: (cfg, ts, viva, amostras[uint16]).
    Com tudo=True devolve todos os pacotes, na ordem, como tuplas:
        ("forma",  cfg, ts, viva, amostras, n_pre)
        ("pico",   cfg, ts, viva, dict(pico4, base, area, tpico, flags))
        ("status", cfg, dict(versao_fw, limiar, confirma, modo, saida, ativo, n_pre, n_pos, ack, reg))
    self.n_pre é o índice do trigger da última forma; self.status o último status recebido."""

    def __init__(self):
        self.buf = bytearray()
        self.descartados = 0
        self.invalidos = 0
        self.n_pre = N_PRE
        self.status = None
        self.cfg_status = None             # byte CFG do último status (dá o passo de amostragem)
        self.n_picos = 0

    def _tamanho(self):
        """Tamanho do pacote no início do buffer; 0 = faltam bytes para saber; -1 = inválido."""
        b = self.buf
        if len(b) < 3:
            return 0
        versao = (b[2] >> 4) & 7
        if b[2] > 0x7F or versao not in (1, 2):
            return -1
        if versao == 1:
            return TAM_PACOTE
        if len(b) < 4:
            return 0
        if b[3] == 1:
            return TAM_PICO
        if b[3] == 2:
            if len(b) < 5:
                return 0
            return TAM_STATUS_V3 if b[4] >= 3 else TAM_STATUS
        if b[3] != 0:
            return -1
        if len(b) < 6:
            return 0
        nam = _campo7(b[4:6])
        if max(b[4:6]) > 0x7F or not NAM_MIN <= nam <= NAM_MAX:
            return -1
        return TAM_CAB_FORMA + 2 * nam

    def alimentar(self, dados, final=False, tudo=False):
        self.buf.extend(dados)
        saida = []
        while True:
            idx = self.buf.find(CABECALHO)
            if idx < 0:
                if len(self.buf) > 1:
                    self.descartados += len(self.buf) - 1
                    del self.buf[:-1]
                break
            while idx + 2 < len(self.buf) and self.buf[idx + 2] == 0xFF:
                idx += 1                     # byte baixo 0xFF antes do cabeçalho
            if idx > 0:
                self.descartados += idx
                del self.buf[:idx]
            tam = self._tamanho()
            if tam == 0 or (tam > 0 and len(self.buf) < tam + (0 if final else 2)):
                break
            pacote = self._abrir(bytes(self.buf[:tam])) if tam > 0 else None
            if pacote is not None and len(self.buf) >= tam + 2 and self.buf[tam:tam + 2] != CABECALHO:
                pacote = None                # o próximo pacote tem de começar logo depois
            if pacote is None:
                self.invalidos += 1
                del self.buf[:2]
                continue
            del self.buf[:tam]
            if pacote[0] == "forma":
                self.n_pre = pacote[5]
                saida.append(pacote if tudo else pacote[1:5])
            else:
                if pacote[0] == "status":
                    self.status = pacote[2]
                    self.cfg_status = pacote[1]
                else:
                    self.n_picos += 1
                if tudo:
                    saida.append(pacote)
        return saida

    @staticmethod
    def _abrir(bruto):
        """Valida e decodifica um pacote inteiro; None se inválido."""
        cfg = bruto[2]
        if bruto.find(CABECALHO, 1) >= 0:
            return None
        if (cfg >> 4) & 7 == 1:
            cab, dados, n_pre = bruto[3:13], bruto[13:], N_PRE
        elif bruto[3] == 0:
            cab, dados, n_pre = bruto[8:18], bruto[18:], _campo7(bruto[6:8])
            if max(bruto[3:8]) > 0x7F:
                return None
        else:
            if max(bruto[2:]) > 0x7F:
                return None
            if bruto[3] == 1:
                area = _campo7(bruto[19:23], 28)
                return ("pico", cfg, _campo7(bruto[4:9]), _campo7(bruto[9:14]),
                        dict(pico4=_campo7(bruto[14:17], 16), base=_campo7(bruto[17:19], 14),
                             area=area - (1 << 28) if area >> 27 else area,
                             tpico=_campo7(bruto[23:25], 10), flags=bruto[25] & 0x1F))
            st = dict(versao_fw=bruto[4], limiar=_campo7(bruto[5:7], 14), confirma=bruto[7], modo=bruto[8],
                      saida=bruto[9], ativo=bruto[10], n_pre=_campo7(bruto[11:13], 10),
                      n_pos=_campo7(bruto[13:15], 10), ack=bruto[15], reg=bruto[16])
            if len(bruto) >= TAM_STATUS_V3:
                st.update(filtro=bruto[17], trap_k=_campo7(bruto[18:20], 8), trap_m=_campo7(bruto[20:22], 8),
                          trap_pz=_campo7(bruto[22:25], 16), trap_sh=bruto[25])
            return ("status", cfg, st)
        if max(cab) > 0x7F:
            return None
        d = np.frombuffer(dados, dtype=np.uint8)
        hi = d[0::2].astype(np.uint16)
        lo = d[1::2].astype(np.uint16)
        if np.any(hi > 0x3F):
            return None
        return ("forma", cfg, _campo7(cab[:5]), _campo7(cab[5:]), (hi << 8) | lo, n_pre)


class Desembrulhador:
    """Contadores de 32 bits do FPGA dão a volta (687 s com dt = 160 ns); acumula as voltas.
    Os contadores só crescem, então a diferença módulo 2^32 entre dois pacotes seguidos é o
    avanço real, desde que o intervalo seja menor que uma volta. Para intervalos maiores
    (taxa muito baixa), passe delta_esperado (ticks estimados por outro relógio) e as voltas
    inteiras que faltam são somadas."""

    MOD = 1 << 32

    def __init__(self):
        self.ult = None
        self.acum = 0

    def __call__(self, v, delta_esperado=None):
        if self.ult is None:
            self.acum = int(v)
        else:
            d = (int(v) - self.ult) % self.MOD
            if delta_esperado is not None and delta_esperado > d:
                d += int(round((delta_esperado - d) / self.MOD)) * self.MOD
            self.acum += d
        self.ult = int(v)
        return self.acum


def mediana5(y):
    """Mediana móvel de 5 amostras ao longo do último eixo."""
    from scipy.ndimage import median_filter
    return median_filter(y, size=(1,) * (y.ndim - 1) + (5,), mode="nearest")


def remover_espiculas(y, dt_us, limiar, larg_us=1.2, frac=0.6):
    """Remove espículas estreitas (até ~larg_us/2) sem tocar no pulso real.
    Uma amostra é espícula se foge da mediana móvel de ~larg_us por mais que
    max(limiar, frac x max(|amostra|, |mediana|)) -- ou seja, se ela é "quase toda espícula".
    Pulsos reais ficam abaixo de ~0,5 nesse critério (unipolar com qualquer shaping >= 0,5 us,
    bipolar com shaping >= 1 us a dt <= 0,2 us). Só as amostras marcadas são substituídas.
    Devolve (y_corrigido, mascara_de_espiculas)."""
    from scipy.ndimage import median_filter
    n = max(5, int(round(larg_us / dt_us)) | 1)          # ímpar
    m = median_filter(y, size=(1,) * (y.ndim - 1) + (n,), mode="nearest")
    dev = np.abs(y - m)
    esp = dev > np.maximum(limiar, frac * np.maximum(np.abs(y), np.abs(m)))
    return np.where(esp, m, y), esp


def suaviza3(y):
    s = y.copy()
    s[..., 1:-1] = (y[..., :-2] + y[..., 1:-1] + y[..., 2:]) / 3.0
    return s


def janelas(dt_us, base_ate_us=1.3, pre_janela_us=0.8, janela_us=10.0, n=N_AMOSTRAS, n_pre=N_PRE):
    """Índices: linha de base [0, n_base); busca do pulso [ini, fim)."""
    n_base = max(8, n_pre - int(round(base_ate_us / dt_us)))
    ini = max(n_base, n_pre - int(round(pre_janela_us / dt_us)))
    fim = min(n, n_pre + int(round(janela_us / dt_us)))
    return n_base, ini, fim


def altura_pico_lsb(amostras, dt_us, polaridade=1, filtro=True, limiar=82.0, **kw):
    """Altura de um evento (LSB): base = média do pré-trigger; pulso na polaridade
    positiva; remoção de espículas; suavização 3 pontos; máximo na janela.
    Disparo sem pulso real (só espícula) devolve 0."""
    n_base, ini, fim = janelas(dt_us, **kw)
    x = amostras.astype(np.float64)
    y = polaridade * (x - x[:n_base].mean())
    if filtro:
        y, _ = remover_espiculas(y, dt_us, limiar)
    h = float(suaviza3(y)[ini:fim].max())
    return h if h >= 0.8 * limiar else 0.0


def jordanov(y, k, m, tau_us, dt_us):
    """Filtro trapezoidal de Jordanov-Knoll (NIM A 345, 1994) com correção de polo-zero.
    y: (n, L) pulsos já sem a linha de base e na polaridade positiva (saída de pré-amplificador:
    subida rápida + decaimento exponencial tau_us; tau_us = inf para degrau sem decaimento).
    k = subida do trapézio (amostras), m = topo plano (amostras).
    Devolve o trapézio (n, L) normalizado: o topo vale a amplitude do pulso de entrada.
    Supõe sinal nulo antes do registro (linha de base limpa no pré-trigger)."""
    y = np.asarray(y, dtype=np.float64)
    k, m = int(k), int(m)
    l = k + m
    n, L = y.shape
    yp = np.concatenate([np.zeros((n, k + l)), y], axis=1)
    d = yp[:, k + l:] - yp[:, l:L + l] - yp[:, k:L + k] + yp[:, :L]
    if np.isfinite(tau_us):
        M = 1.0 / np.expm1(dt_us / tau_us)
        r = np.cumsum(d, axis=1) + M * d
        return np.cumsum(r, axis=1) / (k * (M + 1.0))
    return np.cumsum(d, axis=1) / k


def estimar_tau_us(y, dt_us, ini, f_alto=0.6, f_baixo=0.15):
    """Constante de decaimento (us) pela forma mediana normalizada dos pulsos y (n, L):
    reta em log entre f_alto e f_baixo do pico, na descida. Devolve None se não der."""
    y = np.asarray(y, dtype=np.float64)
    pk = y[:, ini:].max(axis=1)
    bom = pk > 0
    if bom.sum() < 20:
        return None
    med = np.median(y[bom] / pk[bom, None], axis=0)
    kp = ini + int(np.argmax(med[ini:]))
    desc = med[kp:]
    a = np.argmax(desc < f_alto) if (desc < f_alto).any() else 0
    b = np.argmax(desc < f_baixo) if (desc < f_baixo).any() else len(desc)
    if a == 0 or b - a < 6:
        return None
    t = np.arange(a, b) * dt_us
    incl = np.polyfit(t, np.log(desc[a:b]), 1)[0]
    return float(-1.0 / incl) if incl < 0 else None


def jordanov_fpga(v, k, m, pz4):
    """Modelo exato (inteiros) do rtl/jk_trapezio.v: v = códigos do ADC (1-D), história nula
    antes da primeira amostra. Devolve s (int64); o topo de um pulso de A LSB fica
    A * k * (pz4 + 4) acima da linha de base de s."""
    v = np.asarray(v, dtype=np.int64)
    l = int(k) + int(m)
    b = v.copy()
    b[k:] -= v[:-k]
    d = b.copy()
    d[l:] -= b[:-l]
    return np.cumsum(4 * np.cumsum(d) + int(pz4) * d)


def parametros_trapezio(subida_us, topo_us, tau_us, dt_us):
    """Registradores do filtro para o mca_top.v: dict(trap_k, trap_m, trap_pz, trap_sh) e a escala
    (contagens do campo PICO4 por LSB do ADC) quando o filtro está ligado."""
    k = int(round(subida_us / dt_us))
    m = int(round(topo_us / dt_us))
    pz4 = int(round(4.0 / np.expm1(dt_us / tau_us)))
    if not 2 <= k <= 255:
        raise ValueError(f"subida de {subida_us} us = {k} amostras de {dt_us * 1000:.0f} ns; o limite é 2..255 "
                         f"(mude log2_media)")
    if not 1 <= m <= 255:
        raise ValueError(f"topo de {topo_us} us = {m} amostras de {dt_us * 1000:.0f} ns; o limite é 1..255")
    if not 4 <= pz4 <= 65535:
        raise ValueError(f"tau de {tau_us} us fora da faixa para o passo de {dt_us * 1000:.0f} ns "
                         f"(de {dt_us * 0.9:.2f} a {dt_us * 16383:.0f} us)")
    sh = max(0, int(np.ceil(np.log2(k * (pz4 + 4) / 4.0))))
    return dict(trap_k=k, trap_m=m, trap_pz=pz4, trap_sh=sh)


def escala_trapezio(st):
    """Contagens do campo PICO4 por LSB do ADC, a partir do status (filtro ligado): entre 2 e 4."""
    return st["trap_k"] * (st["trap_pz"] + 4) / float(1 << st["trap_sh"])


def tau_do_pz(pz4, dt_us):
    return dt_us / np.log1p(4.0 / pz4)
