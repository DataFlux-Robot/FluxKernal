"""Adapter: MechanogenesisBench trace export (`fk trace --out <dir>`).

Package layout (impl plan §10), field names aligned with the bench canonical
IR (digest / lineage / resources / evidence_tier):
  trace.json        all edges: digest/op/inputs/output/state/resources
  certificates/     one JSON per edge
  chain.json        shared-digest cross-generation links (o_i = t_{i+1})
  summary.json      vector scoring: time/cost/material/energy/failures

The bench verifier checks hashes, lineage, budgets, evidence-tier ceilings
and promotion predicates INDEPENDENTLY — this package only exports facts.
"""
from __future__ import annotations

import json
from pathlib import Path


def export_trace(engine, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    (out_dir / "certificates").mkdir(parents=True, exist_ok=True)

    edges = []
    resources_sum = {"time_s": 0.0, "energy_j": 0.0, "material_g": 0.0,
                     "cost": 0.0, "human_s": 0.0, "failures": 0}
    tiers = []
    for edge_d, e in engine.dag.iter_edges():
        edges.append({
            "digest": edge_d,
            "op": e.get("op"),
            "inputs": e.get("inputs", []),
            "output": e.get("output", ""),
            "transform": e.get("transform", {}),
            "state": e.get("state"),
            "resources": e.get("resources", {}),
            "coverage": e.get("coverage", {}),
            "lineage": engine.dag.lineage_of(e.get("output", "")) or "",
        })
        for k in resources_sum:
            resources_sum[k] += float(e.get("resources", {}).get(k, 0) or 0)
        for ev in e.get("certificate", {}).get("evidence", []):
            if isinstance(ev, dict) and "tier" in ev:
                tiers.append(int(ev["tier"]))
        cert = {"edge": edge_d,
                "certificate": e.get("certificate", {}),
                "reason": e.get("reason", "")}
        (out_dir / "certificates" / (edge_d.replace(":", "_") + ".json")) \
            .write_text(json.dumps(cert, indent=1, sort_keys=True, ensure_ascii=False),
                        encoding="utf-8")

    # cross-generation links: any node that is the OUTPUT of one edge and an
    # INPUT of a different edge — the PRSI o_i = t_{i+1} chains
    produced_by = {e["output"]: e["digest"] for e in edges}
    chains = []
    for e in edges:
        for i in e["inputs"]:
            if i in produced_by and produced_by[i] != e["digest"]:
                chains.append({"from_edge": produced_by[i], "to_edge": e["digest"],
                               "shared_node": i})

    (out_dir / "trace.json").write_text(
        json.dumps({"schema": "fk1-trace", "edges": edges}, indent=1, sort_keys=True,
                   ensure_ascii=False), encoding="utf-8")
    (out_dir / "chain.json").write_text(
        json.dumps({"schema": "fk1-chain", "links": chains}, indent=1, sort_keys=True,
                   ensure_ascii=False), encoding="utf-8")
    summary = {
        "schema": "fk1-summary",
        "vector_scoring": resources_sum,      # scalar leaderboard policy is ABOVE the kernel
        "evidence_tiers": {"min": min(tiers) if tiers else None,
                           "max": max(tiers) if tiers else None,
                           "count": len(tiers)},
        "edge_counts": _state_counts(edges),
        "node_count": len(engine.dag.iter_nodes()),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False),
        encoding="utf-8")
    return out_dir


def _state_counts(edges) -> dict:
    out: dict[str, int] = {}
    for e in edges:
        out[e["state"]] = out.get(e["state"], 0) + 1
    return out
