"""L2 plugin: 3D feature evaluation on the OCP (OpenCascade) backend.

This is a PROJECTION layer: it turns a grounded sketch node into a B-rep
projection, computes mass properties, and exports STEP/STL blobs into the
content-addressed store. The kernel core never sees TopoDS objects.

Construction replay (lineage-stable naming, impl plan §8): nodes NEVER
serialize a B-rep; they record HOW to rebuild it. References resolve through
construction paths, not transient face indices, so they survive parameter
changes. The recorded construction is complete and self-contained:
  extrude:  {"op":"extrude", "height":h, "points":[[x,y],...], "material":m}
  revolve:  {"op":"revolve", "angle_deg":a, "points":[...], "material":m}
  boolean:  {"op":"boolean", "bop":"fuse|cut|common", "inputs":[<construction>,...]}
"""
from __future__ import annotations

import math

from .registry import register


def _silence_occt_messenger():
    """OCCT's STEP writer prints transfer statistics to stdout; remove the
    default printer once so node digests and CLI output stay clean."""
    try:
        from OCP.Message import Message
        msgr = Message.DefaultMessenger_s()
        for p in list(msgr.Printers()):
            msgr.RemovePrinter(p)
    except Exception:
        pass


_silence_occt_messenger()

_DENSITY_G_PER_MM3 = {"abs": 1.04e-3, "pla": 1.24e-3, "aluminum": 2.70e-3,
                      "steel": 7.85e-3, "titanium": 4.43e-3}


def _face_from_points(pts: list):
    from OCP.gp import gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
    poly = BRepBuilderAPI_MakePolygon()
    for x, y in pts:
        poly.Add(gp_Pnt(float(x), float(y), 0.0))
    poly.Close()
    return BRepBuilderAPI_MakeFace(poly.Wire()).Face()


def _props(shape) -> dict:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    vp = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vp)
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    cmin, cmax = box.CornerMin(), box.CornerMax()
    xmin, ymin, zmin = cmin.X(), cmin.Y(), cmin.Z()
    xmax, ymax, zmax = cmax.X(), cmax.Y(), cmax.Z()
    com = vp.CentreOfMass()
    return {"volume_mm3": vp.Mass(),
            "com": [com.X(), com.Y(), com.Z()],
            "bbox": [[xmin, ymin, zmin], [xmax, ymax, zmax]]}


def _write_blobs(shape, ctx) -> dict:
    import tempfile, os
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.StlAPI import StlAPI_Writer
    from OCP.STEPControl import STEPControl_Writer, STEPControl_StepModelType
    from OCP.IFSelect import IFSelect_ReturnStatus
    out = {}
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "o.step")
        w = STEPControl_Writer()
        w.Transfer(shape, STEPControl_StepModelType.STEPControl_AsIs)
        if w.Write(sp) == IFSelect_ReturnStatus.IFSelect_RetDone:
            out["step"] = ctx.store.put_blob(open(sp, "rb").read())
        BRepMesh_IncrementalMesh(shape, 0.1, False, 0.1, True)
        tp = os.path.join(td, "o.stl")
        sw = StlAPI_Writer()
        sw.ASCIIMode = False          # binary STL (OCCT defaults to ASCII)
        if sw.Write(shape, tp):
            out["stl"] = ctx.store.put_blob(open(tp, "rb").read())
    return out


def _profile_points(node_specs: list[dict], args: dict) -> list:
    src = node_specs[0] if node_specs else {}
    g = (src.get("ground") or {})
    pts = g.get("points") or ((g.get("construction") or {}).get("points"))
    if not pts:
        raise ValueError("extrude/revolve requires an input with a grounded sketch2d")
    order = args.get("order") or list(pts.keys())
    return [tuple(pts[k]) for k in order]


def _profile_spec(node_specs: list[dict], args: dict) -> dict | None:
    """Return the entity profile (pts/edges/circles) when the input sketch
    carries G1 entities, else None (pure-polygon path stays)."""
    src = node_specs[0] if node_specs else {}
    g = (src.get("ground") or {})
    if g.get("edges") or g.get("circles"):
        return {"pts": g.get("points") or {},
                "edges": g.get("edges") or [],
                "circles": g.get("circles") or []}
    return None


def _arc_edge(p1, p2, r: float, ccw: bool):
    """Edge of a circular arc through p1/p2 with radius r; ccw picks the
    center side (two solutions — never guess silently)."""
    import math as _m
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ
    from OCP.GC import GC_MakeArcOfCircle
    ax_, ay = p1
    bx, by = p2
    dx, dy = bx - ax_, by - ay
    d = _m.hypot(dx, dy)
    if d < 1e-9:
        raise ValueError("arc endpoints coincide")
    if d > 2 * r + 1e-9:
        raise ValueError(f"arc radius {r:g} too small for chord {d:g}")
    h = _m.sqrt(max(r * r - (d / 2) ** 2, 0.0))
    mx, my = (ax_ + bx) / 2, (ay + by) / 2
    ux, uy = dx / d, dy / d
    # two candidate centers at +/- the chord normal; ccw selects
    c1 = (mx + uy * h, my - ux * h)
    c2 = (mx - uy * h, my + ux * h)
    a1 = _m.atan2(ay - c1[1], ax_ - c1[0])
    b1 = _m.atan2(by - c1[1], bx - c1[0])
    def sweep(c):
        a = _m.atan2(ay - c[1], ax_ - c[0])
        b = _m.atan2(by - c[1], bx - c[0])
        sw = (b - a) % (2 * _m.pi)
        return sw
    center = c1 if (sweep(c1) <= _m.pi) == bool(ccw) else c2
    circ = gp_Circ(gp_Ax2(gp_Pnt(center[0], center[1], 0), gp_Dir(0, 0, 1)), r)
    a = _m.atan2(ay - center[1], ax_ - center[0])
    b = _m.atan2(by - center[1], bx - center[0])
    arc = GC_MakeArcOfCircle(circ, a, b, True)
    if not arc.IsDone():
        raise ValueError("arc construction failed")
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    return BRepBuilderAPI_MakeEdge(arc.Value()).Edge()


def _face_from_profile(profile: dict):
    """Face with an entity outer loop (line/arc/spline edges or a single
    outer circle) and circular hole loops."""
    import math as _m
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge,
                                    BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace)
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    pts = {k: (float(v[0]), float(v[1])) for k, v in (profile.get("pts") or {}).items()}
    edges = profile.get("edges") or []
    circles = profile.get("circles") or []
    outer = [c for c in circles if not c.get("hole")]
    holes = [c for c in circles if c.get("hole")]

    if edges:
        mk = BRepBuilderAPI_MakeWire()
        for e in edges:
            et = e.get("e", e.get("type", "line"))
            if et == "line":
                a, b = pts[e["a"]], pts[e["b"]]
                mk.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(a[0], a[1], 0),
                                               gp_Pnt(b[0], b[1], 0)).Edge())
            elif et == "arc":
                a, b = pts[e["a"]], pts[e["b"]]
                mk.Add(_arc_edge(a, b, float(e["r"]), bool(e.get("ccw", True))))
            elif et == "spline":
                through = [pts[n] for n in e.get("through", [])]
                if len(through) < 2:
                    raise ValueError("spline needs >= 2 through points")
                cur = GeomAPI_PointsToBSpline(
                    [gp_Pnt(x, y, 0) for x, y in through]).Curve()
                mk.Add(BRepBuilderAPI_MakeEdge(cur,
                                               gp_Pnt(through[0][0], through[0][1], 0),
                                               gp_Pnt(through[-1][0], through[-1][1], 0)).Edge())
            else:
                raise ValueError(f"unknown sketch entity: {et}")
        face = BRepBuilderAPI_MakeFace(mk.Wire()).Face()
    elif len(outer) == 1:
        c = outer[0]
        ctr = pts[c["c"]]
        circ = gp_Circ(gp_Ax2(gp_Pnt(ctr[0], ctr[1], 0), gp_Dir(0, 0, 1)),
                       float(c["r"]))
        w = BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(circ).Edge())
        face = BRepBuilderAPI_MakeFace(w.Wire()).Face()
    else:
        raise ValueError("profile needs edges or exactly one outer circle")

    for c in holes:
        ctr = pts[c["c"]]
        circ = gp_Circ(gp_Ax2(gp_Pnt(ctr[0], ctr[1], 0), gp_Dir(0, 0, 1)),
                       float(c["r"]))
        hw = BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(circ).Edge()).Wire()
        hw.Reverse()          # inner loop: opposite orientation = a hole
        face = BRepBuilderAPI_MakeFace(face, hw).Face()
    return face


def _parse_at(at, node_specs=None):
    """General placement (the build123d Location analogue).  Accepted forms:

       [dx, dy, dz]                      pure translation
       ((x y z) (ax ay az deg))          translation after rotation
       {origin, axis, angle_deg}         canonical (from spec.frames)
       (:frame <name>)                   named frame of the input node's
                                         spec.frames (any node may carry
                                         frames — skeleton layouts)
    Returns the canonical dict or None.  No case-specific behaviour."""
    if at is None:
        return None
    if isinstance(at, (list, tuple)) and at and isinstance(at[0], str)             and str(at[0]).lstrip(":") == "frame":
        if len(at) < 2:
            raise ValueError("frame reference needs a name: (:frame name)")
        name = str(at[1])
        spec = (node_specs[0].get("spec") or {}) if node_specs else {}
        frames = spec.get("frames") or {}
        if name not in frames:
            raise ValueError(f"unknown frame {name!r} "
                             f"(spec.frames has: {sorted(frames)})")
        return _parse_at(frames[name], node_specs)
    if isinstance(at, dict):
        out = {"origin": [float(v) for v in at.get("origin", [0, 0, 0])]}
        if at.get("axis"):
            out["axis"] = [float(v) for v in at["axis"]]
            out["angle_deg"] = float(at.get("angle_deg", 0.0))
        return out
    if isinstance(at, (list, tuple)) and len(at) == 3             and all(isinstance(v, (int, float)) for v in at):
        return {"origin": [float(v) for v in at]}
    vals = [[float(v) for v in part] for part in at]
    if len(vals) == 1 and len(vals[0]) == 3:
        return {"origin": vals[0]}
    if len(vals) == 2 and len(vals[0]) == 3 and len(vals[1]) == 4:
        return {"origin": vals[0], "axis": vals[1][:3],
                "angle_deg": vals[1][3]}
    raise ValueError(f"bad placement {at!r}: want [dx,dy,dz], "
                     "((x y z) (ax ay az deg)), or (:frame name)")


def _placement_trsf(pl: dict):
    """rotate about the world-origin axis first, then translate."""
    from OCP.gp import gp_Trsf, gp_Vec, gp_Pnt, gp_Dir, gp_Ax1
    t = gp_Trsf()
    if pl.get("axis") and pl.get("angle_deg"):
        r = gp_Trsf()
        r.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*pl["axis"])),
                      math.radians(float(pl["angle_deg"])))
        t = r
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(*[float(v) for v in pl.get("origin", [0, 0, 0])]))
    return tr.Multiplied(t)


def _placed(shape, pl: dict):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    return BRepBuilderAPI_Transform(shape, _placement_trsf(pl), True).Shape()


@register("extrude")
def extrude(node_specs, args, ctx):
    from OCP.gp import gp_Vec
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    height = float(args["height"])
    material = args.get("material", "abs")
    prof = _profile_spec(node_specs, args)
    if prof:
        face = _face_from_profile(prof)
        shape = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, height)).Shape()
        cons = {"op": "extrude", "height": height, "material": material,
                "profile": prof}
    else:
        pts = _profile_points(node_specs, args)
        face = _face_from_points(pts)
        shape = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, height)).Shape()
        cons = {"op": "extrude", "height": height,
                "points": [[float(x), float(y)] for x, y in pts], "material": material}
    pl = _parse_at(args.get("at"), node_specs)
    if pl:
        shape = _placed(shape, pl)
        cons["placement"] = pl
    return _finish_solid(shape, ctx, cons, desc=f"extrude h={height}")


@register("revolve")
def revolve(node_specs, args, ctx):
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax1
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    pts = _profile_points(node_specs, args)
    angle_deg = float(args.get("angle_deg", 360.0))
    material = args.get("material", "abs")
    face = _face_from_points(pts)
    axis = [float(v) for v in args.get("axis", [0, 1, 0])]
    ax = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis))   # through the sketch origin
    shape = BRepPrimAPI_MakeRevol(face, ax, math.radians(angle_deg)).Shape()
    cons = {"op": "revolve", "angle_deg": angle_deg, "axis": axis,
            "points": [[float(x), float(y)] for x, y in pts], "material": material}
    pl = _parse_at(args.get("at"), node_specs)
    if pl:
        shape = _placed(shape, pl)
        cons["placement"] = pl
    return _finish_solid(shape, ctx, cons, desc=f"revolve {angle_deg}deg")


@register("boolean")
def boolean(node_specs, args, ctx):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
    if len(node_specs) < 2:
        raise ValueError("boolean needs >=2 grounded inputs")
    shapes = [rebuild_brep(s) for s in node_specs]
    bop = args.get("bop", args.get("op", "fuse"))
    ops = {"fuse": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut, "common": BRepAlgoAPI_Common}
    shape = ops[bop](shapes[0], shapes[1]).Shape()
    for extra in shapes[2:]:
        shape = ops[bop](shape, extra).Shape()
    cons = {"op": "boolean", "bop": bop,
            "inputs": [(s.get("ground") or {}).get("construction")
                       for s in node_specs]}
    return _finish_solid(shape, ctx, cons, desc=f"boolean/{bop}")


@register("scale-instance")
def scale_instance(node_specs, args, ctx):
    """Derive a scaled instance of an assembly: every grounded solid among
    the node_specs is scaled about the origin and fused into ONE solid.
    The construction records the source constructions BY VALUE (boolean
    pattern), so the projection replays without store access."""
    from OCP.gp import gp_Trsf, gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    ratio = float(args.get("ratio", 1.0))
    material = args.get("material", "pla")
    shapes, cons_inputs = [], []
    for s in node_specs:
        g = (s.get("ground") or {})
        if not g.get("construction"):
            continue
        tr = gp_Trsf()
        tr.SetScale(gp_Pnt(0, 0, 0), ratio)
        shapes.append(BRepBuilderAPI_Transform(rebuild_brep(s), tr, True).Shape())
        cons_inputs.append(g["construction"])
    if not shapes:
        raise ValueError("scale-instance found no grounded solids in the subtree")
    shape = shapes[0]
    for extra in shapes[1:]:
        shape = BRepAlgoAPI_Fuse(shape, extra).Shape()
    cons = {"op": "scale-instance", "ratio": ratio, "material": material,
            "inputs": cons_inputs}
    return _finish_solid(shape, ctx, cons, desc=f"scale-instance r={ratio}")


def rebuild_brep(node_spec: dict):
    """Rebuild a B-rep from a node's recorded construction (projection replay).

    Nodes never serialize TopoDS; they record HOW to rebuild. This is what
    makes lineage-stable naming possible: references survive parameter
    changes because they resolve through construction paths, not transient
    face indices.
    """
    g = node_spec.get("ground") or {}
    cons = g.get("construction")
    if not cons:
        raise ValueError("input node has no replayable construction")
    kind = cons["op"]
    if kind == "extrude":
        from OCP.gp import gp_Vec
        from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
        if cons.get("profile"):
            face = _face_from_profile(cons["profile"])
        else:
            face = _face_from_points([tuple(p) for p in cons["points"]])
        shape = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, cons["height"])).Shape()
        return _placed(shape, cons["placement"]) if cons.get("placement") else shape
    if kind == "revolve":
        from OCP.gp import gp_Pnt, gp_Dir, gp_Ax1
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
        face = _face_from_points([tuple(p) for p in cons["points"]])
        shape = BRepPrimAPI_MakeRevol(
            face, gp_Ax1(gp_Pnt(0, 0, 0),
                         gp_Dir(*cons.get("axis", [0, 1, 0]))),
            math.radians(cons.get("angle_deg", 360.0))).Shape()
        return _placed(shape, cons["placement"]) if cons.get("placement") else shape
    if kind == "boolean":
        sub = [rebuild_brep({"ground": {"construction": c}}) for c in cons["inputs"]]
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
        bop = cons["bop"]
        ops = {"fuse": BRepAlgoAPI_Fuse, "cut": BRepAlgoAPI_Cut,
               "common": BRepAlgoAPI_Common}
        shape = ops[bop](sub[0], sub[1]).Shape()
        for extra in sub[2:]:
            shape = ops[bop](shape, extra).Shape()
        return shape
    if kind == "scale-instance":
        from OCP.gp import gp_Trsf, gp_Pnt
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
        ratio = float(cons.get("ratio", 1.0))
        tr = gp_Trsf()
        tr.SetScale(gp_Pnt(0, 0, 0), ratio)
        sub = [BRepBuilderAPI_Transform(
                   rebuild_brep({"ground": {"construction": c}}), tr, True).Shape()
               for c in cons["inputs"]]
        shape = sub[0]
        for extra in sub[1:]:
            shape = BRepAlgoAPI_Fuse(shape, extra).Shape()
        return shape
    raise ValueError(f"cannot replay construction op: {kind}")


def _finish_solid(shape, ctx, cons: dict, desc: str):
    props = _props(shape)
    material = cons.get("material", "abs")
    density = _DENSITY_G_PER_MM3.get(material, 1.0e-3)
    mass_g = props["volume_mm3"] * density
    blobs = _write_blobs(shape, ctx)
    fields = {"kind": "part",
              "ground": {"type": "brep", "backend": "ocp", "blobs": blobs,
                         "construction": cons,
                         "volume_mm3": props["volume_mm3"], "mass_g": mass_g,
                         "com": props["com"], "bbox": props["bbox"],
                         "material": material}}
    ok = props["volume_mm3"] > 1e-9 and bool(blobs.get("step"))
    evidence = [{"solver": "feature3d/ocp", "op": desc,
                 "volume_mm3": props["volume_mm3"], "mass_g": mass_g,
                 "bbox": props["bbox"], "step_exported": bool(blobs.get("step")),
                 "stl_exported": bool(blobs.get("stl"))}]
    obligations = [
        {"id": "solid-valid", "prop": "evaluated to a valid solid with volume>0",
         "holds": ok, "checker": "feature3d",
         "detail": f"V={props['volume_mm3']:.3f} mm^3"},
        {"id": "export-ok", "prop": "STEP projection exported",
         "holds": bool(blobs.get("step")), "checker": "feature3d", "detail": ""},
    ]
    return fields, evidence, obligations
