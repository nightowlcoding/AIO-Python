from pathlib import Path
import runpy

# Run the recovered IC3 launcher from bytecode.
ROOT = Path(__file__).resolve().parent
PYC_FILE = ROOT / "inventory_control3_launcher.pyc"

if not PYC_FILE.exists():
    raise FileNotFoundError(f"Missing launcher bytecode: {PYC_FILE}")

runpy.run_path(str(PYC_FILE), run_name="__main__")
