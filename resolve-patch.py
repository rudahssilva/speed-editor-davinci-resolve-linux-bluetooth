#!/usr/bin/env python3
"""resolve-patch.py — corrige os 3 checks de tamanho do DaVinci Resolve.

O Resolve compara o retorno de HIDIOCGFEATURE com o tamanho *truncado* que o
BlueZ (bugado) devolvia (7/32/9). Com o BlueZ corrigido (upstream dc2eb1394f)
o ioctl devolve o tamanho certo (8/33/10) e o Resolve rejeita o painel:
"BlueZ daemon version too old, reports malformed data."

Em vez de offsets fixos por versao, este script ACHA as tres comparacoes:

    ioctl(... HIDIOCGFEATURE(len) ...)   ; const base 0xc0004807
    test eax, eax
    js   <erro>
    cmp  eax, N                          ; <- N = 7 / 32 / 9

assinatura procurada: 85 C0 0F 88 <rel32> 83 F8 <N>, com o `07 48 00 C0`
(constante-base do ioctl) ate 64 bytes antes. Patch: N -> N+1.

Uso:
    sudo ./resolve-patch.py              aplica (faz backup na 1a vez)
    sudo ./resolve-patch.py --status     so mostra o estado
    sudo ./resolve-patch.py --restore    volta o backup .pre-resolve-patch
    ./resolve-patch.py --bin /caminho    binario alternativo
                                         (container: aponte para o binario montado)

Reaplique depois de cada atualizacao do Resolve.
"""
import argparse
import mmap
import os
import re
import shutil
import sys

DEFAULT_BIN = os.environ.get("RESOLVE_BIN", "/opt/resolve/bin/resolve")
BACKUP_SUFFIX = ".pre-resolve-patch"

# tamanhos truncados (o que o Resolve espera hoje) -> tamanhos corretos
SIZES = {7: 8, 32: 33, 9: 10}

IOCTL_BASE = b"\x07\x48\x00\xc0"          # HIDIOCGFEATURE(len) sem o len
SIG = re.compile(rb"\x85\xc0\x0f\x88....\x83\xf8(.)", re.S)


def find_checks(m):
    """devolve [(offset_do_imediato, valor_atual)] das 3 comparacoes"""
    found = []
    for mo in SIG.finditer(m):
        cur = mo.group(1)[0]
        if cur not in SIZES and cur not in SIZES.values():
            continue
        cmp_off = mo.start(1)
        if IOCTL_BASE not in m[max(0, cmp_off - 64):cmp_off]:
            continue
        found.append((cmp_off, cur))
    # dedup mantendo ordem
    seen, out = set(), []
    for off, cur in found:
        if off not in seen:
            seen.add(off)
            out.append((off, cur))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()

    path = a.bin
    if not os.path.exists(path):
        sys.exit(f"erro: {path} nao encontrado")

    backup = path + BACKUP_SUFFIX

    if a.restore:
        if not os.path.exists(backup):
            sys.exit(f"erro: backup {backup} nao existe")
        if os.geteuid() != 0:
            sys.exit("precisa de root: sudo ./resolve-patch.py --restore")
        shutil.copy2(backup, path)
        print(f"restaurado {path} a partir de {backup}")
        return

    f = open(path, "rb")
    m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    checks = find_checks(m)
    m.close()
    f.close()

    if a.status:
        for off, cur in checks:
            want = SIZES.get(cur, cur)
            state = "ok   " if cur == want else "FALTA"
            print(f"{state} offset 0x{off:X}: {cur} (esperado {want})")
        if len(checks) != 3:
            print(f"aviso: achei {len(checks)} comparacoes (esperava 3)", file=sys.stderr)
        return

    # Never write into a half-recognised binary: with fewer (or more) than three
    # checks the patch does not make Resolve work, and a false positive would
    # corrupt an unrelated instruction.
    if len(checks) != 3:
        sys.exit("erro: achei %d comparacoes (esperava 3): %s\n"
                 "Nada foi alterado. Se for uma versao nova do Resolve, a "
                 "Blackmagic pode ter mudado o codigo (ou corrigido os checks)."
                 % (len(checks),
                    ", ".join(f"0x{o:X}={c}" for o, c in checks) or "nenhuma"))

    if os.geteuid() != 0:
        sys.exit("precisa de root: sudo ./resolve-patch.py")

    todo = [(off, cur) for off, cur in checks if cur in SIZES]
    if not todo:
        print("tudo ja corrigido.")
        return

    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        print(f"backup: {backup}")

    with open(path, "r+b") as fh:
        for off, cur in todo:
            fh.seek(off)
            fh.write(bytes([SIZES[cur]]))
            print(f"offset 0x{off:X}: {cur} -> {SIZES[cur]} OK")

    print("pronto. Feche e reabra o Resolve.")


if __name__ == "__main__":
    main()
