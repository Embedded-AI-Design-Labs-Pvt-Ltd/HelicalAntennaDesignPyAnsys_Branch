from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Python"))

from ansys_plot_display import AnsysPlotDisplay, os_name_is_windows
from antenna_params import load_config
from comparison_reports import COMPARISON_PLOT_ORDER, _theta_samples, comparison_report_jobs
from result_extractor import _read_hfss_csv


def test_plot_display_class_loads():
    config = load_config(ROOT / "config" / "default_helix.yaml")
    display = AnsysPlotDisplay(hfss=None, config=config)
    setup, category, s11 = display._solution_context()
    assert "Setup1" in setup
    assert "S(1,1)" in s11
    assert category == "Modal Solution Data"
    assert isinstance(os_name_is_windows(), bool)


def test_comparison_report_set():
    config = load_config(ROOT / "config" / "default_helix.yaml")
    names = [job["name"] for job in comparison_report_jobs(config)]
    assert names == list(COMPARISON_PLOT_ORDER)
    assert "Smith_S11" in names
    assert "E_Plane" in names
    assert "H_Plane" in names
    assert len(_theta_samples(config)) == 37
    assert _theta_samples(config)[0] == "0deg"
    assert _theta_samples(config)[-1] == "180deg"


def test_wide_farfield_csv(tmp_path):
    path = tmp_path / "eplane.csv"
    path.write_text(
        "Freq [GHz],dB(GainTotal) [0deg],dB(GainTotal) [5deg],dB(GainTotal) [10deg]\n"
        "3.035,12.8,12.5,11.9\n",
        encoding="utf-8",
    )
    rows = _read_hfss_csv(path, prefer="theta")
    assert rows == [(0.0, 12.8), (5.0, 12.5), (10.0, 11.9)]
