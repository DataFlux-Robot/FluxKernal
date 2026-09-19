"""L2 plugin: 2D sketch grounding — numeric constraint solver.

A sketch in a Node.spec is a PARTIALLY-SPECIFIED design space: point coords may
be numbers or ("param", name). Grounding = solving the constraint system, i.e.
one diffusion-like collapse step. Evidence = residual + dof estimate.

Spec format:
  {"sketch": {
     "pts":   {"p0": [x, y], ...},          # x/y = number | ["param", name]
     "constraints": [ ["fix", "p0", 0, 0], ["dist", "p0", "p1", 40],
                      ["horiz", "p1", "p2"], ["vert", "p2", "p3"],
                      ["symx", "p0", "p3"], ... ] }}
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from .registry import register


def _collect_params(spec: dict) -> tuple[dict, list]:
    """Return (ground_template, param_names) from a sketch spec."""
    pts = spec["sketch"]["pts"]
    params = []
    for pname, (x, y) in pts.items():
        for v in (x, y):
            if isinstance(v, list) and v and v[0] == "param":
                if v[1] not in params:
                    params.append(v[1])
    return pts, params


def _build_points(pts_spec: dict, params: list, values: np.ndarray) -> dict:
    pval = dict(zip(params, values))
    out = {}
    for pname, (x, y) in pts_spec.items():
        def resolve(v):
            if isinstance(v, list) and v and v[0] == "param":
                return float(pval[v[1]])
            return float(v)
        out[pname] = (resolve(x), resolve(y))
    return out


def _residuals(pts: dict, constraints: list) -> list:
    res = []
    for c in constraints:
        kind = c[0]
        if kind == "fix":
            _, p, x, y = c
            res += [pts[p][0] - x, pts[p][1] - y]
        elif kind == "dist":
            _, a, b, d = c
            dx, dy = pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]
            res.append(np.hypot(dx, dy) - d)
        elif kind == "horiz":
            _, a, b = c
            res.append(pts[a][1] - pts[b][1])
        elif kind == "vert":
            _, a, b = c
            res.append(pts[a][0] - pts[b][0])
        elif kind == "symx":   # symmetric about x=0
            _, a, b = c
            res += [pts[a][0] + pts[b][0], pts[a][1] - pts[b][1]]
        else:
            raise ValueError(f"unknown constraint: {kind}")
    return res


@register("ground-sketch")
def ground_sketch(node_specs: list[dict], args: dict, ctx) -> tuple[dict, list, list]:
    """Plugin contract: (input node specs, transform args, ctx)
       -> (node_fields, evidence, obligations)"""
    spec = node_specs[0]["spec"] if node_specs else args.get("sketch", {})
    if "sketch" not in spec and "sketch" in args:
        spec = {"sketch": args["sketch"]}
    pts_spec, params = _collect_params(spec)
    constraints = spec["sketch"].get("constraints", [])

    x0 = np.array([args.get("init", {}).get(p, 10.0) for p in params], dtype=float)
    n_eq = sum(2 if c[0] in ("fix", "symx") else 1 for c in constraints)
    dof = 2 * len(pts_spec) - n_eq

    if len(params) == 0:
        # fully concrete sketch: no solving, just verify the constraints
        grounded = _build_points(pts_spec, params, x0)
        residual = float(np.linalg.norm(np.asarray(
            _residuals(grounded, constraints), dtype=float)))
        converged = residual < 1e-6
        sol_x = x0
    else:
        def fun(v):
            return _residuals(_build_points(pts_spec, params, v), constraints)

        sol = least_squares(fun, x0, method="lm" if n_eq >= len(params) else "trf")
        residual = float(np.linalg.norm(sol.fun))
        grounded = _build_points(pts_spec, params, sol.x)
        converged = bool(sol.success) and residual < 1e-6
        sol_x = sol.x

    fields = {"kind": "sketch",
              "spec": {"sketch": {"pts": {k: list(v) for k, v in grounded.items()},
                                  "constraints": constraints}},
              "params": dict(zip(params, map(float, sol_x))),
              "ground": {"type": "sketch2d",
                         "points": {k: list(v) for k, v in grounded.items()}}}
    evidence = [{"solver": "sketch2d/least_squares", "converged": converged,
                 "residual": residual, "dof_estimate": dof,
                 "params": dict(zip(params, map(float, sol_x)))}]
    obligations = [
        {"id": "solver-converged", "prop": "sketch constraint system grounded",
         "holds": converged, "checker": "sketch2d",
         "detail": f"residual={residual:.2e} dof={dof}"},
    ]
    return fields, evidence, obligations
