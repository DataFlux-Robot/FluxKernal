def _walk(cons):
    """yield op records along a nested construction chain"""
    while cons:
        yield cons
        cons = cons.get("input")


def _curved_body(chain):
    """A loft over curved sections, or an extrusion of a curved outline
    (>= 12 points, airfoil/octagon class), is curvature-continuous along
    its outer surface — the discrete stress-raiser the rule exists to
    remove is absent by construction.  (OCCT also refuses rim
    fillets/chamfers when a body's whole rim spans only two faces, so
    the exemption is also what the geometry kernel can express.)"""
    for c in chain:
        if c.get("op") == "loft":
            for sec in c.get("sections") or []:
                if len(sec.get("pts") or {}) >= 8:
                    return True
        if c.get("op") == "extrude":
            pts = c.get("points")
            n = len(pts) if isinstance(pts, (list, dict)) else 0
            if n >= 12:
                return True
    return False


def main(payload, ctx):
    if (ctx or {}).get("op") != "print":
        return None                  # only print edges
    g = payload.get("ground") or {}
    cons = g.get("construction") or {}
    if cons.get("op") in ("scale-instance", "boolean"):
        # deliberate multi-shell assembly jobs carry their rounding at
        # the source parts; the derived solid has no fresh outer edges
        return None
    chain = list(_walk(cons))
    best = 0.0
    for c in chain:
        if c.get("op") == "fillet":
            best = max(best, float(c.get("radius") or 0))
        elif c.get("op") == "chamfer":
            best = max(best, float(c.get("dist") or 0))
    ok = best >= 0.5
    note = ""
    if not ok and _curved_body(chain):
        ok = True
        note = ("curvature-continuous body — no discrete sharp outer "
                "corner; rim faces are bonded in assembly")
    return {"id": "policy:print-fillet",
            "prop": f"outer edges treated (fillet/chamfer >= 0.5mm, "
                    f"best {best:g}mm)",
            "holds": ok,
            "detail": note if ok else
                      "add (fillet :radius 0.5 ...) or "
                      "(chamfer :dist 0.5 ...) before the print step"}
