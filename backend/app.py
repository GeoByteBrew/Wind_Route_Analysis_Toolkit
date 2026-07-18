"""FastAPI application for Wind Route Analysis Toolkit."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.services.bridges import check_bridges, load_bridges
from backend.services.report import export_csv, export_pdf
from backend.services.route import VehicleConstraints, find_route, load_roads
from backend.services.slope import check_slopes, load_slope_zones

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DATA = ROOT / "backend" / "data"
OUTPUTS = ROOT / "outputs"

app = FastAPI(
    title="Wind Route Analysis Toolkit",
    description=(
        "Python + Leaflet toolkit for analyzing oversized wind-turbine "
        "transport routes in Hérault (France) using open sample geospatial data."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LonLat(BaseModel):
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)


class VehicleInput(BaseModel):
    length_m: float = Field(45.0, gt=0, le=120)
    width_m: float = Field(4.5, gt=0, le=10)
    height_m: float = Field(4.2, gt=0, le=8)
    weight_t: float = Field(80.0, gt=0, le=500)
    max_slope_pct: float = Field(8.0, gt=0, le=25)


class AnalyzeRequest(BaseModel):
    start: LonLat
    end: LonLat
    vehicle: VehicleInput = Field(default_factory=VehicleInput)


def _feasibility(bridge_conflicts: int, steep_count: int, narrow_count: int) -> Literal["feasible", "caution", "blocked"]:
    if bridge_conflicts > 0:
        return "blocked"
    if steep_count > 0 or narrow_count > 0:
        return "caution"
    return "feasible"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "region": "Hérault", "center": "Montpellier"}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    roads = load_roads()
    bridges = load_bridges()
    slopes = load_slope_zones()
    return {
        "region": "Hérault",
        "country": "France",
        "center": {"lon": 3.55, "lat": 43.55},
        "bounds": [[43.25, 2.70], [43.85, 4.25]],
        "counts": {
            "roads": int(len(roads)),
            "bridges": int(len(bridges)),
            "slope_zones": int(len(slopes)),
        },
        "note": "Sample / synthetic geospatial data for demonstration.",
    }


@app.get("/api/layers/roads")
def layer_roads() -> dict[str, Any]:
    return load_roads().__geo_interface__


@app.get("/api/layers/bridges")
def layer_bridges() -> dict[str, Any]:
    return load_bridges().__geo_interface__


@app.get("/api/layers/slopes")
def layer_slopes() -> dict[str, Any]:
    return load_slope_zones().__geo_interface__


@app.get("/api/layers/places")
def layer_places() -> dict[str, Any]:
    path = DATA / "places.geojson"
    if not path.exists():
        raise HTTPException(404, "places.geojson missing — run scripts/generate_sample_data.py")
    import json

    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    vehicle = VehicleConstraints(
        length_m=req.vehicle.length_m,
        width_m=req.vehicle.width_m,
        height_m=req.vehicle.height_m,
        weight_t=req.vehicle.weight_t,
        max_slope_pct=req.vehicle.max_slope_pct,
    )

    try:
        route_result = find_route(
            start={"lon": req.start.lon, "lat": req.start.lat},
            end={"lon": req.end.lon, "lat": req.end.lat},
            vehicle=vehicle,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    route_geom = route_result["route_geometry"]
    bridges = check_bridges(route_geom, vehicle.height_m)
    slopes = check_slopes(route_geom, vehicle.max_slope_pct)

    # Narrow roads: segments already filtered by hard width; report near-miss widths
    narrow = route_result["narrow_segments"]
    # Also surface roads that exist in network but were excluded? Not needed for MVP.

    bridge_conflicts = bridges["conflict_count"]
    steep_count = slopes["steep_count"]
    feasibility = _feasibility(bridge_conflicts, steep_count, len(narrow))
    issues_count = bridge_conflicts + steep_count + len(narrow)

    payload: dict[str, Any] = {
        "route": route_result["route"],
        "segments": route_result["segments"],
        "narrow_roads": narrow,
        "bridges": bridges,
        "slopes": slopes,
        "snapped_start": route_result["snapped_start"],
        "snapped_end": route_result["snapped_end"],
        "vehicle": req.vehicle.model_dump(),
        "summary": {
            "distance_km": route_result["route"]["properties"]["distance_km"],
            "feasibility": feasibility,
            "issues_count": issues_count,
            "bridge_conflicts": bridge_conflicts,
            "steep_zones": steep_count,
            "narrow_segments": len(narrow),
            "region": "Hérault",
        },
    }

    export_id = uuid.uuid4().hex[:10]
    csv_path = export_csv(payload, export_id)
    pdf_path = export_pdf(payload, export_id)
    geojson_path = OUTPUTS / f"route_{export_id}.geojson"
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    import json

    geojson_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [payload["route"]]
                + bridges.get("features", [])
                + slopes.get("features", []),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    payload["downloads"] = {
        "geojson": f"/api/exports/{geojson_path.name}",
        "csv": f"/api/exports/{csv_path.name}",
        "pdf": f"/api/exports/{pdf_path.name}",
    }
    payload["export_id"] = export_id
    return payload


@app.get("/api/exports/{filename}")
def get_export(filename: str) -> FileResponse:
    # Prevent path traversal
    safe = Path(filename).name
    path = OUTPUTS / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Export not found")
    media = {
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".geojson": "application/geo+json",
        ".json": "application/json",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=safe)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
