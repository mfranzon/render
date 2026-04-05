---
name: render
description: |
  Generate a 3D model from a text description using build123d and render it
  in the browser viewer. Use when asked to "render", "make a 3D model",
  "create a part", "design a", "model a", or any 3D modeling request.
argument-hint: [description of the 3D model]
allowed-tools:
  - Bash
  - Write
  - Read
---

# /render — Generate & View 3D Models

Generate build123d Python code from a description, execute it, and display
the result in the browser viewer at http://localhost:3123.

## Preamble (run first)

```bash
bash ${CLAUDE_SKILL_DIR}/setup.sh
```

If this prints `READY`, continue. If not, the setup will install build123d
into the skill's own venv (one-time, ~30s).

## Steps

1. **Start the viewer** (if not already running):
   ```bash
   lsof -i :3123 -t >/dev/null 2>&1 && echo "VIEWER_RUNNING" || (${CLAUDE_SKILL_DIR}/.venv/bin/python3 ${CLAUDE_SKILL_DIR}/viewer/serve.py &>/tmp/build123d-viewer.log & sleep 1 && echo "VIEWER_STARTED" && open http://localhost:3123)
   ```

2. **Write the script**: Create `${CLAUDE_SKILL_DIR}/viewer/models/script.py` that:
   - Imports `from build123d import *`
   - Imports `from viewer.render import render`
   - Builds the requested 3D model using build123d algebra or builder API
   - Calls `render("model", result)` at the end to export it

3. **Run it**:
   ```bash
   PYTHONPATH=${CLAUDE_SKILL_DIR} ${CLAUDE_SKILL_DIR}/.venv/bin/python3 ${CLAUDE_SKILL_DIR}/viewer/models/script.py
   ```

4. **Confirm** the model was rendered and tell the user to check http://localhost:3123.
   The viewer auto-reloads — the model appears within 1 second.
   The user can open the code panel (</> button) in the browser to tweak parameters
   and re-render with Ctrl+Enter.

## Description: $ARGUMENTS

## build123d Quick Reference

### Algebra mode (preferred — simpler)
```python
from build123d import *
from viewer.render import render

# Primitives
box = Box(width, depth, height)
cyl = Cylinder(radius, height)
sphere = Sphere(radius)
cone = Cone(bottom_radius, top_radius, height)
torus = Torus(major_radius, minor_radius)

# Booleans
result = box - cyl          # cut
result = box + cyl          # fuse
result = box & cyl          # intersect

# Positioning
part = Pos(x, y, z) * Box(1, 1, 1)
part = Rot(x_deg, y_deg, z_deg) * Cylinder(1, 2)

# Fillets and chamfers (on edges)
result = fillet(box.edges(), radius=0.5)
result = chamfer(box.edges(), length=0.3)

# 2D sketches → 3D
sketch = Rectangle(10, 5)
solid = extrude(sketch, amount=3)

# Sweep, loft, revolve
solid = revolve(sketch, axis=Axis.X, revolution_arc=360)

# Colors
result.color = Color("steelblue")
result.color = Color(0.8, 0.2, 0.2)  # RGB floats
```

### Builder mode (for complex models)
```python
from build123d import *
from viewer.render import render

with BuildPart() as part:
    Box(10, 10, 5)
    with BuildSketch(part.faces().sort_by(Axis.Z)[-1]):
        Circle(3)
    extrude(amount=-5, mode=Mode.SUBTRACT)
    fillet(part.edges().filter_by(Axis.Z), radius=0.5)

render("model", part.part)
```

### Key operations
- `extrude(shape, amount)` — extrude 2D to 3D
- `revolve(shape, axis, revolution_arc)` — revolve 2D around axis
- `sweep(path, profile)` — sweep profile along path
- `loft([face1, face2])` — loft between faces
- `fillet(edges, radius)` — round edges
- `chamfer(edges, length)` — bevel edges
- `mirror(shape, about=Plane.XZ)` — mirror
- `offset(shape, amount)` — shell/offset

### Useful selectors
- `shape.edges()` — all edges
- `shape.faces()` — all faces
- `shape.faces().sort_by(Axis.Z)[-1]` — top face
- `shape.edges().filter_by(Axis.Z)` — vertical edges
- `shape.edges().group_by(Axis.Z)[-1]` — top edges

## Important

- Always use algebra mode unless the model genuinely requires builder contexts
- Use a descriptive name in `render("gear", result)` — each name creates a separate model in the gallery. Avoid reusing "model" so the user can browse previous renders
- Set colors for better visualization
- The viewer auto-reloads — the model appears in the browser within 1 second
- If the script fails, show the error and fix the code — do NOT ask the user to debug
