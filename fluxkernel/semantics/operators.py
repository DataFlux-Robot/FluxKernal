"""L3: the operator engine — every tactic = one edge (impl plan §7 + v1.1/v1.2).

Shared execution skeleton for all operators:
  1. preconditions (per-op table) — failure => obligation holds=False => the
     edge is still committed but REJECTED (informative failure, kept forever)
  2. flow-down: contract obligations handed down from parent to child
  3. L2 plugin executes the transform -> (node_fields, evidence, obligations)
  4. structural obligations (input-verified / role-transition-legal /
     budget-closed) + contract arithmetic (C1–C4, medium ledger)
  5. certificate binding -> DAG.commit (fail-closed lifecycle, lint-gated)

Lean reading: refine≈refine tactic, compose≈eliminator/回装, abstract≈回退重开,
evaluate≈weakened native_decide, exact≈`exact lemma` from the catalog (Mathlib
位格), procure≈axiom introduction, manufacture≈转向新证明义务族,
integrate (v1.1)≈one lemma closing several goals / shared `let` subterm.
"""
from __future__ import annotations

import copy
import time

from ..core.objects import (Edge, Node, Certificate, ResourceVector, Obligation, ROLES)
from ..core.dag import DAG, DagError
from ..store.objstore import Store
from .ontology import transition_legal
from . import contracts
from .contracts import ContractError, parse_bound


class PluginCtx:
    """What untrusted L2 plugins may see: the store (for blobs) + a logger."""

    def __init__(self, store: Store, journal: list):
        self.store = store
        self._journal = journal

    def say(self, msg: str) -> None:
        self._journal.append(str(msg))


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


_PLUGINS_LOADED = False


def load_plugins() -> list[str]:
    """Import all solver modules so their @register decorators fire.
    OCP-dependent modules keep OCP imports lazy (inside functions), so this
    never fails on machines where the geometry backend is unavailable."""
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return []
    failed = []
    from ..solvers import sketch2d, registry  # noqa: F401
    for mod in ("feature3d", "mission", "mate", "dfam", "process", "line",
                "catalog", "cosim"):
        try:
            __import__(f"fluxkernel.solvers.{mod}", fromlist=["*"])
        except Exception as e:  # missing optional backend etc.
            failed.append(f"{mod}: {e}")
    _PLUGINS_LOADED = True
    return failed


class Engine:
    def __init__(self, store: Store, load: bool = True):
        self.store = store
        self.dag = DAG(store)
        self.dag.add_promotion_gate(contracts.make_lint_gate(store))
        self.journal: list[str] = []
        self.plugin_failures = load_plugins() if load else []

    # ------------------------------------------------------------ helpers --
    def _pctx(self) -> PluginCtx:
        return PluginCtx(self.store, self.journal)

    def _commit(self, edge: Edge, node: Node, cert: Certificate,
                resources: ResourceVector, edge_name=None, node_name=None) -> dict:
        ed, nd = self.dag.commit_edge(edge, node, cert, resources,
                                      edge_name=edge_name, node_name=node_name)
        line = f"{edge.op:11s} {edge_name or ed[8:20]} -> {node.kind}:{nd[8:20]} [{edge.state}]"
        if edge.reason:
            line += f"  {edge.reason}"
        self.journal.append(line)
        return {"edge": ed, "node": nd, "state": edge.state, "reason": edge.reason,
                "obligations": [o.to_dict() for o in cert.obligations]}

    def _input(self, ref: str) -> tuple[str, dict]:
        d, node = self.dag.get_node(ref)
        return d, node.payload()

    @staticmethod
    def _plugin(transform_name: str):
        from ..solvers import registry
        return registry.get(transform_name)

    def _structural_obligations(self, parent_payload: dict | None,
                                child_role: str) -> list[Obligation]:
        obs = [Obligation(id="input-verified", prop="inputs produced by promoted edges",
                          holds=True, checker="core", detail="")]
        if parent_payload is not None:
            legal = transition_legal(parent_payload.get("role"), child_role)
            obs.append(Obligation(
                id="role-transition-legal",
                prop=f"{parent_payload.get('role')} -> {child_role} legal",
                holds=legal, checker="ontology",
                detail="" if legal else "T2: illegal role transition"))
        return obs

    def _call_plugin(self, transform: dict, input_payloads: list[dict]):
        name = transform.get("name", "")
        fn = self._plugin(name)
        return fn(input_payloads, transform.get("args") or {}, self._pctx())

    def _make_edge(self, op: str, inputs: list[str], transform: dict,
                   coverage: dict | None = None) -> Edge:
        return Edge(op=op, inputs=inputs, transform=transform, output="",
                    coverage=coverage or {})

    # ------------------------------------------------------------ genesis --
    def node(self, name: str, role: str, kind: str, spec: dict,
             params: dict | None = None, variants: list | None = None,
             facet: str = "BODY") -> str:
        if role not in ROLES:
            raise DagError("T2", f"unknown role: {role}")
        n = Node(role=role, kind=kind, spec=spec or {},
                 params=params or {}, variants=variants or [], facet=facet)
        d = self.dag.put_node(n, name)
        self.journal.append(f"node        {name} = {role}/{kind} {d[8:20]}")
        return d

    # ------------------------------------------------------------- refine --
    def refine(self, goal, transform: dict, out_name: str | None = None,
               out_role: str | None = None, out_kind: str | None = None,
               out_spec: dict | None = None, out_params: dict | None = None,
               resources: dict | None = None) -> dict:
        """refine = one collapse step (add constraints / pick a variant / ground
        params). `goal` may be a single ref or a list of refs (boolean ops take
        multiple grounded inputs; the first is the primary parent for flow-down).
        transform {"name": "decompose"} fans out children like the .fcad
        `(decompose :into ...)` form. out_spec/out_params NARROW the parent
        (deep-merge), never replace it."""
        goals = list(goal) if isinstance(goal, (list, tuple)) else [goal]
        resolved = [self._input(g) for g in goals]
        goal_d, goal_payload = resolved[0]
        child_role = out_role or goal_payload.get("role", "Component")

        if transform.get("name") == "decompose":
            return self._decompose(goal_d, goal_payload, transform,
                                   out_name, child_role, resources)

        # -- execute the transform (plugin if registered, else structural) --
        obligations: list[Obligation] = []
        parent_spec = goal_payload.get("spec", {})
        base_spec = _deep_merge(parent_spec, out_spec) if out_spec is not None \
            else parent_spec
        from ..solvers import registry
        tname = transform.get("name", "")
        if tname == "param-perturb":
            # kernel-native: collapse holes to the declared values
            fields = {"params": _deep_merge(goal_payload.get("params") or {},
                                            transform.get("args", {}).get("values") or {})}
            evidence = [{"solver": "kernel/param-perturb", "tier": 0,
                         "values": transform.get("args", {}).get("values", {})}]
            plugin_obs = []
        elif tname == "select-variant":
            # kernel-native: collapse the variant space to the chosen variant
            choice = transform.get("args", {}).get("choice")
            fields = {"spec": {"variant": choice}, "variants": []}
            evidence = [{"solver": "kernel/select-variant", "tier": 0,
                         "choice": choice}]
            plugin_obs = []
        elif tname and tname in registry.available():
            try:
                fields, evidence, plugin_obs = self._call_plugin(
                    transform, [p for _, p in resolved])
                plugin_obs = [o if isinstance(o, Obligation) else Obligation.from_dict(o)
                              for o in plugin_obs]
            except (ContractError, ValueError, RuntimeError, KeyError) as e:
                fields, evidence = {}, []
                plugin_obs = [Obligation(id="solver-ran", prop=str(e), holds=False,
                                         checker=tname, detail="E1")]
        else:
            fields, evidence = {}, [{"solver": "kernel/structural",
                                     "transform": tname,
                                     "args": transform.get("args", {}), "tier": 0}]
            plugin_obs = []

        child_spec = _deep_merge(base_spec, fields.get("spec") or {})
        child = Node(role=child_role,
                     kind=out_kind or fields.get("kind") or goal_payload.get("kind", "part"),
                     spec=child_spec,
                     params=_deep_merge(_deep_merge(goal_payload.get("params") or {},
                                                    out_params or {}),
                                        fields.get("params") or {}),
                     variants=fields.get("variants", goal_payload.get("variants", [])),
                     ground=fields.get("ground") or goal_payload.get("ground"),
                     supersedes=(transform.get("args") or {}).get("supersedes", []))

        obligations += self._structural_obligations(goal_payload, child_role)
        obligations += plugin_obs
        obligations += contracts.flow_down_obligations(goal_payload.get("spec", {}),
                                                       child_spec)
        cert = Certificate(obligations=obligations, evaluator="kernel",
                           evidence=evidence, executor=transform.get("name", "structural"))
        edge = self._make_edge("refine", [d for d, _ in resolved], transform)
        res = self._commit(edge, child, cert, ResourceVector(**(resources or {})),
                           edge_name=None, node_name=out_name)
        res["children"] = []
        return res

    def _decompose(self, goal_d: str, goal_payload: dict, transform: dict,
                   out_name: str | None, child_role: str,
                   resources: dict | None) -> dict:
        """decompose: output = refined parent state (records children), then one
        refine edge per child; children names bind as '<parent>/<slot>'."""
        args = transform.get("args") or {}
        slots = args.get("into") or []
        if not slots:
            raise DagError("S1", "decompose requires :into [...] slots")
        parent_spec = goal_payload.get("spec", {}) or {}
        flow = args.get("flow_down") or {}
        child_specs = args.get("specs") or {}
        roles = args.get("roles") or {}
        kinds = args.get("kinds") or {}

        # parent output node: same contract + structural record of decomposition;
        # the DECLARED out_role wins (e.g. Resource demanded as System, PRSI §3.2)
        parent_out_spec = _deep_merge(parent_spec, {"decomposed_into": slots})
        parent_node = Node(role=child_role or goal_payload.get("role", "System"),
                           kind=goal_payload.get("kind", "system"),
                           spec=parent_out_spec,
                           params=goal_payload.get("params") or {},
                           variants=goal_payload.get("variants") or [])
        obligations = self._structural_obligations(goal_payload,
                                                   child_role or goal_payload.get("role"))
        # budget allocation legality: Σ child slices ≤ parent budget per qty
        for qty, pb in contracts.qty_entries(parent_spec, "budget").items():
            pp = parse_bound(pb)
            pv = pp["hi"] if pp["hi"] is not None else pp["lo"]
            total = 0.0
            for slot in slots:
                sb = (flow.get(slot, {}).get("budget") or {}).get(qty)
                if sb is None:
                    continue
                sp = parse_bound(sb)
                total += sp["hi"] if sp["hi"] is not None else sp["lo"]
            if pv is not None:
                obligations.append(Obligation(
                    id="budget-closed",
                    prop=f"Σ child budget[{qty}]={total:g} ≤ parent {pv:g}",
                    holds=total <= pv + 1e-12, checker="contracts",
                    detail="" if total <= pv + 1e-12 else "allocation exceeds parent budget"))
        cert = Certificate(obligations=obligations, evaluator="kernel",
                           evidence=[{"solver": "kernel/structural",
                                      "transform": "decompose", "into": slots, "tier": 0}],
                           executor="decompose")
        res = self._commit(self._make_edge("refine", [goal_d], transform),
                           parent_node, cert, ResourceVector(**(resources or {})),
                           node_name=out_name)

        # children: inherit contract scaffolding, specialize per slot
        children = []
        for slot in slots:
            role = roles.get(slot) or _default_child_role(goal_payload.get("role"))
            child_spec = _inherit_contract(parent_spec, flow.get(slot, {}),
                                           child_specs.get(slot, {}))
            child = Node(role=role, kind=kinds.get(slot, slot), spec=child_spec,
                         params=_deep_merge(goal_payload.get("params") or {}, {}))
            c_obs = self._structural_obligations(goal_payload, role)
            c_obs += contracts.flow_down_obligations(parent_spec, child_spec)
            c_cert = Certificate(
                obligations=c_obs, evaluator="kernel",
                evidence=[{"solver": "kernel/structural", "transform": "decompose",
                           "slot": slot, "tier": 0}], executor="decompose")
            c_edge = self._make_edge("refine", [res["node"]],
                                     {"name": "decompose", "args": {"slot": slot}})
            c_res = self._commit(c_edge, child, c_cert,
                                 ResourceVector(),
                                 node_name=f"{out_name}/{slot}" if out_name else slot)
            children.append(c_res)
        res["children"] = children
        return res

    # ------------------------------------------------------------- compose --
    def compose(self, inputs: list[str], out_name: str, out_role: str,
                out_kind: str | None = None, out_spec: dict | None = None,
                rollup: dict | None = None, resources: dict | None = None,
                transform_spec: dict | None = None) -> dict:
        children = [self._input(r) for r in inputs]
        child_list = [(d, p.get("spec") or {}) for d, p in children]
        base_spec = out_spec or {}
        spec = _deep_merge({"goals": [], "semantics": [], "assumes": [],
                            "guarantees": [], "budget": {}, "effluent": {},
                            "forbidden": [], "not_responsible": [],
                            "time_scale": None}, base_spec)
        # auto roll-up contract: a composed system inherits the union of its
        # children's contracts (scaffolding verbatim; goals/guarantees union;
        # internal assumes drop out; budgets/effluents sum per qty+medium)
        if not out_spec and child_list:
            spec = _auto_rollup_contract(child_list)

        obligations = []
        for d, p in children:
            obligations += self._structural_obligations({"role": out_role},
                                                        p.get("role", "Component"))
        media = self._referenced_media(child_list)
        for m_d, _ in media:
            led = contracts.ledger(self.dag, m_d)
            obligations += led["obligations"]
        obligations += contracts.compose_obligations(child_list, spec, media)

        # roll-up assertions (V-model right leg): declared parent guarantees
        # must be discharged by aggregated child evidence (soft→evidence vector)
        evidence = []
        for d, p in children:
            evidence += p.get("evidence", [])
        # if the compose declares a solver transform (e.g. line-eval), run it:
        # the plugin grounds the composed system (takt/oee/capacity) and its
        # evidence feeds the roll-up assertions
        transform = {"name": "compose", "args": {}}
        node_ground = None
        node_kind = out_kind or "assembly"
        tname = (transform_spec or {}).get("name", "")
        if tname and tname != "compose":
            from ..solvers import registry
            if tname in registry.available():
                transform = transform_spec
                try:
                    p_fields, p_evidence, p_obs = self._call_plugin(
                        transform_spec, [p for _, p in children])
                    evidence = evidence + p_evidence
                    obligations += [o if isinstance(o, Obligation) else Obligation.from_dict(o)
                                    for o in p_obs]
                    node_ground = p_fields.get("ground")
                    node_kind = out_kind or p_fields.get("kind") or node_kind
                except (ContractError, ValueError, RuntimeError, KeyError) as e:
                    obligations.append(Obligation(id="solver-ran", prop=str(e),
                                                  holds=False, checker=tname,
                                                  detail="E1"))
        if rollup:
            for qty, b in rollup.items():
                val = _metric(evidence, qty)
                bp = parse_bound(b)
                ok = val is not None and _holds_bound(val, bp)
                obligations.append(Obligation(
                    id="rollup-met", prop=f"roll-up {qty}={val} {b}",
                    holds=ok, checker="kernel", oclass="soft",
                    detail="" if ok else f"M1: roll-up {qty} not met"))

        node = Node(role=out_role, kind=node_kind, spec=spec, ground=node_ground)
        cert = Certificate(obligations=obligations, evaluator="kernel",
                           evidence=evidence or [{"solver": "kernel/compose",
                                                  "children": [d for d, _ in children],
                                                  "tier": 0}], executor="compose")
        return self._commit(self._make_edge("compose", [d for d, _ in children],
                                            transform),
                            node, cert, ResourceVector(**(resources or {})),
                            node_name=out_name)

    # ----------------------------------------------------------- integrate --
    def integrate(self, inputs: list[str], out_name: str, closes: list[str],
                  from_ref: str | None = None, match: str = "",
                  out_role: str = "Component", out_kind: str | None = None,
                  out_spec: dict | None = None,
                  resources: dict | None = None) -> dict:
        """v1.1 §13: one node closing goals from DIFFERENT subtrees (diamond).
        interface-union-consistent = budget/effluent union has no contradictions
        + C1–C4 over the union; every closed ancestor goal verified separately."""
        children = [self._input(r) for r in inputs]
        child_list = [(d, p.get("spec") or {}) for d, p in children]
        spec = out_spec or _auto_rollup_contract(child_list)

        obligations = []
        # union consistency: same qty, non-contradictory directions/bounds
        for slot in ("budget", "effluent"):
            seen: dict[str, tuple[float, float]] = {}
            for d, s in child_list:
                for q, b in contracts.qty_entries(s, slot).items():
                    p = parse_bound(b)
                    v = p["hi"] if p["hi"] is not None else p["lo"]
                    if q in seen and abs(seen[q][0] - v) > 1e-12:
                        obligations.append(Obligation(
                            id="interface-union-consistent",
                            prop=f"{slot}[{q}] consistent across merged subtrees",
                            holds=False, checker="contracts",
                            detail=f"U2: {q} declared {seen[q][0]:g} and {v:g}"))
                    seen[q] = (v, v)
        media = self._referenced_media(child_list)
        for m_d, _ in media:
            led = contracts.ledger(self.dag, m_d)
            obligations += led["obligations"]
        obligations += contracts.compose_obligations(child_list, spec, media)

        # coverage map: every closed goal verified separately (not just common ancestor)
        coverage = {}
        evidence = [{"solver": "kernel/integrate",
                     "inputs": [d for d, _ in children], "tier": 0}]
        if from_ref and match:
            try:
                entry_fields, entry_ev, entry_obs = self._call_plugin(
                    {"name": "catalog-match", "args": {"from": from_ref, "match": match}},
                    [p for _, p in children])
                evidence += entry_ev
                obligations += [o if isinstance(o, Obligation) else Obligation.from_dict(o)
                                for o in entry_obs]
                spec = _deep_merge(spec, entry_fields.get("spec") or {})
            except (KeyError, ContractError, ValueError) as e:
                obligations.append(Obligation(id="catalog-hit", prop=str(e),
                                              holds=False, checker="catalog",
                                              detail="E1: catalog match failed"))
        for g in closes:
            try:
                g_d, g_payload = self._input(g)
                covered = _spec_superset(spec, g_payload.get("spec") or {})
                obligations.append(Obligation(
                    id="goal-covered",
                    prop=f"integrated node covers ancestor goal {g_d[:20]}…",
                    holds=covered, checker="contracts",
                    detail="" if covered else "integrated item spec does not ⊇ goal spec"))
                coverage[g_d] = evidence[0].get("solver", "kernel/integrate")
            except (KeyError, DagError) as e:
                obligations.append(Obligation(id="goal-covered", prop=str(g),
                                              holds=False, checker="contracts",
                                              detail=f"I1: {e}"))

        node = Node(role=out_role, kind=out_kind or "integrated-part", spec=spec)
        cert = Certificate(obligations=obligations, evaluator="kernel",
                           evidence=evidence, executor="integrate")
        res = self._commit(self._make_edge("integrate", [d for d, _ in children],
                                           {"name": "integrate",
                                            "args": {"closes": closes,
                                                     "from": from_ref, "match": match}}),
                           node, cert, ResourceVector(**(resources or {})),
                           node_name=out_name)
        res["coverage"] = coverage
        return res

    # ----------------------------------------------------------- abstract --
    def abstract(self, node_ref: str, back_to: str | None = None,
                 reason: str = "") -> dict:
        """Non-destructive retreat: re-reference an ancestor (or copy the node
        as a branch point); history stays as evidence. Superseding happens on
        the NEXT refine via args.supersedes."""
        n_d, n_payload = self._input(node_ref)
        if back_to:
            a_d, a_payload = self._input(back_to)
            target, t_payload, t_name = a_d, a_payload, back_to
        else:
            target, t_payload, t_name = n_d, n_payload, node_ref
        node = Node(**{**t_payload, "lineage": []})
        obs = [Obligation(id="retreat-legal", prop="abstract always allowed",
                          holds=True, checker="core", detail=reason)]
        cert = Certificate(obligations=obs, evaluator="kernel",
                           evidence=[{"solver": "kernel/structural", "op": "abstract",
                                      "back_to": back_to, "reason": reason, "tier": 0}],
                           executor="abstract")
        edge = self._make_edge("abstract", [n_d],
                               {"name": "abstract",
                                "args": {"back_to": back_to, "reason": reason}})
        return self._commit(edge, node, cert, ResourceVector(),
                            node_name=f"{t_name}#a{int(time.time())}")

    # ----------------------------------------------------------- evaluate --
    def evaluate(self, target: str, solver: str, fidelity: int = 0,
                 expect: dict | None = None, args: dict | None = None,
                 resources: dict | None = None) -> dict:
        """Weakened native_decide: run an L2 evaluation plugin; expect
        assertions become machine-checked obligations (M1 on miss). The
        evaluated node is a NEW digest (evidence enters identity); the
        target's name rebinds to it so later forms see the current state."""
        t_d, t_payload = self._input(target)
        was_named = not target.startswith("fk1:")
        transform = {"name": solver,
                     "args": {**(args or {}), "fidelity": fidelity}}
        obligations: list[Obligation] = []
        try:
            fields, evidence, plugin_obs = self._call_plugin(transform, [t_payload])
            plugin_obs = [o if isinstance(o, Obligation) else Obligation.from_dict(o)
                          for o in plugin_obs]
        except KeyError:
            raise DagError("E1", f"no solver plugin registered: {solver}")
        except (ContractError, ValueError, RuntimeError, IndexError) as e:
            fields, evidence = {}, [{"solver": solver, "tier": fidelity, "failed": str(e)}]
            plugin_obs = [Obligation(id="solver-ran", prop=str(e), holds=False,
                                     checker=solver, detail="E1")]
        obligations += plugin_obs
        for qty, b in (expect or {}).items():
            val = _metric(evidence, qty)
            bp = parse_bound(b)
            ok = val is not None and _holds_bound(val, bp)
            obligations.append(Obligation(
                id="expect-met", prop=f"{qty}={val} {b}",
                holds=ok, checker="kernel",
                detail="" if ok else f"M1: {qty}={val} violates {b}"))

        merged = _deep_merge(t_payload, fields)
        merged["evidence"] = list(t_payload.get("evidence", [])) + evidence
        node = Node(**{**merged, "lineage": []})
        cert = Certificate(obligations=obligations, evaluator=solver,
                           evidence=evidence, executor=solver)
        edge = self._make_edge("evaluate", [t_d], transform)
        res = self._commit(edge, node, cert, ResourceVector(**(resources or {})))
        if was_named and res["state"] in ("promoted", "verified", "evidenced"):
            self.store.bind_name(target, res["node"])
        return res

    # --------------------------------------------------- exact / procure --
    def _close_from_catalog(self, op: str, goal: str, catalog: str, match: str,
                            tier: int, out_name: str | None = None) -> dict:
        g_d, g_payload = self._input(goal)
        obligations: list[Obligation] = []
        evidence: list[dict] = []
        fields: dict = {}
        try:
            fields, evidence, plugin_obs = self._call_plugin(
                {"name": "catalog-match", "args": {"from": catalog, "match": match}},
                [g_payload])
            plugin_obs = [o if isinstance(o, Obligation) else Obligation.from_dict(o)
                          for o in plugin_obs]
            obligations += plugin_obs
            entry_spec = fields.get("spec") or {}
            obligations.append(Obligation(
                id="spec-superset",
                prop=f"catalog entry spec ⊇ goal spec ({match!r})",
                holds=_spec_superset(entry_spec, g_payload.get("spec") or {}),
                checker="contracts", detail=""))
        except (KeyError, ContractError, ValueError) as e:
            obligations.append(Obligation(id="catalog-hit", prop=str(e), holds=False,
                                          checker="catalog", detail="E1: no catalog hit"))
        evidence = evidence or [{"solver": "catalog", "query": match, "tier": tier}]
        # the closed design keeps the goal's FULL contract (so lint still
        # passes) and gains the entry's guarantees/catalog provenance
        spec = _deep_merge(g_payload.get("spec") or {}, fields.get("spec") or {})
        node = Node(role=g_payload.get("role", "Part"),
                    kind=fields.get("kind") or g_payload.get("kind", "part"),
                    spec=spec, ground=fields.get("ground"),
                    evidence=evidence)
        cert = Certificate(obligations=obligations, evaluator="catalog",
                           evidence=evidence, executor=op)
        edge = self._make_edge(op, [g_d], {"name": "catalog-match",
                                           "args": {"from": catalog, "match": match}})
        res = self._commit(edge, node, cert, ResourceVector(), node_name=out_name)
        res["coverage"] = {g_d: evidence[0].get("solver", "catalog")}
        return res

    def exact(self, goal: str, catalog: str, match: str,
              out_name: str | None = None) -> dict:
        """`exact lemma`: a catalog design closes the goal directly."""
        return self._close_from_catalog("exact", goal, catalog, match, tier=1,
                                        out_name=out_name)

    def procure(self, goal: str, catalog: str, match: str = "",
                out_name: str | None = None) -> dict:
        """Axiom introduction: purchased item; evidence tier=procured(2) ≠ verified."""
        return self._close_from_catalog("procure", goal, catalog,
                                        match or g_default_query(goal), tier=2,
                                        out_name=out_name)

    # --------------------------------------------------------- manufacture --
    def manufacture(self, part: str, into: list[str] | None = None,
                    args: dict | None = None, resources: dict | None = None,
                    out_name: str | None = None) -> dict:
        """Part -> Process family: the part goal pivots into a new obligation
        family (machining ops). Children bind as '<out>/<op>' and each op
        carries its own grounded takt/cost so line-eval can roll them up."""
        p_d, p_payload = self._input(part)
        if p_payload.get("role") != "Part":
            raise DagError("T2", "manufacture requires a Part input")
        transform = {"name": "process-plan",
                     "args": {**(args or {}), "into": into or []}}
        obligations: list[Obligation] = []
        try:
            fields, evidence, plugin_obs = self._call_plugin(transform, [p_payload])
            plugin_obs = [o if isinstance(o, Obligation) else Obligation.from_dict(o)
                          for o in plugin_obs]
            obligations += plugin_obs
        except KeyError:
            fields, evidence = {}, [{"solver": "kernel/structural", "tier": 0}]
        plan_spec = _inherit_contract(p_payload.get("spec") or {}, {},
                                      fields.get("spec") or {})
        node = Node(role="Process", kind=fields.get("kind") or "process-plan",
                    spec=plan_spec, ground=fields.get("ground"))
        obligations += self._structural_obligations(p_payload, "Process")
        cert = Certificate(obligations=obligations, evaluator="process",
                           evidence=evidence, executor="process-plan")
        res = self._commit(self._make_edge("manufacture", [p_d], transform),
                           node, cert, ResourceVector(**(resources or {})),
                           node_name=out_name)
        children = []
        op_details = ((fields.get("ground") or {}).get("op_details")
                      or [{"op": op, "takt_min": 1.0, "cost": 0.0} for op in (into or [])])
        p_guarantees = (p_payload.get("spec") or {}).get("guarantees") or []
        for det in op_details:
            op = det.get("op", "?")
            op_spec = _inherit_contract(p_payload.get("spec") or {},
                                        {"guarantees": p_guarantees}, {})
            op_node = Node(role="Process", kind=op, spec=op_spec,
                           ground={"type": "process-op", "takt_min": det.get("takt_min", 1.0),
                                   "cost": det.get("cost", 0.0)})
            c_cert = Certificate(
                obligations=self._structural_obligations(p_payload, "Process"),
                evaluator="process",
                evidence=[{"solver": "process/rules", "op": op, "tier": 0,
                           "takt_min": det.get("takt_min", 1.0),
                           "cost": det.get("cost", 0.0)}])
            c_res = self._commit(
                self._make_edge("refine", [res["node"]],
                                {"name": "process-op", "args": {"op": op}}),
                op_node, c_cert, ResourceVector(),
                node_name=f"{out_name or part}/{op}")
            children.append(c_res)
        res["children"] = children
        return res

    # -------------------------------------------------------------- realize --
    def realize(self, root: str, until: str = "standard-part",
                max_steps: int = 64) -> dict:
        """Combinator tactic: repeat (decompose <;> try-exact <;> eval) until
        every open leaf goal closes by exact/procure. Terminates: no new
        decompositions are invented; bounded by max_steps."""
        from .goals import open_goals_under
        closed = []
        for _ in range(max_steps):
            open_leaves = [g for g in open_goals_under(self.dag, root)
                           if g["role"] in ("Part", "Component")]
            if not open_leaves:
                return {"done": True, "closed": closed, "steps": len(closed)}
            progressed = False
            for g in open_leaves:
                query = _realize_query(g)
                for op in ("exact", "procure"):
                    res = getattr(self, op)(g["ref"], "catalog", query)
                    closed.append({"goal": g["ref"], "op": op,
                                   "state": res["state"]})
                    if res["state"] == "promoted":
                        progressed = True
                        break
            if not progressed:
                return {"done": False, "closed": closed, "steps": len(closed),
                        "reason": "no catalog hit for remaining leaves"}
        return {"done": False, "closed": closed, "steps": len(closed),
                "reason": "max_steps exceeded"}

    # ------------------------------------------------------------- private --
    def _referenced_media(self, child_list) -> list[tuple[str, dict]]:
        """(digest, medium NODE payload) for every Medium referenced by the
        children's budget/effluent declarations."""
        media = []
        for _, s in child_list:
            for slot in ("budget", "effluent"):
                for q, b in contracts.qty_entries(s, slot).items():
                    m = parse_bound(b)["medium"]
                    if m and all(d != m for d, _ in media):
                        try:
                            obj = self.store.get_object(m)
                            media.append((m, obj["payload"]))
                        except KeyError:
                            pass
        return media


# ---------------------------------------------------------------- helpers --
def _default_child_role(parent_role: str | None) -> str:
    return {"Intent": "System", "System": "Component", "Component": "Part",
            "Part": "Process", "Process": "Line", "Line": "Resource",
            "Resource": "Component"}.get(parent_role or "", "Component")


def _inherit_scaffolding(parent_spec: dict) -> dict:
    """Contract scaffolding a child inherits verbatim: semantics, time scale,
    forbidden list, not_responsible."""
    p = parent_spec or {}
    return {k: copy.deepcopy(p[k]) for k in
            ("semantics", "time_scale", "forbidden", "not_responsible")
            if p.get(k)}


def _auto_rollup_contract(child_list: list[tuple[str, dict]]) -> dict:
    """Derived contract of a composed system (used when the caller declares
    none): union of goals/guarantees/forbidden; assumes that are NOT covered
    by a sibling guarantee stay as the system's environmental assumes;
    budgets/effluents sum per quantity (keeping medium refs)."""
    spec = _inherit_scaffolding(child_list[0][1] if child_list else {})
    goals, guarantees, assumes = [], [], []
    for _, s in child_list:
        goals += copy.deepcopy(s.get("goals") or [])
        guarantees += copy.deepcopy(s.get("guarantees") or [])
        assumes += copy.deepcopy(s.get("assumes") or [])
    kept_assumes = []
    for entry in assumes:
        covered = False
        for q, b in (entry.get("bounds") or {}).items():
            for _, ps in child_list:
                for ge in contracts.entry_bounds(ps, "guarantees"):
                    if q in (ge.get("bounds") or {}):
                        cov, _ = contracts.covers(b, ge["bounds"][q])
                        covered = covered or cov
        if not covered:
            kept_assumes.append(entry)
    spec["goals"] = goals
    spec["guarantees"] = guarantees
    spec["assumes"] = kept_assumes or assumes[:1]
    for slot in ("budget", "effluent"):
        sums: dict = {}
        for _, s in child_list:
            for q, b in contracts.qty_entries(s, slot).items():
                p = parse_bound(b)
                v = p["hi"] if p["hi"] is not None else p["lo"]
                if v is None:
                    continue
                key = (q, p["medium"])
                prev = sums.get(key)
                sums[key] = prev + v if prev is not None else v
        spec[slot] = {q: ({"op": "<=", "value": v, "medium": m} if m else ["<=", v])
                      for (q, m), v in sums.items()}
    return spec


def _inherit_contract(parent_spec: dict, flow: dict, explicit: dict) -> dict:
    """Build a child contract: scaffolding + env assumes from parent +
    guarantees/budget from flow-down allocations + explicit overrides."""
    p = parent_spec or {}
    spec = _inherit_scaffolding(p)
    spec["assumes"] = copy.deepcopy(p.get("assumes", []))
    parent_goals = copy.deepcopy(p.get("goals", []))
    for g in parent_goals:
        g["stmt"] = f"[{g.get('id')}] " + g.get("stmt", "")
    spec["goals"] = parent_goals
    if flow.get("guarantees"):
        spec["guarantees"] = flow["guarantees"]
    if flow.get("budget"):
        spec["budget"] = flow["budget"]
    if flow.get("assumes"):
        spec.setdefault("assumes", [])
        spec["assumes"] = copy.deepcopy(flow["assumes"])
    if p.get("param_bounds"):
        spec["param_bounds"] = copy.deepcopy(p["param_bounds"])
    return _deep_merge(spec, explicit)


def _metric(evidence: list, name: str):
    """Look a metric up in flattened evidence dicts (last write wins)."""
    val = None
    for e in evidence or []:
        if isinstance(e, dict) and name in e:
            val = e[name]
    return val


def _holds_bound(val, bp: dict) -> bool:
    ok = True
    if bp["lo"] is not None:
        ok = ok and val >= bp["lo"] - 1e-12
    if bp["hi"] is not None:
        ok = ok and val <= bp["hi"] + 1e-12
    return ok


def _spec_superset(entry_spec: dict, goal_spec: dict) -> bool:
    """Does the catalog/integrated entry cover every quantity the goal demands?

    For each demanded bound (budget dict entries + guarantee/assume entry
    bounds), some entry bound of the same qty must ADMIT it: the entry's
    capability interval intersects the demand (a motor rated 3000–24000 rpm
    satisfies 'rpm>=12000' — it can operate there). Disjoint = not covered."""
    demands: list[tuple[str, object]] = []
    for slot in ("budget", "assumes", "guarantees"):
        for q, b in contracts.qty_entries(goal_spec, slot).items():
            demands.append((q, b))
        for e in contracts.entry_bounds(goal_spec, slot):
            for q, b in (e.get("bounds") or {}).items():
                demands.append((q, b))
    supply: dict[str, list] = {}
    for slot in ("budget", "assumes", "guarantees"):
        for q, b in contracts.qty_entries(entry_spec, slot).items():
            supply.setdefault(q, []).append(b)
        for e in contracts.entry_bounds(entry_spec, slot):
            for q, b in (e.get("bounds") or {}).items():
                supply.setdefault(q, []).append(b)
    for q, gb in demands:
        for cand in supply.get(q, []):
            _, disjoint = contracts.covers(gb, cand)
            if not disjoint:
                break          # some supply interval intersects the demand
        else:
            if supply.get(q):
                return False   # qty supplied but every interval misses the demand
            # qty not supplied at all: not promised => vacuous
    return True


def g_default_query(goal: str) -> str:
    return goal


def _realize_query(goal_view: dict) -> str:
    """Derive a catalog query from a goal's guarantee bounds
    ('torque_nm>=8 rpm>=12000' style)."""
    parts = []
    spec = goal_view.get("spec") or {}
    for e in contracts.entry_bounds(spec, "guarantees"):
        for q, b in (e.get("bounds") or {}).items():
            p = parse_bound(b)
            if p["hi"] is not None:
                parts.append(f"{q}<={p['hi']:g}")
            elif p["lo"] is not None:
                parts.append(f"{q}>={p['lo']:g}")
    return " ".join(parts)
