#!/usr/bin/env python3
"""Case-level exact Lean/URDF/native preservation, with fresh Lean execution."""

import argparse
import json
from pathlib import Path

from fluxkernel.robotics.bundle import verify
from fluxkernel.robotics.lean_document import to_lean, from_lean, tree, sha
from fluxkernel.robotics.native import read
from fluxkernel.robotics.urdf_import import import_urdf
from fluxkernel.robotics.validation import check_projection


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", action="append", required=True, metavar="NAME=BUNDLE")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "fk-lossless-cases-v1", "cases": [], "model_calls": 0}
    for item in args.input:
        name, sep, path = item.partition("=")
        if not sep or not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Use NAME=BUNDLE with a simple case name")
        original = Path(path).resolve()
        before = verify(original, True)
        folder = args.output / name
        folder.mkdir()
        original_files = json.loads((original / "manifest.json").read_text())
        files = {
            n: sha((original / n).read_bytes())
            for n in [*original_files, "manifest.json"]
        }
        a = to_lean(original, folder / "lean")
        b = from_lean(folder / "lean", folder / "restored")
        restored = folder / "restored"
        c = to_lean(restored, folder / "lean-again")
        same_lean = (folder / "lean/Robot.lean").read_bytes() == (
            folder / "lean-again/Robot.lean"
        ).read_bytes()
        equal_files = all(
            sha((restored / n).read_bytes()) == value for n, value in files.items()
        )
        same_source = all(
            sha((original / n).read_bytes()) == value for n, value in files.items()
        )
        proof = verify(restored, True)
        projection = check_projection(restored)
        # Independent full-document reconstruction: no native sidecar and no XML cache.
        standalone = folder / "standalone-lean"
        to_lean(original / "robot.urdf", standalone)
        (standalone / "source.urdf").unlink()
        d = from_lean(standalone, folder / "lean-generated")
        regenerated = folder / "lean-generated/robot.urdf"
        equal_tree = tree(regenerated.read_bytes()) == tree(
            (original / "robot.urdf").read_bytes()
        )
        consumer = import_urdf(regenerated, folder / "consumer")
        r = read(original)
        accepted = all(
            [
                same_lean,
                equal_files,
                same_source,
                equal_tree,
                before["proof_accepted"],
                proof["proof_accepted"],
                projection["accepted"],
                consumer["proof_accepted"],
                consumer["projection_accepted"],
            ]
        )
        report["cases"].append(
            {
                "name": name,
                "source": str(original),
                "to_lean": a,
                "from_lean": b,
                "lean_again": c,
                "standalone_from_lean": d,
                "native": {
                    "bodies": len(r["bodies"]),
                    "joints": len(r["joints"]),
                    "actuators": len(r["actuators"]),
                    "meshes": len(r["meshes"]),
                },
                "lean_bytes_equal": same_lean,
                "all_native_file_bytes_equal": equal_files,
                "source_unchanged": same_source,
                "complete_xml_tree_equal": equal_tree,
                "source_file_sha256": files,
                "proof": proof,
                "projection": projection,
                "standalone_consumer": consumer,
                "accepted": accepted,
            }
        )
        (args.output / "benchmark.json").write_text(json.dumps(report, indent=2))
        print(
            name,
            "accepted=" + str(accepted),
            "sealed_files=" + str(len(files)),
            flush=True,
        )
    report["accepted"] = all(c["accepted"] for c in report["cases"])
    (args.output / "benchmark.json").write_text(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
