from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Python"))

from antenna_params import load_config
from geometry_generator import plate_side_mm
from synthesis import l_section_from_zin, synthesize, synthesis_summary


def test_3ghz_axial_dimensions():
    config = synthesize(load_config(ROOT / "config" / "default_helix.yaml"))
    ant = config.antenna
    assert abs(ant.frequency_ghz - 3.035) < 1e-9
    assert abs(ant.wavelength_mm - 98.778) < 0.05
    assert ant.turns == 3.0
    assert ant.helix_diameter_mm is not None
    assert abs(ant.helix_diameter_mm - 41.88) < 0.05
    assert abs((ant.pitch_mm or 0.0) - 37.20) < 0.05
    assert 110.0 < ant.axial_length_mm < 113.0
    assert 180.0 < ant.theoretical_zin_ohm < 190.0
    assert ant.theoretical_gain_dbi > 10.0
    assert ant.theoretical_axial_ratio_db < 1.5
    assert config.feed.enable_impedance_match is True
    assert abs(config.feed.match_l_h * 1e9 - 5.11) < 0.05
    assert abs(config.feed.match_c_f * 1e12 - 0.80) < 0.03
    assert config.feed.pin_height_mm >= 8.0


def test_l_section_from_real_zin():
    inductance_h, capacitance_f, topology = l_section_from_zin(
        complex(140.0, 0.0), 50.0, 3.035e9
    )
    assert topology == "load"
    assert 3.3 < inductance_h * 1e9 < 3.8
    assert 0.45 < capacitance_f * 1e12 < 0.55


def test_l_section_from_complex_zin():
    inductance_h, capacitance_f, topology = l_section_from_zin(
        complex(72.2, -53.9), 50.0, 3.035e9
    )
    assert topology == "load"
    assert 2.6 < inductance_h * 1e9 < 3.3
    assert 0.12 < capacitance_f * 1e12 < 0.25


def test_physical_plate_side_for_known_match_c():
    side = plate_side_mm(0.207e-12)
    assert 3.0 < side < 6.5


def test_l_section_port_topology_when_r_below_z0():
    inductance_h, capacitance_f, topology = l_section_from_zin(
        complex(40.3, -50.4), 50.0, 3.035e9
    )
    assert topology == "port"
    assert 3.2 < inductance_h * 1e9 < 4.2
    assert 0.40 < capacitance_f * 1e12 < 0.65


def test_summary_keys():
    config = synthesize(load_config(ROOT / "config" / "default_helix.yaml"))
    summary = synthesis_summary(config)
    assert summary["frequency_ghz"] == 3.035
    assert summary["resonance_ghz"] == 3.035
    assert "theoretical_gain_dbi" in summary
