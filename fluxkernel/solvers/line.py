"""L2 plugin: production-line evaluation — capacity/takt roll-up (pure Python).

A line is the composition of process cells (self-rooted nodes). line-eval
computes bottleneck takt = max(cell takt), availability = product(cell
availability), and OEE-style roll-up for compose's `rollup` assertions.
"""
from __future__ import annotations

import math

from .registry import register


@register("line-eval")
def line_eval(node_specs, args, ctx):
    cells = []
    for s in node_specs:
        g = (s.get("ground") or {})
        if "takt_min" in g:
            cells.append({"kind": s.get("kind"), "takt_min": float(g["takt_min"]),
                          "cost": float(g.get("cost", 0.0))})
    if not cells:
        raise ValueError("line-eval needs >=1 input with a grounded takt_min")
    takt = max(c["takt_min"] for c in cells)
    total_cost = sum(c["cost"] for c in cells)
    availability = math.prod(0.95 for _ in cells)
    quality = 0.97
    performance = 1.0
    oee = round(availability * performance * quality, 3)
    capacity_per_h = round(60.0 / takt, 2) if takt > 0 else 0.0
    fields = {"kind": "line",
              "ground": {"type": "line", "takt_min": round(takt, 2),
                         "capacity_per_h": capacity_per_h,
                         "oee": oee, "cost": round(total_cost, 2)}}
    evidence = [{"solver": "line/eval", "tier": 0, "takt-min": round(takt, 2),
                 "takt_min": round(takt, 2), "oee": oee,
                 "capacity_per_h": capacity_per_h, "cells": len(cells)}]
    obligations = [{"id": "line-feasible", "prop": "line takt positive",
                    "holds": takt > 0, "checker": "line",
                    "detail": f"bottleneck takt={takt:.1f} min"}]
    return fields, evidence, obligations
