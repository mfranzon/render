---
name: render
description: |
  Generate a 3D model from a text description or reference image using build123d
  and render it in the browser viewer. Use when asked to "render", "make a 3D model",
  "create a part", "design a", "model a", "model from image", "recreate this",
  or any 3D modeling request. Supports reference photos, sketches, and drawings.
  Also handles "apply pending edit" — when the user selects an area in the viewer
  and submits a change request, Claude reads viewer/edits/latest.{png,json} and
  modifies the current model's script.
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
- **Edit mode**: the arguments contain the phrase `apply pending edit` (singular
  or plural) or start with `edit`. The user has submitted one or more ✎ edits
  from the viewer and they are queued in `viewer/edits/pending/`. Skip to the
  **Edit mode** steps below — process every pending edit, not just one.
  Example: `/render apply pending edits`
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
   clipping plane with X/Y/Z axis, position slider, and flip. The edit (✎) button
   lets the user drag a box over an area, type an instruction, and queue it for
   this Claude session to modify that part of the model.

5. **Auto-arm the edit-apply loop** (do this on every text/image render; it's
   idempotent — calling it again just resets the timer). Call `ScheduleWakeup`
   with `delaySeconds: 60`, `prompt: "/loop /render apply pending edits"`, and
   a short `reason` like "auto-apply ✎ edits from viewer". Tell the user one
   line: "auto-apply loop armed — ✎ edits will be picked up within ~60s".

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

9. **Auto-arm the edit-apply loop** (same as text-mode step 5). Call
   `ScheduleWakeup` with `delaySeconds: 60`, `prompt: "/loop /render apply
   pending edits"`, and a short `reason`. Tell the user: "auto-apply loop
   armed — ✎ edits will be picked up within ~60s".

## Steps — Edit mode (apply pending edits)

The browser viewer lets the user draw a rectangle on the 3D model and type an
instruction. Each ✎ submission writes one pair of files under
`${CLAUDE_SKILL_DIR}/viewer/edits/pending/`:
- `<id>.png` — screenshot with a **red rectangle** marking the area to change.
- `<id>.json` — metadata: `prompt`, `model`, `script`, `rect`, `timestamp`.

Multiple edits can queue up. Process them oldest-first, then move each pair to
`viewer/edits/processed/` so the next poll / rerun doesn't re-apply them.

1. **List pending edits** (oldest first):
   ```bash
   ls -1tr ${CLAUDE_SKILL_DIR}/viewer/edits/pending/*.json 2>/dev/null
   ```
   If the list is empty, report **"no pending edits"** and stop. (When invoked
   via `/loop`, a no-op tick is expected — do not invent work.)

2. **For each pending `.json`** (oldest to newest):

   a. **Read the metadata**: `cat <path>` → get `id`, `prompt`, `model`, `script`.

   b. **Echo the prompt to the chat** (required, before any code change). Print
      a visible line in your chat response using this exact format:

      ```
      📝 Edit prompt: "<prompt verbatim>"  (model: <model>, id: <id>)
      ```

      The user wants to see each ✎ suggestion surfaced here as a prompt
      rather than only applied silently. Do this for every pending edit, even
      when running via `/loop` — the echo is what makes the auto-apply loop
      transparent.

   c. **Read the screenshot** (`<id>.png`) with the `Read` tool. The red
      rectangle marks the region the user wants changed. Identify which
      build123d feature in the code corresponds to that region (a specific
      hole, fillet, chamfer, boss, wall, pixel, etc.).

   d. **Read the model script** at `${CLAUDE_SKILL_DIR}/<script>` (from the
      metadata). If `model` is empty or the file is missing, fall back to
      `viewer/models/script.py`.

   e. **Modify the script** to address `prompt` *for the highlighted region
      only*. Keep all other geometry unchanged. If the mapping is ambiguous
      (e.g. multiple similar holes), make a best guess based on the rectangle's
      position and note the assumption when reporting back.

   f. **Run it**:
      ```bash
      PYTHONPATH=${CLAUDE_SKILL_DIR} ${CLAUDE_SKILL_DIR}/.venv/bin/python3 ${CLAUDE_SKILL_DIR}/<script>
      ```

   g. **Move the edit files out of the queue**:
      ```bash
      mkdir -p ${CLAUDE_SKILL_DIR}/viewer/edits/processed
      mv ${CLAUDE_SKILL_DIR}/viewer/edits/pending/<id>.{png,json} ${CLAUDE_SKILL_DIR}/viewer/edits/processed/
      ```

3. **Confirm**: one line per applied edit — what you changed and any
   assumption about which feature matched the red rectangle. The viewer
   auto-reloads.

### Auto-apply (hands-free)

The user can run `/loop /render apply pending edits` once per session. `/loop`
wakes up on a short interval and re-invokes this edit mode — each viewer ✎
submission is picked up within ~60s with no manual action. When the queue is
empty, the tick is a no-op.

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

# Colors — never use black; always use clear/light colors
result.color = Color("steelblue")      # good
result.color = Color(0.8, 0.2, 0.2)   # RGB floats — all channels above 0.25
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
- **Never use black or near-black colors.** Always use clear, light, or saturated colors so the model is easy to see in the viewer. Good choices: `"steelblue"`, `"cornflowerblue"`, `"mediumseagreen"`, `"goldenrod"`, `"tomato"`, `"mediumpurple"`, `"coral"`, `"lightslategray"` — or RGB floats where all channels are above 0.25.
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
