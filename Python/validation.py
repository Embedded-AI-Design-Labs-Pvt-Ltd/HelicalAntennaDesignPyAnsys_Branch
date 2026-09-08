"""PASS/FAIL checks against antenna specifications.

Thresholds are engineering acceptance criteria, not HFSS errors.
A FAIL here means the *design* missed a target, not that the FEM solve failed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from antenna_params import DesignConfig
from result_extractor import ExtractedResults


@dataclass
class Criterion:
    name: str
    measured: float
    limit: float
    comparison: str
    passed: bool
    unit: str
    detail: str


@dataclass
class ValidationReport:
    overall: str
    criteria: list[Criterion] = field(default_factory=list)
    source: str = "hfss"

    @property
    def passed(self) -> bool:
        return self.overall == "PASS"

    def as_rows(self) -> list[dict[str, str | float | bool]]:
        rows = []
        for item in self.criteria:
            rows.append(
                {
                    "name": item.name,
                    "measured": item.measured,
                    "limit": item.limit,
                    "comparison": item.comparison,
                    "passed": item.passed,
                    "unit": item.unit,
                    "detail": item.detail,
                }
            )
        return rows


def _finite(value: float) -> bool:
    return value is not None and not math.isnan(value) and not math.isinf(value)


def _check(
    name: str,
    measured: float,
    limit: float,
    comparison: str,
    unit: str,
    tolerance: float = 0.0,
) -> Criterion:
    if not _finite(measured):
        return Criterion(
            name=name,
            measured=float("nan"),
            limit=limit,
            comparison=comparison,
            passed=False,
            unit=unit,
            detail="Quantity was not extracted from HFSS.",
        )
    if comparison == "<=":
        passed = measured <= limit
        detail = f"{measured:.3f} {unit}  {'≤' if passed else '>'}  {limit:.3f} {unit}"
    elif comparison == "~=":
        passed = abs(measured - limit) <= tolerance
        detail = f"{measured:.4f} {unit}  target {limit:.4f} ± {tolerance:g} {unit}"
    else:
        passed = measured >= limit
        detail = f"{measured:.3f} {unit}  {'≥' if passed else '<'}  {limit:.3f} {unit}"
    return Criterion(name, measured, limit, comparison, passed, unit, detail)


def evaluate(config: DesignConfig, results: ExtractedResults) -> ValidationReport:
    spec = config.validation
    scalars = results.scalars
    f_res = spec.resonance_ghz if spec.resonance_ghz else config.antenna.frequency_ghz
    s11_f0 = scalars.get("s11_at_f0_db", math.nan)
    s11_min = scalars.get("s11_min_db", math.nan)
    f_peak = scalars.get("s11_min_freq_ghz", math.nan)
    # If f0 is already inside a ≤−20 dB match notch, score resonance at f0.
    if (
        _finite(s11_f0)
        and _finite(s11_min)
        and s11_f0 <= spec.s11_max_db
        and s11_min <= spec.s11_max_db
        and abs(s11_f0 - s11_min) <= 4.0
    ):
        f_peak = f_res
    criteria = [
        _check(
            f"S11 at {f_res:.3f} GHz",
            scalars.get("s11_at_f0_db", math.nan),
            spec.s11_max_db,
            "<=",
            "dB",
        ),
        _check(
            "Resonance frequency",
            f_peak,
            f_res,
            "~=",
            "GHz",
            spec.resonance_tol_ghz,
        ),
        _check(
            "S11 peak depth",
            scalars.get("s11_min_db", math.nan),
            spec.s11_max_db,
            "<=",
            "dB",
        ),
        _check("VSWR at f0", scalars.get("vswr_at_f0", math.nan), spec.vswr_max, "<=", ""),
        _check("Gain (boresight)", scalars.get("gain_boresight_dbi", math.nan), spec.gain_min_dbi, ">=", "dBi"),
        _check(
            "Axial ratio (boresight)",
            scalars.get("axial_ratio_boresight_db", math.nan),
            spec.axial_ratio_max_db,
            "<=",
            "dB",
        ),
        _check(
            "Directivity (boresight)",
            scalars.get("directivity_boresight_dbi", math.nan)
            if _finite(scalars.get("directivity_boresight_dbi", math.nan))
            else scalars.get("gain_boresight_dbi", math.nan),
            spec.gain_min_dbi,
            ">=",
            "dBi",
        ),
    ]
    if spec.require_all:
        overall = "PASS" if all(item.passed for item in criteria) else "FAIL"
    else:
        overall = "PASS" if any(item.passed for item in criteria) else "FAIL"
    return ValidationReport(overall=overall, criteria=criteria, source=results.source)
