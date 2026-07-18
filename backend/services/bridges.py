"""Bridge clearance checks along a candidate route."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, mapping

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@lru_cache(maxsize=1)
def load_bridges() -> gpd.GeoDataFrame:
    path = DATA_DIR / "bridges.geojson"
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf


def check_bridges(route_geom: LineString, vehicle_height_m: float, buffer_deg: float = 0.02) -> dict[str, Any]:
    """Flag bridges near the route whose clearance is below vehicle height."""
    bridges = load_bridges()
    corridor = route_geom.buffer(buffer_deg)
    nearby = bridges[bridges.intersects(corridor)].copy()

    conflicts = []
    ok = []
    for _, row in nearby.iterrows():
        clearance = float(row["clearance_m"])
        feature = {
            "type": "Feature",
            "properties": {
                "id": row.get("id"),
                "name": row.get("name"),
                "clearance_m": clearance,
                "road_ref": row.get("road_ref"),
                "vehicle_height_m": vehicle_height_m,
                "margin_m": round(clearance - vehicle_height_m, 2),
                "status": "conflict" if clearance < vehicle_height_m else "ok",
            },
            "geometry": mapping(row.geometry),
        }
        if clearance < vehicle_height_m:
            conflicts.append(feature)
        else:
            ok.append(feature)

    return {
        "type": "FeatureCollection",
        "features": conflicts + ok,
        "conflict_count": len(conflicts),
        "checked_count": len(nearby),
    }
