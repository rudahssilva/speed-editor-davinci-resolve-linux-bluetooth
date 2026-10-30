#!/usr/bin/env python3
"""ble_auth.py - autentica o Speed Editor pelo Bluetooth.

Estrategia: o caminho hidraw entrega o challenge com o ultimo byte zerado
(bug do stack HID-over-GATT do BlueZ), e o BlueZ bloqueia WRITES via D-Bus.
Entao dividimos: WRITES pelo hidraw (chegam corretos no ar), READS direto
no GATT via D-Bus (chegam intactos).

Uso:
    ./ble_auth.py                 # autentica uma vez
    ./ble_auth.py --watch         # daemon: re-autentica a cada 500s
    ./ble_auth.py --verbose       # mostra cada etapa

O algoritmo de autenticacao (bmd_kbd_auth) vem de
https://github.com/smunaut/blackmagic-misc (Apache-2.0); veja NOTICE.
"""
import dbus
import fcntl
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from read_hid import HIDIOCSFEATURE, bmd_kbd_auth, find_device  # noqa: E402

BUS = dbus.SystemBus()
REPORT_REF_UUID = "00002908-0000-1000-8000-00805f9b34fb"

VERBOSE = "--verbose" in sys.argv


def log(msg):
    if VERBOSE:
        print(msg)


def managed_objects():
    om = dbus.Interface(BUS.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
    return om.GetManagedObjects()


def find_device_path():
    """Acha o Speed Editor conectado pelo Modalias (usb:v1EDBpDA0E...)."""
    for path, ifaces in managed_objects().items():
        if "org.bluez.Device1" not in ifaces:
            continue
        props = ifaces["org.bluez.Device1"]
        modalias = (props.get("Modalias") or "").upper()
        if "1EDB" in modalias and "DA0E" in modalias and props.get("Connected"):
            return path
    return None


def find_feature_char(dev_path):
    for path, ifaces in managed_objects().items():
        if not path.startswith(dev_path + "/"):
            continue
        if "org.bluez.GattDescriptor1" not in ifaces:
            continue
        if ifaces["org.bluez.GattDescriptor1"].get("UUID") != REPORT_REF_UUID:
            continue
        try:
            d = dbus.Interface(BUS.get_object("org.bluez", path), "org.bluez.GattDescriptor1")
            val = bytes(d.ReadValue({}))
        except Exception:  # noqa: BLE001
            continue
        if len(val) == 2 and val[0] == 0x06 and val[1] == 0x03:
            return path.rsplit("/", 1)[0]
    return None


def gatt_read(char_path) -> bytes:
    ch = dbus.Interface(BUS.get_object("org.bluez", char_path), "org.bluez.GattCharacteristic1")
    return bytes(ch.ReadValue({}))


def gatt_read_until(char_path, want_step: int, tries: int = 10, delay: float = 0.15) -> bytes:
    """Le ate aparecer o step esperado (o painel processa o write de forma assincrona)."""
    last = b""
    for _ in range(tries):
        last = gatt_read(char_path)
        if len(last) >= 9 and last[0] == want_step:
            return last
        time.sleep(delay)
    return last


def send_feature_hid(fd, data: bytes):
    fcntl.ioctl(fd, HIDIOCSFEATURE(len(data)), bytearray(data))


def handshake(fd, char_path) -> int:
    # reset (via hidraw, chega certo no ar)
    send_feature_hid(fd, bytes([0x06] + [0] * 9))
    ch = gatt_read_until(char_path, 0x00)
    log(f"challenge GATT: {ch.hex(' ')}")
    if len(ch) < 9 or ch[0] != 0x00:
        raise RuntimeError(f"challenge inesperado: {ch.hex(' ')}")
    challenge = int.from_bytes(ch[1:9], "little")
    log(f"challenge intacto: {ch[1:9].hex(' ')} = {hex(challenge)}")

    # nosso challenge (zeros)
    send_feature_hid(fd, bytes([0x06, 0x01] + [0] * 8))
    rsp = gatt_read_until(char_path, 0x02)
    log(f"resposta deles : {rsp.hex(' ')}")
    if len(rsp) < 9 or rsp[0] != 0x02:
        raise RuntimeError(f"step 0x02 inesperado: {rsp.hex(' ')}")

    # nossa resposta
    response = bmd_kbd_auth(challenge)
    send_feature_hid(fd, bytes([0x06, 0x03]) + response.to_bytes(8, "little"))
    st = gatt_read_until(char_path, 0x04, tries=15, delay=0.2)
    log(f"status         : {st.hex(' ')}")
    if len(st) < 9 or st[0] != 0x04:
        raise RuntimeError(f"rejeitado (step=0x{st[0]:02x})")
    return int.from_bytes(st[1:3], "little")


def open_hid():
    dev = find_device("0005")
    if not dev:
        return None, None
    try:
        return os.open(dev, os.O_RDWR | os.O_NONBLOCK), dev
    except OSError as exc:
        print(f"erro ao abrir {dev}: {exc}", file=sys.stderr)
        return None, dev


def main():
    dev_path = find_device_path()
    if not dev_path:
        print("Speed Editor nao encontrado no Bluetooth", file=sys.stderr)
        return 1
    char = find_feature_char(dev_path)
    fd, dev = open_hid()
    if not char:
        print("caracteristica do feature report 0x06 nao encontrada", file=sys.stderr)
        return 1
    if fd is None:
        print("hidraw do Speed Editor (Bluetooth) nao encontrado", file=sys.stderr)
        return 1

    try:
        if "--watch" in sys.argv:
            print("daemon: re-autenticando a cada 500s (Ctrl+C para sair)")
            while True:
                try:
                    t = handshake(fd, char)
                    print(f"{time.strftime('%H:%M:%S')} autenticado OK (timeout {t}s)")
                    time.sleep(max(10, t - 100))
                except KeyboardInterrupt:
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"{time.strftime('%H:%M:%S')} falhou: {exc}", file=sys.stderr)
                    # o link pode ter caido: reabre tudo e tenta de novo
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    time.sleep(20)
                    while True:
                        dev_path = find_device_path()
                        if dev_path:
                            new_char = find_feature_char(dev_path)
                            if new_char:
                                char = new_char
                        fd, dev = open_hid()
                        if fd is not None:
                            break
                        print("    aguardando dispositivo...", file=sys.stderr)
                        time.sleep(10)
            return 0

        t = handshake(fd, char)
    except Exception as exc:  # noqa: BLE001
        print(f"FALHA: {exc}", file=sys.stderr)
        return 1
    finally:
        os.close(fd)

    print(f"autenticado OK pelo ar (timeout {t}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
