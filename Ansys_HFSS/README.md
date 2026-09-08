# Ansys HFSS — electromagnetic solver layer

Python / PyAEDT does **not** replace this layer. HFSS performs the numerical
electromagnetic computation, primarily with the Finite Element Method (FEM).

```
Python / PyAEDT
       │
       ▼
Ansys Electronics Desktop
       │
       ▼
HFSS Design
       │
       ├── Electromagnetic model   (geometry, materials, port, radiation BC)
       ├── FEM mesh                (tetrahedra, length mesh, slider)
       ├── Adaptive solution       (driven setup + interpolating sweep)
       └── EM results              (S11, VSWR, Gain, Directivity, AR, pattern)
```

## Electromagnetic model

Created by `Python/geometry_generator.py`, `port_setup.py`, and `boundary_setup.py`.

| Object | Role |
|---|---|
| HelixWire | Radiating conductor (copper, 6 turns, D = 33.7 mm) |
| Ground | Thin 3D copper image plane |
| FeedPin / FeedPinUpper | 50 Ω lumped-port launch (pin stops at z = 0) |
| MatchL / MatchC | Series L (nH) and shunt C (pF) match sheets |
| GroundPost | Ground return for the shunt C |
| PortSheet | Lumped Port1 (50 Ω) |
| AirBox | Truncated free-space domain + absorbing boundary |
| InfiniteSphere1 | Far-field post-processing surface |

## FEM mesh

Created by `Python/solver_setup.py`.

- Initial mesh from the HFSS slider
- Length mesh on the helix wire (~λ/25)
- Adaptive refinement during the driven solution

## Adaptive solution

Applied automatically by `Python/solver_setup.py` (`setup.update()` + save).
`Python/simulation_runner.py` then runs **Analyze All** (`hfss.analyze(setup=None)`
or `odesign.AnalyzeAll()`). No HFSS GUI Apply / Analyze click is required.

- Driven Modal (default) or Driven Terminal
- Adaptive frequency = design frequency (3.035 GHz)
- Convergence on MaxΔS
- Interpolating sweep across 0.85 f₀ … 1.15 f₀ (2.580–3.490 GHz, 51 pts)

## EM results

Created in the AEDT Results folder and extracted after Analyze All.

| Metric | HFSS FEM | Spec | Result |
|---|---|---|---|
| S11 at 3.035 GHz | −27.8 dB | ≤ −20 dB | PASS |
| Resonance (S11 min) | 3.035 GHz (−31.4 dB peak) | 3.035 ± 0.005 GHz | PASS |
| VSWR at 3.035 GHz | 1.09 | ≤ 2.0 | PASS |
| Gain (boresight) | 12.14 dBi | ≥ 8 dBi | PASS |
| Directivity (boresight) | 12.14 dBi | ≥ 8 dBi | PASS |
| Axial ratio (boresight) | 1.46 dB | ≤ 3 dB | PASS |

Matched extract: series L 2.15 nH + physical plate 0.28 pF. Dashboard: `results/20260906_222837/dashboard.html`.

- S11 / return loss
- VSWR
- Gain and directivity vs θ
- Axial ratio vs θ
- Radiation pattern (φ = 0° and 90°)
