from pathlib import Path
import marshal

ROOT = Path(__file__).resolve().parent
BYTECODE_FILE = ROOT / "ml_trends.pyc"

if not BYTECODE_FILE.exists():
    raise FileNotFoundError(f"Missing compiled ml_trends bytecode: {BYTECODE_FILE}")

data = BYTECODE_FILE.read_bytes()
if len(data) < 16:
    raise ValueError(f"Invalid bytecode file header: {BYTECODE_FILE}")

code = marshal.loads(data[16:])
exec(code, globals(), globals())
