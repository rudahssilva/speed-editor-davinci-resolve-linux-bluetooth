#!/usr/bin/env python3
"""read_hid.py - testa o Speed Editor: autentica, le os reports e (opcional) acende LED.

Uso:
    ./read_hid.py              # acha o hidraw do Speed Editor, autentica, le
    ./read_hid.py --led        # alem de ler, pisca o LED "CUT" (testa o caminho de saida)
    ./read_hid.py /dev/hidraw4

Se autenticar e aparecerem reports ao apertar botoes, o transporte (USB ou
Bluetooth) esta 100% funcional no nivel do kernel + HID.

O handshake segue o trabalho documentado em:
  - https://github.com/smunaut/blackmagic-misc  (auth original)
  - crate bmdse / @blackmagic-controller        (mesma sequencia)
"""
import fcntl
import glob
import os
import select
import struct
import sys
import time

VID = "1EDB"
PID = "DA0E"

DEBUG = False
DELAY = 0.0


# ---- ioctls de HID ----
def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (0x48 << 8) | nr


def HIDIOCGFEATURE(size: int) -> int:  # noqa: N802
    return _ioc(3, 0x07, size)  # _IOC_READ|_IOC_WRITE


def HIDIOCSFEATURE(size: int) -> int:  # noqa: N802
    return _ioc(3, 0x06, size)


MASK64 = 0xFFFFFFFFFFFFFFFF

AUTH_EVEN = [
    0x3AE1206F97C10BC8, 0x2A9AB32BEBF244C6, 0x20A6F8B8DF9ADF0A, 0xAF80ECE52CFC1719,
    0xEC2EE2F7414FD151, 0xB055ADFD73344A15, 0xA63D2E3059001187, 0x751BF623F42E0DDE,
]
AUTH_ODD = [
    0x3E22B34F502E7FDE, 0x24656B981875AB1C, 0xA17F3456DF7BF8C3, 0x6DF72E1941AEF698,
    0x72226F011E66AB94, 0x3831A3C606296B42, 0xFD7FF81881332C89, 0x61A3F6474FF236C6,
]
MASK = 0xA79A63F585D37BF0


def rol8(v: int) -> int:
    return ((v << 56) | (v >> 8)) & MASK64


def bmd_kbd_auth(challenge: int) -> int:
    n = challenge & 7
    v = challenge
    for _ in range(n):
        v = rol8(v)
    if (v & 1) == ((0x78 >> n) & 1):
        k = AUTH_EVEN[n]
    else:
        v ^= rol8(v)
        k = AUTH_ODD[n]
    return (v ^ (rol8(v) & MASK) ^ k) & MASK64


def send_feature(fd: int, data: bytes) -> None:
    fcntl.ioctl(fd, HIDIOCSFEATURE(len(data)), bytearray(data))


def get_feature(fd: int, report_id: int, size: int = 10) -> bytes:
    buf = bytearray(size)
    buf[0] = report_id
    res = fcntl.ioctl(fd, HIDIOCGFEATURE(size), buf, True)
    return bytes(res if isinstance(res, (bytes, bytearray)) else buf)


CONVS = {
    "LE(8)": lambda b: int.from_bytes(b, "little"),
    "BE(8)": lambda b: int.from_bytes(b, "big"),
    "LE(7)": lambda b: int.from_bytes(b[:7], "little"),
    "BE(7)": lambda b: int.from_bytes(b[:7], "big"),
}


def authenticate(fd: int, conv=None, order: str = "little", verbose: bool = None,
                 *, reset: bool = True, our_chal: bytes = None, polls: int = 1) -> int:
    """Faz o handshake. Retorna o timeout (s) ate precisar autenticar de novo."""
    show = DEBUG if verbose is None else verbose
    conv = conv or CONVS["LE(8)"]
    our_chal = our_chal or bytes(8)

    def dbg(label: str, data: bytes) -> None:
        if not show:
            return
        step = f"step=0x{data[1]:02x}" if len(data) > 1 else ""
        print(f"    [debug] {label:21s} {data.hex(' ')}  {step}".rstrip())

    if reset:
        pkt = bytes([0x06] + [0] * 9)
        send_feature(fd, pkt)
        dbg("SET reset", pkt)
        time.sleep(DELAY)

    ch = get_feature(fd, 0x06)
    dbg("GET challenge", ch)
    time.sleep(DELAY)
    if len(ch) < 10 or ch[0] != 0x06 or ch[1] != 0x00:
        raise RuntimeError(f"resposta inesperada no challenge: {ch.hex(' ')}")
    challenge = conv(ch[2:10])
    dbg("challenge interpretado", challenge.to_bytes(8, "little"))

    pkt = bytes([0x06, 0x01]) + our_chal
    send_feature(fd, pkt)
    dbg("SET nosso challenge", pkt)
    time.sleep(DELAY)

    rsp = get_feature(fd, 0x06)
    dbg("GET resposta", rsp)
    time.sleep(DELAY)

    response = bmd_kbd_auth(challenge)
    pkt = bytes([0x06, 0x03]) + response.to_bytes(8, order)
    send_feature(fd, pkt)
    dbg("SET nossa resposta", pkt)
    time.sleep(DELAY)

    st = bytes(10)
    for _ in range(max(1, polls)):
        st = get_feature(fd, 0x06)
        dbg("GET status", st)
        if len(st) >= 10 and st[1] == 0x04:
            return int.from_bytes(st[2:4], "little")
        time.sleep(0.05)
    raise RuntimeError(f"rejeitado (step=0x{st[1]:02x})")


def ble_tricks(fd: int) -> bool:
    """Tenta estrategias alternativas de auth (para o Bluetooth)."""
    strategies = [
        ("padrao", {}),
        ("sem reset", {"reset": False}),
        ("challenge aleatorio", {"our_chal": os.urandom(8)}),
        ("aleatorio + sem reset", {"reset": False, "our_chal": os.urandom(8)}),
        ("poll 10x apos 0x03", {"polls": 10}),
        ("aleatorio + poll 10x", {"our_chal": os.urandom(8), "polls": 10}),
        ("sem reset + resposta BE", {"reset": False, "order": "big"}),
        ("aleatorio + BE", {"our_chal": os.urandom(8), "order": "big"}),
        ("sem reset + poll + BE", {"reset": False, "order": "big", "polls": 10}),
        ("tudo junto", {"reset": False, "order": "big", "polls": 10, "our_chal": os.urandom(8)}),
    ]
    for name, kw in strategies:
        try:
            timeout = authenticate(fd, verbose=False, **kw)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:24s} -> {exc}")
        else:
            print(f"  {name:24s} -> OK  (timeout {timeout}s)")
            return True
        time.sleep(0.2)
    return False


def try_variants(fd: int) -> bool:
    """Testa interpretacoes de challenge e ordem de resposta ate uma funcionar."""
    combos = [(f"{cname} / resposta {order}", conv, order)
              for cname, conv in CONVS.items()
              for order in ("little", "big")]
    for name, conv, order in combos:
        try:
            timeout = authenticate(fd, conv, order, verbose=False)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:28s} -> {exc}")
        else:
            print(f"  {name:28s} -> OK  (timeout {timeout}s)")
            return True
        time.sleep(0.05)
    return False


BUTTONS = {
    0x0001: "SmartInsert", 0x0002: "Append", 0x0003: "RippleOverwrite", 0x0004: "CloseUp",
    0x0005: "PlaceOnTop", 0x0006: "SourceOverwrite", 0x0007: "In", 0x0008: "Out",
    0x0009: "TrimIn", 0x000A: "TrimOut", 0x000B: "Roll", 0x000C: "SlipSource",
    0x000D: "SlipDestination", 0x000E: "TransitionDuration", 0x000F: "Cut",
    0x0010: "Dissolve", 0x0011: "SmoothCut", 0x001A: "Source", 0x001B: "Timeline",
    0x001C: "Shuttle", 0x001D: "Jog", 0x001E: "Scroll", 0x001F: "SyncBin",
    0x0022: "Transition", 0x0025: "VideoOnly", 0x0026: "AudioOnly", 0x002B: "RippleDelete",
    0x002C: "AudioLevel", 0x002D: "FullView", 0x002E: "Snap", 0x002F: "Split",
    0x0030: "LiveOverwrite", 0x0031: "Escape", 0x0033: "Cam1", 0x0034: "Cam2",
    0x0035: "Cam3", 0x0036: "Cam4", 0x0037: "Cam5", 0x0038: "Cam6", 0x0039: "Cam7",
    0x003A: "Cam8", 0x003B: "Cam9", 0x003C: "StopPlay",
}

WHEEL_MODES = {0x00: "relativo", 0x01: "absoluto continuo", 0x03: "absoluto dead-zero"}

LED_CUT = 1 << 1  # ButtonLed::Cut


def find_device(bus: str = None):
    """Retorna o /dev/hidraw do Speed Editor. bus='0003' = USB, '0005' = Bluetooth."""
    for uevent in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
        try:
            with open(uevent) as f:
                text = f.read()
        except OSError:
            continue
        upper = text.upper()
        if VID not in upper or PID not in upper:
            continue
        if bus and f"HID_ID={bus}:" not in upper:
            continue
        node = os.path.basename(os.path.dirname(os.path.dirname(uevent)))
        return f"/dev/{node}"
    return None


def auth_only(log: str = "/tmp/speed-editor-auth.log") -> int:
    """Autentica o painel no barramento USB e sai. Usado pela regra udev."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    result = "sem dispositivo usb"
    for _ in range(15):
        dev = find_device("0003")
        if not dev:
            time.sleep(0.1)
            continue
        try:
            fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
        except OSError as exc:
            result = f"{dev}: {exc}"
            time.sleep(0.1)
            continue
        try:
            timeout = authenticate(fd, verbose=False)
            result = f"{dev}: OK (re-auth {timeout}s)"
            code = 0
        except Exception as exc:  # noqa: BLE001
            result = f"{dev}: {exc}"
            code = 1
        finally:
            os.close(fd)
        try:
            with open(log, "a") as f:
                f.write(f"{stamp} {result}\n")
        except OSError:
            pass
        return code
    try:
        with open(log, "a") as f:
            f.write(f"{stamp} {result}\n")
    except OSError:
        pass
    return 1


def describe(data: bytes) -> str:
    rid = data[0]
    if rid == 0x04 and len(data) == 13:
        codes = [int.from_bytes(data[i:i + 2], "little") for i in range(1, 13, 2)]
        names = [BUTTONS.get(c, f"0x{c:04x}") for c in codes if c]
        return f"botoes: {', '.join(names) if names else '(nenhum)'}"
    if rid == 0x03 and len(data) == 7:
        mode = WHEEL_MODES.get(data[1], f"0x{data[1]:02x}")
        value = struct.unpack("<i", data[2:6])[0]
        return f"jog: modo={mode} valor={value}"
    if rid == 0x07 and len(data) == 3:
        return f"bateria: carregando={bool(data[1])} nivel={data[2]}%"
    if rid == 0x06:
        return f"bateria/info: {data.hex(' ')}"
    return ""


def main() -> int:
    global DEBUG, DELAY

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    want_led = "--led" in sys.argv
    want_auth = "--no-auth" not in sys.argv
    want_variants = "--variants" in sys.argv
    want_tricks = "--ble-tricks" in sys.argv
    DEBUG = "--debug" in sys.argv
    if "--slow" in sys.argv:
        DELAY = 0.15

    if "--auth-only" in sys.argv:
        return auth_only()

    dev = args[0] if args else find_device()
    if not dev:
        print("Speed Editor nao encontrado (VID 1EDB / PID DA0E).", file=sys.stderr)
        return 1

    print(f"abrindo {dev} ...")
    try:
        fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    except PermissionError:
        print(f"SEM PERMISSAO em {dev}.\nRode: sudo ./install-udev.sh", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"erro ao abrir {dev}: {exc}", file=sys.stderr)
        return 2

    if want_tricks:
        print("testando estrategias de auth para Bluetooth...\n")
        if ble_tricks(fd):
            print("\n>> alguma estrategia funcionou (veja qual, acima)")
            return 0
        print("\n>> nenhuma estrategia funcionou")
        return 3

    if want_variants:
        print("testando variantes de interpretacao do challenge...\n")
        if try_variants(fd):
            print("\n>> alguma variante FUNCIONOU (veja qual, acima)")
            return 0
        print("\n>> nenhuma variante funcionou")
        return 3

    if want_auth:
        print("autenticando (handshake feature report 0x06)...")
        try:
            timeout = authenticate(fd)
            print(f"autenticado OK (re-auth em ~{timeout}s)")
        except Exception as exc:  # noqa: BLE001
            print(f"FALHA na autenticacao: {exc}", file=sys.stderr)
            print("(o transporte chegou, mas o handshake nao completou)", file=sys.stderr)
            if "--debug" not in sys.argv:
                print("rode com --debug para ver cada etapa", file=sys.stderr)
            return 3
    else:
        print("pulando autenticacao (--no-auth)")

    if want_led:
        os.write(fd, bytes([0x02]) + LED_CUT.to_bytes(4, "little"))
        time.sleep(0.6)
        os.write(fd, bytes([0x02]) + (0).to_bytes(4, "little"))
        print("LED 'CUT' piscou (se voce viu, o caminho de SAIDA funciona)")

    print("\nok. aperte botoes e gire o jog. Ctrl+C para sair.\n")
    want_stats = "--stats" in sys.argv
    times = []
    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 1.0)
            if not ready:
                continue
            data = os.read(fd, 64)
            if not data:
                continue
            now = time.monotonic()
            if want_stats:
                times.append(now)
                continue
            extra = describe(data)
            print(f"report 0x{data[0]:02x} {data.hex(' ')}")
            if extra:
                print(f"    -> {extra}")
    except KeyboardInterrupt:
        print("\nsaindo.")
    finally:
        os.close(fd)

    if want_stats and times:
        dur = times[-1] - times[0]
        gaps = sorted(b - a for a, b in zip(times, times[1:]))
        if gaps:
            big = sum(1 for g in gaps if g > 0.1)
            print("\n=== stats ===")
            print(f"reports: {len(times)}  em {dur:.1f}s  (media {len(times)/dur if dur else 0:.1f}/s)")
            print(f"gap min {gaps[0]*1000:.0f}ms / mediana {gaps[len(gaps)//2]*1000:.0f}ms / "
                  f"95% {gaps[int(len(gaps)*0.95)]*1000:.0f}ms / max {gaps[-1]*1000:.0f}ms")
            print(f"gaps > 100ms: {big} de {len(gaps)}")
            print("liso = mediana baixa (<20ms) e poucos gaps grandes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
