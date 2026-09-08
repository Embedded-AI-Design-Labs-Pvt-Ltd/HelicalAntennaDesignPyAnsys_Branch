"""Standard Results reports used for HFSS vs Balanis/Kraus comparison.

Report names match the HFSS Results folder:
S11, Gain, VSWR, AR, Smith chart, E-plane, H-plane.
"""

from __future__ import annotations

from typing import Any

from antenna_params import DesignConfig


COMPARISON_PLOT_ORDER = (
    "S11_Return_Loss",
    "VSWR",
    "Smith_S11",
    "Gain_Boresight",
    "AR_vs_Theta",
    "E_Plane",
    "H_Plane",
    "Directivity_Theta",
)


def _theta_samples(config: DesignConfig) -> list[str]:
    start = int(round(config.boundary.theta_start))
    stop = int(round(config.boundary.theta_stop))
    step = int(round(config.boundary.theta_step)) or 5
    return [f"{angle}deg" for angle in range(start, stop + 1, step)]


def solution_context(config: DesignConfig) -> tuple[str, str, str, str]:
    setup = f"{config.solver.setup_name} : {config.solver.sweep_name}"
    if "terminal" in config.project.solution_type.lower():
        return setup, "Terminal Solution Data", "dB(St(Port1_T1,Port1_T1))", "VSWR(Port1_T1)"
    return setup, "Modal Solution Data", "dB(S(1,1))", "VSWR(1)"


def comparison_report_jobs(config: DesignConfig, setup_sweep: str | None = None) -> list[dict[str, Any]]:
    """HFSS report definitions for the seven comparison graphs."""
    setup, category, s11, vswr = solution_context(config)
    if setup_sweep:
        setup = setup_sweep
    adaptive = f"{config.solver.setup_name} : LastAdaptive"
    sphere = config.boundary.infinite_sphere
    theta = _theta_samples(config)
    # LastAdaptive has one frequency — "All" matches it. A literal 3.035GHz
    # token often misses the stored variation and yields an empty far-field plot.
    e_plane = {"Freq": ["All"], "Phi": ["0deg"], "Theta": theta}
    h_plane = {"Freq": ["All"], "Phi": ["90deg"], "Theta": theta}
    gain_freq = {"Freq": ["All"], "Theta": ["0deg"], "Phi": ["0deg"]}
    return [
        {
            "name": "S11_Return_Loss",
            "expressions": s11,
            "plot_type": "Rectangular Plot",
            "report_category": category,
            "setup": setup,
            "native_y": [s11],
        },
        {
            "name": "VSWR",
            "expressions": vswr,
            "plot_type": "Rectangular Plot",
            "report_category": category,
            "setup": setup,
            "native_y": [vswr],
        },
        {
            "name": "Smith_S11",
            "expressions": "S(1,1)",
            "plot_type": "Smith Chart",
            "report_category": category,
            "setup": setup,
            "native_y": ["S(1,1)"],
        },
        {
            "name": "Gain_Boresight",
            "expressions": "dB(GainTotal)",
            "plot_type": "Rectangular Plot",
            "report_category": "Far Fields",
            "setup": adaptive,
            "context": sphere,
            "primary": "Freq",
            "variations": gain_freq,
        },
        {
            "name": "AR_vs_Theta",
            "expressions": "AR_dB",
            "plot_type": "Rectangular Plot",
            "report_category": "Far Fields",
            "setup": adaptive,
            "context": sphere,
            "primary": "Theta",
            "variations": e_plane,
            "native_y": ["AR_dB"],
            "alt_expressions": [
                "dB(GainRHCP)-dB(GainLHCP)",
                "GainRHCP",
            ],
        },
        {
            "name": "E_Plane",
            "expressions": "dB(GainTotal)",
            "plot_type": "Rectangular Plot",
            "report_category": "Far Fields",
            "setup": adaptive,
            "context": sphere,
            "primary": "Theta",
            "variations": e_plane,
            "native_y": ["dB(GainTotal)"],
        },
        {
            "name": "H_Plane",
            "expressions": "dB(GainTotal)",
            "plot_type": "Rectangular Plot",
            "report_category": "Far Fields",
            "setup": adaptive,
            "context": sphere,
            "primary": "Theta",
            "variations": h_plane,
            "native_y": ["dB(GainTotal)"],
        },
        {
            "name": "Directivity_Theta",
            "expressions": "dB(DirTotal)",
            "plot_type": "Rectangular Plot",
            "report_category": "Far Fields",
            "setup": adaptive,
            "context": sphere,
            "primary": "Theta",
            "variations": e_plane,
            "native_y": ["dB(DirTotal)"],
            "alt_expressions": ["dB(GainTotal)"],
        },
    ]
