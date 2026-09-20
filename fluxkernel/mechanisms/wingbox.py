"""Mechanism: wingbox 2.0 — layout, generators, compose recipe.

Every coordinate is COMPUTED from the parameters; nothing hand-placed.
Layout model (X=span, Y=chord, Z=height):
  - two skins (span x chord-2*edge) closing top/bottom
  - front/rear spars (webs) at 25% / 75% chord, stood upright
  - rib-1..N webs BETWEEN the spars at even span stations
  - rib-1 is reserved for downstream machining (termination: reserve)
"""
from __future__ import annotations

import math

T_SKIN = 2.0
T_SPAR = 30.0
T_RIB = 3.0
EDGE = 10.0            # chord-wise inset of the skins
SPAR_FRAC = (0.26, 0.76)   # spar centre positions as chord fractions
MARGIN = 1.3           # budget headroom over computed mass


def layout(p: dict) -> dict:
    """Named frames for every part — computed, deterministic."""
    span = float(p["span"])
    chord = float(p["chord"])
    height = float(p["height"])
    n = int(round(float(p["rib-count"])))
    if n < 1:
        raise ValueError(f"rib-count {n} < 1")
    pitch = span / n
    sf, sr = SPAR_FRAC[0] * chord, SPAR_FRAC[1] * chord
    rib_chord = sr - sf - T_SPAR          # between the spar inner faces
    rib_h = height - 2 * T_SKIN - 8
    web_h = height - 2 * T_SKIN
    frames = {
        "skin-upper": [[0, EDGE, height - T_SKIN]],
        "skin-lower": [[0, EDGE, 0]],
        # spar web drawn in local XY (span x web_h), stood by +90° about X
        "spar-front": [[0, sf + T_SPAR / 2, T_SKIN], [1, 0, 0, 90]],
        "spar-rear": [[0, sr + T_SPAR / 2, T_SKIN], [1, 0, 0, 90]],
    }
    for i in range(1, n + 1):
        # rib web drawn in local XY (rib_chord x rib_h), rotated by the
        # cyclic permutation (1,1,1)120° so it stands across the chord
        frames[f"rib-{i}"] = [[i * pitch - T_RIB / 2, sf + T_SPAR / 2,
                               T_SKIN + 4], [1, 1, 1, 120]]
    return frames


def profile(p: dict, part: str) -> dict:
    """Sketch profile + extrusion parameters for one part."""
    span = float(p["span"])
    chord = float(p["chord"])
    n = int(round(float(p["rib-count"])))
    pitch = span / n
    sf, sr = SPAR_FRAC[0] * chord, SPAR_FRAC[1] * chord
    rib_chord = sr - sf - T_SPAR
    web_h = float(p["height"]) - 2 * T_SKIN
    rib_h = web_h - 8
    if part.startswith("skin"):
        w, h = span, chord - 2 * EDGE
        thick = T_SKIN
    elif part.startswith("spar"):
        w, h = span, web_h
        thick = T_SPAR
    elif part.startswith("rib"):
        w, h = rib_chord, rib_h
        thick = T_RIB
    else:
        raise ValueError(f"wingbox has no part {part!r}")
    return {"w": w, "h": h, "thick": thick, "material": "aluminum"}


def mass_kg(p: dict, part: str) -> float:
    pr = profile(p, part)
    return pr["w"] * pr["h"] * pr["thick"] * 2.7e-3 / 1000.0


def generate(p: dict) -> dict:
    """Per-part geometry descriptors + flow-down budgets (whole family)."""
    n = int(round(float(p["rib-count"])))
    into = ["skin-upper", "skin-lower", "spar-front", "spar-rear"] + \
        [f"rib-{i}" for i in range(1, n + 1)]
    parts = {}
    flow = {}
    for name in into:
        pr = profile(p, name)
        parts[name] = pr
        flow[name] = {
            "budget": {"mass_kg": ["<=", math.ceil(mass_kg(p, name) * MARGIN)]},
            "guarantees": [{"id": f"g-{name}", "stmt": f"{name} carries load",
                            "bounds": {"mass_kg": ["<=",
                                        math.ceil(mass_kg(p, name) * MARGIN)]}}],
        }
    return {"into": into, "parts": parts, "flow_down": flow,
            "roles": {k: "Part" for k in into},
            "kinds": {("skin-panel" if k.startswith("skin") else
                       "spar" if k.startswith("spar") else "rib"): None
                      for k in []},  # placeholder, filled below
            }


def kinds_of(into: list) -> dict:
    out = {}
    for k in into:
        out[k] = ("skin-panel" if k.startswith("skin") else
                  "spar" if k.startswith("spar") else "rib")
    return out


def assemble(p: dict) -> dict:
    """Compose recipe: children are world-grounded at their frames —
    identity placements through the real interference gate."""
    n = int(round(float(p["rib-count"])))
    count = 4 + n
    return {"transform": {"name": "assemble",
                          "args": {"placements": [[0, 0, 0]] * count}},
            "out_kind": "wing-assembly"}


DEFAULT_PARAMS = {"t-skin": T_SKIN, "t-spar": T_SPAR, "t-rib": T_RIB}
RESERVE = ["rib-1"]      # left open for downstream machining
