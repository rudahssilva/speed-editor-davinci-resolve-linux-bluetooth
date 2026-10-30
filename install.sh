#!/usr/bin/env bash
# install.sh — instala tudo que o Speed Editor precisa no Linux (Bluetooth)
#
#   ./install.sh                 instala tudo (com sudo onde necessario)
#   CONTAINER=nome ./install.sh  container distrobox do Resolve (default: davincibox)
#   ./install.sh --check         so diagnostico (udev + BlueZ + binario do Resolve)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONTAINER="${CONTAINER:-davincibox}"
GRP="$(id -gn)"
BIN_DIR="$HOME/.local/bin"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31merro:\033[0m %s\n' "$*" >&2; exit 1; }

if [ "${1:-}" = "--check" ]; then
    "$HERE/check.sh"
    step "BlueZ (tamanho do GET_REPORT)"
    "$HERE/bluez-probe.py" || true
    step "binario do Resolve"
    "$HERE/resolve-patch.sh" --status || true
    exit 0
fi

# ---------- 1. udev ----------
step "1/4 Regra udev"
RULE="/etc/udev/rules.d/99-blackmagic-hidraw.rules"
TMP="$(mktemp)"
sed "s/GROUP=\"input\"/GROUP=\"$GRP\"/g" "$HERE/99-blackmagic-hidraw.rules" > "$TMP"
sudo cp "$TMP" "$RULE" || fail "sudo cp falhou"
rm -f "$TMP"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
echo "ok: $RULE (grupo $GRP)"

# ---------- 2. daemon de auth (fallback) ----------
step "2/4 Daemon de auth (fallback)"
mkdir -p "$BIN_DIR"
install -m 0755 "$HERE/read_hid.py" "$BIN_DIR/read_hid.py"
install -m 0755 "$HERE/ble_auth.py" "$BIN_DIR/ble_auth.py"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
sed "s|@BIN@|$BIN_DIR/ble_auth.py|" "$HERE/speed-editor-ble-auth.service" > "$UNIT_DIR/speed-editor-ble-auth.service"
systemctl --user daemon-reload
systemctl --user enable --now speed-editor-ble-auth.service
echo "ok: $BIN_DIR/{read_hid,ble_auth}.py + servico speed-editor-ble-auth"

# ---------- 3. patch no binario do Resolve ----------
step "3/4 Patch no binario do Resolve"
if command -v podman >/dev/null 2>&1 && podman container exists "$CONTAINER" 2>/dev/null; then
    # Resolve dentro de um container distrobox/podman (caso tipico)
    podman cp "$HERE/resolve-patch.sh" "$CONTAINER:/tmp/resolve-patch.sh"
    podman exec -u root "$CONTAINER" sh /tmp/resolve-patch.sh
elif [ -f /opt/resolve/bin/resolve ]; then
    # Resolve instalado direto no host (sem container)
    sudo sh "$HERE/resolve-patch.sh"
else
    echo "nao achei o Resolve (nem o container '$CONTAINER', nem /opt/resolve/bin/resolve)."
    echo "Rode manualmente:"
    echo "  podman exec -u root <container> sh $HERE/resolve-patch.sh   # se for container"
    echo "  sudo sh $HERE/resolve-patch.sh                              # se for no host"
fi

# ---------- 4. BlueZ ----------
step "4/4 BlueZ"
"$HERE/bluez-probe.py" 2>/dev/null && true
RC=$?
if [ "$RC" = 0 ]; then
    echo "BlueZ ok (GET_REPORT com tamanho correto)."
elif [ "$RC" = 2 ]; then
    echo "BlueZ com o bug do ultimo byte. Siga bluez/README-BLUEZ-PATCH.md"
    echo "(apos recompilar, rode ./install.sh --check de novo)"
else
    echo "Speed Editor nao conectado agora; rode ./install.sh --check com ele conectado."
fi

echo
echo "pronto. Conecte o painel (repair.sh se precisar re-parear) e abra o Resolve."
