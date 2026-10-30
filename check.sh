#!/usr/bin/env bash
# check.sh - diagnostico do Speed Editor no Linux (rode como usuario normal, SEM sudo)
#
# Responde: o dispositivo existe? em que barramento? o seu usuario pode abrir?
set -uo pipefail

echo "=== nodes hidraw da Blackmagic (VID 1edb) ==="
found=0
for u in /sys/class/hidraw/hidraw*/device/uevent; do
    [ -e "$u" ] || continue
    id=$(grep -o 'HID_ID=[0-9A-Fa-f:]*' "$u" 2>/dev/null | cut -d= -f2)
    case "$id" in *1EDB*|*1edb*) ;; *) continue ;; esac
    found=1
    node=$(basename "$(dirname "$(dirname "$u")")")
    name=$(grep -o 'HID_NAME=.*' "$u" | cut -d= -f2-)
    bus=${id%%:*}
    case "$bus" in
        0003)      bus_txt="USB" ;;
        0005)      bus_txt="Bluetooth (HID-over-GATT)" ;;
        *)         bus_txt="bus $bus" ;;
    esac
    echo
    echo "--- /dev/$node  [$bus_txt]"
    echo "    nome : $name"
    echo "    id   : $id"
    ls -l "/dev/$node" 2>&1 | sed 's/^/    /'
    grp=$(stat -c %G "/dev/$node" 2>/dev/null || echo "?")
    if id -nG | tr ' ' '\n' | grep -qx "$grp"; then
        in_grp="sim"
    else
        in_grp="NAO"
    fi
    echo "    grupo: $grp  (voce pertence? $in_grp)"
    echo "    seu usuario: $(id -un)  grupos: $(id -nG)"
    if head -c 0 "/dev/$node" 2>/dev/null; then
        echo "    acesso: OK (seu usuario consegue abrir)"
    else
        echo "    acesso: BLOQUEADO"
    fi
done

if [ "$found" = 0 ]; then
    echo "Nenhum dispositivo Blackmagic encontrado em /sys/class/hidraw."
    echo "Confira se ele esta ligado e conectado (USB ou Bluetooth)."
    exit 1
fi

echo
echo "=== dica ==="
echo "BLOQUEADO? rode:  sudo ./install-udev.sh"
echo "(o script usa o seu grupo primario, nao precisa de logout)"
