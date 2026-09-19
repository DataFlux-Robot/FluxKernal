"""Regenerate preview/index.html showing ALL grounded geometry of sha_pek:

  left   — assembled 1:20 mockup (5 parts, fin rotated 90°, as placed)
  center — the same 5 parts in a manufactured-state exploded row
           (the fin shows as a flat plate: rotation is an assembly op)
  right  — the full-scale wing rib web (600x200x3 mm aluminum)

One fused coarse-mesh STL -> self-contained canvas page (file://-safe).
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


def placed(name, translation, rotation=None):
    payload = eng.store.get_object(eng.store.resolve(name))["payload"]
    shp = rebuild_brep(payload)
    tr = gp_Trsf()
    if rotation:
        axis, ang = rotation
        r = gp_Trsf()
        r.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), math.radians(ang))
        tr.SetTranslation(gp_Vec(*translation))
        tr = tr.Multiplied(r)
    else:
        tr.SetTranslation(gp_Vec(*translation))
    return BRepBuilderAPI_Transform(shp, tr, True).Shape()


def fuse(shapes):
    out = shapes[0]
    for s in shapes[1:]:
        out = BRepAlgoAPI_Fuse(out, s).Shape()
    return out


# assembly placements exactly as the assemble edge declared them
ASSEMBLY = [
    ("m-fuselage-solid", ([0, 0, 0], None)),
    ("m-wing-solid", ([0, 140, 30], None)),
    ("m-hstab-solid", ([0, 285, 20], None)),
    ("m-fin-solid", ([-1.5, 0, 25], ([0, 1, 0], 90.0))),
    ("m-motor-solid", ([0, 0, 0], None)),
]

# scene layout — all three groups along the fuselage axis (world +Y), which
# the viewer maps to screen-horizontal; the rib is stood up (rotY 90°) to show
# its full 600x200 face instead of a 3mm edge
ASSEMBLY_SHIFT_Y = -900
EXPLODED = [
    ("m-motor-solid", [0, 0, 0]),           # in front, as supplied
    ("m-fuselage-solid", [0, 380, 0]),
    ("m-wing-solid", [0, 830, 0]),          # flat plate, as made
    ("m-hstab-solid", [0, 1180, 0]),
    ("m-fin-solid", [0, 1430, 0]),          # flat, un-rotated
]
RIB = ([0, 1950, 660], ([0, 1, 0], 90.0))   # stood up at the row's end

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


def group_box(entries):
    """Combined bbox of a group of (name, translation, rotation) placements."""
    lo = [1e30] * 3
    hi = [-1e30] * 3
    for name, tr, rot in entries:
        box = Bnd_Box()
        BRepBndLib.Add_s(placed(name, tr, rot), box)
        mn, mx = box.CornerMin(), box.CornerMax()
        for k, f in enumerate((mn.X, mn.Y, mn.Z)):
            lo[k] = min(lo[k], f())
        for k, f in enumerate((mx.X, mx.Y, mx.Z)):
            hi[k] = max(hi[k], f())
    return lo, hi


asm = [(name, [t[0], t[1] + ASSEMBLY_SHIFT_Y, t[2]], rot)
       for name, (t, rot) in ASSEMBLY]
exp = [(name, t, None) for name, t in EXPLODED]
rib = [("rib-solid", RIB[0], RIB[1])]
GROUPS = [asm, exp, rib]

# Camera leveling: the preview page's default camera combines yaw+pitch, so a
# wide flat row drifts diagonally on screen by sin(phi)sin(theta)/cos(phi) per
# mm of world-Y.  Pre-offsetting each group's Z by -k*(Yc - scene_Y_center)
# lands every group at the same screen height.  THETA/PHI must stay in sync
# with the camera defaults in preview.py's _PAGE.
THETA, PHI = 0.55, 0.3
K_LEVEL = math.sin(PHI) * math.sin(THETA) / math.cos(PHI)

ylo = min(group_box(g0)[0][1] for g0 in GROUPS)
yhi = max(group_box(g0)[1][1] for g0 in GROUPS)
CX = (ylo + yhi) / 2.0

# per-group dz = band-center on the rib's mid-height + camera leveling
rlo, rhi = group_box(rib)
Z0 = (rlo[2] + rhi[2]) / 2.0
dz_of = {}
for key, g0 in zip(("asm", "exp", "rib"), GROUPS):
    lo, hi = group_box(g0)
    yc, zc = (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0
    dz_of[key] = (Z0 - zc) - K_LEVEL * (yc - CX)

shapes = [placed(name, [t[0], t[1], t[2] + dz_of[key]], rot)
          for key, g0 in zip(("asm", "exp", "rib"), GROUPS)
          for name, t, rot in g0]

# label anchors ride along with their group's dz so they stay glued to it
# (the rib spans Z0-300 .. Z0+300 around its own dz)
LABELS = [
    ("① 整机装配 1:20", [-260, ASSEMBLY_SHIFT_Y + 150, Z0 + dz_of["asm"] + 120], 34),
    ("② 分解零件 · 制造态", [0, 830, Z0 + dz_of["exp"] + 130], 34),
    ("③ 翼肋 600×200×3 · 全尺寸", [40, 2010, Z0 + dz_of["rib"] + 310], 48),
]

scene = fuse(shapes)

# coarse preview mesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer
BRepMesh_IncrementalMesh(scene, 1.0, False, 1.0, True)
stl_path = os.path.join(tempfile.mkdtemp(), "scene.stl")
sw = StlAPI_Writer()
sw.ASCIIMode = False
assert sw.Write(scene, stl_path)
stl_bytes = Path(stl_path).read_bytes()

out = REPO / "preview"
out.mkdir(exist_ok=True)
(out / "sha_pek_all.stl").write_bytes(stl_bytes)
(out / "index.html").write_text(
    render_page(stl_bytes,
                "SHA-PEK — 全部已接地几何 (all grounded geometry)",
                "① 装配体 ② 五零件分解列 ③ 全尺寸翼肋 · 同一场景按机身轴排布",
                labels=LABELS),
    encoding="utf-8")
n_tri = (len(stl_bytes) - 84) // 50
print(f"preview written: {out/'index.html'} | shapes: {len(shapes)} | "
      f"triangles: {n_tri} | stl: {len(stl_bytes)//1024} KB")
