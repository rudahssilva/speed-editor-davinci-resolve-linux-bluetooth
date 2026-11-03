#!/usr/bin/env bash
# install.sh — everything the Speed Editor needs on Linux (Bluetooth)
#
#   ./install.sh                       udev + helper scripts + Resolve patch
#   ./install.sh --with-auth-daemon    also enable the ble_auth fallback daemon
#   CONTAINER=name ./install.sh        distrobox/podman container holding Resolve
#   ./install.sh --check               diagnose only (udev + BlueZ + Resolve binary)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONTAINER="${CONTAINER:-davincibox}"
GRP="$(id -gn)"
BIN_DIR="$HOME/.local/bin"
RULE="/etc/udev/rules.d/99-blackmagic-hidraw.rules"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Never run the whole script as root: the udev rule would then ship with
# GROUP="root" (the panel stays unreadable for you) and the helpers would be
# installed into /root/.local/bin for root's systemd user session. The script
# sudo's by itself for the single step that needs it.
if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ]; then
    fail "run it as your user, not with sudo: ./install.sh  (it calls sudo for the udev rule)"
fi

if [ "${1:-}" = "--check" ]; then
    "$HERE/check.sh"
    step "BlueZ (GET_REPORT reply size)"
    "$HERE/bluez-probe.py" || true
    step "Resolve binary"
    # Resolve may live inside the distrobox container; check it there without
    # copying anything in (the script reads itself from stdin).
    if command -v podman >/dev/null 2>&1 && podman container exists "$CONTAINER" 2>/dev/null; then
        podman exec -i -u root "$CONTAINER" python3 - --status < "$HERE/resolve-patch.py" || true
    else
        "$HERE/resolve-patch.py" --status || true
    fi
    exit 0
fi

# ---------- 1. udev ----------
step "1/4 udev rule ($RULE)"
TMP="$(mktemp)"
sed "s/GROUP=\"input\"/GROUP=\"$GRP\"/g" "$HERE/99-blackmagic-hidraw.rules" > "$TMP"
sudo cp "$TMP" "$RULE" || fail "sudo cp failed"
rm -f "$TMP"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
echo "ok: $RULE (group $GRP)"

# ---------- 2. helper scripts ----------
step "2/4 helper scripts"
mkdir -p "$BIN_DIR"
install -m 0755 "$HERE/read_hid.py" "$BIN_DIR/read_hid.py"
install -m 0755 "$HERE/ble_auth.py" "$BIN_DIR/ble_auth.py"
install -m 0755 "$HERE/resolve-patch.py" "$BIN_DIR/resolve-patch.py"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
sed "s|@BIN@|$BIN_DIR/ble_auth.py|" "$HERE/speed-editor-ble-auth.service" \
    > "$UNIT_DIR/speed-editor-ble-auth.service"
systemctl --user daemon-reload
if [ "${1:-}" = "--with-auth-daemon" ]; then
    if ! python3 -c "import dbus" 2>/dev/null; then
        echo "warning: python-dbus missing — ble_auth.py will not run."
        echo "  Arch: sudo pacman -S python-dbus   (or skip the daemon: Resolve does the auth itself)"
    fi
    systemctl --user enable --now speed-editor-ble-auth.service
    echo "ok: $BIN_DIR/{read_hid,ble_auth,resolve-patch}.py + auth daemon ENABLED"
else
    # Resolve renews the handshake itself once BlueZ is fixed; running both
    # makes the two 600 s countdowns fight each other.
    echo "ok: $BIN_DIR/{read_hid,ble_auth,resolve-patch}.py"
    echo "auth daemon installed but left disabled (enable only if the panel goes quiet:"
    echo "  systemctl --user enable --now speed-editor-ble-auth.service)"
fi

# ---------- 3. Resolve patch ----------
step "3/4 Resolve binary patch"
if command -v podman >/dev/null 2>&1 && podman container exists "$CONTAINER" 2>/dev/null; then
    # Resolve inside a distrobox/podman container (the typical setup)
    podman cp "$HERE/resolve-patch.py" "$CONTAINER:/tmp/resolve-patch.py"
    podman exec -u root "$CONTAINER" python3 /tmp/resolve-patch.py
elif [ -f /opt/resolve/bin/resolve ]; then
    # Resolve installed straight on the host
    sudo "$HERE/resolve-patch.py"
else
    echo "no Resolve found (neither container '$CONTAINER' nor /opt/resolve/bin/resolve)."
    echo "Run it by hand:"
    echo "  podman exec -u root <container> python3 /tmp/resolve-patch.py   # container"
    echo "  sudo $HERE/resolve-patch.py                                     # host"
fi

# ---------- 4. BlueZ ----------
step "4/4 BlueZ"
"$HERE/bluez-probe.py" 2>/dev/null
RC=$?
if [ "$RC" = 0 ]; then
    echo "BlueZ ok (GET_REPORT returns the full reply)."
elif [ "$RC" = 2 ]; then
    echo "BlueZ drops the last byte of numbered reports. Follow bluez/README-BLUEZ-PATCH.md"
    echo "(after rebuilding, run ./install.sh --check again)"
else
    echo "Speed Editor not connected right now; run ./install.sh --check with it connected."
fi

echo
echo "done. Connect the panel (tools/repair.sh if it needs re-pairing) and open Resolve."
