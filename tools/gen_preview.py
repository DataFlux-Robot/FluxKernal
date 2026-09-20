"""Regenerate preview/index.html: the REAL decomposition, at real scale.

Answers review v03's two observations directly — the wing you see IS the
decomposed wingbox (two skins, two spars, six ribs, all at their skeleton
frames), the machine IS a gantry mill (bed, columns, crossbeam, Z-head,
with rib-1 standing on the bed as the workpiece).  Plus the printer frame
and the 1:20 mockup DERIVED from the real subtree by scale-instance.

  group 1 — the whole aircraft 1:1 (wingbox parts + fuselage
            surfaces, all at their world :at placements)
  group 2 — gantry mill (shift +Y): bed/columns/crossbeam/z-head + rib-1
  group 3 — reference printer frame, stood on edge
  group 4 — derived 1:20 mockup (what the DAG declares, scaled)

Catalog items (spindle/rails/screws/servos/CNC) carry no geometry —
honest rendering: only grounded shapes appear.
"""
import math
import os
import tempfile
from pathlib import Path

from fluxkernel.store.objstore import Store
from fluxkernel.semantics.operators import Engine
from fluxkernel.interface.runner import Runner
from fluxkernel.solvers.feature3d import rebuild_brep, _silence_occt_messenger
from fluxkernel.strategy.preview import render_page

REPO = Path(__file__).resolve().parents[1]
_silence_occt_messenger()

td = tempfile.mkdtemp(prefix="fk-preview-")
eng = Engine(Store(os.path.join(td, ".fk")))
# rc==1 is expected: the script keeps one deliberately-rejected form (e2x)
Runner(eng).run((REPO / "examples" / "sha_pek.fcad").read_text(encoding="utf-8"))

from OCP.gp import gp_Trsf, gp_Vec, gp_Pnt, gp_Dir, gp_Ax1
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


def placed(name, translation, rotation=None, scale=None):
    payload = eng.store.get_object(eng.store.resolve(name))["payload"]
    shp = rebuild_brep(payload)
    tr = gp_Trsf()
    if scale:
        sc = gp_Trsf()
        sc.SetScale(gp_Pnt(0, 0, 0), scale)
        tr = tr.Multiplied(sc)
    if rotation:
        axis, ang = rotation
        r = gp_Trsf()
        r.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), math.radians(ang))
        tr = tr.Multiplied(r)
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(*translation))
    tr = t.Multiplied(tr)
    return BRepBuilderAPI_Transform(shp, tr, True).Shape()


def fuse(shapes):
    out = shapes[0]
    for s in shapes[1:]:
        out = BRepAlgoAPI_Fuse(out, s).Shape()
    return out


# ── group 1: the WHOLE AIRCRAFT at 1:1 — wingbox parts exactly as
# grounded, plus the fuselage surfaces at their aircraft-level :at frames
# (cabin above the wing centre, empennage behind the trailing edge,
# fin stood up) — the decomposed aircraft, every part where the DAG
# places it ──
WING = [f"wingbox/{n}/solid" for n in
        ("skin-upper", "skin-lower", "spar-front", "spar-rear",
         "rib-1", "rib-2", "rib-3", "rib-4", "rib-5", "rib-6")]
FUS = ["cabin-solid", "cwl-solid", "cwr-solid", "cbhf-solid", "cbhr-solid",
       "boom-solid", "hstab-solid", "fin-solid"]
wing = [(n, [0, 0, 0], None) for n in WING + FUS]

# ── group 2: the gantry mill; rib-1 stands on the bed as the workpiece ──
MILL_Y = 3200
mill = [(n, [0, MILL_Y, 0], None) for n in
        ("bed-solid", "colL-solid", "colR-solid", "beam-solid", "head-solid",
         "xcar-solid", "ycar-solid", "zcar-solid")]
# rib-1: translate its world frame onto the bed top (z 6 -> 60+MILL offset,
# x/y centred on the bed) — standing web, like a part in a fixture
rib = [("wingbox/rib-1/solid", [-750, MILL_Y - 750, 54], None)]

# ── group 3: the printer frame stood on edge ──
PRT_Y = 6300
printer = [("pframe-solid", [-4, PRT_Y, 600], ([0, 1, 0], 90.0))]

# ── group 4: the DERIVED 1:20 mockup ──
MK_Y = 6600
MK_DETAIL = 12.0           # detail-view magnification (preview only)
mockup = [("mockup-solid", [0, MK_Y, 0], None, MK_DETAIL)]

GROUPS = [("wing", wing), ("mill", mill + rib),
          ("printer", printer), ("mockup", mockup)]


def group_box(entries):
    lo, hi = [1e30] * 3, [-1e30] * 3
    for e in entries:
        name, tr, rot = e[0], e[1], (e[2] if len(e) > 2 else None)
        sc = e[3] if len(e) > 3 else None
        box = Bnd_Box()
        BRepBndLib.Add_s(placed(name, tr, rot, scale=sc), box)
        mn, mx = box.CornerMin(), box.CornerMax()
        for k, f in enumerate((mn.X, mn.Y, mn.Z)):
            lo[k] = min(lo[k], f())
        for k, f in enumerate((mx.X, mx.Y, mx.Z)):
            hi[k] = max(hi[k], f())
    return lo, hi


# camera leveling (see preview.py's camera defaults — keep in sync)
THETA, PHI = 0.55, 0.3
K_LEVEL = math.sin(PHI) * math.sin(THETA) / math.cos(PHI)

ylo = min(group_box(g)[0][1] for _, g in GROUPS)
yhi = max(group_box(g)[1][1] for _, g in GROUPS)
CX = (ylo + yhi) / 2.0

# band-center on the mill's mid-height (the tallest machine group)
mlo, mhi = group_box(GROUPS[1][1])
Z0 = (mlo[2] + mhi[2]) / 2.0
dz_of = {}
for key, g0 in GROUPS:
    lo, hi = group_box(g0)
    yc, zc = (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0
    dz_of[key] = (Z0 - zc) - K_LEVEL * (yc - CX)

shapes = [placed(name, [t[0], t[1], t[2] + dz_of[key]], rot,
                   scale=(e[3] if len(e) > 3 else None))
          for key, g0 in GROUPS for e in g0
          for name, t, rot in [(e[0], e[1], (e[2] if len(e) > 2 else None))]]

LABELS = [
    ("① 整机装配 1:1 · 翼盒（双蒙皮+双梁+6肋）+舱壳（地板/侧壁/隔框）+尾梁+平尾+垂尾",
     [1500, 750, Z0 + dz_of["wing"] + 240], 34),
    ("② gantry 铣床 · 床身/立柱/横梁/Z头 + rib-1 工件（打印制造）",
     [-600, MILL_Y - 500, Z0 + dz_of["mill"] + 260], 34),
    ("③ 打印机机架 600×600 · 自举",
     [0, PRT_Y - 300, Z0 + dz_of["printer"] + 320], 44),
    ("④ 派生样机 · 真实子树 1:20（视图放大 12×）",
     [0, MK_Y, Z0 + dz_of["mockup"] + 200], 34),
]

# V2: one triangle soup, per-part color — the shape index rides the STL
# uint16 attribute field (strategy/scene.py), the palette is role-coded
from fluxkernel.strategy import scene as fkscene
entries = []
for key, g0 in GROUPS:
    for e in g0:
        name, t = e[0], e[1]
        rot = e[2] if len(e) > 2 else None
        sc = e[3] if len(e) > 3 else None
        payload = eng.store.get_object(eng.store.resolve(name))["payload"]
        entries.append((placed(name, t, rot, scale=sc), fkscene.role_color(payload)))
stl_bytes, n_tri = fkscene.write_stl_shapes([(shp, i) for i, (shp, _) in enumerate(entries)])
shape_colors = [list(c) for _, c in entries]

out = REPO / "preview"
out.mkdir(exist_ok=True)
(out / "sha_pek_all.stl").write_bytes(stl_bytes)
(out / "index.html").write_text(
    render_page(stl_bytes,
                "SHA-PEK — 真实分解：wingbox · gantry 铣床 · 打印机 · 派生样机",
                "①=整机1:1 ②=机床架构 ③=打印机 ④=派生样机 · 颜色=角色 "
                "(蓝Part/琥珀Component/红Resource/青目录代表性)",
                labels=LABELS, shape_colors=shape_colors),
    encoding="utf-8")
print(f"preview written: {out/'index.html'} | shapes: {len(entries)} | "
      f"triangles: {n_tri} | stl: {len(stl_bytes)//1024} KB")
