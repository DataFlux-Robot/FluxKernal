"""Finite, data-only decorative-part recipes. CAD in mm; native meshes in m."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Vector = Annotated[list[Number], Field(min_length=3, max_length=3)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Feature(Strict):
    shape: Literal["box", "ellipsoid", "fin"]
    size_mm: Annotated[
        list[Annotated[float, Field(strict=True, ge=1, le=80, allow_inf_nan=False)]],
        Field(min_length=3, max_length=3),
    ]
    center_mm: Vector
    rotation_deg: Vector


class Recipe(Strict):
    schema_version: Literal["fk-robot-part-v1"]
    zone_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    rationale: str = Field(min_length=1, max_length=1800)
    symmetry: Literal["bilateral", "none"]
    material: Literal["pla", "petg"]
    color_rgb: Annotated[
        list[Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]],
        Field(min_length=3, max_length=3),
    ]
    base_size_mm: tuple[
        Annotated[float, Field(strict=True, ge=4, le=24)],
        Annotated[float, Field(strict=True, ge=4, le=24)],
        Annotated[float, Field(strict=True, ge=1, le=4)],
    ]
    features: list[Feature] = Field(min_length=1, max_length=8)


def checked(recipe):
    r = Recipe.model_validate(recipe)
    if not (
        4 <= r.base_size_mm[0] <= 24
        and 4 <= r.base_size_mm[1] <= 24
        and 1 <= r.base_size_mm[2] <= 4
    ):
        raise ValueError("Base dimensions must be [4..24,4..24,1..4] mm")
    if any(not 0 <= x <= 1 for x in r.color_rgb):
        raise ValueError("RGB must be in 0..1")
    for f in r.features:
        if any(not 1 <= x <= 80 for x in f.size_mm):
            raise ValueError("Feature dimensions must be 1..80 mm")
        if any(abs(x) > 80 for x in f.center_mm):
            raise ValueError("Feature centers outside bounded recipe")
        if any(abs(x) > 180 for x in f.rotation_deg):
            raise ValueError("Rotation outside -180..180 degrees")
        if r.symmetry == "bilateral" and f.center_mm[1] < 0:
            raise ValueError(
                "Bilateral source features use Y >= 0; host mirrors across Y=0"
            )
    return r


def generate(recipe):
    """Return a labeled build123d solid; execute no source provided by a model."""
    import build123d as b
    from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform
    from OCP.gp import gp_GTrsf, gp_Mat

    r = checked(recipe)
    shape = b.extrude(
        b.Ellipse(r.base_size_mm[0] / 2, r.base_size_mm[1] / 2), r.base_size_mm[2]
    )
    for f in r.features:
        x, y, z = f.size_mm
        if f.shape == "box":
            part = b.Box(x, y, z)
        elif f.shape == "ellipsoid":
            transform = gp_GTrsf()
            transform.SetVectorialPart(gp_Mat(x / 2, 0, 0, 0, y / 2, 0, 0, 0, z / 2))
            part = b.Shape.cast(
                BRepBuilderAPI_GTransform(
                    b.Solid.make_sphere(1).wrapped, transform, True
                ).Shape()
            )
        else:
            # Triangular fin in YZ, thickness X, bounding box centered at origin.
            wire = b.Wire.make_polygon(
                [(-x / 2, -y / 2, -z / 2), (-x / 2, y / 2, -z / 2), (-x / 2, 0, z / 2)],
                close=True,
            )
            part = b.extrude(b.Face(wire), x, dir=(1, 0, 0))
        part = part.moved(b.Location(f.center_mm, f.rotation_deg))
        shape = shape.fuse(part)
        # An unrotated feature centered on Y=0 already equals its reflection.
        # Avoid a coincident duplicate in the OCCT Boolean operation.
        if r.symmetry == "bilateral" and (f.center_mm[1] != 0 or any(f.rotation_deg)):
            shape = shape.fuse(part.mirror(b.Plane.XZ))
    shape = shape.clean()
    if not shape.is_valid or len(shape.solids()) != 1 or shape.volume <= 0:
        raise ValueError(
            "Recipe must produce one valid connected positive-volume solid; "
            f"got valid={shape.is_valid}, solids={len(shape.solids())}, "
            f"volume_mm3={shape.volume}; features must overlap"
        )
    shape.label = r.name
    return shape


def export(recipe, output):
    import build123d as b
    import numpy as np
    from scipy.spatial.transform import Rotation
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from ..solvers.feature3d import _silence_occt_messenger
    from .native import write

    r = checked(recipe)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    write(root / "recipe.json", r.model_dump())
    (root / "part.py").write_text(
        'from pathlib import Path\nimport json\nfrom fluxkernel.robotics.part_geometry import generate\ndef gen_step():\n    return generate(json.loads(Path(__file__).with_name("recipe.json").read_text()))\n'
    )
    shape = generate(r.model_dump())
    box = shape.bounding_box()
    bounds = [[float(x) for x in box.min], [float(x) for x in box.max]]
    if bounds[0][2] < -1e-5:
        raise ValueError(
            "No geometry may extend below the fixed mounting plane Z=0; "
            f"actual bbox_mm={bounds}"
        )
    _silence_occt_messenger()
    if not b.export_step(shape, root / "part.step") or not b.export_stl(
        shape, root / "part.stl", tolerance=0.08
    ):
        raise ValueError("CAD export failed")
    vertices, faces = shape.tessellate(0.08, 0.1)
    lines = ["# FluxKernel CAD tessellation; metres"]
    lines += [
        "v " + " ".join(format(float(x) / 1000, ".17g") for x in v) for v in vertices
    ]
    lines += ["f " + " ".join(str(i + 1) for i in f) for f in faces]
    (root / "part.obj").write_text("\n".join(lines) + "\n")
    vp = GProp_GProps()
    # Adaptive integration is required for trimmed affine ellipsoid surfaces.
    # The default fixed quadrature changes with STEP's surface representation.
    error = BRepGProp.VolumePropertiesGK_s(shape.wrapped, vp, 1e-8, False, True, False, False)
    if error < 0:
        raise ValueError("Adaptive CAD mass integration failed")
    moments_props = GProp_GProps()
    # Fixed Gaussian moment integration is more stable than the adaptive
    # volume-driven stopping rule for inertial tensors (see cylinder regression).
    BRepGProp.VolumeProperties_s(shape.wrapped, moments_props)
    density = {"pla": 1240.0, "petg": 1270.0}[r.material]
    tensor = (
        np.array(
            [
                [moments_props.MatrixOfInertia().Value(i + 1, j + 1) for j in range(3)]
                for i in range(3)
            ]
        )
        * density
        * 1e-15
        * vp.Mass() / moments_props.Mass()
    )
    moments, axes = np.linalg.eigh(tensor)
    if np.linalg.det(axes) < 0:
        axes[:, 0] *= -1
    q = Rotation.from_matrix(axes).as_quat()
    com = moments_props.CentreOfMass()
    result = {
        "bbox_mm": bounds,
        "volume_mm3": vp.Mass(),
        "mass_kg": vp.Mass() * density * 1e-9,
        "inertial_position": [com.X() / 1000, com.Y() / 1000, com.Z() / 1000],
        "principal_inertia": moments.tolist(),
        "inertial_quaternion": [q[3], *q[:3]],
        "vertices": len(vertices),
        "faces": len(faces),
        "solids": 1,
        "density_kg_m3": density,
        "mass_basis": "Uniform solid CAD and declared nominal polymer density; not measured print mass",
        "integration": "Gauss-Kronrod volume (1e-8); fixed Gaussian COM/inertia, inertia normalized to GK mass. Numerical estimates, not physical measurements.",
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.iterdir()
            if p.is_file()
        },
    }
    write(root / "properties.json", result)
    return result


if __name__ == "__main__":
    import sys

    export(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2])
