# Helical Antenna — PyAEDT + Ansys Electronics Desktop Student

Public repository: **[Embedded-AI-Design-Labs-Pvt-Ltd/HelicalAntennaDesignPyAnsys](https://github.com/Embedded-AI-Design-Labs-Pvt-Ltd/HelicalAntennaDesignPyAnsys)**

This project implements and analyzes a **3-turn axial-mode helical antenna** using **PyAEDT** and **Ansys Electronics Desktop (AEDT) Student**.

The final design is tuned for operation at **3.035 GHz** and evaluated against the specified S11, VSWR, gain, directivity, and axial-ratio requirements.

---

## Quick Start

Run the simulation using:

```bash
python run_hfss.py
````

or double-click:

```text
Run_HFSS_Simulation.bat
```

The automation:

1. Opens **Ansys Electronics Desktop Student**
2. Loads or creates `work/Helical_Antenna.aedt`
3. Creates/applies the helix geometry
4. Configures the feed and lumped port
5. Applies the matching network
6. Creates the radiation boundary
7. Configures the mesh
8. Creates `Setup1` and `Sweep1`
9. Leaves the Student GUI open for inspection

### Analyze in HFSS

After the project opens:

1. Confirm the helix geometry in the **3D Modeler**
2. Right-click **Analysis → Analyze All**
3. Open **Results**
4. Review:

   * S11
   * VSWR
   * Gain
   * Directivity
   * Axial Ratio
   * Radiation Pattern

### Optional — Analyze from Python

```powershell
python run_hfss.py --analyze-all
```

---

# Final 3.035 GHz Axial-Mode Design

The final design uses a **3-turn axial-mode helical antenna** with **right-hand circular polarization (RHCP)**.

The antenna geometry and matching network were tuned in HFSS to achieve the required electromagnetic performance at **3.035 GHz**.

| Parameter               |                     Final Value |
| ----------------------- | ------------------------------: |
| Operating Frequency     |                   **3.035 GHz** |
| Number of Turns         |                           **3** |
| Helix Centerline Radius |                    **20.94 mm** |
| Helix Diameter          |                    **41.88 mm** |
| Helix Pitch             |                    **37.20 mm** |
| Wire Diameter           |                    **1.024 mm** |
| Wire Gauge              |                      **18 AWG** |
| Polarization            |                        **RHCP** |
| Ground-Plane Diameter   |                   **112.59 mm** |
| Ground-Plane Radius     |                   **56.295 mm** |
| Helix Material          |                      **Copper** |
| Ground Material         |                      **Copper** |
| Matching Network        | **Series L + physical shunt C** |
| Matching Inductor       |                     **5.11 nH** |
| Matching Capacitor      |                     **0.80 pF** |

---

## Geometry

The modified requirement geometry specifies:

* **3 turns**
* Helix centerline radius = **20.94 mm**
* Helix diameter = **41.88 mm**
* Wire diameter = **1.024 mm**
* Ground-plane diameter = **112.59 mm**
* RHCP axial-mode operation
* Operating frequency = **3.035 GHz**

### Pitch Optimization

The original modified requirement specified a pitch of **29.27 mm**.

During HFSS optimization, the helix pitch was tuned to improve the antenna performance.

The final saved performance-optimized configuration uses:

```text
Pitch = 37.20 mm
```

The pitch change was made to achieve the required S11, VSWR, gain, directivity, and axial-ratio performance.

> **Note:** The final design is performance-optimized and therefore uses a pitch different from the original 29.27 mm geometry requirement.

---

# Matching Network

The final design uses a matching network consisting of a **series inductance** and a **physical shunt capacitance**.

```text
                Helical Antenna
                      │
                      │
                 Antenna Node
                      │
          ┌───────────┴───────────┐
          │                       │
       Series L                Shunt C
       5.11 nH                 0.80 pF
          │                       │
          │                    Ground
          │
       50 Ω Port
```

Final matching components:

| Component          |       Value | Configuration  |
| ------------------ | ----------: | -------------- |
| Matching Inductor  | **5.11 nH** | Series         |
| Matching Capacitor | **0.80 pF** | Physical shunt |
| Port Impedance     |    **50 Ω** | Lumped Port    |

---

# Final HFSS FEM Results

The following results were obtained from the **final saved Ansys HFSS Student simulation** at **3.035 GHz**.

| Metric              | Final HFSS Result |            Requirement |  Status  |
| ------------------- | ----------------: | ---------------------: | :------: |
| Operating Frequency |     **3.035 GHz** |          **3.035 GHz** | **PASS** |
| S11                 |   **−15.8005 dB** |      **−15 to −25 dB** | **PASS** |
| VSWR                |    **1.3871 : 1** | **1.1 : 1 to 1.4 : 1** | **PASS** |
| Directivity         |   **10.2739 dBi** |    **10.0 – 14.5 dBi** | **PASS** |
| Antenna Gain        |   **10.2204 dBi** |      **9.5 – 14.0 dB** | **PASS** |
| Axial Ratio         |     **1.4452 dB** |           **< 1.5 dB** | **PASS** |

---

# Performance Summary

| Requirement                     |    Final Result |  Status  |
| ------------------------------- | --------------: | :------: |
| Operating Frequency = 3.035 GHz |   **3.035 GHz** | **PASS** |
| S11 ≤ −15 dB                    | **−15.8005 dB** | **PASS** |
| VSWR ≤ 1.4 : 1                  |  **1.3871 : 1** | **PASS** |
| Directivity 10.0–14.5 dBi       | **10.2739 dBi** | **PASS** |
| Gain 9.5–14.0 dB                | **10.2204 dBi** | **PASS** |
| Axial Ratio < 1.5 dB            |   **1.4452 dB** | **PASS** |

## Overall Result

### **ALL SPECIFIED PERFORMANCE REQUIREMENTS PASSED**

The final 3-turn helical antenna satisfies all specified performance requirements at **3.035 GHz**.

The design meets the required:

* Operating frequency
* Impedance matching
* VSWR
* Directivity
* Gain
* Circular polarization / axial ratio

---

# HFSS Simulation Configuration

| Setting               | Value                                         |
| --------------------- | --------------------------------------------- |
| Simulation Software   | **Ansys Electronics Desktop Student 2025 R2** |
| Solver                | **HFSS Driven Modal**                         |
| Analysis Method       | **Finite Element Method (FEM)**               |
| Operating Frequency   | **3.035 GHz**                                 |
| Solution Setup        | **Setup1**                                    |
| Frequency Sweep       | **Sweep1**                                    |
| Sweep Type            | **Interpolating**                             |
| Sweep Points          | **51**                                        |
| Radiation Boundary    | **Radiation**                                 |
| Polarization          | **RHCP**                                      |
| Port Type             | **Lumped Port**                               |
| Port Impedance        | **50 Ω**                                      |
| Helix Geometry Method | **Student-safe polyline**                     |
| UDP Helix             | **Disabled**                                  |
| Student Edition       | **Enabled**                                   |

---

# Mesh Configuration

The design is configured for the Ansys HFSS Student Edition limitations.

```text
Mesh Slider Level        = 1
Helix Max Length         = 0.04 λ
Length Mesh              = Disabled
Generate Mesh            = Enabled
```

The Student-safe polyline helix implementation is used instead of the UDP helix implementation.

---

# Solver Configuration

The HFSS solution uses:

```text
Setup Name               = Setup1
Sweep Name               = Sweep1
Sweep Type               = Interpolating
Sweep Points             = 51
Maximum Adaptive Passes  = 4
Minimum Adaptive Passes  = 1
Maximum ΔS               = 0.03
Radiation Fields         = Enabled
Cores                    = 2
```

Frequency sweep range:

```text
Start = 0.85 × 3.035 GHz = 2.57975 GHz
Stop  = 1.15 × 3.035 GHz = 3.49025 GHz
```

---

# Validation Criteria

The final antenna was evaluated against the specified engineering requirements:

| Parameter           |            Requirement |
| ------------------- | ---------------------: |
| Operating Frequency |          **3.035 GHz** |
| S11                 |      **−15 to −25 dB** |
| VSWR                | **1.1 : 1 to 1.4 : 1** |
| Directivity         |    **10.0 – 14.5 dBi** |
| Gain                |      **9.5 – 14.0 dB** |
| Axial Ratio         |           **< 1.5 dB** |

All specified performance requirements were achieved by the final saved HFSS simulation.

---

# Axial Ratio

The final axial-ratio result is:

```text
Axial Ratio = 1.4452 dB
```

The reported value was evaluated at:

```text
Theta = 0°
Phi   = 0°
```

This satisfies the required:

```text
Axial Ratio < 1.5 dB
```

---

# Gain and Directivity

Final HFSS results:

```text
Gain        = 10.2204 dBi
Directivity = 10.2739 dBi
```

Both values fall within the specified performance ranges.

---

# S11 and VSWR

At the target operating frequency:

```text
Frequency = 3.035 GHz
S11       = −15.8005 dB
VSWR      = 1.3871 : 1
```

The results satisfy the specified impedance-matching requirements.

---

# Project Structure

```text
HelicalAntennaDesignPyAnsys/
│
├── Ansys_HFSS/
│
├── Python/
│
├── config/
│   └── default_helix.yaml
│
├── examples/
│
├── results/
│
├── tests/
│
├── work/
│
├── .gitignore
├── README.md
├── requirements.txt
├── Run_HFSS_Simulation.bat
└── run_hfss.py
```

---

# Configuration File

The primary configuration file is:

```text
config/default_helix.yaml
```

Important antenna parameters:

```yaml
antenna:
  frequency_ghz: 3.035
  mode: axial
  polarization: rhcp
  turns: 3.0
  helix_diameter_mm: 41.88
  pitch_mm: 37.20
  wire_diameter_mm: 1.024
  ground_size_mm: 112.59
  conductor_material: copper
  ground_material: copper
```

Matching configuration:

```yaml
feed:
  type: lumped_port
  port_name: Port1
  port_impedance_ohm: 50.0
  enable_impedance_match: true
  match_l_nh: 5.11
  match_c_pf: 0.80
```

---

# Reproducing the Simulation

## 1. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

## 2. Run the HFSS Automation

```bash
python run_hfss.py
```

The script launches Ansys Electronics Desktop Student and builds/configures the HFSS design.

## 3. Analyze the Design

From the HFSS GUI:

```text
Analysis → Analyze All
```

Or analyze from Python:

```powershell
python run_hfss.py --analyze-all
```

## 4. Review Results

The generated HFSS project is stored under:

```text
work/
```

Simulation outputs are stored under:

```text
results/
```

---

# Results and Reports

HFSS results can be reviewed using the generated reports and plots for:

* S11
* VSWR
* Gain
* Directivity
* Axial Ratio
* RHCP/LHCP response
* Radiation Pattern

The final project can be opened from:

```text
work/Helical_Antenna.aedt
```

---

# Important Notes

### 1. Final Design vs Original Geometry

The original modified requirement specified:

```text
Pitch = 29.27 mm
```

The final performance-tuned design uses:

```text
Pitch = 37.20 mm
```

This change was made during HFSS optimization to satisfy the electromagnetic performance requirements.

### 2. Matching Network

The matching network is specific to the final 3-turn geometry.

```text
Series L = 5.11 nH
Shunt C  = 0.80 pF
```

The older matching values associated with the previous 6-turn reference design should not be used as the final values for this design.

### 3. Student Edition

The project is designed to run with **Ansys Electronics Desktop Student** and uses a Student-safe polyline implementation for the helix.

---

# Final Design Status

**Design Status: COMPLETE**

```text
Operating Frequency = 3.035 GHz
Number of Turns     = 3
Polarization        = RHCP
Helix Diameter      = 41.88 mm
Helix Pitch         = 37.20 mm
Wire Diameter       = 1.024 mm
Ground Diameter     = 112.59 mm

S11                 = −15.8005 dB
VSWR                = 1.3871 : 1
Gain                = 10.2204 dBi
Directivity         = 10.2739 dBi
Axial Ratio         = 1.4452 dB
```

### **FINAL RESULT: ALL SPECIFIED PERFORMANCE REQUIREMENTS PASSED**

---

# Project

**Embedded AI Design Labs Pvt Ltd**

Author: Muhammad Samiullah — [muhammadsami@embedailabs.com](mailto:muhammadsami@embedailabs.com)

**GitHub:** [Embedded AI Design Labs Pvt Ltd](https://github.com/Embedded-AI-Design-Labs-Pvt-Ltd)

**Website:** [https://www.embedailabs.com](https://www.embedailabs.com)

```

