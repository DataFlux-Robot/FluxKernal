"""Scratch smoke test for the L3 core loop (not part of the acceptance suite)."""
import tempfile, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fluxkernel.store.objstore import Store
from fluxkernel.semantics.operators import Engine
from fluxkernel.semantics import contracts, goals

td = tempfile.mkdtemp()
st = Store(os.path.join(td, ".fk"))
eng = Engine(st)
assert not eng.plugin_failures or all("No module" in f for f in eng.plugin_failures)

# --- terms (glossary) ---
t_power = contracts.put_term(st, "power", "watts delivered at the DC bus under load")
t_therm = contracts.put_term(st, "thermal", "heat rejected into the cabin air")


def contract(guarantees=None, budget=None, assumes=None, effluent=None):
    return {
        "goals": [{"id": "g1", "stmt": "deliver regulated power", "falsifiable": True,
                   "measure": "bench: vout under step load", "terms": ["power"]}],
        "semantics": [t_power, t_therm],
        "assumes": assumes or [{"id": "a1", "stmt": "vin 22-29V",
                                "bounds": {"vin_v": {">=": 22, "<=": 29}},
                                "terms": ["power"]}],
        "guarantees": guarantees or [{"id": "gu1", "stmt": "vout 26-28V",
                                      "bounds": {"vout_v": {">=": 26, "<=": 28}},
                                      "terms": ["power"]}],
        "budget": budget or {},
        "effluent": effluent or {},
        "forbidden": [{"id": "f1", "stmt": "reverse polarity", "check": "inspection"}],
        "not_responsible": ["source regulation"],
        "time_scale": "control-tick",
    }


# --- medium: DC bus, capacity 100 W, margin 20% ---
eng.node("bus", "Medium", "dc-bus",
         {"capacity": {"power_w": ["<=", 100]}, "margin": 0.2,
          "state": {"power_w": 0.0}, "degradation": {}})
bus_d = st.resolve("bus")

# genesis system whose children draw from the bus
eng.node("pwr-sys", "System", "power-system", contract())

# child A: assumes 22-29V, guarantees 26-28V, draws 50W from the bus
spec_a = contract(budget={"power_w": {"op": "<=", "value": 50, "medium": bus_d}})
r_a = eng.refine("pwr-sys", {"name": "mk-converter"}, out_name="conv-a",
                 out_role="Component", out_kind="converter", out_spec=spec_a)
print("A:", r_a["state"], r_a["reason"] or "")

# child B: draws 50W as well -> 100 > 100*0.8 = 80 => C2 must fail
spec_b = contract(budget={"power_w": {"op": "<=", "value": 50, "medium": bus_d}},
                  guarantees=[{"id": "gu1", "stmt": "vout 27-27.5V",
                               "bounds": {"vout_v": {">=": 27, "<=": 27.5}},
                               "terms": ["power"]}])
r_b = eng.refine("pwr-sys", {"name": "mk-converter"}, out_name="conv-b",
                 out_role="Component", out_kind="converter", out_spec=spec_b)
print("B:", r_b["state"], r_b["reason"] or "")

# ledger check
led = contracts.ledger(eng.dag, "bus")
print("ledger sums:", led["sums"], "ok:", led["ok"])

# compose A+B into a power module: C2 should fail via medium-capacity
r_c = eng.compose(["conv-a", "conv-b"], out_name="pwr-mod", out_role="Component",
                  out_kind="power-module", out_spec=contract())
print("C:", r_c["state"], r_c["reason"] or "")
assert r_c["state"] == "rejected" and "medium-capacity" in r_c["reason"], "C2 must fire"

# downstream edge referencing rejected output must I3-reject
r_d = eng.refine("pwr-mod", {"name": "mk2"}, out_name="pwr-mod2", out_role="Component")
print("D:", r_d["state"], r_d["reason"] or "")
assert r_d["state"] == "rejected" and "I3" in r_d["reason"]

# goals/risks views
gv = goals.goals_view(eng.dag)
print("open goals:", [(g["kind"], g["risks"]) for g in gv["open"]])
rv = goals.risks_view(eng.dag)
print("risk kinds:", sorted({r["kind"] for r in rv["risks"]}))
nv = goals.next_goal(eng.dag)
print("next:", nv["kind"] if nv else None)
wh = goals.why(eng.dag, "conv-a")
print("why chain:", [(w["kind"], w.get("via")) for w in wh])

# lint gate: incomplete contract never promotes
bad = {"goals": [], "semantics": [], "assumes": [], "guarantees": [], "budget": {},
       "effluent": {}, "forbidden": [], "not_responsible": [], "time_scale": None}
r_e = eng.refine("pwr-sys", {"name": "mk3"}, out_name="bad-node", out_role="Component",
                 out_spec=bad)
print("E:", r_e["state"], r_e["reason"] or "")
assert r_e["state"] == "proposed" and r_e["reason"].startswith("L"), "lint gate must cap"

print("SMOKE OK")
