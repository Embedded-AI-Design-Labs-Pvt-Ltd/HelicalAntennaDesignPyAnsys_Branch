"""Attach to the open Student project and create Results plots if a solution exists."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import datetime

from ansys_plot_display import AnsysPlotDisplay
from antenna_params import default_config_path, load_config
from hfss_session import HfssSession
from report_generator import write_html, write_plots
from result_extractor import ResultExtractor, theoretical_placeholder
from synthesis import synthesize
from validation import ValidationReport, evaluate

LOGGER = logging.getLogger(__name__)


def create_plots(project_root: Path | None = None) -> list[str]:
    root = project_root or ROOT.parent
    config = synthesize(load_config(default_config_path()))
    config.session.new_desktop = False
    config.session.rebuild_design = False
    session = HfssSession(config, root)
    hfss = session.open()
    try:
        for attr in ("solution_type", "nominal_sweep", "existing_analysis_sweeps"):
            try:
                value = getattr(hfss, attr)
                LOGGER.info("%s = %s", attr, value)
            except Exception:
                pass
        try:
            LOGGER.info("Setups: %s", list(hfss.setup_names))
        except Exception as exc:
            LOGGER.warning("No setups: %s", exc)
        opened: list[str] = []
        try:
            opened = AnsysPlotDisplay(hfss, config).show(include_fields=False)
        except (Exception, SystemExit) as exc:
            LOGGER.warning("HFSS report windows incomplete: %s", exc)
        results = theoretical_placeholder(config)
        try:
            extracted = ResultExtractor(hfss, config).extract()
            if extracted.s11 is not None or extracted.gain_eplane is not None:
                results = extracted
        except (Exception, SystemExit) as exc:
            LOGGER.warning("Could not extract FEM traces yet: %s", exc)
            results.notes.append("HFSS solution is not ready. Dashboard shows Balanis/Kraus comparison templates.")
        results.aedt_reports = opened or results.aedt_reports
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = root / config.project.results_dir / stamp
        output_dir.mkdir(parents=True, exist_ok=True)
        results.write_csv(output_dir / "data")
        plots = write_plots(results, output_dir / "plots", config)
        report = evaluate(config, results) if results.source == "hfss" else ValidationReport(
            overall="READY", criteria=[], source=results.source
        )
        dashboard = write_html(
            config,
            results,
            report,
            output_dir,
            plots,
            {"mode": "plots", "ansys_plots": opened},
        )
        LOGGER.info("Comparison dashboard: %s", dashboard)
        print(f"Dashboard : {dashboard}")
        session.save()
        return opened
    finally:
        session.close(keep_desktop=True)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s")
    opened = create_plots()
    print("Opened HFSS Results plots:", ", ".join(opened) if opened else "(none)")
    if not opened:
        print("Analyze All did not produce a solution, or reports could not be created.")
        print("Check Message Manager for port/validation errors, then Analyze All again.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
