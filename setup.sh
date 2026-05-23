#!/usr/bin/env bash
# Bootstrap the render skill: creates venv + installs build123d, and
# materialises .env from .env.example on first run.
set -e

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SKILL_DIR/.venv"
PROJECT_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"

# Materialise .env on first run. Emit ENV_CREATED so the skill knows to
# prompt the user for their preferred output formats.
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo "ENV_CREATED"
    else
        echo "WARNING: $ENV_EXAMPLE not found — cannot initialize .env" >&2
    fi
fi

# Fast check: marker file means setup already succeeded
if [ -f "$VENV_DIR/.b3d-ready" ]; then
    echo "READY"
    exit 0
fi

# Slower fallback: venv exists but no marker (e.g. partial install).
# Windows uses Scripts/python.exe; *nix uses bin/python3.
if [ -d "$VENV_DIR" ]; then
    if   [ -f "$VENV_DIR/bin/python3" ];     then PY="$VENV_DIR/bin/python3"
    elif [ -f "$VENV_DIR/Scripts/python.exe" ]; then PY="$VENV_DIR/Scripts/python.exe"
    else PY=""
    fi
    if [ -n "$PY" ] && "$PY" -c "import build123d" 2>/dev/null; then
        touch "$VENV_DIR/.b3d-ready"
        echo "READY"
        exit 0
    fi
fi

echo "Setting up render skill..."
python3 -m venv "$VENV_DIR"

# Resolve pip + the venv's site-packages dir — Windows uses Scripts/, *nix uses bin/.
if   [ -f "$VENV_DIR/bin/pip" ];           then PIP="$VENV_DIR/bin/pip";          PY="$VENV_DIR/bin/python3"
elif [ -f "$VENV_DIR/Scripts/pip.exe" ];   then PIP="$VENV_DIR/Scripts/pip.exe";  PY="$VENV_DIR/Scripts/python.exe"
else
    echo "ERROR: cannot find pip in $VENV_DIR (looked in bin/ and Scripts/)" >&2
    exit 1
fi

"$PIP" install --quiet \
    "build123d @ git+https://github.com/gumyr/build123d.git" \
    pyvista

echo "READY"
