"""Render helper — exports build123d shapes to .glb + .step for the viewer.

Output formats are selectable via the RENDER_FORMATS environment variable
(comma-separated list). Default: "glb,step,stl,obj". Supported tokens:
    glb   — viewer-ready glTF binary (also used as FBX source)
    step  — STEP CAD interchange
    stl   — triangle mesh (3D-print ready)
    obj   — Wavefront OBJ (via trimesh, derived from STL)
    fbx   — Autodesk FBX (via Blender headless, derived from GLB)
FBX export uses `blender` on PATH; set BLENDER_EXE to override the path.

These variables can also be defined in a ``.env`` file at the project root
(``<root>/.env``). Lines like ``KEY=value`` are loaded at import time, with
``#`` for comments. Real environment variables always take precedence over
the file, so command-line overrides still work.
"""

import inspect
import os
import shutil
import subprocess
from pathlib import Path

# Outputs land in <project_root>/output/.
# render.py lives at <root>/.claude/skills/render/viewer/render.py, so the
# project root is parents[4].
PROJECT_ROOT = Path(__file__).resolve().parents[4]
MODELS_DIR = PROJECT_ROOT / "output"

DEFAULT_FORMATS = ("glb", "step", "stl", "obj")


def _load_dotenv(env_path: Path = PROJECT_ROOT / ".env") -> None:
    """Tiny .env loader — KEY=value lines, # comments, ignores blanks.

    The .env file is **required**. If it does not exist, raise a clear
    error pointing the user at the .env.example template. Real environment
    variables override file values, so command-line overrides still work.
    """
    if not env_path.is_file():
        raise FileNotFoundError(
            f".env not found at {env_path}. Copy .env.example to .env and "
            "edit as needed."
        )
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv()


def _selected_formats() -> set[str]:
    raw = os.environ.get("RENDER_FORMATS")
    if raw is None:
        return set(DEFAULT_FORMATS)
    return {f.strip().lower() for f in raw.split(",") if f.strip()}


def _export_fbx_via_blender(glb_path: Path, fbx_path: Path) -> None:
    """Convert a .glb to .fbx by driving Blender in --background mode."""
    blender_exe = os.environ.get("BLENDER_EXE") or shutil.which("blender")
    if not blender_exe or not Path(blender_exe).is_file():
        raise FileNotFoundError(
            "Blender not found on PATH — set BLENDER_EXE env var to the "
            "blender executable."
        )
    glb_norm = str(glb_path).replace("\\", "/")
    fbx_norm = str(fbx_path).replace("\\", "/")
    script = (
        "import bpy\n"
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
        f"bpy.ops.import_scene.gltf(filepath=r'{glb_norm}')\n"
        f"bpy.ops.export_scene.fbx(filepath=r'{fbx_norm}', "
        "path_mode='COPY', embed_textures=True)\n"
    )
    result = subprocess.run(
        [blender_exe, "--background", "--python-expr", script],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        tail_out = (result.stdout or "")[-400:]
        tail_err = (result.stderr or "")[-400:]
        raise RuntimeError(
            f"blender fbx export failed (exit {result.returncode})\n"
            f"stdout tail: {tail_out}\nstderr tail: {tail_err}"
        )


DEFAULT_WALL_THICKNESS = 1.2   # mm — typical FDM perimeter width
DEFAULT_INFILL_SPACING = 5.0   # mm between infill walls
DEFAULT_INFILL_THICKNESS = 0.8 # mm wall thickness of each infill line
DEFAULT_INFILL_PATTERN = "grid"  # grid | triangles | honeycomb


def _bbox(shape):
    bb = shape.bounding_box()
    return (
        bb.min.X, bb.min.Y, bb.min.Z,
        bb.max.X, bb.max.Y, bb.max.Z,
    )


def _build_infill_grid(bbox_shape, spacing: float, thickness: float):
    """Orthogonal crosshatch walls spanning the full bbox, centered on it.

    Walls are placed symmetrically around the bbox center so the outermost
    wall sits exactly on the bbox face; after clipping + fusing with the
    shell, every infill wall welds into the perimeter with no gap at the
    top, bottom, or side caps.
    """
    from build123d import Box, Pos

    xmin, ymin, zmin, xmax, ymax, zmax = _bbox(bbox_shape)
    sx, sy, sz = xmax - xmin, ymax - ymin, zmax - zmin
    cx, cy, cz = (xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2

    lines = None
    nx = int((sx / 2) / spacing)
    ny = int((sy / 2) / spacing)
    for i in range(-ny, ny + 1):
        y = cy + i * spacing
        wall = Pos(cx, y, cz) * Box(sx * 1.4, thickness, sz * 1.4)
        lines = wall if lines is None else lines + wall
    for i in range(-nx, nx + 1):
        x = cx + i * spacing
        wall = Pos(x, cy, cz) * Box(thickness, sy * 1.4, sz * 1.4)
        lines = wall if lines is None else lines + wall
    return lines


def _build_infill_triangles(bbox_shape, spacing: float, thickness: float):
    """Three families of parallel walls at 0°, 60°, 120°."""
    from build123d import Box, Pos, Rot

    xmin, ymin, zmin, xmax, ymax, zmax = _bbox(bbox_shape)
    sx, sy, sz = xmax - xmin, ymax - ymin, zmax - zmin
    cx, cy, cz = (xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2
    span = max(sx, sy) * 2.0

    lines = None
    for angle_deg in (0, 60, 120):
        local_y = -span / 2 + spacing
        while local_y < span / 2:
            wall_local = Pos(0, local_y, 0) * Box(span, thickness, sz * 2.0)
            wall = Pos(cx, cy, cz) * Rot(0, 0, angle_deg) * wall_local
            lines = wall if lines is None else lines + wall
            local_y += spacing
    return lines


def _build_infill_honeycomb(bbox_shape, spacing: float, thickness: float):
    """Hex cell walls extruded through the full Z — spans full bbox."""
    import math
    from build123d import RegularPolygon, Pos, extrude

    xmin, ymin, zmin, xmax, ymax, zmax = _bbox(bbox_shape)
    sx, sy, sz = xmax - xmin, ymax - ymin, zmax - zmin
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

    hex_r = max(spacing, thickness * 2 + 0.5)
    dx = math.sqrt(3) * hex_r
    dy = 1.5 * hex_r
    nx = int(sx / dx) + 3
    ny = int(sy / dy) + 3

    outers = None
    inners = None
    for iy in range(-ny, ny + 1):
        for ix in range(-nx, nx + 1):
            x = cx + ix * dx + (iy % 2) * (dx / 2)
            y = cy + iy * dy
            outer = Pos(x, y) * RegularPolygon(hex_r, 6)
            inner_hex = Pos(x, y) * RegularPolygon(hex_r - thickness, 6)
            outers = outer if outers is None else outers + outer
            inners = inner_hex if inners is None else inners + inner_hex

    if outers is None:
        return None
    walls_sketch = outers - inners
    solid = extrude(walls_sketch, amount=sz * 2.0)
    return Pos(0, 0, zmin - sz * 0.5) * solid


_INFILL_BUILDERS = {
    "grid": _build_infill_grid,
    "triangles": _build_infill_triangles,
    "honeycomb": _build_infill_honeycomb,
}


def render(
    name: str,
    shape,
    wall_thickness: float | None = None,
    infill_spacing: float | None = None,
    infill_thickness: float | None = None,
    infill_pattern: str = DEFAULT_INFILL_PATTERN,
    printable: bool = False,
    **kwargs,
):
    """Export a shape for the viewer.

    By default this exports the authored CAD geometry exactly. Pass
    ``printable=True`` or explicit wall/infill settings to export a generated
    printable shell with infill instead.

    Args:
        name: filename (without extension)
        shape: any build123d Shape (Solid, Compound, Part, etc.)
        wall_thickness: optional mm of outer wall thickness. 0 disables shelling.
        infill_spacing: optional mm between infill walls. 0 disables infill.
        infill_thickness: optional mm thickness of each infill wall.
        infill_pattern: "grid" | "triangles" | "honeycomb".
        printable: when true, generate a printable shell/infill derivative.
        **kwargs: passed to export_gltf.
    """
    from build123d import export_gltf, export_step, export_stl, offset, Kind

    out_dir = MODELS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    export_shape = shape
    make_printable = (
        printable
        or wall_thickness is not None
        or infill_spacing is not None
        or infill_thickness is not None
    )
    wall_thickness = DEFAULT_WALL_THICKNESS if wall_thickness is None else wall_thickness
    infill_spacing = DEFAULT_INFILL_SPACING if infill_spacing is None else infill_spacing
    infill_thickness = DEFAULT_INFILL_THICKNESS if infill_thickness is None else infill_thickness

    if make_printable and wall_thickness > 0:
        try:
            # Build the result by subtracting empty pockets from the solid
            # shape. This guarantees a single connected solid with no fuse-
            # seam tolerance gaps between shell and infill:
            #   inner   = cavity interior (offset of outer shape)
            #   infill  = grid of walls spanning the full bbox
            #   pockets = inner ∖ infill  (the air gaps between infill walls)
            #   result  = shape ∖ pockets
            # Every infill wall is therefore contiguous with the outer shell,
            # top, and bottom caps — nothing relies on a boolean fuse.
            inner = offset(shape, amount=-wall_thickness, kind=Kind.INTERSECTION)
            if infill_spacing > 0 and infill_thickness > 0:
                builder = _INFILL_BUILDERS.get(infill_pattern)
                if builder is None:
                    print(f"unknown infill pattern '{infill_pattern}'; shell only")
                    export_shape = shape - inner
                else:
                    try:
                        infill = builder(shape, infill_spacing, infill_thickness)
                        if infill is None:
                            export_shape = shape - inner
                        else:
                            pockets = inner - infill
                            export_shape = shape - pockets
                    except Exception as e:
                        print(f"infill failed ({e}); shell only")
                        export_shape = shape - inner
            else:
                export_shape = shape - inner
        except Exception as e:
            print(f"shell failed ({e}); exporting solid")
            export_shape = shape

    formats = _selected_formats()
    # OBJ derives from STL, FBX derives from GLB — make sure the source exists
    # even when the user didn't explicitly request it (kept as temp file).
    needs_stl_tmp = "obj" in formats and "stl" not in formats
    needs_glb_tmp = "fbx" in formats and "glb" not in formats
    results: dict[str, Path] = {}
    tmp_files: list[Path] = []

    # --- GLB ---
    if "glb" in formats or needs_glb_tmp:
        glb_out = out_dir / f"{name}.glb"
        export_gltf(export_shape, str(glb_out), binary=True, **kwargs)
        if "glb" in formats:
            results["glb"] = glb_out
        else:
            tmp_files.append(glb_out)
        glb_source = glb_out
    else:
        glb_source = None

    # --- STEP ---
    if "step" in formats:
        step_out = out_dir / f"{name}.step"
        export_step(export_shape, str(step_out))
        results["step"] = step_out

    # --- STL ---
    if "stl" in formats or needs_stl_tmp:
        stl_out = out_dir / f"{name}.stl"
        export_stl(export_shape, str(stl_out))
        if "stl" in formats:
            results["stl"] = stl_out
        else:
            tmp_files.append(stl_out)
        stl_source = stl_out
    else:
        stl_source = None

    # --- OBJ (derived from STL via trimesh) ---
    if "obj" in formats:
        obj_out = out_dir / f"{name}.obj"
        try:
            import trimesh
            mesh = trimesh.load(str(stl_source))
            mesh.export(str(obj_out))
            results["obj"] = obj_out
        except Exception as e:
            print(f"obj export failed ({e})")

    # --- FBX (derived from GLB via Blender headless) ---
    if "fbx" in formats:
        fbx_out = out_dir / f"{name}.fbx"
        try:
            _export_fbx_via_blender(glb_source, fbx_out)
            results["fbx"] = fbx_out
        except Exception as e:
            print(f"fbx export failed ({e})")

    # Clean up any temp source files we generated only to feed FBX/OBJ
    for tmp in tmp_files:
        try:
            tmp.unlink()
        except Exception:
            pass

    # Save a copy of the calling script alongside the model
    caller = inspect.stack()[1].filename
    if caller and Path(caller).is_file():
        try:
            source = Path(caller).read_text()
            (out_dir / f"{name}.py").write_text(source)
        except Exception as e:
            print(f"could not save caller script ({e})")

    for fmt in ("glb", "step", "stl", "obj", "fbx"):
        if fmt in results:
            print(f"{fmt}: {results[fmt]}")
    return results.get("glb")


def render_printable(
    name: str,
    shape,
    wall_thickness: float = DEFAULT_WALL_THICKNESS,
    infill_spacing: float = DEFAULT_INFILL_SPACING,
    infill_thickness: float = DEFAULT_INFILL_THICKNESS,
    infill_pattern: str = DEFAULT_INFILL_PATTERN,
    **kwargs,
):
    """Export a generated shell/infill version for quick printable previews."""
    return render(
        name,
        shape,
        wall_thickness=wall_thickness,
        infill_spacing=infill_spacing,
        infill_thickness=infill_thickness,
        infill_pattern=infill_pattern,
        printable=True,
        **kwargs,
    )
