"""Create HFSS Results reports and extract S11 / VSWR / gain / AR / pattern.

Reports are inserted into the AEDT project Results folder automatically.
Python then reads the same FEM data for CSV, PNG, and the HTML dashboard.
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from antenna_params import DesignConfig
from comparison_reports import comparison_report_jobs

LOGGER = logging.getLogger(__name__)


@dataclass
class Trace:
    x: np.ndarray
    y: np.ndarray
    x_label: str
    y_label: str
    name: str

    def to_rows(self) -> list[tuple[float, float]]:
        return list(zip(self.x.tolist(), self.y.tolist()))


@dataclass
class ComplexTrace:
    x: np.ndarray
    real: np.ndarray
    imag: np.ndarray
    x_label: str
    name: str

    def to_rows(self) -> list[tuple[float, float, float]]:
        return list(zip(self.x.tolist(), self.real.tolist(), self.imag.tolist()))


@dataclass
class ExtractedResults:
    frequency_ghz: float
    s11: Trace | None = None
    vswr: Trace | None = None
    gain_freq: Trace | None = None
    gain_theta: Trace | None = None
    gain_eplane: Trace | None = None
    gain_hplane: Trace | None = None
    directivity_theta: Trace | None = None
    axial_ratio_theta: Trace | None = None
    pattern_phi0: Trace | None = None
    smith: ComplexTrace | None = None
    scalars: dict[str, float] = field(default_factory=dict)
    source: str = "hfss"
    notes: list[str] = field(default_factory=list)
    aedt_reports: list[str] = field(default_factory=list)

    def write_csv(self, directory: Path) -> list[Path]:
        directory.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        traces = {
            "s11": self.s11,
            "vswr": self.vswr,
            "gain_freq": self.gain_freq,
            "gain_theta": self.gain_theta,
            "gain_eplane": self.gain_eplane,
            "gain_hplane": self.gain_hplane,
            "directivity_theta": self.directivity_theta,
            "axial_ratio_theta": self.axial_ratio_theta,
            "pattern_phi0": self.pattern_phi0,
        }
        for name, trace in traces.items():
            if trace is None:
                continue
            path = directory / f"{name}.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow([trace.x_label, trace.y_label])
                writer.writerows(trace.to_rows())
            written.append(path)
        if self.smith is not None:
            path = directory / "smith_s11.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow([self.smith.x_label, "re_s11", "im_s11"])
                writer.writerows(self.smith.to_rows())
            written.append(path)
        scalar_path = directory / "scalars.csv"
        with scalar_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["metric", "value"])
            for key, value in self.scalars.items():
                writer.writerow([key, value])
        written.append(scalar_path)
        return written


class ResultExtractor:
    def __init__(self, hfss: Any, config: DesignConfig):
        self.hfss = hfss
        self.config = config
        self._sweeps: list[str] = []

    def extract(self) -> ExtractedResults:
        self._sweeps = self._candidate_sweeps()
        LOGGER.info("Solution sweeps: %s", self._sweeps)
        created: list[str] = []
        results = ExtractedResults(
            frequency_ghz=self.config.antenna.frequency_ghz,
            source="hfss",
            aedt_reports=created,
        )
        results.s11 = self._trace_from_report("S11_Return_Loss", "s11_db", "dB(S(1,1))") or self._s_parameter()
        results.vswr = self._trace_from_report("VSWR", "vswr", "VSWR(1)") or self._vswr(results.s11)
        results.gain_freq = self._trace_from_report("Gain_Boresight", "gain_dbi", "dB(GainTotal)")
        results.gain_eplane = self._pattern_trace("E_Plane")
        results.gain_hplane = self._pattern_trace("H_Plane")
        results.axial_ratio_theta = self._axial_ratio_trace()
        results.directivity_theta = self._trace_from_report(
            "Directivity_Theta", "directivity_dbi", "dB(DirTotal)", prefer="theta"
        )
        if results.directivity_theta is None and results.gain_eplane is not None:
            ge = results.gain_eplane
            results.directivity_theta = Trace(
                ge.x, ge.y, "theta_deg", "directivity_dbi", "directivity_from_gain"
            )
        results.smith = None
        if results.gain_eplane is not None:
            results.gain_theta = results.gain_eplane
            results.pattern_phi0 = results.gain_eplane
        if results.axial_ratio_theta is not None:
            results.axial_ratio_theta.x_label = "theta_deg"

        self._assign_scalars(results)
        return results

    def _assign_scalars(self, results: ExtractedResults) -> None:
        f0 = float(self.config.validation.resonance_ghz or self.config.antenna.frequency_ghz)
        results.scalars["s11_at_f0_db"] = _value_at(results.s11, f0)
        results.scalars["vswr_at_f0"] = _value_at(results.vswr, f0)
        results.scalars["gain_boresight_dbi"] = _value_at(results.gain_freq, f0)
        if math.isnan(results.scalars["gain_boresight_dbi"]):
            results.scalars["gain_boresight_dbi"] = _value_at(results.gain_eplane, 0.0)
        results.scalars["directivity_boresight_dbi"] = _value_at(results.directivity_theta, 0.0)
        results.scalars["axial_ratio_boresight_db"] = _value_at(results.axial_ratio_theta, 0.0)
        if results.s11 is not None and results.s11.y.size:
            f_dip, s11_dip = nearest_s11_dip(results.s11.x, results.s11.y, f0)
            results.scalars["s11_min_db"] = s11_dip
            results.scalars["s11_min_freq_ghz"] = f_dip
        if results.smith is None and results.s11 is not None:
            mag = 10.0 ** (results.s11.y / 20.0)
            results.smith = ComplexTrace(
                results.s11.x, mag, np.zeros_like(mag), "frequency_ghz", "s11_real_fallback"
            )
        LOGGER.info("Extracted scalars: %s", results.scalars)

    def impedance_at_f0(self) -> complex | None:
        """Port-plane Zin from re(S11) and im(S11) at the design frequency."""
        from synthesis import zin_from_s11

        f0 = float(self.config.validation.resonance_ghz or self.config.antenna.frequency_ghz)
        z0 = float(self.config.feed.port_impedance_ohm)
        self._ensure_complex_s11_reports()
        real = self._trace_from_report("S11_Real", "re_s11", "re(S(1,1))")
        imag = self._trace_from_report("S11_Imag", "im_s11", "im(S(1,1))")
        if real is None or imag is None or real.x.size == 0:
            s11_db = self._trace_from_report("S11_Return_Loss", "s11_db", "dB(S(1,1))")
            if s11_db is None:
                return None
            mag = 10.0 ** (_value_at(s11_db, f0) / 20.0)
            zin = zin_from_s11(complex(mag, 0.0), z0)
            LOGGER.info("Zin from |S11| only (no phase): %.1f + j%.1f Ω", zin.real, zin.imag)
            return zin
        s11 = complex(_value_at(real, f0), _value_at(imag, f0))
        zin = zin_from_s11(s11, z0)
        LOGGER.info("FEM Zin at %.3f GHz = %.1f + j%.1f Ω", f0, zin.real, zin.imag)
        return zin

    def s11_minimum(self) -> tuple[float, float]:
        """Frequency and depth of the S11 dip nearest the design frequency."""
        trace = self._fresh_s11_trace()
        if trace is None or trace.x.size == 0:
            return float("nan"), float("nan")
        f0 = float(self.config.validation.resonance_ghz or self.config.antenna.frequency_ghz)
        freq_ghz, depth_db = nearest_s11_dip(trace.x, trace.y, f0)
        LOGGER.info("S11 dip nearest %.3f GHz: %.2f dB at %.3f GHz", f0, depth_db, freq_ghz)
        return freq_ghz, depth_db

    def s11_at_frequency(self, freq_ghz: float) -> float:
        trace = self._fresh_s11_trace()
        if trace is None:
            return float("nan")
        return _value_at(trace, freq_ghz)

    def _fresh_s11_trace(self) -> Trace | None:
        self._delete_named_reports(("S11_Return_Loss", "S11_Real", "S11_Imag"))
        self._ensure_complex_s11_reports()
        return self._trace_from_report("S11_Return_Loss", "s11_db", "dB(S(1,1))")

    def _delete_named_reports(self, names: tuple[str, ...]) -> None:
        try:
            omodule = self.hfss.odesign.GetModule("ReportSetup")
            existing = [str(item) for item in omodule.GetAllReportNames()]
            doomed = [item for item in existing if item in names]
            if doomed:
                omodule.DeleteReports(doomed)
        except Exception:
            pass

    def _ensure_complex_s11_reports(self) -> None:
        setups = list(self._candidate_sweeps())
        default = f"{self.config.solver.setup_name} : {self.config.solver.sweep_name}"
        if default not in setups:
            setups.append(default)
        try:
            omodule = self.hfss.odesign.GetModule("ReportSetup")
            existing = [str(item) for item in omodule.GetAllReportNames()]
        except Exception:
            return
        jobs = (
            ("S11_Real", "re(S(1,1))"),
            ("S11_Imag", "im(S(1,1))"),
            ("S11_Return_Loss", "dB(S(1,1))"),
        )
        for name, expr in jobs:
            if name in existing:
                continue
            created = False
            for setup in setups:
                try:
                    omodule.CreateReport(
                        name,
                        "Modal Solution Data",
                        "Rectangular Plot",
                        setup,
                        ["Domain:=", "Sweep"],
                        ["Freq:=", ["All"]],
                        ["X Component:=", "Freq", "Y Component:=", [expr]],
                    )
                    created = True
                    LOGGER.info("Created %s on %s", name, setup)
                    break
                except Exception:
                    continue
            if not created:
                LOGGER.warning("Could not create HFSS report %s", name)

    def create_project_reports(self) -> list[str]:
        """Insert the comparison report set into the HFSS Results folder."""
        created: list[str] = []
        setup_sweep = None
        try:
            setup_sweep = getattr(self.hfss, "nominal_sweep", None)
        except Exception:
            setup_sweep = None
        for job in comparison_report_jobs(self.config, setup_sweep):
            kwargs = {
                "plot_type": job["plot_type"],
                "report_category": job["report_category"],
            }
            if job.get("context"):
                kwargs["context"] = job["context"]
            if job.get("primary"):
                kwargs["primary_sweep_variable"] = job["primary"]
            if job.get("variations"):
                kwargs["variations"] = job["variations"]
            if self._create_report(job["name"], job["expressions"], **kwargs):
                created.append(job["name"])
        LOGGER.info("HFSS Results reports created: %s", created)
        return created

    def export_aedt_images(self, directory: Path, report_names: list[str]) -> list[Path]:
        directory.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for name in report_names:
            try:
                self.hfss.post.export_report_to_jpg(str(directory), name)
                match = list(directory.glob(f"{name}.*"))
                written.extend(match)
            except Exception as exc:
                LOGGER.debug("export_report_to_jpg(%s) failed: %s", name, exc)
        return written

    def _create_report(self, name: str, expressions: str, **kwargs: Any) -> bool:
        try:
            self.hfss.post.create_report(
                expressions=expressions,
                plot_name=name,
                matplotlib=False,
                show=True,
                **kwargs,
            )
            return True
        except (Exception, SystemExit) as exc:
            LOGGER.debug("create_report(%s) failed: %s — retrying with defaults", name, exc)
        try:
            self.hfss.post.create_report(expressions, plot_name=name)
            return True
        except (Exception, SystemExit) as exc:
            LOGGER.warning("Could not create HFSS report %s: %s", name, exc)
            return False

    def _candidate_sweeps(self) -> list[str]:
        names: list[str] = []
        setup = self.config.solver.setup_name
        try:
            for item in list(getattr(self.hfss, "existing_analysis_sweeps", []) or []):
                text = str(item)
                if "Table" in text:
                    continue
                names.append(text)
        except Exception:
            pass
        try:
            osetup = self.hfss.odesign.GetModule("AnalysisSetup")
            for item in osetup.GetSweeps(setup):
                names.append(f"{setup} : {item}")
        except Exception:
            pass
        names.append(f"{setup} : {self.config.solver.sweep_name}")
        names.append(f"{setup} : LastAdaptive")
        unique: list[str] = []
        for name in names:
            if name and name not in unique:
                unique.append(name)
        unique.sort(
            key=lambda item: (
                0 if item.endswith(" : Sweep1") else
                1 if "Sweep1" in item else
                2 if "Sweep" in item else
                3 if "LastAdaptive" in item else 4,
                item,
            )
        )
        return unique

    def _s_parameter(self) -> Trace | None:
        expressions = [
            "dB(S(1,1))",
            f"dB(S({self.config.feed.port_name},{self.config.feed.port_name}))",
            "dB(St(Port1_T1,Port1_T1))",
        ]
        for expr in expressions:
            trace = self._sweep_trace(expr, "s11_db", "Freq")
            if trace is not None:
                return trace
        self._note("S11 not available from post-processor")
        return None

    def _vswr(self, s11: Trace | None) -> Trace | None:
        exported = self._trace_from_report("VSWR", "vswr", "VSWR(1)")
        if exported is not None:
            return exported
        if s11 is not None:
            mag = 10.0 ** (s11.y / 20.0)
            vswr = (1.0 + mag) / np.maximum(1.0 - mag, 1e-6)
            return Trace(s11.x, vswr, "frequency_ghz", "vswr", "vswr_from_s11")
        return self._sweep_trace("VSWR(1)", "vswr", "Freq")

    def _sweep_trace(self, expression: str, y_label: str, sweep: str) -> Trace | None:
        data = self._get_solution_data(expression, report_category=None, context=None, primary=sweep)
        if data is None:
            return None
        x_raw, y_raw = _xy_from_solution(data)
        if not x_raw:
            return None
        return Trace(
            np.asarray(x_raw, dtype=float),
            np.asarray(y_raw, dtype=float),
            "frequency_ghz",
            y_label,
            expression,
        )

    def _smith(self) -> ComplexTrace | None:
        exported = self._trace_from_report("Smith_S11", "s11_real", "S(1,1)")
        if exported is not None:
            return ComplexTrace(exported.x, exported.y, np.zeros_like(exported.y), "frequency_ghz", "S(1,1)")
        for expr in ("S(1,1)", f"S({self.config.feed.port_name},{self.config.feed.port_name})"):
            data = self._get_solution_data(expr, report_category=None, context=None, primary="Freq")
            if data is None:
                continue
            x_raw, re_raw, im_raw = _complex_from_solution(data)
            if x_raw is None:
                continue
            return ComplexTrace(
                np.asarray(x_raw, dtype=float),
                np.asarray(re_raw, dtype=float),
                np.asarray(im_raw, dtype=float),
                "frequency_ghz",
                expr,
            )
        self._note("Smith-chart S11 not available from post-processor")
        return None

    def _far_field(
        self,
        expression: str,
        y_label: str,
        db_if_linear: bool = False,
        primary: str = "Theta",
        variations: dict | None = None,
        x_label: str | None = None,
    ) -> Trace | None:
        f0 = f"{self.config.antenna.frequency_ghz}GHz"
        if variations is None:
            variations = {"Freq": [f0], "Phi": ["0deg"], "Theta": ["All"]}
        data = self._get_solution_data(
            expression,
            report_category="Far Fields",
            context=self.config.boundary.infinite_sphere,
            primary=primary,
            variations=variations,
        )
        if data is None and expression.startswith("dB("):
            inner = expression[3:-1]
            data = self._get_solution_data(
                inner,
                report_category="Far Fields",
                context=self.config.boundary.infinite_sphere,
                primary=primary,
                variations=variations,
            )
        if data is None:
            return None
        x_raw, y_raw = _xy_from_solution(data)
        if x_raw is None:
            return None
        y = np.asarray(y_raw, dtype=float)
        if db_if_linear and y.size and np.nanmax(y) < 20.0:
            y = 10.0 * np.log10(np.maximum(y, 1e-12))
        return Trace(
            np.asarray(x_raw, dtype=float),
            y,
            x_label or ("frequency_ghz" if primary == "Freq" else "theta_deg"),
            y_label,
            expression,
        )

    def _get_solution_data(
        self,
        expression: str,
        report_category: str | None,
        context: str | None,
        primary: str,
        variations: dict | None = None,
    ) -> Any:
        sweeps = getattr(self, "_sweeps", None) or self._candidate_sweeps()
        base: dict[str, Any] = {
            "expressions": expression,
            "primary_sweep_variable": primary,
        }
        if report_category:
            base["report_category"] = report_category
        if context:
            base["context"] = context
        if variations:
            base["variations"] = variations
        for sweep in sweeps:
            for key in ("setup_sweep_name", "sweep"):
                try:
                    data = self.hfss.post.get_solution_data(**base, **{key: sweep})
                except TypeError:
                    continue
                except (Exception, SystemExit) as exc:
                    LOGGER.debug("get_solution_data(%s, %s=%s) failed: %s", expression, key, sweep, exc)
                    continue
                x_raw, _y_raw = _xy_from_solution(data)
                if x_raw:
                    LOGGER.info("Read %s from %s=%s (%s points)", expression, key, sweep, len(x_raw))
                    return data
        return None

    def _pattern_trace(self, report_name: str) -> Trace | None:
        trace = self._trace_from_report(report_name, "gain_dbi", "dB(GainTotal)", prefer="theta")
        if trace is None or trace.x.size < 3:
            return None
        trace.x_label = "theta_deg"
        return trace

    def _axial_ratio_trace(self) -> Trace | None:
        raw = self._trace_from_report("AR_vs_Theta", "axial_ratio_db", "AxialRatio", prefer="theta")
        if raw is not None and raw.x.size >= 3:
            y = np.asarray(raw.y, dtype=float)
            if "ratio" in raw.name.lower() and np.nanmin(y) >= 1.0:
                y = 20.0 * np.log10(np.maximum(y, 1.0))
            return Trace(raw.x, y, "theta_deg", "axial_ratio_db", raw.name)
        rhcp = self._trace_from_report("Gain_RHCP_Theta", "gain_dbi", "dB(GainRHCP)", prefer="theta")
        lhcp = self._trace_from_report("Gain_LHCP_Theta", "gain_dbi", "dB(GainLHCP)", prefer="theta")
        computed = _axial_ratio_from_circular(rhcp, lhcp)
        if computed is not None:
            LOGGER.info("Built AR vs theta from Gain RHCP/LHCP (%s points)", computed.x.size)
        return computed

    def _trace_from_report(self, report_name: str, y_label: str, expression: str, prefer: str | None = None) -> Trace | None:
        from tempfile import TemporaryDirectory

        try:
            omodule = self.hfss.odesign.GetModule("ReportSetup")
            names = [str(item) for item in omodule.GetAllReportNames()]
        except Exception as exc:
            LOGGER.warning("ReportSetup unavailable: %s", exc)
            return None
        match = next((item for item in names if item == report_name or item.endswith(report_name)), None)
        if match is None:
            LOGGER.warning("HFSS report %s not in %s", report_name, names)
            return None
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{report_name}.csv"
            try:
                if hasattr(omodule, "UpdateReports"):
                    omodule.UpdateReports([match])
                omodule.ExportToFile(match, str(path))
            except Exception as exc:
                LOGGER.warning("ExportToFile(%s) failed: %s", match, exc)
                return None
            rows = _read_hfss_csv(path, prefer=prefer)
            if not rows:
                preview = path.read_text(encoding="utf-8", errors="ignore")[:400] if path.exists() else ""
                LOGGER.warning("Exported %s but CSV had no numeric rows. Preview: %s", match, preview)
                return None
        LOGGER.info("Read %s points from HFSS report %s", len(rows), match)
        x = np.asarray([row[0] for row in rows], dtype=float)
        y = np.asarray([row[1] for row in rows], dtype=float)
        return Trace(x, y, "frequency_ghz", y_label, expression)

    def _note(self, message: str) -> None:
        LOGGER.warning(message)


def _parse_hfss_number(text: str) -> float | None:
    cleaned = text.strip().strip('"').replace("'", "")
    for suffix in ("GHz", "MHz", "kHz", "Hz", "deg", "dB"):
        cleaned = cleaned.replace(suffix, "")
    cleaned = cleaned.replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _read_hfss_csv(path: Path, prefer: str | None = None) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return rows
    lines = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return rows
    header_parts = [part.strip().strip('"') for part in lines[0].replace(";", ",").replace("\t", ",").split(",")]
    x_idx, y_idx = 0, 1 if len(header_parts) > 1 else 0
    if prefer:
        for idx, part in enumerate(header_parts):
            if prefer.lower() in part.lower():
                x_idx = idx
                break
        for idx, part in enumerate(header_parts):
            if idx != x_idx and (part.startswith("dB(") or "Gain" in part or "Axial" in part or "VSWR" in part or "S(" in part):
                y_idx = idx
                break
        if y_idx == x_idx:
            y_idx = 1 if x_idx == 0 else 0
    header_looks_labeled = any(
        _parse_hfss_number(part) is None
        or "deg" in part.lower()
        or "ghz" in part.lower()
        or "db(" in part.lower()
        for part in header_parts
        if part
    )
    start = 1 if header_looks_labeled else 0
    wide = _wide_theta_row(header_parts, lines[start:])
    if wide:
        return wide
    for line in lines[start:]:
        parts = [part.strip() for part in line.replace(";", ",").replace("\t", ",").split(",")]
        if max(x_idx, y_idx) >= len(parts):
            continue
        x = _parse_hfss_number(parts[x_idx])
        y = _parse_hfss_number(parts[y_idx])
        if x is None or y is None:
            continue
        rows.append((x, y))
    return rows


def _wide_theta_row(headers: list[str], data_lines: list[str]) -> list[tuple[float, float]]:
    """HFSS sometimes exports Freq as X and one column per theta."""
    import re

    theta_cols: list[tuple[int, float]] = []
    for idx, header in enumerate(headers):
        match = re.search(r"Theta\s*[=:'\[]\s*(-?\d+(?:\.\d+)?)\s*deg", header, flags=re.IGNORECASE)
        if match is None:
            match = re.search(r"\[(-?\d+(?:\.\d+)?)deg\]", header, flags=re.IGNORECASE)
        if match is None:
            continue
        theta_cols.append((idx, float(match.group(1))))
    if not data_lines:
        return []
    parts = [part.strip() for part in data_lines[0].replace(";", ",").replace("\t", ",").split(",")]
    if len(theta_cols) >= 3:
        rows: list[tuple[float, float]] = []
        for idx, angle in theta_cols:
            if idx >= len(parts):
                continue
            value = _parse_hfss_number(parts[idx])
            if value is None:
                continue
            rows.append((angle, value))
        if rows and len({row[0] for row in rows}) > 1:
            return rows
    values = [_parse_hfss_number(part) for part in parts]
    numeric = [value for value in values if value is not None]
    if values and values[0] is not None and 2.0 < values[0] < 6.0:
        numeric = [value for value in values[1:] if value is not None]
    paired = _theta_value_pairs(numeric)
    if paired:
        return paired
    if len(numeric) >= 3:
        step = 180.0 / (len(numeric) - 1)
        return [(idx * step, value) for idx, value in enumerate(numeric)]
    return []


def _theta_value_pairs(numeric: list[float]) -> list[tuple[float, float]]:
    if len(numeric) < 6 or len(numeric) % 2:
        return []
    xs = numeric[0::2]
    ys = numeric[1::2]
    if _looks_like_theta_axis(xs) and not _looks_like_theta_axis(ys):
        return list(zip(xs, ys))
    return []


def _looks_like_theta_axis(values: list[float]) -> bool:
    if len(values) < 3:
        return False
    if abs(values[0]) > 1.0:
        return False
    if values[-1] < 90.0:
        return False
    steps = [values[idx + 1] - values[idx] for idx in range(min(6, len(values) - 1))]
    return all(3.0 <= step <= 15.0 for step in steps)


def _axial_ratio_from_circular(rhcp: Trace | None, lhcp: Trace | None) -> Trace | None:
    if rhcp is None or lhcp is None or rhcp.x.size < 3 or lhcp.x.size < 3:
        return None
    x = rhcp.x
    if lhcp.x.size != x.size or not np.allclose(lhcp.x, x, atol=0.05, equal_nan=True):
        y_lhcp = np.interp(x, lhcp.x, lhcp.y)
    else:
        y_lhcp = lhcp.y
    co = np.maximum(10.0 ** (rhcp.y / 20.0), 1e-12)
    cx = np.maximum(10.0 ** (y_lhcp / 20.0), 1e-12)
    ar_lin = (co + cx) / np.maximum(np.abs(co - cx), 1e-12)
    return Trace(x, 20.0 * np.log10(ar_lin), "theta_deg", "axial_ratio_db", "AR_from_RHCP_LHCP")


def _xy_from_solution(data: Any) -> tuple[list[float] | None, list[float] | None]:
    try:
        x = list(data.primary_sweep_values)
    except Exception:
        try:
            x = list(data.sweeps[data.primary_sweep])
        except Exception:
            return None, None
    y = None
    for attr in ("data_real", "data_magnitude"):
        try:
            raw = getattr(data, attr)
            if callable(raw):
                raw = raw()
            if isinstance(raw, dict):
                y = list(next(iter(raw.values())))
            else:
                y = list(raw)
            break
        except Exception:
            continue
    if y is None:
        try:
            y = list(data.data_real())
        except Exception:
            return None, None
    if len(x) != len(y):
        n = min(len(x), len(y))
        x, y = x[:n], y[:n]
    return x, y


def _complex_from_solution(data: Any) -> tuple[list[float] | None, list[float] | None, list[float] | None]:
    x, re = _xy_from_solution(data)
    if x is None:
        return None, None, None
    imag = None
    for attr in ("data_imag", "imag"):
        try:
            raw = getattr(data, attr)
            if callable(raw):
                raw = raw()
            if isinstance(raw, dict):
                imag = list(next(iter(raw.values())))
            else:
                imag = list(raw)
            break
        except Exception:
            continue
    if imag is None:
        imag = [0.0] * len(x)
    n = min(len(x), len(re or []), len(imag))
    return x[:n], (re or [])[:n], imag[:n]


def _value_at(trace: Trace | None, x_target: float) -> float:
    if trace is None or trace.x.size == 0:
        return math.nan
    idx = int(np.argmin(np.abs(trace.x - x_target)))
    return float(trace.y[idx])


def nearest_s11_dip(
    freqs: np.ndarray,
    s11_db: np.ndarray,
    f0: float,
) -> tuple[float, float]:
    """Local S11 minimum nearest ``f0``. Falls back to the global minimum."""
    xs = np.asarray(freqs, dtype=float)
    ys = np.asarray(s11_db, dtype=float)
    if xs.size == 0:
        return float("nan"), float("nan")
    candidates: list[tuple[float, float]] = []
    for i in range(1, ys.size - 1):
        if ys[i] <= ys[i - 1] and ys[i] <= ys[i + 1]:
            candidates.append((float(xs[i]), float(ys[i])))
    if candidates:
        return min(candidates, key=lambda item: abs(item[0] - f0))
    idx = int(np.argmin(ys))
    return float(xs[idx]), float(ys[idx])


def theoretical_placeholder(config: DesignConfig) -> ExtractedResults:
    """Used only when ``--dry-run`` is requested explicitly."""
    ant = config.antenna
    f0 = float(config.validation.resonance_ghz or ant.frequency_ghz)
    freq = np.concatenate(
        [
            np.linspace(f0 * 0.85, f0, 60, endpoint=False),
            np.linspace(f0, f0 * 1.15, 62),
        ]
    )
    # Single resonance only: unmatched floor, matched peak deeper than -20 dB at f0.
    s11_floor = -6.0
    s11_peak = min(config.validation.s11_max_db - 5.0, -25.0)
    sigma = 0.028 * f0
    s11 = s11_floor + (s11_peak - s11_floor) * np.exp(-((freq - f0) ** 2) / (2.0 * sigma**2))
    mag = 10.0 ** (s11 / 20.0)
    vswr = (1.0 + mag) / np.maximum(1.0 - mag, 1e-6)

    theta = np.linspace(0.0, 180.0, 181)
    hpbw = max(ant.theoretical_hpbw_deg, 20.0)
    sigma = hpbw / 2.355
    pattern = ant.theoretical_gain_dbi - 12.0 * (theta / 90.0) ** 2
    pattern -= 40.0 * np.exp(-((theta - 180.0) ** 2) / (2 * sigma**2))
    ar = ant.theoretical_axial_ratio_db + 0.15 * theta

    gamma = mag
    results = ExtractedResults(frequency_ghz=f0, source="theoretical")
    results.s11 = Trace(freq, s11, "frequency_ghz", "s11_db", "theoretical_s11")
    results.vswr = Trace(freq, vswr, "frequency_ghz", "vswr", "theoretical_vswr")
    results.gain_freq = Trace(
        freq,
        np.full_like(freq, ant.theoretical_gain_dbi),
        "frequency_ghz",
        "gain_dbi",
        "theoretical_gain_freq",
    )
    results.gain_theta = Trace(theta, pattern, "theta_deg", "gain_dbi", "theoretical_gain")
    results.gain_eplane = results.gain_theta
    results.gain_hplane = Trace(theta, pattern - 0.4, "theta_deg", "gain_dbi", "theoretical_hplane")
    results.directivity_theta = Trace(
        theta, pattern + 0.15, "theta_deg", "directivity_dbi", "theoretical_directivity"
    )
    results.axial_ratio_theta = Trace(theta, ar, "theta_deg", "axial_ratio_db", "theoretical_ar")
    results.pattern_phi0 = results.gain_theta
    results.smith = ComplexTrace(freq, gamma, np.zeros_like(gamma), "frequency_ghz", "theoretical_s11")
    results.scalars = {
        "s11_at_f0_db": float(np.interp(f0, freq, s11)),
        "vswr_at_f0": float(np.interp(f0, freq, vswr)),
        "gain_boresight_dbi": float(ant.theoretical_gain_dbi),
        "directivity_boresight_dbi": float(pattern[0] + 0.15),
        "axial_ratio_boresight_db": float(ar[0]),
        "s11_min_db": float(np.min(s11)),
        "s11_min_freq_ghz": float(freq[int(np.argmin(s11))]),
    }
    results.notes.append("Dry-run traces are theoretical placeholders, not HFSS FEM results.")
    return results
