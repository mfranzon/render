"""Render helper — exports build123d shapes to .glb + .step for the viewer."""

from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"


def render(name: str, shape, **kwargs):
    """Export a shape to the viewer's models directory.

    Args:
        name: filename (without extension)
        shape: any build123d Shape (Solid, Compound, Part, etc.)
        **kwargs: passed to export_gltf (e.g. linear_deflection, angular_deflection)
    """
    from build123d import export_gltf, export_step

    MODELS_DIR.mkdir(exist_ok=True)

    glb_out = MODELS_DIR / f"{name}.glb"
    export_gltf(shape, str(glb_out), binary=True, **kwargs)

    step_out = MODELS_DIR / f"{name}.step"
    export_step(shape, str(step_out))

    print(f"rendered: {glb_out}")
    print(f"step:     {step_out}")
    return glb_out
