"""L3: tactic-state views — `fk goals / sorry / risks / next / why`.

goals = the Lean goals view transposed onto the DAG:
  (1) open subgoals: non-leaf nodes with no promoted outgoing edge
      (a leaf is closed by exact/procure);
  (2) param holes (["param", name] = sorry) and their downstream contagion;
  (3) rejected edges (the informative-failure archive);
  plus a risks column (v1.2 §25): lint-failing nodes.

risks (v1.2 §18) = the unsettled-risk ledger: holes + lint failures +
lint-capped edges + stale term references + stale plant models (v1.1
plant-model-current) + undischarged hard obligations.
"""
from __future__ import annotations

from . import contracts
from .contracts import ContractError


# ------------------------------------------------------------- structure --
def _out_edges(dag) -> dict[str, list[dict]]:
    """node_digest -> list of edges consuming it as input."""
    out: dict[str, list[dict]] = {}
    for _, e in dag.iter_edges():
        for i in e.get("inputs", []):
            out.setdefault(i, []).append(e)
    return out


def _is_leaf_closed(dag, node_d: str, payload: dict, consumers: dict) -> bool:
    """Leaf goals close via exact/procure (standard or purchased parts)."""
    for e in consumers.get(node_d, []):
        if e.get("state") == "promoted" and e.get("op") in ("exact", "procure"):
            return True
    return False


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


# ------------------------------------------------------------------ goals --
def goals_view(dag) -> dict:
    consumers = _out_edges(dag)
    superseded = _superseded_by(dag)
    open_goals, rejected = [], []
    for node_d, payload in dag.iter_nodes():
        state = dag.node_state(node_d)
        if payload.get("role") == "Medium":
            continue                      # media are environment, not goals
        promoted_out = any(e.get("state") == "promoted"
                           for e in consumers.get(node_d, []))
        closed_leaf = _is_leaf_closed(dag, node_d, payload, consumers)
        if (not promoted_out and not closed_leaf and node_d not in superseded
                and state != "rejected"):
            lint = contracts.lint_node(payload, dag.store)
            open_goals.append({
                "ref": node_d, "role": payload.get("role"),
                "kind": payload.get("kind"), "state": state,
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


def _dependents(dag, node_d: str) -> list[str]:
    consumers = _out_edges(dag)
    out, frontier = set(), [node_d]
    while frontier:
        cur = frontier.pop()
        for e in consumers.get(cur, []):
            nxt = e.get("output", "")
            if nxt and nxt not in out:
                out.add(nxt)
                frontier.append(nxt)
    return sorted(out)


def holes_view(dag) -> dict:
    holes = []
    for node_d, payload in dag.iter_nodes():
        for h in _holes_of(payload):
            holes.append({"hole": h, "node": node_d,
                          "blocks": [d for d in _dependents(dag, node_d)
                                     if d != node_d]})
    return {"holes": holes}


# --------------------------------------------------------------- risks ----
def risks_view(dag) -> dict:
    risks = []
    # 1. param holes (sorry) with contagion
    for h in holes_view(dag)["holes"]:
        risks.append({"kind": "hole", "ref": h["node"], "detail": h["hole"],
                      "blocks": h["blocks"]})
    # 2. lint failures (nodes that can never promote; v1.2 §18)
    for node_d, payload in dag.iter_nodes():
        failed = contracts.lint_node(payload, dag.store)
        if failed:
            risks.append({"kind": "lint", "ref": node_d,
                          "detail": ",".join(failed),
                          "blocks": [d for d in _dependents(dag, node_d)
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
                          "blocks": [d for d in _dependents(dag, node_d)
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
                              "blocks": [d for d in _dependents(dag, node_d)
                                         if d != node_d]})
    # 7. explicitly declared open joints (fk elicit step 6 — never smoothed)
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
    """Lineage walk back to the genesis Intent (Lean: `#print ancestors`)."""
    d = dag.store.resolve(ref)
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
        chain[-1]["via"] = f"{pe.get('op')}/{pe.get('transform', {}).get('name', '')}"
        d = (pe.get("inputs") or [None])[0]
    return chain
