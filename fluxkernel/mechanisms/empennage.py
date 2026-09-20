"""Mechanism: empennage — airfoil-section stabilizers (V1).

hstab: a small airfoil lofted spanwise (the same cyclic frame as the
wing skin).  fin: the same section lofted VERTICALLY — section chord
along local x, thickness along local y, loft axis local z = height;
rotZ90 maps chord->fore-aft, thickness->spanwise, height->up.
"""
from __future__ import annotations

import math

from .airfoil import naca4, loop_area

MARGIN = 1.3
N_PTS = 18


def layout(p: dict) -> dict:
    x0 = float(p.get("x0", 0.0))
    y0 = float(p.get("y0", 0.0))
    z0 = float(p.get("z0", 0.0))
    return {
        # hstab: airfoil in local XY (chord, thickness), loft local Z=span;
        # cyclic (1,1,1)120 -> chord fore-aft, thickness up, span spanwise
        "hstab": [[x0, y0, z0], [1, 1, 1, 120]],
        # fin: section in local XY (chord, thickness), loft local Z=height;
        # rotZ90 -> chord fore-aft, thickness spanwise, height up
        "fin": [[float(p.get("fin-x0", x0)), float(p.get("fin-y0", y0)),
                 float(p.get("fin-z0", z0))], [0, 0, 1, 90]],
    }


def profile(p: dict, part: str) -> dict:
    tc = float(p.get("tc", 0.10))
    chord = float(p.get("chord", 200.0))
    if part == "hstab":
        span = float(p.get("h-span", 600.0))
        sec = naca4(chord, tc, 0.0, N_PTS)
        return {"pts": sec, "thick": span, "material": "aluminum"}
    if part == "fin":
        h = float(p.get("fin-height", 300.0))
        sec = naca4(chord, tc, 0.0, N_PTS)
        return {"pts": sec, "thick": h, "material": "aluminum"}
    raise ValueError(f"empennage has no part {part!r}")


def mass_kg(p: dict, part: str) -> float:
    pr = profile(p, part)
    return loop_area(pr["pts"]) * pr["thick"] * 2.7e-3 / 1000.0


def generate(p: dict) -> dict:
    into = ["hstab", "fin"]
    parts, flow = {}, {}
    for name in into:
        pr = profile(p, name)
        parts[name] = pr
        m = math.ceil(mass_kg(p, name) * MARGIN)
        flow[name] = {
            "budget": {"mass_kg": ["<=", m]},
            "guarantees": [{"id": f"g-{name}",
                            "stmt": f"{name} stabilizes",
                            "bounds": {"mass_kg": ["<=", m]}}],
        }
    return {"into": into, "parts": parts, "flow_down": flow,
            "roles": {k: "Part" for k in into}}


def kinds_of(into: list) -> dict:
    return {k: "stabilizer" for k in into}


def assemble(p: dict) -> dict:
    return {"transform": {"name": "assemble",
                          "args": {"placements": [[0, 0, 0]] * 2}},
            "out_kind": "empennage-assembly"}
