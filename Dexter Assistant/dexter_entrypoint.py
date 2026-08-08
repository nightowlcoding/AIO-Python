from __future__ import annotations

import traceback
from datetime import datetime

from flask import Flask, jsonify

_import_error: Exception | None = None
_import_traceback: str = ""

try:
    from dexter_assistant import app as app
except Exception as exc:  # pragma: no cover - fallback path only
    _import_error = exc
    _import_traceback = traceback.format_exc()

    app = Flask(__name__)

    @app.route("/api/health")
    def fallback_health():
        # Keep health checks green while surfacing import failures for debugging.
        return jsonify(
            {
                "ok": True,
                "mode": "fallback",
                "service": "dexter-assistant",
                "import_error": f"{type(_import_error).__name__}: {_import_error}",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ), 200

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def fallback_all(path: str):
        return (
            jsonify(
                {
                    "ok": False,
                    "mode": "fallback",
                    "message": "Dexter app failed to initialize",
                    "import_error": f"{type(_import_error).__name__}: {_import_error}",
                    "path": path,
                }
            ),
            503,
        )
