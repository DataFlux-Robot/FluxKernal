"""L2 plugins: per-layer simulator matrix (evolution plan E2).

Each plugin is an honestly-tiered heuristic (no CFD/FEA): tier 1 = first
order physics estimate, tier 2 = aggregated geometry bookkeeping.  The
point is that every role layer can produce *checkable* evidence, not that
any single number is high-fidelity.  All formulas are written out so a
reviewer can recompute them by hand.
"""
from __future__ import annotations

import math

from .registry import register

RHO_SL = 1.225          # kg/m^3, sea level ISA
G = 9.81                # m/s^2


def _pval(node, args, key, default):
    """params value -> args override -> spec.param_bounds midpoint -> default."""
    ov = args.get("overrides") or {}
    if key in ov:
        return float(ov[key])
    p = (node.get("params") or {}) if node else {}
    v = p.get(key)
    if isinstance(v, (list, tuple)) and v and v[0] == "param":
        pb = ((node.get("spec") or {}).get("param_bounds") or {}).get(key) or {}
        try:
            lo = float(pb.get(">=", default * 0.5)) if isinstance(pb, dict) \
                else default * 0.5
            hi = float(pb.get("<=", default * 1.5)) if isinstance(pb, dict) \
                else default * 1.5
            return (lo + hi) / 2.0
        except (TypeError, ValueError):
            return default
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- aero ----
@register("aero-2d")
def aero_2d(node_specs, args, ctx):
    """Wing-level aero estimate (tier 1).  Drag polar with Oswald efficiency:

        CL  = 2 * m * g / (rho * v^2 * S)
        CDi = CL^2 / (pi * AR * e)
        L/D = CL / (CD0 + CDi)

    Inputs: ar, s_m2, mass_kg, cruise_ms, cd0, e (params, then args, then
    defaults tuned to the SHA-PEK case)."""
    s0 = node_specs[0] if node_specs else {}
    ar = _pval(s0, args, "ar", 14.0)
    area = _pval(s0, args, "s_m2", 3.5)
    m = _pval(s0, args, "mass_kg", 1200.0)
    v = _pval(s0, args, "cruise_ms", 95.0)
    cd0 = _pval(s0, args, "cd0", 0.028)
    e = _pval(s0, args, "e", 0.85)

    q = 0.5 * RHO_SL * v * v
    cl = (m * G) / (q * area) if q * area > 0 else 0.0
    cdi = cl * cl / (math.pi * ar * e)
    cd = cd0 + cdi
    ld = cl / cd if cd > 0 else 0.0
    fidelity = int(args.get("fidelity", 1))
    evidence = [{"solver": "aero/2d", "tier": fidelity,
                 "ld_ratio": round(ld, 2), "cl_cruise": round(cl, 4),
                 "cdi": round(cdi, 5), "cd_total": round(cd, 5),
                 "ar": ar, "s_m2": area, "cruise_ms": v}]
    obligations = [{"id": "aero-computed", "prop": "L/D estimated from polar",
                    "holds": ld > 0, "checker": "aero-2d",
                    "detail": f"L/D={ld:.2f} CL={cl:.3f}"}]
    return {}, evidence, obligations


# ------------------------------------------------------------ propulsion --
@register("prop-map")
def prop_map(node_specs, args, ctx):
    """Electric propulsion mapping (tier 1).  Ideal actuator disk (static):

        P   = tau * omega                       (shaft power)
        T   = (2 rho A)^(1/3) * P_eta^(2/3)      (static thrust, A = pi d^2/4)
        I   = P / (eff * V_bus)                  (bus current)

    Inputs: torque_nm, rpm, prop_d_m, eff, bus_v."""
    s0 = node_specs[0] if node_specs else {}
    tau = _pval(s0, args, "torque_nm", 8.0)
    rpm = _pval(s0, args, "rpm", 12000.0)
    d = _pval(s0, args, "prop_d_m", 0.5)
    eff = _pval(s0, args, "eff", 0.7)
    bus_v = _pval(s0, args, "bus_v", 48.0)

    omega = rpm * 2.0 * math.pi / 60.0
    p = tau * omega
    a = math.pi * d * d / 4.0
    p_eta = p * eff
    thrust = (2.0 * RHO_SL * a) ** (1.0 / 3.0) * p_eta ** (2.0 / 3.0)
    current = p / (eff * bus_v) if eff * bus_v > 0 else 0.0
    fidelity = int(args.get("fidelity", 1))
    evidence = [{"solver": "prop/map", "tier": fidelity,
                 "thrust_n": round(thrust, 2), "shaft_w": round(p, 1),
                 "current_a": round(current, 2), "rpm": rpm,
                 "torque_nm": tau, "prop_d_m": d}]
    obligations = [{"id": "prop-mapped", "prop": "thrust/current mapped",
                    "holds": thrust > 0, "checker": "prop-map",
                    "detail": f"T={thrust:.1f}N I={current:.1f}A"}]
    return {}, evidence, obligations


# ----------------------------------------------------------- structure ----
@register("beam-fe")
def beam_fe(node_specs, args, ctx):
    """Plate/beam bending estimate (tier 1).  Rectangular section from the
    grounded bbox, simply-supported centre load:

        I     = b * h^3 / 12                    (b = thickness, h = height)
        sigma = M * c / I                       (c = h/2)
        delta = F * L^3 / (48 E I)

    Load F defaults from the guarantee bound bending_knm (kN*m) treated as
    the limit moment arm at mid-span; yield stress by material."""
    s0 = node_specs[0] if node_specs else {}
    g = (s0.get("ground") or {})
    bbox = g.get("bbox") or [[0, 0, 0], [10, 10, 10]]
    dims = sorted((abs(bbox[1][k] - bbox[0][k]) for k in range(3)), reverse=True)
    length, height, thick = dims[0], dims[1], dims[2]
    material = str(g.get("material") or "pla").lower()
    E = {"pla": 3.5e3, "aluminum": 69e3, "steel": 200e3}.get(material, 3.5e3)  # MPa
    yield_mpa = {"pla": 60.0, "aluminum": 240.0, "steel": 350.0}.get(material, 60.0)

    # limit moment from the contract if declared (kN*m) — informational
    m_knm = None
    for slot in ("guarantees", "goals"):
        for entry in (s0.get("spec") or {}).get(slot) or []:
            b = (entry.get("bounds") or {}).get("bending_knm")
            if b:
                try:
                    m_knm = float(b.get("<=") if isinstance(b, dict) else b[1])
                    break
                except (TypeError, ValueError, KeyError):
                    pass
        if m_knm is not None:
            break
    # test load: explicit args, else a span-scaled heuristic (~0.5 N/mm)
    f_n = float(args.get("load_n", max(20.0, 0.5 * length)))

    i_mm4 = thick * height ** 3 / 12.0
    c = height / 2.0
    m_nmm = f_n * length / 4.0            # simply supported, centre load
    sigma = m_nmm * c / i_mm4 if i_mm4 > 0 else float("inf")
    delta = f_n * length ** 3 / (48.0 * E * i_mm4) if i_mm4 > 0 else float("inf")

    fidelity = int(args.get("fidelity", 1))
    ev = {"solver": "beam/plate", "tier": fidelity,
          "i_mm4": round(i_mm4, 1), "stress_mpa": round(sigma, 3),
          "deflection_mm": round(delta, 4), "yield_mpa": yield_mpa,
          "length_mm": length, "height_mm": height, "thick_mm": thick,
          "material": material, "load_n": round(f_n, 1),
          "moment_nmm": round(m_nmm, 1)}
    if m_knm is not None:
        ev["limit_moment_knm"] = m_knm
    evidence = [ev]
    obligations = [
        {"id": "stress-ok", "prop": f"sigma {sigma:.1f} <= yield {yield_mpa}",
         "holds": sigma <= yield_mpa, "checker": "beam-fe",
         "detail": f"sigma={sigma:.1f}MPa vs {material} yield {yield_mpa}MPa"},
        {"id": "deflection-ok",
         "prop": f"delta {delta:.2f}mm <= span/150 ({length / 150:.1f}mm)",
         "holds": delta <= length / 150.0, "checker": "beam-fe",
         "detail": f"delta={delta:.2f}mm"},
    ]
    return {}, evidence, obligations


# ----------------------------------------------------------- assembly -----
@register("mass-rollup")
def mass_rollup(node_specs, args, ctx):
    """Assembly mass bookkeeping (tier 2): total mass, centre of mass and a
    box-approximation inertia tensor (per-part I_cm from bbox dimensions +
    parallel axis to the assembly COM)."""
    total = 0.0
    mx = my = mz = 0.0
    parts = 0
    for s in node_specs:
        g = (s.get("ground") or {})
        m = float(g.get("mass_g") or 0.0)
        if m <= 0:
            continue
        com = g.get("com") or [0.0, 0.0, 0.0]
        bbox = g.get("bbox") or [[0, 0, 0], [1, 1, 1]]
        dims = [abs(bbox[1][k] - bbox[0][k]) for k in range(3)]
        total += m
        mx += m * com[0]
        my += m * com[1]
        mz += m * com[2]
        parts += 1
        # stash per-part dims+com for the inertia pass
        s["_mr"] = (m, com, dims)
    if total <= 0:
        raise ValueError("mass-rollup needs grounded parts with mass_g")
    com = [mx / total, my / total, mz / total]
    izz = 0.0
    for s in node_specs:
        info = s.pop("_mr", None)
        if not info:
            continue
        m, pcom, dims = info
        # box inertia about own COM (z axis): m/12 * (dx^2 + dy^2)
        izz += m / 12.0 * (dims[0] ** 2 + dims[1] ** 2)
        # parallel axis to assembly COM (mm offsets)
        izz += m * ((pcom[0] - com[0]) ** 2 + (pcom[1] - com[1]) ** 2)

    fidelity = int(args.get("fidelity", 2))
    evidence = [{"solver": "mass/rollup", "tier": fidelity,
                 "mass_g": round(total, 2), "mass_kg": round(total / 1000.0, 3),
                 "com_mm": [round(c, 2) for c in com],
                 "izz_gmm2": round(izz, 1), "parts": parts}]
    obligations = [{"id": "mass-accounted",
                    "prop": f"{parts} grounded parts, {total:.0f} g total",
                    "holds": True, "checker": "mass-rollup",
                    "detail": f"mass={total:.1f}g"}]
    return {}, evidence, obligations
