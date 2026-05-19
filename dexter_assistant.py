from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "Dexter Assistant" / "dexter_assistant.py"

if not _MODULE_PATH.exists():
    raise FileNotFoundError(f"Dexter Assistant entrypoint not found: {_MODULE_PATH}")

_spec = importlib.util.spec_from_file_location("dexter_assistant_impl", _MODULE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Failed to load module spec for {_MODULE_PATH}")

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

app = _module.app
