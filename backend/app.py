"""FastAPI application for Route Analysis Toolkit."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.services.custom_analyze import analyze_custom_route
from backend.services.parse_route import parse_route_file
from backend.services.report import export_csv, export_pdf
from backend.services.vehicle import VehicleConstraints

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DATA = ROOT / "backend" / "data"
OUTPUTS = ROOT / "outputs"
SAMPLE_KMZ = DATA / "sample_montpellier_lyon.kmz"
SAMPLE_OBSTACLES = DATA / "sample_obstacles.json"

app = FastAPI(
    title="Route Analysis Toolkit",
    description=(
        "Python + Leaflet toolkit for analyzing oversized transport corridors: "
        "upload a route (GeoJSON/KML/KMZ/GPX), mark obstacles, export PDF/CSV reports. "
        "Includes a Montpellier → Lyon sample KMZ."
    ),
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class VehicleInput(BaseModel):
    length_m: float = Field(45.0, gt=0, le=120)
    width_m: float = Field(4.5, gt=0, le=10)
    height_m: float = Field(4.2, gt=0, le=8)
    weight_t: float = Field(80.0, gt=0, le=500)
    max_slope_pct: float = Field(8.0, gt=0, le=25)


class ObstacleInput(BaseModel):
    id: Optional[str] = None
    name: str = "Obstacle"
    type: Literal["low_bridge", "narrow_road", "weight_limit", "steep_slope", "note"] = "low_bridge"
    value: Optional[float] = None
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)
    note: Optional[str] = ""


class CustomAnalyzeRequest(BaseModel):
    route: dict[str, Any]
    obstacles: list[ObstacleInput] = Field(default_factory=list)
    vehicle: VehicleInput = Field(default_factory=VehicleInput)


def _write_exports(payload: dict[str, Any]) -> dict[str, str]:
    export_id = uuid.uuid4().hex[:10]
    csv_path = export_csv(payload, export_id)
    pdf_path = export_pdf(payload, export_id)
    geojson_path = OUTPUTS / f"route_{export_id}.geojson"
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    features = [payload["route"]]
    if payload.get("obstacles"):
        features.extend(payload["obstacles"].get("features", []))

    geojson_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )
    return {
        "geojson": f"/api/exports/{geojson_path.name}",
        "csv": f"/api/exports/{csv_path.name}",
        "pdf": f"/api/exports/{pdf_path.name}",
        "export_id": export_id,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.0", "modes": "upload"}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    return {
        "region": "France",
        "sample": "Montpellier → Lyon",
        "center": {"lon": 4.35, "lat": 44.70},
        "bounds": [[43.50, 3.70], [45.90, 5.00]],
        "accepted_formats": ["geojson", "kml", "kmz", "gpx"],
        "modes": ["upload"],
        "note": "Upload a corridor, mark obstacles, export a report.",
    }


@app.get("/api/sample/route")
def sample_route() -> dict[str, Any]:
    if not SAMPLE_KMZ.exists():
        raise HTTPException(404, "sample_montpellier_lyon.kmz missing")
    parsed = parse_route_file(SAMPLE_KMZ.name, SAMPLE_KMZ.read_bytes())
    obstacles = []
    if SAMPLE_OBSTACLES.exists():
        obstacles = json.loads(SAMPLE_OBSTACLES.read_text(encoding="utf-8"))
    parsed["obstacles"] = obstacles
    parsed["route"]["properties"]["name"] = "Montpellier → Lyon (sample KMZ)"
    return parsed


@app.post("/api/upload/route")
async def upload_route(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    if len(content) > 20_000_000:
        raise HTTPException(400, "File too large (max 20 MB)")
    try:
        return parse_route_file(file.filename or "route.kmz", content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not parse route file: {exc}") from exc


@app.post("/api/analyze")
@app.post("/api/analyze/custom")
def analyze_custom(req: CustomAnalyzeRequest) -> dict[str, Any]:
    vehicle = VehicleConstraints(
        length_m=req.vehicle.length_m,
        width_m=req.vehicle.width_m,
        height_m=req.vehicle.height_m,
        weight_t=req.vehicle.weight_t,
        max_slope_pct=req.vehicle.max_slope_pct,
    )
    try:
        result = analyze_custom_route(
            route_feature=req.route,
            obstacles=[o.model_dump() for o in req.obstacles],
            vehicle=vehicle,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    payload: dict[str, Any] = {
        **result,
        "vehicle": req.vehicle.model_dump(),
    }
    downloads = _write_exports(payload)
    payload["export_id"] = downloads.pop("export_id")
    payload["downloads"] = downloads
    return payload


@app.get("/api/exports/{filename}")
def get_export(filename: str) -> FileResponse:
    safe = Path(filename).name
    path = OUTPUTS / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Export not found")
    media = {
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".geojson": "application/geo+json",
        ".json": "application/json",
        ".kmz": "application/vnd.google-earth.kmz",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=safe)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
