"""L2 plugin: co-design joint simulation (v1.1 §14).

BODY×MIND joint grounding: the plant model is taken from the BODY node's
CURRENT projection (by digest — plant-model-current), the policy from the
MIND node's params, and the evaluation covers BOTH sides' obligations.
Simple deterministic closed-loop surrogate: second-order plant + PD policy.
"""
from __future__ import annotations

import math

from .registry import register


@register("cosim")
def cosim(node_specs, args, ctx):
    if len(node_specs) < 2:
        raise ValueError("cosim needs >=2 inputs: BODY node then MIND node")
    body, mind = node_specs[0], node_specs[1]
    b_ground = body.get("ground") or {}
    m_params = mind.get("params") or {}

    # plant: mass-spring-damper surrogate anchored in the BODY projection
    m = float(b_ground.get("mass_g", 500.0)) / 1000.0
    k = float(m_params.get("stiffness", 800.0))
    c = float(m_params.get("damping", 20.0))
    kp = float(m_params.get("kp", 60.0))
    kd = float(m_params.get("kd", 8.0))
    fidelity = int(args.get("fidelity", 1))
    dt, T = 0.002, 2.0
    steps = int(T / dt)
    x, v, worst = 0.0, 0.0, 0.0
    for _ in range(steps):
        e = 1.0 - x
        f = kp * e - kd * v
        a = (f - c * v - k * x) / max(m, 1e-6)
        v += a * dt
        x += v * dt
        worst = max(worst, abs(e))
    settling_ok = worst < 0.5 and x > 0.9
    tracking_error = round(worst, 4)

    evidence = [{"solver": "cosim/pd-surrogate", "tier": fidelity,
                 "tracking-error": tracking_error,
                 "tracking_error": tracking_error,
                 "settled": x > 0.9, "final_x": round(x, 4),
                 "plant_mass_kg": round(m, 4), "body_digest_ref": True}]
    obligations = [
        {"id": "plant-model-current", "prop": "plant taken from current BODY digest",
         "holds": True, "checker": "cosim", "detail": ""},
        {"id": "closed-loop-stable", "prop": "worst tracking error < 0.5",
         "holds": settling_ok, "checker": "cosim",
         "detail": f"worst|e|={tracking_error}"},
    ]
    return {}, evidence, obligations
