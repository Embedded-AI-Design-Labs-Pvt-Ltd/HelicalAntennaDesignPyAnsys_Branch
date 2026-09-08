"""Open simulation plots as native windows inside Ansys Electronics Desktop.

Reports and field overlays are created in the HFSS GUI, not only exported.
"""

from __future__ import annotations

import logging
from typing import Any

from antenna_params import DesignConfig
from comparison_reports import _theta_samples, comparison_report_jobs, solution_context

LOGGER = logging.getLogger(__name__)


class AnsysPlotDisplay:
    def __init__(self, hfss: Any, config: DesignConfig):
        self.hfss = hfss
        self.config = config
        self.opened: list[str] = []

    def show(self, include_fields: bool = False) -> list[str]:
        """Create comparison reports, overlay fields, and bring AEDT to the foreground."""
        try:
            self._ensure_graphical()
            self._fit_model()
            self._configure_farfield_sphere()
            self._log_farfield_quantities()
            self._ensure_ar_output()
            self.opened.extend(self._create_comparison_plots())
            self.opened.extend(self._create_polarization_traces())
            if include_fields:
                try:
                    self.opened.extend(self._create_field_overlay())
                except Exception as exc:
                    LOGGER.debug("Field overlay skipped: %s", exc)
            self._refresh_reports()
            self._bring_ansys_to_front()
        except Exception as exc:
            LOGGER.warning("HFSS comparison plots incomplete: %s", exc)
        except SystemExit as exc:
            LOGGER.warning("PyAEDT aborted a report call: %s", exc)
        LOGGER.info("Ansys GUI plots opened: %s", self.opened)
        return self.opened

    def _ensure_graphical(self) -> None:
        if self.config.session.non_graphical:
            LOGGER.warning("non_graphical is True — plots cannot be shown in the AEDT GUI")
        desktop = getattr(self.hfss, "desktop_class", None)
        odesktop = getattr(desktop, "odesktop", None) or getattr(self.hfss, "odesktop", None)
        for method_name in ("RestoreWindow", "ShowWindow"):
            method = getattr(odesktop, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass

    def _fit_model(self) -> None:
        try:
            self.hfss.modeler.fit_all()
        except Exception:
            pass

    def _solution_context(self) -> tuple[str, str, str]:
        setup, category, s11, _vswr = solution_context(self.config)
        return setup, category, s11

    def _active_sweep(self) -> str | None:
        target = f"{self.config.solver.setup_name} : {self.config.solver.sweep_name}"
        sweeps: list[str] = []
        try:
            sweeps = [str(item) for item in (getattr(self.hfss, "existing_analysis_sweeps", []) or [])]
        except Exception:
            sweeps = []
        if target in sweeps:
            return target
        for item in sweeps:
            if item.endswith(f" : {self.config.solver.sweep_name}"):
                return item
        for attr in ("nominal_sweep",):
            try:
                value = getattr(self.hfss, attr, None)
                if value and "LastAdaptive" not in str(value):
                    return str(value)
            except Exception:
                continue
        for item in sweeps:
            if "Sweep" in item:
                return item
        return sweeps[0] if sweeps else None

    def _nominal_variations(self) -> dict[str, Any]:
        for attr in ("nominal_wvalues", "nominal_values"):
            try:
                manager = getattr(self.hfss, "available_variations", None)
                raw = getattr(manager, attr, None) if manager else None
                if callable(raw):
                    raw = raw()
                if raw:
                    return dict(raw)
            except Exception:
                continue
        return {}

    def _sphere_names(self) -> list[str]:
        try:
            return [str(item) for item in self.hfss.odesign.GetModule("RadField").GetInfiniteSphereNames()]
        except Exception:
            return []

    def _configure_farfield_sphere(self) -> None:
        """Edit InfiniteSphere1 in place. Do not insert InfiniteSphere1_2, _3, …"""
        b = self.config.boundary
        name = b.infinite_sphere
        pol = "Circular" if self.config.antenna.polarization.lower() in {"rhcp", "lhcp"} else "Linear"
        props = [
            f"NAME:{name}",
            "UseCustomRadiationSurface:=",
            False,
            "CSDefinition:=",
            "Theta-Phi",
            "Polarization:=",
            pol,
            "ThetaStart:=",
            f"{b.theta_start}deg",
            "ThetaStop:=",
            f"{b.theta_stop}deg",
            "ThetaStep:=",
            f"{b.theta_step}deg",
            "PhiStart:=",
            f"{b.phi_start}deg",
            "PhiStop:=",
            f"{b.phi_stop}deg",
            "PhiStep:=",
            f"{b.phi_step}deg",
            "UseLocalCS:=",
            False,
        ]
        try:
            rad = self.hfss.odesign.GetModule("RadField")
            rad.EditInfiniteSphereSetup(name, props)
            LOGGER.info(
                "Far-field sphere %s  polarization=%s  theta=%s–%s step %s deg",
                name,
                pol,
                b.theta_start,
                b.theta_stop,
                b.theta_step,
            )
        except Exception as exc:
            LOGGER.warning("Could not edit infinite sphere %s: %s", name, exc)

    def _log_farfield_quantities(self) -> None:
        try:
            quantities = self.hfss.post.available_report_quantities(
                report_category="Far Fields",
                display_type="Rectangular Plot",
                context=self.config.boundary.infinite_sphere,
            )
            LOGGER.info("Far-field quantities: %s", quantities)
        except (Exception, SystemExit) as exc:
            LOGGER.debug("Far-field quantity list unavailable: %s", exc)

    def _ensure_ar_output(self) -> None:
        """Student far-field reports omit AxialRatio. Define AR from RHCP/LHCP."""
        setup = f"{self.config.solver.setup_name} : LastAdaptive"
        expr = (
            "20*log10((sqrt(GainRHCP)+sqrt(GainLHCP))/"
            "abs(sqrt(GainRHCP)-sqrt(GainLHCP)))"
        )
        context = ["Context:=", self.config.boundary.infinite_sphere]
        try:
            omod = self.hfss.odesign.GetModule("OutputVariable")
        except Exception:
            try:
                omod = self.hfss.odesign.GetModule("OutputVariables")
            except Exception as exc:
                LOGGER.debug("Output variable module unavailable: %s", exc)
                return
        existing: list[str] = []
        for getter in ("GetOutputVariables", "GetAllOutputVariables"):
            method = getattr(omod, getter, None)
            if not callable(method):
                continue
            try:
                existing = [str(item) for item in method()]
                break
            except Exception:
                continue
        if "AR_dB" in existing:
            LOGGER.info("Far-field output variable AR_dB already exists")
            return
        for method_name, args in (
            ("CreateOutputVariable", ("AR_dB", expr, setup, "Far Fields", context)),
            ("CreateOutputVariable", ("AR_dB", expr, setup, "Far Fields")),
        ):
            method = getattr(omod, method_name, None)
            if not callable(method):
                continue
            try:
                method(*args)
                LOGGER.info("Created far-field output variable AR_dB")
                return
            except Exception:
                continue
        LOGGER.debug("AR_dB output variable already present or not created")

    def _create_comparison_plots(self) -> list[str]:
        created = []
        adaptive = f"{self.config.solver.setup_name} : LastAdaptive"
        for job in comparison_report_jobs(self.config, self._active_sweep()):
            far = job.get("report_category") == "Far Fields"
            setup = adaptive if far else job["setup"]
            expressions = [job["expressions"], *job.get("alt_expressions", [])]
            ok = False
            for expr in expressions:
                ok = self._create_report(
                    name=job["name"],
                    expressions=expr,
                    plot_type=job["plot_type"],
                    report_category=job["report_category"],
                    setup=setup,
                    context=job.get("context"),
                    primary=job.get("primary"),
                    secondary=job.get("secondary"),
                    variations=job.get("variations"),
                    native_category=job["report_category"],
                    native_y=[expr],
                )
                if ok:
                    break
            if ok:
                created.append(job["name"])
        return created

    def _create_polarization_traces(self) -> list[str]:
        """RHCP/LHCP vs theta — used to build AR if AxialRatio has no samples."""
        sphere = self.config.boundary.infinite_sphere
        adaptive = f"{self.config.solver.setup_name} : LastAdaptive"
        cuts = {"Freq": ["All"], "Phi": ["0deg"], "Theta": _theta_samples(self.config)}
        opened: list[str] = []
        for name, expr in (("Gain_RHCP_Theta", "dB(GainRHCP)"), ("Gain_LHCP_Theta", "dB(GainLHCP)")):
            if self._create_report(
                name=name,
                expressions=expr,
                plot_type="Rectangular Plot",
                report_category="Far Fields",
                setup=adaptive,
                context=sphere,
                primary="Theta",
                variations=cuts,
                native_category="Far Fields",
                native_y=[expr],
            ):
                opened.append(name)
        return opened

    def _create_field_overlay(self) -> list[str]:
        """Show Mag_E on a cut-plane through the helix in the 3D modeler."""
        setup = None
        for candidate in (
            self._safe_attr("nominal_adaptive"),
            self._safe_attr("nominal_sweep"),
            f"{self.config.solver.setup_name} : LastAdaptive",
        ):
            if candidate:
                setup = candidate
                break
        frequency = f"{self.config.antenna.frequency_ghz}GHz"
        for factory in (
            lambda: self.hfss.post.create_fieldplot_cutplane(
                assignment=["Global:XZ"],
                quantity="Mag_E",
                setup=setup,
                intrinsics={"Freq": frequency, "Phase": "0deg"},
            ),
            lambda: self.hfss.post.create_fieldplot_cutplane(
                ["Global:XZ"],
                "Mag_E",
                setup,
                {"Freq": frequency, "Phase": "0deg"},
            ),
            lambda: self.hfss.post.create_fieldplot_volume(
                assignment=["AirBox"],
                quantity="Mag_E",
                setup=setup,
                intrinsics={"Freq": frequency, "Phase": "0deg"},
            ),
        ):
            try:
                plot = factory()
                name = getattr(plot, "name", None) or "Mag_E"
                LOGGER.info("Field overlay created in HFSS modeler: %s", name)
                return [str(name)]
            except Exception as exc:
                LOGGER.debug("Field overlay attempt failed: %s", exc)
        LOGGER.warning("Could not overlay Mag_E on the HFSS model")
        return []

    def _safe_attr(self, name: str) -> Any:
        try:
            return getattr(self.hfss, name, None)
        except Exception:
            return None

    def _create_report(
        self,
        name: str,
        expressions: str,
        plot_type: str,
        report_category: str,
        setup: str,
        context: str | None = None,
        primary: str | None = None,
        secondary: str | None = None,
        variations: dict | None = None,
        native_category: str | None = None,
        native_y: list[str] | None = None,
    ) -> bool:
        self._delete_report(name)
        if self._native_create_report(
            name=name,
            category=native_category or report_category,
            plot_type=plot_type,
            setup=setup,
            expressions=native_y or [expressions],
            context=context,
            primary=primary,
            secondary=secondary,
            variations=variations,
        ):
            return True
        return False

    def _native_create_report(
        self,
        name: str,
        category: str,
        plot_type: str,
        setup: str,
        expressions: list[str],
        context: str | None,
        primary: str | None,
        secondary: str | None,
        variations: dict | None,
    ) -> bool:
        try:
            omodule = self.hfss.odesign.GetModule("ReportSetup")
        except Exception as exc:
            LOGGER.debug("ReportSetup module unavailable: %s", exc)
            return False

        allowed = {"Freq", "Theta", "Phi", "Phase"}
        families = ["Freq:=", ["All"]]
        if variations:
            families = []
            for key, value in variations.items():
                if key not in allowed:
                    continue
                items = value if isinstance(value, (list, tuple)) else [value]
                families.extend([f"{key}:=", [str(item) for item in items]])
        if context:
            context_array = ["Context:=", context]
        else:
            context_array = ["Domain:=", "Sweep"]

        if plot_type == "3D Polar Plot":
            display = [
                "Phi Component:=",
                "Phi",
                "Theta Component:=",
                "Theta",
                "Mag Component:=",
                expressions,
            ]
        elif plot_type == "Smith Chart":
            display = ["Polar Component:=", expressions]
        elif plot_type == "Radiation Pattern":
            display = [
                "Ang Component:=",
                primary or "Theta",
                "Mag Component:=",
                expressions,
            ]
        else:
            x_name = primary or "Freq"
            display = ["X Component:=", x_name, "Y Component:=", expressions]
            if secondary:
                display.extend(["Y2 Component:=", secondary])

        try:
            omodule.CreateReport(
                name,
                category,
                plot_type,
                setup,
                context_array,
                families,
                display,
            )
            LOGGER.info("Opened AEDT plot window via ReportSetup: %s", name)
            return True
        except Exception as exc:
            LOGGER.warning("Native CreateReport(%s) failed: %s", name, exc)
            return False

    def _delete_report(self, name: str) -> None:
        existing: list[str] = []
        try:
            existing = [str(item) for item in self.hfss.odesign.GetModule("ReportSetup").GetAllReportNames()]
        except Exception:
            existing = []
        if name not in existing:
            return
        try:
            self.hfss.odesign.GetModule("ReportSetup").DeleteReports([name])
        except Exception:
            pass

    def _refresh_reports(self) -> None:
        try:
            omodule = self.hfss.odesign.GetModule("ReportSetup")
            if hasattr(omodule, "UpdateAllReports"):
                omodule.UpdateAllReports()
            elif self.opened and hasattr(omodule, "UpdateReports"):
                omodule.UpdateReports(self.opened)
        except Exception as exc:
            LOGGER.debug("UpdateAllReports skipped: %s", exc)

    def _bring_ansys_to_front(self) -> None:
        desktop = getattr(self.hfss, "desktop_class", None)
        odesktop = getattr(desktop, "odesktop", None) or getattr(self.hfss, "odesktop", None)
        for method_name in ("RestoreWindow", "MaximizeWindow"):
            method = getattr(odesktop, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
        if os_name_is_windows():
            _foreground_aedt()


def os_name_is_windows() -> bool:
    import os

    return os.name == "nt"


def _foreground_aedt() -> None:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if "Electronics Desktop" in title or "HFSS" in title or "Ansys" in title:
                found.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        if found:
            hwnd = found[0]
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            LOGGER.info("Brought Ansys Electronics Desktop to the foreground")
    except Exception as exc:
        LOGGER.debug("Could not foreground AEDT: %s", exc)
