"""L2 plugin: 3D assembly — placements + interference checking (OCP).

`assemble` takes >=2 grounded B-rep nodes plus placements (translation
vectors) and checks pairwise interference via Common volume > eps. Closed
kinematic loops are just multi-mate constraints expressed as edges — the DAG
does not force a tree (FLUXmeme graph stance, design v0.1 §3.2).
"""
from __future__ import annotations

import math

from .registry import register


@register("assemble")
def assemble(node_specs, args, ctx):
    from .feature3d import rebuild_brep
    from OCP.gp import gp_Trsf, gp_Vec, gp_Pnt, gp_Dir, gp_Ax1
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
        tr = gp_Trsf()
        if len(pl) == 7:
            # [dx, dy, dz, ax, ay, az, angle_deg]: rotate about the axis,
            # then translate
            rot = gp_Trsf()
            rot.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0),
                                   gp_Dir(float(pl[3]), float(pl[4]),
                                          float(pl[5]))),
                            math.radians(float(pl[6])))
            tr.SetTranslation(gp_Vec(float(pl[0]), float(pl[1]), float(pl[2])))
            tr = tr.Multiplied(rot)
        else:
            if list(pl) != [0, 0, 0]:
                tr.SetTranslation(gp_Vec(float(pl[0]), float(pl[1]), float(pl[2])))
        if list(pl) != [0, 0, 0]:
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
    # the assembled model is exportable: fuse the placed shapes into one
    # shape -> STEP/STL blobs. (TopoDS_Builder.Add segfaults on this OCP
    # 8.0.1 wheel; BRepAlgoAPI_Fuse is the proven path — for disjoint parts
    # the fused volume equals the sum.)
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    export_shape = shapes[0]
    for s in shapes[1:]:
        export_shape = BRepAlgoAPI_Fuse(export_shape, s).Shape()
    from .feature3d import _write_blobs
    blobs = _write_blobs(export_shape, ctx)
    fields = {"kind": "assembly",
              "ground": {"type": "assembly",
                         "parts": len(node_specs),
                         "volume_mm3": round(total_v, 4), "mass_g": round(mass, 3),
                         "placements": placements,
                         "blobs": blobs}}
    evidence = [{"solver": "mate/ocp", "tier": 0, "parts": len(node_specs),
                 "interferences": len(interferences),
                 "mass_g": round(mass, 3)}]
    obligations = [
        {"id": "no-interference", "prop": "pairwise Common volume <= eps",
         "holds": not interferences, "checker": "mate",
         "detail": str(interferences[:3]) if interferences else ""},
    ]
    return fields, evidence, obligations


@register("mate-solve")
def mate_solve(node_specs, args, ctx):
    """G4: analytic mating — placements SOLVED from named-feature mates,
    not hand-filled.  v1 solves translations against named bbox planes
    ('plane:zmax' etc. recorded by feature3d); the base part (input 0)
    stays at identity.  Each 'plane' mate consumes one translation axis
    of one movable part; any unconsumed axis is reported (fully-mated is
    soft — mechanisms may demand it).  Solved placements then go through
    the SAME interference gate as assemble."""
    import math
    if len(node_specs) < 2:
        raise ValueError("mate-solve needs >= 2 grounded inputs")

    def feats(spec):
        g = (spec.get("ground") or {})
        f = (g.get("construction") or {}).get("features") or {}
        if f:
            return f
        (x0, y0, z0), (x1, y1, z1) = g.get("bbox") or [[0, 0, 0], [1, 1, 1]]
        return {"plane:xmin": x0, "plane:xmax": x1,
                "plane:ymin": y0, "plane:ymax": y1,
                "plane:zmin": z0, "plane:zmax": z1}

    F = [feats(spec) for spec in node_specs]
    eff = [dict(f) for f in F]      # effective positions after prior mates
    offsets = [[0.0, 0.0, 0.0] for _ in node_specs]
    consumed = [set() for _ in node_specs]
    axis_of = {"x": 0, "y": 1, "z": 2}

    for m in args.get("mates", []):
        kind = m[0]
        if kind != "plane":
            raise ValueError(f"mate-solve v1 supports 'plane' mates, "
                             f"got {kind!r} — other combinations belong "
                             f"to mechanism authors, not hand-tuning")
        # (plane <moving-idx> <feat> <base-idx> <feat> <gap>)
        mi, mfeat, bi, bfeat = int(m[1]), str(m[2]), int(m[3]), str(m[4])
        gap = float(m[5]) if len(m) > 5 else 0.0
        if mfeat not in F[mi] or bfeat not in F[bi]:
            raise ValueError(f"unknown named feature in mate {m!r} — "
                             f"features: {sorted(F[mi])} / {sorted(F[bi])}")
        axis = mfeat.split(":")[1][0]            # xmin/xmax/y.../z...
        if axis != bfeat.split(":")[1][0]:
            raise ValueError(f"mate {m!r} mixes axes — plane mates are "
                             f"per-axis")
        k = axis_of[axis]
        # moving plane lands on the base plane's EFFECTIVE position
        # (+gap outward); the moving part's own effective planes shift by
        # the applied delta so chained mates see the updated layout
        target = eff[bi][bfeat] + (gap if bfeat.endswith("max") else -gap)
        delta = target - eff[mi][mfeat]
        offsets[mi][k] += delta
        for name, val in eff[mi].items():
            if isinstance(val, (int, float)) and name.startswith(f"plane:{axis}"):
                eff[mi][name] = val + delta
        consumed[mi].add(k)

    free = []
    for i in range(1, len(node_specs)):
        for k, ax in enumerate("xyz"):
            if k not in consumed[i]:
                free.append(f"part[{i}].{ax}")
    mated_ok = not free

    # apply offsets as plain translations, reuse the assemble pipeline
    placements = [[0, 0, 0]] + [offsets[i] for i in range(1, len(node_specs))]
    res = assemble(node_specs, {**args, "placements": placements}, ctx)
    fields, evidence, obligations = res
    g = dict(fields["ground"])
    g["placements"] = placements
    g["mate_solution"] = {"mates": args.get("mates", []),
                          "free_axes": free}
    fields = {**fields, "ground": g}
    evidence = list(evidence) + [{
        "solver": "mate/solve", "tier": 0, "placements": placements,
        "free_axes": free}]
    obligations = list(obligations) + [{
        "id": "fully-mated", "prop": "no free translation axes",
        "holds": mated_ok, "checker": "mate-solve", "class": "soft",
        "detail": "" if mated_ok else
        f"free axes: {', '.join(free)} — add a plane mate for each"}]
    return fields, evidence, obligations
