# /render — 3D Model Skill for Claude Code

<img width="1541" height="952" alt="Screenshot 2026-08-04 alle 10 37 42" src="https://github.com/user-attachments/assets/bd29f0c9-efe3-47b3-8547-f60e37558dea" />


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
- Hamburger (☰) menu in the top-right with all toolbar actions
- Code editor panel (`</> code`) for tweaking parameters, Ctrl+Enter to re-render
- Model gallery (`▦ models`) to browse previous renders
- Render mode toggle (solid / wireframe / x-ray)
- Dimension overlay (`□ dims`) with a bounding box and W/D/H labels
- Cross-section slice (`✂ slice`) — X/Y/Z axis, position slider, flip
- STEP export (`⬳ STEP`) for sending to a slicer or CAD tool
- Edit mode (`✎ edit`) — drag a box on the model, type an instruction, Claude applies it
- Auto-reload on new models

By default, `render("model", shape)` exports the authored build123d geometry
exactly. For a quick shell/infill preview, use `render("model", shape,
printable=True)` or `render_printable("model", shape)`.

## Region-based edits (✎)

Click `✎ edit` in the menu, drag a rectangle over the part of the model you
want to change, type an instruction ("make this hole bigger", "replace this
grid with dots", "add a Ø3 mm hole here"), and press send. The viewer captures
a screenshot with the red selection rectangle and queues it under
`viewer/edits/pending/`.

Claude picks up queued edits in one of two ways:

- **On-demand**: type `/render apply pending edits` — Claude processes every
  queued edit, modifies the relevant `viewer/models/<name>.py`, re-runs it,
  and the viewer reloads.
- **Hands-free**: run `/loop /render apply pending edits` once per session.
  Claude re-checks the queue about every 60s until you stop the loop.

Every applied edit is echoed back in chat as `📝 Edit prompt: "..."` so you
can see exactly what you asked for before the change lands.

## Files

```
├── SKILL.md           # Skill definition + build123d API reference
├── setup.sh           # One-time bootstrap (creates .venv, installs build123d)
├── viewer/
│   ├── index.html     # Three.js viewer, hamburger menu, edit/slice tools
│   ├── serve.py       # Local HTTP server (port 3123) + /api/edit endpoint
│   ├── render.py      # render() helper: exports .glb + .step + .stl and
│   │                  # saves a copy of the model script next to them
│   ├── models/        # Generated .glb / .step files + scripts
│   └── edits/
│       ├── pending/   # Queued ✎ edits waiting for Claude
│       └── processed/ # Applied edits (kept for history)
└── README.md
```

## Requirements

- Python 3.10+
- Claude Code

No other Python dependencies: `setup.sh` creates an isolated venv and installs
everything. The viewer page itself loads three.js from jsdelivr, so the first
load needs network access.

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
