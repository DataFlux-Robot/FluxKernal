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
        max_ang = math.cos(math.radians(90.0 - float(args.get("crit_angle_deg", 45))))
        bad = 0
        for i in range(min(n, 20000)):
            off = 84 + i * 50
            if off + 50 > len(data):
                break
            nx, ny, nz = struct.unpack("<fff", data[off:off + 12])
            vlen = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            tris += 1
            if (-nz / vlen) > -max_ang:   # downward-facing beyond critical angle
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
