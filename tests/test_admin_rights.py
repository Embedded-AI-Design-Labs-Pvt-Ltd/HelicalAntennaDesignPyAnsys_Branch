from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Python"))

from admin_rights import is_admin, subprocess_args


def test_is_admin_returns_bool():
    assert isinstance(is_admin(), bool)


def test_subprocess_args_marks_elevated():
    command = subprocess_args(Path("run_hfss.py"), ["--verbose", "--no-elevate"])
    assert "--elevated" in command
    assert "--no-elevate" not in command
    assert "--verbose" in command
