"""Smoke-test the render helper export path."""

from pathlib import Path
from tempfile import TemporaryDirectory

from build123d import Box, Cylinder

import viewer.render as render_module


def main():
    with TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        render_module.MODELS_DIR = out_dir

        model = Box(30, 30, 30) - Cylinder(8, 40)
        render_module.render("smoke_cube_with_hole", model)

        expected = [
            out_dir / "smoke_cube_with_hole.glb",
            out_dir / "smoke_cube_with_hole.step",
            out_dir / "smoke_cube_with_hole.stl",
        ]
        missing = [str(path) for path in expected if not path.is_file()]
        if missing:
            raise SystemExit("missing render outputs: " + ", ".join(missing))

    print("smoke render OK")


if __name__ == "__main__":
    main()
