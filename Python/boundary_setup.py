"""Radiation / PML boundary, PEC ground, and far-field infinite sphere.

The air box is *not* the antenna. It is the truncated computational domain.
An absorbing boundary approximates free space so radiated fields do not
reflect back into the helix.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from antenna_params import DesignConfig

LOGGER = logging.getLogger(__name__)


class BoundarySetup:
    def __init__(self, hfss: Any, config: DesignConfig, objects: dict[str, str]):
        self.hfss = hfss
        self.config = config
        self.objects = objects
        self.airbox_name = "AirBox"
        self.sphere_name = config.boundary.infinite_sphere

    def create(self) -> dict[str, str]:
        self._create_airbox()
        self._assign_absorber()
        self._insert_infinite_sphere()
        return {"airbox": self.airbox_name, "infinite_sphere": self.sphere_name}

    def _create_airbox(self) -> None:
        ant = self.config.antenna
        feed = self.config.feed
        pad = self.config.boundary.padding_mm
        extra = self.config.boundary.extra_axial_padding_mm

        half_xy = (ant.ground_size_mm or 0.0) / 2.0 + pad
        z_min = -(feed.pin_height_mm + 0.5) - pad
        z_max = ant.axial_length_mm + pad + extra
        size_x = 2.0 * half_xy
        size_y = 2.0 * half_xy
        size_z = z_max - z_min

        box = self.hfss.modeler.create_box(
            origin=[-half_xy, -half_xy, z_min],
            sizes=[size_x, size_y, size_z],
            name=self.airbox_name,
            material="vacuum",
        )
        try:
            box.display_wireframe = True
        except Exception:
            pass
        LOGGER.info(
            "AirBox  XY=±%.1f mm  Z=[%.1f, %.1f] mm",
            half_xy,
            z_min,
            z_max,
        )

    def _assign_absorber(self) -> None:
        kind = self.config.boundary.type.lower()
        if kind == "pml":
            try:
                self.hfss.assign_auto_pml()
                LOGGER.info("Assigned auto PML")
                return
            except Exception as exc:
                LOGGER.warning("PML assignment failed (%s). Using Radiation.", exc)

        last_error = None
        for attempt in range(3):
            try:
                self.hfss.assign_radiation_boundary_to_objects(self.airbox_name)
                last_error = None
                break
            except TypeError:
                try:
                    self.hfss.assign_radiation_boundary_to_objects([self.airbox_name])
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
            except Exception as exc:
                last_error = exc
                LOGGER.debug("Radiation on object failed (%s). Trying faces.", exc)
                if self._assign_radiation_to_faces():
                    last_error = None
                    break
            time.sleep(0.4)

        if last_error is not None and not self._radiation_exists():
            raise RuntimeError(f"Could not assign radiation boundary to {self.airbox_name}: {last_error}")
        if not self._radiation_exists() and not self._assign_radiation_to_faces():
            LOGGER.warning("Radiation boundary was not reported after assignment")
        LOGGER.info("Radiation boundary on %s", self.airbox_name)

    def _assign_radiation_to_faces(self) -> bool:
        try:
            faces = self.hfss.modeler.get_object_faces(self.airbox_name)
            self.hfss.assign_radiation_boundary_to_faces(faces)
            LOGGER.info("Radiation boundary on faces of %s", self.airbox_name)
            return True
        except Exception as exc:
            LOGGER.debug("Radiation on faces failed: %s", exc)
            return False

    def _radiation_exists(self) -> bool:
        try:
            names = self.hfss.odesign.GetModule("BoundarySetup").GetBoundariesOfType("Radiation")
            if names:
                return True
        except Exception:
            pass
        try:
            for boundary in getattr(self.hfss, "boundaries", None) or []:
                name = str(getattr(boundary, "name", boundary)).lower()
                kind = str(getattr(boundary, "type", "")).lower()
                if "rad" in name or "radiation" in kind:
                    return True
        except Exception:
            pass
        return False

    def _sphere_exists(self) -> bool:
        try:
            names = [str(item) for item in self.hfss.odesign.GetModule("RadField").GetInfiniteSphereNames()]
            return self.sphere_name in names or bool(names)
        except Exception:
            return False

    def _insert_infinite_sphere(self) -> None:
        if not self._radiation_exists():
            LOGGER.warning("No radiation boundary yet; assigning again before InfiniteSphere")
            self._assign_absorber()
        b = self.config.boundary
        last_error = None
        for attempt in range(3):
            try:
                self.hfss.insert_infinite_sphere(
                    name=self.sphere_name,
                    theta_start=b.theta_start,
                    theta_stop=b.theta_stop,
                    theta_step=b.theta_step,
                    phi_start=b.phi_start,
                    phi_stop=b.phi_stop,
                    phi_step=b.phi_step,
                )
                last_error = None
            except TypeError:
                try:
                    self.hfss.insert_infinite_sphere(
                        definition="Independent",
                        x_start=b.phi_start,
                        x_stop=b.phi_stop,
                        x_step=b.phi_step,
                        y_start=b.theta_start,
                        y_stop=b.theta_stop,
                        y_step=b.theta_step,
                        name=self.sphere_name,
                    )
                    last_error = None
                except Exception as exc:
                    last_error = exc
            except Exception as exc:
                last_error = exc
            if self._sphere_exists():
                LOGGER.info("Infinite sphere '%s' inserted for far-field post-processing", self.sphere_name)
                return
            time.sleep(0.5)
            if not self._radiation_exists():
                self._assign_absorber()
        if last_error is not None:
            LOGGER.warning("Infinite sphere insert incomplete: %s", last_error)
        else:
            LOGGER.warning("Infinite sphere '%s' was not retained after insert", self.sphere_name)
