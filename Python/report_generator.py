"""CSV, PNG plots, and a self-contained HTML dashboard."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from antenna_params import DesignConfig
from result_extractor import ComplexTrace, ExtractedResults, Trace, theoretical_placeholder
from synthesis import synthesis_summary
from validation import ValidationReport

HFSS_COLOR = "#e8b86d"
THEORY_COLOR = "#7eb6ff"
LIMIT_COLOR = "#7ec8a3"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "axes.facecolor": "#12171f",
        "figure.facecolor": "#0c1016",
        "axes.edgecolor": "#3d4a5c",
        "axes.labelcolor": "#d7e0ea",
        "xtick.color": "#9aa8b8",
        "ytick.color": "#9aa8b8",
        "text.color": "#d7e0ea",
        "grid.color": "#243040",
        "grid.linestyle": "--",
        "axes.grid": True,
    }
)


def _encode_png(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _plot_s11(
    measured: Trace | None,
    theory: Trace | None,
    path: Path,
    config: DesignConfig,
    measured_label: str = "HFSS",
) -> Path:
    f_res = float(config.validation.resonance_ghz or config.antenna.frequency_ghz)
    limit = config.validation.s11_max_db
    fig, ax = plt.subplots(figsize=(8.2, 4.4), dpi=140)
    peak_trace = measured if measured is not None else theory
    if measured is not None:
        ax.plot(measured.x, measured.y, color=HFSS_COLOR, linewidth=2.1, label=measured_label)
    if theory is not None:
        ax.plot(
            theory.x,
            theory.y,
            color=THEORY_COLOR,
            linewidth=1.6,
            linestyle="--",
            label="Balanis / Kraus",
        )
    ax.axvline(f_res, color="#c97b84", linewidth=1.15, linestyle="--", label=f"{f_res:.3f} GHz")
    ax.axhline(limit, color=LIMIT_COLOR, linewidth=1.1, linestyle=":", label=f"{limit:.0f} dB")
    if peak_trace is not None and peak_trace.y.size:
        idx = int(np.argmin(peak_trace.y))
        fx = float(peak_trace.x[idx])
        fy = float(peak_trace.y[idx])
        ax.scatter([fx], [fy], color="#f2d08a", s=42, zorder=5)
        ax.annotate(
            f"{fx:.3f} GHz\n{fy:.1f} dB",
            xy=(fx, fy),
            xytext=(8, -18),
            textcoords="offset points",
            color="#f2d08a",
            fontsize=9,
        )
    ax.set_title(f"S  ·  single resonance at {f_res:.3f} GHz   (S11 < {limit:.0f} dB)")
    ax.set_xlabel("frequency GHz")
    ax.set_ylabel("S11 dB")
    ax.legend(loc="best", framealpha=0.35)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def _plot_trace(trace: Trace, path: Path, title: str, hline: float | None = None) -> Path:
    return _plot_comparison(trace, None, path, title, hline=hline, xlabel=trace.x_label, ylabel=trace.y_label)


def _plot_comparison(
    measured: Trace | None,
    theory: Trace | None,
    path: Path,
    title: str,
    hline: float | None = None,
    xlabel: str = "",
    ylabel: str = "",
    measured_label: str = "HFSS",
    theory_label: str = "Balanis / Kraus",
) -> Path:
    fig, ax = plt.subplots(figsize=(8.2, 4.4), dpi=140)
    if measured is not None:
        ax.plot(measured.x, measured.y, color=HFSS_COLOR, linewidth=2.1, label=measured_label)
        xlabel = xlabel or measured.x_label
        ylabel = ylabel or measured.y_label
    if theory is not None:
        ax.plot(
            theory.x,
            theory.y,
            color=THEORY_COLOR,
            linewidth=1.6,
            linestyle="--",
            label=theory_label,
        )
        xlabel = xlabel or theory.x_label
        ylabel = ylabel or theory.y_label
    if hline is not None:
        ax.axhline(hline, color=LIMIT_COLOR, linewidth=1.1, linestyle=":", label="limit")
    ax.set_title(title)
    ax.set_xlabel(xlabel.replace("_", " "))
    ax.set_ylabel(ylabel.replace("_", " "))
    if measured is not None or theory is not None:
        ax.legend(loc="best", framealpha=0.35)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def _polar_comparison(
    measured: Trace | None,
    theory: Trace | None,
    path: Path,
    title: str,
) -> Path:
    fig, ax = plt.subplots(figsize=(5.8, 5.8), dpi=140, subplot_kw={"projection": "polar"})
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    if measured is not None:
        ax.plot(np.radians(measured.x), measured.y, color=HFSS_COLOR, linewidth=2.1, label="HFSS")
    if theory is not None:
        ax.plot(
            np.radians(theory.x),
            theory.y,
            color=THEORY_COLOR,
            linewidth=1.6,
            linestyle="--",
            label="Balanis / Kraus",
        )
    ax.set_title(title, pad=16)
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), framealpha=0.35)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def _clip_unit(xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = xs**2 + ys**2 <= 1.002
    return np.where(mask, xs, np.nan), np.where(mask, ys, np.nan)


def _smith_circles(ax) -> None:
    theta = np.linspace(0.0, 2.0 * np.pi, 721)
    ax.plot(np.cos(theta), np.sin(theta), color="#8a97a8", linewidth=1.1)
    ax.axhline(0.0, color="#3d4a5c", linewidth=0.8)
    ax.axvline(0.0, color="#3d4a5c", linewidth=0.8)
    for r in (0.2, 0.5, 1.0, 2.0, 5.0):
        cx = r / (1.0 + r)
        radius = 1.0 / (1.0 + r)
        xs, ys = _clip_unit(cx + radius * np.cos(theta), radius * np.sin(theta))
        ax.plot(xs, ys, color="#2b3646", linewidth=0.7)
    for react in (0.2, 0.5, 1.0, 2.0, 5.0, -0.2, -0.5, -1.0, -2.0, -5.0):
        cy = 1.0 / react
        radius = abs(1.0 / react)
        xs, ys = _clip_unit(1.0 + radius * np.cos(theta), cy + radius * np.sin(theta))
        ax.plot(xs, ys, color="#2b3646", linewidth=0.6)
    ax.set_xlim(-1.15, 1.15)
    ax.set_ylim(-1.15, 1.15)
    ax.set_aspect("equal")
    ax.axis("off")


def _plot_smith(
    measured: ComplexTrace | None,
    theory: ComplexTrace | None,
    theory_zin_ohm: float,
    z0: float,
    path: Path,
    f0: float,
) -> Path:
    fig, ax = plt.subplots(figsize=(5.8, 5.8), dpi=140)
    _smith_circles(ax)
    if measured is not None and measured.real.size:
        ax.plot(measured.real, measured.imag, color=HFSS_COLOR, linewidth=2.0, label="HFSS S11")
        idx = int(np.argmin(np.abs(measured.x - f0)))
        ax.scatter([measured.real[idx]], [measured.imag[idx]], color=HFSS_COLOR, s=36, zorder=5)
    if theory is not None and theory.real.size:
        ax.plot(
            theory.real,
            theory.imag,
            color=THEORY_COLOR,
            linewidth=1.4,
            linestyle="--",
            label="Balanis / Kraus",
        )
    if theory_zin_ohm > 0.0 and z0 > 0.0:
        gamma = (theory_zin_ohm - z0) / (theory_zin_ohm + z0)
        ax.scatter([gamma], [0.0], color=THEORY_COLOR, s=48, marker="D", zorder=6, label=f"Zin {theory_zin_ohm:.0f} Ω")
    ax.set_title("Smith chart  S11")
    ax.legend(loc="upper right", bbox_to_anchor=(1.32, 1.08), framealpha=0.35)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def write_plots(
    results: ExtractedResults,
    plot_dir: Path,
    config: DesignConfig,
    theory: ExtractedResults | None = None,
) -> dict[str, Path]:
    if theory is None and results.source == "hfss":
        theory = theoretical_placeholder(config)
    if theory is None:
        theory = ExtractedResults(frequency_ghz=config.antenna.frequency_ghz, source="theoretical")

    if results.source in {"theoretical", "setup_applied"}:
        measured_label = "Balanis / Kraus"
    elif results.source == "hfss":
        measured_label = "HFSS"
    else:
        measured_label = results.source.replace("_", " ")
    plots: dict[str, Path] = {}
    plots["s11"] = _plot_s11(
        results.s11,
        theory.s11 if results.source == "hfss" else None,
        plot_dir / "s11.png",
        config,
        measured_label=measured_label,
    )
    gain_meas = results.gain_freq or results.gain_theta
    plots["gain"] = _plot_comparison(
        gain_meas,
        theory.gain_freq if results.gain_freq is not None else theory.gain_theta,
        plot_dir / "gain.png",
        "Gain  ·  boresight vs frequency" if results.gain_freq is not None else "Gain  ·  vs theta",
        hline=config.validation.gain_min_dbi,
        measured_label=measured_label,
    )
    plots["vswr"] = _plot_comparison(
        results.vswr,
        theory.vswr,
        plot_dir / "vswr.png",
        "VSWR",
        hline=config.validation.vswr_max,
        measured_label=measured_label,
    )
    plots["axial_ratio"] = _plot_comparison(
        results.axial_ratio_theta,
        theory.axial_ratio_theta,
        plot_dir / "axial_ratio.png",
        "AR  ·  axial ratio vs theta  (E-plane)",
        hline=config.validation.axial_ratio_max_db,
        measured_label=measured_label,
    )
    plots["smith"] = _plot_smith(
        results.smith,
        theory.smith if results.source != "theoretical" else None,
        config.antenna.theoretical_zin_ohm,
        config.feed.port_impedance_ohm,
        plot_dir / "smith.png",
        config.antenna.frequency_ghz,
    )
    plots["e_plane"] = _polar_comparison(
        results.gain_eplane or results.gain_theta,
        theory.gain_eplane,
        plot_dir / "e_plane.png",
        "E-plane  ·  Gain(θ), φ = 0°",
    )
    plots["h_plane"] = _polar_comparison(
        results.gain_hplane,
        theory.gain_hplane,
        plot_dir / "h_plane.png",
        "H-plane  ·  Gain(θ), φ = 90°",
    )
    if results.directivity_theta is not None:
        plots["directivity"] = _plot_comparison(
            results.directivity_theta,
            theory.directivity_theta,
            plot_dir / "directivity.png",
            "Directivity vs theta  (φ = 0°)",
            measured_label=measured_label,
        )
    return plots


def write_html(
    config: DesignConfig,
    results: ExtractedResults,
    report: ValidationReport,
    output_dir: Path,
    plots: dict[str, Path],
    run_meta: dict,
) -> Path:
    encoded = {name: _encode_png(path) for name, path in plots.items()}
    summary = synthesis_summary(config)
    badge_class = "pass" if report.passed else "fail"
    criteria_html = "".join(
        (
            "<tr>"
            f"<td>{item.name}</td>"
            f"<td>{item.measured:.3f}</td>"
            f"<td>{item.limit:.3f} {item.unit}</td>"
            f"<td class={'ok' if item.passed else 'bad'}>{'PASS' if item.passed else 'FAIL'}</td>"
            f"<td>{item.detail}</td>"
            "</tr>"
        )
        for item in report.criteria
    )
    param_rows = "".join(
        f"<tr><td>{key}</td><td>{value}</td></tr>" for key, value in summary.items()
    )
    captions = {
        "s11": "S · single resonance at 3.035 GHz, S11 < −20 dB",
        "gain": "Gain · boresight  (HFSS vs Balanis/Kraus)",
        "vswr": "VSWR  (HFSS vs Balanis/Kraus)",
        "axial_ratio": "AR · axial ratio vs theta",
        "smith": "Smith chart · S11",
        "e_plane": "E-plane · Gain(θ), φ = 0°",
        "h_plane": "H-plane · Gain(θ), φ = 90°",
        "directivity": "Directivity vs theta",
    }
    plot_blocks = "".join(
        (
            f'<figure><img src="data:image/png;base64,{encoded[name]}" alt="{name}">'
            f"<figcaption>{captions.get(name, name.replace('_', ' '))}</figcaption></figure>"
        )
        for name in ("s11", "gain", "vswr", "axial_ratio", "smith", "e_plane", "h_plane", "directivity")
        if name in encoded
    )
    notes = "".join(f"<li>{note}</li>" for note in results.notes)
    f0 = float(config.validation.resonance_ghz or config.antenna.frequency_ghz)
    theory_s = theoretical_placeholder(config).scalars if results.source == "hfss" else {}
    resonance_row = next((item for item in report.criteria if item.name == "Resonance frequency"), None)
    resonance_hz = resonance_row.measured if resonance_row is not None else results.scalars.get("s11_min_freq_ghz")
    dir_val = results.scalars.get("directivity_boresight_dbi")
    if not isinstance(dir_val, float) or dir_val != dir_val:
        dir_val = results.scalars.get("gain_boresight_dbi")
    compare_pairs = (
        ("S11 at f0 (dB)", results.scalars.get("s11_at_f0_db"), theory_s.get("s11_at_f0_db"), config.validation.s11_max_db, "<="),
        ("Resonance (GHz)", resonance_hz, f0, f0, "~="),
        ("S11 peak (dB)", results.scalars.get("s11_min_db"), theory_s.get("s11_min_db"), config.validation.s11_max_db, "<="),
        ("VSWR at f0", results.scalars.get("vswr_at_f0"), theory_s.get("vswr_at_f0"), config.validation.vswr_max, "<="),
        ("Gain (dBi)", results.scalars.get("gain_boresight_dbi"), config.antenna.theoretical_gain_dbi, config.validation.gain_min_dbi, ">="),
        ("Directivity (dBi)", dir_val, config.antenna.theoretical_directivity_dbi, config.validation.gain_min_dbi, ">="),
        ("Axial ratio (dB)", results.scalars.get("axial_ratio_boresight_db"), config.antenna.theoretical_axial_ratio_db, config.validation.axial_ratio_max_db, "<="),
    )
    compare_html = ""
    for name, hfss, theory, limit, how in compare_pairs:
        hfss_s = f"{hfss:.3f}" if isinstance(hfss, float) and hfss == hfss else "—"
        theory_s_txt = f"{theory:.3f}" if isinstance(theory, float) and theory == theory else "—"
        ok = False
        if isinstance(hfss, float) and hfss == hfss:
            if how == "<=":
                ok = hfss <= limit
            elif how == ">=":
                ok = hfss >= limit
            else:
                ok = abs(hfss - limit) <= config.validation.resonance_tol_ghz
        compare_html += (
            f"<tr><td>{name}</td><td>{hfss_s}</td><td>{theory_s_txt}</td>"
            f"<td class={'ok' if ok else 'bad'}>{'PASS' if ok else 'FAIL'}</td></tr>"
        )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Helical Antenna — HFSS Dashboard</title>
  <style>
    :root {{
      --bg: #0c1016; --card: #161c26; --line: #2b3646;
      --text: #e7eef6; --muted: #93a0b0; --amber: #e8b86d;
      --pass: #7ec8a3; --fail: #e07a7a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      background: var(--bg); color: var(--text);
    }}
    header {{
      padding: 28px 36px 20px; border-bottom: 1px solid var(--line);
      display: flex; justify-content: space-between; align-items: flex-end;
    }}
    h1 {{ margin: 0 0 6px; font-size: 28px; letter-spacing: 0.02em; }}
    .sub {{ color: var(--muted); font-size: 14px; }}
    .badge {{
      padding: 10px 18px; border-radius: 999px; font-weight: 700;
      letter-spacing: 0.08em;
    }}
    .badge.pass {{ background: #173328; color: var(--pass); }}
    .badge.fail {{ background: #3a1b1b; color: var(--fail); }}
    main {{ padding: 28px 36px 48px; }}
    .grid {{ display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 20px; }}
    section {{
      background: var(--card); border: 1px solid var(--line);
      border-radius: 12px; padding: 18px 20px 20px;
    }}
    h2 {{ margin: 0 0 12px; font-size: 16px; color: var(--amber); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 7px 8px; border-bottom: 1px solid var(--line); text-align: left; }}
    td.ok {{ color: var(--pass); font-weight: 700; }}
    td.bad {{ color: var(--fail); font-weight: 700; }}
    .plots {{
      margin-top: 20px; display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px;
    }}
    figure {{ margin: 0; background: var(--card); border: 1px solid var(--line);
      border-radius: 12px; padding: 10px; }}
    img {{ width: 100%; border-radius: 8px; }}
    figcaption {{ color: var(--muted); font-size: 12px; padding: 6px 4px 2px; }}
    code {{ color: var(--amber); }}
    ul {{ color: var(--muted); }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Helical Antenna Dashboard</h1>
      <div class="sub">
        {config.project.name} / {config.project.design} ·
        f<sub>0</sub> = {config.antenna.frequency_ghz} GHz ·
        source = {results.source} ·
        {run_meta.get("elapsed_s", "—")} s
      </div>
    </div>
    <div class="badge {badge_class}">{report.overall}</div>
  </header>
  <main>
    <div class="grid">
      <section>
        <h2>Acceptance</h2>
        <table>
          <thead><tr><th>Metric</th><th>Measured</th><th>Limit</th><th>Result</th><th>Detail</th></tr></thead>
          <tbody>{criteria_html}</tbody>
        </table>
      </section>
      <section>
        <h2>Balanis / Kraus synthesis</h2>
        <table>
          <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
          <tbody>{param_rows}</tbody>
        </table>
      </section>
    </div>
    <section style="margin-top:0; margin-bottom:16px">
      <h2>Results comparison</h2>
      <p class="sub">
        Amber = HFSS FEM. Blue dashed = Balanis / Kraus closed-form.
        Graphs: S, Gain, VSWR, AR, Smith chart, E-plane, H-plane, Directivity.
      </p>
      <table>
        <thead><tr><th>Quantity</th><th>HFSS</th><th>Theory</th><th>vs spec</th></tr></thead>
        <tbody>{compare_html}</tbody>
      </table>
    </section>
    <div class="plots">{plot_blocks}</div>
    <section style="margin-top:20px">
      <h2>Architecture</h2>
      <p class="sub">
        Python / PyAEDT is the automation layer.
        Ansys Electronics Desktop hosts the HFSS design.
        HFSS performs the FEM electromagnetic solve.
        Python extracts S, Gain, VSWR, AR, Smith chart, E-plane and H-plane for comparison.
      </p>
      <ul>{notes}<li>Project: <code>{config.project.name}</code></li>
      <li>Design: <code>{config.project.design}</code></li></ul>
    </section>
  </main>
</body>
</html>
"""
    path = output_dir / "dashboard.html"
    path.write_text(html, encoding="utf-8")
    (output_dir / "run_meta.json").write_text(
        json.dumps(
            {
                "overall": report.overall,
                "source": results.source,
                "scalars": results.scalars,
                "synthesis": summary,
                "meta": run_meta,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
