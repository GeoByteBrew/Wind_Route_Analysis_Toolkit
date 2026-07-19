"""Route geometry helpers: snap-to-route, chainage (km), distance profile."""

from __future__ import annotations

from typing import Any

import numpy as np
from shapely.geometry import LineString, Point

from backend.services.parse_route import line_length_m


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def ensure_linestring(geom) -> LineString:
    if geom.geom_type == "MultiLineString":
        coords = []
        for part in geom.geoms:
            coords.extend(list(part.coords))
        return LineString(coords)
    return geom


def snap_to_route(route_geom: LineString, lon: float, lat: float) -> dict[str, Any]:
    """Snap a click to the nearest point on the route and return chainage in km."""
    route = ensure_linestring(route_geom)
    total_m = line_length_m(route)
    if total_m <= 0 or len(route.coords) < 2:
        raise ValueError("Route geometry is empty or invalid.")

    pt = Point(lon, lat)
    # Fraction along projected geometry length (CRS units) → scale to haversine distance
    proj = float(route.project(pt))
    geom_len = float(route.length) or 1.0
    frac = min(1.0, max(0.0, proj / geom_len))
    snapped = route.interpolate(proj)
    km = round((frac * total_m) / 1000.0, 2)
    offset_m = round(_haversine_m(lon, lat, snapped.x, snapped.y), 1)

    return {
        "lon": float(snapped.x),
        "lat": float(snapped.y),
        "km": km,
        "km_label": f"km {km:.2f}",
        "offset_m": offset_m,
        "distance_km_total": round(total_m / 1000.0, 2),
    }


def distance_profile(route_geom: LineString, step_km: float = 50.0) -> list[dict[str, Any]]:
    """Sample points along the route every step_km (plus start/end)."""
    route = ensure_linestring(route_geom)
    total_m = line_length_m(route)
    total_km = total_m / 1000.0
    if total_km <= 0:
        return []

    targets = [0.0]
    k = step_km
    while k < total_km:
        targets.append(round(k, 2))
        k += step_km
    if targets[-1] != round(total_km, 2):
        targets.append(round(total_km, 2))

    geom_len = float(route.length) or 1.0
    profile = []
    for km in targets:
        frac = 0.0 if total_km == 0 else min(1.0, km / total_km)
        pt = route.interpolate(frac * geom_len)
        profile.append(
            {
                "km": km,
                "km_label": f"km {km:.2f}",
                "lon": float(pt.x),
                "lat": float(pt.y),
            }
        )
    return profile
