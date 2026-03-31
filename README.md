# /render — 3D Model Skill for Claude Code

A Claude Code skill that generates 3D models from text descriptions using [build123d](https://github.com/gumyr/build123d) and renders them in a browser viewer.

```
/render a gear with 12 teeth
/render a phone case with rounded corners
/render a torus knot
```

Claude writes the parametric Python code, executes it, and the model appears in your browser within seconds. Open the code panel to tweak parameters and re-render with Ctrl+Enter.

## Install

```bash
# Clone into your Claude Code skills directory
git clone https://github.com/YOUR_USER/claude-render-skill.git ~/.claude/skills/render

# First run installs build123d automatically (~30s)
```

That's it. Type `/render a box with a hole` in any Claude Code session.

## How it works

```
you: "/render a gear"
        │
        ▼
   Claude Code writes build123d Python code
        │
        ▼
   Executes → exports .glb to viewer/models/
        │
        ▼
   Three.js viewer auto-loads the model
   http://localhost:3123
```

The viewer starts automatically on first render. It includes:
- Three.js 3D viewport with orbit controls
- Code editor panel (click `</> code`) for tweaking parameters
- Ctrl+Enter to re-render from the browser
- Auto-reload on new models

## Files

```
├── SKILL.md           # Skill definition + build123d API reference
├── setup.sh           # One-time bootstrap (creates .venv, installs build123d)
├── viewer/
│   ├── index.html     # Three.js viewer with code editor
│   ├── serve.py       # Local HTTP server (port 3123)
│   ├── render.py      # render() helper for exporting .glb
│   └── models/        # Generated .glb files + scripts
└── README.md
```

## Requirements

- Python 3.10+
- Claude Code

No other dependencies — `setup.sh` creates an isolated venv and installs everything.

## Manual usage

You can also use the viewer standalone without Claude Code:

```bash
# Start the viewer
~/.claude/skills/render/.venv/bin/python3 ~/.claude/skills/render/viewer/serve.py

# Write a script
cat > ~/.claude/skills/render/viewer/models/script.py << 'EOF'
from build123d import *
from viewer.render import render

box = Box(10, 10, 10) - Cylinder(4, 12)
box.color = Color("steelblue")
render("model", box)
EOF

# Run it
PYTHONPATH=~/.claude/skills/render ~/.claude/skills/render/.venv/bin/python3 ~/.claude/skills/render/viewer/models/script.py
```
