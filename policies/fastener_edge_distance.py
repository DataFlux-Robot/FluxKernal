def main(payload, ctx):
    """Holes declared on the sketch carry :edge (distance to nearest edge,
    mm) — 2d rule per fastener diameter d."""
    g = payload.get("ground") or {}
    holes = (g.get("circles") or [])
    checked = [h for h in holes if h.get("edge") is not None and not h.get("hole") is False]
    checked = [h for h in checked if h.get("hole")]
    if not checked:
        return None
    bad = []
    for h in checked:
        d = 2.0 * float(h["r"])
        if float(h["edge"]) < d - 1e-9:
            bad.append(f"{h['c']}: edge {float(h['edge']):g} < 2d {d:g}")
    return {"id": "policy:fastener-edge-distance",
            "prop": f"{len(checked)} hole(s) satisfy edge >= 2d",
            "holds": not bad,
            "detail": "; ".join(bad) if bad else ""}
