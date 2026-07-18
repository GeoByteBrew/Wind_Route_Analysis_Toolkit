"""Slope hazard zone intersection for a candidate route."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, mapping

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@lru_cache(maxsize=1)
def load_slope_zones() -> gpd.GeoDataFrame:
    path = DATA_DIR / "slope_zones.geojson"
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf


def check_slopes(
    route_geom: LineString,
    vehicle_max_slope_pct: float,
) -> dict[str, Any]:
    """Return slope zones intersected by the route that exceed the vehicle limit."""
    zones = load_slope_zones()
    hits = zones[zones.intersects(route_geom)].copy()

    features = []
    steep = []
    for _, row in hits.iterrows():
        max_slope = float(row["max_slope_pct"])
        status = "steep" if max_slope > vehicle_max_slope_pct else "moderate"
        feature = {
            "type": "Feature",
            "properties": {
                "id": row.get("id"),
                "name": row.get("name"),
                "max_slope_pct": max_slope,
                "vehicle_max_slope_pct": vehicle_max_slope_pct,
                "status": status,
            },
            "geometry": mapping(row.geometry),
        }
        features.append(feature)
        if status == "steep":
            steep.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "steep_count": len(steep),
        "intersect_count": len(features),
    }
