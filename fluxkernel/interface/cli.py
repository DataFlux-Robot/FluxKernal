"""L4: the `fk` command line — tactic mode (the human-facing surface).

Every write command = one edge = one DAG commit. State lives in <cwd>/.fk/
(git-like). <ref> = mutable name (index.json) or immutable digest.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..core.dag import DAG, DagError
from ..store.objstore import Store
from ..semantics import contracts, goals as goalsview
from ..semantics.operators import Engine
from . import fcad, diagnostics
from .runner import Runner

FK_DIR = ".fk"


def _store(cwd: Path | None = None) -> Store:
    root = (cwd or Path.cwd()) / FK_DIR
    if not root.exists():
        sys.exit("fatal: not a fk workspace (run `fk init`)")
    return Store(root)


def _engine(cwd: Path | None = None) -> Engine:
    return Engine(_store(cwd))


def _name_of(store: Store, digest: str) -> str:
    for name, d in store.names().items():
        if d == digest and not name.startswith("@") and not name.startswith("term/"):
            return name
    return digest[8:20] + "…"


def _short(d: str) -> str:
    return (d or "")[8:22]


# ------------------------------------------------------------- session ----
def cmd_init(a):
    root = Path.cwd() / FK_DIR
    if root.exists() and not a.force:
        sys.exit("fatal: .fk already exists (use --force to re-init index only)")
    Store(root)
    print(f"initialized empty fk workspace at {root}")


def cmd_run(a):
    text = Path(a.script).read_text(encoding="utf-8")
    store = _store()
    eng = Engine(store)
    runner = Runner(eng)
    try:
        code = runner.run(text)
    except fcad.FcadError as e:
        sys.exit(str(e))
    for line in eng.journal:
        print(line)
    rejected = [r for r in runner.results if r.get("state") == "rejected"]

    print(f"\nforms: {len(runner.results)}  rejected: {len(rejected)}")
    if rejected:
        print("REJECTED:")
        for r in rejected:
            print(f"  {r.get('form')}: {r.get('reason') or r.get('error')}")

    # L2.2 + perception fail-closed: reference-carrying cases archive
    # four-view renders as a default run artifact; unmet case requires
    # force rc != 0 (perception unavailable != perception passed)
    gv = goalsview.goals_view(eng.dag)
    case = gv.get("case", [])
    has_ref = any(p.get("kind") == "reference-image"
                  for _, p in eng.dag.iter_nodes())
    if has_ref:
        try:
            from ..strategy import scene, render_png
            parts = scene.collect_grounded(eng)
            if parts:
                tri = [(scene.role_color(p2), scene.mesh_shape(shp))
                       for _, p2, shp in parts]
                out_dir = Path(".fk") / "renders" / "last"
                paths = render_png.render_views(tri, out_dir,
                                                 title="run archive")
                print(f"renders archived: {len(paths)} views in {out_dir}")
        except Exception as e:  # noqa: BLE001
            print(f"render archive skipped: {e}")
    if case:
        print("CASE CONTRACT UNMET:")
        for c in case:
            print(f"  {c.get('termination', 'case-requirement')}")
            for rr in c.get("risks", []):
                print(f"    - {rr}")
        if code == 0:
            code = 1
    return code


# ---------------------------------------------------------- tactic state --
def cmd_goals(a):
    view = goalsview.goals_view(_engine().dag)
    n_case = len(view.get("case", []))
    total = len(view["open"]) + n_case
    print(f"OPEN GOALS ({total})")
    for g in view["open"]:
        line = (f"  {g['kind']:<18} {g['role']:<10} state={g['state']}"
                f"  term={g.get('termination', '?')}")
        if g["holes"]:
            line += f"  holes: {','.join(g['holes'])}"
        if g["risks"]:
            line += f"  risks: {','.join(g['risks'])}"
        print(line)
    if n_case:
        print(f"CASE CONTRACT ({n_case} requires unmet — process not "
              f"finished, not a design error):")
        for c in view["case"]:
            print(f"  {c.get('kind', 'case-requirement'):<18} "
                  f"{c.get('termination', '?')}")
            for r in c.get("risks", []):
                print(f"    - {r}")
    if view["holes"]:
        print(f"HOLES ({len(view['holes'])})")
        for h in view["holes"]:
            blocks = ",".join(_short(b) for b in h["blocks"]) or "-"
            print(f"  {h['hole']}  blocks: {blocks}")
    print(f"REJECTED ({len(view['rejected'])})")
    for r in view["rejected"]:
        print(f"  {_short(r['edge'])} [{diagnostics.worst_code(r['reason']) or 'C0'}] "
              f"{r['reason']}")
    return 0


def cmd_sorry(a):
    view = goalsview.holes_view(_engine().dag, include_collapsed=getattr(a, "all", False))
    print(f"SORRY HOLES ({len(view['holes'])})")
    for h in view["holes"]:
        line = f"  {h['hole']} at {_short(h['node'])}  -> {len(h['blocks'])} dependent(s)"
        if h.get("collapsed_at"):
            line += f"  collapsed-at: {_short(h['collapsed_at'])}"
        print(line)
    return 0


def cmd_risks(a):
    view = goalsview.risks_view(_engine().dag)
    print(f"UNSETTLED RISKS ({len(view['risks'])})")
    for r in view["risks"]:
        blocks = ",".join(_short(b) for b in r["blocks"]) or "-"
        print(f"  [{r['kind']:<11}] {_short(r['ref'])}  {r['detail']}  blocks: {blocks}")
    return 0


def cmd_goal(a):
    eng = _engine()
    d, node = eng.dag.get_node(a.ref)
    print(f"{_name_of(eng.store, d)}  role={node.role} kind={node.kind} "
          f"facet={node.facet}")
    print(json.dumps(node.spec, indent=1, ensure_ascii=False)[:2000])
    pe = eng.dag.producing_edge(d)
    if pe:
        print(f"producing edge: {pe.get('op')}/{pe.get('transform', {}).get('name')} "
              f"[{pe.get('state')}]")
    return 0


def cmd_next(a):
    g = goalsview.next_goal(_engine().dag)
    if not g:
        print("no open goals")
        return 0
    print(f"next: {g['kind']} ({g['role']}) state={g['state']} "
          f"risks={','.join(g['risks']) or 'none'}")
    return 0


# ------------------------------------------------------------ contract ----
def cmd_lint(a):
    eng = _engine()
    if a.ref:
        d, node = eng.dag.get_node(a.ref)
        failed = contracts.lint_node(node.payload(), eng.store)
        print(f"{_short(d)}: " + (",".join(failed) if failed else "clean"))
        for c in failed:
            print(f"  [{c}] {diagnostics.explain(c)}")
        return 0 if not failed else 1
    if getattr(a, "rule", None):
        # single-rule query (skill command mapping)
        case = contracts.lint_case(eng.dag)
        print(f"{a.rule}: {'FAIL' if a.rule in case else 'pass'}")
        return 0 if a.rule not in case else 1
    bad = 0
    for d, payload in eng.dag.iter_nodes():
        failed = contracts.lint_node(payload, eng.store)
        if failed:
            bad += 1
            print(f"{_short(d)} {_name_of(eng.store, d):<20} {','.join(failed)}")
    case = contracts.lint_case(eng.dag)
    for r in case:
        print(f"case {'':<24} {r}  ({diagnostics.explain(r)})")
    bad += len(case)
    print("all nodes clean" if not bad else f"{bad} node(s) failing lint")
    return 0 if not bad else 1


def cmd_ledger(a):
    led = contracts.ledger(_engine().dag, a.medium)
    print(f"medium {_short(led['medium'])}  margin={led['margin']}")
    for q, cap in led["capacity"].items():
        used = led["sums"]["budget"].get(q, 0.0)
        allowed = cap * (1 - led["margin"])
        mark = "OK " if led["ok"].get(q) else "OVER"
        print(f"  [{mark}] {q}: Σbudget={used:g} / allowed={allowed:g} (cap={cap:g})")
        for row in led["rows"]["budget"]:
            if row["qty"] == q:
                mark2 = " (rolled up)" if row.get("subsumed") else ""
                print(f"      - {_short(row['node'])} ({row['kind']}) {row['value']:g}{mark2}")
    for o in led["obligations"]:
        if not o.holds:
            print(f"  obligation medium-capacity FAILED: {o.prop}")
    return 0 if all(led["ok"].values()) else 1


ELICIT_STEPS = [
    ("worst", "STEP 1/6 — 最坏十件事 (worst things that can go wrong) → goals+forbidden\n"
              "  e.g. [\"单台飞控失效时仍可改平着陆\", ...]"),
    ("nouns", "STEP 2/6 — 关键名词的操作定义 (key nouns → operational definitions)\n"
              "  e.g. {\"受控\": \"过载/迎角/指示空速落在集合S内\"}"),
    ("flows", "STEP 3/6 — 数据/能量/控制三流交界 (budget/effluent declarations)\n"
              "  e.g. {\"budget\": {\"power_w\": [\"<=\", 30]}, \"effluent\": {\"heat_w\": [\"<=\", 4]}}"),
    ("heuristics", "STEP 4/6 — 经验参数带前提不等式 (four questions complete or rejected):\n"
                   "  e.g. [{\"param\":\"skin-t\", \"ineq\":\">=0.5\", \"metric\":\"buckling\",\n"
                   "         \"disturbance\":\"gust\", \"threshold\":\"first-mode\",\n"
                   "         \"detector\":\"ground-vibe\"}]"),
    ("not_responsible", "STEP 5/6 — 不负责清单 (explicit disclaimers)\n"
                        "  e.g. [\"液压源压力维持\"]"),
    ("gaps", "STEP 6/6 — 接不上的口子 (unresolved joints — recorded as risks, never smoothed)\n"
             "  e.g. [\"母线阻抗模型在1kHz以下未验证\"]"),
]


def cmd_elicit(a):
    eng = _engine()
    d, node = eng.dag.get_node(a.node)
    answers = {}
    if a.answers:
        answers = json.loads(Path(a.answers).read_text(encoding="utf-8"))
    else:
        if not sys.stdin.isatty():
            sys.exit("fatal: elicit needs a tty or --answers file.json")
        for key, prompt in ELICIT_STEPS:
            print(prompt)
            lines = []
            while True:
                try:
                    ln = input()
                except EOFError:
                    break
                if not ln:
                    break
                lines.append(ln)
            answers[key] = _parse_step(key, "\n".join(lines))
    spec = elicit_spec(eng, answers)
    merged = {**node.payload(), "spec": spec}
    from ..core.objects import Node
    new_d = eng.dag.put_node(Node(**{**merged, "lineage": []}), a.node)
    failed = contracts.lint_node(merged, eng.store)
    print(f"elicited contract bound to {a.node} ({_short(new_d)}); "
          f"lint: {','.join(failed) if failed else 'clean'}")
    return 0


def _parse_step(key: str, text: str):
    text = text.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return [ln.strip() for ln in text.splitlines() if ln.strip()]


def elicit_spec(eng: Engine, answers: dict) -> dict:
    """Six elicitation steps (v1.2 §22) -> a five-slot contract spec."""
    spec: dict = {"goals": [], "semantics": [], "assumes": [], "guarantees": [],
                  "budget": {}, "effluent": {}, "forbidden": [],
                  "not_responsible": [], "time_scale": "mission",
                  "open_risks": []}
    # ① worst things -> goals + forbidden
    for i, w in enumerate(answers.get("worst") or []):
        spec["goals"].append({"id": f"g{i+1}", "stmt": f"survive: {w}",
                              "falsifiable": True,
                              "measure": answers.get("measure", "test campaign")})
        spec["forbidden"].append({"id": f"f{i+1}", "stmt": w, "check": "test"})
    # ② nouns -> term registry entries
    for name, opdef in (answers.get("nouns") or {}).items():
        contracts.put_term(eng.store, name, str(opdef))
        spec["semantics"].append(eng.store.names()[contracts.TERM_PREFIX + name])
    # ③ three flows -> budget / effluent
    flows = answers.get("flows") or {}
    spec["budget"] = dict(flows.get("budget") or {})
    spec["effluent"] = dict(flows.get("effluent") or {})
    spec["assumes"] = list(flows.get("assumes") or [])
    spec["guarantees"] = list(flows.get("guarantees") or [])
    # ④ heuristics: only accepted with all four questions answered
    pb: dict = {}
    for h in answers.get("heuristics") or []:
        if not isinstance(h, dict):
            continue
        if all(h.get(k) for k in ("metric", "disturbance", "threshold", "detector")):
            pb[h.get("param", "?")] = {"source": h}
        else:
            spec["open_risks"].append(
                f"heuristic {h.get('param')!r} rejected: four questions incomplete")
    spec["param_bounds"] = pb
    # ⑤ disclaimers
    spec["not_responsible"] = list(answers.get("not_responsible") or [])
    # ⑥ unresolved joints stay as risks, never smoothed
    spec["open_risks"] += [str(g) for g in answers.get("gaps") or []]
    return spec


# ------------------------------------------------------------- tactics ----
def cmd_node(a):
    eng = _engine()
    spec = fcad.spec_from_sexpr(fcad.parse(a.spec)[0], eng.store) if a.spec else {}
    d = eng.node(a.name, a.role, a.kind or a.name, spec,
                 facet=a.facet or "BODY")
    for line in eng.journal:
        print(line)
    print(f"{a.name} = {d}")
    return 0


def cmd_refine(a):
    eng = _engine()
    args = dict(kv.split("=", 1) for kv in (a.arg or []))
    args = {k: _auto_v(v) for k, v in args.items()}
    if a.spec:
        args["_spec"] = fcad.spec_from_sexpr(fcad.parse(a.spec)[0], eng.store)
    res = eng.refine(a.goal, {"name": a.via, "args": args},
                     out_name=a.out, out_role=a.role, out_kind=a.kind)
    for line in eng.journal:
        print(line)
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] in ("promoted", "ok") else 1


def _auto_v(v: str):
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def cmd_eval(a):
    eng = _engine()
    expect = fcad.parse_expect(a.expect or "")
    res = eng.evaluate(a.goal, a.with_, fidelity=a.fidelity, expect=expect)
    for line in eng.journal:
        print(line)
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] == "promoted" else 1


def cmd_exact(a):
    eng = _engine()
    res = eng.exact(a.goal, a.from_, a.match or "", out_name=a.out)
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] == "promoted" else 1


def cmd_procure(a):
    eng = _engine()
    res = eng.procure(a.goal, a.from_, a.match or "", out_name=a.out)
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] == "promoted" else 1


def cmd_compose(a):
    eng = _engine()
    rollup = fcad.parse_expect(a.rollup or "") if a.rollup else None
    res = eng.compose(a.inputs, out_name=a.out, out_role=a.role or "System",
                      out_kind=a.kind, rollup=rollup)
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] == "promoted" else 1


def cmd_integrate(a):
    eng = _engine()
    res = eng.integrate(a.inputs, out_name=a.out, closes=(a.closes or []),
                        from_ref=a.from_ or None, match=a.match or "")
    if res.get("coverage"):
        print("coverage map:")
        for g, ev in res["coverage"].items():
            print(f"  {_short(g)} <- {ev}")
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] == "promoted" else 1


def cmd_abstract(a):
    eng = _engine()
    res = eng.abstract(a.node, back_to=a.back_to, reason=a.reason or "")
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] == "promoted" else 1


def cmd_manufacture(a):
    eng = _engine()
    res = eng.manufacture(a.part, into=(a.into.split(",") if a.into else []))
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] == "promoted" else 1


def cmd_print(a):
    eng = _engine()
    res = eng.print_part(a.part, a.printer, out_name=a.out)
    print(f"{res['state']}" + (f": {res['reason']}" if res["reason"] else ""))
    return 0 if res["state"] == "promoted" else 1


# ----------------------------------------------------------- combinators --
def cmd_realize(a):
    eng = _engine()
    res = eng.realize(a.root, until=a.until, max_steps=a.max_steps,
                      printer=a.printer)
    for line in eng.journal:
        print(line)
    print(f"realize done={res['done']} steps={res['steps']}"
          + (f" reason={res.get('reason')}" if res.get("reason") else ""))
    for r in res.get("remaining") or []:
        print(f"  remaining: {r.get('kind')} ({r.get('role')}, "
              f"{r.get('termination', '?')})")
    return 0 if res["done"] else 1


def cmd_evolve(a):
    from ..strategy.evolve import run_evolve
    eng = _engine()
    res = run_evolve(eng, a)
    return res


def cmd_watch(a):
    from ..strategy.watch import run_watch
    return run_watch(a)


# ------------------------------------------------------------ inspect ----
def cmd_check(a):
    eng = _engine()
    d, node = eng.dag.get_node(a.ref)
    pe = eng.dag.producing_edge(d)
    print(f"{node.role}/{node.kind} [{eng.dag.node_state(d)}]")
    failed = contracts.lint_node(node.payload(), eng.store)
    print(f"lint: {','.join(failed) if failed else 'clean'}")
    if pe:
        print(f"edge {pe.get('op')}/{pe.get('transform', {}).get('name')} "
              f"[{pe.get('state')}]")
        for o in pe.get("certificate", {}).get("obligations", []):
            mark = "OK" if o.get("holds") else ("NO" if o.get("holds") is False else "??")
            print(f"  [{mark}] {o.get('id')}: {o.get('prop')}")
    return 0


def cmd_graph(a):
    eng = _engine()
    edges = eng.dag.iter_edges()
    if a.dot:
        print("digraph fk {")
        for d, p in eng.dag.iter_nodes():
            print(f'  "{_short(d)}" [label="{p.get("kind")}/{p.get("role")}"];')
        for _, e in edges:
            for i in e["inputs"]:
                print(f'  "{_short(i)}" -> "{_short(e["output"])}" '
                      f'[label="{e["op"]}:{e.get("state", "")}"];')
        print("}")
        return 0
    for _, e in edges:
        ins = " ".join(_short(i) for i in e["inputs"])
        print(f"{ins or '(genesis)'} --{e['op']}/{e.get('transform', {}).get('name', '')}"
              f"[{e.get('state')}]--> {_short(e['output'])}")
    return 0


def cmd_impact(a):
    """fk impact <ref> --set <set>/<key>=<value> [--apply]

    Change propagation: dry-run reports the consumption footprint;
    --apply replays the stored source script in a SHADOW store with the
    parameter override injected after its definition, then re-verifies.
    The original store is never mutated (history is immutable)."""
    from . import impact as fki
    eng = _engine()
    try:
        overrides = fki.parse_sets(a.set)
    except ValueError as e:
        print(f"fatal: {e}")
        return 2
    if not overrides:
        print("fatal: nothing to do — pass --set <set>/<key>=<value>")
        return 2
    names = eng.store.names()
    if not names.get("@last-script"):
        print("fatal: no stored script — run `fk run <script>` first")
        return 2
    text = eng.store.get_blob(names["@last-script"]).decode("utf-8")
    forms = fcad.parse(text)
    for set_name, kvs in overrides.items():
        n = fki._forms_consuming(forms, set_name)
        print(f"{set_name}: {n} form(s) reference its parameters; "
              f"override " + ", ".join(f"{k}={v:g}" for k, v in kvs.items()))
    if not a.apply:
        print("dry-run (pass --apply to replay in a shadow store)")
        return 0
    res = fki.replay_with_overrides(eng.store, overrides)
    ok = not res["verify"] and not res["open"]
    print(f"shadow replay {res['store_root']}")
    print(f"  injected: {', '.join(res['injected']) or '-'}")
    print(f"  script rc={res['rc']} (1 may be the deliberate failure)")
    print(f"  verify: {'OK' if not res['verify'] else res['verify']}")
    print(f"  open goals: {len(res['open'])}"
          + (f" -> {[o['kind'] for o in res['open']][:6]}" if res["open"] else ""))
    return 0 if ok else 1


def cmd_why(a):
    chain = goalsview.why(_engine().dag, a.ref)
    for step in chain:
        via = f"  <- {step['via']}" if step.get("via") else "  (genesis)"
        print(f"{step['kind']}:{step['role']}{'' if step.get('facet') == 'BODY' else '/' + str(step.get('facet'))} "
              f"{_short(step['ref'])}{via}")
        if step.get("bindings"):
            bs = "  ".join(f"{b['expr']}={b['value']:g}" for b in step["bindings"])
            print(f"    params: {bs}")
        if step.get("evidence"):
            print(f"    evidence: {'  '.join(step['evidence'])}")
    return 0


def cmd_log(a):
    for rec in _store().read_edge_log():
        r = rec["record"]
        print(f"{_short(rec['edge'])} {r.get('op', ''):<11} {r.get('state', ''):<9} "
              f"{r.get('reason', '')}")
    return 0


def cmd_status(a):
    eng = _engine()
    nodes = eng.dag.iter_nodes()
    edges = eng.dag.iter_edges()
    counts: dict[str, int] = {}
    for _, e in edges:
        counts[e["state"]] = counts.get(e["state"], 0) + 1
    print(f"nodes: {len(nodes)}  edges: {len(edges)}")
    print("edge states: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    rv = goalsview.risks_view(eng.dag)
    kinds: dict[str, int] = {}
    for r in rv["risks"]:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print("risks: " + (" ".join(f"{k}={v}" for k, v in sorted(kinds.items())) or "none"))
    return 0


def cmd_search(a):
    from ..solvers import catalog as catalog_mod
    hits = catalog_mod.search(a.query)
    for h in hits:
        print(f"  {h['name']:<24} tier={h.get('tier', '?')} "
              f"{json.dumps(h.get('bounds', {}), ensure_ascii=False)}")
    print(f"{len(hits)} hit(s)")
    return 0


def cmd_show(a):
    eng = _engine()
    obj = eng.dag.get_obj(a.ref)
    if a.json:
        print(json.dumps(obj["payload"], indent=1, ensure_ascii=False))
        return 0
    p = obj["payload"]
    if obj["kind"] == "node":
        print(f"node {p.get('role')}/{p.get('kind')} facet={p.get('facet')} "
              f"state={eng.dag.node_state(obj['digest'])}")
        print(json.dumps(p.get("spec"), indent=1, ensure_ascii=False)[:3000])
        if p.get("ground"):
            print("ground: " + json.dumps(p["ground"], ensure_ascii=False)[:500])
    else:
        print(f"edge {p.get('op')} [{p.get('state')}] {p.get('reason', '')}")
        print(json.dumps(p.get("certificate", {}), indent=1, ensure_ascii=False)[:3000])
    return 0


def cmd_export(a):
    eng = _engine()
    d, node = eng.dag.get_node(a.ref)
    g = node.ground or {}
    blobs = g.get("blobs", {})
    wrote = []
    if a.step and blobs.get("step"):
        Path(a.step).write_bytes(eng.store.get_blob(blobs["step"]))
        wrote.append(a.step)
    if a.stl and blobs.get("stl"):
        Path(a.stl).write_bytes(eng.store.get_blob(blobs["stl"]))
        wrote.append(a.stl)
    if not wrote:
        sys.exit("fatal: node has no exportable blobs (ground a solid first)")
    print("wrote: " + ", ".join(wrote))
    return 0


def cmd_trace(a):
    from ..adapters.mbench import export_trace
    eng = _engine()
    export_trace(eng, Path(a.out))
    print(f"trace package written to {a.out}")
    return 0


def cmd_render(a):
    """fk render --png <prefix> [--view iso|front|top|right|all]

    V2/P7: the perception input channel — the honest DAG geometry (every
    grounded part at its recorded placement) as offline four-view PNGs,
    consumable by `fk review` (VLM) or a human."""
    eng = _engine()
    from ..strategy import scene, render_png
    parts = scene.collect_grounded(eng)
    if not parts:
        sys.exit("fatal: no grounded geometry in this workspace")
    # CC3/C6: default renders the VEHICLE group only — equipment
    # (printer frames, mills) reads as clutter and has been mistaken
    # for defects two reviews running; --with-equipment opts in
    if not getattr(a, "with_equipment", False):
        parts = [(n, p2, shp) for n, p2, shp in parts
                 if not any(t in n for t in
                            ("printer", "pframe", "p-stepper", "p-board",
                             "mill", "mbed", "mcol", "mbeam", "mhead",
                             "xax2", "yax2", "zax2",
                             "xrail", "yrail", "zrail", "xscrew",
                             "yscrew", "zscrew", "xservo", "yservo",
                             "zservo", "xcar2", "ycar2", "zcar2"))]
    tri_groups = []
    for name, payload, shp in parts:
        tri_groups.append((scene.role_color(payload), scene.mesh_shape(shp)))
    views = list(render_png.VIEWS) if a.view == "all" else [a.view]
    paths = render_png.render_views(tri_groups, a.png, views=views,
                                    title=a.title or "fk scene",
                                    theme=getattr(a, "theme", "dark"))
    if not paths:
        sys.exit("fatal: render produced no images")
    for p in paths:
        print(f"rendered: {p}")
    return 0


def cmd_review(a):
    """fk review <ref> [--vs original.jpg] [--selftest] — strategy/review.py."""
    from ..strategy.review import run_review, run_selftest
    if getattr(a, "selftest", False):
        return run_selftest()
    if not a.ref:
        sys.exit("fatal: fk review needs a goal ref (or --selftest)")
    return run_review(_engine(), a)


def cmd_report(a):
    """fk report — cold-store snapshot for progress docs: edge/node
    counts, rejected edges with reasons, open goals, verify verdict.
    Numbers come from THIS store only (single-run semantics)."""
    eng = _engine()
    edges = list(eng.dag.iter_edges())
    rejected = [{"output": _name_of(eng.store, e.get("output", "")),
                 "op": e.get("op"), "reason": e.get("reason", "")}
                for _, e in edges if e.get("state") == "rejected"]
    gv = goalsview.goals_view(eng.dag)
    snap = {"nodes": len(list(eng.dag.iter_nodes())),
            "edges": len(edges), "rejected": rejected,
            "open_goals": len(gv["open"]) + len(gv.get("case", [])),
            "open_design_goals": len(gv["open"]),
            "open_case_requires": len(gv.get("case", [])),
            "verify": "OK" if not verify_store(eng) else "FAILED"}
    print(json.dumps(snap, ensure_ascii=False, indent=1))
    return 0


def cmd_iterate(a):
    """fk iterate <script.fcad> --budget N [--agent cmd] — strategy/loop.py."""
    from ..strategy.loop import run_iterate
    return run_iterate(a)


def cmd_verify(a):
    eng = _engine()
    problems = verify_store(eng)
    if problems:
        print(f"VERIFY FAILED ({len(problems)}):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("verify OK: all edges replay, links exact, contracts current, "
          "media within capacity")
    return 0


def verify_store(eng: Engine) -> list[str]:
    """Whole-store fail-closed recheck (pure recomputation, no mutation).

    P7a red line: `review` edges are schema-checked only — soft
    obligations, evidence present — and the VLM is NEVER re-run here."""
    problems = []
    for edge_d, e in eng.dag.iter_edges():
        state = e.get("state")
        if state == "promoted":
            obs = e.get("certificate", {}).get("obligations", [])
            hard_bad = [o["id"] for o in obs
                        if o.get("class", "hard") == "hard" and o.get("holds") is not True]
            if hard_bad:
                problems.append(f"{_short(edge_d)}: promoted but hard obligations "
                                f"undischarged: {hard_bad}")
            if not e.get("certificate", {}).get("evidence"):
                problems.append(f"{_short(edge_d)}: promoted without evidence")
            if e.get("op") == "review":
                if any(o.get("class") != "soft" for o in obs):
                    problems.append(f"{_short(edge_d)}: review edge carries a "
                                    f"non-soft obligation — VLM may not gate")
    for node_d, payload in eng.dag.iter_nodes():
        if payload.get("facet") == "MIND":
            spec = payload.get("spec") or {}
            if spec.get("plant_name"):
                cur = eng.store.names().get(spec["plant_name"])
                if cur and cur != spec.get("plant_ref"):
                    problems.append(f"{_short(node_d)}: [P1] plant-model-current "
                                    f"failed ({spec['plant_name']} moved on)")
        stale = contracts.stale_terms(eng.store, payload.get("spec") or {})
        if stale:
            problems.append(f"{_short(node_d)}: {len(stale)} stale term reference(s)")
    for node_d, payload in eng.dag.iter_nodes():
        if payload.get("role") == "Medium":
            led = contracts.ledger(eng.dag, node_d)
            for o in led["obligations"]:
                if not o.holds:
                    problems.append(f"medium {_short(node_d)}: {o.prop}")
    return problems


# ------------------------------------------------------------------ main --
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fk",
                                 description="FluxKernel — CAD+MBSE design kernel CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("run"); s.add_argument("script")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("goals"); s.set_defaults(fn=cmd_goals)
    s = sub.add_parser("sorry"); s.add_argument("--all", action="store_true",
                                                help="include collapsed holes")
    s.set_defaults(fn=cmd_sorry)
    s = sub.add_parser("risks"); s.set_defaults(fn=cmd_risks)
    s = sub.add_parser("impact"); s.add_argument("ref", nargs="?")
    s.add_argument("--set", action="append", default=[],
                   help="<set>/<key>=<value> (repeatable)")
    s.add_argument("--apply", action="store_true",
                   help="replay in a shadow store and re-verify")
    s.set_defaults(fn=cmd_impact)
    s = sub.add_parser("goal"); s.add_argument("ref"); s.set_defaults(fn=cmd_goal)
    s = sub.add_parser("next"); s.set_defaults(fn=cmd_next)

    s = sub.add_parser("lint"); s.add_argument("ref", nargs="?")
    s.add_argument("--rule", default=None); s.set_defaults(fn=cmd_lint)
    s = sub.add_parser("ledger"); s.add_argument("medium"); s.set_defaults(fn=cmd_ledger)
    s = sub.add_parser("elicit"); s.add_argument("node")
    s.add_argument("--answers"); s.set_defaults(fn=cmd_elicit)

    s = sub.add_parser("node"); s.add_argument("name")
    s.add_argument("--role", required=True); s.add_argument("--kind")
    s.add_argument("--spec"); s.add_argument("--facet", choices=["BODY", "MIND"])
    s.set_defaults(fn=cmd_node)
    s = sub.add_parser("refine"); s.add_argument("goal"); s.add_argument("--via", required=True)
    s.add_argument("--out"); s.add_argument("--role"); s.add_argument("--kind")
    s.add_argument("--spec"); s.add_argument("--arg", action="append")
    s.set_defaults(fn=cmd_refine)
    s = sub.add_parser("eval"); s.add_argument("goal"); s.add_argument("--with",
                                                                       dest="with_",
                                                                       required=True)
    s.add_argument("--fidelity", type=int, default=0); s.add_argument("--expect")
    s.set_defaults(fn=cmd_eval)
    s = sub.add_parser("exact"); s.add_argument("goal"); s.add_argument("--from",
                                                                        dest="from_",
                                                                        default="catalog")
    s.add_argument("--match", default=""); s.add_argument("--out")
    s.set_defaults(fn=cmd_exact)
    s = sub.add_parser("procure"); s.add_argument("goal"); s.add_argument("--from",
                                                                          dest="from_",
                                                                          default="catalog")
    s.add_argument("--match", default=""); s.add_argument("--out")
    s.set_defaults(fn=cmd_procure)
    s = sub.add_parser("compose"); s.add_argument("inputs", nargs="+"); s.add_argument("--out",
                                                                                       required=True)
    s.add_argument("--role"); s.add_argument("--kind"); s.add_argument("--rollup")
    s.set_defaults(fn=cmd_compose)
    s = sub.add_parser("integrate"); s.add_argument("inputs", nargs="+")
    s.add_argument("--out", required=True); s.add_argument("--closes", nargs="*",
                                                           default=[])
    s.add_argument("--from", dest="from_"); s.add_argument("--match", default="")
    s.set_defaults(fn=cmd_integrate)
    s = sub.add_parser("abstract"); s.add_argument("node"); s.add_argument("--back-to",
                                                                           dest="back_to")
    s.add_argument("--reason", default=""); s.set_defaults(fn=cmd_abstract)
    s = sub.add_parser("manufacture"); s.add_argument("part"); s.add_argument("--into")
    s.set_defaults(fn=cmd_manufacture)
    s = sub.add_parser("print"); s.add_argument("part"); s.add_argument("printer")
    s.add_argument("--out"); s.set_defaults(fn=cmd_print)

    s = sub.add_parser("realize"); s.add_argument("root")
    s.add_argument("--until", default="standard-part")
    s.add_argument("--printer", default=None,
                   help="print resource ref for termination-set mode")
    s.add_argument("--max-steps", type=int, default=256)
    s.set_defaults(fn=cmd_realize)
    s = sub.add_parser("evolve"); s.add_argument("goal")
    s.add_argument("--printer", default=None,
                   help="print resource for termination-swap mutations")
    s.add_argument("--pop", type=int, default=8); s.add_argument("--gen", type=int, default=3)
    s.add_argument("--select-by", default="cost,mass_g")
    s.add_argument("--archive", default="")
    s.set_defaults(fn=cmd_evolve)
    s = sub.add_parser("watch"); s.add_argument("script"); s.set_defaults(fn=cmd_watch)

    s = sub.add_parser("check"); s.add_argument("ref"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("graph"); s.add_argument("--dot", action="store_true")
    s.set_defaults(fn=cmd_graph)
    s = sub.add_parser("why"); s.add_argument("ref"); s.set_defaults(fn=cmd_why)
    s = sub.add_parser("log"); s.set_defaults(fn=cmd_log)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("search"); s.add_argument("query"); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("show"); s.add_argument("ref"); s.add_argument("--json",
                                                                      action="store_true")
    s.set_defaults(fn=cmd_show)
    s = sub.add_parser("export"); s.add_argument("ref"); s.add_argument("--step")
    s.add_argument("--stl"); s.set_defaults(fn=cmd_export)
    s = sub.add_parser("trace"); s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_trace)
    s = sub.add_parser("render"); s.add_argument("--png", required=True)
    s.add_argument("--view", default="all",
                   choices=["iso", "front", "top", "right", "all"])
    s.add_argument("--title", default="")
    s.add_argument("--theme", default="dark", choices=["dark", "light"])
    s.add_argument("--with-equipment", action="store_true")
    s.set_defaults(fn=cmd_render)
    s = sub.add_parser("review"); s.add_argument("ref", nargs="?")
    s.add_argument("--selftest", action="store_true")
    s.add_argument("--vs", default="")
    s.add_argument("--budget-rounds", type=int, default=1)
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("report"); s.set_defaults(fn=cmd_report)
    s = sub.add_parser("iterate"); s.add_argument("script")
    s.add_argument("--budget", type=int, default=50)
    s.add_argument("--agent", default="")
    s.add_argument("--no-vlm", action="store_true")
    s.set_defaults(fn=cmd_iterate)
    s = sub.add_parser("verify"); s.set_defaults(fn=cmd_verify)
    return p


def main(argv=None):
    p = build_parser()
    a = p.parse_args(argv)
    rc = a.fn(a)
    sys.exit(0 if rc is None else rc)


if __name__ == "__main__":
    main()
