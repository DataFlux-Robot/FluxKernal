"""Case-contract (CC1/D1): the methodology as a hard gate.

A case-contract declares WHAT "done" means for this design exercise —
decomposition depth, termination profile, manufacturing chains, the
simulation matrix, reference fidelity.  Each requirement evaluates to a
standard obligation straight into C0; OPEN(0) from here on means
"goal closure AND case profile satisfied" (goals_view merges the two).

This is the fix for "a case can be legally shallow": the 11-step frame
lived in the user's head and the skill prose; now it lives where the
kernel can enforce it.
"""
from __future__ import annotations

# whitelisted requirement keys + their validators
REQUIRE_KEYS = {
    "min-part-decompose-depth": float,
    "part-leaf-ratio": tuple,          # (op, value)
    "termination": list,               # allowed terminal sets
    "manufacturing-chains": dict,      # {n: int, with-machine: bool}
    "sim-matrix": list,                # [(role, solver), ...]
    "reference-fidelity": dict,        # {issues-max: int}
}

# profile templates keyed by :type
PROFILES = {
    "product": {
        "termination": ["standard-parts", "printable"],
    },
    "prsi-full": {
        "termination": ["standard-parts", "printable"],
        "manufacturing-chains": {"n": 1, "with-machine": True},
    },
    "product-reverse": {
        "termination": ["standard-parts", "printable"],
        "reference-fidelity": {"issues-max": 2},
    },
}


def validate_schema(payload: dict) -> list[str]:
    """Unknown require keys are refused — a typo must never pass
    silently (same discipline as C0/U3)."""
    errs = []
    for k in (payload.get("requires") or {}):
        if k not in REQUIRE_KEYS:
            errs.append(f"unknown require {k!r} (known: {sorted(REQUIRE_KEYS)})")
    typ = payload.get("type")
    if typ is not None and typ not in PROFILES:
        errs.append(f"unknown case type {typ!r} (known: {sorted(PROFILES)})")
    return errs


def _part_stats(dag):
    """(total Parts, decomposed Parts, leaf Parts).  A Part counts as
    DECOMPOSED only when a decompose edge consumes the Part itself —
    being a descendant of some System's decomposition is the normal
    state of every part and says nothing about depth."""
    nodes = dict(dag.iter_nodes())
    decomposed = set()
    for _, e in dag.iter_edges():
        if (e.get("transform") or {}).get("name") != "decompose":
            continue
        for i in e.get("inputs") or []:
            p = nodes.get(i)
            if p is not None and p.get("role") == "Part":
                decomposed.add(i)
    total = dec = leaf = 0
    for d, p in nodes.items():
        if p.get("role") != "Part":
            continue
        total += 1
        if d in decomposed:
            dec += 1
        else:
            leaf += 1
    return total, dec, leaf


def _descendants(dag, root, nodes, seen=None):
    seen = seen if seen is not None else set()
    if root in seen:
        return set()
    seen.add(root)
    out = {root}
    for _, e in dag.iter_edges():
        ins = e.get("inputs") or []
        if root in ins and e.get("op") == "refine":
            out |= _descendants(dag, e.get("output", ""), nodes, seen)
    return out


def _terminal_sets(dag):
    """leaves grouped by how they closed: standard-parts / printable /
    process-family / open."""
    from .goals import _closed_nodes, _out_edges
    closed = _closed_nodes(dag)
    nodes = dict(dag.iter_nodes())
    stats = {"standard-parts": 0, "printable": 0, "process-family": 0,
             "open": 0}
    for d, p in nodes.items():
        if p.get("role") != "Part" or d not in closed:
            if p.get("role") == "Part" and d not in closed:
                stats["open"] += 1
            continue
        how = _how_closed(dag, d)
        stats[how] = stats.get(how, 0) + 1
    return stats


def _how_closed(dag, d):
    for _, e in dag.iter_edges():
        if d in (e.get("inputs") or []):
            if e.get("op") in ("exact", "procure"):
                return "standard-parts"
            if (e.get("transform") or {}).get("name") == "print":
                return "printable"
            if e.get("op") == "manufacture":
                return "process-family"
    return "other"


def _mfg_chains(dag):
    """promoted manufacture edges whose args carry a :machine binding,
    and that machine's own compose is promoted (not nominal)."""
    chains = 0
    machines = []
    for _, e in dag.iter_edges():
        if e.get("op") != "manufacture" or e.get("state") != "promoted":
            continue
        targs = (e.get("transform") or {}).get("args") or {}
        mach = targs.get("machine")
        if not mach:
            continue
        try:
            m_d = dag.store.resolve(str(mach))
        except KeyError:
            continue
        # the machine itself must be developed (a promoted compose
        # produced it — not a contract-only node)
        pe = dag.producing_edge(m_d)
        if pe is not None and pe.get("op") == "compose" \
                and pe.get("state") == "promoted":
            chains += 1
            machines.append(m_d)
    return chains, machines


def evaluate(dag, cc: dict) -> list[dict]:
    """Every require -> one obligation (id=case:<key>, hard)."""
    obs = []
    reqs = dict(cc.get("requires") or {})
    for key, want in reqs.items():
        if key == "min-part-decompose-depth":
            total, dec, _ = _part_stats(dag)
            ratio = (dec / total) if total else 0.0
            ok = ratio >= float(want)
            obs.append({"id": f"case:{key}", "prop":
                        f"decomposed-Part ratio {ratio:.2f} >= {want}",
                        "holds": ok, "checker": "casecontract",
                        "detail": "" if ok else
                        "decompose the leaf Parts one level (T4 pattern: "
                        "shell -> panels with flow-down budgets)"})
        elif key == "part-leaf-ratio":
            total, _, leaf = _part_stats(dag)
            ratio = (leaf / total) if total else 0.0
            op, val = want[0], float(want[1])
            ok = ratio <= val if op == "<=" else ratio >= val
            obs.append({"id": f"case:{key}", "prop":
                        f"Part leaf ratio {ratio:.2f} {op} {val}",
                        "holds": ok, "checker": "casecontract",
                        "detail": "" if ok else "too many undecomposed "
                                   "Part leaves — split the major ones"})
        elif key == "termination":
            stats = _terminal_sets(dag)
            bad = {k: v for k, v in stats.items()
                   if k not in want and v > 0}
            ok = not bad
            obs.append({"id": "case:termination", "prop":
                        f"leaf terminations within {want} (open={stats['open']})",
                        "holds": ok, "checker": "casecontract",
                        "detail": "" if ok else
                        f"leaves closed outside the allowed sets: {bad}"})
        elif key == "manufacturing-chains":
            # DSL forms give either a bare count or a dict {n, with-machine}
            if isinstance(want, dict):
                n_want = int(want.get("n", 1))
                with_mach = bool(want.get("with-machine", True))
            else:
                n_want = int(want)
                with_mach = True
            chains, machines = _mfg_chains(dag)
            ok = chains >= n_want if with_mach else chains >= n_want
            obs.append({"id": "case:manufacturing-chains", "prop":
                        f"promoted :machine chains {chains} >= {n_want}",
                        "holds": ok, "checker": "casecontract",
                        "detail": "" if ok else
                        "no promoted manufacturing chain with a developed "
                        ":machine — add one (SHA-PEK mill-branch pattern) "
                        "or waive with a stated reason"})
        elif key == "sim-matrix":
            missing = []
            by_role = {}
            for _, e in dag.iter_edges():
                if e.get("op") != "evaluate" or e.get("state") != "promoted":
                    continue
                solver = (e.get("transform") or {}).get("name", "")
                ins = e.get("inputs") or []
                if not ins:
                    continue
                tgt = dag.store.get_object(ins[0])["payload"]
                by_role.setdefault(tgt.get("role"), set()).add(solver)
            for role, solver in want:
                if solver not in by_role.get(role, set()):
                    missing.append(f"{role}/{solver}")
            obs.append({"id": "case:sim-matrix", "prop":
                        f"sim matrix covers {len(want)} pairs",
                        "holds": not missing, "checker": "casecontract",
                        "detail": "" if not missing else
                        f"missing eval evidence: {missing}"})
        elif key == "reference-fidelity":
            max_i = int((want or {}).get("issues-max", 2))            if isinstance(want, dict) else int(want)
            issues = None
            for _, e in dag.iter_edges():
                if e.get("op") == "review" and e.get("state") == "promoted":
                    issues = sum(1 for o in
                                 (e.get("certificate") or {})
                                 .get("obligations", [])
                                 if o.get("holds") is False)
            ok = issues is not None and issues <= max_i
            obs.append({"id": "case:reference-fidelity", "prop":
                        f"review issues {issues} <= {max_i}",
                        "holds": ok, "checker": "casecontract",
                        "detail": "" if ok else
                        ("no review edge yet — run fk review --vs <ref>"
                         if issues is None else
                         f"{issues} issues exceed {max_i}")})
    return obs
