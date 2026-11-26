"""Confere os quadros Ethernet capturados na simulação (eth.hex): preâmbulo, FCS, IP, UDP."""
import sys, zlib, struct
def quadros(nome="eth.hex"):
    q, atual = [], []
    for l in open(nome):
        l = l.strip()
        if l == "--":
            if atual: q.append(bytes(atual)); atual = []
        elif l: atual.append(int(l, 16))
    if atual: q.append(bytes(atual))
    return q
def csum_ip(h):
    s = sum(struct.unpack(">10H", h)); s = (s & 0xFFFF) + (s >> 16); s = (s & 0xFFFF) + (s >> 16); return s
def abre(f, verboso=False):
    """Devolve o conteúdo UDP; levanta AssertionError se algo estiver errado."""
    assert f[:7] == b"\x55" * 7 and f[7] == 0xD5, "preâmbulo/SFD"
    q = f[8:]
    assert len(q) >= 64, f"quadro curto ({len(q)})"
    assert zlib.crc32(q[:-4]) == struct.unpack("<I", q[-4:])[0], "FCS"
    dst, src, et = q[:6], q[6:12], q[12:14]
    assert et == b"\x08\x00", "EtherType"
    ip = q[14:34]
    assert ip[0] == 0x45 and ip[9] == 17, "IPv4/UDP"
    assert csum_ip(ip) == 0xFFFF, "checksum IP"
    tot = struct.unpack(">H", ip[2:4])[0]
    sp, dp, ulen, uc = struct.unpack(">4H", q[34:42])
    assert ulen == tot - 20 and uc == 0, "UDP"
    dados = q[42:42 + ulen - 8]
    assert len(dados) == ulen - 8, "comprimento"
    assert all(b == 0 for b in q[42 + ulen - 8:-4]), "enchimento"
    if verboso:
        print(f"  dst {dst.hex(':')} src {src.hex(':')} {'.'.join(map(str, ip[12:16]))}:{sp} -> "
              f"{'.'.join(map(str, ip[16:20]))}:{dp} dados {len(dados)} bytes, quadro {len(q)} bytes")
    return dados
if __name__ == "__main__":
    import json
    sys.path.insert(0, ".")
    from confere_v1 import confere
    qs = quadros(); print(len(qs), "quadros")
    dados = b"".join(abre(f, i == 0) for i, f in enumerate(qs))
    sys.exit(0 if confere(dados, json.load(open("estimulo.json")), rotulo="UDP v1") else 1)
