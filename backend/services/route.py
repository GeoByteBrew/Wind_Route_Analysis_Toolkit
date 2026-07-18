"""Route finding on the sample Hérault road network."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, Point, mapping
from shapely.ops import nearest_points, unary_union

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@dataclass
class VehicleConstraints:
    length_m: float
    width_m: float
    height_m: float
    weight_t: float
    max_slope_pct: float = 8.0


@lru_cache(maxsize=1)
def load_roads() -> gpd.GeoDataFrame:
    path = DATA_DIR / "roads.geojson"
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf


def _node_id(coord: tuple[float, float]) -> str:
    return f"{coord[0]:.5f},{coord[1]:.5f}"


def build_graph(roads: gpd.GeoDataFrame, vehicle: VehicleConstraints) -> nx.Graph:
    """Build undirected graph; edges narrower than vehicle width are excluded."""
    g = nx.Graph()
    for _, row in roads.iterrows():
        geom: LineString = row.geometry
        if geom is None or geom.is_empty:
            continue
        width = float(row.get("width_m", 99))
        slope = float(row.get("max_slope_pct", 0))
        if width < vehicle.width_m:
            continue
        if slope > vehicle.max_slope_pct:
            continue

        coords = list(geom.coords)
        u = _node_id(coords[0])
        v = _node_id(coords[-1])
        g.add_node(u, x=coords[0][0], y=coords[0][1])
        g.add_node(v, x=coords[-1][0], y=coords[-1][1])

        length = float(row.get("length_m") or geom.length)
        # Prefer wider, flatter roads via soft cost penalty
        cost = length * (1.0 + max(0.0, vehicle.width_m / width - 0.5) * 0.2)
        cost *= 1.0 + max(0.0, slope - 3.0) * 0.05

        g.add_edge(
            u,
            v,
            weight=cost,
            length_m=length,
            road_id=row.get("id"),
            name=row.get("name"),
            width_m=width,
            max_slope_pct=slope,
            highway=row.get("highway"),
            geometry=geom,
        )
    return g


def _nearest_node(g: nx.Graph, lon: float, lat: float) -> str:
    point = Point(lon, lat)
    best_node = None
    best_dist = float("inf")
    for nid, data in g.nodes(data=True):
        d = point.distance(Point(data["x"], data["y"]))
        if d < best_dist:
            best_dist = d
            best_node = nid
    if best_node is None:
        raise ValueError("Road graph is empty for the given vehicle constraints.")
    return best_node


def find_route(
    start: dict[str, float],
    end: dict[str, float],
    vehicle: VehicleConstraints,
) -> dict[str, Any]:
    roads = load_roads()
    graph = build_graph(roads, vehicle)
    if graph.number_of_edges() == 0:
        raise ValueError(
            "No traversable roads for these vehicle constraints. "
            "Try reducing width or increasing max slope."
        )

    src = _nearest_node(graph, start["lon"], start["lat"])
    dst = _nearest_node(graph, end["lon"], end["lat"])

    try:
        path_nodes = nx.shortest_path(graph, src, dst, weight="weight")
    except nx.NetworkXNoPath as exc:
        raise ValueError(
            "No path found between start and destination under current constraints."
        ) from exc

    segments: list[dict[str, Any]] = []
    line_parts: list[LineString] = []
    total_m = 0.0
    min_width = float("inf")
    max_slope = 0.0

    for a, b in zip(path_nodes[:-1], path_nodes[1:]):
        edge = graph.edges[a, b]
        geom: LineString = edge["geometry"]
        # Ensure direction follows path
        ax, ay = graph.nodes[a]["x"], graph.nodes[a]["y"]
        if Point(geom.coords[0]).distance(Point(ax, ay)) > Point(geom.coords[-1]).distance(
            Point(ax, ay)
        ):
            geom = LineString(list(geom.coords)[::-1])

        line_parts.append(geom)
        length = float(edge["length_m"])
        total_m += length
        min_width = min(min_width, float(edge["width_m"]))
        max_slope = max(max_slope, float(edge["max_slope_pct"]))
        segments.append(
            {
                "road_id": edge.get("road_id"),
                "name": edge.get("name"),
                "highway": edge.get("highway"),
                "width_m": edge.get("width_m"),
                "max_slope_pct": edge.get("max_slope_pct"),
                "length_m": round(length, 1),
            }
        )

    route_line = unary_union(line_parts)
    if route_line.geom_type == "MultiLineString":
        # Flatten for a continuous display geometry
        coords = []
        for part in route_line.geoms:
            coords.extend(list(part.coords))
        route_geom = LineString(coords)
    else:
        route_geom = route_line

    narrow = [
        s
        for s in segments
        if float(s["width_m"]) < vehicle.width_m + 1.5  # tight relative to vehicle
    ]

    return {
        "route": {
            "type": "Feature",
            "properties": {
                "distance_km": round(total_m / 1000.0, 2),
                "segment_count": len(segments),
                "min_width_m": round(min_width, 2) if min_width != float("inf") else None,
                "max_slope_pct": round(max_slope, 2),
            },
            "geometry": mapping(route_geom),
        },
        "segments": segments,
        "narrow_segments": narrow,
        "snapped_start": {
            "lon": graph.nodes[src]["x"],
            "lat": graph.nodes[src]["y"],
        },
        "snapped_end": {
            "lon": graph.nodes[dst]["x"],
            "lat": graph.nodes[dst]["y"],
        },
        "route_geometry": route_geom,
    }


def roads_near_route(route_geom: LineString, buffer_deg: float = 0.01) -> gpd.GeoDataFrame:
    roads = load_roads()
    return roads[roads.intersects(route_geom.buffer(buffer_deg))].copy()


def snap_hint(lon: float, lat: float) -> dict[str, Any]:
    """Return nearest road endpoint for UI feedback."""
    roads = load_roads()
    point = Point(lon, lat)
    union = unary_union(roads.geometry)
    nearest = nearest_points(point, union)[1]
    return {"lon": nearest.x, "lat": nearest.y}
