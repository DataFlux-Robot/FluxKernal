"""Regenerate preview/index.html: aircraft + fabrication equipment.

Scene (all grounded geometry, along the fuselage axis which the viewer maps
to screen-horizontal):

  left   - ① the 1:20 aircraft mockup (5 parts, fin rotated, as assembled)
  center - ② the 3-axis mill bed (800x600x60, printed) with ③ the wing-rib
           workpiece (600x200x3) sitting on it — the machine that machines
           the rib that goes into the aircraft
  right  - ④ the reference printer frame (600x600x8) standing on edge —
           the generation-0 capital that printed the mill's bed

The two-generation loop this DAG actually contains: ④ prints ②, ② machines
③, ③ assembles into ①.  Spindle/drive/stepper/board are catalog items and
carry no geometry (honest rendering: only grounded shapes appear).

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
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


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

ASSEMBLY_SHIFT_Y = -1050
# mill: bed flat on the ground, rib workpiece lying on its top surface
BED = [0, 250, 0]
RIB_ON_BED = [-300, 150, 61.5]
# printer frame stood on edge to show its full 600x600 face
PFRAME = ([-4, 950, 600], ([0, 1, 0], 90.0))


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
mill = [("bed-solid", BED, None), ("rib-solid", RIB_ON_BED, None)]
printer = [("pframe-solid", PFRAME[0], PFRAME[1])]
GROUPS = [asm, mill, printer]

# Camera leveling: the preview page's default camera (yaw+pitch) makes a
# wide flat row drift diagonally on screen by sin(phi)sin(theta)/cos(phi) per
# mm of world-Y.  Pre-offsetting each group's Z by -k*(Yc - scene_Y_center)
# lands every group at the same screen height.  THETA/PHI must stay in sync
# with the camera defaults in preview.py's _PAGE.
THETA, PHI = 0.55, 0.3
K_LEVEL = math.sin(PHI) * math.sin(THETA) / math.cos(PHI)

ylo = min(group_box(g0)[0][1] for g0 in GROUPS)
yhi = max(group_box(g1)[1][1] for g1 in GROUPS)
CX = (ylo + yhi) / 2.0

# per-group dz = band-center on the printer frame's mid-height + leveling
plo, phi_ = group_box(printer)
Z0 = (plo[2] + phi_[2]) / 2.0
dz_of = {}
for key, g0 in zip(("asm", "mill", "printer"), GROUPS):
    lo, hi = group_box(g0)
    yc, zc = (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0
    dz_of[key] = (Z0 - zc) - K_LEVEL * (yc - CX)

shapes = [placed(name, [t[0], t[1], t[2] + dz_of[key]], rot)
          for key, g0 in zip(("asm", "mill", "printer"), GROUPS)
          for name, t, rot in g0]

# label anchors ride along with their group's dz so they stay glued to it
LABELS = [
    ("① 飞行器样机 1:20",
     [-260, ASSEMBLY_SHIFT_Y + 150, Z0 + dz_of["asm"] + 120], 34),
    ("② 3轴铣床身 800×600×60 · 打印制造",
     [-250, 40, Z0 + dz_of["mill"] + 50], 34),
    ("③ 翼肋 600×200×3 · 床上工件",
     [220, 460, Z0 + dz_of["mill"] + 60], 30),
    ("④ 打印机机架 600×600·自举",
     [0, 1230, Z0 + dz_of["printer"] + 320], 46),
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
                "SHA-PEK — 飞行器与加工设备 (aircraft + fabrication equipment)",
                "双代闭环 ④→②→③→①：打印机造床身 · 床身铣翼肋 · 翼肋装机 · "
                "主轴/电机/控制板为目录件（无几何）",
                labels=LABELS),
    encoding="utf-8")
n_tri = (len(stl_bytes) - 84) // 50
print(f"preview written: {out/'index.html'} | shapes: {len(shapes)} | "
      f"triangles: {n_tri} | stl: {len(stl_bytes)//1024} KB")
