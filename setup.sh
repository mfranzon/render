#!/usr/bin/env bash
# Bootstrap the render skill: creates venv + installs build123d
set -e

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SKILL_DIR/.venv"

# Fast check: marker file means setup already succeeded
if [ -f "$VENV_DIR/.b3d-ready" ]; then
    echo "READY"
    exit 0
fi

# Slower fallback: venv exists but no marker (e.g. partial install)
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python3" ]; then
    if "$VENV_DIR/bin/python3" -c "import build123d" 2>/dev/null; then
        touch "$VENV_DIR/.b3d-ready"
        echo "READY"
        exit 0
    fi
fi

echo "Setting up render skill..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet "build123d @ git+https://github.com/gumyr/build123d.git"
echo "READY"
