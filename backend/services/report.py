"""Export analysis results as CSV and PDF."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"


def _ensure_outputs() -> Path:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    return OUTPUTS


def export_csv(result: dict[str, Any], export_id: str | None = None) -> Path:
    out = _ensure_outputs()
    export_id = export_id or uuid.uuid4().hex[:10]
    path = out / f"report_{export_id}.csv"

    rows: list[dict[str, Any]] = []
    for feature in result.get("bridges", {}).get("features", []):
        props = feature["properties"]
        if props.get("status") != "conflict":
            continue
        rows.append(
            {
                "type": "bridge_clearance",
                "name": props.get("name"),
                "detail": f"clearance={props.get('clearance_m')}m < height={props.get('vehicle_height_m')}m",
                "severity": props.get("status"),
            }
        )

    for seg in result.get("narrow_roads", []):
        rows.append(
            {
                "type": "narrow_road",
                "name": seg.get("name"),
                "detail": f"width={seg.get('width_m')}m",
                "severity": "caution",
            }
        )

    for feature in result.get("slopes", {}).get("features", []):
        props = feature["properties"]
        if props.get("status") != "steep":
            continue
        rows.append(
            {
                "type": "steep_slope",
                "name": props.get("name"),
                "detail": f"max_slope={props.get('max_slope_pct')}%",
                "severity": props.get("status"),
            }
        )

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["type", "name", "detail", "severity"])
        writer.writeheader()
        writer.writerows(rows)

    return path


def export_pdf(result: dict[str, Any], export_id: str | None = None) -> Path:
    out = _ensure_outputs()
    export_id = export_id or uuid.uuid4().hex[:10]
    path = out / f"report_{export_id}.pdf"

    summary = result.get("summary", {})
    vehicle = result.get("vehicle", {})
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=8,
        textColor=colors.HexColor("#0f3d2e"),
    )
    body = styles["BodyText"]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm)
    story = []
    story.append(Paragraph("Wind Route Analysis Toolkit — Route Report", title_style))
    story.append(
        Paragraph(
            f"Region: Hérault (Occitanie, France) · Generated: "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            body,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>Summary</b>", styles["Heading2"]))
    story.append(
        Paragraph(
            f"Distance: {summary.get('distance_km')} km · "
            f"Feasibility: <b>{summary.get('feasibility')}</b> · "
            f"Issues: {summary.get('issues_count')}",
            body,
        )
    )
    story.append(Spacer(1, 6))

    story.append(Paragraph("<b>Vehicle constraints</b>", styles["Heading2"]))
    story.append(
        Paragraph(
            f"Length {vehicle.get('length_m')} m · Width {vehicle.get('width_m')} m · "
            f"Height {vehicle.get('height_m')} m · Weight {vehicle.get('weight_t')} t · "
            f"Max slope {vehicle.get('max_slope_pct')}%",
            body,
        )
    )
    story.append(Spacer(1, 8))

    table_data = [["Issue type", "Name", "Detail"]]
    for feature in result.get("bridges", {}).get("features", []):
        p = feature["properties"]
        if p.get("status") == "conflict":
            table_data.append(
                [
                    "Low bridge",
                    str(p.get("name")),
                    f"{p.get('clearance_m')} m clearance",
                ]
            )
    for seg in result.get("narrow_roads", []):
        table_data.append(
            ["Narrow road", str(seg.get("name")), f"{seg.get('width_m')} m width"]
        )
    for feature in result.get("slopes", {}).get("features", []):
        p = feature["properties"]
        if p.get("status") == "steep":
            table_data.append(
                ["Steep slope", str(p.get("name")), f"{p.get('max_slope_pct')} %"]
            )

    if len(table_data) == 1:
        table_data.append(["—", "No blocking issues", "Route looks feasible on sample data"])

    table = Table(table_data, colWidths=[35 * mm, 60 * mm, 70 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f3d2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5d4cc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7f5")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(Paragraph("<b>Constraint issues</b>", styles["Heading2"]))
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "<i>Demo note: analysis uses synthetic sample geospatial data for Hérault. "
            "Not for operational transport planning.</i>",
            body,
        )
    )

    doc.build(story)
    return path
