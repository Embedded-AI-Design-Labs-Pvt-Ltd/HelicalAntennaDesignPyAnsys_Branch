"""Create the helical-antenna electromagnetic model in HFSS Student.

Sheets (2D) have no Material property in HFSS. The ground is a thin 3D
copper cylinder so the required circular ground plane is retained.
PortSheet and MatchL stay 2D faces for the lumped port/RLC boundaries.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from antenna_params import DesignConfig

LOGGER = logging.getLogger(__name__)

AXIS_Z = 2
GROUND_THICKNESS_MM = 0.5
RESERVED_HFSS_VARS = {"freq", "Freq", "phase", "Phase", "theta", "Theta", "phi", "Phi"}
MATCH_SHEET_MM = 2.0
EPS0 = 8.854187817e-12
CAP_GAP_MM = 0.8
CAP_FRINGE = 1.35
CAP_THICK_MM = 0.4
CAP_PAD_MM = 6.0


def _mm(value: float) -> str:
    return f"{value}mm"


def feed_reference_z(config: DesignConfig) -> tuple[float, float, float]:
    """Ground top, pin start, and helix-side match node (mm)."""
    ground_z = -config.feed.pin_height_mm
    gap = max(2.0, config.feed.pin_height_mm * 0.2)
    pin_z = ground_z + gap
    return ground_z, pin_z, pin_z + 2.0 * MATCH_SHEET_MM


def plate_side_mm(capacitance_f: float) -> float:
    """Square plate side for a parallel-plate shunt C, including fringe."""
    if capacitance_f <= 0.0:
        return 0.0
    area_m2 = capacitance_f * (CAP_GAP_MM * 1e-3) / (EPS0 * CAP_FRINGE)
    return max(1.6, min(7.5, math.sqrt(max(area_m2, 0.0)) * 1e3))


def apply_physical_capacitor(hfss: Any, config: DesignConfig, capacitance_f: float) -> str | None:
    """Copper plate over GroundPost — Student-safe C, no lumped capacitance token."""
    try:
        if "CapPlate" in list(hfss.modeler.object_names):
            hfss.modeler.delete("CapPlate")
    except Exception:
        pass
    if capacitance_f <= 0.0:
        LOGGER.info("Physical shunt C omitted (0 pF)")
        return None
    # Keep the plate small so Student mesh and feed parasitics stay under control.
    capacitance_f = min(capacitance_f, 1.0e-12)

    ant = config.antenna
    x0 = ant.helix_radius_mm
    pin_r = (ant.wire_diameter_mm or 0.0) / 2.0
    _ground_z, _pin_z, load_z = feed_reference_z(config)
    side = plate_side_mm(capacitance_f)
    metal = "copper"
    if (ant.conductor_material or "").strip().lower() not in {"", "pec"}:
        metal = ant.conductor_material
    plate = hfss.modeler.create_box(
        origin=[x0 + pin_r - 0.2, -side / 2.0, load_z],
        sizes=[side, side, CAP_THICK_MM],
        name="CapPlate",
        material=metal,
    )
    name = getattr(plate, "name", "CapPlate")
    try:
        if "HelixWire" in list(hfss.modeler.object_names):
            hfss.modeler.unite(["HelixWire", name])
            name = "HelixWire"
            LOGGER.info("United CapPlate with HelixWire")
    except Exception as exc:
        LOGGER.warning("Could not unite CapPlate: %s", exc)
    LOGGER.info(
        "Physical shunt C = %.3f pF  plate=%.2f×%.2f mm  gap=%.2f mm",
        capacitance_f * 1e12,
        side,
        side,
        CAP_GAP_MM,
    )
    return name


def helix_centerline(radius_mm: float, pitch_mm: float, turns: float, points_per_turn: int = 8):
    """Discrete helix path used by the swept-polyline fallback."""
    count = max(int(turns * points_per_turn), 8)
    points = []
    for i in range(count + 1):
        turn = i / points_per_turn
        angle = 2.0 * math.pi * turn
        points.append(
            [
                radius_mm * math.cos(angle),
                radius_mm * math.sin(angle),
                pitch_mm * turn,
            ]
        )
    return points


class GeometryGenerator:
    """Build and materialize the axial-mode helix geometry."""

    def __init__(self, hfss: Any, config: DesignConfig):
        self.hfss = hfss
        self.config = config
        self.object_names: dict[str, str] = {}

    def create(self) -> dict[str, str]:
        self._set_design_variables()
        helix_name = self._create_helix()
        self._refresh_modeler()
        ground_name = self._create_ground()
        feed_names = self._create_feed()
        helix_name = self._unite_feed_to_helix(helix_name, feed_names)
        self._clear_ground_intersections(ground_name, helix_name, feed_names)
        self.object_names = {
            "helix": helix_name,
            "ground": ground_name,
            **feed_names,
        }
        LOGGER.info("Geometry objects: %s", self.object_names)
        try:
            self.hfss.modeler.fit_all()
        except Exception:
            pass
        return self.object_names

    def _set_design_variables(self) -> None:
        self._purge_reserved_variables()
        ant = self.config.antenna
        feed = self.config.feed
        variables = {
            "f0": f"{ant.frequency_ghz}GHz",
            "helix_diameter": _mm(ant.helix_diameter_mm or 0.0),
            "helix_radius": _mm(ant.helix_radius_mm),
            "pitch": _mm(ant.pitch_mm or 0.0),
            "turns": str(ant.turns),
            "wire_diameter": _mm(ant.wire_diameter_mm or 0.0),
            "ground_size": _mm(ant.ground_size_mm or 0.0),
            "pin_height": _mm(feed.pin_height_mm),
            "feeder_length": _mm(feed.feeder_length_mm),
            "coax_inner": _mm(feed.coax_inner_radius_mm),
            "coax_outer": _mm(feed.coax_outer_radius_mm),
        }
        for name, value in variables.items():
            if name in RESERVED_HFSS_VARS:
                LOGGER.warning("Skipped reserved HFSS variable name '%s'", name)
                continue
            self.hfss[name] = value
        LOGGER.info("HFSS design variables written")

    def _purge_reserved_variables(self) -> None:
        for name in RESERVED_HFSS_VARS:
            try:
                manager = getattr(self.hfss, "variable_manager", None)
                variables = getattr(manager, "variables", {}) if manager else {}
                if name in variables:
                    manager.delete_variable(name)
                    LOGGER.info("Deleted reserved HFSS variable '%s'", name)
            except Exception:
                try:
                    self.hfss.odesign.DeleteVariable(name)
                    LOGGER.info("Deleted reserved HFSS variable '%s'", name)
                except Exception:
                    pass

    def _create_helix(self) -> str:
        if self.config.session.use_udp_helix:
            try:
                return self._create_helix_udp()
            except Exception as exc:
                LOGGER.warning("UDP helix failed (%s). Falling back to swept polyline.", exc)
        return self._create_helix_polyline()

    def _create_helix_udp(self) -> str:
        ant = self.config.antenna
        wire_r = (ant.wire_diameter_mm or 0.0) / 2.0
        params = [
            ["PolygonSegments", "8"],
            ["PolygonRadius", _mm(wire_r)],
            ["StartHelixRadius", _mm(ant.helix_radius_mm)],
            ["RadiusChange", "0mm"],
            ["Pitch", _mm(ant.pitch_mm or 0.0)],
            ["Turns", str(ant.turns)],
            ["SegmentsPerTurn", "24"],
            ["RightHanded", "1" if ant.right_handed else "0"],
        ]
        helix = self.hfss.modeler.create_udp(
            dll="SegmentedHelix/PolygonHelix.dll",
            parameters=params,
            library="syslib",
            name="HelixWire",
        )
        try:
            udm = self.hfss.get_oo_object(self.hfss.oeditor, helix.name)
            self.hfss.set_oo_property_value(
                aedt_object=udm,
                object_name="CreateUserDefinedPart:1",
                prop_name="RightHanded",
                value=1 if ant.right_handed else 0,
            )
        except Exception as exc:
            LOGGER.debug("Could not set UDP RightHanded property: %s", exc)

        self._assign_material(helix, ant.conductor_material)
        self._disable_solve_inside(helix)
        try:
            self.hfss.modeler.split(helix, "XY", "PositiveOnly")
        except Exception as exc:
            LOGGER.debug("Helix split skipped: %s", exc)
        LOGGER.info("Created helix via SegmentedHelix UDP")
        return helix.name

    def _create_helix_polyline(self) -> str:
        ant = self.config.antenna
        points = helix_centerline(
            radius_mm=ant.helix_radius_mm,
            pitch_mm=ant.pitch_mm or 0.0,
            turns=ant.turns,
            points_per_turn=6,
        )
        # Student-safe swept rectangular cross-section. The configured wire
        # diameter is retained in both dimensions.
        helix = self.hfss.modeler.create_polyline(
            points,
            name="HelixWire",
            xsection_type="Rectangle",
            xsection_width=_mm(ant.wire_diameter_mm or 0.0),
            xsection_height=_mm(ant.wire_diameter_mm or 0.0),
        )
        self._assign_material(helix, ant.conductor_material)
        self._disable_solve_inside(helix)
        LOGGER.info("Created helix via swept polyline (%d points)", len(points))
        return helix.name

    def _create_ground(self) -> str:
        """Thin circular 3D ground plane for HFSS Student.

        The requirement specifies a ground-plane diameter, so the model uses
        a cylindrical copper disk rather than the previous square box.
        """
        ant = self.config.antenna
        feed = self.config.feed
        diameter = ant.ground_size_mm or 0.0
        radius = diameter / 2.0
        ground_z = -feed.pin_height_mm
        thickness = GROUND_THICKNESS_MM
        material = self._solid_material(ant.ground_material)

        if diameter <= 0.0:
            raise ValueError("ground_size_mm must be greater than 0")

        try:
            ground = self.hfss.modeler.create_cylinder(
                orientation=AXIS_Z,
                origin=[0.0, 0.0, ground_z - thickness],
                radius=radius,
                height=thickness,
                name="Ground",
                material=material,
                num_sides=32,
            )
        except TypeError:
            # Some PyAEDT/HFSS Student builds do not expose num_sides in
            # create_cylinder. Retry with the common argument set.
            ground = self.hfss.modeler.create_cylinder(
                orientation=AXIS_Z,
                origin=[0.0, 0.0, ground_z - thickness],
                radius=radius,
                height=thickness,
                name="Ground",
                material=material,
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not create the required circular ground plane. "
                "The previous code silently fell back to a square box; "
                "this version stops instead so the geometry cannot be "
                "mistaken for the required circular ground."
            ) from exc

        self._assign_material(ground, material)
        self._disable_solve_inside(ground)
        LOGGER.info(
            "Created circular 3D ground plane: diameter=%.3f mm thickness=%.3f mm material=%s",
            diameter,
            thickness,
            material,
        )
        return getattr(ground, "name", "Ground")

    def _create_feed(self) -> dict[str, str]:
        """Create a physically connected Student-safe feed and L/shunt-C match.

        Electrical topology:

            50-ohm port -> series L -> antenna node
                                      |
                                      C
                                      |
                                    ground

        ``MatchL`` is a 2-D sheet used by port_setup.py for the HFSS
        Lumped-RLC boundary. ``MatchC`` is a real copper plate separated
        from a grounded copper post by CAP_GAP_MM.
        """
        ant = self.config.antenna
        feed = self.config.feed

        x0 = ant.helix_radius_mm
        y0 = 0.0
        ground_z = -feed.pin_height_mm
        metal = self._solid_material(ant.conductor_material)

        # The port sheet spans the air/feed gap between the ground plane and
        # the lower feed conductor.
        port_gap = max(2.0, feed.pin_height_mm * 0.2)
        pin_z = ground_z + port_gap
        pin_r = max((ant.wire_diameter_mm or 0.0) / 2.0, 0.2)

        names: dict[str, str] = {"port_cap": "Ground"}

        if feed.enable_impedance_match:
            # Keep the complete series-L section below z=0 so the upper
            # conductor can physically meet the first helix point at z=0.
            lower_h = 1.0
            l_gap = 1.0

            if pin_z + lower_h + l_gap >= -0.1:
                # This protects the geometry if a different feed height is
                # supplied in YAML.
                lower_h = max(0.5, -pin_z - l_gap - 0.1)

            l_bottom = pin_z + lower_h
            l_top = l_bottom + l_gap
            upper_h = max(0.5, -l_top)

            # Lower conductor from the port to the RLC sheet.
            pin_lower = self._create_z_solid(
                x0, y0, pin_z, pin_r, lower_h, "FeedPin", metal
            )

            # Series-inductor sheet. port_setup.py applies the configured
            # match_l_nh to this exact sheet.
            match_l = self.hfss.modeler.create_rectangle(
                orientation="YZ",
                origin=[x0, -pin_r, l_bottom],
                sizes=[2.0 * pin_r, l_gap],
                name="MatchL",
            )

            # Upper conductor reaches z=0, where the helix starts.
            pin_upper = self._create_z_solid(
                x0, y0, l_top, pin_r, upper_h, "FeedPinUpper", metal
            )

            names["feed_pin"] = getattr(pin_lower, "name", "FeedPin")
            names["feed_pin_upper"] = getattr(pin_upper, "name", "FeedPinUpper")
            names["match_l"] = getattr(match_l, "name", "MatchL")

            # The antenna/shunt node is the top of the series-L section.
            node_z = l_top

        else:
            pin_h = max(0.5, -pin_z)
            pin = self._create_z_solid(
                x0, y0, pin_z, pin_r, pin_h, "FeedPin", metal
            )
            names["feed_pin"] = getattr(pin, "name", "FeedPin")
            node_z = 0.0

        # Lumped port sheet bridges the ground-to-feed gap.
        port_sheet = self.hfss.modeler.create_rectangle(
            orientation="YZ",
            origin=[x0, -pin_r, ground_z],
            sizes=[2.0 * pin_r, port_gap],
            name="PortSheet",
        )
        try:
            port_sheet.color = (128, 0, 0)
        except Exception:
            pass
        names["port_sheet"] = getattr(port_sheet, "name", "PortSheet")

        if feed.enable_impedance_match:
            # Requested physical capacitance.
            match_c_pf = max(0.0, float(getattr(feed, "match_c_pf", 0.0) or 0.0))
            capacitance_f = min(match_c_pf * 1e-12, 1.0e-12)
            side = plate_side_mm(capacitance_f)

            if side > 0.0:
                # Offset the plate in +X so it covers the pin and leaves room
                # for a grounded post that cannot overlap FeedPin.
                feed_half = max(2.0 * pin_r, 0.2) / 2.0
                plate_x0 = x0 - feed_half
                cap_z = node_z - CAP_THICK_MM
                match_c = self.hfss.modeler.create_box(
                    origin=[plate_x0, -side / 2.0, cap_z],
                    sizes=[side, side, CAP_THICK_MM],
                    name="MatchC",
                    material=metal,
                )
                self._assign_material(match_c, metal)
                self._disable_solve_inside(match_c)
                names["match_c"] = getattr(match_c, "name", "MatchC")
                upper = names.get("feed_pin_upper")
                if upper:
                    try:
                        self.hfss.modeler.unite([upper, names["match_c"]])
                        names["match_c"] = upper
                        LOGGER.info("United MatchC with %s", upper)
                    except Exception as exc:
                        LOGGER.warning("Could not unite MatchC with %s: %s", upper, exc)

                post_side = min(2.0, max(1.2, side * 0.25))
                post_x0 = plate_x0 + side - post_side
                min_clear_x = x0 + feed_half + 0.5
                if post_x0 < min_clear_x:
                    post_x0 = min_clear_x
                    post_side = max(0.8, plate_x0 + side - post_x0)
                post_top = cap_z - CAP_GAP_MM
                post_h = max(0.5, post_top - ground_z)

                post = self.hfss.modeler.create_box(
                    origin=[post_x0, -post_side / 2.0, ground_z],
                    sizes=[post_side, post_side, post_h],
                    name="GroundPost",
                    material=metal,
                )
                self._assign_material(post, metal)
                self._disable_solve_inside(post)

                try:
                    self.hfss.modeler.unite(
                        ["Ground", getattr(post, "name", "GroundPost")]
                    )
                    names["ground_post"] = "Ground"
                    names["port_cap"] = "Ground"
                except Exception as exc:
                    names["ground_post"] = getattr(post, "name", "GroundPost")
                    LOGGER.warning("Could not unite GroundPost with Ground: %s", exc)

                LOGGER.info(
                    "Physical shunt C requested=%.3f pF; plate=%.3f x %.3f x %.3f mm; "
                    "gap=%.3f mm; node_z=%.3f mm",
                    capacitance_f * 1e12,
                    side,
                    side,
                    CAP_THICK_MM,
                    CAP_GAP_MM,
                    node_z,
                )
            else:
                LOGGER.info("Physical shunt C omitted (match_c_pf <= 0)")

            LOGGER.info(
                "Match topology: 50-ohm port -> series L on MatchL -> antenna node; "
                "physical shunt C on MatchC -> Ground"
            )

        LOGGER.info(
            "Port gap=%.3f mm, pin_z=%.3f mm, node_z=%.3f mm",
            port_gap,
            pin_z,
            node_z,
        )
        return names

    def _unite_feed_to_helix(self, helix_name: str, feed_names: dict[str, str]) -> str:
        """Boolean-unite the pin into the helix so HFSS does not see intersecting metals."""
        pin = feed_names.get("feed_pin_upper") or (
            feed_names.get("feed_pin") if "match_l" not in feed_names else None
        )
        if not pin:
            return helix_name
        try:
            result = self.hfss.modeler.unite([helix_name, pin])
            united = getattr(result, "name", None) or helix_name
            LOGGER.info("United %s with %s -> %s", pin, helix_name, united)
            if feed_names.get("feed_pin_upper") == pin:
                feed_names.pop("feed_pin_upper", None)
            elif feed_names.get("feed_pin") == pin:
                feed_names["feed_pin"] = united
            return united
        except Exception as exc:
            LOGGER.warning("Could not unite %s with %s: %s", pin, helix_name, exc)
            return helix_name

    def _clear_ground_intersections(
        self, ground_name: str, helix_name: str, feed_names: dict[str, str]
    ) -> None:
        """Cut feed metals out of Ground so Analyze All does not fail on overlaps."""
        tools = []
        for key in ("feed_pin", "feed_pin_upper"):
            name = feed_names.get(key)
            if name and name not in tools and name != ground_name:
                tools.append(name)
        if helix_name and helix_name != ground_name and helix_name not in tools:
            tools.append(helix_name)
        for tool in tools:
            try:
                self.hfss.modeler.subtract(ground_name, tool, keep_originals=True)
                LOGGER.info("Subtracted %s from %s to remove intersection", tool, ground_name)
            except Exception as exc:
                LOGGER.debug("subtract %s from %s skipped: %s", tool, ground_name, exc)

    def _disable_solve_inside(self, obj: Any) -> None:
        try:
            obj.solve_inside = False
        except Exception:
            try:
                name = obj.name if hasattr(obj, "name") else obj
                self.hfss.modeler[name].solve_inside = False
            except Exception:
                pass

    def _refresh_modeler(self) -> None:
        for method_name in ("refresh", "refresh_all_ids"):
            method = getattr(self.hfss.modeler, method_name, None)
            if callable(method):
                try:
                    method()
                    return
                except Exception:
                    continue

    def _create_z_solid(self, x, y, z, radius, height, name, material):
        """Box along Z — Student 2025.2 CreateCylinder is unreliable after UDP helix."""
        side = max(2.0 * radius, 0.2)
        obj = self.hfss.modeler.create_box(
            origin=[x - side / 2.0, y - side / 2.0, z],
            sizes=[side, side, height],
            name=name,
            material=material,
        )
        LOGGER.info("Created solid %s", name)
        self._disable_solve_inside(obj)
        return obj

    def _create_cylinder(self, origin, radius, height, name, material):
        try:
            obj = self.hfss.modeler.create_cylinder(
                orientation=AXIS_Z,
                origin=origin,
                radius=radius,
                height=height,
                name=name,
            )
            self._assign_material(obj, material)
            return obj
        except Exception as exc:
            LOGGER.warning("Cylinder %s failed (%s). Using a box.", name, exc)
            return self._create_z_solid(
                origin[0], origin[1], origin[2], radius, abs(height), name, material
            )

    def _solid_material(self, material: str) -> str:
        name = (material or "copper").strip()
        if name.lower() == "pec":
            return "copper"
        return name

    def _assign_material(self, obj: Any, material: str) -> None:
        if obj is None:
            return
        if self._is_sheet(obj):
            LOGGER.debug("Skipping material on sheet %s", getattr(obj, "name", obj))
            return
        material = self._solid_material(material)
        try:
            obj.material_name = material
            return
        except Exception:
            pass
        try:
            self.hfss.assign_material(obj.name if hasattr(obj, "name") else obj, material)
        except Exception as exc:
            LOGGER.warning("Material assignment failed for %s (%s): %s", getattr(obj, "name", obj), material, exc)

    def _is_sheet(self, obj: Any) -> bool:
        try:
            if hasattr(obj, "is3d") and obj.is3d is False:
                return True
        except Exception:
            pass
        try:
            return bool(getattr(obj, "object_type", "") == "Sheet")
        except Exception:
            return False
