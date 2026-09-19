"""L2 plugin: DfAM checks — wall thickness / overhang evidence for a B-rep
node under a declared process (impl plan §8). Tier-0 geometry heuristics;
physical truth stays with evidence tiers, not the kernel.
"""
from __future__ import annotations

import math

from .registry import register


@register("dfam-check")
def dfam_check(node_specs, args, ctx):
    s = node_specs[0] if node_specs else {}
    g = (s.get("ground") or {})
    if not g.get("construction"):
        raise ValueError("dfam-check needs a grounded B-rep input")
    bbox = g.get("bbox") or [[0, 0, 0], [1, 1, 1]]
    dims = [abs(bbox[1][k] - bbox[0][k]) for k in range(3)]
    min_dim = min(dims)
    process = args.get("process", "fdm")

    # tier-0 heuristics: min wall from bbox, overhangs from STL triangle normals
    stl_d = (g.get("blobs") or {}).get("stl")
    overhang_pct = 0.0
    tris = 0
    if stl_d and process in ("fdm", "sla"):
        import struct
        data = ctx.store.get_blob(stl_d)
        n = struct.unpack("<I", data[80:84])[0]
        crit = math.cos(math.radians(90.0 - float(args.get("crit_angle_deg", 45))))
        tris = min(n, 20000)
        # first pass: bed level = global min z
        base_z = None
        verts = []
        for i in range(tris):
            off = 84 + i * 50
            if off + 50 > len(data):
                tris = i
                break
            v = struct.unpack("<9f", data[off + 12:off + 48])
            verts.append(v)
            zmin_t = min(v[2], v[5], v[8])
            base_z = zmin_t if base_z is None else min(base_z, zmin_t)
        bad = 0
        eps = 1e-6
        for i, v in enumerate(verts):
            nx, ny, nz = struct.unpack("<3f", data[84 + i * 50:84 + i * 50 + 12])
            vlen = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            downward = (-nz / vlen) > crit           # steeper than critical angle
            on_bed = min(v[2], v[5], v[8]) <= base_z + eps
            if downward and not on_bed:
                bad += 1
        overhang_pct = round(100.0 * bad / tris, 2) if tris else 0.0

    min_wall_ok = min_dim >= float(args.get("min_wall_mm", 1.0))
    overhang_ok = overhang_pct <= float(args.get("max_overhang_pct", 40.0))
    evidence = [{"solver": "dfam/heuristic", "tier": 0, "process": process,
                 "min_dim_mm": round(min_dim, 3), "triangles": tris,
                 "overhang_pct": overhang_pct}]
    obligations = [
        {"id": "wall-ok", "prop": f"min dimension >= {args.get('min_wall_mm', 1.0)}mm",
         "holds": min_wall_ok, "checker": "dfam",
         "detail": f"min_dim={min_dim:.2f}mm"},
        {"id": "overhang-ok", "prop": f"overhang <= {args.get('max_overhang_pct', 40)}%",
         "holds": overhang_ok, "checker": "dfam",
         "detail": f"{overhang_pct}% downward faces beyond critical angle"},
    ]
    return {}, evidence, obligations


@register("dfam-print")
def dfam_print(node_specs, args, ctx):
    """FDM printability gate — termination set (b) of the evolution plan.

    Hard obligations (a promoted print edge means all held, via C0):
      wall-ok      thinnest bbox dimension >= min_wall_mm
      overhang-ok  downward faces beyond the self-supporting angle
                   (excluding the bed layer) <= max_overhang_pct
      connected    the STL is one connected shell (vertex-welded union-find)
      warp-ok      height/footprint aspect ratio <= max_aspect
    Thresholds are deliberately lenient: a false "unprintable" verdict
    balloons the tree into full manufacture branches (risk #3).
    """
    import struct
    s = node_specs[0] if node_specs else {}
    g = (s.get("ground") or {})
    if not g.get("construction"):
        raise ValueError("dfam-print needs a grounded B-rep input")
    bbox = g.get("bbox") or [[0, 0, 0], [1, 1, 1]]
    dims = [abs(bbox[1][k] - bbox[0][k]) for k in range(3)]
    min_dim = min(dims)

    min_wall_ok = min_dim >= float(args.get("min_wall_mm", 0.5))

    stl_d = (g.get("blobs") or {}).get("stl")
    overhang_pct, tris, comps = 0.0, 0, 1
    if stl_d:
        data = ctx.store.get_blob(stl_d)
        n = struct.unpack("<I", data[80:84])[0]
        crit = math.cos(math.radians(90.0 - float(args.get("crit_angle_deg", 50))))
        tris = min(n, 20000)
        tri_ids, vid = [], {}
        bad = 0
        base_z = None
        for i in range(tris):
            off = 84 + i * 50
            if off + 50 > len(data):
                tris = i
                break
            v = struct.unpack("<9f", data[off + 12:off + 48])
            zmin_t = min(v[2], v[5], v[8])
            base_z = zmin_t if base_z is None else min(base_z, zmin_t)
            ids = []
            for c in range(3):
                k = (round(v[c * 3], 3), round(v[c * 3 + 1], 3), round(v[c * 3 + 2], 3))
                if k not in vid:
                    vid[k] = len(vid)
                ids.append(vid[k])
            tri_ids.append(ids)
        eps = 1e-6
        for i in range(tris):
            off = 84 + i * 50
            nx, ny, nz = struct.unpack("<3f", data[off:off + 12])
            vlen = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            v = struct.unpack("<9f", data[off + 12:off + 48])
            downward = (-nz / vlen) > crit
            on_bed = min(v[2], v[5], v[8]) <= base_z + eps
            if downward and not on_bed:
                bad += 1
        overhang_pct = round(100.0 * bad / tris, 2) if tris else 0.0
        # connectivity: union-find over vertex-welded triangles
        parent = list(range(len(vid)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for ids in tri_ids:
            ra, rb, rc = find(ids[0]), find(ids[1]), find(ids[2])
            if ra != rb:
                parent[ra] = rb
            if find(ids[0]) != rc:
                parent[find(ids[0])] = rc
        comps = len({find(i) for i in range(len(vid))}) if vid else 1

    overhang_ok = overhang_pct <= float(args.get("max_overhang_pct", 60.0))
    # a DELIBERATE assembly (fused from many named sources) prints as a
    # job of several shells — each shell is one printed item; only a
    # single part must be a single connected shell
    deliberate_assembly = (g.get("construction") or {}).get("op") in         ("scale-instance", "boolean")
    connected_ok = comps == 1 or deliberate_assembly
    height = dims[2]
    footprint = max(dims[0], dims[1], 1e-9)
    aspect = height / footprint
    warp_ok = aspect <= float(args.get("max_aspect", 12.0))

    evidence = [{"solver": "dfam/print", "tier": 2,
                 "min_dim_mm": round(min_dim, 3), "triangles": tris,
                 "overhang_pct": overhang_pct, "shells": comps,
                 "aspect_ratio": round(aspect, 2)}]
    obligations = [
        {"id": "wall-ok", "prop": f"min dimension >= {args.get('min_wall_mm', 0.5)}mm",
         "holds": min_wall_ok, "checker": "dfam",
         "detail": f"min_dim={min_dim:.2f}mm"},
        {"id": "overhang-ok", "prop": f"overhang <= {args.get('max_overhang_pct', 60)}%",
         "holds": overhang_ok, "checker": "dfam",
         "detail": f"{overhang_pct}% beyond {args.get('crit_angle_deg', 50)} deg"},
        {"id": "connected", "prop": "single connected shell",
         "holds": connected_ok, "checker": "dfam", "detail": f"{comps} shell(s)"},
        {"id": "warp-ok", "prop": f"aspect <= {args.get('max_aspect', 12)}",
         "holds": warp_ok, "checker": "dfam",
         "detail": f"height/footprint={aspect:.2f}"},
    ]
    return {}, evidence, obligations
