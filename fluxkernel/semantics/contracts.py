"""L3: contract arithmetic — the v1.2 contract-native spec model.

spec is a CONTRACT, not a property bag. Nine slots (see core.objects.CONTRACT_SLOTS):
  goals / semantics / assumes / guarantees / budget / effluent / forbidden /
  not_responsible / time_scale
Medium nodes instead carry {capacity, margin, state, degradation}.

Everything here is DECIDABLE finite arithmetic (intervals, sums, label checks) —
"the kernel does not prove physics, only contract arithmetic". Physical truth
stays with evidence tiers.

Lint rule ids (append-only discipline; L4 is fixed by the v1.2 doc as the
noun-resolution rule):
  L1 input-space bounded        (every assume has numeric bounds)
  L2 guarantees decidable       (guarantees bounded + goals falsifiable+measured)
  L3 fault modes enumerated     (forbidden list with a check method)
  L4 terms resolved             (all spec nouns resolve to term-registry digests)
  L5 time scale single          (one scale or an explicitly stratified list)
  L6 free params bounded        (every param hole has a range or a checker)
Medium nodes are exempt from L1–L6 (they are environment declarations, not
contract-bearing design states).
"""
from __future__ import annotations

from ..core.objects import Obligation

BOUND_OPS = ("<=", ">=", "=", "<", ">")
TERM_PREFIX = "term/"          # store index binding: term/<name> -> digest


class ContractError(Exception):
    def __init__(self, code: str, msg: str):
        self.code = code
        super().__init__(f"[{code}] {msg}")


# ---------------------------------------------------------------- bounds ----
def parse_bound(b) -> dict:
    """Normalize a bound to {"lo": float|None, "hi": float|None, "medium": str|None}.

    Accepted forms:
      ["<=", 30]  [">=", 22]  ["=", 28]                one-sided
      {"<=": 30, ">=": 22}                             interval
      {"op": "<=", "value": 30, "medium": "<digest>"}  one-sided + medium ref
      {"<=": 4, "medium": "<digest>"}                   interval + medium ref
    """
    if isinstance(b, dict):
        if "op" in b:
            if b["op"] not in BOUND_OPS:
                raise ContractError("T2", f"bad bound op {b['op']!r}")
            v = float(b["value"])
            lo = v if b["op"] in (">=", "=", ">") else None
            hi = v if b["op"] in ("<=", "=", "<") else None
            return {"lo": lo, "hi": hi, "medium": b.get("medium")}
        if "=" in b:                       # exact-value form {qty: {"=": v}}
            v = float(b["="])
            return {"lo": v, "hi": v, "medium": b.get("medium")}
        lo = float(b[">="]) if ">=" in b else None
        hi = float(b["<="]) if "<=" in b else None
        return {"lo": lo, "hi": hi, "medium": b.get("medium")}
    if isinstance(b, (list, tuple)) and len(b) == 2 and b[0] in BOUND_OPS:
        v = float(b[1])
        lo = v if b[0] in (">=", "=", ">") else None
        hi = v if b[0] in ("<=", "=", "<") else None
        return {"lo": lo, "hi": hi, "medium": None}
    raise ContractError("T2", f"unparseable bound: {b!r}")


def bound_str(qty: str, b) -> str:
    p = parse_bound(b)
    parts = []
    if p["lo"] is not None:
        parts.append(f"{qty}>={p['lo']:g}")
    if p["hi"] is not None:
        parts.append(f"{qty}<={p['hi']:g}")
    return " & ".join(parts) or qty


def covers(assume_b, guarantee_b) -> tuple[bool, bool]:
    """Is the provider's guarantee interval INSIDE the consumer's tolerance?

    Returns (covered, contradiction): covered = guarantee ⊆ assume;
    contradiction = provably disjoint intervals (K1 contract conflict —
    exposed BEFORE detailed design, v1.2 §21).
    """
    a, g = parse_bound(assume_b), parse_bound(guarantee_b)
    contradiction = ((g["lo"] is not None and a["hi"] is not None and g["lo"] > a["hi"])
                     or (g["hi"] is not None and a["lo"] is not None and g["hi"] < a["lo"]))
    covered = ((a["lo"] is None or (g["lo"] is not None and g["lo"] >= a["lo"]))
               and (a["hi"] is None or (g["hi"] is not None and g["hi"] <= a["hi"])))
    return covered, contradiction


def qty_entries(spec: dict, slot: str) -> dict:
    """Quantity->bound map for a spec slot (budget/effluent/guarantee bounds)."""
    return {k: v for k, v in (spec.get(slot) or {}).items()} if isinstance(spec.get(slot), dict) else {}


def entry_bounds(spec: dict, slot: str) -> list[dict]:
    return [e for e in (spec.get(slot) or []) if isinstance(e, dict)]


def is_medium(spec: dict) -> bool:
    return isinstance(spec, dict) and "capacity" in spec


# ------------------------------------------------------------------ lint ----
def _has_numeric_side(b) -> bool:
    try:
        p = parse_bound(b)
        return p["lo"] is not None or p["hi"] is not None
    except ContractError:
        return False


def lint_node(node_payload: dict, store) -> list[str]:
    """The five objectivity rules + noun resolution. Returns FAILED rule ids."""
    # archival records (P7a VLM review edges) carry no contract — they are
    # evidence, not design states; the lint contract rules do not apply
    if node_payload.get("kind") in ("params", "review"):
        return []
    spec = node_payload.get("spec") or {}
    if is_medium(spec):
        # Media: capacity must be bounded (that is their whole contract).
        cap = spec.get("capacity") or {}
        return [] if cap and all(_has_numeric_side(b) for b in cap.values()) else ["L1"]

    failed: list[str] = []

    # L1 input space bounded
    assumes = entry_bounds(spec, "assumes")
    if (not assumes
            or any(not e.get("id") or not e.get("stmt") for e in assumes)
            or any(not e.get("bounds") or
                   not all(_has_numeric_side(b) for b in e["bounds"].values())
                   for e in assumes)):
        failed.append("L1")

    # L2 guarantees decidable + goals falsifiable with a measure
    guarantees = entry_bounds(spec, "guarantees")
    goals = entry_bounds(spec, "goals")
    g_bad = (not guarantees or any(not e.get("id") or not e.get("stmt") for e in guarantees)
             or any(not e.get("bounds") or
                    not all(_has_numeric_side(b) for b in e["bounds"].values())
                    for e in guarantees))
    goal_bad = (not goals or any(e.get("falsifiable") is not True or not e.get("measure")
                                 or not e.get("stmt") for e in goals))
    if g_bad or goal_bad:
        failed.append("L2")

    # L3 fault modes enumerated (forbidden states with a decidable check method)
    forbidden = entry_bounds(spec, "forbidden")
    if (not forbidden
            or any(not e.get("stmt") or e.get("check") not in
                   ("reachability", "inspection", "test") for e in forbidden)):
        failed.append("L3")

    # L4 every spec noun resolves to the term registry (semantic glossary)
    if not _terms_resolve(spec, store):
        failed.append("L4")

    # L5 single time scale (or an explicitly stratified list)
    ts = spec.get("time_scale")
    if not ts or (not isinstance(ts, str) and not (isinstance(ts, list) and ts)):
        failed.append("L5")

    # L6 free parameters have a range or a checker
    pb = spec.get("param_bounds") or {}
    pc = spec.get("param_checks") or {}
    for name, v in (node_payload.get("params") or {}).items():
        if isinstance(v, (list, tuple)) and v and v[0] == "param":
            if name not in pb and name not in pc:
                failed.append("L6")
                break

    return failed


def _terms_resolve(spec: dict, store) -> bool:
    """spec.semantics digests must exist; entry-level term refs must resolve.

    Entries (goals/assumes/guarantees/forbidden) may declare
    "terms": [name-or-digest, ...]; every one must resolve in the registry.
    A non-empty semantics slot with resolvable digests is required.
    """
    sem = spec.get("semantics") or []
    if not sem:
        return False
    idx = store.names()
    for d in sem:
        obj = None
        try:
            obj = store.get_object(d)
        except KeyError:
            pass
        if not obj or obj.get("kind") != "term":
            return False
    for slot in ("goals", "assumes", "guarantees", "forbidden"):
        for e in entry_bounds(spec, slot):
            for t in e.get("terms", []):
                if not _term_exists(t, store):
                    return False
    return True


def _term_exists(t: str, store) -> bool:
    if t.startswith("fk1:"):
        try:
            return store.get_object(t).get("kind") == "term"
        except KeyError:
            return False
    return TERM_PREFIX + t in store.names()


def make_lint_gate(store):
    """Promotion gate injected into the kernel DAG (v1.2 §18): nodes failing
    lint may exist but their producing edge never rises above `proposed`."""
    def gate(node_payload: dict) -> list[str]:
        return lint_node(node_payload, store)
    return gate


# ----------------------------------------------------------------- terms ----
def put_term(store, name: str, opdef: str, notes: str = "") -> str:
    """Register/refresh an operational definition in the glossary.

    Content-addressed: a changed opdef gets a NEW digest; the index binding
    term/<name> moves, which invalidates every spec still referencing the old
    digest (term-current obligation, same mechanism as plant-model-current).
    """
    d = store.put_object("term", {"name": name, "opdef": opdef, "notes": notes})
    store.bind_name(TERM_PREFIX + name, d)
    return d


def resolve_term(store, ref: str) -> tuple[str, dict] | tuple[None, None]:
    idx = store.names()
    d = idx.get(TERM_PREFIX + ref, ref) if not ref.startswith("fk1:") else ref
    try:
        obj = store.get_object(d)
        if obj["kind"] == "term":
            return d, obj["payload"]
    except KeyError:
        pass
    return None, None


def stale_terms(store, spec: dict) -> list[str]:
    """Term digests referenced by a spec that are no longer the current
    registration of their name (term-current violations)."""
    idx = store.names()
    stale = []
    for d in spec.get("semantics") or []:
        obj = None
        try:
            obj = store.get_object(d)
        except KeyError:
            pass
        if not obj or obj.get("kind") != "term":
            stale.append(d)
            continue
        name = obj["payload"].get("name", "")
        if name and idx.get(TERM_PREFIX + name) != d:
            stale.append(d)
    return stale


# ---------------------------------------------------------------- ledger ----
def ledger(dag, medium_ref: str) -> dict:
    """Derived medium account (v1.2 §19): sum of all REFERENCING nodes'
    budget/effluent declarations against capacity × (1 − margin).

    Only physically real nodes count (state promoted/genesis). Roll-up
    subsumption: when a promoted compose/integrate output declares its own
    budget on the same (qty, medium), its input children's declarations are
    already contained in the parent's — counting both would double-book.
    """
    m_d, m_spec = _medium_spec(dag, medium_ref)
    cap = {q: parse_bound(b) for q, b in (m_spec.get("capacity") or {}).items()}
    margin = float(m_spec.get("margin", 0.2))
    rows = {"budget": [], "effluent": []}
    sums = {"budget": {}, "effluent": {}}

    subsumed = _subsumed_allocations(dag)

    for node_d, payload in dag.iter_nodes():
        state = dag.node_state(node_d)
        if state not in ("promoted", "genesis"):
            continue
        spec = payload.get("spec") or {}
        for slot in ("budget", "effluent"):
            for q, b in qty_entries(spec, slot).items():
                p = parse_bound(b)
                if p["medium"] != m_d:
                    continue
                v = p["hi"] if p["hi"] is not None else p["lo"]
                if v is None:
                    continue
                rows[slot].append({"node": node_d, "kind": payload.get("kind"),
                                   "qty": q, "value": v,
                                   "subsumed": (node_d, slot, q) in subsumed})
                if (node_d, slot, q) not in subsumed:
                    sums[slot][q] = sums[slot].get(q, 0.0) + v

    obligations = []
    ok = {}
    for q, cp in cap.items():
        cap_v = cp["hi"] if cp["hi"] is not None else cp["lo"]
        if cap_v is None:
            continue
        allowed = cap_v * (1.0 - margin)
        used_b = sums["budget"].get(q, 0.0)
        used_e = sums["effluent"].get(q, 0.0)
        ok[q] = (used_b <= allowed + 1e-12) and (used_e <= allowed + 1e-12)
        obligations.append(Obligation(
            id="medium-capacity",
            prop=(f"Σbudget[{q}]={used_b:g}, Σeffluent[{q}]={used_e:g} "
                  f"≤ capacity×(1−margin)={allowed:g} on {m_d[:24]}…"),
            holds=ok[q], checker="contracts",
            detail="" if ok[q] else "G2: medium over capacity"))
    return {"medium": m_d, "capacity": {q: (cp['hi'] if cp['hi'] is not None else cp['lo'])
                                        for q, cp in cap.items()},
            "margin": margin, "rows": rows, "sums": sums, "ok": ok,
            "obligations": obligations}


def _subsumed_allocations(dag) -> set[tuple[str, str, str]]:
    """(node_digest, slot, qty) triples already absorbed by a promoted
    successor that re-declares the same slot+qty:
      - compose/integrate: auto roll-up budgets contain the children's
      - exact/procure: the closed design realizes the goal's allocations
      - refine/evaluate: the successor's declaration replaces the
        predecessor's (refine chains would otherwise double-book one
        physical declaration across every stage)
    """
    subsumed: set[tuple[str, str, str]] = set()
    for edge_d, e in dag.iter_edges():
        if e.get("op") not in ("compose", "integrate", "exact", "procure",
                               "refine", "evaluate", "manufacture") \
                or e.get("state") != "promoted":
            continue
        try:
            parent = dag.store.get_object(e.get("output", ""))["payload"]
        except KeyError:
            continue
        p_spec = parent.get("spec") or {}
        for slot in ("budget", "effluent"):
            for q in qty_entries(p_spec, slot):
                for i in e.get("inputs", []):
                    subsumed.add((i, slot, q))
    return subsumed


def _medium_spec(dag, medium_ref: str) -> tuple[str, dict]:
    d = dag.store.resolve(medium_ref)
    obj = dag.store.get_object(d)
    if obj["kind"] != "node":
        raise ContractError("T2", f"{medium_ref} is not a node")
    payload = obj["payload"]
    if payload.get("role") != "Medium":
        raise ContractError("T2", f"{medium_ref} is not a Medium node")
    return d, payload.get("spec") or {}


# ------------------------------------------------------------- C1 – C4 ------
def check_ag_coverage(consumers: list[tuple[str, dict]],
                      providers: list[tuple[str, dict]]) -> list[Obligation]:
    """C1: every consumer Assume covered by some provider Guarantee (or the
    composed parent's own promises/environment). Machine-decidable interval
    check. CONTRADICTION FIRST: a sibling guarantee on the same qty that is
    disjoint from the assume makes the wiring physically impossible (the
    rail cannot be both >=12 and <=5) — reported as K1 even when some other
    provider (e.g. an environment passthrough) would nominally cover it."""
    out = []
    for c_d, c_spec in consumers:
        for entry in entry_bounds(c_spec, "assumes"):
            for q, ab in (entry.get("bounds") or {}).items():
                results = []
                for p_d, p_spec in providers:
                    for ge in entry_bounds(p_spec, "guarantees"):
                        if q in (ge.get("bounds") or {}):
                            cov, contra = covers(ab, ge["bounds"][q])
                            results.append((cov, contra, p_d))
                if any(k for _, k, _ in results):
                    out.append(Obligation(
                        id="ag-coverage",
                        prop=f"{c_d[:20]}… assume [{entry.get('id')}] {q} "
                             f"compatible with every provider guarantee",
                        holds=False, checker="contracts",
                        detail=f"K1: contradictory contract intervals on {q}"))
                    continue
                if any(c for c, _, _ in results):
                    continue   # covered by at least one provider
                out.append(Obligation(
                    id="ag-coverage",
                    prop=f"{c_d[:20]}… assume [{entry.get('id')}] {q} covered by a provider guarantee",
                    holds=False, checker="contracts",
                    detail=f"no provider guarantee covers {bound_str(q, ab)}"))
    return out


def check_effluent_absorption(children: list[tuple[str, dict]],
                              media: list[tuple[str, dict]]) -> list[Obligation]:
    """C3: downstream tolerance must absorb upstream Effluent WORST values
    (never typical values). Medium-mediated effluent is absorbed by the
    medium's capacity (checked by the ledger, C2) — only un-mediated effluent
    demands an explicit sibling/downstream tolerance."""
    media_cap_qtys = set()
    for _, m_payload in media:
        for q in ((m_payload.get("spec") or {}).get("capacity") or {}):
            media_cap_qtys.add(q)
    out = []
    for u_d, u_spec in children:
        for q, eb in qty_entries(u_spec, "effluent").items():
            p = parse_bound(eb)
            worst = p["hi"] if p["hi"] is not None else p["lo"]
            if worst is None:
                continue
            if p["medium"] and q in media_cap_qtys:
                continue   # the medium's ledger owns this absorption
            tol = None
            for c_d, c_spec in children:
                if c_d == u_d:
                    continue
                for ae in entry_bounds(c_spec, "assumes"):
                    for q2, ab in (ae.get("bounds") or {}).items():
                        if q2 == q:
                            ap = parse_bound(ab)
                            if ap["lo"] is not None:
                                tol = max(tol or 0.0, ap["lo"])
            ok = tol is not None and tol >= worst - 1e-12
            out.append(Obligation(
                id="effluent-absorption",
                prop=f"effluent {q} worst={worst:g} absorbed "
                     f"(tolerance {tol if tol is not None else 'none declared'})",
                holds=ok, checker="contracts",
                detail="" if ok else "G3: downstream cannot swallow worst-case effluent"))
    return out


def check_time_scale(children: list[tuple[str, dict]], out_scale) -> list[Obligation]:
    """C4: quantities inside one contract share a time scale or are explicitly
    stratified (label check)."""
    scales = []
    for _, spec in children:
        ts = (spec or {}).get("time_scale")
        if isinstance(ts, list):
            scales.extend(ts)
        elif ts:
            scales.append(ts)
    if len(set(scales)) <= 1:
        return []
    out_list = out_scale if isinstance(out_scale, list) else [out_scale]
    ok = all(s in out_list for s in scales)
    return [Obligation(
        id="time-scale-stratified",
        prop=f"time scales {sorted(set(scales))} stratified in output contract",
        holds=ok, checker="contracts",
        detail="" if ok else "T3: mixed time scales without explicit stratification")]


def compose_obligations(children: list[tuple[str, dict]],
                        out_spec: dict, media: list[tuple[str, dict]]) -> list[Obligation]:
    """All four lossy-combination rules (v1.2 §20). C2 (medium capacity) is
    added by the operator via ledger(); here C1/C3/C4. Providers for C1 are
    the sibling children plus the composed parent — its guarantees (what it
    feeds the children) and its assumes (environment contracts that pass
    through to the children)."""
    env = {"guarantees": (out_spec or {}).get("assumes", [])}
    providers = children + [("<parent>", out_spec), ("<parent-env>", env)]
    obligations = check_ag_coverage(children, providers)
    obligations += check_effluent_absorption(children, media)
    obligations += check_time_scale(children, (out_spec or {}).get("time_scale"))
    return obligations


# ------------------------------------------------------------- flow-down ----
def flow_down_obligations(parent_spec: dict, child_spec: dict) -> list[Obligation]:
    """Refine flow-down (v1.2 §17.2): the child's assumes must be covered by the
    parent's guarantees (what the parent promises to provide) OR the parent's
    own assumes (environment constraints the child inherits). The child's
    budget cannot exceed the parent's allocation per quantity."""
    obligations = []
    inherited_env = {"guarantees": (parent_spec or {}).get("assumes", [])}
    providers = [("<parent>", parent_spec), ("<parent-env>", inherited_env)]
    obligations += check_ag_coverage([("<child>", child_spec)], providers)
    for q, cb in qty_entries(child_spec, "budget").items():
        pb = qty_entries(parent_spec, "budget").get(q)
        if pb is None:
            continue
        cp, pp = parse_bound(cb), parse_bound(pb)
        child_v = cp["hi"] if cp["hi"] is not None else cp["lo"]
        parent_v = pp["hi"] if pp["hi"] is not None else pp["lo"]
        if child_v is not None and parent_v is not None and child_v > parent_v + 1e-12:
            obligations.append(Obligation(
                id="budget-closed",
                prop=f"child budget[{q}]={child_v:g} within parent {parent_v:g}",
                holds=False, checker="contracts", detail="budget exceeds parent allocation"))
    return obligations
