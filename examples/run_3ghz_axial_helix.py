"""Apply the 3 GHz helix to HFSS, Analyze All, and write results."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Python"))

from pipeline import run_pipeline


if __name__ == "__main__":
    result = run_pipeline(
        config_path=ROOT / "config" / "default_helix.yaml",
        project_root=ROOT,
        dry_run="--dry-run" in sys.argv,
        analyze_all=True if "--analyze-all" in sys.argv else None,
    )
    print(result.validation.overall)
    print(result.dashboard)
