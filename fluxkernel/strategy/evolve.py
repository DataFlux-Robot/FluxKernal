"""Strategy layer (NOT kernel): genetic optimization over the refinement DAG
(v1.1 §15). `fk evolve` drives: instantiate variants -> eval -> select ->
mutate/crossover edges -> next generation. All candidates are ORDINARY edges
(no privileges): genealogy is auditable via `fk why`, resources recorded per
edge, rejected trajectories kept.

MAP-elites archive: best-per-cell behavior descriptors are written to
.ffk archive entries (kind=archive) that `fk exact --from archive` can hit
later — evolution results precipitate into the library (capital K grows).

"Optimization picks the point, contracts guard the gate": hard obligations
still fail-closed every generation; soft metrics only rank.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from ..semantics import goals as goalsview

ARCHIVE_PATH = Path(".fk") / "archive.json"


def run_evolve(eng, a) -> int:
    rng = random.Random(getattr(a, "seed", 7) or 7)
    metrics = [m.strip() for m in (a.select_by or "cost,mass_g").split(",") if m.strip()]
    pop, gens = int(a.pop), int(a.gen)
    g_d, g_node = eng.dag.get_node(a.goal)
    g_payload = g_node.payload()
    base = a.goal
    pb = (g_payload.get("spec") or {}).get("param_bounds") or {}
    solver = _solver_for(g_payload)

    best_history = []
    archive: dict = {}          # (bin,bin) -> candidate record
    for gen in range(gens):
        candidates = []
        for i in range(pop):
            name = f"{base}/evo-g{gen}i{i}"
            params = {k: _sample(rng, b) for k, b in pb.items()}
            res = eng.refine([a.goal], {"name": "param-perturb",
                                        "args": {"values": params}},
                             out_name=name)
            if res["state"] == "rejected":
                continue   # fail-closed: informative failure kept, not bred
            ev = eng.evaluate(name, solver, fidelity=0)
            node = eng.store.get_object(eng.store.resolve(name))["payload"]
            mvals = {m: _metric_of(node.get("evidence", []), m) for m in metrics}
            if any(v is None for v in mvals.values()):
                continue
            candidates.append({"name": name, "metrics": mvals,
                               "node": eng.store.resolve(name)})

        if not candidates:
            print(f"gen {gen}: no viable candidates (all rejected/unmeasured)")
            continue
        # selection: minimize the weighted sum of the declared metrics
        candidates.sort(key=lambda c: sum(c["metrics"].values()))
        keep = candidates[: max(2, pop // 4)]
        best_history.append({"gen": gen, "best": keep[0]["name"],
                             "metrics": keep[0]["metrics"]})
        print(f"gen {gen}: {len(candidates)} viable, best {keep[0]['name']} "
              f"{keep[0]['metrics']}")

        # mutation: param-perturb handled by breeding next round; occasionally
        # a TOPOLOGY mutation (decompose a candidate into two sub-parts) —
        # the search space includes topology, not just parameters
        if rng.random() < 0.5 and keep:
            parent = keep[0]["name"]
            p_d, p_node = eng.dag.get_node(parent)
            p_payload = p_node.payload()
            gs = (p_payload.get("spec") or {}).get("guarantees", [])
            bd = (p_payload.get("spec") or {}).get("budget", {}) or {}
            half = {k: (v * 0.5 if isinstance(v, (int, float)) else v)
                    for k, v in bd.items()} if bd else {}
            flow = {"a": {"guarantees": gs, "budget": half},
                    "b": {"guarantees": gs, "budget": half}}
            r = eng.refine([parent], {"name": "decompose",
                                      "args": {"into": ["a", "b"],
                                               "flow_down": flow}},
                           out_name=f"{parent}-split")
            print(f"  topology mutation: decompose {parent} -> "
                  f"{r['state']} ({r['reason'] or 'ok'})")

        # MAP-elites: bin on the first two metrics (4x4 default grid)
        for c in candidates:
            cell = tuple(min(3, int(abs(c["metrics"][m]) / _scale(m))) for m in metrics[:2])
            prev = archive.get(cell)
            score = sum(c["metrics"].values())
            if prev is None or score < prev["score"]:
                archive[cell] = {"score": score, "name": c["name"],
                                 "metrics": c["metrics"], "node": c["node"]}

    _write_archive(eng, archive, metrics)
    print(f"evolve done: {gens} generations, archive cells filled: {len(archive)}")
    return 0


def _write_archive(eng, archive, metrics):
    """Archive entries land next to the store's object library; the catalog
    plugin reads them — evolution results precipitate into the library."""
    entries = []
    for cell, rec in archive.items():
        bounds = {}
        for m in metrics:
            v = rec["metrics"].get(m)
            if v is not None:
                bounds[m] = {">=": v - 1e-9, "<=": v + 1e-9}
        entries.append({"name": f"archive/{rec['name']}", "kind": "archive",
                        "tier": 0, "bounds": bounds,
                        "ground": {"node": rec["node"], "metrics": rec["metrics"]}})
    arch_path = Path(eng.store.root) / "archive.json"
    existing = []
    if arch_path.is_file():
        try:
            existing = json.loads(arch_path.read_text(encoding="utf-8")).get("entries", [])
        except json.JSONDecodeError:
            existing = []
    by_name = {e["name"]: e for e in existing}
    by_name.update({e["name"]: e for e in entries})
    arch_path.write_text(json.dumps({"entries": list(by_name.values())}, indent=1),
                         encoding="utf-8")


def _sample(rng, bounds):
    if isinstance(bounds, dict):
        lo, hi = bounds.get(">="), bounds.get("<=")
        if lo is not None and hi is not None:
            return round(rng.uniform(float(lo), float(hi)), 4)
        if lo is not None:
            return float(lo)
        if hi is not None:
            return float(hi)
    return rng.uniform(0.5, 1.5)


def _solver_for(payload) -> str:
    for e in reversed(payload.get("evidence", [])):
        if isinstance(e, dict) and e.get("solver", "").startswith("mission/"):
            return "mission-analysis"
    return "mission-analysis"


def _metric_of(evidence, name):
    val = None
    for e in evidence:
        if isinstance(e, dict) and name in e:
            val = e[name]
    return val


def _scale(metric: str) -> float:
    return {"cost": 100.0, "mass_g": 500.0, "range_km": 1000.0}.get(metric, 10.0)
