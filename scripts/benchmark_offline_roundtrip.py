#!/usr/bin/env python3
"""Test local sealed bundles through both conversion directions and XML-free export.

Run under scripts/without_network.py to enforce the offline acceptance condition.
Inputs and their assets must already be installed; this script never acquires them.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from fluxkernel.robotics import lean_document, lean_runtime, urdf_assets
from fluxkernel.robotics.lean_document import to_lean, from_lean, tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = {
        "lean_binary": str(lean_runtime.lean_binary()),
        "implementations": {
            module.__name__: hashlib.sha256(
                Path(module.__file__).read_bytes()
            ).hexdigest()
            for module in (lean_document, lean_runtime, urdf_assets)
        },
        "cases": [],
    }
    for bundle in args.bundles:
        result = {"source": str(bundle), "accepted": False}
        try:
            with tempfile.TemporaryDirectory(prefix="fk-offline-acceptance-") as tmp:
                root = Path(tmp)
                to_lean(bundle, root / "original")
                # Move the package, so no original absolute package path survives.
                shutil.move(root / "original", root / "relocated")
                restored = from_lean(root / "relocated", root / "restored")
                assert restored["native_bundle_restored"]
                files = json.loads((bundle / "manifest.json").read_text())
                for name in [*files, "manifest.json"]:
                    assert (bundle / name).read_bytes() == (
                        root / "restored" / name
                    ).read_bytes()
                to_lean(root / "restored", root / "again")
                assert (root / "relocated/Robot.lean").read_bytes() == (
                    root / "again/Robot.lean"
                ).read_bytes()
                # URDF-only package: no original XML or native sidecar available.
                to_lean(bundle / "robot.urdf", root / "standalone")
                (root / "standalone/source.urdf").unlink()
                generated = from_lean(root / "standalone", root / "generated")
                assert not generated["lexical_bytes_restored"]
                assert tree((root / "generated/robot.urdf").read_bytes()) == tree(
                    (bundle / "robot.urdf").read_bytes()
                )
                result.update(
                    accepted=True,
                    sealed_files=len(files) + 1,
                    sealed_bytes_equal=True,
                    lean_source_equal=True,
                    xml_free_reconstruction=True,
                    relocated_package=True,
                )
        except Exception as exc:
            result["error"] = str(exc)
        report["cases"].append(result)
        print(json.dumps(result), flush=True)
    report["accepted"] = all(c["accepted"] for c in report["cases"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    if not report["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
