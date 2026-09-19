"""Regenerate preview/index.html for the SHA-PEK mockup: rebuild the five
grounded parts, apply assemble placements, fuse, coarse-mesh, embed base64."""
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

placements = [
    ([0, 0, 0], None),
    ([0, 140, 30], None),
    ([0, 285, 20], None),
    ([-1.5, 0, 25], ([0, 1, 0], 90.0)),      # fin: rotY 90°, then translate
    ([0, -8, 0], None),
]
parts = ["m-fuselage", "m-wing", "m-hstab", "m-fin", "m-motor"]

from OCP.gp import gp_Trsf, gp_Vec, gp_Pnt, gp_Dir, gp_Ax1
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

shapes = []
for name, (t, rot) in zip(parts, placements):
    payload = eng.store.get_object(eng.store.resolve(f"{name}-solid"))["payload"]
    shp = rebuild_brep(payload)
    tr = gp_Trsf()
    if rot:
        axis, ang = rot
        r = gp_Trsf()
        r.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), math.radians(ang))
        tr.SetTranslation(gp_Vec(*t))
        tr = tr.Multiplied(r)
    else:
        tr.SetTranslation(gp_Vec(*t))
    shapes.append(BRepBuilderAPI_Transform(shp, tr, True).Shape())

fused = shapes[0]
for s in shapes[1:]:
    fused = BRepAlgoAPI_Fuse(fused, s).Shape()

# coarse preview mesh (deflection 1.0 mm on a ~560 mm model)
import tempfile as tf
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer
BRepMesh_IncrementalMesh(fused, 1.0, False, 1.0, True)
stl_path = os.path.join(tf.mkdtemp(), "model.stl")
sw = StlAPI_Writer()
sw.ASCIIMode = False               # binary STL
assert sw.Write(fused, stl_path)
stl_bytes = Path(stl_path).read_bytes()

out = REPO / "preview"
out.mkdir(exist_ok=True)
(out / "sha_pek_model.stl").write_bytes(stl_bytes)
(out / "index.html").write_text(
    render_page(stl_bytes, "SHA-PEK 1:20 mockup — sha-pek-model"), encoding="utf-8")
n_tri = (len(stl_bytes) - 84) // 50
print(f"preview written: {out/'index.html'} | triangles: {n_tri} | "
      f"stl: {len(stl_bytes)//1024} KB")
