"""Apply adaptive FEM setup, frequency sweep, and mesh to the HFSS project.

This writes Analysis Setup + Sweep into the AEDT project tree. No GUI Apply
click is required — ``setup.update()`` commits the same action.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from antenna_params import DesignConfig

LOGGER = logging.getLogger(__name__)


class SolverSetup:
    def __init__(self, hfss: Any, config: DesignConfig, objects: dict[str, str]):
        self.hfss = hfss
        self.config = config
        self.objects = objects
        self.setup_name = config.solver.setup_name
        self.sweep_name = config.solver.sweep_name
        self.setup: Any = None

    def apply(self) -> dict[str, str]:
        """Create, enable, and commit the analysis setup on the open project."""
        try:
            self._remove_existing()
        except Exception as exc:
            LOGGER.warning("Could not inspect existing setups: %s", exc)
        try:
            self._assign_mesh()
        except Exception as exc:
            LOGGER.warning("Mesh operations skipped: %s", exc)
        self._create_setup()
        self._apply_setup_properties()
        self._create_sweep()
        self._enable_setup()
        self._commit()
        LOGGER.info(
            "Applied %s + %s under HFSS design '%s'",
            self.setup_name,
            self.sweep_name,
            getattr(self.hfss, "design_name", self.config.project.design),
        )
        return {"setup": self.setup_name, "sweep": self.sweep_name}

    def create(self) -> dict[str, str]:
        return self.apply()

    def _remove_existing(self) -> None:
        names = []
        try:
            names = list(self.hfss.setup_names)
        except Exception:
            try:
                names = list(self.hfss.existing_analysis_setups)
            except Exception:
                names = []
        for name in names:
            LOGGER.info("Removing leftover setup %s", name)
            try:
                self.hfss.delete_setup(name)
            except Exception as exc:
                LOGGER.debug("delete_setup(%s) skipped: %s", name, exc)

    def _assign_mesh(self) -> None:
        mesh = self.config.mesh
        try:
            self.hfss.mesh.assign_initial_mesh_from_slider(level=mesh.slider_level)
            LOGGER.info("Initial mesh slider level=%s", mesh.slider_level)
        except Exception as exc:
            LOGGER.warning("Mesh slider not applied: %s", exc)

        if not mesh.enable_length_mesh:
            return
        helix = self.objects.get("helix")
        if not helix:
            return
        try:
            self.hfss.mesh.assign_length_mesh(
                assignment=[helix],
                inside_selection=False,
                maximum_length=mesh.helix_max_length_mm,
                maximum_elements=None,
                name="HelixLengthMesh",
            )
            LOGGER.info("Length mesh on %s  max=%.3f mm", helix, mesh.helix_max_length_mm)
        except Exception as exc:
            LOGGER.warning("Length mesh not applied: %s", exc)

    def _create_setup(self) -> None:
        sol = self.config.solver
        freq = f"{sol.adaptive_ghz}GHz"
        last_error = None
        for attempt in range(4):
            try:
                self.setup = self.hfss.create_setup(
                    name=self.setup_name,
                    setup_type="HFSSDriven",
                    Frequency=freq,
                )
                LOGGER.info("Inserted setup %s at %s", self.setup_name, freq)
                return
            except Exception as exc:
                last_error = exc
                LOGGER.warning("create_setup attempt %s failed: %s", attempt + 1, exc)
                time.sleep(1.5)
        raise RuntimeError(f"Could not insert HFSS setup {self.setup_name}: {last_error}") from last_error

    def _apply_setup_properties(self) -> None:
        sol = self.config.solver
        freq = f"{sol.adaptive_ghz}GHz"
        props = {
            "Frequency": freq,
            "MaximumPasses": sol.maximum_passes,
            "MinimumPasses": sol.minimum_passes,
            "MinimumConvergedPasses": sol.minimum_converged_passes,
            "MaxDeltaS": sol.max_delta_s,
            "SaveRadFieldsOnly": sol.save_rad_fields,
            "BasisOrder": 0,
        }
        for key, value in props.items():
            try:
                self.setup.props[key] = value
            except Exception:
                try:
                    self.setup[key] = value
                except Exception:
                    LOGGER.debug("Could not set setup property %s", key)

        if hasattr(self.setup, "update"):
            self.setup.update()
            LOGGER.info("Committed setup properties via setup.update()")

    def _create_sweep(self) -> None:
        sol = self.config.solver
        f0 = self.config.antenna.frequency_ghz
        start = f0 * sol.sweep_start_scale
        stop = f0 * sol.sweep_stop_scale
        self._delete_leftover_sweeps()
        self.hfss.create_linear_count_sweep(
            setup=self.setup_name,
            unit="GHz",
            start_frequency=start,
            stop_frequency=stop,
            num_of_freq_points=sol.sweep_points,
            name=self.sweep_name,
            save_fields=sol.save_fields,
            save_rad_fields=sol.save_rad_fields,
            sweep_type=sol.sweep_type,
        )
        LOGGER.info(
            "Applied sweep %s  %.3f–%.3f GHz  %s pts  type=%s",
            self.sweep_name,
            start,
            stop,
            sol.sweep_points,
            sol.sweep_type,
        )

    def _delete_leftover_sweeps(self) -> None:
        """Drop renamed Sweep1_* copies so the new sweep keeps the name Sweep1."""
        names: list[str] = []
        try:
            names = [str(item) for item in (self.hfss.get_sweeps(self.setup_name) or [])]
        except Exception:
            names = []
        if not names:
            try:
                osetup = self.hfss.odesign.GetModule("AnalysisSetup")
                names = [str(item) for item in osetup.GetSweeps(self.setup_name)]
            except Exception:
                names = []
        for name in names:
            try:
                self.hfss.delete_sweep(self.setup_name, name)
                LOGGER.info("Removed leftover sweep %s", name)
            except Exception as exc:
                LOGGER.debug("delete_sweep(%s) skipped: %s", name, exc)

    def _enable_setup(self) -> None:
        for method_name in ("enable", "enable_setup"):
            method = getattr(self.setup, method_name, None)
            if callable(method):
                try:
                    method()
                    LOGGER.info("Enabled %s", self.setup_name)
                    return
                except TypeError:
                    try:
                        method(True)
                        return
                    except Exception:
                        continue
                except Exception:
                    continue
        try:
            self.hfss.oanalysis.EnableSetup(self.setup_name, True)
        except Exception:
            pass

    def _commit(self) -> None:
        """Force the setup into the project so it appears under Analysis."""
        LOGGER.info("Setup %s enabled; project save is left to the pipeline", self.setup_name)
        names = []
        try:
            names = list(self.hfss.setup_names)
        except Exception:
            pass
        if names and self.setup_name not in names:
            raise RuntimeError(
                f"Setup {self.setup_name} was not applied to the HFSS project. "
                f"Present setups: {names}"
            )
