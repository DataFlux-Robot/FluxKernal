def main(payload, ctx):
    g = payload.get("ground") or {}
    bbox = g.get("bbox")
    if not (bbox and g.get("construction")):
        return None                      # no grounded geometry here
    min_dim = min(abs(bbox[1][k] - bbox[0][k]) for k in range(3))
    floor = float(ctx["params"].get("min-wall-mm", 0.5))
    ok = min_dim >= floor
    return {"id": "policy:min-wall",
            "prop": f"min wall {min_dim:.3f}mm >= {floor:g}mm",
            "holds": ok,
            "detail": "" if ok else
            f"min dimension {min_dim:.3f}mm < {floor:g}mm — thicken the "
            f"thinnest feature or change the process"}
