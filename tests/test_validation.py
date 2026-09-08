from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Python"))

from antenna_params import load_config
from result_extractor import theoretical_placeholder
from synthesis import synthesize
from validation import evaluate


def test_theoretical_placeholder_has_traces():
    config = synthesize(load_config(ROOT / "config" / "default_helix.yaml"))
    results = theoretical_placeholder(config)
    assert results.s11 is not None
    assert results.vswr is not None
    assert results.gain_theta is not None
    assert results.gain_freq is not None
    assert results.gain_eplane is not None
    assert results.gain_hplane is not None
    assert results.axial_ratio_theta is not None
    assert results.smith is not None
    assert results.source == "theoretical"


def test_validation_runs():
    config = synthesize(load_config(ROOT / "config" / "default_helix.yaml"))
    results = theoretical_placeholder(config)
    report = evaluate(config, results)
    assert report.overall in {"PASS", "FAIL"}
    assert len(report.criteria) == 7
    assert abs(results.scalars["s11_min_freq_ghz"] - 3.035) < 1e-9
    assert results.scalars["s11_min_db"] < -20.0
    assert results.scalars["s11_at_f0_db"] < -20.0


def test_notch_at_f0_scores_resonance_pass():
    config = synthesize(load_config(ROOT / "config" / "default_helix.yaml"))
    results = theoretical_placeholder(config)
    results.scalars.update(
        {
            "s11_at_f0_db": -23.1,
            "s11_min_db": -26.3,
            "s11_min_freq_ghz": 2.962,
            "vswr_at_f0": 1.15,
            "gain_boresight_dbi": 12.17,
            "directivity_boresight_dbi": 12.13,
            "axial_ratio_boresight_db": 0.89,
        }
    )
    report = evaluate(config, results)
    resonance = next(item for item in report.criteria if item.name == "Resonance frequency")
    s11 = next(item for item in report.criteria if item.name.startswith("S11 at"))
    assert s11.passed
    assert resonance.passed
    assert abs(resonance.measured - 3.035) < 1e-9
    assert report.overall == "PASS"


def test_automation_flags_default_on():
    config = load_config(ROOT / "config" / "default_helix.yaml")
    assert config.solver.analyze_all is False
    assert config.solver.generate_mesh is True
    assert config.session.rebuild_design is True
    assert config.session.student_version is True
    assert config.session.show_plots_in_ansys is True
