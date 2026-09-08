"""Clean HFSS port and impedance-match setup for the helical antenna.

This version intentionally keeps the impedance-match path simple:
    1. Create Port1 as the configured lumped/wave port.
    2. Assign one SERIAL lumped-RLC boundary to the existing MatchL sheet.
    3. Do NOT create another capacitor boundary.
    4. Do NOT call ChangeProperty/EditLumpedRLC.
    5. Do NOT use a native CurrentLine fallback.

The physical MatchC plate is created by geometry_generator.py.
"""

from __future__ import annotations

import logging
from typing import Any

from antenna_params import DesignConfig

LOGGER = logging.getLogger(__name__)


class PortSetup:
    def __init__(
        self,
        hfss: Any,
        config: DesignConfig,
        objects: dict[str, str],
    ):
        self.hfss = hfss
        self.config = config
        self.objects = objects
        self.port_name = config.feed.port_name

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def create(self) -> str:
        feed_type = self.config.feed.type.lower().strip()

        if feed_type == "lumped_port":
            return self._lumped_port()

        return self._wave_port()

    # ------------------------------------------------------------------
    # Wave port
    # ------------------------------------------------------------------
    def _wave_port(self) -> str:
        sheet = self.objects["port_sheet"]
        impedance = self.config.feed.port_impedance_ohm
        name = self.port_name

        # Try the current PyAEDT API first.
        try:
            self.hfss.wave_port(
                assignment=sheet,
                name=name,
                impedance=impedance,
                renormalize=True,
            )
            LOGGER.info(
                "Wave port '%s' created on %s, Z0=%.1f ohm",
                name,
                sheet,
                impedance,
            )
            self._assign_impedance_match()
            return name

        except Exception as exc:
            LOGGER.warning(
                "wave_port() failed: %s. Trying create_wave_port_from_sheet().",
                exc,
            )

        # Compatibility path for older PyAEDT releases.
        try:
            self.hfss.create_wave_port_from_sheet(
                sheet,
                portname=name,
                impedance=impedance,
            )
            LOGGER.info(
                "Wave port '%s' created using create_wave_port_from_sheet().",
                name,
            )
            self._assign_impedance_match()
            return name

        except Exception as exc:
            LOGGER.warning(
                "Wave-port creation failed: %s. Falling back to lumped port.",
                exc,
            )

        return self._lumped_port()

    # ------------------------------------------------------------------
    # Lumped port
    # ------------------------------------------------------------------
    def _lumped_port(self) -> str:
        sheet = self.objects["port_sheet"]

        # Use the explicit reference object if available.
        # Otherwise use the ground conductor.
        reference = self.objects.get("port_cap") or self.objects.get("ground")

        name = self.port_name
        impedance = self.config.feed.port_impedance_ohm

        # ZPos is the vertical direction because the port sheet is a YZ
        # sheet and the feed travels vertically.
        zpos = getattr(
            getattr(self.hfss, "axis_directions", None),
            "ZPos",
            5,
        )

        try:
            self.hfss.lumped_port(
                assignment=sheet,
                reference=reference,
                name=name,
                impedance=impedance,
                renormalize=True,
                integration_line=zpos,
            )

        except TypeError:
            # Compatibility fallback for older PyAEDT signatures.
            self.hfss.lumped_port(
                assignment=sheet,
                reference=reference,
                name=name,
            )

        LOGGER.info(
            "Lumped port '%s' created on %s, reference=%s, Z0=%.1f ohm",
            name,
            sheet,
            reference,
            impedance,
        )

        self._assign_impedance_match()
        return name

    # ------------------------------------------------------------------
    # Impedance matching
    # ------------------------------------------------------------------
    def _assign_impedance_match(self) -> None:
        feed = self.config.feed

        if not feed.enable_impedance_match:
            LOGGER.info("Impedance matching is disabled in configuration.")
            return

        self.apply_match_values(
            feed.match_l_h,
            feed.match_c_f,
            "load",
        )

    def apply_match_values(
        self,
        inductance_h: float,
        capacitance_f: float,
        topology: str = "load",
    ) -> None:
        """Assign the series matching inductor to MatchL.

        MatchC is a PHYSICAL capacitor plate generated by
        geometry_generator.py. It must not be assigned again here as an
        RLC boundary.
        """

        del topology

        match_l = self.objects.get("match_l")

        if not match_l:
            raise RuntimeError(
                "MatchL sheet was not created by geometry_generator.py. "
                "Cannot assign the matching inductor."
            )

        zpos = getattr(
            getattr(self.hfss, "axis_directions", None),
            "ZPos",
            5,
        )

        self._delete_boundary_if_present("MatchL_RLC")
        self._delete_boundary_if_present("MatchC_RLC")

        if inductance_h > 0.0:
            rlc = self.hfss.assign_lumped_rlc_to_sheet(
                assignment=match_l,
                start_direction=zpos,
                name="MatchL_RLC",
                rlc_type="Serial",
                inductance=float(inductance_h),
            )
            if not rlc:
                raise RuntimeError("HFSS/PyAEDT did not create MatchL_RLC on MatchL.")
            LOGGER.info(
                "MatchL_RLC created successfully: sheet=%s, type=Serial, L=%.6g nH",
                match_l,
                inductance_h * 1e9,
            )
        else:
            LOGGER.warning(
                "Configured matching inductance is %.6g H. No MatchL_RLC will be created.",
                inductance_h,
            )

        LOGGER.info(
            "Physical MatchC retained: C=%.6g pF. No MatchC_RLC boundary was created.",
            capacitance_f * 1e12,
        )

    # ------------------------------------------------------------------
    # Boundary cleanup
    # ------------------------------------------------------------------
    def _delete_boundary_if_present(self, name: str) -> None:
        """Delete a stale boundary and HFSS-renamed copies (name_XXXX)."""
        victims: list[str] = [name]
        try:
            for boundary in list(getattr(self.hfss, "boundaries", None) or []):
                bname = str(getattr(boundary, "name", boundary))
                if bname == name or bname.startswith(f"{name}_"):
                    victims.append(bname)
        except Exception:
            pass
        delete_boundary = getattr(self.hfss, "delete_boundary", None)
        for victim in dict.fromkeys(victims):
            if callable(delete_boundary):
                try:
                    delete_boundary(victim)
                    LOGGER.info("Removed stale boundary '%s'.", victim)
                    continue
                except Exception:
                    pass
            try:
                self.hfss.odesign.GetModule("BoundarySetup").DeleteBoundaries([victim])
                LOGGER.info("Removed stale boundary '%s'.", victim)
            except Exception:
                pass


# ----------------------------------------------------------------------
# Compatibility helper used by some external scripts
# ----------------------------------------------------------------------
def create_port_setup(
    hfss: Any,
    config: DesignConfig,
    objects: dict[str, str],
) -> str:
    """Create the configured port and matching network."""
    return PortSetup(hfss, config, objects).create()
