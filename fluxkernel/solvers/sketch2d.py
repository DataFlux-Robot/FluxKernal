"""L2 plugin: 2D sketch grounding — numeric constraint solver (G1).

Entities: named points (as before) + edges (line/arc/spline) forming the
outer loop + circles (hole or outer).  Constraints (12): the original five
(fix/dist/horiz/vert/symx) plus parallel/perp/angle/tangent/equal/
coincident/horiz-dist/vert-dist.  Circle radii given as unresolved param
holes join the solver's unknown vector.

Everything stays on the numeric `_residuals` channel — no symbolic
reasoning, honest convergence evidence, `fully-constrained` as a soft
obligation (dof == 0; mechanisms may promote it to hard).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import least_squares

from .registry import register


def _collect_params(spec: dict) -> tuple[dict, list]:
    """Return (ground_template, param_names) from a sketch spec — point
    coordinates AND free circle radii both count as holes."""
    sk = spec["sketch"]
    pts = sk.get("pts", {})
    params = []
    for pname, xy in pts.items():
        for v in xy:
            if isinstance(v, list) and v and v[0] == "param":
                if v[1] not in params:
                    params.append(v[1])
    for circ in sk.get("circles", []) or []:
        r = circ.get("r")
        if isinstance(r, list) and r and r[0] == "param":
            if r[1] not in params:
                params.append(r[1])
    return pts, params


def _build_points(pts_spec: dict, params: list, values) -> dict:
    pval = dict(zip(params, map(float, values)))
    resolve = lambda v: float(pval[v[1]]) if isinstance(v, (list, tuple)) \
        and v and v[0] == "param" else float(v)
    return {k: (resolve(xy[0]), resolve(xy[1])) for k, xy in pts_spec.items()}


def _residuals(pts: dict, constraints: list, radii: dict | None = None) -> list:
    """radii: circle-name -> radius value (resolved or current guess)."""
    radii = radii or {}

    def R(cname):
        if cname not in radii:
            raise ValueError(f"constraint needs circle {cname!r} radius")
        return radii[cname]

    def sub(a, b):
        return pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]

    def vlen(dx, dy):
        return math.hypot(dx, dy) or 1e-12

    res = []
    for c in constraints:
        kind = c[0]
        if kind == "fix":
            _, p, x, y = c
            res += [pts[p][0] - x, pts[p][1] - y]
        elif kind == "dist":
            _, a, b, d = c
            dx, dy = sub(a, b)
            res.append(math.hypot(dx, dy) - d)
        elif kind == "horiz":
            _, a, b = c
            res.append(pts[a][1] - pts[b][1])
        elif kind == "vert":
            _, a, b = c
            res.append(pts[a][0] - pts[b][0])
        elif kind == "symx":   # symmetric about x=0
            _, a, b = c
            res += [pts[a][0] + pts[b][0], pts[a][1] - pts[b][1]]
        # ---- G1 additions (numeric channel, same tolerance discipline) ----
        elif kind == "coincident":
            _, a, b = c
            res += [pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]]
        elif kind == "parallel":                 # ab ∥ cd → cross ≈ 0
            _, a, b, cc, d = c
            abx, aby = sub(a, b)
            cdx, cdy = sub(cc, d)
            res.append((abx * cdy - aby * cdx) / (vlen(abx, aby) * vlen(cdx, cdy)))
        elif kind == "perp":                     # ab ⟂ cd → dot/(|·|) ≈ 0
            _, a, b, cc, d = c
            abx, aby = sub(a, b)
            cdx, cdy = sub(cc, d)
            res.append((abx * cdx + aby * cdy) / (vlen(abx, aby) * vlen(cdx, cdy)))
        elif kind == "angle":                    # angle(ab, cd) = deg
            _, a, b, cc, d, deg = c
            abx, aby = sub(a, b)
            cdx, cdy = sub(cc, d)
            cos1 = (abx * cdx + aby * cdy) / (vlen(abx, aby) * vlen(cdx, cdy))
            res.append(cos1 - math.cos(math.radians(float(deg))))
        elif kind == "equal":                    # |ab| = |cd|
            _, a, b, cc, d = c
            abx, aby = sub(a, b)
            cdx, cdy = sub(cc, d)
            res.append(vlen(abx, aby) - vlen(cdx, cdy))
        elif kind == "hdist":                    # xa - xb = d
            _, a, b, d = c
            res.append((pts[a][0] - pts[b][0]) - float(d))
        elif kind == "vdist":                    # ya - yb = d
            _, a, b, d = c
            res.append((pts[a][1] - pts[b][1]) - float(d))
        elif kind == "tangent":                  # line ab tangent to circle
            _, a, b, cname = c
            ax, ay = pts[a]
            bx, by = pts[b]
            cx, cy = pts[cname]
            dx, dy = bx - ax, by - ay
            L = vlen(dx, dy)
            dist = abs((cx - ax) * dy - (cy - ay) * dx) / L
            res.append(dist - R(cname))
        else:
            raise ValueError(f"unknown constraint: {kind}")
    return res


_EQS_PER = {"fix": 2, "symx": 2, "coincident": 2}


@register("ground-sketch")
def ground_sketch(node_specs: list[dict], args: dict, ctx) -> tuple[dict, list, list]:
    """Plugin contract: (input node specs, transform args, ctx)
       -> (node_fields, evidence, obligations)"""
    spec = node_specs[0].get("spec", {}) if node_specs else {}
    if "sketch" not in spec:
        arg_sk = args.get("sketch", {})
        # the elaborator may hand us {"sketch": {...}} or the bare sketch body
        spec = arg_sk if isinstance(arg_sk, dict) and "sketch" in arg_sk \
            else {"sketch": arg_sk}
    pts_spec, params = _collect_params(spec)
    sk = spec["sketch"]
    constraints = sk.get("constraints", [])
    edges = sk.get("edges", []) or []
    circles = sk.get("circles", []) or []

    # circle radii: concrete numbers stay fixed; param holes join the solve
    fixed_radii = {}
    free_circle_names = []
    for circ in circles:
        r = circ.get("r")
        name = circ.get("c") or circ.get("name", "?")
        if isinstance(r, (int, float)):
            fixed_radii[name] = float(r)
        else:
            free_circle_names.append(name)

    n_unknown = len(params) + len(free_circle_names)
    x0 = np.array([args.get("init", {}).get(p, 10.0) for p in params]
                  + [args.get("init", {}).get(f"r:{n}", 10.0)
                     for n in free_circle_names], dtype=float)
    n_eq = sum(_EQS_PER.get(c[0], 1) for c in constraints)
    dof = 2 * len(pts_spec) + len(free_circle_names) - n_eq

    def split(v):
        return dict(zip(params, map(float, v[:len(params)]))), \
            dict(zip(free_circle_names,
                     map(float, v[len(params):])))

    if n_unknown == 0:
        # fully concrete sketch: no solving, just verify the constraints
        grounded = _build_points(pts_spec, params, x0)
        residual = float(np.linalg.norm(np.asarray(
            _residuals(grounded, constraints, fixed_radii), dtype=float)))
        converged = residual < 1e-6
        sol_x = x0
    else:
        def fun(v):
            pvals, rvals = split(v)
            pts = _build_points(pts_spec, params, v[:len(params)])
            return _residuals(pts, constraints, {**fixed_radii, **rvals})

        sol = least_squares(fun, x0, method="lm" if n_eq >= n_unknown else "trf")
        residual = float(np.linalg.norm(sol.fun))
        grounded = _build_points(pts_spec, params, sol.x[:len(params)])
        converged = bool(sol.success) and residual < 1e-6
        sol_x = sol.x
        pvals, rvals = split(sol.x)
        fixed_radii.update(rvals)

    out_edges = [dict(e) for e in edges]
    out_circles = []
    for circ in circles:
        c = dict(circ)
        c["r"] = fixed_radii.get(c.get("c") or c.get("name", "?"),
                                 c.get("r") if isinstance(c.get("r"), (int, float))
                                 else None)
        out_circles.append(c)

    fields = {"kind": "sketch",
              "spec": {"sketch": {"pts": {k: list(v) for k, v in grounded.items()},
                                  "edges": out_edges,
                                  "circles": out_circles,
                                  "constraints": constraints}},
              "params": dict(zip(params, map(float, sol_x[:len(params)]))),
              "ground": {"type": "sketch2d",
                         "points": {k: list(v) for k, v in grounded.items()},
                         "edges": out_edges,
                         "circles": out_circles}}
    evidence = [{"solver": "sketch2d/constraints", "tier": 0,
                 "converged": converged, "residual": residual,
                 "dof": dof, "dof_estimate": dof,
                 "params": dict(zip(params, map(float, sol_x)))}]
    obligations = [{"id": "solver-converged", "prop": "constraint residual < 1e-6",
                    "holds": converged, "checker": "sketch2d",
                    "detail": "" if converged else f"residual={residual:.2e}"}]
    # fully-constrained: soft by default (mechanisms may demand dof == 0)
    obligations.append({"id": "fully-constrained",
                        "prop": "sketch dof == 0",
                        "holds": dof == 0, "checker": "sketch2d",
                        "class": "soft",
                        "detail": "" if dof == 0 else
                        f"dof={dof} free ({len(params)} params, "
                        f"{len(free_circle_names)} radii)"})
    return fields, evidence, obligations
