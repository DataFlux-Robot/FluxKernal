"""L2 plugin: process planning — Part -> ordered fabrication ops (rule lib).

`manufacture` pivots a Part goal into a Process family (impl plan §7). This
plugin derives a rule-based op sequence with resource estimates from the
part's evaluated geometry (volume / bbox), so process trees carry their own
evidence instead of hand-waving.
"""
from __future__ import annotations

from .registry import register

# rule library: material -> (op, minutes per 1000 mm^3, cost per op)
_RULES = {
    "aluminum": [("stock", 2.0, 8.0), ("milling-3axis", 1.4, 22.0),
                 ("milling-5axis", 2.2, 45.0), ("inspection", 3.0, 12.0)],
    "steel": [("stock", 3.0, 10.0), ("milling-3axis", 2.6, 30.0),
              ("heat-treat", 40.0, 35.0), ("inspection", 4.0, 12.0)],
    "pla": [("stock", 1.0, 4.0), ("fdm-print", 8.0, 6.0), ("inspection", 2.0, 8.0)],
    "abs": [("stock", 1.0, 4.0), ("fdm-print", 8.0, 6.0), ("inspection", 2.0, 8.0)],
}
_DEFAULT = [("stock", 2.0, 8.0), ("milling-3axis", 1.8, 25.0), ("inspection", 3.0, 12.0)]


@register("process-plan")
def process_plan(node_specs, args, ctx):
    part = node_specs[0] if node_specs else {}
    ground = part.get("ground") or {}
    volume = float(ground.get("volume_mm3", 1000.0))
    material = str(ground.get("material", ""))
    into = args.get("into") or []
    ops_rule = _RULES.get(material, _DEFAULT)
    if into:
        # caller-declared op sequence; estimate by matching rule rates
        rates = {op: (t, c) for op, t, c in ops_rule}
        ops = [(op,) + rates.get(op, (5.0, 20.0)) for op in into]
    else:
        ops = list(ops_rule)
    takt_min = sum(t for _, t, _ in ops) * (volume / 1000.0) ** 0.5 + 1.0
    cost = sum(c for _, _, c in ops)
    scale = (volume / 1000.0) ** 0.5
    op_details = [{"op": op, "takt_min": round(t * scale, 2), "cost": c}
                  for op, t, c in ops]
    fields = {"kind": "process-plan",
              "ground": {"type": "process", "ops": [op for op, _, _ in ops],
                         "op_details": op_details,
                         "takt_min": round(takt_min, 2), "cost": round(cost, 2)},
              "spec": {"guarantees": [{"id": "pp1", "stmt": "plan takt",
                                       "bounds": {"takt_min": ["<=", max(60.0, takt_min * 1.2)]}}]}}
    evidence = [{"solver": "process/rules", "tier": 0, "material": material,
                 "volume_mm3": volume, "takt_min": round(takt_min, 2),
                 "cost": round(cost, 2), "ops": [op for op, _, _ in ops]}]
    obligations = [{"id": "process-feasible", "prop": "op sequence non-empty and finite",
                    "holds": bool(ops) and takt_min > 0, "checker": "process",
                    "detail": f"{len(ops)} ops, takt={takt_min:.1f} min"}]
    return fields, evidence, obligations
