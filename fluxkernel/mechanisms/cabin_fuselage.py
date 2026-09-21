"""Mechanism: cabin-fuselage — a lofted, shelled fuselage.

Replaces the five-panel box: one two-section loft (cabin section ->
contracted tail section) shelled to the wall thickness (tail tip open),
solid inset bulkheads at computed stations.  Every frame computed from
width/height/length; local frame: section XY = (width, -height down),
loft axis local Z = world +Y (aft), via rotX(-90).
"""
from __future__ import annotations

import math

WALL = 3.0
T_BH = 3.0
CLEAR = 6.0
MARGIN = 1.3


def _section(w: float, h: float, section: str = "octagon"):
    """Cross-section loop.  "rect" = plain rectangle (box trucks: vertical
    walls, flat panels); "octagon" = chamfered tube (aero bodies)."""
    if section == "rect":
        return [(-w / 2, 0.0), (w / 2, 0.0), (w / 2, -h), (-w / 2, -h)]
    return _octagon(w, h)


def _octagon(w: float, h: float, cut: float = 0.35, sides: int = 4):
    """Rounded-rectangle section (4+2*sides pts), y NEGATIVE = height
    downward (the frame's rotX(-90) maps local -y to world +z).
    sides=4 gives the classic octagon — the fuselage section.  (Lofts
    over >=12-point sections come back INVALID from OCCT and silently
    break every boolean; 8-point tapered lofts are solid.)"""
    import math as _m
    ns = max(2, sides)
    c = min(w, h) * cut * 0.5
    pts = []
    for k in range(ns + 1):          # top edge, left -> right
        pts.append((-w / 2 + c + (w - 2 * c) * k / ns, 0.0))
    for k in range(1, ns + 1):       # right edge down
        pts.append((w / 2, -c - (h - 2 * c) * k / ns))
    for k in range(1, ns + 1):       # bottom edge, right -> left
        pts.append((w / 2 - c - (w - 2 * c) * k / ns, -h))
    for k in range(1, ns):           # left edge up
        pts.append((-w / 2, -h + c + (h - 2 * c) * k / ns))
    return pts


def _interp(w0, w1, t):
    return w0 + (w1 - w0) * t


def _inset_oct(pts, wall):
    """Octagon inset by wall along local normals (same averaged-normal
    scheme as the wing skin cutter)."""
    n = len(pts)
    a = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    sgn = 1.0 if a > 0 else -1.0
    out = []
    for i in range(n):
        px, py = pts[(i - 1) % n]
        cx, cy = pts[i]
        nx, ny = pts[(i + 1) % n]
        e1 = (cx - px, cy - py)
        e2 = (nx - cx, ny - cy)
        l1 = math.hypot(*e1) or 1.0
        l2 = math.hypot(*e2) or 1.0
        m1 = (-e1[1] / l1 * sgn, e1[0] / l1 * sgn)
        m2 = (-e2[1] / l2 * sgn, e2[0] / l2 * sgn)
        mx, my = m1[0] + m2[0], m1[1] + m2[1]
        ml = math.hypot(mx, my) or 1.0
        # miter: shift along the corner bisector so the PERPENDICULAR
        # distance to each edge equals wall (cos half-angle correction),
        # capped at 2x to protect acute corners from self-intersection
        cos_half = max(0.5, mx / ml)
        out.append((cx + mx / ml * wall / cos_half,
                    cy + my / ml * wall / cos_half))
    return out


def layout(p: dict) -> dict:
    """Frames: the shell prism runs nose->tail (local z = length maps to
    world +Y via rotX(-90)); the cutter starts one wall in and overruns
    the tail so the cut leaves the tail tip open; bulkheads at stations.
    x0/y0/z0 place the mechanism's nose-centre in the aircraft frame."""
    L = float(p["length"])
    x0 = float(p.get("x0", 0.0))
    y0 = float(p.get("y0", 0.0))
    z0 = float(p.get("z0", 0.0))
    frames = {
        "shell": [[x0, y0, z0], [1, 0, 0, -90]],
        "shell-cutter": [[x0, y0 + WALL, z0], [1, 0, 0, -90]],
    }
    for i, frac in enumerate((0.12, 0.55, 0.8), start=1):
        # lift off the outer bottom surface by wall + clearance (the
        # bulkhead lives between the inner walls, not across them)
        frames[f"bh-{i}"] = [[x0, y0 + frac * L, z0 + WALL + CLEAR],
                             [1, 0, 0, -90]]
    return frames


def profile(p: dict, part: str) -> dict:
    L = float(p["length"])
    w, h = float(p["width"]), float(p["height"])
    tail_frac = float(p.get("tail-frac", 0.45))
    wt, ht = w * tail_frac, h * tail_frac
    taper_at = float(p.get("taper-start", 0.55))
    if part == "shell":
        # constant-section cabin tube: prism hollowed by an inset core
        # prism (proven primitive pair — tapered-loft booleans are NOT
        # reliable in OCCT: ruled lofts over >=8-pt sections come back
        # invalid and silently void every cut)
        section = str(p.get("section", "octagon"))
        sec = _section(w, h, section)
        if section == "rect":
            # exact analytic inset: wall is uniform by construction
            cut = [(-(w / 2 - WALL), 0.0), (w / 2 - WALL, 0.0),
                   (w / 2 - WALL, -(h - WALL)), (-(w / 2 - WALL), -(h - WALL))]
        else:
            cut = _inset_oct(sec, WALL + 0.5)
        post = []
        if section == "rect":
            # four long corners are discrete stress raisers — round them
            # on the SOLID prism before hollowing (thin-wall rims hit
            # OCCT's "only 2 faces" limit)
            post = [{"name": "fillet",
                     "args": {"edges": "all", "radius": 0.6}}]
        return {"pts": sec, "thick": L, "material": "pla",
                "post": post,
                "cutter": {"pts": cut,
                           "thick": L + 10.0 - WALL,
                           "frame": "shell-cutter"}}
    if part.startswith("bh-"):
        i = int(part.split("-")[1])
        frac = (0.12, 0.55, 0.8)[i - 1]
        # inset to the local section (tapering) minus wall + clearance
        t = frac
        wi = _interp(w, wt, t) - 2 * (WALL + CLEAR)
        hi = _interp(h, ht, t) - 2 * (WALL + CLEAR)
        sec = _section(wi, hi, str(p.get("section", "octagon")))
        return {"pts": sec, "thick": T_BH, "material": "pla",
                "post": [{"name": "fillet",
                          "args": {"edges": {"plane": "ymin"},
                                   "radius": 0.6}}]}
    raise ValueError(f"cabin-fuselage has no part {part!r}")


def _oct_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def _oct_perim(pts):
    return sum(math.dist(pts[i], pts[(i + 1) % len(pts)])
               for i in range(len(pts)))


def mass_kg(p: dict, part: str) -> float:
    L = float(p["length"])
    rho = 1.24e-3 / 1000.0
    pr = profile(p, part)
    if part == "shell":
        per = _oct_perim(_section(float(p["width"]), float(p["height"]),
                                  str(p.get("section", "octagon"))))
        return per * L * WALL * 1.24e-3 / 1000.0 * 1.15 * 1.15
    return _oct_area(pr["pts"]) * pr["thick"] * 1.24e-3 / 1000.0


def generate(p: dict) -> dict:
    into = ["shell", "bh-1", "bh-2", "bh-3"]
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
    return {k: ("fuselage-shell" if k == "shell" else "bulkhead")
            for k in into}


def assemble(p: dict) -> dict:
    return {"transform": {"name": "assemble",
                          "args": {"placements": [[0, 0, 0]] * 4}},
            "out_kind": "fuselage-assembly"}


DEFAULT_PARAMS = {"wall": WALL, "t-bh": T_BH}
