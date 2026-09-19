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


@register("extrude")
def extrude(node_specs, args, ctx):
    from OCP.gp import gp_Vec
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    pts = _profile_points(node_specs, args)
    height = float(args["height"])
    material = args.get("material", "abs")
    face = _face_from_points(pts)
    shape = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, height)).Shape()
    cons = {"op": "extrude", "height": height,
            "points": [[float(x), float(y)] for x, y in pts], "material": material}
    return _finish_solid(shape, ctx, cons, desc=f"extrude h={height}")


@register("revolve")
def revolve(node_specs, args, ctx):
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax1
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    pts = _profile_points(node_specs, args)
    angle_deg = float(args.get("angle_deg", 360.0))
    material = args.get("material", "abs")
    face = _face_from_points(pts)
    ax = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0))  # profile revolves about Y axis
    shape = BRepPrimAPI_MakeRevol(face, ax, math.radians(angle_deg)).Shape()
    cons = {"op": "revolve", "angle_deg": angle_deg,
            "points": [[float(x), float(y)] for x, y in pts], "material": material}
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
        face = _face_from_points([tuple(p) for p in cons["points"]])
        return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, cons["height"])).Shape()
    if kind == "revolve":
        from OCP.gp import gp_Pnt, gp_Dir, gp_Ax1
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
        face = _face_from_points([tuple(p) for p in cons["points"]])
        return BRepPrimAPI_MakeRevol(
            face, gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)),
            math.radians(cons.get("angle_deg", 360.0))).Shape()
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
