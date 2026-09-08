"""Open AEDT Student, load the project, apply setup, leave Analyze All to the user."""

from __future__ import annotations

import logging
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from ansys_plot_display import AnsysPlotDisplay
from antenna_params import DesignConfig, load_config
from boundary_setup import BoundarySetup
from geometry_generator import GeometryGenerator
from hfss_session import PYAEDT_AVAILABLE, HfssSession
from port_setup import PortSetup
from report_generator import write_html, write_plots
from result_extractor import ExtractedResults, ResultExtractor, theoretical_placeholder
from simulation_runner import SimulationRunner
from solver_setup import SolverSetup
from synthesis import synthesize, synthesis_summary
from validation import ValidationReport, evaluate

LOGGER = logging.getLogger(__name__)


def _build_hfss_model(hfss: Any, config: DesignConfig, session: HfssSession) -> PortSetup:
    """Create geometry, port, radiation, and analysis setup on an empty design."""
    LOGGER.info("Applying helical geometry to HFSS design %s", config.project.design)
    objects = GeometryGenerator(hfss, config).create()
    LOGGER.info("Applying port %s", config.feed.port_name)
    port = PortSetup(hfss, config, objects)
    port.create()
    LOGGER.info("Applying radiation boundary and infinite sphere")
    BoundarySetup(hfss, config, objects).create()
    LOGGER.info("Applying analysis setup and frequency sweep to the Student project")
    SolverSetup(hfss, config, objects).apply()
    session.save()
    return port


class PipelineResult:
    def __init__(
        self,
        config: DesignConfig,
        results: ExtractedResults,
        validation: ValidationReport,
        output_dir: Path,
        dashboard: Path,
        dry_run: bool,
        setup_only: bool = False,
    ):
        self.config = config
        self.results = results
        self.validation = validation
        self.output_dir = output_dir
        self.dashboard = dashboard
        self.dry_run = dry_run
        self.setup_only = setup_only


def run_pipeline(
    config_path: str | Path | None = None,
    project_root: str | Path | None = None,
    dry_run: bool = False,
    synthesize_only: bool = False,
    analyze_all: bool | None = None,
) -> PipelineResult:
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
    if config_path is None:
        from antenna_params import default_config_path

        config_path = default_config_path()

    config = synthesize(load_config(config_path))
    if analyze_all is not None:
        config.solver.analyze_all = analyze_all

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = root / config.project.results_dir / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Synthesis: %s", synthesis_summary(config))
    if synthesize_only:
        results = theoretical_placeholder(config)
        results.notes.append("synthesize-only: HFSS was not launched.")
        return _finalize(config, results, output_dir, dry_run=True, meta={"mode": "synthesize-only"})

    if dry_run:
        results = theoretical_placeholder(config)
        return _finalize(config, results, output_dir, dry_run=True, meta={"mode": "dry-run"})

    if not PYAEDT_AVAILABLE:
        raise RuntimeError(
            "PyAEDT is not installed. Install with: pip install ansys-aedt-core"
        )

    session = HfssSession(config, root)
    hfss = session.open()
    try:
        port = _build_hfss_model(hfss, config, session)
        session.notify_ready()

        if not config.solver.analyze_all:
            LOGGER.info(
                "Electronics Desktop Student is ready. "
                "In HFSS: right-click Analysis → Analyze All to solve and view plots."
            )
            opened: list[str] = []
            results = theoretical_placeholder(config)
            results.source = "setup_applied"
            results.notes = [
                "Ansys Electronics Desktop Student is open with the project loaded.",
                "Setup1 + Sweep1 are applied under Analysis.",
                "Do not create Results plots until Analyze All finishes a valid solve.",
                "After the solve: python run_hfss.py --plots",
                f"Project file: {session.project_path}",
            ]
            ready = ValidationReport(overall="READY", criteria=[], source="setup_applied")
            note = output_dir / "SETUP_READY.txt"
            note.write_text("\n".join(results.notes), encoding="utf-8")
            plots = write_plots(results, output_dir / "plots", config, theory=None)
            dashboard = write_html(
                config,
                results,
                ready,
                output_dir,
                plots,
                {"mode": "setup_applied", "ansys_plots": opened},
            )
            return PipelineResult(
                config,
                results,
                ready,
                output_dir,
                dashboard,
                dry_run=False,
                setup_only=True,
            )

        LOGGER.info("Starting HFSS Analyze All")
        runner = SimulationRunner(hfss, config)
        run_info = runner.analyze_all()
        session.save()
        extractor = ResultExtractor(hfss, config)
        opened: list[str] = []
        if config.session.show_plots_in_ansys:
            LOGGER.info("Opening simulation plots in the Ansys HFSS GUI")
            try:
                opened = AnsysPlotDisplay(hfss, config).show(include_fields=False)
            except (Exception, SystemExit) as exc:
                LOGGER.warning("HFSS plot windows incomplete: %s", exc)
                opened = []
            run_info["ansys_plots"] = opened
        LOGGER.info("Extracting FEM traces")
        results = extractor.extract()
        results.aedt_reports = opened or results.aedt_reports
        if opened:
            results.notes.append("Simulation plots are open in Ansys Electronics Desktop Student.")
            try:
                extractor.export_aedt_images(output_dir / "aedt_reports", results.aedt_reports)
            except Exception:
                pass
        try:
            session.save()
        except Exception:
            pass
        return _finalize(config, results, output_dir, dry_run=False, meta=run_info)
    except Exception:
        try:
            session.save()
            session.bring_to_front()
        except Exception:
            pass
        raise
    finally:
        try:
            session.close(keep_desktop=True)
        except Exception:
            LOGGER.debug("Desktop release after apply skipped")


def _finalize(
    config: DesignConfig,
    results: ExtractedResults,
    output_dir: Path,
    dry_run: bool,
    meta: dict[str, Any],
) -> PipelineResult:
    report = evaluate(config, results)
    csv_dir = output_dir / "data"
    plot_dir = output_dir / "plots"
    results.write_csv(csv_dir)
    plots = write_plots(results, plot_dir, config)
    dashboard = write_html(config, results, report, output_dir, plots, meta)
    LOGGER.info("Dashboard: %s", dashboard)
    LOGGER.info("Validation: %s", report.overall)
    if config.session.auto_open_dashboard:
        _open_dashboard(dashboard)
    return PipelineResult(config, results, report, output_dir, dashboard, dry_run)


def _open_dashboard(dashboard: Path) -> None:
    try:
        webbrowser.open(dashboard.resolve().as_uri())
        LOGGER.info("Opened dashboard in the default browser")
    except Exception as exc:
        LOGGER.warning("Could not open dashboard automatically: %s", exc)
