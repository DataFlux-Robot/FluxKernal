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
    """Intent -> point-mass parametric model; all key params stay as holes."""
    spec = node_specs[0].get("spec", {}) if node_specs else {}
    fields = {"kind": "point-mass",
              "params": {"mtow_kg": ["param", "mtow"],
                         "fuel_frac": ["param", "ff"],
                         "ld_ratio": ["param", "ld"],
                         "sfc_kg_n_h": ["param", "sfc"],
                         "cruise_ms": ["param", "v"]},
              "spec": {**spec, "param_bounds": {
                  "mtow": {">=": 500, "<=": 8000},
                  "ff": {">=": 0.12, "<=": 0.45},
                  "ld": {">=": 8, "<=": 22},
                  "sfc": {">=": 0.015 / 3.6, "<=": 0.08 / 3.6},
                  "v": {">=": 40, "<=": 180}}}}
    evidence = [{"solver": "mission/point-mass", "tier": 0,
                 "holes": ["mtow", "ff", "ld", "sfc", "v"]}]
    obligations = [{"id": "model-formed", "prop": "point-mass model with bounded holes",
                    "holds": True, "checker": "mission", "detail": ""}]
    return fields, evidence, obligations


@register("mission-analysis")
def mission_analysis(node_specs, args, ctx):
    """Breguet range from current params (holes fall back to param_bounds
    midpoints). Evidence carries range-km and range-margin-km for `expect`."""
    p = dict(node_specs[0].get("params", {})) if node_specs else {}
    pb = (node_specs[0].get("spec", {}) or {}).get("param_bounds", {}) if node_specs else {}

    def val(name, default):
        v = p.get(name, default)
        if isinstance(v, (list, tuple)) and v and v[0] == "param":
            b = pb.get(v[1] if len(v) > 1 else name) or pb.get(name) or {}
            lo = b.get(">=", default * 0.5) if isinstance(b, dict) else default * 0.5
            hi = b.get("<=", default * 1.5) if isinstance(b, dict) else default * 1.5
            return (lo + hi) / 2.0
        return float(v)

    mtow = val("mtow_kg", 2000.0)
    ff = val("fuel_frac", 0.25)
    ld = val("ld_ratio", 15.0)
    sfc = val("sfc_kg_n_h", 0.03 / 3.6)     # kg/(N·s)
    v = val("cruise_ms", 90.0)
    g = 9.81
    w1 = mtow * (1.0 - ff)
    range_km = (v / (g * sfc)) * ld * math.log(mtow / w1) / 1000.0 if w1 > 0 else 0.0
    req = None
    for e in (node_specs[0].get("spec", {}) or {}).get("goals", []) if node_specs else []:
        for q, b in (e.get("bounds") or {}).items():
            if q == "range_km" and isinstance(b, dict):
                req = b.get(">=")
    margin = (range_km - req) if req is not None else range_km
    fidelity = int(args.get("fidelity", 0))
    evidence = [{"solver": "mission/breguet", "tier": fidelity,
                 "range_km": round(range_km, 1), "range-margin-km": round(margin, 1),
                 "ld_ratio": ld, "fuel_frac": ff, "mtow_kg": mtow, "cruise_ms": v}]
    obligations = [{"id": "range-computed", "prop": "Breguet range computed",
                    "holds": range_km > 0, "checker": "mission",
                    "detail": f"R={range_km:.1f} km"}]
    return {}, evidence, obligations
