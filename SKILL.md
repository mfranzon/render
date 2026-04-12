---
name: render
description: |
  Generate a 3D model from a text description or reference image using build123d
  and render it in the browser viewer. Use when asked to "render", "make a 3D model",
  "create a part", "design a", "model a", "model from image", "recreate this",
  or any 3D modeling request. Supports reference photos, sketches, and drawings.
argument-hint: [image path and/or description of the 3D model]
allowed-tools:
  - Bash
  - Write
  - Read
  - WebSearch
  - WebFetch
---

# /render — Generate & View 3D Models

Generate build123d Python code from a description (and optionally a reference
image), execute it, and display the result in the browser viewer at
http://localhost:3123.

## Preamble (run first)

```bash
bash ${CLAUDE_SKILL_DIR}/setup.sh
```

If this prints `READY`, continue. If not, the setup will install build123d
into the skill's own venv (one-time, ~30s).

## Detect mode

Look at `$ARGUMENTS`:
- **Image mode**: the arguments contain a file path to an image (`.png`, `.jpg`,
  `.jpeg`, `.webp`, `.gif`, `.bmp`, `.svg`). The path may be followed by an
  optional text description.
  Example: `/render ~/photos/bracket.jpg a mounting bracket`
- **Text mode**: no image path — just a text description.
  Example: `/render a gear with 20 teeth`

## Steps — Text mode (no image)

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
   and re-render with Ctrl+Enter. The slice (✂) button enables a cross-section
   clipping plane with X/Y/Z axis, position slider, and flip.

## Steps — Image mode (reference image provided)

1. **Start the viewer** (same as text mode):
   ```bash
   lsof -i :3123 -t >/dev/null 2>&1 && echo "VIEWER_RUNNING" || (${CLAUDE_SKILL_DIR}/.venv/bin/python3 ${CLAUDE_SKILL_DIR}/viewer/serve.py &>/tmp/build123d-viewer.log & sleep 1 && echo "VIEWER_STARTED" && open http://localhost:3123)
   ```

2. **Read the image**: Use the `Read` tool on the image file path. Claude will
   see the image contents thanks to multimodal vision.

3. **Analyze the image**: Study the image carefully and identify:
   - What the object is (type, category, common name)
   - Overall shape and geometry (prismatic, cylindrical, organic, etc.)
   - Key features (holes, slots, fillets, chamfers, ribs, bosses, etc.)
   - Approximate proportions and relative dimensions
   - Any visible text, labels, or dimension callouts
   - Material appearance (helps choose colors)

4. **Research online**: Use `WebSearch` to find more information about the object.
   Search for:
   - Standard/typical dimensions if the object is a known part (e.g. "M8 bolt
     dimensions mm", "standard electrical outlet plate dimensions")
   - Technical drawings or specs if it's a recognizable component
   - build123d examples of similar geometry if the shape is complex
   
   Use `WebFetch` to read any promising results that have dimension tables or
   technical specs. This step is critical — real-world dimensions make the
   model accurate instead of just proportionally correct.

5. **Plan the geometry**: Before writing code, outline your modeling strategy:
   - Base shape and dimensions (in mm)
   - Boolean operations needed (cuts, fuses)
   - Features to add (fillets, chamfers, patterns)
   - Which build123d API to use (algebra for simple, builder for complex)

6. **Write the script**: Create `${CLAUDE_SKILL_DIR}/viewer/models/script.py`.
   Include a comment block at the top noting:
   - Source: reference image
   - Estimated/researched dimensions
   - Any assumptions made

7. **Run it**:
   ```bash
   PYTHONPATH=${CLAUDE_SKILL_DIR} ${CLAUDE_SKILL_DIR}/.venv/bin/python3 ${CLAUDE_SKILL_DIR}/viewer/models/script.py
   ```

8. **Confirm** the model was rendered and tell the user to check
   http://localhost:3123. Mention what dimensions you used and any assumptions,
   so the user can adjust in the code panel.

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

# Fillets and chamfers (on specific edges)
# Vertical edges of a box
result = fillet(box.edges().filter_by(Axis.Z), radius=0.5)
# Top edges only
result = fillet(box.edges().group_by(Axis.Z)[-1], radius=0.3)
# All edges (may fail if radius too large)
result = fillet(box.edges(), radius=0.2)

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
    # Fillets only on vertical edges (safer than all edges)
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
- `shape.edges().filter_by(Axis.Z)` — vertical edges only (safe for fillet)
- `shape.edges().group_by(Axis.Z)[-1]` — top edges only
- `shape.edges().group_by(Axis.Z)[0]` — bottom edges only

## Important

- Fillets may fail if radius is too large for the edge — use `filter_by(Axis.Z)` for vertical edges or smaller radius
- Always use algebra mode unless the model genuinely requires builder contexts
- Use a descriptive name in `render("gear", result)` — each name creates a separate model in the gallery. Avoid reusing "model" so the user can browse previous renders
- Set colors for better visualization
- The viewer auto-reloads — the model appears in the browser within 1 second
- If the script fails, show the error and fix the code — do NOT ask the user to debug

## Image mode tips

- **Always research dimensions online** — don't just guess from the image. A photo
  of a bolt should produce a model with real bolt dimensions, not arbitrary sizes.
- If the object is unrecognizable, ask the user what it is before proceeding.
- For complex organic shapes, focus on capturing the essential geometry — build123d
  is a CAD tool, not a mesh sculptor. Approximate curves with arcs and splines.
- When the image is a technical/engineering drawing with dimensions marked, use
  those dimensions directly — no need to search online.
- For photos taken at an angle, account for perspective distortion when estimating
  proportions.
- If the image shows multiple objects, ask the user which one to model (or model
  the most prominent one).
- Mention your dimension sources and assumptions so the user can correct them.
