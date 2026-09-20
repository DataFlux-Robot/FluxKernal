"""NACA 4-digit airfoil sections — the shared generator of the mechanism
library (wingbox v3 skins/ribs, empennage lofts).

Convention: the returned loop is ORDERED (trailing edge -> upper ->
leading edge -> lower -> trailing edge) so it feeds straight into polygon
sketches and G2 lofts; y is the half-thickness direction, centered on
the camber line.  The TE-coefficient (-0.1036) closes the trailing edge.
"""
from __future__ import annotations

import math


def naca4(chord: float, tc: float = 0.12, camber: float = 0.02,
          n: int = 24) -> list[tuple[float, float]]:
    """Ordered airfoil loop; cosine spacing, 2n points."""
    def yt(x):
        return 5.0 * tc * (0.2969 * math.sqrt(x) - 0.1260 * x
                           - 0.3516 * x * x + 0.2843 * x ** 3
                           - 0.1036 * x ** 4)

    def yc(x):
        if camber <= 1e-9:
            return 0.0
        p = 0.4
        m = camber
        if x < p:
            return m / (p * p) * (2 * p * x - x * x)
        return m / ((1 - p) ** 2) * ((1 - 2 * p) + 2 * p * x - x * x)

    te = 1.0 - 0.004          # blunt trailing edge (0.4% chord) — a
    # knife-edge TE makes the ruled loft an INVALID solid (zero-angle
    # wedge); every manufactured airfoil is blunt there anyway
    xs = [0.5 * (1.0 - math.cos(math.pi * i / n)) for i in range(n + 1)]
    loop = []
    for x in reversed(xs):                     # TE -> LE over the upper side
        if x > te:
            continue
        loop.append((x * chord, (yc(x) + yt(x)) * chord))
    for x in xs[1:]:                           # past LE -> TE, lower side
        if x > te:
            continue
        loop.append((x * chord, (yc(x) - yt(x)) * chord))
    loop.append((te * chord, yc(1.0) * chord))          # blunt TE centre
    return loop


def half_thickness(chord: float, tc: float, camber: float,
                   frac: float) -> float:
    """Local section height (2*yt) at chord fraction frac (0..1)."""
    x = min(max(frac, 0.0), 1.0)
    t = 5.0 * tc * (0.2969 * math.sqrt(x) - 0.1260 * x
                    - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1036 * x ** 4)
    return 2.0 * t * chord


def loop_area(loop) -> float:
    """Shoelace area (mass estimates from the actual profile)."""
    a = 0.0
    for i in range(len(loop)):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % len(loop)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def inset_loop(loop, wall: float):
    """Offset a closed polygon inward by `wall` along local normals
    (per-vertex average of adjacent edge normals).  For airfoil-class
    loops with leading-edge radius >> wall this is a faithful inner
    surface for skin/tube walls."""
    n = len(loop)
    # signed area decides which side is interior
    a = 0.0
    for i in range(n):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    sgn = 1.0 if a > 0 else -1.0
    out = []
    for i in range(n):
        px, py = loop[(i - 1) % n]
        cx, cy = loop[i]
        nx, ny = loop[(i + 1) % n]
        e1 = (cx - px, cy - py)
        e2 = (nx - cx, ny - cy)
        l1 = math.hypot(*e1) or 1.0
        l2 = math.hypot(*e2) or 1.0
        # inward normal (CCW loop: rotate dir by +90 deg, i.e. (-dy, dx))
        n1 = (-e1[1] / l1 * sgn, e1[0] / l1 * sgn)
        n2 = (-e2[1] / l2 * sgn, e2[0] / l2 * sgn)
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        ml = math.hypot(mx, my) or 1.0
        # plain averaged-normal shift: no miter magnification, so sharp
        # corners (the trailing edge) can never self-intersect; the wall
        # runs marginally thin right at the TE apex, which is bonded
        out.append((cx + mx / ml * wall, cy + my / ml * wall))
    return out


def camber_at(x: float, camber: float, p: float = 0.4) -> float:
    """Camber-line ordinate at chord fraction x (dimensionless)."""
    if camber <= 1e-9:
        return 0.0
    if x < p:
        return camber / (p * p) * (2 * p * x - x * x)
    return camber / ((1 - p) ** 2) * ((1 - 2 * p) + 2 * p * x - x * x)
