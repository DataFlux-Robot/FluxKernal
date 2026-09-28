#!/usr/bin/env python3
"""Reproduce pinned native robot imports, Lean checks and numeric projections.

Downloads model data unless --source-cache contains verified microduck/xgoduck
snapshots. No upstream code, policy weights or model API is executed.
"""

import argparse
import json
import shutil
from pathlib import Path
from fluxkernel.robotics.bundle import import_robot, finish, verify, seal
from fluxkernel.robotics.native import read, write
from fluxkernel.robotics.sources import hardware_inventory
from fluxkernel.robotics.validation import check_projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path)
    parser.add_argument("--include-hardware", action="store_true")
    parser.add_argument("--hardware-cache", type=Path)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    results = []
    for name in ("microduck", "xgoduck"):
        cached = args.source_cache / name if args.source_cache else None
        result = import_robot(name, args.output, cached)
        root = Path(result["directory"])
        if name == "xgoduck" and args.include_hardware:
            if args.hardware_cache:
                shutil.copytree(args.hardware_cache, root / "hardware")
            r = read(root)
            r["manufacturing"] = hardware_inventory(root / "hardware")
            result = finish(r, root)
        if args.render:
            from fluxkernel.robotics.render import render

            render(root, root / "views.png")
            seal(root)
        result["verification"] = verify(root, rerun_proof=True)
        result["projection"] = check_projection(root)
        results.append(result)
    a, b = (read(r["directory"]) for r in results)
    report = {
        "schema": "fk-robot-benchmark-v1",
        "model_calls": 0,
        "accepted": all(
            r["proof_accepted"]
            and r["verification"]["accepted"]
            and r["projection"]["accepted"]
            for r in results
        ),
        "robots": results,
        "cross_platform": {
            "same_plant": a["controller"]["plant_sha256"]
            == b["controller"]["plant_sha256"],
            "same_servo_family": a["controller"]["servo_family"]
            == b["controller"]["servo_family"],
            "policy_transfer_approved": False,
        },
        "physical_status": "unverified",
    }
    write(args.output / "benchmark.json", report)
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
