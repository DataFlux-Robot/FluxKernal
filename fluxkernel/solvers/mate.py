"""L2 plugin: 3D assembly — placements + interference checking (OCP).

`assemble` takes >=2 grounded B-rep nodes plus placements (translation
vectors) and checks pairwise interference via Common volume > eps. Closed
kinematic loops are just multi-mate constraints expressed as edges — the DAG
does not force a tree (FLUXmeme graph stance, design v0.1 §3.2).
"""
from __future__ import annotations

from .registry import register


@register("assemble")
def assemble(node_specs, args, ctx):
    from .feature3d import rebuild_brep
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    if len(node_specs) < 2:
        raise ValueError("assemble needs >=2 grounded inputs")
    placements = args.get("placements") or [[0, 0, 0] for _ in node_specs]
    shapes = []
    for s, pl in zip(node_specs, placements):
        shp = rebuild_brep(s)
        if list(pl) != [0, 0, 0]:
            tr = gp_Trsf()
            tr.SetTranslation(gp_Vec(float(pl[0]), float(pl[1]), float(pl[2])))
            shp = BRepBuilderAPI_Transform(shp, tr, True).Shape()
        shapes.append(shp)

    interferences = []
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            common = BRepAlgoAPI_Common(shapes[i], shapes[j]).Shape()
            gp = GProp_GProps()
            BRepGProp.VolumeProperties_s(common, gp)
            v = gp.Mass()
            if v > float(args.get("eps_mm3", 1e-3)):
                interferences.append({"a": i, "b": j, "volume_mm3": round(v, 4)})

    total_v = 0.0
    mass = 0.0
    for s in node_specs:
        g = s.get("ground") or {}
        total_v += float(g.get("volume_mm3", 0.0))
        mass += float(g.get("mass_g", 0.0))
    fields = {"kind": "assembly",
              "ground": {"type": "assembly",
                         "parts": len(node_specs),
                         "volume_mm3": round(total_v, 4), "mass_g": round(mass, 3),
                         "placements": placements}}
    evidence = [{"solver": "mate/ocp", "tier": 0, "parts": len(node_specs),
                 "interferences": len(interferences),
                 "mass_g": round(mass, 3)}]
    obligations = [
        {"id": "no-interference", "prop": "pairwise Common volume <= eps",
         "holds": not interferences, "checker": "mate",
         "detail": str(interferences[:3]) if interferences else ""},
    ]
    return fields, evidence, obligations
