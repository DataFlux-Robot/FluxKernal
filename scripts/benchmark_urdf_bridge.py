#!/usr/bin/env python3
"""Offline URDF import, actual Lean recheck, second round trip and consumer checks.

Use repeated --input NAME=FILE arguments. Inputs and prior bundles stay unchanged.
No model calls, upstream execution or network fetching occurs in this benchmark.
"""

import argparse
import hashlib
import json
from pathlib import Path
from fluxkernel.robotics.urdf_import import import_urdf
from fluxkernel.robotics.bundle import verify
from fluxkernel.robotics.native import read, write
from fluxkernel.robotics.validation import check_projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, metavar="NAME=FILE")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "fk-urdf-bridge-benchmark-v1",
        "model_calls": 0,
        "cases": [],
        "physical_status": "unverified",
    }
    for item in args.input:
        name, sep, value = item.partition("=")
        if not name or not sep:
            parser.error("Use NAME=FILE")
        path = Path(value).resolve()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        source_verification = (
            verify(path.parent, True)
            if (path.parent / "robot.json").is_file()
            else None
        )
        first = import_urdf(path, args.output)
        root = Path(first["directory"])
        check = verify(root, True)
        projection = check_projection(root)
        second = import_urdf(root / "robot.urdf", args.output)
        child = Path(second["directory"])
        second_check = verify(child, True)
        second_projection = check_projection(child)
        r = read(root)
        rr = read(child)
        accepted = (
            first["proof_accepted"]
            and second["proof_accepted"]
            and check["exchange"]["accepted"]
            and second_check["exchange"]["accepted"]
            and projection["accepted"]
            and second_projection["accepted"]
            and [(b["name"], b["parent"]) for b in r["bodies"]]
            == [(b["name"], b["parent"]) for b in rr["bodies"]]
            and len(r["joints"]) == len(rr["joints"])
            and before == hashlib.sha256(path.read_bytes()).hexdigest()
        )
        report["cases"].append(
            {
                "name": name,
                "source": str(path),
                "source_sha256": before,
                "source_verification": source_verification,
                "first": first,
                "second": second,
                "verification": check,
                "projection": projection,
                "second_verification": second_check,
                "second_projection": second_projection,
                "source_unchanged": True,
                "accepted": bool(accepted),
            }
        )
        write(args.output / "benchmark.json", report)
    report["accepted"] = all(c["accepted"] for c in report["cases"])
    write(args.output / "benchmark.json", report)
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
