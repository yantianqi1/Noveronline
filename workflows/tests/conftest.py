from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"

for path in (SRC_ROOT, ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
