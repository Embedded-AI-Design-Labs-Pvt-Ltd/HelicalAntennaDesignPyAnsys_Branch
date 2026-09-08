"""Closed-form helical-antenna synthesis (Balanis / Kraus).

These equations size the geometry *before* HFSS runs. HFSS then computes the
true electromagnetic fields with FEM. Synthesis is not a substitute for the
solver — it is the starting design.
"""

from __future__ import annotations

import math

from antenna_params import C0_MM_PER_S, DesignConfig

# Axial-mode helix: Kraus / Balanis (Antenna Theory, Ch. 10)
#   C/λ ≈ 0.8 … 1.2     (typically 1.0)
#   α   ≈ 12° … 14°
#   N   ≥ 3
#   Zin ≈ 140 · (C/λ) Ω
#   D0  ≈ 15 N C² S / λ³
#   AR  ≈ (2N + 1) / 2N
#   HPBW ≈ 52 λ^{3/2} / (C √(N S))  degrees


def l_section_match(zl_ohm: float, z0_ohm: float, freq_hz: float) -> tuple[float, float]:
    """Series L + shunt C for a real load. Topology is chosen automatically."""
    inductance_h, capacitance_f, _topology = l_section_from_zin(
        complex(zl_ohm, 0.0), z0_ohm, freq_hz
    )
    return inductance_h, capacitance_f


def l_section_from_zin(zin: complex, z0_ohm: float, freq_hz: float) -> tuple[float, float, str]:
    """Exact L-section for FEM Zin = R + jX.

    Returns (L, C, topology):
    - ``load``: series L from the port, shunt C across the helix
    - ``port``: shunt C at the port node, series L toward the helix
    """
    resistance = float(zin.real)
    reactance = float(zin.imag)
    if resistance <= 0.0 or freq_hz <= 0.0:
        return 0.0, 0.0, "none"
    omega = 2.0 * math.pi * freq_hz
    magnitude_sq = resistance * resistance + reactance * reactance
    conductance = resistance / magnitude_sq
    susceptance = -reactance / magnitude_sq

    if conductance < 1.0 / z0_ohm:
        series_x = math.sqrt(z0_ohm * (1.0 / conductance - z0_ohm))
        shunt_b = series_x / (z0_ohm * z0_ohm + series_x * series_x) - susceptance
        if shunt_b > 0.0:
            return series_x / omega, shunt_b / omega, "load"

    if resistance < z0_ohm:
        q = math.sqrt(z0_ohm / resistance - 1.0)
        capacitance_f = q / (omega * z0_ohm)
        inductance_h = (resistance * q - reactance) / omega
        if inductance_h > 0.0 and capacitance_f > 0.0:
            return inductance_h, capacitance_f, "port"

    return 0.0, 0.0, "none"


def zin_from_s11(s11: complex, z0_ohm: float) -> complex:
    denom = 1.0 - s11
    if abs(denom) < 1e-9:
        return complex(z0_ohm, 0.0)
    return z0_ohm * (1.0 + s11) / denom


def lin_to_db(value: float) -> float:
    if value <= 0.0:
        return -999.0
    return 10.0 * math.log10(value)


def synthesize(config: DesignConfig) -> DesignConfig:
    """Fill derived millimetre dimensions and theoretical estimates."""
    ant = config.antenna
    feed = config.feed
    boundary = config.boundary
    mesh = config.mesh

    wavelength = C0_MM_PER_S / ant.frequency_hz
    ant.wavelength_mm = wavelength

    if ant.mode.lower() != "axial":
        raise ValueError(
            f"Unsupported mode '{ant.mode}'. This project implements axial-mode synthesis."
        )

    if ant.helix_diameter_mm is None:
        circumference = ant.circumference_over_lambda * wavelength
        ant.helix_diameter_mm = circumference / math.pi
    else:
        circumference = math.pi * ant.helix_diameter_mm

    ant.circumference_mm = circumference
    ant.helix_radius_mm = ant.helix_diameter_mm / 2.0
    ant.circumference_over_lambda = circumference / wavelength

    if ant.pitch_mm is None:
        ant.pitch_mm = circumference * math.tan(math.radians(ant.pitch_angle_deg))
    else:
        ant.pitch_angle_deg = math.degrees(math.atan(ant.pitch_mm / circumference))

    if ant.wire_diameter_mm is None:
        ant.wire_diameter_mm = ant.wire_diameter_over_lambda * wavelength
    if ant.ground_size_mm is None:
        ant.ground_size_mm = ant.ground_size_over_lambda * wavelength

    ant.axial_length_mm = ant.turns * ant.pitch_mm

    c_over_l = circumference / wavelength
    s_over_l = ant.pitch_mm / wavelength
    n_s_over_l = ant.turns * s_over_l

    ant.theoretical_zin_ohm = 140.0 * c_over_l
    directivity_lin = 15.0 * ant.turns * (c_over_l**2) * s_over_l
    ant.theoretical_directivity_dbi = lin_to_db(directivity_lin)
    # Axial-mode radiation efficiency is high; gain ≈ directivity for PEC/copper.
    ant.theoretical_gain_dbi = ant.theoretical_directivity_dbi
    axial_ratio_lin = (2.0 * ant.turns + 1.0) / (2.0 * ant.turns)
    ant.theoretical_axial_ratio_db = lin_to_db(axial_ratio_lin)
    if c_over_l > 0.0 and n_s_over_l > 0.0:
        ant.theoretical_hpbw_deg = 52.0 / (c_over_l * math.sqrt(n_s_over_l))
    else:
        ant.theoretical_hpbw_deg = 0.0

    feed.pin_height_mm = feed.pin_height_over_lambda * wavelength
    feed.feeder_length_mm = feed.feeder_length_over_lambda * wavelength
    feed.coax_inner_radius_mm = feed.coax_inner_over_lambda * wavelength
    feed.coax_outer_radius_mm = feed.coax_outer_over_lambda * wavelength
    if feed.enable_impedance_match:
        if feed.match_l_h <= 0.0 or feed.match_c_f <= 0.0:
            feed.match_l_h, feed.match_c_f = l_section_match(
                ant.theoretical_zin_ohm, feed.port_impedance_ohm, ant.frequency_hz
            )
        # Port gap + series-L gap + two 2 mm pin stubs. Keeps RLC sheets coarse.
        feed.pin_height_mm = max(feed.pin_height_mm, 8.0)

    boundary.padding_mm = boundary.padding_over_lambda * wavelength
    boundary.extra_axial_padding_mm = boundary.extra_axial_padding_over_lambda * wavelength
    mesh.helix_max_length_mm = mesh.helix_max_length_over_lambda * wavelength

    return config


def synthesis_summary(config: DesignConfig) -> dict[str, float | str]:
    ant = config.antenna
    return {
        "frequency_ghz": ant.frequency_ghz,
        "mode": ant.mode,
        "polarization": ant.polarization,
        "wavelength_mm": round(ant.wavelength_mm, 3),
        "turns": ant.turns,
        "helix_diameter_mm": round(ant.helix_diameter_mm or 0.0, 3),
        "pitch_mm": round(ant.pitch_mm or 0.0, 3),
        "pitch_angle_deg": round(ant.pitch_angle_deg, 3),
        "C_over_lambda": round(ant.circumference_over_lambda, 4),
        "wire_diameter_mm": round(ant.wire_diameter_mm or 0.0, 3),
        "ground_size_mm": round(ant.ground_size_mm or 0.0, 3),
        "axial_length_mm": round(ant.axial_length_mm, 3),
        "theoretical_zin_ohm": round(ant.theoretical_zin_ohm, 2),
        "theoretical_gain_dbi": round(ant.theoretical_gain_dbi, 2),
        "theoretical_directivity_dbi": round(ant.theoretical_directivity_dbi, 2),
        "theoretical_axial_ratio_db": round(ant.theoretical_axial_ratio_db, 2),
        "theoretical_hpbw_deg": round(ant.theoretical_hpbw_deg, 2),
        "resonance_ghz": round(ant.frequency_ghz, 3),
        "s11_target_db": config.validation.s11_max_db,
        "match_l_nh": round(config.feed.match_l_h * 1e9, 3),
        "match_c_pf": round(config.feed.match_c_f * 1e12, 3),
    }
