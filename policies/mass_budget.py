def main(payload, ctx):
    spec = payload.get("spec") or {}
    b = (spec.get("budget") or {}).get("mass_kg")
    g = payload.get("ground") or {}
    mass_kg = g.get("mass_g")
    if b is None or mass_kg is None:
        return None                      # nothing to cross-check
    hi = b.get("hi", b.get("<=")) if isinstance(b, dict) else (
        b[1] if isinstance(b, (list, tuple)) and len(b) == 2 else None)
    if hi is None:
        return None
    m = float(mass_kg) / 1000.0
    ok = m <= float(hi) + 1e-9
    return {"id": "policy:mass-budget",
            "prop": f"mass {m:.3f}kg <= budget {float(hi):g}kg",
            "holds": ok,
            "detail": "" if ok else
            f"mass {m:.3f}kg exceeds budget {float(hi):g}kg by "
            f"{m - float(hi):.3f}kg — lighten children or renegotiate the "
            f"budget at the flow-down source"}
