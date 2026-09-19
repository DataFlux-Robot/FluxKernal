"""Patch sha_pek.fcad: (1) wing STRUCTURAL decomposition (skin/spar/rib,
rib grounded sketch->extrude, wing-assy compose); (2) the machine-tool chain
(manufacture -> process ops -> line -> Resource -> System decompose ->
exact/procure from catalog -> fab-mill compose) with a DC-bus medium ledger."""
from pathlib import Path

from fluxkernel.interface import fcad
S = fcad.to_sexpstr

REPO = Path(__file__).resolve().parents[1]
FCAD = REPO / "examples" / "sha_pek.fcad"

# ---------------------------------------------------------------- blocks --
DC_BUS = """
;; ── shared medium: DC power bus feeding the fabrication cell ──
(node dc-bus :role Medium :kind dc-bus
  :spec (medium (capacity (power_w (<= 5000))) (margin 0.2)))
"""


def flow_entry(slot, budget, gid, stmt, pairs):
    budgets = []
    for bp in budget:
        if len(bp) == 4:
            q, op, v, medium = bp
            budgets.append([q, [op, v, ":medium", medium]])
        else:
            q, op, v = bp
            budgets.append([q, [op, v]])
    return S([slot,
              [":budget", budgets],
              [":guarantees", [[gid, stmt, [":bounds",
                                            [[q, [op, v]] for q, op, v in pairs]]]]]])


def decompose(name, inp, outn, role, into, entries):
    lines = [f"(refine {name} :in ({inp}) :out {outn} :role {role}",
             "  :transform (decompose",
             f"    :into ({' '.join(into)})",
             "    :flow-down ("]
    lines += ["      " + flow_entry(*e) for e in entries[:-1]]
    lines.append("      " + flow_entry(*entries[-1]) + ")")
    lines.append("    ))")
    return "\n".join(lines)


WING_BLOCK = """
;; ── wing STRUCTURAL decomposition: skin / spar / rib (contracts flow down) ──
""" + decompose(
    "e4a", "sha-pek-v1/wing", "wing-v1", "Component",
    ["skin", "spar", "rib"],
    [("skin", [("mass_kg", "<=", 120)], "gws", "skin panels carry airload",
      [("mass_kg", "<=", 120)]),
     ("spar", [("mass_kg", "<=", 80)], "gwp", "main spar carries bending",
      [("mass_kg", "<=", 80), ("bending_knm", "<=", 45)]),
     ("rib", [("mass_kg", "<=", 12)], "gwr", "rib web carries panel shear",
      [("mass_kg", "<=", 12), ("web_h_mm", ">=", 150)])]) + """

;; ground the rib web: sketch (one bounded hole) -> 3mm aluminum extrusion
(refine e4b :in (wing-v1/rib) :out rib-sk :kind sketch
  :transform (ground-sketch :sketch (sketch
    (pts (p0 (param hw) 0) (p1 (param hw) 200) (p2 0 200) (p3 0 0))
    (constraints (fix p3 0 0) (dist p1 p2 600) (vert p0 p1) (horiz p1 p2))))
  :spec (contract (param-bounds (hw (>= 500) (<= 700)))))
(refine e4c :in (rib-sk) :out rib-solid :kind rib
  :transform (extrude :height 3 :material aluminum))

;; compose the wing subtree back (V right leg, one level down)
(compose e4d :in (wing-v1/skin wing-v1/spar rib-solid)
  :out wing-assy :role Component :kind wing-assembly)
"""

FAB_BLOCK = """
;; ══ production branch: the machined rib demands a fabrication cell ══
;; Part -> process family -> line -> machine Resource -> machine as System
;; (PRSI recursion) -> catalog closures -> fab-mill compose. The DC-bus
;; ledger gates the cell's power draw (Σ ≤ capacity×(1−margin)).
(manufacture e5a :in (rib-solid) :out rib-proc
  :transform (process-plan :into (stock milling-3axis inspection)))
(compose e5b :in (rib-proc/stock rib-proc/milling-3axis rib-proc/inspection)
  :out rib-line :role Line :kind rib-line
  :transform (line-eval)
  :rollup ((takt_min (<= 60)) (oee (>= 0.5))))
(refine e5c :in (rib-line) :out fab-req :role Resource :kind 3axis-mill-demand)
""" + decompose(
    "e5d", "fab-req", "fab-v1", "System",
    ["bed", "spindle-motor", "cnc-drive"],
    [("bed", [("mass_kg", "<=", 2000), ("power_w", "<=", 100, "dc-bus")],
      "gfb", "static stiffness", [("mass_kg", "<=", 2000)]),
     ("spindle-motor", [("mass_kg", "<=", 9), ("power_w", "<=", 3000, "dc-bus")],
      "gfs", "spindle torque and speed",
      [("torque_nm", ">=", 8), ("rpm", ">=", 12000)]),
     ("cnc-drive", [("mass_kg", "<=", 40), ("power_w", "<=", 500, "dc-bus")],
      "gfd", "drive bandwidth", [("power_w", "<=", 500)])]) + """

(exact e5e :target fab-v1/spindle-motor :from catalog
  :match "torque_nm>=8 rpm>=12000" :out fab-spindle-std)
(procure e5f :target fab-v1/cnc-drive :from catalog
  :match "power_w>=200 power_w<=600" :out fab-drive-bought)
(compose e5g :in (fab-v1/bed fab-spindle-std fab-drive-bought)
  :out fab-mill :role Resource :kind 3axis-mill)
"""

# ---------------------------------------------------------------- patch ---
text = FCAD.read_text(encoding="utf-8")
lines = text.splitlines(keepends=False)

# 1) dc-bus medium right after the cabin-air node form
assert "(node cabin-air" in text
idx = next(i for i, ln in enumerate(lines) if ln.startswith("(node cabin-air"))
# form ends when depth returns to 0
d = 0
end = idx
for j in range(idx, len(lines)):
    d += lines[j].count("(") - lines[j].count(")")
    if d == 0:
        end = j
        break
lines[end + 1:end + 1] = DC_BUS.strip("\n").splitlines()

# 2) wing block before the e5 compose; rewrite e5 inputs to wing-assy
e5 = next(i for i, ln in enumerate(lines) if ln.startswith("(compose e5 "))
lines[e5] = lines[e5].replace(
    ":in (sha-pek-v1/wing sha-pek-v1/fuselage sha-pek-v1/avionics epu-std)",
    ":in (wing-assy sha-pek-v1/fuselage sha-pek-v1/avionics epu-std)")
assert "wing-assy" in lines[e5], lines[e5]
lines[e5:e5] = WING_BLOCK.strip("\n").splitlines()

# 3) fab block right before the mockup branch
mk = next(i for i, ln in enumerate(lines)
          if "geometric mockup branch" in ln)
lines[mk:mk] = FAB_BLOCK.strip("\n").splitlines()

FCAD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
forms = fcad.parse(FCAD.read_text(encoding="utf-8"))
print("patched OK; forms:", len(forms))
