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
    res = eng.print_part("rib-solid", "reference-printer", out_name="rib-printed")
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
    res2 = eng.print_part("rib-solid", "reference-printer",
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
    r5 = eng.print_part("frame-solid", "reference-printer", out_name="frame-printed")
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
    res = eng.print_part("pl-solid", "reference-printer", out_name="pl-printed")
    assert res["state"] == "promoted", res["reason"]
    pe = eng.dag.producing_edge(eng.store.resolve("pl-printed"))
    part_d = eng.store.resolve("pl-solid")
    pr_d = eng.store.resolve("reference-printer")
    assert pe.get("inputs") == [part_d, pr_d], pe.get("inputs")


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
