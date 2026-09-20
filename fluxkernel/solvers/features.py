"""L2 plugin: G2 feature operators — fillet/chamfer/loft/shell/pattern/
mirror.  Every operator records its construction BY VALUE (source
construction + parameters) and replays through rebuild_brep; failures
become readable ValueErrors (rejected edges with repair text, never bare
exceptions).
"""
from __future__ import annotations

from .registry import register
from .feature3d import _finish_solid, _props, rebuild_brep


def _edge_vertices(edge):
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    out = []
    ex = TopExp_Explorer(edge, TopAbs_VERTEX)
    while ex.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))
        out.append((p.X(), p.Y(), p.Z()))
        ex.Next()
    return out


def _edges_of(shape, sel):
    """Edge selection — three-anchor policy: 'all' or a selector dict
    {'parallel-to': [x,y,z]}; 0 hits is an error, never a guess."""
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    import math as _m
    out = []
    ex = TopExp_Explorer(shape, TopAbs_EDGE)
    while ex.More():
        out.append(TopoDS.Edge(ex.Current()))
        ex.Next()
    if sel in (None, "all"):
        return out
    if isinstance(sel, dict) and "plane" in sel:
        from ..solvers.feature3d import _props as _fprops
        axis = {"x": 0, "y": 1, "z": 2}.get(str(sel["plane"])[0], 2)
        hi_side = str(sel["plane"]).endswith("max")
        bb = _fprops(shape)["bbox"]
        target = bb[1][axis] if hi_side else bb[0][axis]
        from OCP.BRep import BRep_Tool
        keep = []
        for e in out:
            vs = _edge_vertices(e)
            if vs and all(abs(v[axis] - target) < 1e-6 for v in vs):
                keep.append(e)
        if not keep:
            raise ValueError(f"edge selector plane={sel['plane']!r} "
                             f"matched 0 edges — never a guess")
        return keep
    if isinstance(sel, dict) and "parallel-to" in sel:
        d = [float(v) for v in sel["parallel-to"]]
        n = _m.hypot(*d) or 1.0
        d = [v / n for v in d]
        # tol: minimum |direction·axis| (default exact); <1 admits
        # near-parallel edges, e.g. the slightly skewed longitudinals
        # of a tapered loft
        tol = float(sel.get("tol", 1.0 - 1e-6))
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Line
        keep = []
        for e in out:
            try:
                ad = BRepAdaptor_Curve(e)
                if ad.GetType() == GeomAbs_Line:
                    v = ad.Line().Direction()
                    dot = abs(v.X() * d[0] + v.Y() * d[1] + v.Z() * d[2])
                    if dot > tol:
                        keep.append(e)
            except Exception:
                pass
        if not keep:
            raise ValueError(f"edge selector {sel!r} matched 0 edges — "
                             f"widen the selector or use 'all'")
        return keep
    raise ValueError(f"bad edge selector {sel!r}: 'all' or "
                     "{'parallel-to': [x,y,z]}")


def _fillet_or_chamfer(node_specs, args, ctx, kind):
    from OCP.BRepFilletAPI import (BRepFilletAPI_MakeFillet,
                                   BRepFilletAPI_MakeChamfer)
    src = rebuild_brep(node_specs[0])
    src_cons = (node_specs[0].get("ground") or {}).get("construction") or {}
    sel = args.get("edges", "all")
    val = float(args["radius"] if kind == "fillet" else args["dist"])
    mk = (BRepFilletAPI_MakeFillet(src) if kind == "fillet"
          else BRepFilletAPI_MakeChamfer(src))
    for e in _edges_of(src, sel):
        mk.Add(val, e)
    mk.Build()
    if not mk.IsDone():
        raise ValueError(f"{kind} value {val:g} failed on the selected "
                         f"edges (selector {sel!r}) — reduce the value")
    cons = {"op": kind, "edges": sel,
            ("radius" if kind == "fillet" else "dist"): val,
            "material": src_cons.get("material", "abs"),
            "input": src_cons}
    return _finish_solid(mk.Shape(), ctx, cons, desc=f"{kind} {val:g}",
                          at=args.get("at"), node_specs=node_specs)


@register("fillet")
def fillet(node_specs, args, ctx):
    return _fillet_or_chamfer(node_specs, args, ctx, "fillet")


@register("chamfer")
def chamfer(node_specs, args, ctx):
    return _fillet_or_chamfer(node_specs, args, ctx, "chamfer")


@register("loft")
def loft(node_specs, args, ctx):
    """Loft over >=2 polygon sketch sections; :zs gives each section's
    parallel z offset (sections are planar z=0 sketches)."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    if len(node_specs) < 2:
        raise ValueError("loft needs >= 2 sketch sections as inputs")
    zs = args.get("zs") or [0.0] * len(node_specs)
    if len(zs) != len(node_specs):
        raise ValueError(f"loft :zs needs one z per section "
                         f"({len(zs)} given for {len(node_specs)} inputs)")
    ruled = bool(args.get("ruled", True))
    material = args.get("material", "abs")
    mk = BRepOffsetAPI_ThruSections(True, ruled)
    sections = []
    for s, z in zip(node_specs, zs):
        z = float(z)
        g = (s.get("ground") or {})
        pts = g.get("points") or {}
        if not pts or (g.get("edges") or g.get("circles")):
            raise ValueError("loft sections: polygon sketches only in v1 "
                             "(no entity edges/circles)")
        sections.append({"pts": {k: list(v) for k, v in pts.items()}})
        order = list(pts.keys())
        mk.AddWire(_polygon_wire(
            [(float(pts[k][0]), float(pts[k][1]), z) for k in order]))
    mk.Build()
    if not mk.IsDone():
        raise ValueError("loft failed — sections degenerate or coincident")
    cons = {"op": "loft", "ruled": ruled, "material": material,
            "zs": [float(z) for z in zs], "sections": sections}
    return _finish_solid(mk.Shape(), ctx, cons, desc="loft",
                          at=args.get("at"), node_specs=node_specs)


@register("shell")
def shell(node_specs, args, ctx):
    """Hollow a solid, opening the 'top' face (bbox z-max)."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
    from OCP.OCP.collections import List_TopoDS_Shape
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    src = rebuild_brep(node_specs[0])
    src_cons = (node_specs[0].get("ground") or {}).get("construction") or {}
    thick = float(args["thick"])
    open_sel = str(args.get("open", "zmax"))
    axes = {"xmax": (0, True), "xmin": (0, False),
            "ymax": (1, True), "ymin": (1, False),
            "zmax": (2, True), "zmin": (2, False)}
    if open_sel not in axes:
        raise ValueError(f"shell :open must be one of {sorted(axes)}")
    ax, hi = axes[open_sel]
    bb = _props(src)["bbox"]
    target = bb[1][ax] if hi else bb[0][ax]
    faces = []
    ex = TopExp_Explorer(src, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face(ex.Current())
        fb = _props(f)["bbox"]
        if abs(fb[0][ax] - target) < 1e-6 and abs(fb[1][ax] - target) < 1e-6:
            faces.append(f)
        ex.Next()
    if not faces:
        raise ValueError(f"shell: no face found at {open_sel} — check the "
                         f"input solid's orientation")
    removed = List_TopoDS_Shape()
    for f in faces:
        removed.Append(f)
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidByJoin(src, removed, -thick, 1.0e-3)
    if not mk.IsDone():
        raise ValueError(f"shell thickness {thick:g} failed — try a "
                         f"smaller thickness")
    cons = {"op": "shell", "thick": thick, "open": open_sel,
            "material": src_cons.get("material", "abs"), "input": src_cons}
    return _finish_solid(mk.Shape(), ctx, cons, desc=f"shell {thick:g}",
                          at=args.get("at"), node_specs=node_specs)


@register("cut")
def cut(node_specs, args, ctx):
    """Boolean difference input[0] - input[1] (pockets, bores, hollow
    bodies).  Construction records both chains by value for replay."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    src = rebuild_brep(node_specs[0])
    tool = rebuild_brep(node_specs[1])
    src_cons = (node_specs[0].get("ground") or {}).get("construction") or {}
    tool_cons = (node_specs[1].get("ground") or {}).get("construction") or {}
    mk = BRepAlgoAPI_Cut(src, tool)
    mk.Build()
    if not mk.IsDone():
        raise ValueError("cut failed — check the tool intersects the body")
    cons = {"op": "cut", "input": src_cons, "tool": tool_cons,
            "material": src_cons.get("material", "abs")}
    return _finish_solid(mk.Shape(), ctx, cons, desc="cut",
                         at=args.get("at"), node_specs=node_specs)


@register("pattern-linear")
def pattern_linear(node_specs, args, ctx):
    """Linear array: count copies of the input along dir, spacing apart,
    fused into one part (count/spacing may be :param/:expr)."""
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    src = rebuild_brep(node_specs[0])
    src_cons = (node_specs[0].get("ground") or {}).get("construction") or {}
    direction = [float(v) for v in args.get("dir", [1, 0, 0])]
    count = int(args.get("count", 2))
    spacing = float(args.get("spacing", 10.0))
    if count < 1:
        raise ValueError(f"pattern count {count} < 1")
    shape = src
    for i in range(1, count):
        tr = gp_Trsf()
        tr.SetTranslation(gp_Vec(*[v * spacing * i for v in direction]))
        shape = BRepAlgoAPI_Fuse(
            shape, BRepBuilderAPI_Transform(src, tr, True).Shape()).Shape()
    cons = {"op": "pattern", "dir": direction, "count": count,
            "spacing": spacing,
            "material": src_cons.get("material", "abs"), "input": src_cons}
    return _finish_solid(shape, ctx, cons,
                         desc=f"pattern n={count} s={spacing:g}",
                         at=args.get("at"))


@register("mirror")
def mirror(node_specs, args, ctx):
    """Mirror about 'xy'|'yz'|'xz' or {'normal': [x,y,z], 'point': [...]}."""
    from OCP.gp import gp_Trsf, gp_Ax2, gp_Pnt, gp_Dir
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    src = rebuild_brep(node_specs[0])
    src_cons = (node_specs[0].get("ground") or {}).get("construction") or {}
    plane = args.get("plane", "yz")
    tr = gp_Trsf()
    axes = {"xy": (0, 0, 1), "yz": (1, 0, 0), "xz": (0, 1, 0)}
    if plane in axes:
        tr.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*axes[plane])))
    elif isinstance(plane, dict) and "normal" in plane:
        tr.SetMirror(gp_Ax2(
            gp_Pnt(*[float(v) for v in plane.get("point", [0, 0, 0])]),
            gp_Dir(*[float(v) for v in plane["normal"]])))
    else:
        raise ValueError(f"bad mirror plane {plane!r}: 'xy'/'yz'/'xz' or "
                         "{'normal':[x,y,z],'point':[...]}")
    shape = BRepBuilderAPI_Transform(src, tr, True).Shape()
    cons = {"op": "mirror", "plane": plane,
            "material": src_cons.get("material", "abs"), "input": src_cons}
    return _finish_solid(shape, ctx, cons, desc=f"mirror {plane!r}")


def _polygon_wire(points3):
    from OCP.gp import gp_Pnt
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge,
                                    BRepBuilderAPI_MakeWire)
    mk = BRepBuilderAPI_MakeWire()
    n = len(points3)
    for i in range(n):
        a = points3[i]
        b = points3[(i + 1) % n]
        mk.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(*a), gp_Pnt(*b)).Edge())
    return mk.Wire()


def rebuild_feature(cons: dict):
    """Replay a G2 feature from its by-value construction (called from
    feature3d.rebuild_brep)."""
    from OCP.gp import gp_Trsf, gp_Vec, gp_Ax2, gp_Pnt, gp_Dir
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

    def _src():
        return rebuild_brep({"ground": {"construction": cons["input"]}})

    kind = cons["op"]
    if kind in ("fillet", "chamfer"):
        from OCP.BRepFilletAPI import (BRepFilletAPI_MakeFillet,
                                       BRepFilletAPI_MakeChamfer)
        val = cons.get("radius", cons.get("dist"))
        src = _src()
        mk = (BRepFilletAPI_MakeFillet(src) if kind == "fillet"
              else BRepFilletAPI_MakeChamfer(src))
        for e in _edges_of(src, cons.get("edges", "all")):
            mk.Add(float(val), e)
        mk.Build()
        return mk.Shape()
    if kind == "loft":
        from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
        mk = BRepOffsetAPI_ThruSections(True, bool(cons.get("ruled", True)))
        for sec, z in zip(cons["sections"], cons.get("zs", [])):
            pts = sec["pts"]
            order = list(pts.keys())
            mk.AddWire(_polygon_wire(
                [(float(pts[k][0]), float(pts[k][1]), float(z))
                 for k in order]))
        mk.Build()
        return mk.Shape()
    if kind == "shell":
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
        from OCP.OCP.collections import List_TopoDS_Shape
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopoDS import TopoDS
        src = _src()
        axes = {"xmax": (0, True), "xmin": (0, False),
                "ymax": (1, True), "ymin": (1, False),
                "zmax": (2, True), "zmin": (2, False)}
        sel = str(cons.get("open", "zmax"))
        ax, hi = axes[sel]
        target = _props(src)["bbox"][1 if hi else 0][ax]
        removed = List_TopoDS_Shape()
        ex = TopExp_Explorer(src, TopAbs_FACE)
        while ex.More():
            f = TopoDS.Face(ex.Current())
            fb = _props(f)["bbox"]
            if abs(fb[0][ax] - target) < 1e-6 and abs(fb[1][ax] - target) < 1e-6:
                removed.Append(f)
            ex.Next()
        if not removed.Extent():
            raise ValueError(f"shell replay: no face at {sel}")
        mk = BRepOffsetAPI_MakeThickSolid()
        mk.MakeThickSolidByJoin(src, removed, -float(cons["thick"]), 1.0e-3)
        return mk.Shape()
    if kind == "cut":
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        mk = BRepAlgoAPI_Cut(rebuild_brep({"ground": {"construction": cons["input"]}}),
                             rebuild_brep({"ground": {"construction": cons["tool"]}}))
        mk.Build()
        if not mk.IsDone():
            raise ValueError("cut replay failed")
        return mk.Shape()
    if kind == "pattern":
        src = _src()
        shape = src
        for i in range(1, int(cons["count"])):
            tr = gp_Trsf()
            sp = float(cons["spacing"]) * i
            tr.SetTranslation(gp_Vec(*[v * sp for v in cons["dir"]]))
            shape = BRepAlgoAPI_Fuse(
                shape, BRepBuilderAPI_Transform(src, tr, True).Shape()).Shape()
        return shape
    if kind == "mirror":
        src = _src()
        plane = cons["plane"]
        tr = gp_Trsf()
        axes = {"xy": (0, 0, 1), "yz": (1, 0, 0), "xz": (0, 1, 0)}
        if plane in axes:
            tr.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*axes[plane])))
        else:
            tr.SetMirror(gp_Ax2(
                gp_Pnt(*[float(v) for v in plane.get("point", [0, 0, 0])]),
                gp_Dir(*[float(v) for v in plane["normal"]])))
        return BRepBuilderAPI_Transform(src, tr, True).Shape()
    raise ValueError(f"cannot replay feature op: {kind}")
