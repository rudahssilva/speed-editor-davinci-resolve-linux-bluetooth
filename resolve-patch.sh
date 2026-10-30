#!/bin/bash
# resolve-patch.sh — corrige os 3 checks de tamanho no binario do DaVinci Resolve
# que exigem o comportamento BUGADO do BlueZ (retorno truncado do GET_FEATURE).
#
# Contexto: com o BlueZ corrigido (commit dc2eb1394f), o ioctl HIDIOCGFEATURE
# retorna o tamanho CORRETO (ID + dados). O Resolve 19.1.x compara com o
# tamanho truncado (so os dados) e rejeita o painel no Bluetooth:
#   "BlueZ daemon version too old, reports malformed data."
#
# Os checks sao tres `cmp eax, N` em /opt/resolve/bin/resolve (19.1.x):
#   off 0x4002C71: 0x07 -> 0x08  (report 0x01, 7 dados)
#   off 0x4003C05: 0x20 -> 0x21  (report 0x08, 32 dados)
#   off 0x40041F6: 0x09 -> 0x0A  (report 0x06, 9 dados / auth)
#
# Uso:
#   podman exec -u root davincibox sh /caminho/resolve-patch.sh      aplica
#   podman exec -u root davincibox sh /caminho/resolve-patch.sh --status  so verifica
#
# Reaplique apos cada atualizacao do Resolve (o instalador sobrescreve o binario).

set -uo pipefail
BIN="${RESOLVE_BIN:-/opt/resolve/bin/resolve}"
STATUS_ONLY="${1:-}"

if [ "$(id -u)" != "0" ]; then
    echo "Este script deve rodar como root dentro do container. Ex.:"
    echo "  podman exec -u root <container> sh $0"
    exit 1
fi

if [ ! -f "$BIN" ]; then
    echo "erro: $BIN nao encontrado" >&2
    exit 1
fi

state_byte() { # $1=offset
    dd if="$BIN" bs=1 skip="$1" count=1 2>/dev/null | od -An -t u1 | tr -d ' '
}

O1=$((0x4002C71)); V1=8   # 0x07 -> 0x08
O2=$((0x4003C05)); V2=33  # 0x20 -> 0x21
O3=$((0x40041F6)); V3=10  # 0x09 -> 0x0A

b1=$(state_byte $O1); b2=$(state_byte $O2); b3=$(state_byte $O3)

status() {
    local off=$1 cur=$2 want=$3
    if [ "$cur" = "$want" ]; then printf 'ok    '; else printf 'FALTA '; fi
    printf 'offset 0x%X: %s (esperado %s)\n' "$off" "$cur" "$want"
}
status $O1 "$b1" "$V1"
status $O2 "$b2" "$V2"
status $O3 "$b3" "$V3"

if [ "$STATUS_ONLY" = "--status" ]; then
    exit 0
fi

# guarda um backup antes de mexer
if [ ! -f "$BIN.pre-resolve-patch" ]; then
    cp -p "$BIN" "$BIN.pre-resolve-patch"
fi

patch_byte() { # $1=offset $2=antigo $3=novo
    local off=$1 old=$2 new=$3 cur
    cur=$(state_byte "$off")
    if [ "$cur" = "$new" ]; then
        echo "offset $off: ja corrigido"
        return 0
    fi
    if [ "$cur" != "$old" ]; then
        echo "offset $off: byte inesperado ($cur != $old). Versao do Resolve mudou?" >&2
        echo "NAO alterado. Ajuste os offsets no script conforme a versao." >&2
        return 1
    fi
    printf "\\$(printf '%03o' "$new")" | dd of="$BIN" bs=1 seek="$off" conv=notrunc 2>/dev/null
    echo "offset $off: $old -> $new OK"
    return 0
}

rc=0
patch_byte $O1 7 8 || rc=1
patch_byte $O2 32 33 || rc=1
patch_byte $O3 9 10 || rc=1

if [ "$rc" = 0 ]; then
    echo "pronto. Feche e reabra o Resolve."
else
    echo "patch incompleto — veja acima."
fi
exit $rc
