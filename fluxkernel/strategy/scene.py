"""Shared scene assembly for the preview page and `fk render --png`.

One mesh pipeline, two consumers: the file://-safe HTML canvas renderer
(preview.py) and the offline matplotlib four-view renderer (render_png.py).
Binary STL carries the shape index in the per-triangle "attribute byte
count" field (uint16 at offset 48) — the standard extension slot — so a
single triangle soup still colors per part.

V2 palette: role-coded base colors (spec P7/V2).  Catalog-representative
geometry (V3) gets its own color so "representative envelope" is visible
at a glance.
"""
from __future__ import annotations

import struct

# role -> (r, g, b) base color, 0..255
PALETTE_ROLE = {
    "Part": (96, 144, 190),        # steel blue
    "Component": (214, 158, 72),   # amber
    "Medium": (128, 132, 140),     # gray
    "Resource": (186, 96, 72),     # brick red
    "System": (150, 120, 190),     # violet
    "Intent": (120, 190, 160),     # sea green
}
CATALOG_REPRESENTATIVE = (92, 178, 170)   # teal — V3 marker


def role_color(payload: dict) -> tuple[int, int, int]:
    """Base color of a node by role; catalog-representative geometry wins."""
    g = payload.get("ground") or {}
    c = g.get("construction") or {}
    if c.get("tier") == "catalog-representative" or c.get("op") == "catalog-geom":
        return CATALOG_REPRESENTATIVE
    return PALETTE_ROLE.get(payload.get("role", "Part"), PALETTE_ROLE["Part"])


def mesh_shape(shape, linear=0.08, angular=0.06):
    """Triangles of a TopoDS shape as [(nx,ny,nz, x1..z3), ...]."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.Poly import Poly_Triangulation
    from OCP.TopLoc import TopLoc_Location

    BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
    tris = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face(exp.Current())
        loc = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(face, loc)
        if poly is not None:
            trsf = loc.Transformation()
            nodes = []
            for i in range(1, poly.NbNodes() + 1):
                p = poly.Node(i).Transformed(trsf)
                nodes.append((p.X(), p.Y(), p.Z()))
            for i in range(1, poly.NbTriangles() + 1):
                a, b, c = poly.Triangle(i).Get()
                if a < 1 or b < 1 or c < 1:
                    continue
                p, q, r = nodes[a - 1], nodes[b - 1], nodes[c - 1]
                ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
                vx, vy, vz = r[0] - p[0], r[1] - p[1], r[2] - p[2]
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                ln = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
                tris.append((nx / ln, ny / ln, nz / ln,
                             *p, *q, *r))
        exp.Next()
    return tris


def write_stl_shapes(shapes) -> bytes:
    """Binary STL of [(shape, shape_index), ...]; index rides the uint16
    attribute field so consumers can color per part without separate
    meshes.  Returns bytes; callers also get the count via len/50."""
    groups = []
    for shape, idx in shapes:
        for t in mesh_shape(shape):
            groups.append((t, idx))
    n = len(groups)
    out = bytearray(84 + 50 * n)
    out[:80] = b"fk scene V2: uint16 attribute = shape index".ljust(80, b"\0")
    struct.pack_into("<I", out, 80, n)
    off = 84
    for t, idx in groups:
        struct.pack_into("<12fH", out, off,
                         t[0], t[1], t[2],          # normal
                         t[3], t[4], t[5],          # v1
                         t[6], t[7], t[8],          # v2
                         t[9], t[10], t[11],        # v3
                         idx & 0xFFFF)
        off += 50
    return bytes(out), n


def collect_grounded(eng):
    """[(name, payload, shape), ...] for the honest DAG geometry — every
    grounded node with construction, EXCEPT print outputs whose source
    solid is already in the set (same geometry twice = z-fighting)."""
    from ..solvers.feature3d import rebuild_brep, _silence_occt_messenger
    _silence_occt_messenger()
    grounded = {}
    for name in sorted(eng.store.names()):
        try:
            d = eng.store.resolve(name)
            payload = eng.store.get_object(d)["payload"]
        except KeyError:
            continue
        if payload.get("kind") == "params" or payload.get("role") in \
                ("Medium", "Intent"):
            continue
        if (payload.get("ground") or {}).get("construction"):
            grounded[d] = (name, payload)
    # print outputs duplicate their input solid — skip when source present
    skip = set()
    for _, e in eng.dag.iter_edges():
        if (e.get("transform") or {}).get("name") == "print" \
                and e.get("state") == "promoted":
            ins = e.get("inputs") or []
            if len(ins) >= 2 and ins[0] in grounded:
                skip.add(e.get("output", ""))
    out = []
    for d, (name, payload) in grounded.items():
        if d in skip:
            continue
        try:
            out.append((name, payload, rebuild_brep(payload)))
        except Exception:
            continue
    return out
