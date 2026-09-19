"""Adapter: minimal .flux projection (BODY/MIND facets, FLUXmeme stance).

FluxKernel only PROJECTS into the asset world — it does not own it. Each
promoted node becomes a self-rooted record with a BODY payload (ground
blobs / projections) or MIND payload (policy/params/plant_ref), digests
preserved so cross-references remain content-addressed.
"""
from __future__ import annotations

import json
from pathlib import Path


def export_flux(engine, out_file: Path) -> Path:
    records = []
    for node_d, p in engine.dag.iter_nodes():
        if engine.dag.node_state(node_d) != "promoted":
            continue
        facet = p.get("facet", "BODY")
        records.append({
            "digest": node_d,
            "facet": facet,
            "kind": p.get("kind"),
            "BODY": {"ground": p.get("ground")} if facet == "BODY" else None,
            "MIND": {"params": p.get("params"),
                     "plant_ref": (p.get("spec") or {}).get("plant_ref")}
            if facet == "MIND" else None,
        })
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
    return out_file
