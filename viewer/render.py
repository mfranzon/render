"""Render helper — exports build123d shapes to .glb for the viewer."""

from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"


def render(name: str, shape, **kwargs):
    """Export a shape to the viewer's models directory.

    Args:
        name: filename (without extension)
        shape: any build123d Shape (Solid, Compound, Part, etc.)
        **kwargs: passed to export_gltf (e.g. linear_deflection, angular_deflection)
    """
    from build123d import export_gltf

    MODELS_DIR.mkdir(exist_ok=True)
    out = MODELS_DIR / f"{name}.glb"
    export_gltf(shape, str(out), binary=True, **kwargs)
    print(f"rendered: {out}")
    return out
