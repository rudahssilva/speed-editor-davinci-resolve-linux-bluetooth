#!/usr/bin/env python3
"""parse_btmon.py - extrai as trocas ATT (reads/writes/notifications) de um log btmon.

Uso:
    ./parse_btmon.py [--all] /caminho/bt.log

Por padrao mostra so reports do Speed Editor (06 auth, 03 jog, 04 botoes, 02 LEDs).
--all mostra todas as PDUs.
"""
import re
import sys

ATT_RE = re.compile(r"ATT: (.+?) \(0x([0-9a-f]{2})\) len (\d+)")
HANDLE_RE = re.compile(r"Handle: (0x[0-9a-fA-F]+)")
DATAHDR_RE = re.compile(r"(?:Data|Value)\[\d*\]:")
HEXLINE_RE = re.compile(r"^\s+((?:[0-9a-fA-F]{2}\s+)+)")


def parse(path):
    events = []
    cur = None
    collecting = False
    with open(path, errors="replace") as f:
        for line in f:
            m = ATT_RE.search(line)
            if m:
                cur = {"op": m.group(1), "code": m.group(2), "len": m.group(3),
                       "handle": None, "data": None}
                collecting = False
                events.append(cur)
                continue
            if cur is None:
                continue
            m = HANDLE_RE.search(line)
            if m and cur["handle"] is None:
                cur["handle"] = m.group(1)
                continue
            if DATAHDR_RE.search(line):
                collecting = True
                if cur["data"] is None:
                    cur["data"] = ""
                continue
            if collecting:
                m2 = HEXLINE_RE.match(line)
                if m2:
                    cur["data"] = (cur["data"] or "") + m2.group(1).strip() + " "
                else:
                    collecting = False
    for e in events:
        if e["data"] is not None:
            e["data"] = e["data"].strip()
    return events


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else "/tmp/bt.txt"
    only_speed_editor = "--all" not in sys.argv

    events = parse(path)
    shown = 0
    for e in events:
        if e["data"] is None and e["handle"] is None:
            continue
        data = e["data"] or ""
        if only_speed_editor and not re.match(r"^(0?6|0?3|0?4|0?2)\b", data, re.I):
            continue
        print(f'{e["op"]:<26} code=0x{e["code"]} len={e["len"]:<3} h={e["handle"] or "-":<8} {data}')
        shown += 1

    print(f"\n--- {shown} PDUs mostrados de {len(events)} no arquivo", file=sys.stderr)


if __name__ == "__main__":
    main()
