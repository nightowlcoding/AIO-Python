from pathlib import Path
import marshal

ROOT = Path(__file__).resolve().parent
BYTECODE_FILE = ROOT / "inventory_control3_launcher.pyc"

def _exec_bytecode() -> None:
    if not BYTECODE_FILE.exists():
        raise FileNotFoundError(f"Missing launcher bytecode: {BYTECODE_FILE}")

    data = BYTECODE_FILE.read_bytes()
    if len(data) < 16:
        raise ValueError(f"Invalid bytecode file header: {BYTECODE_FILE}")

    code = marshal.loads(data[16:])
    exec(code, globals(), globals())


_exec_bytecode()
