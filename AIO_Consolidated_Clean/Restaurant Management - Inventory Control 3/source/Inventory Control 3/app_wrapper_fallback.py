from pathlib import Path
import runpy

# Run the recovered compiled IC3 app from bytecode.
ROOT = Path(__file__).resolve().parent
PYC_FILE = ROOT / "app.pyc"

if not PYC_FILE.exists():
    raise FileNotFoundError(f"Missing compiled app bytecode: {PYC_FILE}")

runpy.run_path(str(PYC_FILE), run_name="__main__")
