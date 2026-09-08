"""Windows Administrator elevation for the HFSS automation process.

AEDT COM, license checkout, and project writes inherit this process token.
The elevated Python process is what launches Electronics Desktop.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def is_admin() -> bool:
    if os.name != "nt":
        return hasattr(os, "geteuid") and os.geteuid() == 0
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin(argv: list[str] | None = None, working_dir: Path | None = None) -> None:
    """Re-launch this script with a full Administrator token if needed."""
    if is_admin():
        LOGGER.info("Admin mode: full-rights token is active")
        return
    if os.name != "nt":
        LOGGER.warning("Admin elevation is only automated on Windows")
        return

    import ctypes

    script = Path(sys.argv[0]).resolve()
    args = argv if argv is not None else sys.argv[1:]
    command = subprocess_args(script, args)
    directory = str(working_dir or script.parent)
    LOGGER.info("Requesting Administrator elevation (UAC)")
    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        command,
        directory,
        1,
    )
    if rc <= 32:
        raise RuntimeError(
            f"Administrator elevation failed (ShellExecuteW={rc}). "
            "Right-click Run_HFSS_Simulation.bat and choose Run as administrator."
        )
    raise SystemExit(0)


def subprocess_args(script: Path, args: list[str]) -> str:
    parts = [f'"{script}"']
    for item in args:
        if item in {"--no-elevate"}:
            continue
        parts.append(f'"{item}"' if " " in item else item)
    parts.append("--elevated")
    return " ".join(parts)
