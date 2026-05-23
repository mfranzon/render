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
from pathlib import Path

_server = None  # set in main(); used by the /api/shutdown endpoint

PORT = 3123
SKILL_DIR = Path(__file__).resolve().parent.parent
VIEWER_DIR = Path(__file__).resolve().parent
# Project root holds the output dir. Skill lives at <root>/.claude/skills/render
# so the root is SKILL_DIR.parents[2].
PROJECT_ROOT = SKILL_DIR.parents[2]
MODELS_DIR = PROJECT_ROOT / "output"
EDITS_DIR = VIEWER_DIR / "edits"
VENV_PYTHON = SKILL_DIR / ".venv" / "bin" / "python3"


def get_python():
    """Return the venv python if available, else system python3."""
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"


def _model_glbs():
    """Return all model glbs under MODELS_DIR/<name>/<name>.glb (one level deep).

    Older flat-layout files (MODELS_DIR/<name>.glb) are also returned so the
    gallery still shows pre-migration renders.
    """
    nested = [g for g in MODELS_DIR.glob("*/*.glb") if g.stem == g.parent.name]
    flat = list(MODELS_DIR.glob("*.glb"))
    return nested + flat


def get_model_version():
    """Return current version based on latest glb mtime."""
    glbs = _model_glbs()
    if not glbs:
        return 0
    return int(max(os.path.getmtime(f) for f in glbs) * 1000)


def _rel_glb_path(glb: Path) -> str:
    """URL path under /models/ for a given glb file."""
    return glb.relative_to(MODELS_DIR).as_posix()


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(VIEWER_DIR), **kwargs)

    def translate_path(self, path):
        # /models/<rel> is served from the external output directory.
        # Strip query string defensively (base impl usually already does this).
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/models/"):
            rel = clean[len("/models/"):]
            # Block parent-dir escape.
            target = (MODELS_DIR / rel).resolve()
            try:
                target.relative_to(MODELS_DIR.resolve())
            except ValueError:
                return str(MODELS_DIR)  # will 404
            return str(target)
        return super().translate_path(path)

    def _host_ok(self):
        # Block DNS rebinding: only accept localhost Host headers.
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host in ("localhost", "127.0.0.1", "[::1]", "::1", ""):
            return True
        self.send_error(403, "forbidden host")
        return False

    def do_GET(self):
        if not self._host_ok():
            return
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
        if not self._host_ok():
            return
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
        glbs = sorted(_model_glbs(), key=os.path.getmtime, reverse=True)
        step_name = None
        name = None
        file_url = None
        code = ""
        if glbs:
            top = glbs[0]
            name = top.stem
            file_url = _rel_glb_path(top)
            if top.with_suffix(".step").exists():
                step_name = name
            # Each model has its own input script alongside the exports.
            script = self._script_for_name(name)
            if script is not None:
                code = script.read_text(encoding="utf-8")
        data = {
            "file": file_url,
            "name": name,
            "version": get_model_version(),
            "code": code,
            "step": step_name,
        }
        self.send_json(data)

    def _script_for_name(self, name: str) -> Path | None:
        """Resolve the script path for a model name, supporting both layouts."""
        nested = MODELS_DIR / name / f"{name}.py"
        if nested.exists():
            return nested
        flat = MODELS_DIR / f"{name}.py"
        if flat.exists():
            return flat
        return None

    def get_model_info(self):
        # /api/model/<name> — return code for a specific model
        name = self.path.split("/api/model/", 1)[1]
        if "/" in name or "\\" in name or ".." in name or not name:
            self.send_error(400, "invalid name")
            return
        script = self._script_for_name(name)
        try:
            if script is not None:
                script.resolve().relative_to(MODELS_DIR.resolve())
        except ValueError:
            self.send_error(400, "invalid name")
            return
        code = script.read_text(encoding="utf-8") if script else ""
        self.send_json({"name": name, "code": code})

    def list_models(self):
        glbs = sorted(_model_glbs(), key=os.path.getmtime, reverse=True)
        models = []
        for g in glbs:
            stat = g.stat()
            step_exists = g.with_suffix(".step").exists()
            script = g.with_suffix(".py")
            models.append({
                "file": _rel_glb_path(g),
                "name": g.stem,
                "mtime": int(stat.st_mtime * 1000),
                "size": stat.st_size,
                "step": g.stem if step_exists else None,
                "has_script": script.exists(),
            })
        self.send_json({"models": models})

    def download_file(self):
        # /api/download/<name> — serves the STEP for that model name.
        name = self.path.split("/api/download/", 1)[1]
        if "/" in name or "\\" in name or ".." in name or not name:
            self.send_error(400, "invalid name")
            return
        # Strip a trailing .step the client may have appended.
        if name.endswith(".step"):
            name = name[: -len(".step")]
        candidates = [MODELS_DIR / name / f"{name}.step", MODELS_DIR / f"{name}.step"]
        filepath = next((p for p in candidates if p.exists()), None)
        if filepath is None:
            self.send_error(404, "File not found")
            return
        try:
            filepath.resolve().relative_to(MODELS_DIR.resolve())
        except ValueError:
            self.send_error(400, "invalid path")
            return
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/STEP")
        self.send_header("Content-Disposition", f'attachment; filename="{name}.step"')
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def save_edit(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        image_data_url = body.get("image", "")
        prompt = (body.get("prompt") or "").strip()
        model_name = body.get("model") or ""
        if model_name and ("/" in model_name or "\\" in model_name or ".." in model_name):
            self.send_json({"ok": False, "error": "invalid model name"})
            return
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

        # Relative to project root — SKILL.md resolves it via ${CLAUDE_PROJECT_DIR}.
        # Edits without a model name don't have a script to modify, so the path
        # would be invalid — but we still record what the browser sent.
        script_rel = (
            f"output/{model_name}/{model_name}.py"
            if model_name
            else ""
        )
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
        model_name = (body.get("model") or "").strip()
        if not model_name:
            self.send_json({"ok": False, "error": "model name required"})
            return
        if "/" in model_name or "\\" in model_name or ".." in model_name:
            self.send_json({"ok": False, "error": "invalid model name"})
            return

        # Per-model script: each model owns output/<name>/<name>.py.
        script_path = MODELS_DIR / model_name / f"{model_name}.py"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(code, encoding="utf-8")

        t0 = time.time()
        try:
            result = subprocess.run(
                [get_python(), str(script_path)],
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
    _server = http.server.HTTPServer(("127.0.0.1", port), ViewerHandler)
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
