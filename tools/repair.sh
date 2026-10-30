#!/usr/bin/env bash
# repair.sh - refaz o pareamento do Speed Editor no Linux.
#
# Use DEPOIS de resetar o painel: segure CUT + SMTH CUT por ~3s
# (todos os LEDs piscam fraquinho ao soltar).
#
# O Speed Editor so guarda um host por vez. Se ele estiver pareado com
# outra maquina (Mac/Windows), "esqueca" o dispositivo la tambem.
set -uo pipefail

MAC="${1:-80:4B:50:69:A3:C1}"

echo "==> removendo entrada antiga ($MAC)"
bluetoothctl remove "$MAC" 2>/dev/null

echo "==> escaneando por 20s (o painel deve aparecer como 'Speed Editor')"
timeout 20 bluetoothctl scan on >/dev/null 2>&1 &
SCAN=$!

# espera o dispositivo aparecer no scan
for _ in $(seq 1 20); do
    if bluetoothctl devices 2>/dev/null | grep -qi "$MAC"; then
        echo "    encontrado."
        break
    fi
    sleep 1
done

echo "==> pareando"
timeout 40 bluetoothctl --timeout 35 pair "$MAC" | grep -iE 'pair|fail|error|auth' || true

echo "==> marcando como confiavel"
bluetoothctl trust "$MAC" >/dev/null 2>&1

echo "==> conectando"
timeout 40 bluetoothctl --timeout 35 connect "$MAC" | grep -iE 'connect|fail|error' || true

wait $SCAN 2>/dev/null

echo
echo "==> estado final"
bluetoothctl info "$MAC" 2>/dev/null | grep -Ei 'name|paired|bonded|connected|battery'

echo
if bluetoothctl info "$MAC" 2>/dev/null | grep -q 'Connected: yes'; then
    echo "conectado. rode: ./check.sh"
else
    echo "NAO conectou."
    echo "  1) confirme que o painel foi resetado (CUT + SMTH CUT por 3s)"
    echo "  2) veja se ele nao esta conectado em outra maquina"
    echo "  3) cabo USB fora"
fi
