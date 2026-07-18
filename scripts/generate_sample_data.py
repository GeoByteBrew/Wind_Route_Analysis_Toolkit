#!/usr/bin/env python3
"""Generate synthetic but geographically plausible sample data for Hérault (France).

This is demo data for portfolio / educational use — not production routing data.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data"

# Key places in Hérault (lon, lat)
PLACES = {
    "Montpellier": (3.8767, 43.6108),
    "Beziers": (3.2158, 43.3442),
    "Sete": (3.6976, 43.4028),
    "Lodeve": (3.3181, 43.7322),
    "Lunel": (4.1361, 43.6761),
    "Agde": (3.4758, 43.3108),
    "Pezenas": (3.4233, 43.4600),
    "Clermont": (3.4331, 43.6275),
    "Gignac": (3.5522, 43.6522),
    "Frontignan": (3.7558, 43.4489),
    "Mauguio": (4.0089, 43.6167),
    "Saint-Pons": (2.7667, 43.4833),
}


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def _interpolate(a: tuple[float, float], b: tuple[float, float], n: int = 8) -> list[list[float]]:
    return [
        [a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n]
        for i in range(n + 1)
    ]


def build_roads() -> dict:
    """Build a connected road network between Hérault towns."""
    edges = [
        # Coastal / A9 corridor
        ("Montpellier", "Mauguio", "A9", 12.0, "motorway"),
        ("Mauguio", "Lunel", "A9", 12.0, "motorway"),
        ("Montpellier", "Frontignan", "D612", 7.0, "primary"),
        ("Frontignan", "Sete", "D612", 7.0, "primary"),
        ("Sete", "Agde", "D612", 6.5, "primary"),
        ("Agde", "Beziers", "D612", 7.0, "primary"),
        ("Montpellier", "Pezenas", "A75 spur", 8.0, "trunk"),
        ("Pezenas", "Beziers", "A75", 9.0, "motorway"),
        # Inland / upland (narrower, steeper context)
        ("Montpellier", "Gignac", "D908", 6.0, "primary"),
        ("Gignac", "Clermont", "D908", 5.5, "secondary"),
        ("Clermont", "Lodeve", "D908", 5.0, "secondary"),
        ("Lodeve", "Saint-Pons", "D908", 4.5, "secondary"),
        ("Clermont", "Pezenas", "D609", 5.0, "secondary"),
        ("Gignac", "Pezenas", "D32", 4.0, "tertiary"),
        ("Lodeve", "Beziers", "D35", 4.5, "secondary"),
        ("Lunel", "Mauguio", "D24", 5.5, "secondary"),
        ("Sete", "Pezenas", "D2", 4.0, "tertiary"),
        ("Agde", "Pezenas", "D13", 4.5, "secondary"),
        # Local connector (intentionally narrow for demo constraints)
        ("Frontignan", "Mauguio", "D114", 3.2, "tertiary"),
        ("Gignac", "Frontignan", "D27", 3.5, "tertiary"),
        ("Clermont", "Sete", "D5", 3.8, "tertiary"),
        ("Lodeve", "Gignac", "D25", 3.0, "tertiary"),
    ]

    features = []
    for i, (u, v, name, width, highway) in enumerate(edges):
        coords = _interpolate(PLACES[u], PLACES[v], n=10)
        length = sum(
            _haversine_m(coords[j][0], coords[j][1], coords[j + 1][0], coords[j + 1][1])
            for j in range(len(coords) - 1)
        )
        # Synthetic max slope along segment (%): inland roads steeper
        inland = {u, v} & {"Lodeve", "Saint-Pons", "Clermont", "Gignac"}
        base_slope = 7.0 if inland else 2.5
        max_slope_pct = round(base_slope + (hash(name) % 50) / 10.0, 1)

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": f"road_{i:03d}",
                    "name": name,
                    "from": u,
                    "to": v,
                    "highway": highway,
                    "width_m": width,
                    "max_slope_pct": max_slope_pct,
                    "length_m": round(length, 1),
                    "region": "Hérault",
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            }
        )

    return {"type": "FeatureCollection", "features": features}


def build_bridges() -> dict:
    """Sample bridges / overpasses with vertical clearance (meters)."""
    bridges = [
        ("Pont de la Mosson", 3.85, 43.615, 3.820, "D612"),
        ("Viaduc A9 Montpellier Est", 5.20, 43.608, 3.940, "A9"),
        ("Pont du Lez", 4.10, 43.605, 3.895, "urban"),
        ("Passerelle Frontignan", 3.60, 43.450, 3.760, "D612"),
        ("Pont de Sète Canal", 4.00, 43.405, 3.690, "D612"),
        ("Viaduc Hérault Agde", 4.80, 43.320, 3.470, "D612"),
        ("Pont Neuf Béziers", 3.90, 43.345, 3.220, "D612"),
        ("Pont d'Orb", 4.30, 43.350, 3.230, "local"),
        ("Pont de Lodève", 3.70, 43.730, 3.320, "D908"),
        ("Viaduc Lergue", 4.50, 43.700, 3.350, "D908"),
        ("Pont de Clermont", 3.95, 43.628, 3.435, "D908"),
        ("Pont de Gignac", 4.15, 43.653, 3.555, "D908"),
        ("Passerelle Pézenas", 3.55, 43.462, 3.425, "D609"),
        ("Pont de Lunel", 4.25, 43.675, 4.130, "A9"),
        ("Tunnel fictif Escandorgue", 3.40, 43.690, 3.280, "D35"),
    ]

    features = []
    for i, (name, clearance, lat, lon, road) in enumerate(bridges):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": f"bridge_{i:03d}",
                    "name": name,
                    "clearance_m": clearance,
                    "road_ref": road,
                    "region": "Hérault",
                    "source": "synthetic_sample",
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )

    return {"type": "FeatureCollection", "features": features}


def build_slope_zones() -> dict:
    """Polygons representing steep terrain hazard zones (synthetic)."""
    zones = [
        {
            "name": "Escandorgue foothills",
            "max_slope_pct": 12.5,
            "coords": [
                [3.20, 43.68],
                [3.40, 43.68],
                [3.40, 43.78],
                [3.20, 43.78],
                [3.20, 43.68],
            ],
        },
        {
            "name": "Larzac edge (south)",
            "max_slope_pct": 14.0,
            "coords": [
                [3.28, 43.72],
                [3.45, 43.72],
                [3.45, 43.80],
                [3.28, 43.80],
                [3.28, 43.72],
            ],
        },
        {
            "name": "Clermont hills",
            "max_slope_pct": 9.5,
            "coords": [
                [3.38, 43.60],
                [3.50, 43.60],
                [3.50, 43.66],
                [3.38, 43.66],
                [3.38, 43.60],
            ],
        },
        {
            "name": "Gignac ridge",
            "max_slope_pct": 8.0,
            "coords": [
                [3.52, 43.64],
                [3.60, 43.64],
                [3.60, 43.68],
                [3.52, 43.68],
                [3.52, 43.64],
            ],
        },
    ]

    features = []
    for i, z in enumerate(zones):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": f"slope_{i:03d}",
                    "name": z["name"],
                    "max_slope_pct": z["max_slope_pct"],
                    "region": "Hérault",
                    "source": "synthetic_sample",
                },
                "geometry": {"type": "Polygon", "coordinates": [z["coords"]]},
            }
        )

    return {"type": "FeatureCollection", "features": features}


def build_places() -> dict:
    features = []
    for name, (lon, lat) in PLACES.items():
        features.append(
            {
                "type": "Feature",
                "properties": {"name": name, "region": "Hérault"},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    datasets = {
        "roads.geojson": build_roads(),
        "bridges.geojson": build_bridges(),
        "slope_zones.geojson": build_slope_zones(),
        "places.geojson": build_places(),
    }
    for filename, fc in datasets.items():
        path = DATA / filename
        path.write_text(json.dumps(fc, indent=2), encoding="utf-8")
        print(f"Wrote {path} ({len(fc['features'])} features)")


if __name__ == "__main__":
    main()
