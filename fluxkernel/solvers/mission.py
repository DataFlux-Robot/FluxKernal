"""L2 plugin: low-fidelity mission analysis (Breguet-class, tier-0 evidence).

The first collapse step of the aircraft walkthrough (impl plan §9 step 2):
an Intent becomes a point-mass model whose parameters are HOLES (sorry),
then mission-analysis grounds them enough for a tier-0 range check.
"""
from __future__ import annotations

import math

from .registry import register


@register("point-mass-model")
def point_mass_model(node_specs, args, ctx):
    """Intent -> point-mass parametric model; all key params stay as holes.
    Hole names match the param_bounds keys so lint rule L6 passes.
    sfc is specific fuel consumption in kg/(N·s) (SI: 0.03 kg/(N·h) ≈ 8.3e-6)."""
    spec = node_specs[0].get("spec", {}) if node_specs else {}
    fields = {"kind": "point-mass",
              "params": {"mtow": ["param", "mtow"], "ff": ["param", "ff"],
                         "ld": ["param", "ld"], "sfc": ["param", "sfc"],
                         "v": ["param", "v"]},
              "spec": {**spec, "param_bounds": {
                  "mtow": {">=": 500, "<=": 8000},
                  "ff": {">=": 0.12, "<=": 0.45},
                  "ld": {">=": 8, "<=": 22},
                  "sfc": {">=": 0.015 / 3600, "<=": 0.08 / 3600},
                  "v": {">=": 40, "<=": 180}}}}
    evidence = [{"solver": "mission/point-mass", "tier": 0,
                 "holes": ["mtow", "ff", "ld", "sfc", "v"]}]
    obligations = [{"id": "model-formed", "prop": "point-mass model with bounded holes",
                    "holds": True, "checker": "mission", "detail": ""}]
    return fields, evidence, obligations


@register("mission-analysis")
def mission_analysis(node_specs, args, ctx):
    """Breguet range R = V·(L/D)·ln(W0/W1)/(g·sfc), sfc in kg/(N·s), R in km.
    Holes fall back to param_bounds midpoints. The range requirement is read
    from BOTH goals and guarantees bounds (whichever declares range_km)."""
    p = dict(node_specs[0].get("params", {})) if node_specs else {}
    pb = (node_specs[0].get("spec", {}) or {}).get("param_bounds", {}) if node_specs else {}

    ov = args.get("overrides") or {}

    def val(key, default):
        if key in ov:
            return float(ov[key])
        v = p.get(key, default)
        if isinstance(v, (list, tuple)) and v and v[0] == "param":
            b = pb.get(key) or {}
            lo = b.get(">=", default * 0.5) if isinstance(b, dict) else default * 0.5
            hi = b.get("<=", default * 1.5) if isinstance(b, dict) else default * 1.5
            return (lo + hi) / 2.0
        return float(v)

    mtow = val("mtow", 2000.0)
    ff = val("ff", 0.25)
    ld = val("ld", 15.0)
    sfc = val("sfc", 0.03 / 3600)      # kg/(N·s)
    v = val("v", 90.0)
    g = 9.81
    w1 = mtow * (1.0 - ff)
    range_km = (v * ld * math.log(mtow / w1) / (g * sfc) / 1000.0) if w1 > 0 else 0.0
    req = None
    spec = node_specs[0].get("spec", {}) if node_specs else {}
    for slot in ("goals", "guarantees", "assumes"):
        for e in spec.get(slot, []) or []:
            for q, b in (e.get("bounds") or {}).items():
                if q != "range_km" or req is not None:
                    continue
                try:
                    lo = float(b[">="]) if isinstance(b, dict) and ">=" in b \
                        else (float(b["value"]) if isinstance(b, dict) and
                              b.get("op") in (">=", ">") else None)
                except (TypeError, ValueError):
                    lo = None
                if lo is not None:
                    req = lo
    margin = (range_km - req) if req is not None else range_km
    fidelity = int(args.get("fidelity", 0))
    evidence = [{"solver": "mission/breguet", "tier": fidelity,
                 "range_km": round(range_km, 1), "range-margin-km": round(margin, 1),
                 "ld_ratio": ld, "fuel_frac": ff, "mtow_kg": mtow, "cruise_ms": v}]
    obligations = [{"id": "range-computed", "prop": "Breguet range computed",
                    "holds": range_km > 0, "checker": "mission",
                    "detail": f"R={range_km:.1f} km"}]
    return {}, evidence, obligations
