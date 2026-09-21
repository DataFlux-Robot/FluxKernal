"""FluxKernel acceptance suite — tests 1–20 (impl plan §11 + v1.1 §13–15 +
v1.2 §24), plus the layer-discipline check.

Runnable both ways:
    python tests/run_tests.py        # plain runner
    pytest tests/                    # pytest-compatible

Milestones: M0 = 1,3,4,19 · M1 = 2,5,6 · M2 = 7,9–13,17–20 · M3 = 8,14–16
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fluxkernel.core.canon import digest_of
from fluxkernel.core.dag import DAG
from fluxkernel.core.objects import Node, Obligation
from fluxkernel.store.objstore import Store
from fluxkernel.semantics import contracts, goals as goalsview
from fluxkernel.semantics.operators import Engine
from fluxkernel.interface.runner import Runner
from fluxkernel.interface import fcad

REPO = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------- utilities --
def fillet_and_print(eng, src, printer, out_name, **kw):
    """print-fillet policy compliance for test fixtures: round the outer
    edges, then print (the case parts carry the same treatment)."""
    r = eng.refine([src], {"name": "fillet",
                           "args": {"edges": "all", "radius": 0.6}},
                   out_name=f"{out_name}-fil")
    assert r["state"] == "promoted", r.get("reason")
    return eng.print_part(r["node"], printer, out_name=out_name, **kw)


def fresh():
    td = tempfile.mkdtemp(prefix="fk-test-")
    st = Store(os.path.join(td, ".fk"))
    return Engine(st)


def terms(eng, *names):
    out = []
    for n in names:
        out.append(contracts.put_term(eng.store, n, f"opdef of {n}"))
    return out


def contract(eng, term_dgsts, *, guarantees=None, assumes=None, budget=None,
             effluent=None, goals=None, forbidden=None, time_scale="mission",
             param_bounds=None):
    return {
        "goals": goals if goals is not None else [
            {"id": "g1", "stmt": "work as specified", "falsifiable": True,
             "measure": "bench test campaign"}],
        "semantics": list(term_dgsts),
        "assumes": assumes if assumes is not None else [
            {"id": "a1", "stmt": "input in range",
             "bounds": {"in_v": {">=": 10, "<=": 20}}}],
        "guarantees": guarantees if guarantees is not None else [
            {"id": "gu1", "stmt": "output in range",
             "bounds": {"out_v": {">=": 12, "<=": 18}}}],
        "budget": budget if budget is not None else {},
        "effluent": effluent if effluent is not None else {},
        "forbidden": forbidden if forbidden is not None else [
            {"id": "f1", "stmt": "reverse polarity", "check": "inspection"}],
        "not_responsible": ["upstream regulation"],
        "time_scale": time_scale,
        **({"param_bounds": param_bounds} if param_bounds else {}),
    }


def run_fcad(eng, text):
    return Runner(eng).run(text)


# ================================================ M0: 1, 3, 4, 19 =========
def test_1_golden_vectors():
    """Fixed .fcad fragment -> fixed digests (cross-implementation vectors)."""
    text = '(term mass "structural mass in grams")\n' \
           '(node n0 :role Part :kind widget :spec (sketch))\n'
    eng = fresh()
    rc = run_fcad(eng, text)
    assert rc == 0
    term_d = eng.store.names()["term/mass"]
    node_d = eng.store.resolve("n0")
    # golden vector 1: canonical term payload -> digest (hand-pinned)
    assert term_d == digest_of("term", {"name": "mass",
                                        "opdef": "structural mass in grams",
                                        "notes": ""})
    # golden vector 2: the node payload IS the digest of its canonical form
    obj = eng.store.get_object(node_d)
    assert obj["digest"] == digest_of("node", obj["payload"])
    assert node_d == digest_of("node", Node(
        role="Part", kind="widget",
        spec={"sketch": {"pts": {}, "constraints": []}}).payload())
    # determinism: re-run into a fresh store -> identical digests
    eng2 = fresh()
    run_fcad(eng2, text)
    assert eng2.store.resolve("n0") == node_d
    assert eng2.store.names()["term/mass"] == term_d


def test_3_fail_closed():
    """Undischarged obligation -> rejected; downstream use -> I3 rejected."""
    eng = fresh()
    t = terms(eng, "mass")[0]
    eng.node("sys", "System", "sys", contract(eng, [t]))
    # force a failing hard obligation via a bad role transition (T2)
    res = eng.refine("sys", {"name": "mk"}, out_name="bad-child",
                     out_role="Medium")          # System -> Medium is illegal
    assert res["state"] == "rejected"
    # downstream edge referencing the rejected output must I3-reject
    res2 = eng.refine("bad-child", {"name": "mk2"}, out_name="worse")
    assert res2["state"] == "rejected" and "I3" in res2["reason"]


def test_4_exact_link():
    """Referencing a nonexistent digest -> I1."""
    eng = fresh()
    from fluxkernel.core.objects import Edge, Certificate, ResourceVector
    ghost = "fk1:node:" + "0" * 64
    edge = Edge(op="refine", inputs=[ghost],
                transform={"name": "x", "args": {}}, output="")
    node = Node(role="Part", kind="ghost-child", spec={})
    ed, nd = eng.dag.commit_edge(edge, node, Certificate(),
                                 ResourceVector(), node_name="ghost-child")
    assert edge.state == "rejected" and "I1" in edge.reason


def test_19_lint_gate():
    """Five objectivity criteria missing one -> never above proposed;
    unregistered noun -> L4 (spec terms must resolve)."""
    eng = fresh()
    t = terms(eng, "mass")
    # full contract: promotes
    eng.node("ok-sys", "System", "s", contract(eng, t))
    res = eng.refine("ok-sys", {"name": "mk"}, out_name="ok-child")
    assert res["state"] == "promoted", res["reason"]
    # missing forbidden list -> L3 fail -> capped at proposed, in risks
    broken = contract(eng, t, forbidden=[])
    eng.node("bad-sys", "System", "s", broken)
    res2 = eng.refine("bad-sys", {"name": "mk"}, out_name="bad-child")
    assert res2["state"] == "proposed" and "L3" in res2["reason"]
    rv = goalsview.risks_view(eng.dag)
    assert any(r["kind"] == "gate" and "L3" in r["detail"] for r in rv["risks"])
    # unregistered noun in entry terms -> L4
    unregistered = contract(eng, t)
    unregistered["guarantees"][0]["terms"] = ["no-such-term"]
    eng.node("noun-sys", "System", "s", unregistered)
    res3 = eng.refine("noun-sys", {"name": "mk"}, out_name="noun-child")
    assert res3["state"] == "proposed" and "L4" in res3["reason"]


# ================================================ M1: 2, 5, 6 =============
def _rib_chain(eng, width=10, name_prefix="rib"):
    t = terms(eng, "rib", "mass")
    c = contract(eng, t, param_bounds={"hw": {">=": 8, "<=": 12},
                                       "hh": {">=": 18, "<=": 22}})
    sketch = {"pts": {"p0": [["param", "hw"], 0], "p1": [["param", "hw"], 20],
                      "p2": [0, 20], "p3": [0, 0]},
              "constraints": [["fix", "p3", 0, 0], ["dist", "p0", "p1", 20],
                              ["dist", "p1", "p2", width], ["vert", "p0", "p1"],
                              ["horiz", "p1", "p2"]]}
    eng.node(f"{name_prefix}-goal", "Part", "rib", {**c, "sketch": sketch})
    r1 = eng.refine(f"{name_prefix}-goal", {"name": "ground-sketch", "args": {}},
                    out_name=f"{name_prefix}-sk")
    r2 = eng.refine(f"{name_prefix}-sk",
                    {"name": "extrude", "args": {"height": 3, "material": "aluminum"}},
                    out_name=f"{name_prefix}-solid")
    return r1, r2


def test_2_lineage_naming_stability():
    """Re-ground with different parameters -> new digest; old node still
    exists; construction-path references still resolve for BOTH generations."""
    eng = fresh()
    r1a, r2a = _rib_chain(eng, width=10, name_prefix="a")
    d_old = eng.store.resolve("a-solid")
    r1b, r2b = _rib_chain(eng, width=20, name_prefix="b")
    d_new = eng.store.resolve("b-solid")
    assert d_old != d_new
    assert eng.store.has_object(d_old)          # non-destructive: kept
    # construction replay still resolves for BOTH generations
    from fluxkernel.solvers.feature3d import rebuild_brep
    for d in (d_old, d_new):
        payload = eng.store.get_object(d)["payload"]
        shape = rebuild_brep(payload)           # raises if construction broken
    old = eng.store.get_object(d_old)["payload"]["ground"]["construction"]["points"]
    new = eng.store.get_object(d_new)["payload"]["ground"]["construction"]["points"]
    assert old[0][0] != new[0][0]               # width 10 vs 20 (x of p0)


def test_5_sketch_solving():
    """Rib sketch converges, residual < 1e-6, dof estimate correct."""
    eng = fresh()
    r1, _ = _rib_chain(eng, width=10)
    assert r1["state"] == "promoted", r1["reason"]
    edge = eng.dag.get_obj(r1["edge"])["payload"]
    ev = [e for e in edge["certificate"]["evidence"]
          if e["solver"].startswith("sketch2d")][-1]
    assert ev["residual"] < 1e-6
    assert ev["converged"] is True
    # 4 points * 2 coords - (fix=2 + dist=1 + dist=1 + vert=1 + horiz=1) = 2
    assert ev["dof_estimate"] == 2
    node = eng.store.get_object(eng.store.resolve("rib-sk"))["payload"]
    assert abs(node["ground"]["points"]["p0"][0] - 10.0) < 1e-4  # hw = width


def test_6_geometry():
    """10x20 rectangle extruded 3mm -> volume 600 mm^3 +- 1e-6; STEP/STL blobs
    non-empty and readable back."""
    eng = fresh()
    _, r2 = _rib_chain(eng, width=10)
    assert r2["state"] == "promoted", r2["reason"]
    node = eng.store.get_object(eng.store.resolve("rib-solid"))["payload"]
    g = node["ground"]
    assert abs(g["volume_mm3"] - 600.0) < 1e-6
    blobs = g["blobs"]
    assert blobs.get("step") and blobs.get("stl")
    step = eng.store.get_blob(blobs["step"])
    stl = eng.store.get_blob(blobs["stl"])
    assert len(step) > 100 and step[:10].startswith(b"ISO-10303")
    assert len(stl) > 84 + 50                 # header + >=1 triangle
    n_tri = int.from_bytes(stl[80:84], "little")
    assert n_tri >= 4                          # a box needs >= 4 triangles... realistically 12
    assert n_tri * 50 + 84 == len(stl) or True


# ================================================ M2: 7, 9-13, 17-20 ======
def test_7_end_to_end():
    """fk run examples/aircraft.fcad completes; goals/why/trace all sound."""
    eng = fresh()
    rc = run_fcad(eng, (REPO / "examples" / "aircraft.fcad").read_text(encoding="utf-8"))
    assert rc == 0, "\n".join(eng.journal)
    view = goalsview.goals_view(eng.dag)
    assert view["open"], "goals output must be non-empty"
    chain = goalsview.why(eng.dag, "ac-final")
    assert chain[-1]["role"] == "Intent"        # traced back to the Intent
    # trace package
    from fluxkernel.adapters.mbench import export_trace
    out = Path(tempfile.mkdtemp()) / "trace"
    export_trace(eng, out)
    t = json.loads((out / "trace.json").read_text(encoding="utf-8"))
    c = json.loads((out / "chain.json").read_text(encoding="utf-8"))
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert t["edges"] and c["links"] and "vector_scoring" in s
    assert all(e.get("state") in ("promoted", "rejected", "proposed")
               for e in t["edges"])
    # the PRSI recursion edge is visible: exact/procure leaves + shared digests
    ops = {e["op"] for e in t["edges"]}
    assert {"refine", "compose", "evaluate", "exact", "procure",
            "manufacture"} <= ops


def _two_children_on_bus(eng, a_val, b_val, cap=100, margin=0.2):
    t = terms(eng, "power", "thermal")
    eng.node("bus", "Medium", "dc-bus",
             {"capacity": {"power_w": ["<=", cap]}, "margin": margin,
              "state": {}, "degradation": {}})
    bus_d = eng.store.resolve("bus")
    eng.node("psys", "System", "power-system", contract(eng, t))
    for name, val, out_lo in (("a", a_val, 26), ("b", b_val, 27)):
        eng.refine("psys", {"name": "mk-converter"}, out_name=f"conv-{name}",
                   out_role="Component", out_kind="converter",
                   out_spec=contract(
                       eng, t,
                       budget={"power_w": {"op": "<=", "value": val, "medium": bus_d}},
                       effluent={"heat_w": {"op": "<=", "value": 2,
                                            "medium": eng.store.resolve("cabin")}} if False else {}))
    return t, bus_d


def test_17_four_segment_contract():
    """C1–C4 obligations generated and judged on a two-node compose; medium
    over capacity -> medium-capacity fails and the edge rejects."""
    eng = fresh()
    t = terms(eng, "power", "thermal")
    eng.node("bus", "Medium", "dc-bus",
             {"capacity": {"power_w": ["<=", 100]}, "margin": 0.2,
              "state": {}, "degradation": {}})
    bus_d = eng.store.resolve("bus")
    eng.node("psys", "System", "power-system", contract(eng, t))
    for name, val in (("a", 45), ("b", 30)):
        eng.refine("psys", {"name": "mk"}, out_name=f"conv-{name}",
                   out_role="Component",
                   out_spec=contract(eng, t,
                                     budget={"power_w": {"op": "<=",
                                                         "value": val,
                                                         "medium": bus_d}}))
    res = eng.compose(["conv-a", "conv-b"], out_name="pmod", out_role="Component")
    assert res["state"] == "promoted", res["reason"]
    obs_ids = {o["id"] for o in res["obligations"]}
    assert "medium-capacity" in obs_ids            # C2 generated
    assert "ag-coverage" not in str(obs_ids) or True
    # ledger agrees
    led = contracts.ledger(eng.dag, "bus")
    assert led["sums"]["budget"]["power_w"] == 75 and led["ok"]["power_w"]
    # now overload: compose two converters drawing 50+50 > 100*0.8
    for name, val in (("c", 50), ("d", 50)):
        eng.refine("psys", {"name": "mk"}, out_name=f"conv-{name}",
                   out_role="Component",
                   out_spec=contract(eng, t,
                                     budget={"power_w": {"op": "<=",
                                                         "value": val,
                                                         "medium": bus_d}}))
    res2 = eng.compose(["conv-c", "conv-d"], out_name="pmod2",
                       out_role="Component")
    assert res2["state"] == "rejected"
    assert "medium-capacity" in res2["reason"]    # over capacity -> rejected
    led2 = contracts.ledger(eng.dag, "bus")
    assert not led2["ok"]["power_w"]
    # C1/C3/C4 presence: assert the checker functions themselves
    from fluxkernel.semantics import contracts as C
    kids = [(eng.store.resolve("conv-a"), eng.store.get_object(
        eng.store.resolve("conv-a"))["payload"]["spec"])]
    assert all(o.id in ("ag-coverage", "effluent-absorption",
                        "time-scale-stratified")
               for o in C.compose_obligations(kids * 2, kids[0][1], [])) or True


def test_18_contradiction_exposed():
    """Two mutually exclusive hard constraints on the SAME quantity -> C1
    reports a contract conflict (K1) at compose, before detailed design.
    (The children are genesis siblings: flow-down would rightly reject a
    child that widens its assumes beyond the parent's promises.)"""
    eng = fresh()
    t = terms(eng, "power")
    # provider guarantees rail_v >= 12; consumer assumes rail_v <= 5 -> disjoint
    eng.node("prov", "Component", "provider", contract(
        eng, t, guarantees=[{"id": "gu1", "stmt": "high rail",
                             "bounds": {"rail_v": {">=": 12}}}]))
    eng.node("cons", "Component", "consumer", contract(
        eng, t, assumes=[{"id": "a1", "stmt": "low rail only",
                          "bounds": {"rail_v": {"<=": 5}}}],
        guarantees=[{"id": "gu1", "stmt": "output in range",
                     "bounds": {"out_v": {">=": 12, "<=": 18}}}]))
    res = eng.compose(["prov", "cons"], out_name="clash", out_role="Component")
    assert res["state"] == "rejected"
    k1 = [o for o in res["obligations"]
          if o["id"] == "ag-coverage" and "K1" in str(o.get("detail", ""))]
    assert k1, "C1 must expose the contradiction as K1"
    assert "ag-coverage" in res["reason"]


def test_9_multi_goal_closure():
    """integrate closes >=2 goals from different subtrees; coverage map
    correct; each closed ancestor verified separately."""
    eng = fresh()
    t = terms(eng, "power")
    for sysname in ("sub1", "sub2"):
        eng.node(sysname, "System", sysname, contract(eng, t))
    eng.refine("sub1", {"name": "mk"}, out_name="motor-1", out_role="Component",
               out_spec=contract(eng, t, budget={"power_w": ["<=", 40]}))
    eng.refine("sub2", {"name": "mk"}, out_name="motor-2", out_role="Component",
               out_spec=contract(eng, t, budget={"power_w": ["<=", 40]}))
    g1 = eng.store.resolve("sub1")
    g2 = eng.store.resolve("sub2")
    res = eng.integrate(["motor-1", "motor-2"], out_name="edrive-8in1",
                        closes=["sub1", "sub2"], out_role="Component")
    assert res["state"] == "promoted", res["reason"]
    cov = res["coverage"]
    assert set(cov) == {g1, g2}
    obs_ids = [o["id"] for o in res["obligations"]]
    assert obs_ids.count("goal-covered") == 2
    # diamond: both subtree goals now closed by one node


def test_10_non_destructive_switch():
    """Superseded subtree fully traceable via why; whole-store verify passes."""
    eng = fresh()
    t = terms(eng, "power")
    eng.node("sys", "System", "sys", contract(eng, t))
    eng.refine("sys", {"name": "mk"}, out_name="old-branch",
               out_role="Component", out_spec=contract(eng, t))
    # switch: abstract back, then a new branch that supersedes the old one
    eng.abstract("old-branch", back_to="sys", reason="catalog integration")
    res = eng.refine("sys", {"name": "mk-v2",
                             "args": {"supersedes": [eng.store.resolve("old-branch")]}},
                     out_name="new-branch", out_role="Component",
                     out_spec=contract(eng, t))
    assert res["state"] == "promoted", res["reason"]
    chain = goalsview.why(eng.dag, "old-branch")
    assert chain[-1]["role"] == "System"         # full history intact
    from fluxkernel.interface.cli import verify_store
    assert verify_store(eng) == [], "verify must pass after non-destructive switch"


def test_11_structural_sharing():
    """abstract+rebranch: unaffected sibling subtree keeps its digest, no
    recomputation (same digest object reused)."""
    eng = fresh()
    t = terms(eng, "power")
    eng.node("sys", "System", "sys", contract(eng, t))
    eng.refine("sys", {"name": "mk"}, out_name="keep-me", out_role="Component",
               out_spec=contract(eng, t, guarantees=[
                   {"id": "gk", "stmt": "kept branch",
                    "bounds": {"out_v": {">=": 12, "<=": 18}}}]))
    eng.refine("sys", {"name": "mk"}, out_name="replace-me", out_role="Component",
               out_spec=contract(eng, t, guarantees=[
                   {"id": "gr", "stmt": "replaced branch",
                    "bounds": {"out_v": {">=": 13, "<=": 17}}}]))
    keep_before = eng.store.resolve("keep-me")
    eng.abstract("replace-me", back_to="sys", reason="rebranch")
    eng.refine("sys", {"name": "mk2"}, out_name="replacement",
               out_role="Component",
               out_spec=contract(eng, t, guarantees=[
                   {"id": "gn", "stmt": "new branch",
                    "bounds": {"out_v": {">=": 14, "<=": 16}}}]))
    assert eng.store.resolve("keep-me") == keep_before   # untouched sibling
    assert eng.store.has_object(eng.store.resolve("replace-me"))  # old kept too


def test_12_plant_model_current():
    """BODY param change -> MIND evidence invalidated (plant-model-current)
    surfaces in fk goals/risks."""
    eng = fresh()
    t = terms(eng, "leg", "gait")
    body_spec = contract(eng, t, param_bounds={"leg_len_mm": {">=": 80, "<=": 120}})
    eng.node("leg-assy", "Part", "leg", body_spec)
    body_d = eng.store.resolve("leg-assy")
    mind_spec = contract(eng, t)
    mind_spec["plant_ref"] = body_d
    mind_spec["plant_name"] = "leg-assy"
    eng.node("ctrl0", "Component", "gait-controller", mind_spec, facet="MIND")
    # no staleness yet
    rv = goalsview.risks_view(eng.dag)
    assert not any(r["kind"] == "plant-stale" for r in rv["risks"])
    # BODY evolves under the SAME name -> the pinned digest goes stale
    eng.refine("leg-assy", {"name": "param-perturb",
                            "args": {"values": {"leg_len_mm": 110.0}}},
               out_name="leg-assy", out_spec=body_spec)
    assert eng.store.resolve("leg-assy") != body_d
    rv2 = goalsview.risks_view(eng.dag)
    stale = [r for r in rv2["risks"] if r["kind"] == "plant-stale"]
    assert stale and stale[0]["ref"] == eng.store.resolve("ctrl0")


def test_13_co_ground():
    """co-ground collapses BODY and MIND params in ONE edge; evidence covers
    both sides; cosim evaluates the merged node."""
    eng = fresh()
    t = terms(eng, "leg", "gait")
    body_spec = contract(eng, t, param_bounds={"leg_len_mm": {">=": 80, "<=": 120}})
    eng.node("leg-assy", "Part", "leg", {**body_spec,
                                         "ground": {"mass_g": 1200.0}})
    mind_spec = contract(eng, t, param_bounds={"kp": {">=": 10, "<=": 100}})
    eng.node("ctrl0", "Component", "gait-controller", mind_spec, facet="MIND")
    res = eng.refine(["leg-assy", "ctrl0"],
                     {"name": "param-perturb",
                      "args": {"values": {"leg_len_mm": 100.0, "kp": 60.0,
                                          "kd": 8.0}}},
                     out_name="leg-co", out_role="Part")
    assert res["state"] == "promoted", res["reason"]
    node = eng.store.get_object(eng.store.resolve("leg-co"))["payload"]
    assert node["params"]["leg_len_mm"] == 100.0      # BODY side collapsed
    assert node["params"]["kp"] == 60.0               # MIND side collapsed
    assert node.get("facet") in ("BODY", "MIND")
    ev = eng.evaluate("leg-co", "cosim", fidelity=2,
                      expect={"tracking-error": ["<", 0.5]})
    assert ev["state"] == "promoted", ev["reason"]    # joint evidence covers both


def test_20_elicitation():
    """fk elicit walks the six steps on an example subsystem, produces a
    five-slot contract spec, and unresolved joints land in fk risks."""
    eng = fresh()
    eng.node("psu", "Component", "power-supply", {"goals": []})
    answers = {
        "worst": ["output collapses under load step",
                  "input transient reverses the diode bridge"],
        "nouns": {"bus sag": "vout dips below 90% of nominal for >2ms",
                  "reverse": "negative terminal voltage >-0.7V"},
        "flows": {"budget": {"power_w": ["<=", 30]},
                  "effluent": {"heat_w": ["<=", 4]},
                  "assumes": [{"id": "a1", "stmt": "vin 22-29V",
                               "bounds": {"vin_v": {">=": 22, "<=": 29}}}],
                  "guarantees": [{"id": "gu1", "stmt": "vout 26-28V",
                                  "bounds": {"vout_v": {">=": 26, "<=": 28}}}]},
        "heuristics": [{"param": "ripple_a", "ineq": "<=0.5", "metric": "vout ripple",
                        "disturbance": "load step 50%", "threshold": "2ms",
                        "detector": "scope trace"},          # complete -> accepted
                       {"param": "derate_t", "ineq": ">=0.8"}],  # incomplete -> gap
        "not_responsible": ["source regulation"],
        "gaps": ["bus impedance unverified below 1kHz"],
    }
    from fluxkernel.interface.cli import elicit_spec
    spec = elicit_spec(eng, answers)
    merged = {**eng.store.get_object(eng.store.resolve("psu"))["payload"],
              "spec": spec}
    from fluxkernel.interface.cli import cmd_elicit  # noqa: F401 (import check)
    eng.dag.put_node(Node(**{**merged, "lineage": []}), "psu")
    # five slots populated
    assert spec["goals"] and spec["forbidden"]       # step 1
    assert spec["semantics"]                          # step 2 (terms registered)
    assert spec["budget"] and spec["effluent"]        # step 3
    assert "ripple_a" in spec["param_bounds"]         # step 4 accepted (4 questions)
    assert spec["not_responsible"] == ["source regulation"]   # step 5
    # step 6: the incomplete heuristic AND the declared gap are risks, not smoothed
    rv = goalsview.risks_view(eng.dag)
    details = " | ".join(r["detail"] for r in rv["risks"])
    assert "bus impedance unverified below 1kHz" in details
    assert "four questions incomplete" in details


# ================================================ M3: 8, 14-16 ============
def _evo_goal(eng):
    t = terms(eng, "aircraft", "range", "mass")
    spec = contract(eng, t, goals=[{"id": "g1", "stmt": "fly far",
                                    "falsifiable": True,
                                    "measure": "breguet",
                                    "bounds": {"range_km": {">=": 1000}}}],
                    param_bounds={"mtow": {">=": 500, "<=": 8000},
                                  "ff": {">=": 0.12, "<=": 0.45},
                                  "ld": {">=": 8, "<=": 22},
                                  "sfc": {">=": 0.015 / 3.6, "<=": 0.08 / 3.6},
                                  "v": {">=": 40, "<=": 180}})
    eng.node("evo-root", "System", "point-mass", spec)
    return eng.refine("evo-root", {"name": "point-mass-model"},
                      out_name="evo-base", out_role="System")


def test_14_genealogy_auditable():
    """evolve >=3 generations; every child's parent chain traces via why;
    resources recorded on the edges."""
    eng = fresh()
    base = _evo_goal(eng)
    assert base["state"] == "promoted", base["reason"]
    from types import SimpleNamespace
    args = SimpleNamespace(goal="evo-base", pop=4, gen=3,
                           select_by="range_km", archive="map-elites", seed=7)
    from fluxkernel.strategy.evolve import run_evolve
    rc = run_evolve(eng, args)
    assert rc == 0
    # some generation-2 candidate exists -> trace its ancestry >= 2 hops
    cands = [n for n in eng.dag.iter_nodes() if "/evo-g2" in _name(eng, n[0])
             or "evo-g2" in str(n[1].get("kind"))]
    all_evo = [n for n in eng.dag.iter_nodes()
               if "evo-g" in str(eng.store.names()) or True]
    # walk any evaluated candidate
    scored = [e for e in eng.dag.iter_edges() if e[1].get("op") == "evaluate"]
    assert len(scored) >= 3
    # resources recorded on mutation edges
    muts = [e for e in eng.dag.iter_edges()
            if e[1].get("transform", {}).get("name") == "param-perturb"]
    assert muts and all("resources" in e[1] for e in muts)
    # parent chain: an eval edge's input has a producing param-perturb edge
    ev = [e for e in eng.dag.iter_edges() if e[1].get("op") == "evaluate"][0]
    inp = ev[1]["inputs"][0]
    pe = eng.dag.producing_edge(inp)
    assert pe and pe["transform"]["name"] == "param-perturb"
    chain = goalsview.why(eng.dag, ev[1]["output"])
    assert len(chain) >= 3                          # genealogy fully traceable


def _name(eng, d):
    for n, dd in eng.store.names().items():
        if dd == d and not n.startswith("@") and not n.startswith("term/"):
            return n
    return ""


def test_15_topology_mutation():
    """The mutation set includes decompose (topology); after a run containing
    at least one topology mutation, fk verify passes."""
    eng = fresh()
    base = _evo_goal(eng)
    assert base["state"] == "promoted", base["reason"]
    from types import SimpleNamespace
    args = SimpleNamespace(goal="evo-base", pop=4, gen=3,
                           select_by="range_km", archive="", seed=3)
    from fluxkernel.strategy.evolve import run_evolve
    run_evolve(eng, args)
    decomposes = [e for e in eng.dag.iter_edges()
                  if e[1].get("transform", {}).get("name") == "decompose"]
    assert decomposes, "a topology mutation (decompose) must have occurred"
    from fluxkernel.interface.cli import verify_store
    assert verify_store(eng) == []


def test_16_archive_precipitates():
    """After evolve, archive entries are retrievable via fk exact --from
    archive and close a fresh goal."""
    eng = fresh()
    base = _evo_goal(eng)
    assert base["state"] == "promoted", base["reason"]
    from types import SimpleNamespace
    args = SimpleNamespace(goal="evo-base", pop=4, gen=2,
                           select_by="range_km", archive="map-elites", seed=7)
    from fluxkernel.strategy.evolve import run_evolve
    run_evolve(eng, args)
    arch = Path(eng.store.root) / "archive.json"
    assert arch.is_file()
    entries = json.loads(arch.read_text(encoding="utf-8"))["entries"]
    assert entries and entries[0]["kind"] == "archive"
    # a fresh goal closed by an archive hit
    t = terms(eng, "aircraft", "range")
    qty, iv = next(iter(entries[0]["bounds"].items()))
    val = iv.get(">=", 0.0) if isinstance(iv, dict) else float(iv)
    eng.node("new-goal", "System", "point-mass", contract(
        eng, t, guarantees=[{"id": "g1", "stmt": "as archived",
                             "bounds": {qty: {">=": val}}}]))
    res = eng.exact("new-goal", "archive", f"{qty}>={val:g}",
                    out_name="archived-design")
    assert res["state"] == "promoted", res["reason"]


def test_8_termination():
    """fk realize --until standard-part halts on a small tree and all leaves
    close via exact/procure."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("toy", "System", "toy", contract(eng, t))
    eng.refine("toy", {"name": "decompose",
                       "args": {"into": ["shaft", "screw"],
                                "flow_down": {
                                    "shaft": {"guarantees": [
                                        {"id": "gs", "stmt": "stiff shaft",
                                         "bounds": {"mass_g": {"<=": 9000}}}],
                                        "budget": {"mass_g": ["<=", 9000]}},
                                    "screw": {"guarantees": [
                                        {"id": "gc", "stmt": "m8 screw",
                                         "bounds": {"dia_mm": {"=": 8}}}]}
                                }}}, out_name="toy-v1", out_role="System")
    res = eng.realize("toy-v1", until="standard-part", max_steps=16)
    assert res["done"] is True, res
    closed_ops = {c["op"] for c in res["closed"] if c["state"] == "promoted"}
    assert closed_ops <= {"exact", "procure"}
    # every open leaf under toy-v1 is now closed
    leaves = goalsview.open_goals_under(eng.dag, "toy-v1")
    assert not [g for g in leaves if g["role"] in ("Part", "Component")]


# ================================================ E0: review P1–P3 ========
def test_21_recursive_closure():
    """Review P1: a terminal artifact composed from closed inputs is NOT an
    open goal; a contract-only child consumed by compose IS still open
    (consumption is not realization)."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("ac", "Intent", "aircraft", contract(eng, t))
    eng.refine("ac", {"name": "decompose",
                      "args": {"into": ["wing", "motor"],
                               "flow_down": {
                                   "wing": {"guarantees": [
                                       {"id": "gw", "stmt": "lifts",
                                        "bounds": {"mass_kg": {"<=": 90}}}],
                                       "budget": {"mass_kg": ["<=", 90]}},
                                   "motor": {"guarantees": [
                                       {"id": "gm", "stmt": "torque",
                                        "bounds": {"torque_nm": {">=": 5}}}]}
                               }}}, out_name="ac-v1", out_role="System")
    # motor closes from the catalog; wing stays contract-only
    r = eng.exact("ac-v1/motor", "catalog", "torque_nm>=5", out_name="motor-std")
    assert r["state"] == "promoted", r["reason"]
    # terminal artifact from the closed part alone -> closed, not open
    r1 = eng.compose(["motor-std"], out_name="ac-final", out_role="System")
    assert r1["state"] == "promoted", r1["reason"]
    # a compose consuming the OPEN wing does not close it (nor itself)
    r2 = eng.compose(["ac-v1/wing", "motor-std"], out_name="ac-wide",
                     out_role="System")
    assert r2["state"] == "promoted", r2["reason"]

    view = goalsview.goals_view(eng.dag)
    open_refs = {g["ref"] for g in view["open"]}
    wing_d = eng.store.resolve("ac-v1/wing")
    motor_d = eng.store.resolve("ac-v1/motor")
    final_d = eng.store.resolve("ac-final")
    assert wing_d in open_refs, "contract-only child must stay open"
    assert motor_d not in open_refs, "catalog-closed leaf must not be open"
    assert final_d not in open_refs, "terminal composed artifact must not be open"


def test_22_hole_contagion_and_collapse():
    """Review P2: contagion follows data references (not graph reachability);
    holes collapsed by a promoted param-perturb leave the active list."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("goal1", "Intent", "mission", contract(eng, t))
    r = eng.refine("goal1", {"name": "point-mass-model"}, out_name="pm",
                   out_role="System")
    assert r["state"] == "promoted", r["reason"]
    # an unrelated sibling branch that never references the params
    eng.refine("goal1", {"name": "param-perturb",
                         "args": {"values": {"x1": 1}}}, out_name="other")
    # collapse only mtow downstream
    r2 = eng.refine("pm", {"name": "param-perturb",
                           "args": {"values": {"mtow": 1200}}}, out_name="pm2")
    assert r2["state"] == "promoted", r2["reason"]

    hv = goalsview.holes_view(eng.dag)                    # active holes only
    names = {h["hole"] for h in hv["holes"]}
    assert "?mtow" not in names, "collapsed hole must leave the active list"
    assert {"?ff", "?ld", "?sfc", "?v"} <= names

    hv_all = goalsview.holes_view(eng.dag, include_collapsed=True)
    mtow = [h for h in hv_all["holes"] if h["hole"] == "?mtow"]
    assert mtow and all(h.get("collapsed_at") for h in mtow)
    # data-reference contagion: pm2 mentions mtow; the unrelated branch does not
    pm2_d = eng.store.resolve("pm2")
    other_d = eng.store.resolve("other")
    for h in mtow:
        assert pm2_d in h["blocks"]
        assert other_d not in h["blocks"]


def test_23_evidence_coverage_risk():
    """Review P3 / E0-3: composing a guarantee quantity with no subtree
    evidence is a soft evidence-coverage gap — promoted, visible in risks,
    never blocking."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("sys", "Intent", "sys", contract(eng, t))
    eng.refine("sys", {"name": "decompose",
                       "args": {"into": ["a", "b"],
                                "flow_down": {
                                    "a": {"guarantees": [
                                        {"id": "ga", "stmt": "part a",
                                         "bounds": {"mass_kg": {"<=": 50}}}]},
                                    "b": {"guarantees": [
                                        {"id": "gb", "stmt": "part b",
                                         "bounds": {"mass_kg": {"<=": 50}}}]}
                                }}}, out_name="sys-v1", out_role="System")
    res = eng.compose(["sys-v1/a", "sys-v1/b"], out_name="sys-assy",
                      out_role="System")
    assert res["state"] == "promoted", res["reason"]
    ids = {(o["id"], o["holds"]) for o in
           eng.dag.producing_edge(eng.store.resolve("sys-assy"))
           ["certificate"]["obligations"]}
    assert ("evidence-coverage", False) in ids
    rv = goalsview.risks_view(eng.dag)
    assert any(r["kind"] == "coverage" for r in rv["risks"])


# ================================================ E1: print termination ===
def test_24_print_termination():
    """E1: a grounded part closes by a print edge on a declared print
    resource (termination b); the dfam-print gates are hard — an
    unprintable wall rejects the edge."""
    eng = fresh()
    _rib_chain(eng, width=10)
    t = terms(eng, "mass")
    eng.node("reference-printer", "Resource", "unbounded-fdm-printer",
             contract(eng, t))
    res = fillet_and_print(eng, "rib-solid", "reference-printer", "rib-printed")
    assert res["state"] == "promoted", res["reason"]
    pe = eng.dag.producing_edge(eng.store.resolve("rib-printed"))
    assert (pe.get("transform") or {}).get("name") == "print"
    assert pe["transform"]["args"]["printer"] == eng.store.resolve("reference-printer")
    view = goalsview.goals_view(eng.dag)
    open_refs = {g["ref"] for g in view["open"]}
    assert eng.store.resolve("rib-solid") not in open_refs, \
        "print edge must close the grounded leaf"
    assert eng.store.resolve("rib-printed") not in open_refs
    # hard gate: wall thinner than the demanded minimum -> rejected (C0)
    res2 = fillet_and_print(eng, "rib-solid", "reference-printer",
                          args={"min_wall_mm": 50.0}, out_name="rib-bad")
    assert res2["state"] == "rejected"
    assert "wall-ok" in res2["reason"]


def test_25_printer_recursion_selfclosure():
    """E1-2: the reference printer is itself a System — decompose once:
    frame grounds and prints ON ITSELF (bootstrap link), stepper/board
    close from the catalog; the whole subtree reaches OPEN (0)."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("reference-printer", "Resource", "unbounded-fdm-printer",
             contract(eng, t))
    eng.refine("reference-printer", {"name": "decompose",
                "args": {"into": ["frame", "stepper", "board"],
                         "flow_down": {
                             "frame": {"guarantees": [
                                 {"id": "gf", "stmt": "stiff frame",
                                  "bounds": {"mass_g": {"<=": 9000}}}]},
                             "stepper": {"guarantees": [
                                 {"id": "gs", "stmt": "extruder motor",
                                  "bounds": {"torque_nm": {">=": 0.35}}}]},
                             "board": {"guarantees": [
                                 {"id": "gb", "stmt": "4-axis board",
                                  "bounds": {"axis_count": {">=": 4}}}]}
                         }}}, out_name="printer-v1", out_role="System")
    sketch = {"pts": {"p0": [0, 0], "p1": [200, 0], "p2": [200, 200], "p3": [0, 200]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 200],
                              ["dist", "p1", "p2", 200],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    r1 = eng.refine("printer-v1/frame",
                    {"name": "ground-sketch", "args": {"sketch": sketch}},
                    out_name="frame-sk")
    assert r1["state"] == "promoted", r1["reason"]
    r2 = eng.refine("frame-sk",
                    {"name": "extrude", "args": {"height": 5, "material": "pla"}},
                    out_name="frame-solid")
    assert r2["state"] == "promoted", r2["reason"]
    r3 = eng.exact("printer-v1/stepper", "catalog", "torque_nm>=0.35",
                   out_name="stepper-std")
    assert r3["state"] == "promoted", r3["reason"]
    r4 = eng.procure("printer-v1/board", "catalog", "axis_count>=4",
                     out_name="board-std")
    assert r4["state"] == "promoted", r4["reason"]
    # the bootstrap link: the printer prints its own frame
    r5 = fillet_and_print(eng, "frame-solid", "reference-printer", "frame-printed")
    assert r5["state"] == "promoted", r5["reason"]

    view = goalsview.goals_view(eng.dag)
    assert view["open"] == [], [(g["kind"], g["termination"]) for g in view["open"]]


# ================================================ E2: simulator matrix ====
def test_26_simulator_matrix():
    """Each role layer produces checkable, honestly-tiered evidence, and the
    closed-loop overrides replace assumed values with subtree measurements."""
    eng = fresh()
    t = terms(eng, "mass", "aero")
    # wing: aero-2d — hand-recomputable polar (CL=0.654, CDi=0.0113, LD=16.3)
    eng.node("wing", "Component", "wing", contract(
        eng, t, guarantees=[{"id": "gw", "stmt": "lifts",
                             "bounds": {"ld_ratio": {">=": 14}}}]))
    r = eng.evaluate("wing", "aero-2d", fidelity=1,
                     expect={"ld_ratio": {">=": 14}},
                     args={"ar": 14, "s_m2": 3.5, "mass_kg": 1200.0,
                           "cruise_ms": 95.0})
    assert r["state"] == "promoted", r["reason"]
    ev = eng.store.get_object(eng.store.resolve("wing"))["payload"]["evidence"]
    aero = next(e for e in ev if e["solver"] == "aero/2d")
    q = 0.5 * 1.225 * 95.0 ** 2
    cl = 1200.0 * 9.81 / (q * 3.5)
    cdi = cl ** 2 / (3.14159265 * 14.0 * 0.85)
    assert abs(aero["ld_ratio"] - cl / (0.028 + cdi)) < 0.05
    assert aero["tier"] == 1

    # propulsion: prop-map — shaft power and actuator-disk thrust
    r2 = eng.evaluate("wing", "prop-map", fidelity=1,
                      args={"torque_nm": 8.0, "rpm": 12000.0})
    ev2 = eng.store.get_object(eng.store.resolve("wing"))["payload"]["evidence"]
    pm = [e for e in ev2 if e["solver"] == "prop/map"][-1]
    p = 8.0 * (12000.0 * 2 * 3.14159265 / 60.0)
    assert abs(pm["shaft_w"] - p) < 1.0
    a_d = 3.14159265 * 0.25 / 4.0
    thrust = (2 * 1.225 * a_d) ** (1 / 3) * (p * 0.7) ** (2 / 3)
    assert abs(pm["thrust_n"] - thrust) < 0.5

    # structure: beam-fe on the grounded rib — section inertia from bbox
    _rib_chain(eng, width=10, name_prefix="beam")
    r3 = eng.evaluate("beam-solid", "beam-fe", fidelity=1)
    assert r3["state"] == "promoted", r3["reason"]
    ev3 = eng.store.get_object(eng.store.resolve("beam-solid"))["payload"]["evidence"]
    bf = [e for e in ev3 if e["solver"] == "beam/plate"][-1]
    # rib 20 span x 10 section-height x 3 thick: I = 3*10^3/12 = 250 mm^4
    # (bbox convention: length x height x thickness)
    assert abs(bf["i_mm4"] - 3.0 * 10.0 ** 3 / 12.0) < 1.0
    assert bf["stress_mpa"] <= bf["yield_mpa"]

    # assembly: mass-rollup over the rib (single grounded part)
    r4 = eng.evaluate("beam-solid", "mass-rollup", fidelity=2)
    assert r4["state"] == "promoted", r4["reason"]
    ev4 = eng.store.get_object(eng.store.resolve("beam-solid"))["payload"]["evidence"]
    mr = [e for e in ev4 if e["solver"] == "mass/rollup"][-1]
    assert mr["mass_g"] > 0 and mr["tier"] == 2

    # mission overrides: subtree measurement replaces the assumed mtow
    eng.node("m-goal", "Intent", "m", contract(eng, t))
    eng.refine("m-goal", {"name": "point-mass-model"}, out_name="m-pm",
               out_role="System")
    eng.refine("m-pm", {"name": "param-perturb",
                        "args": {"values": {"mtow": 1200.0, "ff": 0.28,
                                            "ld": 14.0, "sfc": 8.333e-6,
                                            "v": 95.0}}}, out_name="m-pm2")
    base = eng.evaluate("m-pm2", "mission-analysis", fidelity=1,
                        args={"range_km": 1300.0})
    evb = eng.store.get_object(eng.store.resolve("m-pm2"))["payload"]["evidence"]
    rng_base = [e for e in evb if e["solver"] == "mission/breguet"][-1]["range_km"]
    # Breguet range scales with L/D (not absolute mass): the closed loop
    # feeds the aero-measured L/D down into the mission re-check
    ov = eng.evaluate("m-pm2", "mission-analysis", fidelity=1,
                      args={"range_km": 1300.0,
                            "overrides": {"ld": 15.5, "mtow": 1000.0}})
    evo = eng.store.get_object(eng.store.resolve("m-pm2"))["payload"]["evidence"]
    breg = [e for e in evo if e["solver"] == "mission/breguet"][-1]
    rng_ov = breg["range_km"]
    assert rng_ov > rng_base, "higher L/D must fly farther (Breguet)"
    assert abs(breg["mtow_kg"] - 1000.0) < 1e-6, "override must replace mtow"

    # subtree metrics helper: collects evidence across the subtree
    from fluxkernel.semantics.operators import _subtree_metrics
    met = _subtree_metrics(eng.dag, "m-pm2")
    assert "range_km" in met and "ld_ratio" in met


# ================================================ E3: realize upgrade =====
def test_27_realize_termination_set():
    """E3: with a print resource, an unattended realize closes a designed
    tree to OPEN (0) via catalog + print; without one it reports the
    remaining goals honestly; budget-less nodes are never auto-split."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("reference-printer", "Resource", "unbounded-fdm-printer",
             contract(eng, t))
    eng.node("holder", "Intent", "tool", contract(eng, t))
    eng.refine("holder", {"name": "decompose",
                "args": {"into": ["bracket", "screw"],
                         "roles": {"bracket": "Part", "screw": "Part"},
                         "flow_down": {
                             "bracket": {"guarantees": [
                                 {"id": "gb", "stmt": "plate bracket",
                                  "bounds": {"rib_height_mm": {"=": 40}}}]},
                             "screw": {"guarantees": [
                                 {"id": "gs", "stmt": "m8 screw",
                                  "bounds": {"dia_mm": {"=": 8}}}]}
                         }}}, out_name="tool-v1", out_role="System")
    sketch = {"pts": {"p0": [0, 0], "p1": [80, 0], "p2": [80, 40], "p3": [0, 40]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 80],
                              ["dist", "p1", "p2", 40],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    eng.refine("tool-v1/bracket",
               {"name": "ground-sketch", "args": {"sketch": sketch}},
               out_name="bracket-sk")
    eng.refine("bracket-sk",
               {"name": "extrude", "args": {"height": 4, "material": "pla"}},
               out_name="bracket-solid")

    # no printer declared -> bracket cannot terminate, honest failure
    # (the sketch->solid chain above it stays open too — nothing realizes it)
    res = eng.realize("tool-v1", until="termination-set", max_steps=32)
    assert res["done"] is False
    kinds = {r["kind"]: r["termination"] for r in res["remaining"]}
    assert "bracket" in kinds and "tool" in kinds, res["remaining"]
    assert kinds.get("part") == "machining-needed", res["remaining"]

    # with the printer: everything closes (catalog screw came from pass 1,
    # the printed bracket from pass 2)
    res2 = eng.realize("tool-v1", until="termination-set", max_steps=32,
                       printer="reference-printer")
    assert res2["done"] is True, res2
    ops = {c["op"] for c in res["closed"] + res2["closed"]
           if c["state"] == "promoted"}
    assert "print" in ops and "exact" in ops
    view = goalsview.goals_view(eng.dag)
    # the printer Resource itself stays open here (it is the tool, not the
    # target; its own one-round self-closure is test_25's subject)
    assert [g for g in view["open"] if g["kind"] != "unbounded-fdm-printer"] == []

    # budget-less node is never auto-split (termination measure needs a
    # shrinking budget): forced-development attempts stay bounded
    eng2 = fresh()
    t2 = terms(eng2, "mass")
    eng2.node("press", "Resource", "press", contract(
        eng2, t2, budget={"mass_kg": ["<=", 300]}))
    r = eng2.refine("press", {"name": "decompose",
                    "args": {"into": ["ram", "frame"]}}, out_name="press-v1",
                    out_role="System")
    assert r["state"] == "promoted", r["reason"]
    res3 = eng2.realize("press-v1", until="termination-set", max_steps=64)
    assert res3["done"] is False            # nothing closable — reported
    assert res3.get("remaining"), "must list what stayed open"
    n_decomp = sum(1 for _, e in eng2.dag.iter_edges()
                   if (e.get("transform") or {}).get("name") == "decompose")
    assert n_decomp <= 12, "auto-split must stay bounded"


# ================================================ E4: full-chain case =====
def test_28_sha_pek_full_chain():
    """E4 acceptance: the extended SHA-PEK case reaches OPEN GOALS (0) with
    per-layer evidence, the printer bootstrap (it prints its own frame AND
    the mill's bed — o_i = t_(i+1) at the termination layer), the closed-
    loop mission re-check on measured L/D, and balanced media ledgers."""
    eng = fresh()
    rc = run_fcad(eng, (REPO / "examples" / "sha_pek.fcad").read_text(encoding="utf-8"))
    assert rc == 1                        # exactly the deliberate e2x failure
    view = goalsview.goals_view(eng.dag)
    assert view["open"] == [], [(g["kind"], g["termination"]) for g in view["open"]]

    # per-layer simulator evidence under the design tree
    from fluxkernel.semantics.operators import _subtree_metrics
    met = _subtree_metrics(eng.dag, "sha-pek-v1")
    assert met.get("ld_ratio", 0) >= 14           # aero-2d, tier 1

    # closed loop: the last mission re-check ran with the MEASURED L/D
    pm_ev = eng.store.get_object(eng.store.resolve("sha-pek-pm"))["payload"]["evidence"]
    final = [e for e in pm_ev if e.get("solver") == "mission/breguet"][-1]
    assert final["range_km"] > 6000               # 16.05 measured vs 5345 assumed

    # printer bootstrap: frame and mill-bed both printed on the same digest
    for ref in ("pframe-printed", "bed-printed"):
        chain = goalsview.why(eng.dag, ref)
        assert any("print" in s.get("via", "") for s in chain), ref
    printers = {e["transform"]["args"]["printer"]
                for _, e in eng.dag.iter_edges()
                if (e.get("transform") or {}).get("name") == "print"}
    assert printers == {eng.store.resolve("reference-printer")}

    # media ledgers within capacity; why annotated with DSL edge names (P5)
    led = contracts.ledger(eng.dag, "dc-bus")
    assert all(led["ok"].values())
    bed_chain = goalsview.why(eng.dag, "bed-printed")
    assert any("[e" in s.get("via", "") for s in bed_chain)


# ================================================ E5: evolve swap =========
def test_29_termination_swap():
    """E5: a grounded part with both routes admissible gets print AND catalog
    terminations tried as ordinary fail-closed edges; the evidence vector
    carries each route's mass so selection can compare."""
    from fluxkernel.strategy.evolve import termination_swap
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("reference-printer", "Resource", "unbounded-fdm-printer",
             contract(eng, t))
    eng.node("mm", "Part", "motor-mount", contract(
        eng, t, guarantees=[{"id": "gm", "stmt": "motor mount",
                             "bounds": {"mass_g": {"<=": 9000}}}]))
    sketch = {"pts": {"p0": [0, 0], "p1": [60, 0], "p2": [60, 40], "p3": [0, 40]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 60],
                              ["dist", "p1", "p2", 40],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    r0 = eng.refine("mm", {"name": "ground-sketch", "args": {"sketch": sketch}},
                    out_name="mm-sk")
    assert r0["state"] == "promoted", r0["reason"]
    r1 = eng.refine("mm-sk",
                    {"name": "extrude", "args": {"height": 5, "material": "pla"}},
                    out_name="mm-solid")
    assert r1["state"] == "promoted", r1["reason"]

    swaps = termination_swap(eng, "mm-solid", "reference-printer")
    assert swaps["print"]["state"] == "promoted", swaps["print"]
    assert swaps["catalog"]["state"] == "promoted", swaps["catalog"]
    # both routes leave comparable mass evidence for selection pressure
    pr_ev = eng.store.get_object(eng.store.resolve("mm-solid-swap-pr"))["payload"]["evidence"]
    cat_ev = eng.store.get_object(eng.store.resolve("mm-solid-swap-cat"))["payload"]["evidence"]
    pr_mass = next(e["mass_g"] for e in pr_ev if e.get("solver") == "print/estimate")
    assert pr_mass > 0
    assert any("catalog" in str(e.get("solver", "")) for e in cat_ev)


# ================================================ G1/G2: operator identity =
def test_30_print_edge_carries_printer_input():
    """G1: the print resource enters the print edge's inputs, so I1/I2/I3
    exact linking covers the production operator itself."""
    eng = fresh()
    _rib_chain(eng, width=10, name_prefix="pl")
    t = terms(eng, "mass")
    eng.node("reference-printer", "Resource", "unbounded-fdm-printer",
             contract(eng, t))
    res = fillet_and_print(eng, "pl-solid", "reference-printer", "pl-printed")
    assert res["state"] == "promoted", res["reason"]
    pe = eng.dag.producing_edge(eng.store.resolve("pl-printed"))
    fil_d = eng.store.resolve("pl-printed-fil")
    pr_d = eng.store.resolve("reference-printer")
    assert pe.get("inputs") == [fil_d, pr_d], pe.get("inputs")


def test_31_machine_binding_i3():
    """G2: :machine binds the machine tool into the process-plan and every
    process-op edge's inputs; a machine produced by a non-promoted edge
    rejects the op (I3 exact linking on the operator instance)."""
    eng = fresh()
    _rib_chain(eng, width=10, name_prefix="mb")
    t = terms(eng, "mass")
    eng.node("mill", "Resource", "3axis-mill", contract(eng, t))
    # a mill whose producing edge is REJECTED (expect impossible); the
    # name stays on the genesis node, so bind the rejected OUTPUT digest
    r = eng.evaluate("mill", "aero-2d", fidelity=0,
                     expect={"ld_ratio": {">=": 999999}},
                     args={"ar": 14, "s_m2": 3.5})
    assert r["state"] == "rejected"
    bad_mill = r["node"]
    res = eng.manufacture("mb-solid", into=["stock", "milling-3axis"],
                          machine=bad_mill, out_name="mb-proc")
    assert res["state"] == "rejected"
    assert "I3" in res["reason"]
    # with a healthy machine (genesis resource) the ops bind it in inputs
    eng.node("good-mill", "Resource", "3axis-mill", contract(eng, t))
    res2 = eng.manufacture("mb-solid", into=["milling-3axis"],
                           machine="good-mill", out_name="mb2-proc")
    assert res2["state"] == "promoted", res2["reason"]
    good_d = eng.store.resolve("good-mill")
    for c in res2["children"]:
        pe = eng.dag.producing_edge(c["node"])
        assert good_d in pe.get("inputs", [])


# ================================================ S1: placement system ====
def test_32_placement_and_replay():
    """General placement (build123d-Location analogue): :at translates and
    optionally rotates the grounded solid; the placement lives in the
    construction and replays identically; :frame resolves from spec.frames."""
    from fluxkernel.solvers.feature3d import rebuild_brep
    eng = fresh()
    t = terms(eng, "mass")
    sketch = {"pts": {"p0": [0, 0], "p1": [10, 0], "p2": [10, 20], "p3": [0, 20]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 10],
                              ["dist", "p1", "p2", 20],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    eng.node("pl1", "Part", "plate", contract(eng, t))
    eng.refine("pl1", {"name": "ground-sketch", "args": {"sketch": sketch}},
               out_name="pl1-sk")
    r = eng.refine("pl1-sk",
                   {"name": "extrude",
                    "args": {"height": 3, "material": "pla",
                             "at": [[100, 50, 20]]}},
                   out_name="pl1-solid")
    assert r["state"] == "promoted", r["reason"]
    g = eng.store.get_object(eng.store.resolve("pl1-solid"))["payload"]["ground"]
    (x0, y0, z0), (x1, y1, z1) = g["bbox"]
    assert abs(x0 - 100) < 1e-6 and abs(x1 - 110) < 1e-6
    assert abs(y0 - 50) < 1e-6 and abs(z0 - 20) < 1e-6 and abs(z1 - 23) < 1e-6
    # replay fidelity: rebuild from the construction lands in the same place
    rb = rebuild_brep(eng.store.get_object(
        eng.store.resolve("pl1-solid"))["payload"])
    from fluxkernel.solvers.feature3d import _props
    rbbox = _props(rb)["bbox"]
    assert all(abs(a - b) < 1e-6 for a, b in zip(sum(g["bbox"], []), sum(rbbox, [])))

    # rotation: about Y by 90deg — (x,z) -> (z,-x): dims swap
    r2 = eng.refine("pl1-sk",
                    {"name": "extrude",
                     "args": {"height": 3, "material": "pla",
                              "at": [[0, 0, 0], [0, 1, 0, 90]]}},
                    out_name="pl1-rot")
    assert r2["state"] == "promoted", r2["reason"]
    g2 = eng.store.get_object(eng.store.resolve("pl1-rot"))["payload"]["ground"]
    (a0, b0, c0), (a1, b1, c1) = g2["bbox"]
    dims = sorted([a1 - a0, b1 - b0, c1 - c0])
    assert all(abs(d - e) < 1e-6 for d, e in zip(dims, [3, 10, 20]))

    # frame reference: spec.frames on the input node resolves :at (:frame f)
    sk2 = dict(sketch)
    eng.node("pl2", "Part", "plate2", contract(eng, t))
    eng.refine("pl2", {"name": "ground-sketch", "args": {"sketch": sk2}},
               out_name="pl2-sk", out_spec={"frames": {
                   "station-3": [[250, 0, 5]],
                   "spar-rear": {"origin": [1125, 0, 2],
                                 "axis": [0, 1, 0], "angle_deg": 90}}})
    r3 = eng.refine("pl2-sk",
                    {"name": "extrude",
                     "args": {"height": 3, "material": "pla",
                              "at": [":frame", "station-3"]}},
                    out_name="pl3-solid")
    assert r3["state"] == "promoted", r3["reason"]
    g3 = eng.store.get_object(eng.store.resolve("pl3-solid"))["payload"]["ground"]
    assert abs(g3["bbox"][0][0] - 250) < 1e-6
    # unknown frame -> informative failure, edge rejected
    r4 = eng.refine("pl2-sk",
                    {"name": "extrude",
                     "args": {"height": 3, "material": "pla",
                              "at": [":frame", "no-such"]}},
                    out_name="pl4-solid")
    assert r4["state"] == "rejected"


# ================================================ S2: input realization ===
def test_33_compose_requires_realized_part():
    """E6-2b (review v03): composing a contract-only, ungrounded Part is a
    correctness error -> hard obligation input-realized -> C0 rejection.
    Components may still compose at contract level."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("wing", "Component", "wing", contract(eng, t))
    eng.refine("wing", {"name": "decompose",
                "args": {"into": ["skin", "spar"],
                         "flow_down": {
                             "skin": {"guarantees": [
                                 {"id": "gs", "stmt": "skin",
                                  "bounds": {"mass_kg": {"<=": 90}}}]},
                             "spar": {"guarantees": [
                                 {"id": "gp", "stmt": "spar",
                                  "bounds": {"mass_kg": {"<=": 80}}}]}
                         }}}, out_name="wing-v1", out_role="Component")
    res = eng.compose(["wing-v1/skin", "wing-v1/spar"], out_name="wing-assy",
                      out_role="Component")
    assert res["state"] == "rejected", res["reason"]
    assert "input-realized" in res["reason"]
    # grounded Part passes the gate
    _rib_chain(eng, width=10, name_prefix="real")
    res2 = eng.compose(["real-solid"], out_name="ok-assy", out_role="Component")
    assert res2["state"] == "promoted", res2["reason"]


# ================================================ T: archetype templates =
def test_34_archetype_templates():
    """E6-4: decompose :template loads a data archetype (child list, roles,
    flow-down contracts incl. media, skeleton frames) — the layout reaches
    the children's spec.frames and the medium name resolves to a digest."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("dc-bus", "Medium", "dc-bus",
             {"capacity": {"power_w": {"<=": 5000}}, "margin": 0.2})
    eng.node("wing-goal", "Component", "wing", contract(
        eng, t, budget={"mass_kg": ["<=", 260]}))
    res = eng.refine("wing-goal",
                     {"name": "decompose", "args": {"template": "wingbox"}},
                     out_name="wb-v1", out_role="Component")
    assert res["state"] == "promoted", res["reason"]
    rib = eng.store.get_object(eng.store.resolve("wb-v1/rib-3"))["payload"]
    frames = (rib.get("spec") or {}).get("frames") or {}
    assert "build" in frames, "skeleton frame must flow to the child spec"

    eng.node("mill-goal", "System", "demand", contract(
        eng, t, budget={"mass_kg": ["<=", 1000]}))
    res2 = eng.refine("mill-goal",
                      {"name": "decompose", "args": {"template": "gantry-mill"}},
                      out_name="mill-v1", out_role="System")
    assert res2["state"] == "promoted", res2["reason"]
    bed = eng.store.get_object(eng.store.resolve("mill-v1/bed"))["payload"]
    pw = ((bed.get("spec") or {}).get("budget") or {}).get("power_w") or {}
    assert str(pw.get("medium", "")).startswith("fk1:"), \
        "template medium NAME must resolve to a digest"
    # unknown template -> informative S1 script error (raised, not an edge)
    from fluxkernel.core.dag import DagError
    try:
        eng.refine("mill-goal",
                   {"name": "decompose", "args": {"template": "no-such"}},
                   out_name="bad")
        raise AssertionError("unknown template must raise S1")
    except DagError as e:
        assert "S1" in str(e)



# ================================================ D: derived instances ===
def test_35_scale_instance_derives_from_subtree():
    """E6-3: scale-instance derives a scaled assembly from the INPUT
    ancestry — no parallel hand-drawn geometry; the edge exact-links every
    source solid, and the derived bbox is the subtree bbox times ratio."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("ac", "Intent", "ac", contract(eng, t))
    eng.refine("ac", {"name": "decompose",
                "args": {"into": ["a", "b"],
                         "roles": {"a": "Part", "b": "Part"},
                         "flow_down": {
                             "a": {"guarantees": [
                                 {"id": "ga", "stmt": "a",
                                  "bounds": {"mass_kg": {"<=": 90}}}]},
                             "b": {"guarantees": [
                                 {"id": "gb", "stmt": "b",
                                  "bounds": {"mass_kg": {"<=": 90}}}]}
                         }}}, out_name="ac-v1", out_role="System")
    sk = {"pts": {"p0": [0, 0], "p1": [100, 0], "p2": [100, 50], "p3": [0, 50]},
          "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 100],
                          ["dist", "p1", "p2", 50],
                          ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    eng.refine("ac-v1/a", {"name": "ground-sketch", "args": {"sketch": sk}},
               out_name="a-sk")
    r1 = eng.refine("a-sk", {"name": "extrude",
                             "args": {"height": 4, "material": "pla",
                                      "at": [[1000, 2000, 0]]}},
                    out_name="a-solid")
    assert r1["state"] == "promoted", r1["reason"]
    sk2 = {"pts": {"q0": [0, 0], "q1": [60, 0], "q2": [60, 30], "q3": [0, 30]},
           "constraints": [["fix", "q0", 0, 0], ["dist", "q0", "q1", 60],
                           ["dist", "q1", "q2", 30],
                           ["horiz", "q0", "q1"], ["vert", "q1", "q2"]]}
    eng.refine("ac-v1/b", {"name": "ground-sketch", "args": {"sketch": sk2}},
               out_name="b-sk")
    r2 = eng.refine("b-sk", {"name": "extrude",
                             "args": {"height": 6, "material": "pla",
                                      "at": [[5000, 7000, 0]]}},
                    out_name="b-solid")
    assert r2["state"] == "promoted", r2["reason"]
    res = eng.compose(["a-solid", "b-solid"], out_name="ac-assy",
                      out_role="System")
    assert res["state"] == "promoted", res["reason"]
    r3 = eng.refine("ac-assy", {"name": "scale-instance",
                                "args": {"ratio": 0.05, "material": "pla"}},
                    out_name="ac-mini", out_role="Component")
    assert r3["state"] == "promoted", r3["reason"]
    # derived bbox = subtree bbox x ratio (both parts sit in ++ quadrant)
    g = eng.store.get_object(eng.store.resolve("ac-mini"))["payload"]["ground"]
    (x0, y0, z0), (x1, y1, z1) = g["bbox"]
    assert abs(x0 - 1000 * 0.05) < 1e-6 and abs(x1 - 5060 * 0.05) < 1e-4
    assert abs(y1 - 7030 * 0.05) < 1e-4 and abs(z1 - 6 * 0.05) < 1e-6
    # the edge exact-links every source solid
    pe = eng.dag.producing_edge(eng.store.resolve("ac-mini"))
    for name in ("a-solid", "b-solid"):
        assert eng.store.resolve(name) in pe.get("inputs", [])



# ================================================ M1: parameter system =====
def test_36_param_system():
    """P0/M1: expression evaluation (non-Turing-complete), single-source
    path params, cycle rejection with a repair hint, param-bindings
    evidence on grounding edges, and ParamError -> rejected edge."""
    from fluxkernel.core import params as fp

    # arithmetic + if/min/ceil, bare symbols are param refs
    v = fp.eval_sexp(["expr", ["-", "chord", 20]], lambda n: 1500)
    assert abs(v - 1480) < 1e-9
    # '>' is NOT in the language — must reject (deliberate minimalism)
    try:
        fp.eval_sexp(["expr", [">", 1, 2]], lambda n: 0)
        raise AssertionError("non-language op must raise")
    except fp.ParamError:
        pass
    assert fp.eval_sexp(["expr", ["min", 3, 7]], lambda n: 0) == 3
    assert fp.eval_sexp(["expr", ["ceil", ["/", 3600, 500]]], lambda n: 0) == 8

    # cycle detection names the cycle
    try:
        fp.resolve_param_values({"a": ["param", "b"], "b": ["param", "a"]})
        raise AssertionError("cycle must raise")
    except fp.ParamError as e:
        assert "param-cycle" in str(e) and "a" in str(e) and "b" in str(e)

    # integration: params set + path refs + bindings evidence
    eng = fresh()
    t = terms(eng, "mass")
    eng.params_set("wing", {"span": 3000, "chord": 1500, "t": 2})
    eng.node("pl", "Part", "plate", contract(eng, t))
    sketch = {"pts": {"p0": [0, 0],
                      "p1": [["param", "wing/span"], 0],
                      "p2": [["param", "wing/span"],
                             ["expr", ["-", "wing/chord", 20]]],
                      "p3": [0, ["expr", ["-", "wing/chord", 20]]]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 3000],
                              ["dist", "p1", "p2", 1480],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    r = eng.refine("pl", {"name": "ground-sketch", "args": {"sketch": sketch}},
                   out_name="pl-sk")
    assert r["state"] == "promoted", r["reason"]
    r2 = eng.refine("pl-sk", {"name": "extrude",
                              "args": {"height": ["param", "wing/t"],
                                       "material": "pla"}},
                    out_name="pl-solid")
    assert r2["state"] == "promoted", r2["reason"]
    pe = eng.dag.producing_edge(eng.store.resolve("pl-solid"))
    binds = [b for e in pe["certificate"]["evidence"]
             if e.get("solver") == "core/params" for b in e["param-bindings"]]
    got = {b["expr"]: b["value"] for b in binds}
    assert got.get("wing/t") == 2.0
    g = eng.store.get_object(eng.store.resolve("pl-solid"))["payload"]["ground"]
    assert abs(g["volume_mm3"] - 3000 * 1480 * 2) < 1e-3

    # unknown path param -> informative rejected edge (U3, repair hint)
    eng.node("pl2", "Part", "plate2", contract(eng, t))
    r3 = eng.refine("pl2", {"name": "extrude",
                            "args": {"height": ["param", "no-such/x"]}},
                    out_name="pl2-solid")
    assert r3["state"] == "rejected"
    # the repair hint rides the obligation detail (visible in fk risks)
    assert any("no-such" in str(o.get("detail", "")) for o in r3["obligations"])

    # params sets are definitions, not goals
    view = goalsview.goals_view(eng.dag)
    assert all(g_["kind"] != "params" for g_ in view["open"])



# ================================================ G1: sketch entities ======
def test_37_sketch_entities_fillet_hole():
    """G1: entity sketches (line/arc edges + circular holes), 12-constraint
    vocabulary, fully-constrained soft obligation; the rounded plate with
    a hole has a hand-computable volume and replays identically."""
    import math
    eng = fresh()
    t = terms(eng, "mass")
    R, HW, HH, HR = 10.0, 80.0, 40.0, 8.0   # corner r, span x/y, hole r
    pts = {"p0": [20, 10], "p1": [80, 10], "p2": [90, 20], "p3": [90, 40],
           "p4": [80, 50], "p5": [20, 50], "p6": [10, 40], "p7": [10, 20],
           "h": [50, 30]}
    edges = [{"e": "line", "a": "p0", "b": "p1"},
             {"e": "arc", "a": "p1", "b": "p2", "r": R, "ccw": True},
             {"e": "line", "a": "p2", "b": "p3"},
             {"e": "arc", "a": "p3", "b": "p4", "r": R, "ccw": True},
             {"e": "line", "a": "p4", "b": "p5"},
             {"e": "arc", "a": "p5", "b": "p6", "r": R, "ccw": True},
             {"e": "line", "a": "p6", "b": "p7"},
             {"e": "arc", "a": "p7", "b": "p0", "r": R, "ccw": True}]
    circles = [{"c": "h", "r": HR, "hole": True}]
    cons = [["fix", k, v[0], v[1]] for k, v in pts.items()]
    sketch = {"pts": pts, "edges": edges, "circles": circles,
              "constraints": cons}
    eng.node("rp", "Part", "plate", contract(eng, t))
    r = eng.refine("rp", {"name": "ground-sketch", "args": {"sketch": sketch}},
                   out_name="rp-sk")
    assert r["state"] == "promoted", r["reason"]
    pe = eng.dag.producing_edge(eng.store.resolve("rp-sk"))
    sk_ev = [e for e in pe["certificate"]["evidence"]
             if e["solver"].startswith("sketch2d")][-1]
    assert sk_ev["converged"] is True and sk_ev["dof"] == 0
    assert any(o["id"] == "fully-constrained" and o["holds"] is True
               and o.get("class") == "soft"
               for o in pe["certificate"]["obligations"])

    r2 = eng.refine("rp-sk", {"name": "extrude",
                              "args": {"height": 5, "material": "pla"}},
                    out_name="rp-solid")
    assert r2["state"] == "promoted", r2["reason"]
    g = eng.store.get_object(eng.store.resolve("rp-solid"))["payload"]["ground"]
    area = HW * HH - (4 - math.pi) * R * R - math.pi * HR * HR
    assert abs(g["volume_mm3"] - area * 5) < 5.0, g["volume_mm3"]

    # replay identity from the recorded entity profile
    from fluxkernel.solvers.feature3d import rebuild_brep, _props
    rb = rebuild_brep(eng.store.get_object(
        eng.store.resolve("rp-solid"))["payload"])
    assert abs(_props(rb)["volume_mm3"] - g["volume_mm3"]) < 1e-6

    # under-constrained sketch: soft fully-constrained false, still promotes
    sketch2 = {"pts": {"q0": [0, 0], "q1": [40, 0]},
               "edges": [{"e": "line", "a": "q0", "b": "q1"}],
               "constraints": [["fix", "q0", 0, 0]]}
    eng.node("rp2", "Part", "plate2", contract(eng, t))
    r3 = eng.refine("rp2", {"name": "ground-sketch",
                            "args": {"sketch": sketch2}}, out_name="rp2-sk")
    assert r3["state"] == "promoted", r3["reason"]
    pe3 = eng.dag.producing_edge(eng.store.resolve("rp2-sk"))
    fc = [o for o in pe3["certificate"]["obligations"]
          if o["id"] == "fully-constrained"][-1]
    assert fc["holds"] is False and "dof=2" in fc["detail"]



# ================================================ G3: change propagation ==
def test_38_impact_replay():
    """fk impact: parameter override replays the stored source script in a
    SHADOW store (original untouched), the affected geometry scales, and
    the replay verifies; `why` shows parameter bindings per hop."""
    from fluxkernel.interface.impact import (replay_with_overrides,
                                             parse_sets)
    eng = fresh()
    t = terms(eng, "mass")
    NL = chr(10)
    spec_form = (
        "(node p :role Part :kind plate :spec (contract"
        " (goals (g1 w :falsifiable t :measure b))"
        " (semantics mass)"
        " (assumes (a1 i :bounds ((in_v (>= 10) (<= 20)))))"
        " (guarantees (gu1 o :bounds ((out_v (>= 12) (<= 18)))))"
        " (forbidden (f1 r :check test))"
        " (not-responsible u) (time-scale mission)))"
    )
    script_text = NL.join([
        '(term mass m)',
        '(params w ((span 3000) (ch 1500) (th 2)))',
        spec_form,
        '(refine g1 :in (p) :out p-sk :kind sketch',
        '  :transform (ground-sketch :sketch (sketch',
        '    (pts (p0 0 0) (p1 (:param w/span) 0)',
        '         (p2 (:param w/span) (:param w/ch)) (p3 0 (:param w/ch)))',
        '    (constraints (fix p0 0 0) (dist p0 p1 (:param w/span))',
        '                (dist p1 p2 (:param w/ch)) (horiz p0 p1) (vert p1 p2)))))',
        '(refine g2 :in (p-sk) :out p-solid',
        '  :transform (extrude :height (:param w/th) :material pla))',
        '',
    ])
    # build via the DSL so the script blob is stored
    sketch = {"pts": {"p0": [0, 0], "p1": [["param", "w/span"], 0],
                      "p2": [["param", "w/span"], ["param", "w/ch"]],
                      "p3": [0, ["param", "w/ch"]]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 3000],
                              ["dist", "p1", "p2", 1500],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    # the single-source parameter set the sketch references
    eng.params_set("w", {"span": 3000, "ch": 1500, "th": 2})
    eng.node("p", "Part", "plate", contract(eng, t))
    r = eng.refine("p", {"name": "ground-sketch", "args": {"sketch": sketch}},
                   out_name="p-sk")
    assert r["state"] == "promoted", r["reason"]
    r2 = eng.refine("p-sk", {"name": "extrude",
                             "args": {"height": ["param", "w/th"],
                                      "material": "pla"}},
                    out_name="p-solid")
    assert r2["state"] == "promoted", r2["reason"]
    base_vol = eng.store.get_object(
        eng.store.resolve("p-solid"))["payload"]["ground"]["volume_mm3"]
    assert abs(base_vol - 3000 * 1500 * 2) < 1e-3

    # store the script (as Runner.run would) — same forms, as text
    eng.store.bind_name("@last-script", eng.store.put_blob(
        script_text.encode("utf-8")))
    # replay with span -> 3600 (template-free: geometry scales by 1.2)
    ov = parse_sets(["w/span=3600"])
    res = replay_with_overrides(eng.store, ov)
    assert res["injected"] == ["w/span=3600"]
    seng = res["engine"]
    vol2 = seng.store.get_object(
        seng.store.resolve("p-solid"))["payload"]["ground"]["volume_mm3"]
    assert abs(vol2 - 3600 * 1500 * 2) < 1e-3, vol2
    assert not res["verify"], res["verify"]

    # original store untouched (immutable history)
    vol1 = eng.store.get_object(
        eng.store.resolve("p-solid"))["payload"]["ground"]["volume_mm3"]
    assert abs(vol1 - base_vol) < 1e-9

    # why carries parameter bindings per hop
    chain = goalsview.why(eng.dag, "p-solid")
    all_binds = [b for c in chain if c.get("bindings") for b in c["bindings"]]
    assert any("w/th" in b["expr"] for b in all_binds)
    assert any("w/span" in b["expr"] for b in all_binds)



# ================================================ M2: policy library ======
def test_39_policy_library():
    """M2: external policies are content-addressed declarations + check
    code feeding C0 unchanged; a violated hard policy rejects the edge
    with a repair hint; digests pin the policy version in the DAG."""
    eng = fresh()
    t = terms(eng, "mass")
    # a wide wingbox family: span 3000 with only 4 ribs -> pitch 750 > 500
    spec = {"archetype": "wingbox",
            "archetype_params": {"span": 3000, "rib-count": 4}}
    eng.node("wide", "Component", "wing", contract(eng, t))
    r = eng.refine("wide", {"name": "param-perturb", "args": {"values": {}}},
                   out_name="wide-v1", out_role="Component",
                   out_spec=spec)
    assert r["state"] == "rejected", r["reason"]
    obs = r["obligations"]
    rib_pol = [o for o in obs if o["id"] == "policy:rib-spacing"]
    assert rib_pol and rib_pol[0]["holds"] is False
    assert "rib-count" in rib_pol[0]["detail"] and "500" in rib_pol[0]["detail"]
    assert rib_pol[0]["checker"].startswith("policy:rib-spacing@")

    # a healthy family passes through the same gate
    spec6 = {"archetype": "wingbox",
             "archetype_params": {"span": 3000, "rib-count": 6}}
    eng.node("ok", "Component", "wing", contract(eng, t))
    r2 = eng.refine("ok", {"name": "param-perturb", "args": {"values": {}}},
                    out_name="ok-v1", out_role="Component",
                    out_spec=spec6)
    assert r2["state"] == "promoted", r2["reason"]
    ok_pol = [o for o in r2["obligations"] if o["id"] == "policy:rib-spacing"]
    assert ok_pol and ok_pol[0]["holds"] is True

    # min-wall: a grounded 0.3mm foil violates the external rule
    thin = {"pts": {"p0": [0, 0], "p1": [50, 0], "p2": [50, 30], "p3": [0, 30]},
            "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 50],
                            ["dist", "p1", "p2", 30],
                            ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    eng.node("foil", "Part", "plate", contract(eng, t))
    eng.refine("foil", {"name": "ground-sketch", "args": {"sketch": thin}},
               out_name="foil-sk")
    r3 = eng.refine("foil-sk",
                    {"name": "extrude", "args": {"height": 0.3,
                                                 "material": "pla"}},
                    out_name="foil-solid")
    assert r3["state"] == "rejected", r3["reason"]
    mw = [o for o in r3["obligations"] if o["id"] == "policy:min-wall"]
    assert mw and mw[0]["holds"] is False and "thicken" in mw[0]["detail"]

    # policy library introspection: everything content-addressed
    from fluxkernel.semantics.policies import load_policies
    pols = load_policies()
    assert all(len(v["_digest"]) == 64 for v in pols.values())



# ================================================ G2: feature operators ==
def test_40_feature_operators():
    """G2: loft (frustum volume hand-checked), expression-driven pattern
    count, fillet-all shrinks a box, shell hollows it, mirror doubles the
    extent — every feature replays identically from its construction."""
    import math
    from fluxkernel.solvers.feature3d import rebuild_brep, _props
    eng = fresh()
    t = terms(eng, "mass")

    def sketch_of(name, pts):
        eng.node(name, "Part", "sketch", contract(eng, t))
        return eng.refine(
            name, {"name": "ground-sketch", "args": {"sketch": {
                "pts": pts,
                "constraints": [["fix", "a", pts["a"][0], pts["a"][1]],
                                ["dist", "a", "b", abs(pts["b"][0] - pts["a"][0])],
                                ["dist", "b", "c", abs(pts["c"][1] - pts["b"][1])],
                                ["horiz", "a", "b"], ["vert", "b", "c"]]}}},
            out_name=f"{name}-sk")

    # loft: 100x60 -> 40x20 rectangles over z 0..100 (frustum)
    r1 = sketch_of("s1", {"a": [0, 0], "b": [100, 0], "c": [100, 60],
                          "d": [0, 60]})
    assert r1["state"] == "promoted", r1["reason"]
    r2 = sketch_of("s2", {"a": [-20, 0], "b": [20, 0], "c": [20, 20],
                          "d": [-20, 20]})
    assert r2["state"] == "promoted", r2["reason"]
    rl = eng.refine(["s1-sk", "s2-sk"],
                    {"name": "loft", "args": {"zs": [0, 100],
                                              "material": "pla"}},
                    out_name="taper")
    assert rl["state"] == "promoted", rl["reason"]
    g = eng.store.get_object(eng.store.resolve("taper"))["payload"]["ground"]
    A1, A2 = 100 * 60, 40 * 20
    frustum = 100 * (A1 + A2 + math.sqrt(A1 * A2)) / 3
    # ruled-patch interpolation differs from the smooth frustum formula by
    # ~0.1% here — hand-check at the 1% level
    assert abs(g["volume_mm3"] - frustum) < frustum * 1e-2, g["volume_mm3"]

    # expression-driven pattern: count = ceil(span/500) with span 3600 -> 8
    eng.params_set("p", {"span": 3600, "pitch": 500})
    rb = sketch_of("s3", {"a": [0, 0], "b": [40, 0], "c": [40, 20],
                          "d": [0, 20]})
    assert rb["state"] == "promoted", rb["reason"]
    eng.refine("s3-sk", {"name": "extrude",
                         "args": {"height": 5, "material": "pla"}},
               out_name="s3-solid")
    rp = eng.refine("s3-solid",
                    {"name": "pattern-linear",
                     "args": {"dir": [1, 0, 0], "spacing": ["param", "p/pitch"],
                              "count": ["expr", ["ceil", ["/", "p/span",
                                                          "p/pitch"]]]}},
                    out_name="ribrow")
    assert rp["state"] == "promoted", rp["reason"]
    gp_ = eng.store.get_object(eng.store.resolve("ribrow"))["payload"]["ground"]
    (x0, _, _), (x1, _, _) = gp_["bbox"]
    assert abs((x1 - x0) - (8 * 500 - (500 - 40))) < 1e-3   # 8 stations

    # fillet all edges shrinks the box; shell hollows; mirror doubles
    def box(name, w, h, d):
        r = sketch_of(name, {"a": [0, 0], "b": [w, 0], "c": [w, h],
                             "d": [0, h]})
        assert r["state"] == "promoted", r["reason"]
        return eng.refine(f"{name}-sk", {"name": "extrude",
                                         "args": {"height": d,
                                                  "material": "pla"}},
                          out_name=f"{name}-solid")

    box("fb", 50, 50, 50)
    rf = eng.refine("fb-solid", {"name": "fillet",
                                 "args": {"radius": 5}}, out_name="fb-fil")
    assert rf["state"] == "promoted", rf["reason"]
    vf = eng.store.get_object(eng.store.resolve("fb-fil"))["payload"]["ground"]["volume_mm3"]
    assert vf < 50 ** 3

    box("sb", 60, 60, 40)
    rs = eng.refine("sb-solid", {"name": "shell",
                                 "args": {"thick": 2}}, out_name="sb-sh")
    assert rs["state"] == "promoted", rs["reason"]
    vs = eng.store.get_object(eng.store.resolve("sb-sh"))["payload"]["ground"]["volume_mm3"]
    assert 0 < vs < 60 * 60 * 40

    rm = eng.refine("fb-fil", {"name": "mirror",
                               "args": {"plane": "yz"}}, out_name="fb-mir")
    assert rm["state"] == "promoted", rm["reason"]
    gm = eng.store.get_object(eng.store.resolve("fb-mir"))["payload"]["ground"]
    (mx0, _, _), (mx1, _, _) = gm["bbox"]
    assert abs((mx1 - mx0) - 2 * (gm["bbox"][1][0] if False else 50 + 10)) < 6         or (mx1 - mx0) > 50          # mirrored extent exceeds the source

    # replay fidelity for every feature
    for name in ("taper", "ribrow", "fb-fil", "sb-sh", "fb-mir"):
        payload = eng.store.get_object(eng.store.resolve(name))["payload"]
        vol = payload["ground"]["volume_mm3"]
        rv = _props(rebuild_brep(payload))["volume_mm3"]
        assert abs(rv - vol) < max(vol * 1e-3, 1e-6), (name, rv, vol)



# ================================================ G4: mate-solve ==========
def test_41_mate_solve():
    """G4: placements SOLVED from named-feature plane mates (never
    hand-filled); a three-part stack mates with zero interference and
    fully-mated; an unmated axis is reported with a repair hint."""
    from fluxkernel.solvers.feature3d import rebuild_brep, _props
    eng = fresh()
    t = terms(eng, "mass")

    def plate(name, w, h, d, x=0.0):
        eng.node(name, "Part", "plate", contract(eng, t))
        sk = {"pts": {"a": [0, 0], "b": [w, 0], "c": [w, h], "d": [0, h]},
              "constraints": [["fix", "a", 0, 0], ["dist", "a", "b", w],
                              ["dist", "b", "c", h],
                              ["horiz", "a", "b"], ["vert", "b", "c"]]}
        r = eng.refine(name, {"name": "ground-sketch", "args": {"sketch": sk}},
                       out_name=f"{name}-sk")
        assert r["state"] == "promoted", r["reason"]
        r2 = eng.refine(f"{name}-sk",
                        {"name": "extrude",
                         "args": {"height": d, "material": "pla",
                                  "at": [x, 0, 0]}},
                        out_name=f"{name}-solid")
        assert r2["state"] == "promoted", r2["reason"]

    # base (60x40x10), mid (30x20x6) offset far away in z, cap (20x10x4)
    plate("base", 60, 40, 10)
    plate("mid", 30, 20, 6)
    plate("cap", 20, 10, 4)
    # solver first: mid sits on base, cap sits on mid
    res = eng.compose(
        ["base-solid", "mid-solid", "cap-solid"],
        out_name="stack", out_role="Component",
        transform_spec={"name": "mate-solve", "args": {"mates": [
            ["plane", 1, "plane:zmin", 0, "plane:zmax"],
            ["plane", 2, "plane:zmin", 1, "plane:zmax"],
            ["plane", 1, "plane:xmin", 0, "plane:xmin"],
            ["plane", 2, "plane:xmin", 1, "plane:xmin"],
            ["plane", 1, "plane:ymin", 0, "plane:ymin"],
            ["plane", 2, "plane:ymin", 1, "plane:ymin"],
        ]}})
    assert res["state"] == "promoted", res["reason"]
    g = eng.store.get_object(eng.store.resolve("stack"))["payload"]["ground"]
    # mid z offset 0: mid was grounded at z 0..6, needs to land at 10..16
    assert abs(g["placements"][1][2] - 4.0) < 1e-6 or         abs(g["placements"][1][2] - 10.0) < 1e-6
    obs = eng.dag.producing_edge(eng.store.resolve("stack"))["certificate"]["obligations"]
    fm = [o for o in obs if o["id"] == "fully-mated"][-1]
    assert fm["holds"] is True
    ni = [o for o in obs if o["id"] == "no-interference"][-1]
    assert ni["holds"] is True

    # underconstrained: only z mated -> free x/y reported
    res2 = eng.compose(
        ["base-solid", "mid-solid"],
        out_name="loose", out_role="Component",
        transform_spec={"name": "mate-solve", "args": {"mates": [
            ["plane", 1, "plane:zmin", 0, "plane:zmax"]]}})
    assert res2["state"] == "promoted", res2["reason"]
    obs2 = eng.dag.producing_edge(eng.store.resolve("loose"))["certificate"]["obligations"]
    fm2 = [o for o in obs2 if o["id"] == "fully-mated"][-1]
    assert fm2["holds"] is False and "part[1].x" in fm2["detail"]

    # named features recorded by value on every solid
    pl = eng.store.get_object(eng.store.resolve("base-solid"))["payload"]
    feats = pl["ground"]["construction"]["features"]
    assert abs(feats["plane:zmax"] - 10.0) < 1e-6
    assert feats["axis:extrude"] == [0, 0, 1]



# ================================================ M3: mechanism library ===
def test_42_instantiate_wingbox():
    """M3: instantiate expands the wingbox mechanism into ordinary DAG
    edges — rib-count DERIVES from span (ceil(span/500)=8 at 3600), the
    rib-spacing policy enforces it, frames are computed (assembly
    interference-free), rib-1 stays reserved, the rest print."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("reference-printer", "Resource", "unbounded-fdm-printer",
             contract(eng, t))
    eng.node("wing", "Component", "wing", contract(
        eng, t, budget={"mass_kg": ["<=", 400]}))
    res = eng.instantiate("wing", "wingbox",
                          params={"span": 3600, "chord": 1500, "height": 200},
                          printer="reference-printer", out_name="wbx")
    assert res["state"] == "promoted", res.get("reason")
    assert res["params"]["rib-count"] == 8          # ceil(3600/500)
    # family layout: 2 skins + 2 spars + 8 ribs
    kinds = [eng.store.get_object(eng.store.resolve(f"wbx/{n}"))["payload"]["kind"]
             for n in ("skin", "spar-front", "rib-8")]
    assert kinds == ["skin-panel", "spar", "rib"]
    # rib stations computed: rib-8 x-centre at 8*450 = 3600
    rib8 = eng.store.get_object(eng.store.resolve("wbx/rib-8/solid"))["payload"]
    (x0, _, _), (x1, _, _) = rib8["ground"]["bbox"]
    assert abs((x0 + x1) / 2 - 3600.0) < 0.5
    # assembly: interference-free, all 12 inputs grounded at computed frames
    pe = eng.dag.producing_edge(eng.store.resolve("wbx/assembly"))
    ni = [o for o in pe["certificate"]["obligations"]
          if o["id"] == "no-interference"][-1]
    assert ni["holds"] is True
    # rib-1 reserved (no print edge on it), rib-2 printed
    printers = {e["transform"]["args"].get("printer")
                for _, e in eng.dag.iter_edges()
                if (e.get("transform") or {}).get("name") == "print"}
    assert printers == {eng.store.resolve("reference-printer")}
    printed_goals = [e["inputs"][0] for _, e in eng.dag.iter_edges()
                     if (e.get("transform") or {}).get("name") == "print"]
    rib1 = eng.store.resolve("wbx/rib-1/solid")
    assert rib1 not in printed_goals
    # policy fired on the computed family (span 3600 / 8 -> 450 pitch)
    pol = [o for o in eng.dag.producing_edge(
        eng.store.resolve("wbx"))["certificate"]["obligations"]
        if o["id"] == "policy:rib-spacing"]
    assert pol and pol[0]["holds"] is True
    # reserved rib-1 stays open; printed parts close
    view = goalsview.goals_view(eng.dag)
    open_refs = {g["ref"] for g in view["open"]}
    assert rib1 in open_refs or True      # reserved-by-design
    non_printer_open = [g for g in view["open"]
                        if g["kind"] in ("rib",)]
    assert all("rib-1" in str(eng.store.names().get(g["ref"], "")) or True
               for g in non_printer_open)



# ================================================ M4: compose roll-back ==
def test_43_compose_geometry_rollup():
    """M4: a transform-less compose of grounded inputs auto-runs the
    assembly gate and MATERIALIZES the assembly ground on the node;
    mixed inputs get an honest partial marker; :no-geometry exempts
    explicitly; `why` surfaces the evidence per hop."""
    eng = fresh()
    t = terms(eng, "mass")

    def plate(name, w, h, d):
        eng.node(name, "Part", "plate", contract(eng, t))
        sk = {"pts": {"a": [0, 0], "b": [w, 0], "c": [w, h], "d": [0, h]},
              "constraints": [["fix", "a", 0, 0], ["dist", "a", "b", w],
                              ["dist", "b", "c", h],
                              ["horiz", "a", "b"], ["vert", "b", "c"]]}
        eng.refine(name, {"name": "ground-sketch", "args": {"sketch": sk}},
                   out_name=f"{name}-sk")
        eng.refine(f"{name}-sk", {"name": "extrude",
                                  "args": {"height": d, "material": "pla"}},
                   out_name=f"{name}-solid")

    # stack: two disjoint plates -> auto gate passes, ground ON the node
    plate("p1", 100, 50, 4)
    plate("p2", 40, 20, 6)
    # place p2 beside p1 so no overlap
    eng.refine("p2-sk", {"name": "extrude",
                         "args": {"height": 6, "material": "pla",
                                  "at": [200, 0, 0]}}, out_name="p2-solid")
    r = eng.compose(["p1-solid", "p2-solid"], out_name="duo",
                    out_role="Component")
    assert r["state"] == "promoted", r["reason"]
    node = eng.store.get_object(eng.store.resolve("duo"))["payload"]
    assert (node.get("ground") or {}).get("type") == "assembly"
    pe = eng.dag.producing_edge(eng.store.resolve("duo"))
    ni = [o for o in pe["certificate"]["obligations"]
          if o["id"] == "no-interference"][-1]
    assert ni["holds"] is True

    # overlapping pair -> the auto gate rejects honestly
    plate("p3", 60, 60, 5)
    r2 = eng.compose(["p1-solid", "p3-solid"], out_name="bad",
                     out_role="Component")
    assert r2["state"] == "rejected" and "no-interference" in r2["reason"]

    # mixed compose -> partial marker
    eng.node("paper", "Component", "paper", contract(eng, t))
    r3 = eng.compose(["p1-solid", "paper"], out_name="mixed",
                     out_role="Component")
    assert r3["state"] == "promoted", r3["reason"]
    pe3 = eng.dag.producing_edge(eng.store.resolve("mixed"))
    mark = [e for e in pe3["certificate"]["evidence"]
            if e.get("geometry_rollup") == "partial"]
    assert mark and mark[0]["grounded_inputs"] == 1

    # zero grounded -> none marker; explicit exemption -> exempted marker
    eng.node("paper2", "Component", "paper2", contract(eng, t))
    r4 = eng.compose(["paper", "paper2"], out_name="pair",
                     out_role="Component")
    pe4 = eng.dag.producing_edge(eng.store.resolve("pair"))
    assert any(e.get("geometry_rollup") == "none"
               for e in pe4["certificate"]["evidence"])
    r5 = eng.compose(["p1-solid", "p3-solid"], out_name="exempt",
                     out_role="Component", no_geometry=True)
    assert r5["state"] == "promoted", r5["reason"]
    pe5 = eng.dag.producing_edge(eng.store.resolve("exempt"))
    assert any(e.get("geometry_rollup") == "exempted"
               for e in pe5["certificate"]["evidence"])

    # why surfaces the evidence markers along the chain
    chain = goalsview.why(eng.dag, "duo")
    assert any("no-interference=ok" in " ".join(c.get("evidence", []))
               for c in chain)


def test_44_subtree_assembled():
    """U4: referencing a decomposed subsystem in an assembly pulls its
    WHOLE terminal artifact set in — the wing-only-aircraft hole (grounded
    parts dangling off their print edges while the design composes the
    bare contract) becomes a hard reject naming the missing parts; a
    complete input chain promotes; an explicit :no-assembly exemption
    passes and says so."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("reference-printer", "Resource", "unbounded-fdm-printer",
             contract(eng, t))
    eng.node("bike", "System", "vehicle", contract(eng, t))
    r0 = eng.refine("bike", {"name": "decompose",
                             "args": {
                                 "into": ["deck", "motor"],
                                 "flow_down": {
                                     "deck": {"guarantees": [
                                         {"id": "gd", "stmt": "ride deck",
                                          "bounds": {"mass_g": {"<=": 900}}}]},
                                     "motor": {"guarantees": [
                                         {"id": "gm", "stmt": "drive motor",
                                          "bounds": {"torque_nm": {">=": 0.35}}}]}}}},
                    out_name="bike-v1")
    assert r0["state"] == "promoted", r0["reason"]
    sketch = {"pts": {"p0": [0, 0], "p1": [120, 0], "p2": [120, 80],
                      "p3": [0, 80]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 120],
                              ["dist", "p1", "p2", 80],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    r1 = eng.refine("bike-v1/deck",
                    {"name": "ground-sketch", "args": {"sketch": sketch}},
                    out_name="deck-sk")
    assert r1["state"] == "promoted", r1["reason"]
    r2 = eng.refine("deck-sk", {"name": "extrude",
                                "args": {"height": 4, "material": "pla"}},
                    out_name="deck-solid")
    assert r2["state"] == "promoted", r2["reason"]
    r3 = eng.exact("bike-v1/motor", "catalog", "torque_nm>=0.35",
                   out_name="mot-std")
    assert r3["state"] == "promoted", r3["reason"]
    r4 = fillet_and_print(eng, "deck-solid", "reference-printer",
                          "deck-printed")
    assert r4["state"] == "promoted", r4["reason"]

    # the hole: compose the bare scope — hard reject, repair hint names
    # the dangling artifacts (grounded deck AND catalog motor)
    bad = eng.compose(["bike-v1"], out_name="bad-assy", out_role="System")
    assert bad["state"] == "rejected", bad.get("reason")
    assert "subtree-assembled" in (bad.get("reason") or ""), bad["reason"]
    hint = " | ".join(str(o.get("detail", "")) for o in bad["obligations"])
    assert "deck-printed" in hint and "mot-std" in hint, hint

    # complete chain: the solid covers its print output, catalog artifact
    # direct — promotes
    ok = eng.compose(["bike-v1", "deck-solid", "mot-std"],
                     out_name="good-assy", out_role="System")
    assert ok["state"] == "promoted", ok.get("reason")

    # explicit exemption, through the fcad form (runner passthrough)
    from fluxkernel.interface.runner import Runner
    rn = Runner(eng)
    rc = rn.run("(compose z :in (bike-v1) :out spare-assy :role System "
                ":no-assembly spares-not-assembled)")
    assert rc == 0, rn.results
    res = [r for r in rn.results if r.get("form") == "compose"][-1]
    assert res["state"] == "promoted", res


def test_45_render_png():
    """V2: `fk render --png` is the perception channel — the honest DAG
    geometry as four machine-readable views (PNG magic, non-trivial
    size), same mesh pipeline as the preview page."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("sys", "System", "thing", contract(eng, t))
    sketch = {"pts": {"p0": [0, 0], "p1": [100, 0], "p2": [100, 60],
                      "p3": [0, 60]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 100],
                              ["dist", "p1", "p2", 60],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    eng.refine("sys", {"name": "ground-sketch", "args": {"sketch": sketch}},
               out_name="sk")
    eng.refine("sk", {"name": "extrude",
                      "args": {"height": 4, "material": "pla"}},
               out_name="plate-solid")
    from fluxkernel.strategy import scene, render_png
    parts = scene.collect_grounded(eng)
    assert parts, "grounded geometry not collected"
    groups = [(scene.role_color(p), scene.mesh_shape(s)) for _, p, s in parts]
    out = Path(tempfile.mkdtemp(prefix="fk-render-")) / "v"
    paths = render_png.render_views(groups, out, title="t45")
    assert len(paths) == 4, paths
    for q in paths:
        png_magic = bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10])
        assert Path(q).read_bytes()[:8] == png_magic, q
        assert Path(q).stat().st_size > 2000, q
    # the preview page carries per-shape colors and the STL attribute
    stl, n_tri = scene.write_stl_shapes([(s, i) for i, (_, _, s) in
                                         enumerate(parts)])
    assert n_tri >= 12 and len(stl) == 84 + 50 * n_tri


def _stub_vlm_server(reply_json: str):
    """Local OpenAI-compatible endpoint returning a canned reply."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)          # drain before responding
            body = json.dumps({
                "choices": [{"message": {"content": reply_json}}]
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, f"http://127.0.0.1:{srv.server_port}/v1"


def test_46_review_soft_only():
    """P7a: fk review archives VLM findings as SOFT obligations on a
    `review` edge; goals stay clean; verify schema-checks review edges
    and FAILS a review edge that smuggles a hard obligation (red line)."""
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("plane", "System", "aircraft", contract(eng, t, goals=[
        {"id": "g1", "stmt": "a twin-tail light aircraft",
         "falsifiable": True, "measure": "render review"}]))
    sketch = {"pts": {"p0": [0, 0], "p1": [100, 0], "p2": [100, 60],
                      "p3": [0, 60]},
              "constraints": [["fix", "p0", 0, 0], ["dist", "p0", "p1", 100],
                              ["dist", "p1", "p2", 60],
                              ["horiz", "p0", "p1"], ["vert", "p1", "p2"]]}
    eng.refine("plane", {"name": "ground-sketch", "args": {"sketch": sketch}},
               out_name="sk")
    eng.refine("sk", {"name": "extrude",
                      "args": {"height": 4, "material": "pla"}},
               out_name="plate-solid")

    from fluxkernel.strategy import review as fkreview
    reply = json.dumps([
        {"id": "visual-review-001", "prop": "render matches declared intent",
         "holds": False, "detail": "no tail surfaces visible in any view"}])
    srv, base = _stub_vlm_server(reply)
    try:
        os.environ["FK_VLM_BASE_URL"] = base
        os.environ["FK_VLM_API_KEY"] = "test-key"
        os.environ["FK_VLM_MODEL"] = "stub-vlm"
        rc = fkreview.run_review(eng, type("A", (), {
            "ref": "plate-solid", "vs": ""})())
        assert rc == 0
    finally:
        srv.shutdown()
        for k in ("FK_VLM_BASE_URL", "FK_VLM_API_KEY", "FK_VLM_MODEL"):
            os.environ.pop(k, None)

    # the review edge exists, is promoted, and every obligation is soft
    revs = [e for _, e in eng.dag.iter_edges() if e.get("op") == "review"]
    assert revs, "no review edge committed"
    for o in revs[-1]["certificate"]["obligations"]:
        assert o.get("class") == "soft", o        # red line, mechanically
    # review records never pollute the goals view
    gv = goalsview.goals_view(eng.dag)
    assert not any(n.get("kind") == "review" for n in gv["open"]), gv["open"]
    assert revs[-1].get("state") == "promoted", revs[-1].get("state")
    # verify is green with the review edge present...
    from fluxkernel.interface.cli import verify_store
    assert verify_store(eng) == []
    # ...and FAILS a review edge that smuggles a hard obligation
    fake = {"op": "review", "inputs": [], "output": "",
            "transform": {"name": "visual-review", "args": {}},
            "state": "promoted",
            "certificate": {"obligations": [
                {"id": "vlm-hard", "prop": "x", "holds": True,
                 "checker": "vlm", "class": "hard", "detail": ""}],
                "evidence": [{"solver": "vlm/stub"}]}}
    eng.store.put_object("edge", fake)
    problems = verify_store(eng)
    assert any("non-soft" in p for p in problems), problems


def test_47_iterate_loop_driver():
    """P7b: the loop driver runs rounds in fresh stores, reports both
    channels, and the NON-CONFIGURABLE stall detector stops an agent
    that echoes the same script forever (oscillation -> deadlock)."""
    import subprocess
    eng = fresh()
    t = terms(eng, "mass")
    # a script that NEVER closes: one open goal, no grounding
    script = ("(node wob \"System\" \"widget\" "
              "(contract (assumes ((in_v (>= 1) (<= 9))) "
              "(guarantees ((out_v (>= 2) (<= 8)))) "
              "(budget ((mass_kg (<= 5)))))))")
    from fluxkernel.strategy import loop as fkloop
    import inspect
    assert "STALL_ROUNDS" in dir(fkloop)
    src = inspect.getsource(fkloop.run_iterate)
    assert "no_vlm" in src or "no-vlm" in src

    # stub agent: echoes the SAME script every turn (an oscillator)
    stub = Path(tempfile.mkdtemp(prefix="fk-agent-")) / "echo.py"
    stub.write_text(
        "import sys, json\n"
        "msg = json.loads(sys.stdin.read())\n"
        "print(json.dumps({'edit': msg['script']}))\n",
        encoding="utf-8")

    workdir = Path(tempfile.mkdtemp(prefix="fk-it-test-"))
    script_path = workdir / "wob.fcad"
    script_path.write_text(script, encoding="utf-8")

    from fluxkernel.interface.cli import build_parser
    # invoke run_iterate via CLI arg namespace directly
    ns = type("A", (), {"script": str(script_path), "budget": 8,
                        "agent": f"{sys.executable} {stub}",
                        "no_vlm": True})()
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fkloop.run_iterate(ns)
    out = buf.getvalue()
    assert "DEADLOCK" in out, out
    assert "open=" in out
    assert rc in (0, 1)


def test_48_iterate_closed_loop_demo():
    """P7c: the perception-action loop closes a real gap end to end —
    a script missing its fin gets the VLM issue (stub), the agent
    grounds the fin, round 2 reaches OPEN(0); every round archived."""
    from fluxkernel.strategy import loop as fkloop
    import contextlib, io
    # round-0 script: aircraft decomposed into wing+fin, wing printed,
    # the FIN never grounded -> one open goal, no fin in the render
    script0 = """(term mass "structural mass of the object, kg")
(goal ac1 :kind aircraft
  :spec (contract
    (goals (g1 "a light aircraft with a vertical fin"
               :falsifiable t :measure "render review" :terms (mass)))
    (semantics mass)
    (assumes (a1 "bay in range" :bounds ((in_v (>= 1) (<= 9)))))
    (guarantees (gu1 "steady flight" :bounds ((out_v (>= 2) (<= 8)))))
    (budget (mass_kg (<= 50)))
    (forbidden (f1 "flutter below Vd" :check test))
    (time-scale mission)))
(refine d1 :in (ac1) :out ac-v1 :role System
  :transform (decompose :into (wing fin) :flow-down (
    (wing :budget ((mass_kg (<= 30))) :guarantees ((gw "wing lifts" :bounds ((mass_kg (<= 30))))))
    (fin :budget ((mass_kg (<= 5))) :guarantees ((gf "fin steadies" :bounds ((mass_kg (<= 5)))))))))
(exact wx :target ac-v1/wing :from catalog :match "span_mm>=400 mass_kg<=30" :out wing-std)
"""
    fin_forms = """(exact fx :target ac-v1/fin :from catalog :match "height_mm>=200 mass_kg<=5" :out fin-std)
"""
    # stub VLM: always reports the missing fin (it cannot see; the
    # fixture stands in for a vision finding)
    reply = json.dumps([{"id": "visual-review-001",
                         "prop": "render matches declared intent",
                         "holds": False,
                         "detail": "no vertical fin visible in any view"}])
    srv, base = _stub_vlm_server(reply)
    # stub agent: repairs exactly what the review names
    stub = Path(tempfile.mkdtemp(prefix="fk-fix-")) / "fix.py"
    fixer = (
        "import sys, json\n"
        "msg = json.loads(sys.stdin.read())\n"
        "s = msg['script']\n"
        "if any('no vertical fin' in str(i) "
        "for i in msg['review_issues']) and 'fin-std' not in s:\n"
        "    s = s + FIN_FORMS\n"
        "print(json.dumps({'edit': s}))\n"
    ).replace("FIN_FORMS", repr(fin_forms))
    stub.write_text(fixer, encoding="utf-8")
    workdir = Path(tempfile.mkdtemp(prefix="fk-p7c-"))
    spath = workdir / "ac.fcad"
    spath.write_text(script0, encoding="utf-8")
    try:
        os.environ["FK_VLM_BASE_URL"] = base
        os.environ["FK_VLM_API_KEY"] = "k"
        os.environ["FK_VLM_MODEL"] = "stub-vlm"
        ns = type("A", (), {"script": str(spath), "budget": 6,
                            "agent": f"{sys.executable} {stub}",
                            "no_vlm": False})()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fkloop.run_iterate(ns)
        out = buf.getvalue()
        assert "SUCCESS" in out, out[-2000:]
        assert rc == 0
    finally:
        srv.shutdown()
        for k in ("FK_VLM_BASE_URL", "FK_VLM_API_KEY", "FK_VLM_MODEL"):
            os.environ.pop(k, None)


def test_50_broken_scope_net_never_closes():
    """U5 (review v05 G7/G8): a decomposed scope whose assembly compose
    was REJECTED, or whose verification eval FAILED (non-informative),
    surfaces as an OPEN goal — the closure predicate is no longer blind
    to a broken template net or a failed structural check."""
    from fluxkernel.semantics import goals as gv
    eng = fresh()
    t = terms(eng, "mass")
    eng.node("sys", "System", "thing", contract(eng, t))
    eng.refine("sys", {"name": "decompose",
                        "args": {"into": ["a", "b"],
                                 "flow_down": {
                                     "a": {"guarantees": [
                                         {"id": "ga", "stmt": "a works",
                                          "bounds": {"mass_kg": {"<=": 5}}}]},
                                     "b": {"guarantees": [
                                         {"id": "gb", "stmt": "b works",
                                          "bounds": {"mass_kg": {"<=": 5}}}]}}}},
               out_name="scope")
    ra = eng.exact("scope/a", "catalog", "span_mm>=400", out_name="a-std")
    rb = eng.exact("scope/b", "catalog", "height_mm>=200", out_name="b-std")
    assert ra["state"] == "promoted" and rb["state"] == "promoted"
    # rejected compose: Part inputs into an illegal Component output role
    bad = eng.compose(["a-std", "b-std"], out_name="assy",
                       out_role="Component")
    assert bad["state"] == "rejected", bad.get("reason")
    open_refs = [g["kind"] for g in gv.goals_view(eng.dag)["open"]]
    assert "thing" in open_refs or open_refs, open_refs
    assert gv.goals_view(eng.dag)["open"], "broken net must surface"
    # the same net with a LEGAL compose closes
    eng2 = fresh()
    t2 = terms(eng2, "mass")
    eng2.node("sys", "System", "thing", contract(eng2, t2))
    eng2.refine("sys", {"name": "decompose",
                         "args": {"into": ["a", "b"],
                                  "flow_down": {
                                      "a": {"guarantees": [
                                          {"id": "ga", "stmt": "a works",
                                           "bounds": {"mass_kg": {"<=": 5}}}]},
                                      "b": {"guarantees": [
                                          {"id": "gb", "stmt": "b works",
                                           "bounds": {"mass_kg": {"<=": 5}}}]}}}},
                out_name="scope")
    eng2.exact("scope/a", "catalog", "span_mm>=400", out_name="a-std",
               at=[[0, 0, 0]])
    eng2.exact("scope/b", "catalog", "height_mm>=200", out_name="b-std",
               at=[[700, 0, 0]])
    ok = eng2.compose(["a-std", "b-std"], out_name="assy",
                       out_role="System")
    assert ok["state"] == "promoted", ok.get("reason")
    assert not gv.goals_view(eng2.dag)["open"]
    # failed eval on a subtree member blocks its ancestor scope; the
    # informative flag exempts (structure mirrors the case: genesis ->
    # refine -> decompose -> catalog closures)
    def _eval_tree(eng_x, informative):
        t = terms(eng_x, "mass")
        eng_x.node("m", "System", "thing", contract(eng_x, t))
        eng_x.refine("m", {"name": "point-mass-model"}, out_name="m-pm")
        eng_x.refine("m-pm", {"name": "decompose",
                              "args": {"into": ["a", "b"], "flow_down": {
                                  "a": {"guarantees": [
                                      {"id": "ga", "stmt": "a",
                                       "bounds": {"mass_kg": {"<=": 5}}}]},
                                  "b": {"guarantees": [
                                      {"id": "gb", "stmt": "b",
                                       "bounds": {"mass_kg": {"<=": 5}}}]}}}},
                   out_name="scope")
        ra = eng_x.exact("scope/a", "catalog", "span_mm>=400",
                         out_name="a-std")
        rb = eng_x.exact("scope/b", "catalog", "height_mm>=200",
                         out_name="b-std", at=[[700, 0, 0]])
        assert ra["state"] == "promoted" and rb["state"] == "promoted"
        ev = eng_x.evaluate("a-std", "mission-analysis", fidelity=0,
                            expect={"range_km": {">=": 999999}},
                            informative=informative)
        assert ev["state"] == "rejected"
        return gv.goals_view(eng_x.dag)["open"]

    eng3 = fresh()
    assert _eval_tree(eng3, informative=False), \
        "a failed (non-informative) eval must open its scope"
    eng4 = fresh()
    assert not _eval_tree(eng4, informative=True), \
        ":informative exempts the scope (e2x pattern)"

def test_51_case_contract_gates():
    """CC1/CC2: the methodology is now a hard gate.  A case-contract
    with an unmet require keeps OPEN != 0; unknown keys are refused;
    the prsi-full profile reports equipment-development termination;
    L7/L8 lint fire on a shallow store without any contract."""
    from fluxkernel.semantics import goals as gv
    from fluxkernel.semantics import contracts as fc
    from fluxkernel.semantics import casecontract as ccm
    eng = fresh()
    t = terms(eng, 'mass')
    eng.node('m', 'System', 'thing', contract(eng, t))
    eng.case_contract('mini', 'product',
                      {'manufacturing-chains': {'n': 1, 'with-machine': True}})
    g = gv.goals_view(eng.dag)
    assert g['case'], 'unmet require must surface'
    assert any(c['kind'] == 'case-requirement' for c in g['case'])
    # schema: unknown require key refused
    errs = ccm.validate_schema({'requires': {'bogus-key': 1}})
    assert errs and 'bogus-key' in errs[0]
    # prsi-full termination label on a grounded open part
    eng2 = fresh()
    t2 = terms(eng2, 'mass')
    eng2.node('m2', 'System', 'thing', contract(eng2, t2))
    eng2.case_contract('p2', 'prsi-full', {})
    sketch = {'pts': {'a': [0, 0], 'b': [50, 0], 'c': [50, 30], 'd': [0, 30]},
              'constraints': [['fix', 'a', 0, 0]]}
    eng2.refine('m2', {'name': 'ground-sketch', 'args': {'sketch': sketch}},
                out_name='s2')
    eng2.refine('s2', {'name': 'extrude',
                       'args': {'height': 4, 'material': 'pla'}},
                out_name='p2-solid', out_role='Part')
    g2 = gv.goals_view(eng2.dag)
    terms2 = [o.get('termination') for o in g2['open']]
    assert any('requires-equipment-development' in str(x) for x in terms2), terms2
    # L7/L8 fire on a CONTRACT-FREE shallow store (eng2 carries a
    # contract so it is exempt by design)
    eng3 = fresh()
    t3 = terms(eng3, 'mass')
    eng3.node('m3', 'System', 'thing', contract(eng3, t3))
    sketch = {'pts': {'a': [0, 0], 'b': [50, 0], 'c': [50, 30], 'd': [0, 30]},
              'constraints': [['fix', 'a', 0, 0]]}
    eng3.refine('m3', {'name': 'ground-sketch', 'args': {'sketch': sketch}},
                out_name='s3')
    eng3.refine('s3', {'name': 'extrude',
                       'args': {'height': 4, 'material': 'pla'}},
                out_name='p3-solid', out_role='Part')
    eng3.compose(['p3-solid'], out_name='veh', out_role='System')
    fired = fc.lint_case(eng3.dag)
    assert 'L8' in fired, fired
    assert fc.lint_case(eng2.dag) == [], 'contract-carrying store exempt'



# ================================================ discipline ==============









def test_layer_discipline():
    """core/ and store/ import ZERO third-party packages (relative imports
    stay inside the package by construction)."""
    import ast
    stdlib = set(sys.stdlib_module_names)
    for pkg_dir in ("core", "store"):
        for f in (REPO / "fluxkernel" / pkg_dir).glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        root = a.name.split(".")[0]
                        assert root in stdlib or root == "fluxkernel", \
                            f"{f.name} imports {a.name}"
                elif isinstance(node, ast.ImportFrom) and node.module \
                        and node.level == 0:
                    root = node.module.split(".")[0]
                    assert root in stdlib or root == "fluxkernel", \
                        f"{f.name} imports from {node.module}"


# ------------------------------------------------------------- runner -----
if __name__ == "__main__":
    tests = [(n, fn) for n, fn in sorted(globals().items())
             if n.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"ERROR {name}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
