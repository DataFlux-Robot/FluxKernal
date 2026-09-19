"""L3: tactic-state views — `fk goals / sorry / risks / next / why`.

goals = the Lean goals view transposed onto the DAG:
  (1) open subgoals: nodes not yet *closed*.  Closure is recursive
      (review P1 fix): a leaf closes by exact/procure (catalog), by being
      grounded (sketch/solid/process detail), or by a print edge (E1);
      an internal node closes when its promoted decompose children are all
      closed, or when it is composed from fully-closed inputs with the
      roll-up obligations discharged, or when a promoted single-input
      refine/evaluate/abstract edge realizes it into a closed descendant.
      Being merely *consumed* by a compose edge does NOT close a node —
      consumption is not realization;
  (2) param holes (["param", name] = sorry) and their contagion — restricted
      to downstream nodes that actually reference the parameter name in
      their data (params keys / contract bound quantities), not mere graph
      reachability.  Holes collapsed by a promoted param-perturb edge are
      annotated collapsed-at and hidden from the active list by default;
  (3) rejected edges (the informative-failure archive);
  plus a risks column (v1.2 §25): lint-failing nodes, coverage gaps (E0-3).

risks (v1.2 §18) = the unsettled-risk ledger: active holes + lint failures +
lint-capped edges + rejected edges + stale term references + stale plant
models (v1.1 plant-model-current) + evidence-coverage gaps + declared joints.
"""
from __future__ import annotations

from . import contracts
from .contracts import ContractError

# single-input ops whose output *realizes* their input (consumption by
# compose does not: that is aggregation, not realization)
_REPLACE_OPS = {"refine", "evaluate", "abstract"}

# ground types that count as "grounded" leaves (executable detail exists)
_GROUND_TYPES = ("sketch2d", "process", "process-op")


# ------------------------------------------------------------- structure --
def _out_edges(dag) -> dict[str, list[dict]]:
    """node_digest -> list of edges consuming it as input."""
    out: dict[str, list[dict]] = {}
    for _, e in dag.iter_edges():
        for i in e.get("inputs", []):
            out.setdefault(i, []).append(e)
    return out


def _superseded_by(dag) -> set[str]:
    """Nodes superseded by some newer promoted branch (non-destructive)."""
    gone = set()
    for _, e in dag.iter_edges():
        if e.get("state") == "promoted":
            for s in (e.get("transform", {}).get("args", {}) or {}).get("supersedes", []):
                gone.add(s)
            out_obj = None
            try:
                out_obj = dag.store.get_object(e.get("output", ""))
            except KeyError:
                pass
            if out_obj:
                for s in out_obj["payload"].get("supersedes", []):
                    gone.add(s)
    return gone


def _parents(dag) -> dict[str, list[str]]:
    """node_digest -> list of (parent) input digests of its producing edge."""
    par: dict[str, list[str]] = {}
    for _, e in dag.iter_edges():
        par.setdefault(e.get("output", ""), []).extend(e.get("inputs", []))
    return par


def depth_of(dag, node_d: str, parents: dict | None = None) -> int:
    """Path-derived depth (no stored level numbers, §3.2)."""
    parents = parents if parents is not None else _parents(dag)
    seen, depth = set(), 0
    cur = node_d
    while True:
        ps = parents.get(cur, [])
        if not ps or cur in seen:
            return depth
        seen.add(cur)
        cur = ps[0]
        depth += 1


# --------------------------------------------------------------- closure --
def _is_grounded(payload: dict) -> bool:
    g = payload.get("ground") or {}
    return bool(g.get("construction")) or g.get("type") in _GROUND_TYPES


def _closed_nodes(dag, consumers: dict[str, list[dict]] | None = None) -> set[str]:
    """Recursive closure fixpoint (review P1 + E1 termination set).  A node
    closes by:

    leaf     — a terminal production route is assigned: consumed by a
               promoted exact/procure edge (catalog), a print edge
               (termination b) or a manufacture edge (process family); a
               Process node's own executable detail (takt/cost ground)
               closes it.  Mere geometric grounding does NOT close a Part —
               an unassigned grounded part stays open as machining-needed;
    composed — produced by a promoted compose edge whose inputs are all
               closed and whose rollup-met (soft) obligations all hold;
    split    — a promoted decompose scope/child group whose children are all
               closed (media excepted);
    realized — consumed by a promoted single-input refine/evaluate/abstract
               edge whose output is closed (the descendant realized it).
    """
    consumers = consumers if consumers is not None else _out_edges(dag)
    nodes = {d: p for d, p in dag.iter_nodes()}
    alive = {d for d, p in nodes.items()
             if dag.node_state(d) in ("promoted", "genesis")}
    kids: dict[str, list[str]] = {}
    produced_closed: set[str] = set()
    composed_by: dict[str, dict] = {}
    for _, e in dag.iter_edges():
        if e.get("state") != "promoted":
            continue
        tname = (e.get("transform") or {}).get("name", "")
        if tname == "decompose":
            ins = e.get("inputs") or []
            if ins:
                kids.setdefault(ins[0], []).append(e.get("output", ""))
        if e.get("op") in ("exact", "procure") or tname in ("print",):
            # the closure artifact itself (std part / printed part)
            produced_closed.add(e.get("output", ""))
        elif e.get("op") == "evaluate":
            # verification projection: evidences its target, adds no
            # realization obligation of its own
            produced_closed.add(e.get("output", ""))
        elif e.get("op") == "compose":
            composed_by[e.get("output", "")] = e

    def _production_assigned(d: str, payload: dict) -> bool:
        g = payload.get("ground") or {}
        if g.get("type") in ("process", "process-op"):
            return True                        # executable process detail
        for e in consumers.get(d, []):
            if e.get("state") != "promoted":
                continue
            if e.get("op") in ("exact", "procure", "manufacture"):
                return True
            if (e.get("transform") or {}).get("name") == "print":
                return True
        return False

    closed = {d for d in produced_closed if d in alive}
    changed = True
    while changed:
        changed = False
        for d, payload in nodes.items():
            if d in closed or d not in alive:
                continue
            ok = False
            if _production_assigned(d, payload):
                ok = True                                   # leaf termination
            if not ok and d in composed_by:
                e = composed_by[d]
                ins = [i for i in (e.get("inputs") or []) if i in nodes]
                rollups_ok = all(o.get("holds") is True
                                 for o in ((e.get("certificate") or {})
                                           .get("obligations") or [])
                                 if o.get("id") == "rollup-met")
                if ins and all(i in closed for i in ins) and rollups_ok:
                    ok = True                               # composed from closed
            if not ok and d in kids:
                ch = kids[d]
                if ch and all(c in closed
                              or (nodes.get(c) or {}).get("role") == "Medium"
                              for c in ch):
                    ok = True                               # fully decomposed
            if not ok:
                for e in consumers.get(d, []):
                    # decompose CHILD edges are structural, not replacements;
                    # the SCOPE edge (parent -> scope-with-kids) does realize
                    # the parent (the scope is its decomposed design)
                    if (e.get("state") == "promoted"
                            and e.get("op") in _REPLACE_OPS
                            and ((e.get("transform") or {}).get("name") != "decompose"
                                 or e.get("output") in kids)
                            and len(e.get("inputs") or []) == 1
                            and e.get("output") in closed):
                        ok = True                           # realized downstream
                        break
            if ok:
                closed.add(d)
                changed = True
    return closed


def _termination_of(payload: dict) -> str:
    """What stands between an open node and its terminal set."""
    return "machining-needed" if _is_grounded(payload) else "undecomposed"


# ------------------------------------------------------------------ goals --
def goals_view(dag) -> dict:
    consumers = _out_edges(dag)
    superseded = _superseded_by(dag)
    closed = _closed_nodes(dag, consumers)
    open_goals, rejected = [], []
    for node_d, payload in dag.iter_nodes():
        state = dag.node_state(node_d)
        if payload.get("role") == "Medium":
            continue                      # media are environment, not goals
        if node_d in closed or state == "rejected" or node_d in superseded:
            continue
        lint = contracts.lint_node(payload, dag.store)
        open_goals.append({
            "ref": node_d, "role": payload.get("role"),
            "kind": payload.get("kind"), "state": state,
            "termination": _termination_of(payload),
            "holes": sorted(_holes_of(payload)),
            "risks": lint,
        })
    for edge_d, e in dag.iter_edges():
        if e.get("state") == "rejected":
            rejected.append({"edge": edge_d, "op": e.get("op"),
                             "reason": e.get("reason", ""),
                             "output": e.get("output", "")})
    holes = holes_view(dag)
    return {"open": sorted(open_goals, key=lambda g: g["ref"]),
            "holes": holes["holes"], "rejected": rejected}


def open_goals_under(dag, root_ref: str) -> list[dict]:
    """Open goals in the subtree rooted at root_ref (for realize)."""
    root_d = dag.store.resolve(root_ref)
    view = goals_view(dag)
    parents = _parents(dag)
    out = []
    for g in view["open"]:
        anc, cur, seen = set(), g["ref"], set()
        while cur and cur not in seen:
            seen.add(cur)
            cur = parents.get(cur, [None])[0]
            if cur:
                anc.add(cur)
        if root_d in anc or g["ref"] == root_d:
            g = dict(g)
            g["ref_name"] = g["ref"]
            g["spec"] = dag.store.get_object(g["ref"])["payload"].get("spec") or {}
            out.append(g)
    return out


# -------------------------------------------------------------- holes -----
def _holes_of(payload: dict) -> list[str]:
    holes = []
    for name, v in (payload.get("params") or {}).items():
        if isinstance(v, (list, tuple)) and v and v[0] == "param":
            holes.append(f"?{v[1] if len(v) > 1 else name}")
    return holes


def _mentions_param(payload: dict, name: str) -> bool:
    """Does this node's own data actually reference the parameter name?"""
    if name in (payload.get("params") or {}):
        return True
    spec = payload.get("spec") or {}
    for slot in ("goals", "guarantees", "assumes"):
        for entry in spec.get(slot) or []:
            for q in (entry.get("bounds") or {}):
                if q == name:
                    return True
    for slot in ("budget", "effluent"):
        for q in (spec.get(slot) or {}):
            if q == name:
                return True
    return False


def _dependents(dag, node_d: str, consumers: dict | None = None,
                param: str | None = None) -> list[str]:
    """Downstream nodes.  With `param`, only nodes whose own data references
    the parameter name are reported (data-reference contagion, review P2);
    traversal still passes through non-referencing intermediates."""
    consumers = consumers if consumers is not None else _out_edges(dag)
    payloads = {d: p for d, p in dag.iter_nodes()}
    seen, frontier = set(), [node_d]
    while frontier:
        cur = frontier.pop()
        for e in consumers.get(cur, []):
            nxt = e.get("output", "")
            if nxt and nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    out = [d for d in seen if d != node_d]
    if param is not None:
        out = [d for d in out if _mentions_param(payloads.get(d, {}), param)]
    return sorted(out)


def holes_view(dag, include_collapsed: bool = False) -> dict:
    consumers = _out_edges(dag)
    parents = _parents(dag)
    perturb = []          # (input digest, values, edge digest)
    for edge_d, e in dag.iter_edges():
        if (e.get("state") == "promoted"
                and (e.get("transform") or {}).get("name") == "param-perturb"):
            vals = ((e.get("transform") or {}).get("args") or {}).get("values") or {}
            for i in e.get("inputs") or []:
                perturb.append((i, vals, edge_d))

    def _ancestors(d: str) -> set[str]:
        anc, cur, seen = set(), d, set()
        while cur and cur not in seen:
            seen.add(cur)
            for p in parents.get(cur, []):
                anc.add(p)
            nxt = parents.get(cur, [])
            cur = nxt[0] if nxt else None
        return anc

    holes = []
    for node_d, payload in dag.iter_nodes():
        for h in _holes_of(payload):
            name = h[1:]
            collapsed_at = None
            for i, vals, edge_d in perturb:
                if name in vals and (i == node_d or node_d in _ancestors(i)):
                    collapsed_at = edge_d
                    break
            if collapsed_at is not None and not include_collapsed:
                continue
            entry = {"hole": h, "node": node_d,
                     "blocks": _dependents(dag, node_d, consumers, name)}
            if collapsed_at is not None:
                entry["collapsed_at"] = collapsed_at
            holes.append(entry)
    return {"holes": holes}


# --------------------------------------------------------------- risks ----
def risks_view(dag) -> dict:
    consumers = _out_edges(dag)
    risks = []
    # 1. active param holes (sorry) with data-reference contagion
    for h in holes_view(dag)["holes"]:
        risks.append({"kind": "hole", "ref": h["node"], "detail": h["hole"],
                      "blocks": h["blocks"]})
    # 2. lint failures (nodes that can never promote; v1.2 §18)
    for node_d, payload in dag.iter_nodes():
        failed = contracts.lint_node(payload, dag.store)
        if failed:
            risks.append({"kind": "lint", "ref": node_d,
                          "detail": ",".join(failed),
                          "blocks": [d for d in _dependents(dag, node_d, consumers)
                                     if d != node_d]})
    # 3. edges capped at proposed by the lint gate
    for edge_d, e in dag.iter_edges():
        if e.get("state") == "proposed" and e.get("reason", "").startswith("L"):
            risks.append({"kind": "gate", "ref": edge_d, "detail": e.get("reason"),
                          "blocks": [e.get("output", "")]})
    # 4. rejected edges (informative failures are assets, but still risks)
    for edge_d, e in dag.iter_edges():
        if e.get("state") == "rejected":
            risks.append({"kind": "rejected", "ref": edge_d,
                          "detail": e.get("reason", ""), "blocks": []})
    # 5. stale term references (term-current, v1.2 §23)
    for node_d, payload in dag.iter_nodes():
        stale = contracts.stale_terms(dag.store, payload.get("spec") or {})
        if stale:
            risks.append({"kind": "term-stale", "ref": node_d,
                          "detail": f"{len(stale)} stale term digest(s)",
                          "blocks": [d for d in _dependents(dag, node_d, consumers)
                                     if d != node_d]})
    # 6. stale plant models (plant-model-current, v1.1 §14)
    for node_d, payload in dag.iter_nodes():
        spec = payload.get("spec") or {}
        if payload.get("facet") == "MIND" and spec.get("plant_name"):
            cur = dag.store.names().get(spec["plant_name"])
            if cur and cur != spec.get("plant_ref"):
                risks.append({"kind": "plant-stale", "ref": node_d,
                              "detail": f"plant {spec['plant_name']} moved on "
                                        f"({spec.get('plant_ref', '')[:20]}… != current)",
                              "blocks": [d for d in _dependents(dag, node_d, consumers)
                                         if d != node_d]})
    # 7. evidence-coverage gaps (E0-3): promoted composes whose parent
    #    guarantee quantities have no subtree evidence (soft, non-blocking)
    for edge_d, e in dag.iter_edges():
        if e.get("state") != "promoted" or e.get("op") != "compose":
            continue
        for o in ((e.get("certificate") or {}).get("obligations") or []):
            if o.get("id") == "evidence-coverage" and o.get("holds") is not True:
                risks.append({"kind": "coverage", "ref": edge_d,
                              "detail": o.get("detail", ""),
                              "blocks": [e.get("output", "")]})
    # 8. explicitly declared open joints (fk elicit step 6 — never smoothed)
    for node_d, payload in dag.iter_nodes():
        for gap in (payload.get("spec") or {}).get("open_risks") or []:
            risks.append({"kind": "open-joint", "ref": node_d,
                          "detail": str(gap), "blocks": []})
    return {"risks": risks}


# ------------------------------------------------------------ next / why --
def next_goal(dag) -> dict | None:
    view = goals_view(dag)
    if not view["open"]:
        return None
    parents = _parents(dag)
    return sorted(view["open"], key=lambda g: depth_of(dag, g["ref"], parents))[0]


def why(dag, ref: str) -> list[dict]:
    """Lineage walk back to the genesis Intent (Lean: `#print ancestors`).
    Each hop is annotated with the DSL edge name when one is bound
    (review P5 — the dual-role nodes read unambiguously with names)."""
    d = dag.store.resolve(ref)
    edge_names = {dg: n for n, dg in dag.store.names().items()
                  if dg.startswith("fk1:edge:") and not n.startswith("@")}
    chain = []
    seen = set()
    while d and d not in seen:
        seen.add(d)
        payload = dag.store.get_object(d)["payload"]
        chain.append({"ref": d, "role": payload.get("role"),
                      "kind": payload.get("kind"), "facet": payload.get("facet")})
        pe = dag.producing_edge(d)
        if not pe:
            break
        edge_d = dag.store.names().get(f"@lineage/{d}", "")
        chain[-1]["via"] = f"{pe.get('op')}/{pe.get('transform', {}).get('name', '')}"
        if edge_names.get(edge_d):
            chain[-1]["via"] += f" [{edge_names[edge_d]}]"
        d = (pe.get("inputs") or [None])[0]
    return chain
