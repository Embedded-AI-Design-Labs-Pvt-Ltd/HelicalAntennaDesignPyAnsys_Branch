"""Design-parameter contracts for the helical antenna workflow.

All geometry is expressed in millimetres. Frequency is in GHz.
Closed-form fields are filled by ``synthesis.synthesize``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

C0_MM_PER_S = 299_792_458_000.0  # speed of light in mm/s


def _deep_update(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class AntennaSpec:
    frequency_ghz: float = 3.035
    mode: str = "axial"
    polarization: str = "rhcp"
    turns: float = 6.0
    circumference_over_lambda: float = 1.0
    pitch_angle_deg: float = 13.0
    wire_diameter_over_lambda: float = 0.02
    ground_size_over_lambda: float = 0.85
    helix_diameter_mm: float | None = None
    pitch_mm: float | None = None
    wire_diameter_mm: float | None = None
    ground_size_mm: float | None = None
    conductor_material: str = "copper"
    ground_material: str = "pec"

    wavelength_mm: float = 0.0
    helix_radius_mm: float = 0.0
    axial_length_mm: float = 0.0
    circumference_mm: float = 0.0
    theoretical_zin_ohm: float = 0.0
    theoretical_gain_dbi: float = 0.0
    theoretical_directivity_dbi: float = 0.0
    theoretical_axial_ratio_db: float = 0.0
    theoretical_hpbw_deg: float = 0.0

    @property
    def right_handed(self) -> bool:
        return self.polarization.lower() == "rhcp"

    @property
    def frequency_hz(self) -> float:
        return self.frequency_ghz * 1e9


@dataclass
class FeedSpec:
    type: str = "coax_wave_port"
    port_name: str = "Port1"
    port_impedance_ohm: float = 50.0
    enable_impedance_match: bool = False
    match_l_h: float = 0.0
    match_c_f: float = 0.0
    match_l_nh: float | None = None
    match_c_pf: float | None = None
    pin_height_over_lambda: float = 0.05
    feeder_length_over_lambda: float = 0.15
    coax_inner_over_lambda: float = 0.006
    coax_outer_over_lambda: float = 0.02
    dielectric_material: str = "Teflon (tm)"
    pin_height_mm: float = 0.0
    feeder_length_mm: float = 0.0
    coax_inner_radius_mm: float = 0.0
    coax_outer_radius_mm: float = 0.0


@dataclass
class BoundarySpec:
    type: str = "Radiation"
    padding_over_lambda: float = 0.25
    extra_axial_padding_over_lambda: float = 0.15
    infinite_sphere: str = "InfiniteSphere1"
    theta_start: float = 0.0
    theta_stop: float = 180.0
    theta_step: float = 5.0
    phi_start: float = -180.0
    phi_stop: float = 180.0
    phi_step: float = 5.0
    padding_mm: float = 0.0
    extra_axial_padding_mm: float = 0.0


@dataclass
class MeshSpec:
    slider_level: int = 1
    helix_max_length_over_lambda: float = 0.04
    enable_length_mesh: bool = True
    helix_max_length_mm: float = 0.0


@dataclass
class SolverSpec:
    setup_name: str = "Setup1"
    sweep_name: str = "Sweep1"
    adaptive_frequency_ghz: float | None = None
    maximum_passes: int = 10
    minimum_passes: int = 2
    minimum_converged_passes: int = 2
    max_delta_s: float = 0.02
    sweep_type: str = "Interpolating"
    sweep_start_scale: float = 0.75
    sweep_stop_scale: float = 1.30
    sweep_points: int = 101
    save_fields: bool = True
    save_rad_fields: bool = True
    cores: int = 2
    analyze_all: bool = False
    generate_mesh: bool = True

    @property
    def adaptive_ghz(self) -> float:
        return float(self.adaptive_frequency_ghz)


@dataclass
class SessionSpec:
    non_graphical: bool = False
    new_desktop: bool = False
    close_on_exit: bool = False
    specified_version: str | None = None
    use_udp_helix: bool = True
    auto_open_dashboard: bool = True
    rebuild_design: bool = True
    admin_mode: bool = False
    show_plots_in_ansys: bool = True
    student_version: bool = True


@dataclass
class ValidationSpec:
    s11_max_db: float = -20.0
    resonance_ghz: float | None = 3.035
    resonance_tol_ghz: float = 0.005
    vswr_max: float = 2.0
    gain_min_dbi: float = 8.0
    axial_ratio_max_db: float = 3.0
    require_all: bool = True

    @property
    def resonance_target_ghz(self) -> float:
        return float(self.resonance_ghz) if self.resonance_ghz else 3.035


@dataclass
class ProjectSpec:
    name: str = "Helical_Antenna"
    design: str = "Helical_3GHz"
    model_units: str = "mm"
    solution_type: str = "DrivenModal"
    work_dir: str = "work"
    results_dir: str = "results"


@dataclass
class DesignConfig:
    """Full run configuration loaded from YAML."""

    project: ProjectSpec = field(default_factory=ProjectSpec)
    antenna: AntennaSpec = field(default_factory=AntennaSpec)
    feed: FeedSpec = field(default_factory=FeedSpec)
    boundary: BoundarySpec = field(default_factory=BoundarySpec)
    mesh: MeshSpec = field(default_factory=MeshSpec)
    solver: SolverSpec = field(default_factory=SolverSpec)
    session: SessionSpec = field(default_factory=SessionSpec)
    validation: ValidationSpec = field(default_factory=ValidationSpec)
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "project": asdict(self.project),
            "antenna": asdict(self.antenna),
            "feed": asdict(self.feed),
            "boundary": asdict(self.boundary),
            "mesh": asdict(self.mesh),
            "solver": asdict(self.solver),
            "session": asdict(self.session),
            "validation": asdict(self.validation),
        }
        return payload


def _from_section(cls, data: dict | None):
    if not data:
        return cls()
    allowed = {item.name for item in fields(cls)}
    return cls(**{key: value for key, value in data.items() if key in allowed})


def load_config(path: str | Path) -> DesignConfig:
    cfg_path = Path(path)
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    config = DesignConfig(
        project=_from_section(ProjectSpec, raw.get("project")),
        antenna=_from_section(AntennaSpec, raw.get("antenna")),
        feed=_from_section(FeedSpec, raw.get("feed")),
        boundary=_from_section(BoundarySpec, raw.get("boundary")),
        mesh=_from_section(MeshSpec, raw.get("mesh")),
        solver=_from_section(SolverSpec, raw.get("solver")),
        session=_from_section(SessionSpec, raw.get("session")),
        validation=_from_section(ValidationSpec, raw.get("validation")),
        source_path=str(cfg_path.resolve()),
    )
    if config.solver.adaptive_frequency_ghz is None:
        config.solver.adaptive_frequency_ghz = config.antenna.frequency_ghz
    if config.feed.match_l_nh is not None:
        config.feed.match_l_h = float(config.feed.match_l_nh) * 1e-9
    if config.feed.match_c_pf is not None:
        config.feed.match_c_f = float(config.feed.match_c_pf) * 1e-12
    return config


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "default_helix.yaml"
