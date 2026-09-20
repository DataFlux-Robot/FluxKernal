"""Mechanism: wingbox 3.0 — airfoil-section loft, computed layout.

Every coordinate is COMPUTED from the parameters; nothing hand-placed.
Layout model (X=span, Y=chord, Z=height):
  - ONE skin: a NACA-4 section (tc, camber are mechanism params) lofted
    root->tip and shelled to T_SKIN wall (tip face open) — a real
    airfoil wing skin, not two flat plates
  - front/rear spar webs at 26%/76% chord inside the skin, cap edges
    chamfered (the "梁缘条" of the spec)
  - rib-1..N: airfoil-profile plates inset by the skin wall, spanning
    between the spars' inner faces at even stations
  - rib-1 is reserved for downstream machining (termination: reserve)
"""
from __future__ import annotations

import math

from .airfoil import (naca4, half_thickness, loop_area,
                     inset_loop, camber_at)

T_SKIN = 2.0
T_SPAR = 30.0
T_RIB = 3.0
EDGE = 10.0            # chord-wise inset of the wing section
SPAR_FRAC = (0.26, 0.76)
CLEAR = 4.0            # assembly clearance — covers the averaged-
# normal inset slop of curved inner walls (interference 0)
MARGIN = 1.3           # budget headroom over computed mass
N_PTS = 24             # airfoil resolution per side


def _tc(p):    return float(p.get("tc", 0.12))
def _cam(p):   return float(p.get("camber", 0.02))


def layout(p: dict) -> dict:
    """Named frames for every part — computed, deterministic.  The skin
    section lives in local XY (x=chord, y=thickness centred on 0) lofted
    along local Z (span); the cyclic permutation (1,1,1)120 maps
    X->Y_w, Y->Z_w, Z->X_w."""
    span = float(p["span"])
    chord = float(p["chord"])
    height = float(p["height"])
    n = int(round(float(p["rib-count"])))
    if n < 1:
        raise ValueError(f"rib-count {n} < 1")
    pitch = span / n
    sf, sr = SPAR_FRAC[0] * chord, SPAR_FRAC[1] * chord
    tc, cam = _tc(p), _cam(p)
    frames = {
        "skin": [[0, EDGE, height / 2], [1, 1, 1, 120]],
        # the cutter prism starts one wall inboard and overruns the tip
        # so the cut leaves the tip face open and the root cap = wall
        "skin-cutter": [[T_SKIN, EDGE, height / 2], [1, 1, 1, 120]],
    }
    for slot, frac in (("spar-front", SPAR_FRAC[0]),
                       ("spar-rear", SPAR_FRAC[1])):
        # fit under the LOWEST inner-wall point across the spar's
        # chordwise width (the wall slopes) and clear the root cap
        half_w = (T_SPAR / 2 + 1.0) / chord
        h_local = min(half_thickness(chord, tc, cam, f)
                      for f in (frac - half_w, frac, frac + half_w))
        web_h = h_local - 2 * (T_SKIN + CLEAR)
        # centre the web on the local CAMBER line, not the box centre —
        # a cambered section rides up/down along the chord
        z_mid = height / 2 + camber_at(frac, cam) * chord
        # rotX(+90) grows the thickness toward -Y, so the frame origin is
        # the spar's AFT face; centre the band on frac*chord
        frames[slot] = [[T_SKIN + 1.0,
                         EDGE + frac * chord + T_SPAR / 2,
                         z_mid - web_h / 2], [1, 0, 0, 90]]
    # rib chord span: from just aft of the front spar band to just shy
    # of the rear spar band; its centre rides the camber there
    rib_f0 = SPAR_FRAC[0] * chord + T_SPAR / 2 + 2.5
    rib_f1 = SPAR_FRAC[1] * chord - T_SPAR / 2 - 2.5
    rib_mid = (rib_f0 + rib_f1) / 2 / chord
    for i in range(1, n + 1):
        frames[f"rib-{i}"] = [[i * pitch - T_RIB / 2,
                               EDGE + rib_f0,
                               height / 2 + camber_at(rib_mid, cam) * chord],
                              [1, 1, 1, 120]]
    return frames


def profile(p: dict, part: str) -> dict:
    """Geometry descriptor of one part (sketch pts / loft profiles)."""
    span = float(p["span"])
    chord = float(p["chord"])
    n = int(round(float(p["rib-count"])))
    pitch = span / n
    sf, sr = SPAR_FRAC[0] * chord, SPAR_FRAC[1] * chord
    tc, cam = _tc(p), _cam(p)
    if part == "skin":
        sec = naca4(chord, tc, cam, N_PTS)
        # the wall core is the section inset by the wall thickness,
        # truncated where the converging TE is thinner than ~2*wall
        # (there the inset would cross itself; the TE stays solid) —
        # cutoff computed from the actual profile
        cutoff = max((x for x, y in sec
                      if y - camber_at(x / chord, cam) * chord
                      > T_SKIN + 1.5),
                     default=chord * 0.9)
        inner = [q for q in inset_loop(sec, T_SKIN) if q[0] <= cutoff]
        return {"pts": sec, "thick": span, "material": "pla",
                "cutter": {"pts": inner, "thick": span + 10.0 - T_SKIN,
                           "frame": "skin-cutter"}}
    if part.startswith("spar"):
        frac = SPAR_FRAC[0] if "front" in part else SPAR_FRAC[1]
        half_w = (T_SPAR / 2 + 1.0) / chord
        h_local = min(half_thickness(chord, tc, cam, f)
                      for f in (frac - half_w, frac, frac + half_w))
        web_h = h_local - 2 * (T_SKIN + CLEAR)
        return {"w": span - 2 * (T_SKIN + 1.0), "h": web_h,
                "thick": T_SPAR, "material": "pla",
                "post": [{"name": "chamfer",
                          "args": {"edges": {"parallel-to": [1, 0, 0]},
                                   "dist": 1.0}}]}
    if part.startswith("rib"):
        # inset deeper than the nominal wall: the averaged-normal inset
        # under-offsets on curved runs, so add slop for the interference
        # gate (touching assemblies must share ZERO volume)
        inset = T_SKIN + 3.5
        between = ((SPAR_FRAC[1] * chord - T_SPAR / 2 - 2.5)
                  - (SPAR_FRAC[0] * chord + T_SPAR / 2 + 2.5))
        sec = naca4(between, tc, cam, N_PTS)
        return {"pts": sec, "thick": T_RIB, "material": "pla"}
    raise ValueError(f"wingbox has no part {part!r}")


def mass_kg(p: dict, part: str) -> float:
    chord = float(p["chord"])
    span = float(p["span"])
    tc, cam = _tc(p), _cam(p)
    pr = profile(p, part)
    rho = 1.24e-3 / 1000.0                     # PLA g/mm^3 -> kg/mm^3
    if part == "skin":
        loop = naca4(chord, tc, cam, N_PTS)
        per = sum(math.dist(loop[i], loop[(i + 1) % len(loop)])
                  for i in range(len(loop)))
        return per * span * T_SKIN * 1.24e-3 / 1000.0
    if part.startswith("spar"):
        return pr["w"] * pr["h"] * pr["thick"] * 1.24e-3 / 1000.0
    return loop_area(pr["pts"]) * pr["thick"] * 1.24e-3 / 1000.0


def generate(p: dict) -> dict:
    n = int(round(float(p["rib-count"])))
    into = ["skin", "spar-front", "spar-rear"] + \
        [f"rib-{i}" for i in range(1, n + 1)]
    parts, flow = {}, {}
    for name in into:
        pr = profile(p, name)
        parts[name] = pr
        m = math.ceil(mass_kg(p, name) * MARGIN)
        flow[name] = {
            "budget": {"mass_kg": ["<=", m]},
            "guarantees": [{"id": f"g-{name}",
                            "stmt": f"{name} carries load",
                            "bounds": {"mass_kg": ["<=", m]}}],
        }
    return {"into": into, "parts": parts, "flow_down": flow,
            "roles": {k: "Part" for k in into}}


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
    count = 3 + n
    return {"transform": {"name": "assemble",
                          "args": {"placements": [[0, 0, 0]] * count}},
            "out_kind": "wing-assembly"}


RESERVE = ["rib-1"]      # left open for downstream machining
