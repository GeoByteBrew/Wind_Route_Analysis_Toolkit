"""Export analysis results as CSV and PDF."""

from __future__ import annotations

import base64
import csv
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"


def _ensure_outputs() -> Path:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    return OUTPUTS


def _sorted_obstacle_features(result: dict[str, Any]) -> list[dict[str, Any]]:
    feats = list(result.get("obstacles", {}).get("features", []))
    feats.sort(key=lambda f: (f["properties"].get("km") is None, f["properties"].get("km") or 0))
    return feats


def export_csv(result: dict[str, Any], export_id: str | None = None) -> Path:
    out = _ensure_outputs()
    export_id = export_id or uuid.uuid4().hex[:10]
    path = out / f"report_{export_id}.csv"

    rows: list[dict[str, Any]] = []
    for feature in _sorted_obstacle_features(result):
        props = feature["properties"]
        rows.append(
            {
                "km": props.get("km"),
                "km_label": props.get("km_label"),
                "type": props.get("type") or "obstacle",
                "name": props.get("name"),
                "value": props.get("value"),
                "severity": props.get("severity"),
                "bypass_possible": props.get("bypass_possible"),
                "status": props.get("status"),
                "detail": props.get("detail") or "",
                "note": props.get("note") or "",
                "photo_attached": props.get("photo_attached"),
            }
        )

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "km",
                "km_label",
                "type",
                "name",
                "value",
                "severity",
                "bypass_possible",
                "status",
                "detail",
                "note",
                "photo_attached",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return path


def export_pdf(result: dict[str, Any], export_id: str | None = None) -> Path:
    out = _ensure_outputs()
    export_id = export_id or uuid.uuid4().hex[:10]
    path = out / f"report_{export_id}.pdf"

    summary = result.get("summary", {})
    vehicle = result.get("vehicle", {})
    checklist = result.get("checklist", [])
    profile = result.get("distance_profile", [])
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=8,
        textColor=colors.HexColor("#0f3d2e"),
    )
    body = styles["BodyText"]
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=10)

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm)
    story = []
    story.append(Paragraph("Route Analysis Toolkit — Route Report", title_style))
    story.append(
        Paragraph(
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
            f"Template: {summary.get('vehicle_template') or vehicle.get('template_label') or 'Custom'}",
            body,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>Summary</b>", styles["Heading2"]))
    story.append(
        Paragraph(
            f"Distance: <b>{summary.get('distance_km')} km</b> · "
            f"Feasibility: <b>{summary.get('feasibility')}</b> · "
            f"Conflicts: {summary.get('conflict_count', 0)} · "
            f"Cautions: {summary.get('caution_count', 0)} · "
            f"Obstacles: {summary.get('obstacle_count', 0)}",
            body,
        )
    )
    story.append(Spacer(1, 6))

    story.append(Paragraph("<b>Vehicle constraints</b>", styles["Heading2"]))
    story.append(
        Paragraph(
            f"{vehicle.get('template_label') or 'Custom'} · "
            f"Length {vehicle.get('length_m')} m · Width {vehicle.get('width_m')} m · "
            f"Height {vehicle.get('height_m')} m · Weight {vehicle.get('weight_t')} t · "
            f"Max slope {vehicle.get('max_slope_pct')}%",
            body,
        )
    )
    story.append(Spacer(1, 8))

    # Distance profile
    story.append(Paragraph("<b>Distance profile</b>", styles["Heading2"]))
    if profile:
        prof_data = [["Chainage", "Longitude", "Latitude"]]
        for p in profile:
            prof_data.append([p.get("km_label"), f"{p.get('lon'):.5f}", f"{p.get('lat'):.5f}"])
        prof_table = Table(prof_data, colWidths=[35 * mm, 50 * mm, 50 * mm])
        prof_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#245c42")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d4cc")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7f5")]),
                ]
            )
        )
        story.append(prof_table)
    else:
        story.append(Paragraph("No profile points.", body))
    story.append(Spacer(1, 10))

    # Issues in km order
    story.append(Paragraph("<b>Issues (km order)</b>", styles["Heading2"]))
    table_data = [["Km", "Type", "Name", "Sev.", "Bypass", "Status", "Detail"]]
    issue_feats = [
        f
        for f in _sorted_obstacle_features(result)
        if f["properties"].get("status") in ("conflict", "caution", "off_route")
    ]
    for feature in issue_feats:
        p = feature["properties"]
        table_data.append(
            [
                str(p.get("km_label") or "—"),
                str(p.get("type") or "").replace("_", " "),
                str(p.get("name") or "")[:28],
                str(p.get("severity") or ""),
                "yes" if p.get("bypass_possible") else "no",
                str(p.get("status") or ""),
                Paragraph(str(p.get("detail") or "")[:120], small),
            ]
        )
    if len(table_data) == 1:
        table_data.append(["—", "—", "No issues", "—", "—", "ok", "Route looks feasible"])

    table = Table(table_data, colWidths=[22 * mm, 24 * mm, 32 * mm, 16 * mm, 16 * mm, 18 * mm, 48 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f3d2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d4cc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7f5")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 10))

    # Checklist
    story.append(Paragraph("<b>Field checklist</b>", styles["Heading2"]))
    check_data = [["State", "Item", "Detail"]]
    for item in checklist:
        mark = "✓" if item.get("state") == "done" else "☐"
        check_data.append([mark, item.get("item", ""), item.get("detail", "")])
    check_table = Table(check_data, colWidths=[14 * mm, 70 * mm, 90 * mm])
    check_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#245c42")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5d4cc")),
            ]
        )
    )
    story.append(check_table)
    story.append(Spacer(1, 10))

    # Notes + optional first photo
    notes = [
        f["properties"]
        for f in _sorted_obstacle_features(result)
        if f["properties"].get("note") or f["properties"].get("photo_data_url")
    ]
    if notes:
        story.append(Paragraph("<b>Notes & photos</b>", styles["Heading2"]))
        for p in notes[:8]:
            story.append(
                Paragraph(
                    f"<b>{p.get('km_label')} — {p.get('name')}</b>: {p.get('note') or '—'}",
                    body,
                )
            )
            data_url = p.get("photo_data_url") or ""
            if data_url.startswith("data:image") and "," in data_url:
                try:
                    b64 = data_url.split(",", 1)[1]
                    raw = base64.b64decode(b64)
                    img = Image(io.BytesIO(raw))
                    max_w = 70 * mm
                    scale = max_w / float(img.imageWidth)
                    img.drawWidth = max_w
                    img.drawHeight = float(img.imageHeight) * scale
                    story.append(img)
                except Exception:
                    story.append(Paragraph("<i>Photo attached (could not embed)</i>", small))
            story.append(Spacer(1, 4))

    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "<i>Note: analysis uses user-provided geometry and obstacles with route snap/chainage. "
            "Not for certified operational transport planning.</i>",
            body,
        )
    )

    doc.build(story)
    return path
