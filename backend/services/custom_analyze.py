"""Analyze a user-uploaded route against user-entered obstacles and vehicle limits."""

from __future__ import annotations

from typing import Any, Literal

from shapely.geometry import Point, mapping, shape

from backend.services.geometry_utils import distance_profile, ensure_linestring, snap_to_route
from backend.services.parse_route import line_length_m
from backend.services.vehicle import VehicleConstraints

# ~1.5 km lateral tolerance for "on route"
MAX_OFFSET_M = 1500.0


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

    return "caution", "Manual note on route"


def _checklist(evaluated: list[dict[str, Any]], vehicle: VehicleConstraints) -> list[dict[str, str]]:
    conflicts = [f for f in evaluated if f["properties"]["status"] == "conflict"]
    cautions = [f for f in evaluated if f["properties"]["status"] == "caution"]
    bypass_ok = [f for f in conflicts if f["properties"].get("bypass_possible")]
    return [
        {
            "item": "Route geometry loaded",
            "state": "done",
            "detail": "Corridor available for chainage / snap",
        },
        {
            "item": "Vehicle template applied",
            "state": "done",
            "detail": f"{vehicle.template_label} ({vehicle.template_id})",
        },
        {
            "item": "Obstacles reviewed in km order",
            "state": "done" if evaluated else "todo",
            "detail": f"{len(evaluated)} obstacle(s) on file",
        },
        {
            "item": "Resolve hard conflicts",
            "state": "todo" if conflicts else "done",
            "detail": f"{len(conflicts)} conflict(s)"
            + (f", {len(bypass_ok)} with bypass flagged" if bypass_ok else ""),
        },
        {
            "item": "Review caution items",
            "state": "todo" if cautions else "done",
            "detail": f"{len(cautions)} caution(s)",
        },
        {
            "item": "Export report for stakeholders",
            "state": "todo",
            "detail": "PDF / CSV / GeoJSON / project JSON",
        },
    ]


def analyze_custom_route(
    route_feature: dict[str, Any],
    obstacles: list[dict[str, Any]],
    vehicle: VehicleConstraints,
    snap: bool = True,
) -> dict[str, Any]:
    geom = shape(route_feature["geometry"])
    route_geom = ensure_linestring(geom)

    if route_geom.is_empty or len(route_geom.coords) < 2:
        raise ValueError("Route geometry is empty or invalid.")

    distance_km = round(line_length_m(route_geom) / 1000.0, 2)
    profile = distance_profile(route_geom, step_km=50.0)

    evaluated: list[dict[str, Any]] = []
    conflicts = 0
    cautions = 0
    off_route = 0

    for i, obs in enumerate(obstacles):
        lon = float(obs["lon"])
        lat = float(obs["lat"])
        otype = obs.get("type", "note")
        value = obs.get("value")
        value_f = float(value) if value is not None and value != "" else None
        name = obs.get("name") or f"Obstacle {i + 1}"
        severity = obs.get("severity") or "medium"
        bypass = bool(obs.get("bypass_possible"))
        note = obs.get("note") or ""
        photo = obs.get("photo_data_url") or obs.get("photo") or ""

        snap_info = snap_to_route(route_geom, lon, lat)
        on_route = snap_info["offset_m"] <= MAX_OFFSET_M
        use_lon = snap_info["lon"] if snap and on_route else lon
        use_lat = snap_info["lat"] if snap and on_route else lat
        km = snap_info["km"]
        km_label = snap_info["km_label"]

        if not on_route:
            status, detail = "off_route", "Not near the uploaded route corridor"
            off_route += 1
        else:
            status, detail = _evaluate_obstacle(otype, value_f, vehicle)
            if status == "conflict":
                conflicts += 1
                if bypass:
                    detail = f"{detail} · bypass flagged"
            elif status == "caution":
                cautions += 1

        # Keep photos only if reasonably small (avoid huge JSON/PDF payloads)
        photo_kept = str(photo) if photo and len(str(photo)) < 400_000 else ""

        feature = {
            "type": "Feature",
            "properties": {
                "id": obs.get("id") or f"obs_{i:03d}",
                "name": name,
                "type": otype,
                "value": value_f,
                "note": note,
                "severity": severity,
                "bypass_possible": bypass,
                "photo_attached": bool(photo_kept),
                "photo_data_url": photo_kept,
                "status": status,
                "detail": detail,
                "on_route": on_route,
                "km": km,
                "km_label": km_label,
                "snap_offset_m": snap_info["offset_m"],
            },
            "geometry": mapping(Point(use_lon, use_lat)),
        }
        evaluated.append(feature)

    evaluated.sort(key=lambda f: (f["properties"].get("km") is None, f["properties"].get("km") or 0))

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
        "obstacles": {"type": "FeatureCollection", "features": evaluated},
        "distance_profile": profile,
        "checklist": _checklist(evaluated, vehicle),
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
            "vehicle_template": vehicle.template_label,
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
