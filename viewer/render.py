"""Render helper — exports build123d shapes to .glb + .step for the viewer."""

import inspect
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"


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
    wall_thickness: float = DEFAULT_WALL_THICKNESS,
    infill_spacing: float = DEFAULT_INFILL_SPACING,
    infill_thickness: float = DEFAULT_INFILL_THICKNESS,
    infill_pattern: str = DEFAULT_INFILL_PATTERN,
    **kwargs,
):
    """Export a shape as a printable shell with infill.

    Args:
        name: filename (without extension)
        shape: any build123d Shape (Solid, Compound, Part, etc.)
        wall_thickness: mm of outer wall thickness. 0 disables shelling.
        infill_spacing: mm between infill walls. 0 disables infill.
        infill_thickness: mm thickness of each infill wall.
        infill_pattern: "grid" | "triangles" | "honeycomb".
        **kwargs: passed to export_gltf.
    """
    from build123d import export_gltf, export_step, export_stl, offset, Kind

    MODELS_DIR.mkdir(exist_ok=True)

    printable = shape
    if wall_thickness > 0:
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
                    printable = shape - inner
                else:
                    try:
                        infill = builder(shape, infill_spacing, infill_thickness)
                        if infill is None:
                            printable = shape - inner
                        else:
                            pockets = inner - infill
                            printable = shape - pockets
                    except Exception as e:
                        print(f"infill failed ({e}); shell only")
                        printable = shape - inner
            else:
                printable = shape - inner
        except Exception as e:
            print(f"shell failed ({e}); exporting solid")
            printable = shape

    glb_out = MODELS_DIR / f"{name}.glb"
    export_gltf(printable, str(glb_out), binary=True, **kwargs)

    step_out = MODELS_DIR / f"{name}.step"
    export_step(printable, str(step_out))

    stl_out = MODELS_DIR / f"{name}.stl"
    export_stl(printable, str(stl_out))

    # Save a copy of the calling script alongside the model
    caller = inspect.stack()[1].filename
    if caller and Path(caller).is_file():
        try:
            source = Path(caller).read_text()
            (MODELS_DIR / f"{name}.py").write_text(source)
        except Exception as e:
            print(f"could not save caller script ({e})")

    print(f"rendered: {glb_out}")
    print(f"step:     {step_out}")
    print(f"stl:      {stl_out}")
    return glb_out
