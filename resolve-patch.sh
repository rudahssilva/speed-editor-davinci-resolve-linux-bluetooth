#!/bin/sh
# resolve-patch.sh — kept for compatibility; the real patch now lives in
# resolve-patch.py, which LOCATES the three checks in the binary instead of
# relying on hard-coded offsets (Blackmagic ships different builds under the
# same version string, so offsets move).
exec "$(dirname "$0")/resolve-patch.py" "$@"
