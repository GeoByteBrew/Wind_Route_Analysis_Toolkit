"""Parse uploaded route files (GeoJSON, KML, KMZ, GPX) into a LineString feature."""

from __future__ import annotations

import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

import numpy as np
from shapely.geometry import LineString, MultiLineString, mapping, shape
from shapely.ops import linemerge, unary_union


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def line_length_m(geom: LineString | MultiLineString) -> float:
    if geom.geom_type == "MultiLineString":
        return sum(line_length_m(g) for g in geom.geoms)
    coords = list(geom.coords)
    total = 0.0
    for i in range(len(coords) - 1):
        total += _haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
    return total


def _as_linestring(geom) -> LineString | MultiLineString | None:
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "LineString":
        return geom
    if geom.geom_type == "MultiLineString":
        return linemerge(geom)
    if geom.geom_type == "GeometryCollection":
        lines = [g for g in geom.geoms if g.geom_type in ("LineString", "MultiLineString")]
        if not lines:
            return None
        return _as_linestring(unary_union(lines))
    return None


def _from_geojson(raw: bytes | str) -> LineString | MultiLineString:
    data = json.loads(raw)
    geoms = []
    if data.get("type") == "FeatureCollection":
        for feat in data.get("features", []):
            g = shape(feat["geometry"]) if feat.get("geometry") else None
            line = _as_linestring(g)
            if line is not None:
                geoms.append(line)
    elif data.get("type") == "Feature":
        line = _as_linestring(shape(data["geometry"]))
        if line is not None:
            geoms.append(line)
    else:
        line = _as_linestring(shape(data))
        if line is not None:
            geoms.append(line)

    if not geoms:
        raise ValueError("No LineString geometry found in GeoJSON.")
    if len(geoms) == 1:
        return geoms[0]
    return _as_linestring(
        MultiLineString(
            [g for geom in geoms for g in (geom.geoms if geom.geom_type == "MultiLineString" else [geom])]
        )
    ) or geoms[0]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_coord_text(text: str) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for token in re.split(r"\s+", text.strip()):
        if not token:
            continue
        parts = token.split(",")
        if len(parts) < 2:
            continue
        lon, lat = float(parts[0]), float(parts[1])
        coords.append((lon, lat))
    return coords


def _from_kml(raw: bytes | str) -> LineString | MultiLineString:
    root = ET.fromstring(raw)
    lines: list[LineString] = []
    for elem in root.iter():
        if _local(elem.tag) != "LineString":
            continue
        for child in elem:
            if _local(child.tag) == "coordinates" and child.text:
                coords = _parse_coord_text(child.text)
                if len(coords) >= 2:
                    lines.append(LineString(coords))
    if not lines:
        raise ValueError("No LineString found in KML/KMZ. Export a path/line from My Maps.")
    if len(lines) == 1:
        return lines[0]
    return _as_linestring(MultiLineString(lines)) or lines[0]


def _from_kmz(raw: bytes) -> LineString | MultiLineString:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("KMZ archive contains no KML file.")
            # Prefer doc.kml (Google Earth / My Maps convention)
            preferred = next((n for n in kml_names if n.lower().endswith("doc.kml")), kml_names[0])
            return _from_kml(zf.read(preferred))
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid KMZ file (not a valid zip archive).") from exc


def _from_gpx(raw: bytes | str) -> LineString | MultiLineString:
    root = ET.fromstring(raw)
    tracks: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    for elem in root.iter():
        tag = _local(elem.tag)
        if tag in ("trkseg", "rte"):
            if current:
                tracks.append(current)
                current = []
        if tag in ("trkpt", "rtept"):
            lon = elem.attrib.get("lon")
            lat = elem.attrib.get("lat")
            if lon is not None and lat is not None:
                current.append((float(lon), float(lat)))
    if current:
        tracks.append(current)

    lines = [LineString(c) for c in tracks if len(c) >= 2]
    if not lines:
        raise ValueError("No track/route points found in GPX.")
    if len(lines) == 1:
        return lines[0]
    return _as_linestring(MultiLineString(lines)) or lines[0]


def parse_route_file(filename: str, content: bytes) -> dict[str, Any]:
    name = (filename or "route").lower()
    if name.endswith((".geojson", ".json")):
        geom = _from_geojson(content)
        source_format = "geojson"
    elif name.endswith(".kmz"):
        geom = _from_kmz(content)
        source_format = "kmz"
    elif name.endswith(".kml"):
        geom = _from_kml(content)
        source_format = "kml"
    elif name.endswith(".gpx"):
        geom = _from_gpx(content)
        source_format = "gpx"
    else:
        # Try KMZ (zip) then GeoJSON then KML
        try:
            geom = _from_kmz(content)
            source_format = "kmz"
        except Exception:
            try:
                geom = _from_geojson(content)
                source_format = "geojson"
            except Exception:
                try:
                    geom = _from_kml(content)
                    source_format = "kml"
                except Exception as exc:
                    raise ValueError(
                        "Unsupported file. Upload GeoJSON, KML, KMZ (My Maps), or GPX."
                    ) from exc

    if geom.geom_type == "MultiLineString":
        coords = []
        for part in geom.geoms:
            coords.extend(list(part.coords))
        display = LineString(coords) if len(coords) >= 2 else list(geom.geoms)[0]
    else:
        display = geom

    length_m = line_length_m(geom)
    start = list(display.coords)[0]
    end = list(display.coords)[-1]

    feature = {
        "type": "Feature",
        "properties": {
            "name": filename,
            "source_format": source_format,
            "distance_km": round(length_m / 1000.0, 2),
            "vertex_count": len(list(display.coords)),
        },
        "geometry": mapping(display),
    }

    return {
        "route": feature,
        "start": {"lon": start[0], "lat": start[1]},
        "end": {"lon": end[0], "lat": end[1]},
        "distance_km": feature["properties"]["distance_km"],
        "source_format": source_format,
    }
