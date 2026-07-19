"""Analyze a user-uploaded route against user-entered obstacles and vehicle limits."""

from __future__ import annotations

from typing import Any, Literal

from shapely.geometry import LineString, Point, mapping, shape

from backend.services.parse_route import line_length_m
from backend.services.vehicle import VehicleConstraints

ObstacleType = Literal["low_bridge", "narrow_road", "weight_limit", "steep_slope", "note"]

# ~1.1 km corridor at Hérault latitudes (degrees)
ROUTE_BUFFER_DEG = 0.01


def _evaluate_obstacle(
    obstacle_type: str,
    value: float | None,
    vehicle: VehicleConstraints,
) -> tuple[str, str]:
    """Return (status, detail). status in ok|caution|conflict."""
    if obstacle_type == "low_bridge":
        if value is None:
            return "caution", "Clearance not provided"
        if value < vehicle.height_m:
            return "conflict", f"clearance {value} m < vehicle height {vehicle.height_m} m"
        return "ok", f"clearance {value} m ≥ height {vehicle.height_m} m"

    if obstacle_type == "narrow_road":
        if value is None:
            return "caution", "Width not provided"
        if value < vehicle.width_m:
            return "conflict", f"width {value} m < vehicle width {vehicle.width_m} m"
        if value < vehicle.width_m + 1.0:
            return "caution", f"width {value} m is tight vs vehicle {vehicle.width_m} m"
        return "ok", f"width {value} m ≥ vehicle width {vehicle.width_m} m"

    if obstacle_type == "weight_limit":
        if value is None:
            return "caution", "Weight limit not provided"
        if value < vehicle.weight_t:
            return "conflict", f"limit {value} t < vehicle {vehicle.weight_t} t"
        return "ok", f"limit {value} t ≥ vehicle {vehicle.weight_t} t"

    if obstacle_type == "steep_slope":
        if value is None:
            return "caution", "Slope not provided"
        if value > vehicle.max_slope_pct:
            return "conflict", f"slope {value}% > limit {vehicle.max_slope_pct}%"
        return "ok", f"slope {value}% ≤ limit {vehicle.max_slope_pct}%"

    # note / unknown
    return "caution", "Manual note on route"


def analyze_custom_route(
    route_feature: dict[str, Any],
    obstacles: list[dict[str, Any]],
    vehicle: VehicleConstraints,
) -> dict[str, Any]:
    geom = shape(route_feature["geometry"])
    if geom.geom_type == "MultiLineString":
        coords = []
        for part in geom.geoms:
            coords.extend(list(part.coords))
        route_geom = LineString(coords)
    else:
        route_geom = geom

    if route_geom.is_empty or len(route_geom.coords) < 2:
        raise ValueError("Route geometry is empty or invalid.")

    corridor = route_geom.buffer(ROUTE_BUFFER_DEG)
    distance_km = round(line_length_m(route_geom) / 1000.0, 2)

    evaluated: list[dict[str, Any]] = []
    conflicts = 0
    cautions = 0
    off_route = 0

    for i, obs in enumerate(obstacles):
        lon = float(obs["lon"])
        lat = float(obs["lat"])
        pt = Point(lon, lat)
        on_route = bool(corridor.contains(pt) or corridor.intersects(pt) or route_geom.distance(pt) <= ROUTE_BUFFER_DEG)
        otype = obs.get("type", "note")
        value = obs.get("value")
        value_f = float(value) if value is not None and value != "" else None
        name = obs.get("name") or f"Obstacle {i + 1}"

        if not on_route:
            status, detail = "off_route", "Not near the uploaded route corridor"
            off_route += 1
        else:
            status, detail = _evaluate_obstacle(otype, value_f, vehicle)
            if status == "conflict":
                conflicts += 1
            elif status == "caution":
                cautions += 1

        feature = {
            "type": "Feature",
            "properties": {
                "id": obs.get("id") or f"obs_{i:03d}",
                "name": name,
                "type": otype,
                "value": value_f,
                "note": obs.get("note") or "",
                "status": status,
                "detail": detail,
                "on_route": on_route,
            },
            "geometry": mapping(pt),
        }
        evaluated.append(feature)

    if conflicts > 0:
        feasibility: Literal["feasible", "caution", "blocked"] = "blocked"
    elif cautions > 0:
        feasibility = "caution"
    else:
        feasibility = "feasible"

    route_out = {
        "type": "Feature",
        "properties": {
            **(route_feature.get("properties") or {}),
            "distance_km": distance_km,
            "mode": "uploaded_route",
        },
        "geometry": mapping(route_geom),
    }

    return {
        "route": route_out,
        "obstacles": {
            "type": "FeatureCollection",
            "features": evaluated,
        },
        "summary": {
            "distance_km": distance_km,
            "feasibility": feasibility,
            "issues_count": conflicts + cautions,
            "conflict_count": conflicts,
            "caution_count": cautions,
            "off_route_count": off_route,
            "obstacle_count": len(evaluated),
            "mode": "uploaded_route",
            "region": "user_upload",
            # keep keys for shared summary UI
            "bridge_conflicts": sum(
                1
                for f in evaluated
                if f["properties"]["type"] == "low_bridge" and f["properties"]["status"] == "conflict"
            ),
            "steep_zones": sum(
                1
                for f in evaluated
                if f["properties"]["type"] == "steep_slope" and f["properties"]["status"] == "conflict"
            ),
            "narrow_segments": sum(
                1
                for f in evaluated
                if f["properties"]["type"] == "narrow_road"
                and f["properties"]["status"] in ("conflict", "caution")
            ),
        },
    }
