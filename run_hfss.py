"""One-command HFSS automation from the project root."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "Python"))

from run import main


if __name__ == "__main__":
    raise SystemExit(main())
