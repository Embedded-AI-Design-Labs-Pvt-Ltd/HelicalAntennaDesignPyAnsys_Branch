from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Python"))

from antenna_params import load_config
from report_generator import write_html, write_plots
from result_extractor import theoretical_placeholder
from synthesis import synthesize
from validation import evaluate


def test_comparison_plots_written(tmp_path):
    config = synthesize(load_config(ROOT / "config" / "default_helix.yaml"))
    results = theoretical_placeholder(config)
    plots = write_plots(results, tmp_path / "plots", config)
    required = ("s11", "gain", "vswr", "axial_ratio", "smith", "e_plane", "h_plane")
    for name in required:
        assert name in plots
        assert plots[name].is_file()
        assert plots[name].stat().st_size > 0


def test_comparison_dashboard(tmp_path):
    config = synthesize(load_config(ROOT / "config" / "default_helix.yaml"))
    results = theoretical_placeholder(config)
    plots = write_plots(results, tmp_path / "plots", config)
    report = evaluate(config, results)
    dashboard = write_html(config, results, report, tmp_path, plots, {"mode": "test"})
    html = dashboard.read_text(encoding="utf-8")
    assert "Results comparison" in html
    assert "Smith chart" in html
    assert "E-plane" in html
    assert "H-plane" in html
