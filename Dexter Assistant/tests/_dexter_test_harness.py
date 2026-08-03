from __future__ import annotations

import os
import tempfile
import types
import warnings
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "dexter_assistant.py"
TEMPLATE_DIR = MODULE_PATH.parent / "templates"
_BOOTSTRAP_TMP = tempfile.TemporaryDirectory()
_BOOTSTRAP_DB_PATH = Path(_BOOTSTRAP_TMP.name) / "bootstrap_rbac.db"


def load_dexter_module() -> types.ModuleType:
    os.environ.setdefault("DEXTER_SECRET_KEY", "dexter-test-secret-key")
    warnings.filterwarnings(
        "ignore",
        message="Using the in-memory storage for tracking rate limits as no storage was explicitly specified.*",
        category=UserWarning,
    )

    module_source = MODULE_PATH.read_text(encoding="utf-8")
    module_source = module_source.replace(
        'RBAC_DB_PATH = ROOT / "dexter_assistant_rbac.db"',
        f'RBAC_DB_PATH = Path(r"{_BOOTSTRAP_DB_PATH}")',
        1,
    )
    module = types.ModuleType("dexter_assistant_module")
    module.__file__ = str(MODULE_PATH)
    exec(compile(module_source, str(MODULE_PATH), "exec"), module.__dict__)
    module.app.template_folder = str(TEMPLATE_DIR)
    if module.app.jinja_loader is not None and hasattr(module.app.jinja_loader, "searchpath"):
        module.app.jinja_loader.searchpath = [str(TEMPLATE_DIR)]
    return module
