"""Shared vehicle constraint model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VehicleConstraints:
    length_m: float
    width_m: float
    height_m: float
    weight_t: float
    max_slope_pct: float = 8.0
