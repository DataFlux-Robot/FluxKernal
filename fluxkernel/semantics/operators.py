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
from pathlib import Path

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
    for mod in ("feature3d", "features", "mission", "mate", "dfam",
                "process", "line", "catalog", "cosim", "sims"):
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
    def params_set(self, name: str, defs: dict) -> str:
        """(params <name> ((k v)...)): a named single-source parameter set —
        a content-addressed genesis object (kind=params, outside the role
        ontology like terms).  Path references 'name/key' resolve through
        it.  Definitions may be numbers, param refs or expressions."""
        from ..core import params as fkparams
        vals = fkparams.resolve_param_values(defs)   # cycles fail fast here
        node = Node(role="params", kind="params", params=dict(defs),
                    spec={"param_values": vals})
        d = self.dag.put_node(node, name)
        self.journal.append(f"params      {name} = {sorted(vals)} {d[8:20]}")
        return d

    def instantiate(self, at_ref: str, mechanism: str,
                    params: dict | None = None, printer: str | None = None,
                    out_name: str | None = None, features: list | None = None,
                    allow_shape_gap: bool = False) -> dict:
        """(instantiate :at <goal> :mechanism <name> :params ...): expand a
        mechanism package into ORDINARY DAG edges — decompose (computed
        layout+flow-down) -> per-part ground/extrude at computed frames ->
        terminal prints (reserved parts stay open) -> compose recipe.  The
        kernel stays mechanism-agnostic; verify needs no new logic."""
        import json
        from ..core import params as fkparams
        mech_dirs = [Path.cwd() / "mechanisms",
                     Path(__file__).resolve().parents[2] / "mechanisms"]
        decl = None
        for d in mech_dirs:
            f = d / f"{mechanism}.json"
            if f.is_file():
                decl = json.loads(f.read_text(encoding="utf-8"))
                break
        if decl is None:
            raise DagError("S1", f"unknown mechanism {mechanism!r} "
                                 f"(searched mechanisms/)")

        # resolve parameters (defaults may be expressions over the others)
        # param refs (["param", "set/key"]) resolve through the store's
        # parameter sets; literal numbers pass through
        from ..core import params as _fkp

        def _lookup(name):
            if "/" in str(name):
                set_name, key = str(name).split("/", 1)
                p_set = self.store.get_object(
                    self.store.resolve(set_name))["payload"]
                return float((p_set.get("params") or {})[key])
            raise _fkp.ParamError(f"unknown parameter {name!r}")

        def _inline(tree):
            """replace nested ["param", name] refs by their values so the
            expression evaluator only sees numbers and operators"""
            if isinstance(tree, list):
                if tree and tree[0] in ("param", ":param"):
                    return _lookup(str(tree[1]))
                return [_inline(t) for t in tree]
            return tree

        def _pv(v):
            if isinstance(v, list) and v and v[0] in ("param", ":param"):
                return float(_lookup(str(v[1])))
            if isinstance(v, list) and v and v[0] in ("expr", ":expr"):
                return float(_fkp.eval_sexp(_inline(v[1]), _lookup))
            try:
                return float(v)                      # numeric param
            except (TypeError, ValueError):
                return v                             # enum param (e.g. section)

        values = {k: _pv(v) for k, v in (params or {}).items()}
        for k, spec in (decl.get("params") or {}).items():
            if k in values:
                continue
            de = spec.get("default-expr") if isinstance(spec, dict) else None
            if de is not None:
                if isinstance(de, list):
                    try:
                        values[k] = fkparams.eval_sexp(de, lambda n: values.get(n))
                    except fkparams.ParamError:
                        # a bare string default is an enum value, not a
                        # parameter reference
                        values[k] = de
                else:
                    values[k] = de
        for k, spec in (decl.get("params") or {}).items():
            if k not in values or not isinstance(spec, dict):
                continue
            opts = spec.get("options")
            if opts is not None:
                if values[k] not in opts:
                    raise DagError("U3", f"mechanism param {k}={values[k]!r} "
                                         f"not in {opts}")
                continue
            rng = spec.get("range")
            if rng and k in values and not (rng[0] <= values[k] <= rng[1]):
                raise DagError("U3", f"mechanism param {k}={values[k]:g} "
                                     f"outside range {rng}")

        # C5 (D4): shape-gap negotiation — the caller may declare shape
        # features; anything the mechanism does not provide opens an
        # explicit gap (hard reject with the three exit paths) unless
        # :allow-shape-gap t downgrades it to a recorded soft note
        wanted_feats = [str(f) for f in (features or [])]
        provided = set(decl.get("features_provided") or [])
        missing = [f for f in wanted_feats if f not in provided]
        shape_gap_obs = []
        if missing:
            if allow_shape_gap:
                shape_gap_obs.append(Obligation(
                    id="shape-gap", prop=f"features {missing} absent",
                    holds=True, checker="kernel", oclass="soft",
                    detail=f"explicit :allow-shape-gap — mechanism lacks "
                           f"{missing}; upgrade or swap when it matters"))
            else:
                return {"state": "rejected",
                        "reason": "C0: undischarged obligations: shape-gap",
                        "detail": f"missing features {missing}",
                        "hint": "upgrade the mechanism / swap mechanisms / "
                                "hand-write then abstract (fk-mechanism-author)",
                        "children": []}

        import importlib
        mod = importlib.import_module(decl["module"])
        gen = mod.generate(values)
        frames = mod.layout(values)
        into = gen["into"]
        kinds = mod.kinds_of(into)
        # every frame belonging to this part rides its slot spec — the
        # "build" alias plus part-scoped extras (e.g. "skin-cutter")
        specs = {name: {"frames": {
            **{k: v for k, v in frames.items()
               if k == name or k.startswith(name + "-")},
            "build": frames[name]}} for name in into}
        arch_params = {**values,
                       "rib-count": values.get("rib-count",
                                               len([i for i in into
                                                    if i.startswith("rib")]))}

        # 1) decompose with the computed family
        res = self.refine([at_ref],
                          {"name": "decompose", "args": {
                              "into": into,
                              "roles": gen["roles"],
                              "kinds": kinds,
                              "flow_down": gen["flow_down"],
                              "specs": specs,
                              "archetype": f"mech:{mechanism}",
                              "archetype_params": arch_params}},
                          out_name=out_name or f"{mechanism}-v1",
                          out_role=None)   # inherit: Part slots stay Part
        if res["state"] != "promoted":
            return res
        scope = res["node"]
        base = out_name or f"{mechanism}-v1"

        # 2) per-part grounding at computed frames (+ terminal prints).
        #    Part specs: rectangle {w,h,thick} (2.0 compat), polygon
        #    {pts, thick}, or multi-section loft {profiles, zs} — each
        #    optionally followed by a post-op chain (shell/fillet/...)
        def _poly_sketch(poly):
            pts = {f"p{i}": [float(x), float(y)]
                   for i, (x, y) in enumerate(poly)}
            return {"pts": pts, "constraints": []}

        term = decl.get("termination") or {}
        printable = [t for t in term.get("print", [])
                     if t in into and t in frames]
        pr_d = self.store.resolve(printer) if printer else None
        grounded = {}
        for name in into:
            pr = gen["parts"][name]
            if "profiles" in pr:
                sec_nodes = []
                for j, poly in enumerate(pr["profiles"]):
                    r1 = self.refine([f"{base}/{name}"],
                                     {"name": "ground-sketch",
                                      "args": {"sketch": _poly_sketch(poly)}},
                                     out_name=f"{base}/{name}/sec{j}")
                    if r1["state"] != "promoted":
                        return {"state": "rejected",
                                "reason": f"mechanism sketch failed at {name}"
                                          f" sec{j}: {r1['reason']}",
                                "children": []}
                    sec_nodes.append(r1["node"])
                cur = self.refine(sec_nodes,
                                  {"name": "loft",
                                   "args": {"zs": pr.get("zs") or
                                            [0.0] * len(sec_nodes),
                                            "ruled": pr.get("ruled", True),
                                            "material": pr.get("material",
                                                               "aluminum"),
                                            "at": [":frame", "build"]}},
                                  out_name=f"{base}/{name}/solid")
            else:
                if "pts" in pr:
                    sk = _poly_sketch(pr["pts"])
                else:
                    sk = {"pts": {"a": [0, 0], "b": [pr["w"], 0],
                                  "c": [pr["w"], pr["h"]], "d": [0, pr["h"]]},
                          "constraints": [["fix", "a", 0, 0],
                                          ["dist", "a", "b", pr["w"]],
                                          ["dist", "b", "c", pr["h"]],
                                          ["horiz", "a", "b"],
                                          ["vert", "b", "c"]]}
                r1 = self.refine([f"{base}/{name}"],
                                 {"name": "ground-sketch",
                                  "args": {"sketch": sk}},
                                 out_name=f"{base}/{name}/sk")
                if r1["state"] != "promoted":
                    return {"state": "rejected",
                            "reason": f"mechanism grounding failed at {name}: "
                                      f"{r1['reason']}", "children": []}
                cur = self.refine([r1["node"]],
                                  {"name": "extrude",
                                   "args": {"height": pr["thick"],
                                            "material": pr["material"],
                                            "at": [":frame", "build"]}},
                                  out_name=f"{base}/{name}/solid")
            if cur["state"] != "promoted":
                return {"state": "rejected",
                        "reason": f"mechanism solid failed at {name}: "
                                  f"{cur['reason']}", "children": []}
            for post in pr.get("post") or []:
                cur = self.refine([cur["node"]],
                                  {"name": post["name"],
                                   "args": post.get("args", {})},
                                  out_name=f"{base}/{name}/{post['name']}")
                if cur["state"] != "promoted":
                    return {"state": "rejected",
                            "reason": f"mechanism post-op {post['name']} "
                                      f"failed at {name}: {cur['reason']}",
                            "children": []}
            grounded[name] = cur["node"]
            if "cutter" in pr:
                cut_pr = pr["cutter"]
                cut_frame = [":frame", cut_pr.get("frame", "build")]
                if "pts" in cut_pr:
                    rj = self.refine([f"{base}/{name}"],
                                     {"name": "ground-sketch",
                                      "args": {"sketch":
                                               _poly_sketch(cut_pr["pts"])}},
                                     out_name=f"{base}/{name}/cut-sk")
                    if rj["state"] != "promoted":
                        return {"state": "rejected",
                                "reason": f"cutter sketch failed at {name}: "
                                          f"{rj['reason']}", "children": []}
                    cut = self.refine([rj["node"]],
                                      {"name": "extrude",
                                       "args": {"height": cut_pr["thick"],
                                                "material": "aluminum",
                                                "at": cut_frame}},
                                      out_name=f"{base}/{name}/cutter")
                else:
                    cut_nodes = []
                    for j, poly in enumerate(cut_pr["profiles"]):
                        rj = self.refine([f"{base}/{name}"],
                                         {"name": "ground-sketch",
                                          "args": {"sketch":
                                                   _poly_sketch(poly)}},
                                         out_name=f"{base}/{name}/cut-sec{j}")
                        if rj["state"] != "promoted":
                            return {"state": "rejected",
                                    "reason": f"cutter sketch failed at "
                                              f"{name}: {rj['reason']}",
                                    "children": []}
                        cut_nodes.append(rj["node"])
                    cut = self.refine(cut_nodes,
                                      {"name": "loft",
                                       "args": {"zs": cut_pr.get("zs") or
                                                [0.0] * len(cut_nodes),
                                                "ruled": True,
                                                "material": "aluminum",
                                                "at": cut_frame}},
                                      out_name=f"{base}/{name}/cutter")
                if cut["state"] != "promoted":
                    return {"state": "rejected",
                            "reason": f"cutter failed at {name}: "
                                      f"{cut['reason']}", "children": []}
                cur = self.refine([cur["node"], cut["node"]],
                                  {"name": "cut", "args": {}},
                                  out_name=f"{base}/{name}/hollow")
                if cur["state"] != "promoted":
                    return {"state": "rejected",
                            "reason": f"cut failed at {name}: "
                                      f"{cur['reason']}", "children": []}
                grounded[name] = cur["node"]   # the hollow body is the part
            if name in printable and pr_d:
                rp = self.print_part(cur["node"], pr_d,
                                     out_name=f"{base}/{name}/printed")
                if rp["state"] != "promoted":
                    return {"state": "rejected",
                            "reason": f"mechanism print failed at {name}: "
                                      f"{rp['reason']}", "children": []}

        # 3) compose recipe
        recipe = mod.assemble(values)
        inputs = [grounded[n] for n in into]
        rc = self.compose(inputs,
                          out_name=f"{base}/assembly",
                          out_role="Component",
                          out_kind=recipe.get("out_kind", "assembly"),
                          transform_spec=recipe.get("transform"))
        return {"state": rc["state"], "reason": rc.get("reason", ""),
                "node": rc.get("node"), "edge": rc.get("edge"),
                "decompose": res, "assembly": rc,
                "params": values, "mechanism": mechanism}

    def params_override(self, name: str, key: str, value: float) -> str:
        """Re-issue a params set with one definition replaced.  Content-
        addressed: a NEW set object is committed and the name rebinds —
        the old set stays in the store (history is immutable)."""
        old = self.store.get_object(self.store.resolve(name))["payload"]
        defs = dict(old.get("params") or {})
        defs[key] = float(value)
        return self.params_set(name, defs)

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

        # P-layer (M1): resolve :param/:expr leaves in transform args against
        # the input node's parameter context; bindings become edge evidence.
        # Definition-carrying transforms are exempt (their args ARE the defs).
        from ..core import params as fkparams
        p_bindings: list = []
        if transform.get("name", "") not in ("param-perturb", "select-variant",
                                             "decompose"):
            try:
                transform, p_bindings = fkparams.resolve_transform(
                    transform, goal_payload, self.store)
            except fkparams.ParamError as e:
                bad = Node(role=child_role,
                           kind=out_kind or goal_payload.get("kind", "part"),
                           spec=goal_payload.get("spec") or {})
                cert0 = Certificate(
                    obligations=[Obligation(id="param-resolved",
                                            prop="parameter expressions resolve",
                                            holds=False, checker="core/params",
                                            detail=f"U3: {e}")],
                    evaluator="core/params", evidence=[], executor=transform.get("name", ""))
                return self._commit(
                    self._make_edge("refine", [goal_d], transform),
                    bad, cert0, ResourceVector(), node_name=out_name)

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
        elif tname == "scale-instance":
            # E6-3: derive a scaled instance of the WHOLE subtree — gather
            # every grounded solid under the target (promoted edges only,
            # digest-sorted for determinism) and hand them all to the
            # plugin; the edge inputs exact-link every source shape
            sub_ds, sub_payloads = self._subtree_solids(goal_d)
            try:
                fields, evidence, plugin_obs = self._call_plugin(
                    transform, sub_payloads)
                plugin_obs = [o if isinstance(o, Obligation) else Obligation.from_dict(o)
                              for o in plugin_obs]
                extra_inputs = sub_ds
            except (ContractError, ValueError, RuntimeError, KeyError) as e:
                fields, evidence = {}, []
                plugin_obs = [Obligation(id="solver-ran", prop=str(e), holds=False,
                                         checker=tname, detail="E1")]
                extra_inputs = []
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
        obligations += self._policy_obligations(
            {"role": child.role, "kind": child.kind, "spec": child_spec,
             "params": child.params or {}, "ground": child.ground})
        obligations += contracts.flow_down_obligations(goal_payload.get("spec", {}),
                                                       child_spec)
        evidence = evidence + fkparams.bindings_evidence(p_bindings)
        cert = Certificate(obligations=obligations, evaluator="kernel",
                           evidence=evidence, executor=transform.get("name", "structural"))
        edge = self._make_edge(
            "refine", [d for d, _ in resolved] + locals().get("extra_inputs", []),
            transform)
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
        if args.get("template") and not args.get("into"):
            args = _merge_archetype(args, str(args["template"]), self.store)
            transform = {**transform, "args": args}
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
        arch = args.get("archetype")
        arch_params = args.get("archetype_params") or {}
        stamps = {"decomposed_into": slots}
        if arch:
            stamps["archetype"] = arch
            stamps["archetype_params"] = arch_params
        parent_out_spec = _deep_merge(parent_spec, stamps)
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
        cert.obligations += self._policy_obligations(
            {"role": parent_node.role, "kind": parent_node.kind,
             "spec": parent_out_spec, "params": {}, "ground": None})
        res = self._commit(self._make_edge("refine", [goal_d], transform),
                           parent_node, cert, ResourceVector(**(resources or {})),
                           node_name=out_name)

        # children: inherit contract scaffolding, specialize per slot
        children = []
        for slot in slots:
            role = roles.get(slot) or _default_child_role(goal_payload.get("role"))
            child_spec = _inherit_contract(parent_spec, flow.get(slot, {}),
                                           child_specs.get(slot, {}))
            if arch:
                child_spec = _deep_merge(child_spec, {"archetype": arch})
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
                transform_spec: dict | None = None,
                no_geometry: bool = False,
                no_assembly=None) -> dict:
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
        # E6-2b (review v03): a Part composed into a physical assembly
        # must be REALIZED — grounded geometry or a terminal production
        # route.  Composing contract-only paper Parts silently was the
        # wing-assembly bug: the assembly branch and the grounding branch
        # were two disconnected lines.
        for d, p in children:
            if p.get("role") == "Part" and not self._input_realized(d, p):
                obligations.append(Obligation(
                    id="input-realized",
                    prop=f"Part input …{d[24:40]} realized (grounded or terminal)",
                    holds=False, checker="kernel",
                    detail="U2: composing an unrealized Part — ground it or "
                           "close it via catalog/print first"))
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
        # U4 (assembly coverage): referencing a decomposed subsystem in an
        # assembly pulls in its WHOLE terminal artifact set.  Node-level
        # closure (every leaf reaches catalog/print) cannot see the
        # wing-only-aircraft hole — grounded parts dangling off their
        # print edges while the design composes the bare contract node.
        # Hard: the detail lists exactly what is missing.
        if no_assembly:
            evidence = evidence + [{
                "solver": "kernel/compose", "tier": 0,
                "assembly_coverage": "exempted",
                "note": f"explicit :no-assembly exemption: {no_assembly}"}]
        else:
            gaps = self._assembly_gaps(children)
            if gaps:
                obligations.append(Obligation(
                    id="subtree-assembled",
                    prop=f"{len(gaps)} referenced-subtree artifact(s) "
                         f"assembled",
                    holds=False, checker="kernel",
                    detail="U4: terminal parts of a referenced subsystem "
                           "are not in the assembly chain — add them to "
                           ":in (directly or via an intermediate assembly "
                           f"compose): {', '.join(gaps)}"))
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
        # evidence coverage (E0-3, review P3): every guarantee quantity in
        # the composed contract should trace to at least one subtree eval
        # evidence entry — soft: a gap lands in fk risks, never blocks.
        # (contract inheritance can repeat a guarantee along refine chains;
        #  quantities are checked once each)
        _covered = set()
        for g in spec.get("guarantees") or []:
            for q in (g.get("bounds") or {}):
                if q in _covered:
                    continue
                if _metric(evidence, q) is None:
                    obligations.append(Obligation(
                        id="evidence-coverage",
                        prop=f"subtree evidence covers {q}",
                        holds=False, checker="kernel", oclass="soft",
                        detail=f"M2: no subtree evidence for guarantee "
                               f"quantity {q} of '{g.get('id', '?')}'"))
                _covered.add(q)
        if rollup:
            for qty, b in rollup.items():
                val = _metric(evidence, qty)
                bp = parse_bound(b)
                ok = val is not None and _holds_bound(val, bp)
                obligations.append(Obligation(
                    id="rollup-met", prop=f"roll-up {qty}={val} {b}",
                    holds=ok, checker="kernel", oclass="soft",
                    detail="" if ok else f"M1: roll-up {qty} not met"))

        # M4 auto roll-back (review G4/G5): a compose with NO explicit
        # transform and ALL inputs grounded is a physical assembly — run
        # the assemble gate automatically (interference + mass/COM) and
        # MATERIALIZE the assembly ground onto the composed NODE, not just
        # the edge.  Mixed inputs get an honest partial marker; an explicit
        # :no-geometry exemption skips the gate and says so.
        if transform_spec is None and not no_geometry and len(children) >= 2:
            grounded_ins = [p for _, p in children
                            if (p.get("ground") or {}).get("construction")]
            if len(grounded_ins) == len(children):
                try:
                    from ..solvers import registry as _reg
                    _asm = _reg.get("assemble")
                    a_fields, a_ev, a_obs = _asm(
                        [p for _, p in children],
                        {"placements": [[0, 0, 0] for _ in children]},
                        self._pctx())
                    node_ground = a_fields.get("ground") or node_ground
                    node_kind = out_kind or a_fields.get("kind") or node_kind
                    evidence = evidence + a_ev
                    obligations += [Obligation.from_dict(o) for o in a_obs]
                except (ContractError, ValueError, RuntimeError, KeyError,
                        IndexError) as e:
                    obligations.append(Obligation(
                        id="assembly-gate", prop="auto assemble executes",
                        holds=False, checker="assemble",
                        detail=f"E1: {e}"))
            elif not grounded_ins:
                evidence = evidence + [{
                    "solver": "kernel/compose", "tier": 0,
                    "geometry_rollup": "none",
                    "note": "no grounded inputs — contract-level compose; "
                            "ground the parts or declare :no-geometry"}]
            elif all((p.get("ground") or {}).get("mass_g") is not None
                     for _, p in children):
                # nested assembly: the inputs are already-gated inner
                # assemblies / catalog envelopes — materialize the summed
                # mass (interference was checked at the inner level)
                total = sum(float((p.get("ground") or {}).get("mass_g") or 0.0)
                            for _, p in children)
                node_ground = {"type": "assembly", "parts": len(children),
                               "mass_g": round(total, 3),
                               "note": "nested assembly roll-up"}
                evidence = evidence + [{
                    "solver": "kernel/compose", "tier": 0,
                    "geometry_rollup": "nested",
                    "mass_g": round(total, 3),
                    "note": "mass summed from inner assemblies; "
                            "interference owned by the inner gates"}]
            elif grounded_ins:
                evidence = evidence + [{
                    "solver": "kernel/compose", "tier": 0,
                    "geometry_rollup": "partial",
                    "grounded_inputs": len(grounded_ins),
                    "total_inputs": len(children),
                    "note": "not all inputs grounded — no interference "
                            "gate; close or ground them, or declare "
                            ":no-geometry"}]
        elif no_geometry:
            evidence = evidence + [{
                "solver": "kernel/compose", "tier": 0,
                "geometry_rollup": "exempted",
                "note": "explicit :no-geometry exemption"}]

        node = Node(role=out_role, kind=node_kind, spec=spec, ground=node_ground)
        obligations += self._policy_obligations(
            {"role": out_role, "kind": node_kind, "spec": spec,
             "params": {}, "ground": node_ground})
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
                 resources: dict | None = None,
                 informative: bool = False) -> dict:
        """Weakened native_decide: run an L2 evaluation plugin; expect
        assertions become machine-checked obligations (M1 on miss). The
        evaluated node is a NEW digest (evidence enters identity); the
        target's name rebinds to it so later forms see the current state."""
        t_d, t_payload = self._input(target)
        was_named = not target.startswith("fk1:")
        transform = {"name": solver,
                     "args": {**(args or {}), "fidelity": fidelity,
                              "informative": informative}}
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

    # ------------------------------------------- reference-image (CC3/C6) --
    def reference_image(self, path: str, for_ref: str) -> str:
        """Photo bytes into the blob store; a Reference node records the
        provenance (source path, for-ref, tier image-inferred)."""
        import time
        data = Path(path).read_bytes()
        blob_d = self.store.put_blob(data)
        node = Node(role="Reference", kind="reference-image",
                    spec={"blob": blob_d, "source": path,
                          "for": for_ref, "tier": "image-inferred",
                          "captured": time.strftime("%Y-%m-%d %H:%M:%S")})
        d = self.dag.put_node(node, f"@ref-{blob_d[9:17]}")
        self.journal.append(f"reference-image {path} -> {blob_d[9:17]} "
                            f"(for {for_ref or 'library'})")
        return d

    # ------------------------------------------------ case-contract (CC1) --
    def case_contract(self, name: str, typ: str, requires: dict) -> str:
        """Store the case profile as a node (kind=case-contract); the
        closure predicate evaluates it on every goals_view call."""
        from . import casecontract as cc_mod
        node = Node(role="CaseContract", kind="case-contract",
                    spec={"type": typ, "requires": requires})
        d = self.dag.put_node(node, name)
        errs = cc_mod.validate_schema(node.spec)
        if errs:
            self.journal.append(f"case-contract {name} SCHEMA ERRORS: {errs}")
        else:
            self.journal.append(f"case-contract {name} :type {typ} "
                                f"({len(requires)} requires)")
        return d

    # ---------------------------------------------------- review (P7a) --
    def review(self, target: str, findings: list[dict], meta: dict) -> dict:
        """Archive a VLM visual review as a `review` edge on the target.

        RED LINE (spec P7 §B.5): every obligation produced here is class
        "soft" — hardcoded, no parameter, no configuration opening.  A VLM
        opinion never enters C0/U2/U4 or any hard gate.  `fk verify`
        schema-checks these edges (soft-only) and never re-runs the VLM.
        The output node is an archival record (kind=review), not a design
        goal; goals_view filters it like params sets."""
        t_d, t_payload = self._input(target)
        obs = []
        for i, f in enumerate(findings):
            obs.append(Obligation(
                id=str(f.get("id") or f"visual-review-{i:03d}"),
                prop=str(f.get("prop") or "render matches declared intent"),
                holds=bool(f.get("holds", False)),
                checker=str(f.get("checker") or "vlm"),
                oclass="soft",                       # hardcoded — red line
                detail=str(f.get("detail") or "")))
        cert = Certificate(
            obligations=obs, evaluator="vlm",
            evidence=[{"solver": f"vlm/{meta.get('model', '?')}",
                       "tier": "advisory",
                       "images": meta.get("images", []),
                       "vs": meta.get("vs", ""),
                       "intent": meta.get("intent", "")}],
            executor="review")
        node = Node(role="Process", kind="review",
                    spec={"target": t_d, "intent": meta.get("intent", "")},
                    evidence=cert.evidence)
        edge = self._make_edge("review", [t_d],
                               {"name": "visual-review",
                                "args": {"model": meta.get("model", ""),
                                         "views": meta.get("views", [])}})
        return self._commit(edge, node, cert, ResourceVector(),
                            node_name=meta.get("out"))

    # --------------------------------------------------- exact / procure --
    def _close_from_catalog(self, op: str, goal: str, catalog: str, match: str,
                            tier: int, out_name: str | None = None,
                            at=None) -> dict:
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
        # V3: an entry with declared geometry grounds a REPRESENTATIVE
        # envelope (tier catalog-representative).  Red line: mass stays
        # the CATALOG mass; the envelope serves layout/interference only.
        ground = fields.get("ground")
        geo = fields.get("geometry")
        if geo and isinstance(geo, dict):
            try:
                gshape, gcons = self._catalog_envelope(geo)
                if at is not None:
                    from ..solvers.feature3d import _parse_at, _placed
                    pl = _parse_at(at)
                    if pl:
                        gshape = _placed(gshape, pl)
                        gcons = {**gcons, "placement": pl}
                props = self._props_shape(gshape)
                cat_mass = (ground or {}).get("mass_g")
                ground = {"type": "brep", "backend": "ocp",
                          "construction": gcons,
                          "volume_mm3": props["volume_mm3"],
                          "mass_g": cat_mass if cat_mass is not None
                          else props["mass_g"],
                          "com": props["com"], "bbox": props["bbox"],
                          "material": "catalog-representative"}
                evidence = evidence + [{
                    "solver": "catalog/geom", "tier": 0,
                    "note": "representative envelope (not a manufacturer "
                            "model); layout/interference only"}]
            except Exception as e:
                evidence = evidence + [{
                    "solver": "catalog/geom", "tier": 0,
                    "note": f"envelope generation skipped: {e}"}]
        # the closed design keeps the goal's FULL contract (so lint still
        # passes) and gains the entry's guarantees/catalog provenance
        spec = _deep_merge(g_payload.get("spec") or {}, fields.get("spec") or {})
        node = Node(role=g_payload.get("role", "Part"),
                    kind=fields.get("kind") or g_payload.get("kind", "part"),
                    spec=spec, ground=ground,
                    evidence=evidence)
        cert = Certificate(obligations=obligations, evaluator="catalog",
                           evidence=evidence, executor=op)
        edge = self._make_edge(op, [g_d], {"name": "catalog-match",
                                           "args": {"from": catalog, "match": match}})
        res = self._commit(edge, node, cert, ResourceVector(), node_name=out_name)
        res["coverage"] = {g_d: evidence[0].get("solver", "catalog")}
        return res

    def _catalog_envelope(self, geo: dict):
        """Build the representative shape + replayable construction
        (op catalog-geom; the generator file's digest rides the
        construction so `fk verify` replays exactly what was built)."""
        import hashlib
        import importlib.util
        gen_ref = str(geo.get("generator", ""))
        mod_path, fn = gen_ref.split("#", 1)
        for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
            f = base / mod_path
            if f.is_file():
                src = f.read_bytes()
                sha = hashlib.sha256(src).hexdigest()[:12]
                spec_i = importlib.util.spec_from_file_location(
                    "fk_catalog_geom", f)
                mod = importlib.util.module_from_spec(spec_i)
                spec_i.loader.exec_module(mod)
                return getattr(mod, fn)(geo.get("params") or {}),                     {"op": "catalog-geom", "generator": gen_ref,
                     "params": geo.get("params") or {},
                     "source_sha": sha}
        raise FileNotFoundError(f"catalog generator {gen_ref!r} not found")

    def _props_shape(self, shape):
        from ..solvers.feature3d import _props as _fp
        return _fp(shape)

    def exact(self, goal: str, catalog: str, match: str,
              out_name: str | None = None, at=None) -> dict:
        """`exact lemma`: a catalog design closes the goal directly."""
        return self._close_from_catalog("exact", goal, catalog, match, tier=1,
                                        out_name=out_name, at=at)

    def procure(self, goal: str, catalog: str, match: str = "",
                out_name: str | None = None, at=None) -> dict:
        """Axiom introduction: purchased item; evidence tier=procured(2) ≠ verified."""
        return self._close_from_catalog("procure", goal, catalog,
                                        match or g_default_query(goal), tier=2,
                                        out_name=out_name, at=at)

    # --------------------------------------------------------- manufacture --
    def manufacture(self, part: str, into: list[str] | None = None,
                    args: dict | None = None, resources: dict | None = None,
                    out_name: str | None = None,
                    machine: str | None = None) -> dict:
        """Part -> Process family: the part goal pivots into a new obligation
        family (machining ops). Children bind as '<out>/<op>' and each op
        carries its own grounded takt/cost so line-eval can roll them up.

        `machine` (G2): the digest/name of the machine tool this plan runs
        on.  It enters the plan edge's AND every process-op edge's inputs,
        so the DAG asserts "this mill machines this part" and I3 exact
        linking guards the machine's own producing edge."""
        p_d, p_payload = self._input(part)
        if p_payload.get("role") != "Part":
            raise DagError("T2", "manufacture requires a Part input")
        m_d = self.store.resolve(machine) if machine else None
        ops_inputs = lambda base: base + ([m_d] if m_d else [])
        transform = {"name": "process-plan",
                     "args": {**(args or {}),
                              "into": into or [],
                              **({"machine": m_d} if m_d else {})}}
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
        res = self._commit(
            self._make_edge("manufacture", ops_inputs([p_d]), transform),
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
                self._make_edge("refine", ops_inputs([res["node"]]),
                                {"name": "process-op",
                                 "args": {"op": op,
                                          **({"machine": m_d} if m_d else {})}}),
                op_node, c_cert, ResourceVector(),
                node_name=f"{out_name or part}/{op}")
            children.append(c_res)
        res["children"] = children
        return res

    def _subtree_solids(self, root: str) -> tuple[list[str], list[dict]]:
        """Every grounded-solid payload in root's INPUT ancestry (the parts
        this node was composed from), promoted edges only, digest-sorted
        for determinism; root excluded."""
        parents: dict[str, list[str]] = {}
        for _, e in self.dag.iter_edges():
            if e.get("state") == "promoted":
                parents.setdefault(e.get("output", ""), []).extend(e.get("inputs", []))
        seen, stack, found = set(), [root], []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            try:
                payload = self.store.get_object(cur)["payload"]
            except KeyError:
                continue
            if cur != root and (payload.get("ground") or {}).get("construction"):
                found.append((cur, payload))
            stack.extend(parents.get(cur, []))
        found.sort(key=lambda x: x[0])
        return [d for d, _ in found], [p for _, p in found]

    def _policy_obligations(self, payload: dict, op: str = "") -> list:
        """M2: run the external policy library on this payload; results are
        ordinary obligations (hard/soft per policy) straight into C0.  The
        op marker lets policies scope themselves to one operator (e.g.
        print-fillet only on print edges)."""
        try:
            from . import policies as fkpol
            from ..core.objects import Obligation as _Ob
            return [_Ob.from_dict(o) for o in
                    fkpol.policy_obligations(payload, {"op": op})]
        except Exception:
            return []

    def _input_realized(self, d: str, payload: dict) -> bool:
        """A Part may enter a physical composition only when realized:
        grounded geometry, produced by a terminal closure (exact/procure/
        print), or assigned to a production route (manufacture family)."""
        g = payload.get("ground") or {}
        if g.get("construction"):
            return True
        pe = self.dag.producing_edge(d)
        if pe is not None and (
                pe.get("op") in ("exact", "procure")
                or (pe.get("transform") or {}).get("name") == "print"):
            return True
        for _, e in self.dag.iter_edges():
            if d not in (e.get("inputs") or []) or e.get("state") != "promoted":
                continue
            if e.get("op") in ("exact", "procure", "manufacture"):
                return True
            if (e.get("transform") or {}).get("name") == "print":
                return True
        return False

    # ------------------------------------------ assembly coverage (U4) --
    def _assembly_gaps(self, children) -> list[str]:
        """Terminal artifacts under a referenced decomposed subsystem that
        are NOT in this assembly's input chain.  Coverage is the inputs
        themselves, extended through intermediate assembly composes and
        symmetric across terminal production edges (listing the printed
        part covers its solid, and vice versa; same for catalog items)."""
        kids: dict[str, list[str]] = {}
        consumers: dict[str, list[dict]] = {}
        by_output: dict[str, dict] = {}
        consumed = set()   # refine/manufacture inputs = intermediates
        for _, e in self.dag.iter_edges():
            if e.get("state") != "promoted":
                continue
            o = e.get("output", "")
            if o and o not in by_output:
                by_output[o] = e
            for i in e.get("inputs") or []:
                consumers.setdefault(i, []).append(e)
            if e.get("op") in ("refine", "manufacture"):
                consumed.update(e.get("inputs") or [])
            if (e.get("transform") or {}).get("name") == "decompose" \
                    and len(e.get("inputs") or []) == 1:
                kids.setdefault(e["inputs"][0], []).append(o)

        def _terminal(e: dict) -> bool:
            return e.get("op") in ("exact", "procure") or \
                (e.get("transform") or {}).get("name") == "print"

        covered = {d for d, _ in children}
        frontier = list(covered)
        while frontier:
            c = frontier.pop()
            e = by_output.get(c)
            if e is not None and (e.get("op") == "compose" or _terminal(e)):
                for i in e.get("inputs") or []:
                    if i not in covered:
                        covered.add(i)
                        frontier.append(i)
            for e2 in consumers.get(c, []):
                if _terminal(e2) or (e2.get("op") == "refine" and
                        (e2.get("transform") or {}).get("name")
                        not in ("decompose",)):
                    # a terminal output, or a refine CONTINUATION of
                    # the same part (fillet/shell/cut successors),
                    # extends coverage along the production chain
                    o = e2.get("output", "")
                    if o and o not in covered:
                        covered.add(o)
                        frontier.append(o)
                        frontier.append(o)

        names: dict[str, list[str]] = {}
        for n, dg in self.store.names().items():
            names.setdefault(dg, []).append(n)

        gaps: list[str] = []
        for root_d, _ in children:
            if not kids.get(root_d):
                continue                      # leaf/assembly input — no subtree
            for a in self._subtree_artifacts(root_d, consumers, by_output,
                                             consumed):
                if a in covered:
                    continue
                nm = "/".join(sorted(names.get(a, []))) or a[24:34]
                if nm not in gaps:
                    gaps.append(nm)
        return gaps

    def _subtree_artifacts(self, root_d: str, consumers: dict,
                           by_output: dict, consumed: set) -> list[str]:
        """Grounded parts and catalog/print artifacts under root_d's
        refinement subtree.  Compose edges leave the subsystem into
        another assembly context and evaluate edges project — neither
        is followed."""
        def _terminal(e: dict) -> bool:
            return e.get("op") in ("exact", "procure") or \
                (e.get("transform") or {}).get("name") == "print"

        seen, stack, out = {root_d}, [root_d], []
        while stack:
            d = stack.pop()
            for e in consumers.get(d, []):
                if e.get("state") != "promoted" or e.get("op") in \
                        ("compose", "evaluate"):
                    continue
                o = e.get("output", "")
                if not o or o in seen:
                    continue
                seen.add(o)
                p = self.store.get_object(o)["payload"]
                if p.get("role") == "Medium" or o in consumed:
                    stack.append(o)
                    continue
                if (p.get("ground") or {}).get("construction") \
                        or _terminal(by_output.get(o) or e):
                    out.append(o)
                stack.append(o)
        return out

    # ---------------------------------------------------------- print (E1) --
    def print_part(self, part: str, printer: str, args: dict | None = None,
                   resources: dict | None = None,
                   out_name: str | None = None) -> dict:
        """Termination set (b) of the evolution plan: a grounded structural
        part closes by FDM printing on a declared print resource, so the
        manufacturing recursion converges to one shared capital asset
        instead of a per-part process chain.  Fail-closed: the dfam-print
        hard gates must pass for the edge to promote (C0), and a promoted
        print edge is a leaf closure in goals_view."""
        p_d, p_payload = self._input(part)
        if p_payload.get("role") not in ("Part", "Component"):
            raise DagError("T2", "print requires a Part/Component input")
        if not (p_payload.get("ground") or {}).get("construction"):
            raise DagError("U1", "print requires a grounded input "
                                 "(ground.construction)")
        pr_d = self.store.resolve(printer)
        args = {**(args or {}), "printer": pr_d}
        transform = {"name": "print", "args": args}
        obligations: list[Obligation] = []
        evidence: list[dict] = []
        try:
            fields, p_evidence, plugin_obs = self._call_plugin(
                {"name": "dfam-print", "args": args}, [p_payload])
            evidence = list(p_evidence)
            obligations += [o if isinstance(o, Obligation) else Obligation.from_dict(o)
                            for o in plugin_obs]
        except KeyError:
            raise DagError("E1", "no solver plugin registered: dfam-print")
        except (ContractError, ValueError, RuntimeError, IndexError) as e:
            evidence = [{"solver": "dfam-print", "tier": 2, "failed": str(e)}]
            obligations.append(Obligation(id="solver-ran", prop=str(e),
                                          holds=False, checker="dfam-print",
                                          detail="E1"))
        # slice estimate: volume -> grams / hours at a coarse deposition rate
        from ..solvers.feature3d import _DENSITY_G_PER_MM3
        g = p_payload.get("ground") or {}
        vol = float(g.get("volume_mm3") or 0.0)
        mat = str(g.get("material") or "pla").lower()
        grams = vol * _DENSITY_G_PER_MM3.get(mat, 1.24e-3)
        hours = vol / float(args.get("deposition_mm3_s", 8000.0)) / 3600.0
        evidence = evidence + [{
            "solver": "print/estimate", "tier": 2, "printer": pr_d,
            "material": mat, "volume_mm3": round(vol, 2),
            "mass_g": round(grams, 2), "print_h": round(hours, 2)}]
        merged = _deep_merge(p_payload, {})
        merged["evidence"] = list(p_payload.get("evidence", [])) + evidence
        node = Node(**{**merged, "lineage": []})
        obligations += self._structural_obligations(
            p_payload, p_payload.get("role"))
        obligations += self._policy_obligations(
            {"role": p_payload.get("role"), "kind": p_payload.get("kind"),
             "spec": p_payload.get("spec") or {}, "params": {},
             "ground": p_payload.get("ground")}, op="print")
        cert = Certificate(obligations=obligations, evaluator="print",
                           evidence=evidence, executor="print")
        # G1: the print resource enters the edge inputs (inputs[0]=workpiece,
        # inputs[1:]=operator instances) so the I1/I2/I3 exact-link checks
        # cover the production operator itself — a printer whose producing
        # edge went non-promoted rejects every print edge that uses it.
        return self._commit(
            self._make_edge("manufacture", [p_d, pr_d], transform),
            node, cert, ResourceVector(**(resources or {})),
            node_name=out_name)

    # -------------------------------------------------------------- realize --
    # per-layer default evaluators (E2/E3): kind -> (solver, fidelity)
    LAYER_SOLVERS = {
        "wing": ("aero-2d", 1),
        "point-mass": ("mission-analysis", 1),
        "epu": ("prop-map", 1),
        "motor": ("prop-map", 1),
        "rib": ("beam-fe", 1),
        "bed": ("beam-fe", 1),
        "assembly": ("mass-rollup", 2),
    }

    def realize(self, root: str, until: str = "termination-set",
                max_steps: int = 128, printer: str | None = None) -> dict:
        """Termination-set-aware combinator (E3).  Deepest-open-goal loop:

            catalog hit          -> exact, fallback procure
            grounded structural  -> print on the declared print resource
                                    (termination b; manufacture fallback)
            Resource, undecomposed -> forced device development: decompose
                                    with strictly-split budgets (PRSI round)
            otherwise            -> decompose (budget split flow-down)

        Each closed leaf additionally gets its layer-default eval evidence
        when a solver is mapped for its kind.  Termination: every step
        either closes a goal or decomposes into strictly smaller budget
        shares; failed (goal, action) pairs are never retried; bounded by
        max_steps.  `until="standard-part"` restricts closing to
        exact/procure (legacy behaviour, no print, no invented splits)."""
        from .goals import open_goals_under, depth_of
        printer_d = None
        if until == "termination-set" and printer:
            try:
                printer_d = self.store.resolve(printer)
            except KeyError:
                printer_d = None
        done: list[dict] = []
        failed: set[tuple[str, str]] = set()
        parents = {}
        actions_all = ("exact", "procure", "print", "decompose", "manufacture")
        splits_left = 8          # cap on invented decompositions (depth bound)
        for _ in range(max_steps):
            goals = open_goals_under(self.dag, root)
            if not goals:
                return {"done": True, "closed": done, "steps": len(done)}
            term_set = until == "termination-set"
            actions = ("exact", "procure") if not term_set else actions_all
            live = [g2 for g2 in goals
                    if any((g2["ref"], a) not in failed for a in actions)]
            if not live:
                remaining = [{"kind": g2["kind"], "role": g2["role"],
                              "termination": g2.get("termination")}
                             for g2 in goals]
                reason = "no catalog hit for remaining leaves" \
                    if not term_set \
                    else "no admissible action for remaining goals"
                return {"done": False, "closed": done, "steps": len(done),
                        "reason": reason, "remaining": remaining}
            live.sort(key=lambda g: -depth_of(self.dag, g["ref"], parents))
            g = live[0]
            payload = self.store.get_object(g["ref"])["payload"]
            kind = str(payload.get("kind") or "")
            grounded = bool((payload.get("ground") or {}).get("construction"))
            acted = False

            # 1. catalog closure
            query = _realize_query(g)
            for op in ("exact", "procure"):
                if (g["ref"], op) in failed:
                    continue
                res = getattr(self, op)(g["ref"], "catalog", query)
                done.append({"goal": g["ref"], "op": op, "state": res["state"]})
                if res["state"] == "promoted":
                    acted = True
                    self._layer_eval(g["ref"], kind)
                    break
                failed.add((g["ref"], op))
            if acted:
                continue

            # 2. print closure of a grounded structural part
            if term_set and grounded and printer_d and \
                    (g["ref"], "print") not in failed:
                res = self.print_part(g["ref"], printer_d)
                if res["state"] != "promoted" and "print-fillet" in \
                        str(res.get("reason") or ""):
                    rf = self.refine([g["ref"]],
                                     {"name": "fillet",
                                      "args": {"edges": "all", "radius": 0.6}},
                                     out_name=f"realize/{g['ref'][9:17]}-fil")
                    if rf["state"] == "promoted":
                        res = self.print_part(rf["node"], printer_d)
                done.append({"goal": g["ref"], "op": "print",
                             "state": res["state"]})
                if res["state"] == "promoted":
                    self._layer_eval(g["ref"], kind)
                    continue
                failed.add((g["ref"], "print"))
                # fall through to manufacture for Part inputs
                if payload.get("role") == "Part" and \
                        (g["ref"], "manufacture") not in failed:
                    res = self.manufacture(g["ref"])
                    done.append({"goal": g["ref"], "op": "manufacture",
                                 "state": res["state"]})
                    if res["state"] == "promoted":
                        continue
                    failed.add((g["ref"], "manufacture"))

            # 3. forced decompose (budget strictly split -> smaller goals);
            #    only when a budget exists to shrink (termination measure)
            has_budget = bool((g["spec"] or {}).get("budget"))
            if term_set and has_budget and splits_left > 0 and \
                    (g["ref"], "decompose") not in failed:
                splits_left -= 1
                res = self._auto_decompose(g, payload)
                done.append({"goal": g["ref"], "op": "decompose",
                             "state": res["state"]})
                if res["state"] == "promoted":
                    continue
                failed.add((g["ref"], "decompose"))

            # this goal was picked, every applicable action ran, and it is
            # still open -> exhausted for this run (guards that skipped
            # print/manufacture/decompose count as tried)
            for a in actions:
                failed.add((g["ref"], a))
        goals = open_goals_under(self.dag, root)
        return {"done": False, "closed": done, "steps": len(done),
                "reason": "max_steps exceeded",
                "remaining": [{"kind": g2["kind"], "role": g2["role"]}
                              for g2 in goals]}

    def _layer_eval(self, ref: str, kind: str) -> None:
        """Best-effort layer evidence after a closure (never fatal)."""
        mapping = self.LAYER_SOLVERS.get(kind)
        if not mapping:
            return
        solver, fidelity = mapping
        try:
            self.evaluate(ref, solver, fidelity=fidelity)
        except DagError:
            pass

    def _auto_decompose(self, g: dict, payload: dict) -> dict:
        """Invent a strictly-smaller decomposition for an undecomposed goal:
        equal budget split over kind-suffixed children (E3 termination
        measure: each child's share is parent/n <= parent/2).  Resources
        pivot to System (PRSI: a machine is developed as a system)."""
        spec = g["spec"] or {}
        budget = spec.get("budget") or {}
        role = payload.get("role")
        out_role = "System" if role == "Resource" else role
        child_role = "Component" if role in ("System", "Resource", "Intent") \
            else "Part"
        n = 3
        base = str(payload.get("kind") or g.get("kind") or "sub")
        names = [f"{base}-{i + 1}" for i in range(n)]
        flow = {}
        for name in names:
            fb = {}
            for q, b in budget.items():
                p = parse_bound(b)
                share = (p["hi"] if p["hi"] is not None else p["lo"]) / n
                fb[q] = ["<=", share] if p["hi"] is not None else [">=", share]
            flow[name] = ({"budget": fb} if fb else {})
        return self.refine(
            g["ref"], {"name": "decompose",
                       "args": {"into": names, "flow_down": flow}},
            out_name=f"{g.get('ref_name', base)}-split", out_role=out_role)

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


def _resolve_medium_names(flow: dict, store) -> None:
    """Templates are data: budget/effluent media appear as NAMES; resolve
    them to digests so ledger arithmetic sees the same bound form the
    .fcad parser produces (in place)."""
    for entry in flow.values():
        if not isinstance(entry, dict):
            continue
        for slot in ("budget", "effluent"):
            for b in (entry.get(slot) or {}).values():
                if isinstance(b, dict) and b.get("medium")                         and not str(b["medium"]).startswith("fk1:"):
                    try:
                        b["medium"] = store.resolve(str(b["medium"]))
                    except KeyError:
                        pass


def _merge_archetype(args: dict, name: str, store=None) -> dict:
    """E6-4: merge a named architecture template into decompose args.

    Templates are DATA (catalog/archetypes/<name>.json) — reusable
    decomposition patterns (wingbox, gantry-mill, ...) carrying the child
    list, roles/kinds, flow-down contracts and skeleton frames.  Explicit
    args win over template content per key.  Nothing case-specific lives
    in code."""
    import json
    from ..solvers.catalog import catalog_dirs
    for d in catalog_dirs():
        f = d / "archetypes" / f"{name}.json"
        if f.is_file():
            tpl = json.loads(f.read_text(encoding="utf-8"))
            merged = dict(args)
            for k, v in tpl.items():
                if merged.get(k) in (None, [], {}):
                    merged[k] = v
            merged["archetype"] = name           # family identity for policies
            if tpl.get("archetype_params"):
                merged["archetype_params"] = tpl["archetype_params"]
            if store is not None:
                _resolve_medium_names(merged.get("flow_down") or {}, store)
            return merged
    raise DagError("S1", f"unknown archetype template: {name!r} "
                         f"(searched catalog/archetypes/)")


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


def _subtree_metrics(dag, root: str) -> dict:
    """Numeric evidence collected from the subtree under root (E2): the
    closed-loop re-verification reads lower-layer measured values through
    this (last write wins, mirroring _metric)."""
    try:
        root_d = dag.store.resolve(root)
    except KeyError:
        return {}
    kids: dict[str, list[str]] = {}
    for _, e in dag.iter_edges():
        if e.get("state") == "promoted":
            for i in e.get("inputs", []):
                kids.setdefault(i, []).append(e.get("output", ""))
    seen, stack, metrics = set(), [root_d], {}
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        try:
            payload = dag.store.get_object(cur)["payload"]
        except KeyError:
            continue
        for ev in payload.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            for k, v in ev.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    metrics[k] = v
        stack.extend(kids.get(cur, []))
    return metrics
