"""Generate examples/sw45_watch.fcad — the whole file is emitted from
nested lists via S(); parens are balanced by construction.
Run: python tools/gen_sw45.py
"""
import math


def S(x):
    if isinstance(x, list):
        return "(" + " ".join(S(i) for i in x) + ")"
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


def bnd(*pairs):
    """bounds sexpr: ((qty (op v) (op v)) ...) — qty followed by nested
    (op v) pairs, matching the sha_pek/TK hand-written form.  Each pair
    is (qty, op, v); v may be a number or a string."""
    out = []
    for q, op, v in pairs:
        vv = f"{v:g}" if isinstance(v, float) else v
        out.append([q, [op, vv]])
    return out


def ngon(prefix, r, n=24):
    return [[f"{prefix}{k}", round(r * math.cos(2 * math.pi * k / n), 3),
             round(r * math.sin(2 * math.pi * k / n), 3)] for k in range(n)]


def sk(name, src, out, pts):
    return ["refine", name, ":kind", "sketch", ":in", [src],
            ":transform", ["ground-sketch",
                            ["sketch", {"pts": pts}, ["constraints"]]]]


HDR = """;; ==================================================================
;; SW-45 round smart watch - fcad-from-image six stations.  New
;; product class: hand-written branch; fk-mechanism-author will
;; abstract it to a mechanism when a second watch appears.  Circles
;; are 24-gon prisms; the case cavity is a boolean cut.
;; ==================================================================
"""

F = []
F.append(["term", "mass", "total worn mass of the device, kg"])
F.append(["term", "display", "visible display diameter, mm"])
F.append(["term", "capacity", "battery charge capacity, mAh"])
F.append(["term", "printer", "additive fabrication resource"])
F.append(["term", "frame", "structural frame of a machine"])

F.append(["reference-image",
          "C:/Users/zhang/.zcode/cli/image-cache/sess_c614d16a-25a7-45fa-a4a6-8a06fa331ea0/image-cb86ab041cb6f6e60e264a48c323028d.png",
          ":for", "sw45"])

F.append(["case-contract", "sw45", ":type", "product-reverse", ":requires",
          [["termination", ["standard-parts", "printable"]],
           ["reference-fidelity", ["issues-max", 2]]]])

F.append(["node", "reference-printer", ":role", "Resource",
          ":kind", "unbounded-fdm-printer",
          ":spec", ["contract",
              ["goals", ["rp1", "print every structural part",
                          ":falsifiable", "t", ":measure", "dfam gate",
                          ":terms", ["printer", "frame"]]],
              ["semantics", "printer", "frame"],
              ["assumes", ["rp-a1", "unbounded volume",
                            ":bounds", bnd(("dim_mm", ">=", 0.0))]],
              ["guarantees", ["rp-g1", "prints grounded parts",
                               ":bounds", bnd(("mass_g", "<=", 100000))]],
              ["budget", bnd(("mass_kg", "<=", 60.0))],
              ["forbidden", ["rp-f1", "overnight run", ":check", "test"]],
              ["not-responsible", "filament logistics"],
              ["time-scale", "fabrication"]]])

F.append(["goal", "sw45", ":kind", "smartwatch",
          ":spec", ["contract",
              ["goals",
                  ["g1", "round smart watch matching the reference photo",
                   ":falsifiable", "t", ":measure", "render review vs photo",
                   ":terms", ["mass", "display"]],
                  ["g2", "all-day battery per class standard",
                   ":falsifiable", "t", ":measure", "capacity vs class 400mAh",
                   ":terms", ["capacity"]]],
              ["semantics", "mass", "display", "capacity"],
              ["assumes",
                  ["img1", "case dia ~46mm from photo proportions",
                   ":bounds", bnd(("dia_mm", ">=", 42), ("dia_mm", "<=", 50)),
                   ":tier", "image-inferred"],
                  ["web1", "class GW46 46x13mm 63g 472mAh 1.3in display",
                   ":bounds", bnd(("dia_mm", ">=", 42), ("dia_mm", "<=", 50),
                                   ("mass_kg", ">=", 0.04),
                                   ("mass_kg", "<=", 0.08)),
                   ":tier", "web-sourced"],
                  ["route1", "wearable duty",
                   ":bounds", bnd(("mass_kg", ">=", 0.03),
                                   ("mass_kg", "<=", 0.09))]],
              ["guarantees",
                  ["gm", "wearable mass",
                   ":bounds", bnd(("mass_kg", "<=", 0.09))],
                  ["gd", "round display",
                   ":bounds", bnd(("display_mm", ">=", 30.0))]],
              ["budget", bnd(("mass_kg", "<=", 0.1))],
              ["forbidden", ["f1", "skin irritation", ":check", "inspection"]],
              ["not-responsible", "phone pairing app", "cellular radio"],
              ["time-scale", "mission"]]])

FLOW = {
    "case":    {"budget": bnd(("mass_kg", "<=", 0.02)),
                 "guarantees": [{"id": "gcs", "stmt": "case houses all",
                                  "bounds": bnd(("mass_kg", "<=", 0.02))}]},
    "display": {"budget": bnd(("mass_kg", "<=", 0.015)),
                 "guarantees": [{"id": "gdp", "stmt": "round display",
                                  "bounds": bnd(("display_mm", ">=", 30.0))}]},
    "pcb":     {"budget": bnd(("mass_kg", "<=", 0.01)),
                 "guarantees": [{"id": "gpc", "stmt": "compute",
                                  "bounds": bnd(("mass_kg", "<=", 0.01))}]},
    "battery": {"budget": bnd(("mass_kg", "<=", 0.02)),
                 "guarantees": [{"id": "gbt", "stmt": "energy",
                                  "bounds": bnd(("capacity_mah", ">=", 400.0))}]},
    "crown":   {"budget": bnd(("mass_kg", "<=", 0.005)),
                 "guarantees": [{"id": "gcr", "stmt": "side control",
                                  "bounds": bnd(("mass_kg", "<=", 0.005))}]},
    "strap-l": {"budget": bnd(("mass_kg", "<=", 0.015)),
                 "guarantees": [{"id": "gsl", "stmt": "left strap",
                                  "bounds": bnd(("mass_kg", "<=", 0.015))}]},
    "strap-r": {"budget": bnd(("mass_kg", "<=", 0.015)),
                 "guarantees": [{"id": "gsr", "stmt": "right strap",
                                  "bounds": bnd(("mass_kg", "<=", 0.015))}]},
}

F.append(["refine", "e3", ":in", ["sw45"], ":out", "sw45-v1",
          ":role", "System",
          ":transform", ["decompose",
              ":into", ["case", "display", "pcb", "battery", "crown",
                         "strap-l", "strap-r"],
              ":flow-down", FLOW]])

# case: outer prism, cavity prism, cut, print
F.append(sk("e4", "sw45-v1/case", "case-outer-sk", ngon("c", 23.0)))
F.append(["refine", "e5", ":in", ["case-outer-sk"], ":out", "case-outer",
          ":role", "Part", ":kind", "case",
          ":transform", ["extrude", ":height", 13,
                          ":material", "aluminum"]])
F.append(sk("e6", "sw45-v1/case", "case-cut-sk", ngon("k", 21.5)))
F.append(["refine", "e7", ":in", ["case-cut-sk"], ":out", "case-cutter",
          ":role", "Part", ":kind", "cavity",
          ":transform", ["extrude", ":height", 11.5, ":material", "pla",
                          ":at", [0, 0, 1.5]]])
F.append(["refine", "e8", ":in", ["case-outer", "case-cutter"],
          ":out", "case-hollow", ":role", "Part", ":kind", "case",
          ":transform", ["cut"]])
F.append(["print", "e9", ":in", ["case-hollow"],
          ":printer", "reference-printer", ":out", "case-printed"])

# catalog electronics
F.append(["exact", "e10", ":target", "sw45-v1/display", ":from", "catalog",
          ":match", "display_mm>=30", ":out", "display-std",
          ":at", [0, 0, 11.6]])
F.append(["exact", "e11", ":target", "sw45-v1/pcb", ":from", "catalog",
          ":match", "mass_g<=10000", ":out", "pcb-std",
          ":at", [0, 0, 9.3]])
F.append(["exact", "e12", ":target", "sw45-v1/battery", ":from", "catalog",
          ":match", "capacity_mah>=400", ":out", "battery-std",
          ":at", [-15, -12.5, 1.6]])

# crown
F.append(sk("e13", "sw45-v1/crown", "crown-sk", ngon("w", 3.0)))
F.append(["refine", "e14", ":in", ["crown-sk"], ":out", "crown-solid",
          ":role", "Part", ":kind", "crown",
          ":transform", ["extrude", ":height", 5, ":material", "aluminum",
                          ":at", [23.5, 0, 7, [0, 1, 0, 90]]]])
F.append(["print", "e15", ":in", ["crown-solid"],
          ":printer", "reference-printer", ":out", "crown-printed"])

# straps
for tag, slot, x0 in (("l", "strap-l", -115), ("r", "strap-r", 25)):
    F.append(sk(f"e16{tag}", f"sw45-v1/{slot}", f"strap-{tag}-sk",
                [["s0", 0, 0], ["s1", 90, 0], ["s2", 90, 22],
                 ["s3", 0, 22]]))
    F.append(["refine", f"e17{tag}", ":in", [f"strap-{tag}-sk"],
              ":out", f"strap-{tag}-solid", ":role", "Part",
              ":kind", "strap",
              ":transform", ["extrude", ":height", 3, ":material", "pla",
                              ":at", [x0, -11, 8]]])
    F.append(["refine", f"e17f{tag}", ":in", [f"strap-{tag}-solid"],
              ":out", f"strap-{tag}-fil", ":role", "Part", ":kind", "strap",
              ":transform", ["fillet", ":edges", "all", ":radius", 0.6]])
    F.append(["print", f"e18{tag}", ":in", [f"strap-{tag}-fil"],
              ":printer", "reference-printer",
              ":out", f"strap-{tag}-printed"])

# compose + mass
F.append(["compose", "e22", ":in",
          ["case-printed", "display-std", "pcb-std", "battery-std",
           "crown-printed", "strap-l-printed", "strap-r-printed"],
          ":out", "watch-assy", ":role", "System", ":kind", "smartwatch"])
F.append(["eval", "e40", ":target", "watch-assy", ":with", "mass-rollup",
          ":fidelity", 2,
          ":expect", bnd(("mass_kg", "<=", 0.09))])

text = HDR + "\n".join(S(f) for f in F) + "\n"
open("examples/sw45_watch.fcad", "w", encoding="utf-8", newline="\n").write(text)

from fluxkernel.interface import fcad
forms = fcad.parse(text)
print("generated; parses:", len(forms), "forms")
