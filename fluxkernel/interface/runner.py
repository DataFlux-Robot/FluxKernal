"""L4: .fcad runner — each top-level form = one operator call = one commit.

Failure semantics (impl plan §5): any failing form marks its edge rejected,
the script CONTINUES (failure trajectories are training assets), and the
process exit code stays non-zero.
"""
from __future__ import annotations

from ..core.dag import DagError
from ..semantics import contracts
from ..semantics.contracts import ContractError
from ..semantics.operators import Engine
from . import fcad
from .fcad import FcadError, split_kwargs, spec_from_sexpr


class Runner:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.store = engine.store
        self.results: list[dict] = []

    # ---------------------------------------------------------------- run --
    def run(self, text_or_forms) -> int:
        forms = fcad.parse(text_or_forms) if isinstance(text_or_forms, str) else text_or_forms
        failed = 0
        for form in forms:
            if not isinstance(form, list) or not form:
                raise FcadError("S1", f"not a form: {form!r}")
            head = form[0]
            try:
                res = self.dispatch(head, form[1:])
                res.setdefault("form", head)
                self.results.append(res)
                if res.get("state") in ("rejected",) or res.get("error"):
                    failed += 1
            except Exception as e:   # fail-open script semantics: record, continue
                self.results.append({"form": head, "error": f"{type(e).__name__}: {e}",
                                     "state": "rejected"})
                self.engine.journal.append(f"{head:11s} ERROR {type(e).__name__}: {e}")
                failed += 1
        return 1 if failed else 0

    def dispatch(self, head: str, body: list) -> dict:
        fn = getattr(self, f"_form_{head.replace('-', '_')}", None)
        if fn is None:
            raise FcadError("S1", f"unknown top-level form: ({head} ...)")
        return fn(body)

    # --------------------------------------------------------------- forms --
    def _form_term(self, body):
        pos, _ = split_kwargs(body)
        if len(pos) < 2:
            raise FcadError("S1", "(term <name> \"operational definition\")")
        d = contracts.put_term(self.store, pos[0], pos[1],
                               " ".join(str(x) for x in pos[2:]))
        return {"state": "ok", "node": d, "term": pos[0]}

    def _form_node(self, body, role=None):
        pos, kw = split_kwargs(body)
        name = pos[0] if pos else None
        spec = spec_from_sexpr(kw.get("spec", []), self.store) if kw.get("spec") else {}
        facet = kw.get("facet", "BODY")
        d = self.engine.node(name, role or kw.get("role", "Component"),
                             kw.get("kind", name or "node"), spec,
                             params=fcad.params_from_sexpr(kw.get("params", [])),
                             variants=fcad._plain_value(kw.get("variants", []), None)
                             if kw.get("variants") else [],
                             facet=facet)
        return {"state": "ok", "node": d}

    def _form_goal(self, body):
        return self._form_node(body, role="Intent")

    def _transform(self, tsexpr) -> dict:
        if not isinstance(tsexpr, list) or not tsexpr:
            raise FcadError("S1", f"bad transform: {tsexpr!r}")
        pos, kw = split_kwargs(tsexpr)
        name = pos[0] if pos else "identity"
        args = {}
        for k, v in kw.items():
            ku = k.replace("-", "_")
            if isinstance(v, list) and v and v[0] in ("sketch", "contract"):
                args[ku] = spec_from_sexpr(v, self.store)
            elif ku == "flow_down":
                args[ku] = fcad.flowdown_from_sexpr(v, self.store)
            elif ku == "values":
                # param-perturb values: ((mtow 1200) (ff 0.28) ...) -> dict
                args[ku] = fcad.pairs_to_map(v)
            elif ku == "specs":
                args[ku] = {e[0]: spec_from_sexpr(e[1], self.store)
                            for e in v if isinstance(e, list) and len(e) == 2}
            elif ku in ("roles", "kinds"):
                args[ku] = fcad.pairs_to_map(v)
            elif ku in ("into", "closes"):
                args[ku] = [x for x in v if isinstance(x, (str, int))]
            else:
                args[ku] = fcad._plain_value(v, self.store)
        return {"name": name, "args": args}

    def _form_edge(self, body):
        pos, kw = split_kwargs(body)
        op = kw.get("op")
        if op not in ("refine", "compose", "abstract", "evaluate", "exact",
                      "procure", "manufacture", "integrate"):
            raise FcadError("S1", f"unknown edge op: {op!r}")
        return self._op(op, pos, kw)

    def _form_refine(self, body):
        pos, kw = split_kwargs(body)
        return self._op("refine", pos, kw)

    def _form_compose(self, body):
        pos, kw = split_kwargs(body)
        return self._op("compose", pos, kw)

    def _form_integrate(self, body):
        pos, kw = split_kwargs(body)
        return self._op("integrate", pos, kw)

    def _form_abstract(self, body):
        pos, kw = split_kwargs(body)
        return self._op("abstract", pos, kw)

    def _form_manufacture(self, body):
        pos, kw = split_kwargs(body)
        return self._op("manufacture", pos, kw)

    def _form_print(self, body):
        pos, kw = split_kwargs(body)
        part = str(kw.get("in") or (pos[0] if pos else ""))
        printer = str(kw.get("printer") or (pos[1] if len(pos) > 1 else ""))
        if not part or not printer:
            raise FcadError("S1", "(print <name> :in <part> :printer <printer>)")
        transform = self._transform(kw["transform"]) if kw.get("transform") \
            else {"name": "print", "args": {}}
        resources = fcad.resources_from_sexpr(kw.get("resources", []))
        return self.engine.print_part(
            part, printer, args=transform.get("args") or {},
            resources=resources, out_name=kw.get("out"))

    def _form_eval(self, body):
        pos, kw = split_kwargs(body)
        target = kw.get("target") or (pos[0] if len(pos) > 0 else None)
        solver = kw.get("with") or (pos[1] if len(pos) > 1 else None)
        expect = kw.get("expect")
        expect = fcad.expect_from_sexpr(expect) if isinstance(expect, list) \
            else fcad.parse_expect(expect or "")
        args = self._extra_args(kw)
        if isinstance(kw.get("args"), list):
            # flat keyword-value sequence: (process fdm min_wall_mm 1.0)
            flat = kw["args"]
            args.update({str(flat[i]): fcad._plain_value(flat[i + 1], self.store)
                         for i in range(0, len(flat) - 1, 2)})
        return self.engine.evaluate(
            target, solver, fidelity=int(kw.get("fidelity", 0) or 0),
            expect=expect, args=args,
            resources=fcad.resources_from_sexpr(kw.get("resources", [])))

    def _form_exact(self, body):
        pos, kw = split_kwargs(body)
        target = kw.get("target") or (pos[0] if pos else None)
        return self.engine.exact(target, kw.get("from", "catalog"),
                                 kw.get("match", "") or "",
                                 out_name=kw.get("out"))

    def _form_procure(self, body):
        pos, kw = split_kwargs(body)
        target = kw.get("target") or (pos[0] if pos else None)
        return self.engine.procure(target, kw.get("from", "catalog"),
                                   kw.get("match", "") or "",
                                   out_name=kw.get("out"))

    def _extra_args(self, kw) -> dict:
        known = {"op", "in", "out", "target", "with", "from", "match", "expect",
                 "fidelity", "resources", "transform", "into", "closes",
                 "back-to", "reason", "rollup", "role", "kind", "spec",
                 "flow-down", "via", "until", "strategy", "back_to"}
        out = {}
        for k, v in kw.items():
            if k in known:
                continue
            out[k.replace("-", "_")] = fcad._plain_value(v, self.store)
        return out

    def _op(self, op: str, pos: list, kw: dict) -> dict:
        ins = [str(x) for x in (kw.get("in") or [])]
        out_name = kw.get("out")
        transform = self._transform(kw["transform"]) if kw.get("transform") \
            else {"name": op, "args": {}}
        resources = fcad.resources_from_sexpr(kw.get("resources", []))
        if op == "refine":
            return self.engine.refine(
                ins or ([pos[0]] if pos else []), transform,
                out_name=out_name, out_role=kw.get("role"),
                out_kind=kw.get("kind"),
                out_spec=spec_from_sexpr(kw["spec"], self.store) if kw.get("spec") else None,
                out_params=fcad.params_from_sexpr(kw.get("params", [])) or None,
                resources=resources)
        if op == "compose":
            rollup = fcad.bounds_map(kw["rollup"], self.store) \
                if isinstance(kw.get("rollup"), list) else None
            return self.engine.compose(
                ins, out_name=out_name, out_role=kw.get("role", "System"),
                out_kind=kw.get("kind"), out_spec=spec_from_sexpr(
                    kw["spec"], self.store) if kw.get("spec") else None,
                rollup=rollup, resources=resources,
                transform_spec=transform if transform.get("name") != "compose" else None)
        if op == "integrate":
            closes = [str(x) for x in (kw.get("closes") or transform["args"].get("closes", []))]
            return self.engine.integrate(
                ins, out_name=out_name, closes=closes,
                from_ref=kw.get("from") or transform["args"].get("from"),
                match=kw.get("match", "") or transform["args"].get("match", ""),
                out_role=kw.get("role", "Component"), out_kind=kw.get("kind"),
                out_spec=spec_from_sexpr(kw["spec"], self.store) if kw.get("spec") else None,
                resources=resources)
        if op == "abstract":
            return self.engine.abstract(ins[0] if ins else (pos[0] if pos else None),
                                        back_to=kw.get("back-to") or kw.get("back_to"),
                                        reason=str(kw.get("reason", "")))
        if op == "manufacture":
            into = transform["args"].get("into") or [
                str(x) for x in (kw.get("into") or [])]
            return self.engine.manufacture(ins[0] if ins else (pos[0] if pos else None),
                                           into=into, args=transform["args"],
                                           resources=resources, out_name=out_name)
        raise FcadError("S1", f"op {op!r} not reachable here")
