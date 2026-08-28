import sys
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVAL_ROOT))
sys.path.insert(0, str(EVAL_ROOT / "metrics"))
sys.path.insert(0, str(EVAL_ROOT / "datasets" / "match"))
