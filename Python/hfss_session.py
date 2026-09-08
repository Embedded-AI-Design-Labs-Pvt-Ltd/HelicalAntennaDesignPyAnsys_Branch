"""Open Ansys Electronics Desktop Student and activate an HFSS design.

Student 2025.2 often keeps a leftover GUI/lock after a failed run. This session
attaches to that process when possible, waits until 3D Modeler is active, then
builds into a fresh HFSS design.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from admin_rights import is_admin
from antenna_params import DesignConfig

LOGGER = logging.getLogger(__name__)

try:
    from ansys.aedt.core import Hfss

    PYAEDT_AVAILABLE = True
    PYAEDT_IMPORT = "ansys.aedt.core"
except ImportError:  # pragma: no cover
    try:
        from pyaedt import Hfss

        PYAEDT_AVAILABLE = True
        PYAEDT_IMPORT = "pyaedt"
    except ImportError:
        Hfss = None  # type: ignore[assignment]
        PYAEDT_AVAILABLE = False
        PYAEDT_IMPORT = ""


class HfssSession:
    """Owns one Electronics Desktop Student / HFSS design connection."""

    def __init__(self, config: DesignConfig, project_root: Path):
        self.config = config
        self.project_root = Path(project_root)
        self.hfss: Any = None
        self.project_path = (
            self.project_root / self.config.project.work_dir / f"{self.config.project.name}.aedt"
        )

    def open(self) -> Any:
        if not PYAEDT_AVAILABLE:
            raise RuntimeError(
                "PyAEDT is not installed. Install with: pip install ansys-aedt-core"
            )

        self.project_path.parent.mkdir(parents=True, exist_ok=True)
        self._clear_stale_lock()

        LOGGER.info(
            "Opening Electronics Desktop %s  project=%s",
            "Student" if self.config.session.student_version else "commercial",
            self.project_path,
        )
        if self.config.session.admin_mode and not is_admin():
            LOGGER.warning("Admin mode is enabled but this process is not elevated.")

        self.hfss = self._connect()
        self._activate_hfss_design()
        self._wait_for_modeler()
        try:
            self.hfss.modeler.model_units = self.config.project.model_units
        except Exception as exc:
            LOGGER.debug("model_units skipped: %s", exc)
        if self.config.session.rebuild_design:
            self.reset_design()
            self._wait_for_modeler()
        self.bring_to_front()
        return self.hfss

    def _connect(self) -> Any:
        errors: list[str] = []
        # Reuse the Student window from the last run first — a second instance
        # cannot SetActiveEditor on a locked project.
        for new_desktop in (False, True):
            try:
                return self._launch(new_desktop=new_desktop)
            except Exception as exc:
                errors.append(f"new_desktop={new_desktop}: {exc}")
                LOGGER.warning("AEDT connect failed (%s). Trying next option.", exc)

        self._clear_stale_lock()
        try:
            return self._launch(new_desktop=True, use_existing_file=False)
        except Exception as exc:
            errors.append(f"fresh project: {exc}")
        raise RuntimeError(
            "Could not open Ansys Electronics Desktop Student. "
            "Close every AnsysEDT / Electronics Desktop window, then run again. "
            + " | ".join(errors)
        )

    def _launch(self, new_desktop: bool, use_existing_file: bool = True) -> Any:
        kwargs: dict[str, Any] = {
            "design": self.config.project.design,
            "solution_type": self.config.project.solution_type,
            "non_graphical": False,
            "new_desktop": new_desktop,
            "close_on_exit": False,
            "student_version": self.config.session.student_version,
            "remove_lock": True,
        }
        if self.config.session.specified_version:
            kwargs["version"] = self.config.session.specified_version
        if use_existing_file:
            kwargs["project"] = str(self.project_path)

        try:
            app = Hfss(**kwargs)
        except TypeError:
            kwargs.pop("student_version", None)
            kwargs.pop("remove_lock", None)
            app = Hfss(**kwargs)
        LOGGER.info("Connected to AEDT  new_desktop=%s", new_desktop)
        return app

    def _activate_hfss_design(self) -> None:
        name = self.config.project.design
        try:
            self.hfss.set_active_design(name)
            LOGGER.info("Active design set to %s", name)
            return
        except Exception as exc:
            LOGGER.debug("set_active_design(%s) failed: %s", name, exc)
        try:
            self.hfss.insert_design(name, self.config.project.solution_type)
            LOGGER.info("Inserted HFSS design %s", name)
        except Exception:
            try:
                self.hfss.insert_design(name, "HFSS")
            except Exception as exc:
                LOGGER.debug("insert_design failed: %s", exc)
        try:
            self.hfss.set_active_design(name)
        except Exception:
            pass

    def _wait_for_modeler(self, attempts: int = 25) -> None:
        last_error = None
        for step in range(attempts):
            try:
                editor = self.hfss.odesign.SetActiveEditor("3D Modeler")
                if editor:
                    self.hfss._oeditor = editor
                    _ = self.hfss.modeler
                    LOGGER.info("3D Modeler is active")
                    return
            except Exception as exc:
                last_error = exc
                LOGGER.debug("Waiting for 3D Modeler (%s/%s): %s", step + 1, attempts, exc)
                try:
                    self.hfss.set_active_design(self.config.project.design)
                except Exception:
                    pass
                time.sleep(1.0)
        raise RuntimeError(
            "HFSS 3D Modeler did not become active (SetActiveEditor failed). "
            "Close Ansys Electronics Desktop Student completely and run again. "
            f"Last error: {last_error}"
        )

    def _clear_stale_lock(self) -> None:
        for lock in self.project_path.parent.glob(f"{self.project_path.stem}*.lock"):
            try:
                lock.unlink()
                LOGGER.info("Removed stale lock %s", lock.name)
            except Exception as exc:
                LOGGER.debug("Could not remove %s: %s", lock, exc)

    def reset_design(self) -> None:
        """Start from an empty HFSS design so leftover objects cannot block apply."""
        name = self.config.project.design
        self._clear_assignments()
        self._delete_all_reports()
        self._delete_all_setups()
        self._purge_reserved_variables()
        try:
            names = list(self.hfss.modeler.object_names)
            if names:
                LOGGER.info("Clearing %d existing objects for a clean apply", len(names))
                self.hfss.modeler.delete(names)
            LOGGER.info("HFSS design %s is empty and ready", name)
            return
        except Exception as exc:
            LOGGER.warning("Could not clear design %s: %s. Stay on this design.", name, exc)

    def _clear_assignments(self) -> None:
        """Remove ports, RLC, radiation, and far-field setups before deleting solids."""
        try:
            omodule = self.hfss.odesign.GetModule("BoundarySetup")
            for method_name in ("DeleteAllExcitations", "DeleteAllBoundaries"):
                method = getattr(omodule, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
        except Exception as exc:
            LOGGER.debug("Boundary cleanup skipped: %s", exc)
        try:
            orad = self.hfss.odesign.GetModule("RadField")
            names = list(orad.GetInfiniteSphereNames())
            if names:
                orad.DeleteInfiniteSpheres(names)
        except Exception:
            try:
                self.hfss.odesign.GetModule("RadField").DeleteInfiniteSpheres(
                    [self.config.boundary.infinite_sphere]
                )
            except Exception:
                pass

    def _delete_all_setups(self) -> None:
        names: list[str] = []
        try:
            names = list(self.hfss.setup_names)
        except Exception:
            try:
                names = list(self.hfss.existing_analysis_setups)
            except Exception:
                names = []
        for setup_name in names:
            try:
                self.hfss.delete_setup(setup_name)
                LOGGER.info("Deleted leftover setup %s", setup_name)
            except Exception:
                continue

    def _delete_all_reports(self) -> None:
        try:
            omodule = self.hfss.odesign.GetModule("ReportSetup")
            names = list(omodule.GetAllReportNames())
            if names:
                omodule.DeleteReports(names)
                LOGGER.info("Deleted leftover Results reports: %s", names)
        except Exception as exc:
            LOGGER.debug("Report cleanup skipped: %s", exc)

    def _purge_reserved_variables(self) -> None:
        for var_name in ("freq", "Freq"):
            try:
                manager = getattr(self.hfss, "variable_manager", None)
                variables = getattr(manager, "variables", {}) if manager else {}
                if var_name in variables:
                    manager.delete_variable(var_name)
                    LOGGER.info("Deleted reserved variable '%s'", var_name)
                    continue
            except Exception:
                pass
            try:
                self.hfss.odesign.DeleteVariable(var_name)
                LOGGER.info("Deleted reserved variable '%s'", var_name)
            except Exception:
                pass

    def notify_ready(self) -> None:
        message = (
            "Helical antenna setup is applied (Port1, radiation, InfiniteSphere1, Setup1). "
            "In HFSS: right-click Analysis → Analyze All. Ignore earlier 'lost assignment' warnings from rebuild."
        )
        try:
            self.hfss.odesktop.AddMessage(
                self.config.project.name,
                self.config.project.design,
                0,
                message,
            )
        except Exception:
            LOGGER.info(message)
        LOGGER.info(message)

    def bring_to_front(self) -> None:
        desktop = getattr(self.hfss, "desktop_class", None)
        odesktop = getattr(desktop, "odesktop", None) or getattr(self.hfss, "odesktop", None)
        for method_name in ("RestoreWindow", "ShowWindow"):
            method = getattr(odesktop, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
        try:
            from ansys_plot_display import _foreground_aedt

            _foreground_aedt()
        except Exception:
            pass

    def save(self) -> None:
        if self.hfss is None:
            return
        try:
            self.hfss.save_project()
            LOGGER.info("Saved project %s", self.project_path)
        except Exception as exc:
            LOGGER.warning("Save skipped: %s", exc)

    def close(self, keep_desktop: bool = True) -> None:
        if self.hfss is None:
            return
        try:
            self.hfss.release_desktop(False, False if keep_desktop else True)
        except Exception as exc:
            LOGGER.debug("release_desktop skipped: %s", exc)
        self.hfss = None
