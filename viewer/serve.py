"""Standalone viewer server for build123d models.

Usage:
    python serve.py [--port 3123]

Serves a Three.js viewer that auto-loads the latest .glb.
Code panel lets you edit and re-run scripts from the browser.
"""

import base64
import http.server
import json
import os
import subprocess
import sys
import threading
import time
from urllib.parse import unquote
from pathlib import Path

_server = None  # set in main(); used by the /api/shutdown endpoint

PORT = 3123
SKILL_DIR = Path(__file__).parent.parent
VIEWER_DIR = Path(__file__).parent
MODELS_DIR = VIEWER_DIR / "models"
EDITS_DIR = VIEWER_DIR / "edits"
SCRIPT_PATH = MODELS_DIR / "script.py"
VENV_PYTHON = SKILL_DIR / ".venv" / "bin" / "python3"

DOWNLOAD_TYPES = {
    ".glb": "model/gltf-binary",
    ".step": "application/STEP",
    ".stl": "model/stl",
}


def get_python():
    """Return the venv python if available, else system python3."""
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"


def get_model_version():
    """Return current version based on latest glb mtime."""
    glbs = list(MODELS_DIR.glob("*.glb"))
    if not glbs:
        return 0
    return int(max(os.path.getmtime(f) for f in glbs) * 1000)


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(VIEWER_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/latest":
            self.send_latest()
        elif self.path == "/api/list":
            self.list_models()
        elif self.path.startswith("/api/model/"):
            self.get_model_info()
        elif self.path.startswith("/api/download/"):
            self.download_file()
        elif self.path == "/":
            self.path = "/index.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/run":
            self.run_code()
        elif self.path == "/api/edit":
            self.save_edit()
        elif self.path == "/api/shutdown":
            self.shutdown_server()
        else:
            self.send_error(404)

    def shutdown_server(self):
        self.send_json({"ok": True})
        # shutdown() must run off the request thread.
        if _server is not None:
            threading.Thread(target=_server.shutdown, daemon=True).start()

    def send_latest(self):
        glbs = sorted(MODELS_DIR.glob("*.glb"), key=os.path.getmtime, reverse=True)
        code = SCRIPT_PATH.read_text() if SCRIPT_PATH.exists() else ""
        exports = {}
        if glbs:
            for suffix in DOWNLOAD_TYPES:
                export_path = glbs[0].with_suffix(suffix)
                if export_path.exists():
                    exports[suffix.lstrip(".")] = export_path.name
        data = {
            "file": glbs[0].name if glbs else None,
            "version": get_model_version(),
            "code": code,
            "step": exports.get("step"),
            "stl": exports.get("stl"),
            "downloads": exports,
        }
        self.send_json(data)

    def get_model_info(self):
        # /api/model/<name> — return code for a specific model
        name = self.path.split("/api/model/", 1)[1]
        script = MODELS_DIR / f"{name}.py"
        code = script.read_text() if script.exists() else ""
        self.send_json({"name": name, "code": code})

    def list_models(self):
        glbs = sorted(MODELS_DIR.glob("*.glb"), key=os.path.getmtime, reverse=True)
        models = []
        for g in glbs:
            stat = g.stat()
            script = g.with_suffix(".py")
            exports = {}
            for suffix in DOWNLOAD_TYPES:
                export_path = g.with_suffix(suffix)
                if export_path.exists():
                    exports[suffix.lstrip(".")] = export_path.name
            models.append({
                "file": g.name,
                "name": g.stem,
                "mtime": int(stat.st_mtime * 1000),
                "size": stat.st_size,
                "step": exports.get("step"),
                "stl": exports.get("stl"),
                "downloads": exports,
                "has_script": script.exists(),
            })
        self.send_json({"models": models})

    def download_file(self):
        # /api/download/<name> for exported .glb, .step, or .stl files.
        filename = unquote(self.path.split("/api/download/", 1)[1])
        models_root = MODELS_DIR.resolve()
        filepath = (MODELS_DIR / filename).resolve()
        if (
            not filepath.is_file()
            or filepath.suffix.lower() not in DOWNLOAD_TYPES
            or models_root not in (filepath, *filepath.parents)
        ):
            self.send_error(404, "File not found")
            return
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", DOWNLOAD_TYPES[filepath.suffix.lower()])
        self.send_header("Content-Disposition", f'attachment; filename="{filepath.name}"')
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def save_edit(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        image_data_url = body.get("image", "")
        prompt = (body.get("prompt") or "").strip()
        model_name = body.get("model") or ""
        rect = body.get("rect") or {}

        if not prompt:
            self.send_json({"ok": False, "error": "empty prompt"})
            return
        prefix = "data:image/png;base64,"
        if not image_data_url.startswith(prefix):
            self.send_json({"ok": False, "error": "invalid image"})
            return
        image_bytes = base64.b64decode(image_data_url[len(prefix):])

        pending_dir = EDITS_DIR / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        stem = str(ts)
        (pending_dir / f"{stem}.png").write_bytes(image_bytes)

        script_rel = f"viewer/models/{model_name}.py" if model_name else "viewer/models/script.py"
        (pending_dir / f"{stem}.json").write_text(json.dumps({
            "id": stem,
            "prompt": prompt,
            "model": model_name,
            "script": script_rel,
            "rect": rect,
            "timestamp": ts,
        }, indent=2))

        self.send_json({"ok": True, "id": stem})

    def run_code(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        code = body.get("code", "")

        SCRIPT_PATH.write_text(code)

        t0 = time.time()
        try:
            result = subprocess.run(
                [get_python(), str(SCRIPT_PATH)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(SKILL_DIR),
                env={**os.environ, "PYTHONPATH": str(SKILL_DIR)},
            )
            elapsed = f"{time.time() - t0:.1f}s"
            if result.returncode == 0:
                self.send_json({"ok": True, "time": elapsed, "output": result.stdout})
            else:
                err = result.stderr.strip().split("\n")
                short_err = err[-1] if err else "unknown error"
                self.send_json({"ok": False, "error": short_err, "stderr": result.stderr})
        except subprocess.TimeoutExpired:
            self.send_json({"ok": False, "error": "timeout (30s)"})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)})

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if not any(p in str(args) for p in ("/api/latest", "/api/list", "/api/model", "/api/edit")):
            super().log_message(format, *args)


def main():
    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])

    MODELS_DIR.mkdir(exist_ok=True)

    global _server
    _server = http.server.HTTPServer(("", port), ViewerHandler)
    print(f"build123d viewer: http://localhost:{port}")
    print(f"models dir:       {MODELS_DIR}")
    print(f"python:           {get_python()}")
    print("waiting for .glb files...")
    try:
        _server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        _server.server_close()
        print("viewer shutdown")


if __name__ == "__main__":
    main()
