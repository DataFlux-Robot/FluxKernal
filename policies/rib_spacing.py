def main(payload, ctx):
    p = ctx["params"]
    span = p.get("span")
    n = p.get("rib-count")
    if not span or not n:
        return None                      # not this family's business
    pitch = float(span) / float(n)
    ok = pitch <= 500.0 + 1e-9
    hint = "" if ok else (
        f"pitch {pitch:g}mm > 500mm — increase rib-count to at least "
        f"{int(-(-float(span) // 500)) + (1 if float(span) % 500 == 0 else 0)}"
        f" or reduce span")
    return {"id": "policy:rib-spacing",
            "prop": f"rib pitch {pitch:g} <= 500mm",
            "holds": ok, "detail": hint}
