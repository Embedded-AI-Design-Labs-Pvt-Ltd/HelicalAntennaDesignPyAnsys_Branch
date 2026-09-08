"""Run HFSS Analyze All on the applied project setups.

Python only starts the solve. Mesh generation, adaptive passes, and the
frequency sweep are executed by the HFSS FEM solver.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from antenna_params import DesignConfig

LOGGER = logging.getLogger(__name__)


class SimulationRunner:
    def __init__(self, hfss: Any, config: DesignConfig):
        self.hfss = hfss
        self.config = config

    def analyze(self) -> dict[str, Any]:
        return self.analyze_all()

    def analyze_all(self) -> dict[str, Any]:
        setup = self.config.solver.setup_name
        cores = self.config.solver.cores
        started = time.perf_counter()

        LOGGER.info("Validating HFSS design before Analyze All")
        self._validate_design()

        self.reset_solutions()
        if self.config.solver.generate_mesh:
            self._generate_mesh(setup)

        LOGGER.info("HFSS Analyze All  setup=%s  cores=%s", setup, cores)
        self._run_analyze_all(setup, cores)
        self._wait_until_idle()

        elapsed = time.perf_counter() - started
        LOGGER.info("Analyze All finished in %.1f s", elapsed)
        return {
            "setup": setup,
            "sweep": self.config.solver.sweep_name,
            "elapsed_s": round(elapsed, 2),
            "cores": cores,
            "mode": "analyze_all",
        }

    def reset_solutions(self) -> None:
        """Drop cached FEM results so an RLC change is actually re-solved."""
        for method_name in ("cleanup_solution", "clean_solution"):
            method = getattr(self.hfss, method_name, None)
            if callable(method):
                try:
                    method()
                    LOGGER.info("Cleared cached HFSS solutions via %s", method_name)
                    return
                except Exception:
                    continue
        try:
            self.hfss.odesign.DeleteFullVariation("All", True)
            LOGGER.info("Cleared cached HFSS solutions via DeleteFullVariation")
        except Exception as exc:
            LOGGER.debug("Solution reset skipped: %s", exc)

    def _generate_mesh(self, setup: str) -> None:
        LOGGER.info("Generating FEM mesh for %s", setup)
        try:
            self.hfss.mesh.generate_mesh(setup)
            return
        except Exception as exc:
            LOGGER.debug("mesh.generate_mesh failed: %s", exc)
        try:
            self.hfss.odesign.GenerateMesh(setup)
        except Exception as exc:
            LOGGER.warning("Mesh generation skipped: %s", exc)

    def _run_analyze_all(self, setup: str, cores: int) -> None:
        errors: list[str] = []

        if self.config.solver.analyze_all:
            try:
                ok = self.hfss.analyze(setup=None, cores=cores, blocking=True)
                if ok is False:
                    raise RuntimeError("hfss.analyze(setup=None) returned False")
                LOGGER.info("Analyze All via hfss.analyze(setup=None)")
                return
            except Exception as exc:
                errors.append(f"analyze(None): {exc}")

            if self._native_analyze_all():
                return
            errors.append("odesign.AnalyzeAll")

        try:
            ok = self.hfss.analyze(setup=setup, cores=cores, blocking=True)
            if ok is False:
                raise RuntimeError(f"hfss.analyze({setup}) returned False")
            LOGGER.info("Analyzed setup %s", setup)
            return
        except Exception as exc:
            errors.append(f"analyze({setup}): {exc}")

        try:
            self.hfss.analyze_setup(setup, cores=cores)
            LOGGER.info("Analyzed setup %s via analyze_setup", setup)
            return
        except Exception as exc:
            errors.append(f"analyze_setup: {exc}")

        raise RuntimeError("HFSS Analyze All failed. " + " | ".join(errors))

    def _native_analyze_all(self) -> bool:
        for owner_name in ("odesign", "oanalysis"):
            owner = getattr(self.hfss, owner_name, None)
            if owner is None or not hasattr(owner, "AnalyzeAll"):
                continue
            try:
                owner.AnalyzeAll()
                LOGGER.info("Analyze All via %s.AnalyzeAll()", owner_name)
                return True
            except Exception as exc:
                LOGGER.debug("%s.AnalyzeAll failed: %s", owner_name, exc)
        return False

    def _wait_until_idle(self) -> None:
        waiter = getattr(self.hfss, "wait_on_simulations", None)
        if callable(waiter):
            try:
                waiter()
                return
            except Exception:
                pass

        flag = getattr(self.hfss, "are_there_simulations_running", None)
        deadline = time.time() + 6 * 60 * 60
        while time.time() < deadline:
            running = False
            try:
                running = bool(flag() if callable(flag) else flag)
            except Exception:
                break
            if not running:
                return
            time.sleep(5)

    def _validate_design(self) -> None:
        for method_name in ("validate_simple", "validate"):
            method = getattr(self.hfss, method_name, None)
            if method is None:
                continue
            try:
                result = method()
                LOGGER.info("HFSS %s → %s", method_name, result)
                if result in (False, "Incorrect"):
                    raise RuntimeError(f"HFSS design validation failed: {result}")
                return
            except RuntimeError:
                raise
            except Exception as exc:
                LOGGER.debug("%s failed: %s", method_name, exc)
