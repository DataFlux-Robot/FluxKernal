#!/usr/bin/env python3
"""Make an explicit STL-backed display derivative for OBJ-incompatible viewers.

The sealed native bundle is untouched. The preview generator reads its native model;
only mesh URLs change. Binary STL coordinates use float32, recorded in the ledger.
Use: python scripts/preview_urdf_bridge.py BUNDLE OUTPUT
"""

import argparse
import json
import struct
from pathlib import Path
import numpy as np
from fluxkernel.robotics.bundle import verify
from fluxkernel.robotics.native import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    output = args.output.resolve()
    verify(bundle)
    r = read(bundle)
    output.mkdir(parents=True, exist_ok=False)
    (output / "meshes").mkdir()
    aliases = {}
    max_error = 0.0
    for mesh in r["meshes"]:
        vertices = []
        faces = []
        for line in (bundle / mesh["file"]).read_text().splitlines():
            fields = line.split()
            if fields and fields[0] == "v":
                vertices.append([float(v) for v in fields[1:4]])
            elif fields and fields[0] == "f":
                faces.append([int(v) - 1 for v in fields[1:]])
        vertices = np.asarray(vertices)
        max_error = max(
            max_error, float(np.max(np.abs(vertices - vertices.astype(np.float32))))
        )
        raw = bytearray(
            b"FluxKernel viewer derivative; metres".ljust(80, b"\0")
        ) + struct.pack("<I", len(faces))
        for face in faces:
            if len(face) != 3:
                raise ValueError("Preview requires triangulated native OBJ")
            triangle = vertices[face]
            normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            norm = np.linalg.norm(normal)
            if norm:
                normal /= norm
            raw.extend(struct.pack("<12fH", *normal, *triangle.flatten(), 0))
        target = Path(mesh["file"]).with_suffix(".stl")
        (output / target).write_bytes(raw)
        aliases[mesh["file"]] = target.as_posix()
    # Skill-compatible generator retains the sealed native authority, not an edited XML.
    (output / "gen_urdf.py").write_text(
        "from pathlib import Path\nfrom fluxkernel.robotics.native import read\n"
        "from fluxkernel.robotics.projection import urdf_xml\n"
        f"BUNDLE=Path({str(bundle)!r})\nALIASES={aliases!r}\n"
        "def gen_urdf():\n    root=urdf_xml(read(BUNDLE))\n"
        '    for mesh in root.findall(".//mesh"):\n'
        '        mesh.set("filename",ALIASES[mesh.attrib["filename"]])\n'
        "    return root\n"
    )
    (output / "preview.json").write_text(
        json.dumps(
            {
                "authority": str(bundle),
                "purpose": "viewer-only derivative",
                "units": "m",
                "mesh_format": "binary STL float32",
                "max_coordinate_quantization_m": max_error,
                "physical_status": "unverified",
                "sealed_bundle_modified": False,
            },
            indent=2,
        )
    )
    print(output / "gen_urdf.py")


if __name__ == "__main__":
    main()
