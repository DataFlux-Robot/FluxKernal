"""One-off generator: emit examples/aircraft.fcad from structured definitions
(so paren balance is guaranteed by construction)."""
from fluxkernel.interface import fcad

S = fcad.to_sexpstr


def F(*items):
    """Render a form with FLAT keyword args: (head p1 :k v :k2 v2)."""
    parts = []
    for it in items:
        if isinstance(it, list) and it and isinstance(it[0], str) and it[0].startswith(":"):
            parts.append(it[0])
            parts.append(S(it[1]))
        else:
            parts.append(S(it))
    return "(" + " ".join(parts) + ")"


def kw(k, v):
    return [":" + k, v]


def bound(q, op, v, medium=None):
    return [q, [op, v, ":medium", medium]] if medium else [q, [op, v]]


def flow_entry(slot, budget_pairs, gid, stmt, guarantee_pairs):
    budgets = []
    for bp in budget_pairs:
        if len(bp) == 4:
            q, op, v, medium = bp
            budgets.append([q, [op, v, ":medium", medium]])
        else:
            q, op, v = bp
            budgets.append([q, [op, v]])
    return S([slot,
              [":budget", budgets],
              [":guarantees", [[gid, stmt, [":bounds",
                                            [[q, [op, v]] for q, op, v in guarantee_pairs]]]]]])


def decompose(name, inp, outn, role, into, entries):
    lines = [f"(refine {name} :in ({inp}) :out {outn} :role {role}",
             "  :transform (decompose",
             f"    :into ({' '.join(into)})",
             "    :flow-down ("]
    lines += ["      " + flow_entry(*e) for e in entries[:-1]]
    lines.append("      " + flow_entry(*entries[-1]) + ")")   # close flow-down list
    lines.append("    ))")                                     # close decompose + refine
    return "\n".join(lines)


def build():
    o = []
    w = o.append
    w(';; examples/aircraft.fcad —— "我想飞，往返 A 到 B"')
    w(';;')
    w(';; End-to-end acceptance walkthrough (impl plan §9) in the v1.2 contract-native')
    w(';; syntax. Intent -> point-mass holes -> Breguet eval -> decompose -> wing')
    w(';; variants -> rib geometry -> manufacture -> line roll-up -> machine Resource')
    w(';; -> machine as System (PRSI recursion) -> exact/procure from catalog ->')
    w(';; compose back up the V right leg (C1-C4 + medium ledgers on the way).')
    w(';; A failing form marks its edge rejected and the script CONTINUES; the')
    w(';; exit code stays non-zero.')
    w('')
    w(';; ── semantic glossary (v1.2 §23: nouns must resolve before entering specs) ──')
    w(F("term", "aircraft", "powered vehicle sustaining controlled atmosphere flight between two points"))
    w(F("term", "range", "great-circle distance flown with reserves, km"))
    w(F("term", "payload", "revenue mass carried including crew, kg"))
    w(F("term", "mass", "structural + systems mass of the object, kg"))
    w(F("term", "power", "electrical watts drawn from the DC bus under load"))
    w(F("term", "thermal", "heat watts rejected into the cabin air"))
    w(F("term", "takt", "minutes between finished units at the bottleneck"))
    w(F("term", "machining", "material removal by multi-axis milling per drawing dims"))
    w('')
    w(';; ── shared media (v1.2 §19: shared buses/fields are first-class nodes) ──')
    w(F("node", "dc-bus", kw("role", "Medium"), kw("kind", "dc-bus"),
         kw("spec", ["medium", ["capacity", bound("power_w", "<=", 5000)],
                     ["margin", 0.2]])))
    w(F("node", "cabin-air", kw("role", "Medium"), kw("kind", "thermal-env"),
         kw("spec", ["medium", ["capacity", bound("heat_w", "<=", 1200)],
                     ["margin", 0.1]])))
    w('')

    ac0 = ["contract",
           ["goals",
            ["r1", "fly route A to B and back", kw("falsifiable", True),
             kw("measure", "mission sim: range_km with reserves"),
             kw("terms", ["range", "aircraft"])],
            ["p1", "carry paying payload", kw("falsifiable", True),
             kw("measure", "W&B sheet at MTOW"), kw("terms", ["payload"])]],
           ["semantics", "aircraft", "range", "payload", "mass", "thermal"],
           ["assumes", ["env1", "sea-level std day at A and B",
                        kw("bounds", [bound("isa_temp_c", ">=", -20),
                                      bound("isa_temp_c", "<=", 45)])]],
           ["guarantees", ["gr1", "delivers range with reserves",
                           kw("bounds", [bound("range_km", ">=", 2600),
                                         bound("payload_kg", ">=", 500)])]],
           ["budget", bound("mass_kg", "<=", 2600)],
           ["effluent", bound("heat_w", "<=", 300, "cabin-air")],
           ["forbidden", ["f1", "flutter below Vd/1.2", kw("check", "test")],
                         ["f2", "CG outside envelope", kw("check", "inspection")]],
           ["not-responsible", "airport ground handling", "crew licensing"],
           ["time-scale", "mission"]]
    w(';; ── step 1: the vague demand, contract-native ──')
    w("(goal ac0 :kind aircraft\n  :spec " + S(ac0) + ")")
    w('')
    w(';; ── step 2: single point-mass model, ALL parameters are holes (sorry) ──')
    w("(refine e1 :in (ac0) :out ac-point :role System :kind point-mass\n"
      "  :transform (point-mass-model))")
    w(F("eval", "e2", kw("target", "ac-point"), kw("with", "mission-analysis"),
         kw("fidelity", 0), kw("expect", [["range-margin-km", [">", 0]]])))
    w('')
    w(';; ── step 3: decompose into subsystems; contracts flow down (v1.2 §17.2) ──')
    w(decompose("e3", "ac-point", "ac-v1", "System",
                ["wing", "engine", "nose", "tail", "fuselage"],
                [("wing", [("mass_kg", "<=", 700)], "gw1", "wing lifts MTOW at 1.3g",
                  [("lift_n", ">=", 34000), ("mass_kg", "<=", 700)]),
                 ("engine", [("mass_kg", "<=", 550)], "ge1",
                  "thrust for 3.2 m/s^2 climb",
                  [("thrust_n", ">=", 2600), ("mass_kg", "<=", 550)]),
                 ("nose", [("mass_kg", "<=", 120)], "gn1", "houses avionics",
                  [("mass_kg", "<=", 120)]),
                 ("tail", [("mass_kg", "<=", 180)], "gt1", "static margin 5-15%",
                  [("mass_kg", "<=", 180)]),
                 ("fuselage", [("mass_kg", "<=", 900)], "gf1", "payload bay volume",
                  [("mass_kg", "<=", 900)])]))
    w('')
    w(';; ── step 4: variant collapse then decompose the wing ──')
    w("(refine e5 :in (ac-v1/wing) :out wing-v2 :kind wing\n"
      "  :transform (select-variant :choice cantilever))")
    w(decompose("e6", "wing-v2", "wing-v3", "Component", ["skin", "tank", "rib"],
                [("skin", [("mass_kg", "<=", 280)], "gs1",
                  "skin panels carry pressure",
                  [("mass_kg", "<=", 280), ("skin_t_mm", ">=", 0.8)]),
                 ("tank", [("mass_kg", "<=", 180)], "gt1", "seals fuel at 0.3 bar",
                  [("mass_kg", "<=", 180)]),
                 ("rib", [("mass_kg", "<=", 12)], "gr1", "carries panel shear",
                  [("mass_kg", "<=", 12), ("web_h_mm", ">=", 19)])]))
    w(';; the skin keeps a param hole: L6 requires a range — supplied here.')
    w("(refine e6b :in (wing-v3/skin) :out skin-detailed :kind skin-panel\n"
      "  :transform (set-param-bounds)\n"
      "  :spec (contract (param-bounds (skin-t (>= 0.8) (<= 4.0))))\n"
      "  :params (skin-t (param skin-t)))")
    w('')
    w(';; ── step 5: rib geometry — sketch (bounded holes) -> extrude ──')
    sk = ["sketch",
          ["pts", ["p0", ["param", "hw"], 0],
           ["p1", ["param", "hw"], ["param", "hh"]],
           ["p2", 0, ["param", "hh"]], ["p3", 0, 0]],
          ["constraints", ["fix", "p3", 0, 0], ["dist", "p0", "p1", 20],
           ["dist", "p1", "p2", 10], ["vert", "p0", "p1"], ["horiz", "p1", "p2"]]]
    w("(refine e7 :in (wing-v3/rib) :out rib-sk :kind sketch\n"
      "  :transform (ground-sketch :sketch " + S(sk) + ")\n"
      "  :spec (contract (param-bounds (hw (>= 8) (<= 12)) (hh (>= 18) (<= 22)))))")
    w(F("refine", "e8", kw("in", ["rib-sk"]), kw("out", "rib-solid"), kw("kind", "rib"),
         kw("transform", ["extrude", kw("height", 3), kw("material", "aluminum")])))
    w(F("eval", "e8b", kw("target", "rib-solid"), kw("with", "dfam-check"),
         kw("fidelity", 0), kw("args", ["process", "fdm", "min_wall_mm", 1.0]),
         kw("expect", [["min_dim_mm", [">", 2]]])))
    w('')
    w(';; ── steps 7-9: machined part -> process family -> line ──')
    w(F("manufacture", "e9", kw("in", ["rib-solid"]), kw("out", "rib-proc"),
         kw("transform", ["process-plan",
                          kw("into", ["stock", "milling-5axis", "inspection"])])))
    w(F("compose", "e10", kw("in", ["rib-proc/stock", "rib-proc/milling-5axis",
                                    "rib-proc/inspection"]),
         kw("out", "rib-line"), kw("role", "Line"), kw("kind", "rib-line"),
         kw("transform", ["line-eval"]),
         kw("rollup", [["takt_min", ["<=", 12]], ["oee", [">=", 0.5]]])))
    w('')
    w(';; ── steps 10-11: the LINE demands a machine — Resource ≅ System (PRSI) ──')
    w(F("refine", "e11", kw("in", ["rib-line"]), kw("out", "mill-req"),
         kw("role", "Resource"), kw("kind", "5axis-mill-demand")))
    w(decompose("e12", "mill-req", "mill-v1", "System",
                ["bed", "spindle-motor", "cnc-drive"],
                [("bed", [("mass_kg", "<=", 2000),
                          ("power_w", "<=", 100, "dc-bus")],
                  "gb1", "static stiffness", [("mass_kg", "<=", 2000)]),
                 ("spindle-motor", [("mass_kg", "<=", 9),
                                    ("power_w", "<=", 3000, "dc-bus")],
                  "gsm1", "spindle torque and speed",
                  [("torque_nm", ">=", 8), ("rpm", ">=", 12000)]),
                 ("cnc-drive", [("mass_kg", "<=", 40),
                                ("power_w", "<=", 500, "dc-bus")],
                  "gcd1", "drive bandwidth", [("power_w", "<=", 500)])]))
    w('')
    w(';; ── standard parts close goals directly: exact lemma + procure axiom ──')
    w(F("exact", "e13", kw("target", "mill-v1/spindle-motor"),
         kw("from", "catalog"), kw("match", "torque_nm>=8 rpm>=12000"),
         kw("out", "spindle-motor-std")))
    w(F("procure", "e14", kw("target", "mill-v1/cnc-drive"), kw("from", "catalog"),
         kw("match", "power_w>=200 power_w<=600"), kw("out", "cnc-drive-bought")))
    w('')
    w(';; ── the V right leg: compose back up, clearing flow-down obligations ──')
    w(F("compose", "e15", kw("in", ["mill-v1/bed", "spindle-motor-std",
                                    "cnc-drive-bought"]),
         kw("out", "mill-5axis"), kw("role", "Resource"), kw("kind", "5axis-mill")))
    w(F("compose", "e16", kw("in", ["mill-5axis", "rib-proc"]),
         kw("out", "rib-line-v2"), kw("role", "Line"), kw("kind", "rib-line")))
    w(F("compose", "e17", kw("in", ["skin-detailed", "wing-v3/tank", "rib-solid"]),
         kw("out", "wing-assy"), kw("role", "Component"),
         kw("kind", "wing-assembly")))
    w(F("compose", "e18", kw("in", ["wing-assy", "ac-v1/engine", "ac-v1/nose",
                                    "ac-v1/tail", "ac-v1/fuselage"]),
         kw("out", "ac-final"), kw("role", "System"), kw("kind", "aircraft"),
         kw("rollup", [["range_km", [">=", 2600]]])))
    return "\n".join(o) + "\n"


if __name__ == "__main__":
    text = build()
    forms = fcad.parse(text)
    with open("examples/aircraft.fcad", "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("written;", len(forms), "top-level forms")
