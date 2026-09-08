"""Open Ansys Electronics Desktop Student, load the project, and apply setup.

Default: leave Analyze All to the HFSS GUI so you can generate and inspect plots.
Use --analyze-all to solve from Python as well.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from admin_rights import ensure_admin, is_admin  # noqa: E402
from antenna_params import load_config  # noqa: E402
from pipeline import run_pipeline  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Open AEDT Student, load the helical antenna project, and apply HFSS setup."
    )
    parser.add_argument(
        "--config",
        default=str(ROOT.parent / "config" / "default_helix.yaml"),
        help="YAML configuration file",
    )
    parser.add_argument(
        "--analyze-all",
        action="store_true",
        help="Also run HFSS Analyze All from Python after the setup is applied.",
    )
    parser.add_argument(
        "--plots",
        action="store_true",
        help="Do not rebuild. Create S, Gain, VSWR, AR, Smith, E-plane, and H-plane comparison plots.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Optional: skip AEDT and write a theoretical dashboard only.",
    )
    parser.add_argument(
        "--synthesize-only",
        action="store_true",
        help="Optional: write Balanis dimensions only.",
    )
    parser.add_argument(
        "--no-elevate",
        action="store_true",
        help="Do not request Administrator elevation.",
    )
    parser.add_argument(
        "--elevated",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    )

    wants_hfss = not args.dry_run and not args.synthesize_only
    config = load_config(args.config)
    if wants_hfss and config.session.admin_mode and not args.no_elevate and not is_admin():
        ensure_admin(argv if argv is not None else sys.argv[1:], working_dir=ROOT.parent)
    logging.info("Privilege level: %s", "Administrator (full rights)" if is_admin() else "standard user")

    if args.plots:
        from create_results_plots import create_plots

        opened = create_plots(ROOT.parent)
        print("Opened HFSS Results plots:", ", ".join(opened) if opened else "(none)")
        return 0 if opened else 1

    result = run_pipeline(
        config_path=args.config,
        project_root=ROOT.parent,
        dry_run=args.dry_run,
        synthesize_only=args.synthesize_only,
        analyze_all=True if args.analyze_all else None,
    )
    print(f"Status    : {result.validation.overall}")
    if result.setup_only:
        print("AEDT Student is open with the project loaded and Setup1 applied.")
        print("In HFSS: right-click Analysis -> Analyze All, then open Results to view plots.")
        print(f"Project   : {ROOT.parent / 'work' / 'Helical_Antenna.aedt'}")
        return 0
    print(f"Dashboard : {result.dashboard}")
    print(f"Results   : {result.output_dir}")
    return 0 if result.validation.passed or result.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
