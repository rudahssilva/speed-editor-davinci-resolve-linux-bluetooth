#!/usr/bin/env python3
"""bluez-probe.py — detecta o bug do BlueZ (GET_REPORT truncado) em runtime.

Le o report 0x01 (7 bytes de dados) do Speed Editor via HIDIOCGFEATURE com
buffer de 8 bytes, como o Resolve faz:
  ret == 7  -> BlueZ bugado (perde o ultimo byte)
  ret == 8  -> BlueZ corrigido (ID + 7 dados)
Saida:
  0 = corrigido
  2 = bugado
  1 = painel nao encontrado / sem acesso
"""
import fcntl, glob, os, sys


def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("H") << 8) | nr


def GFEATURE(size):
    return _ioc(3, 0x07, size)


def find_hidraw(bus=None):
    for ue in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
        try:
            text = open(ue).read().upper()
        except OSError:
            continue
        if "1EDB" not in text or "DA0E" not in text:
            continue
        if bus and f"HID_ID={bus}:" not in text:
            continue
        return "/dev/" + ue.split("/")[4]
    return None


def main():
    dev = find_hidraw("0005") or find_hidraw("0003")
    if not dev:
        print("Speed Editor nao encontrado (nem USB nem BLE).")
        return 1
    try:
        fd = os.open(dev, os.O_RDWR)
    except OSError as e:
        print(f"sem acesso a {dev}: {e}")
        print("rode: sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw")
        return 1
    buf = bytearray(8)
    buf[0] = 0x01
    try:
        ret = fcntl.ioctl(fd, GFEATURE(8), buf, True)
    except OSError as e:
        print(f"ioctl falhou em {dev}: {e}")
        return 1
    print(f"GET_FEATURE(report 0x01) retornou {ret} (buf={bytes(buf).hex(' ')})")
    if ret == 8:
        print("BlueZ: OK (tamanho correto).")
        return 0
    if ret == 7:
        print("BlueZ: BUGADO (ultimo byte truncado). Aplique o patch.")
        return 2
    print(f"BlueZ: valor inesperado ({ret}); assumindo problema.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
