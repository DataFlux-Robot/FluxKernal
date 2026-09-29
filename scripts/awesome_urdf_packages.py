#!/usr/bin/env python3
"""Test the public complete-package API separately from document-only checks."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import posixpath
import tempfile


def check(case, asset_case, resources):
    from fluxkernel.robotics.lean_document import to_lean, from_lean

    result = {
        "case_id": case["case_id"],
        "entry_ids": case["entry_ids"],
        "status": "failed",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="fk-awesome-package-") as tmp:
            root = Path(tmp)
            a = to_lean(case["file"], root / "lean")
            b = from_lean(root / "lean", root / "restored")
            assert (root / "restored/robot.urdf").read_bytes() == Path(
                case["file"]
            ).read_bytes()
            to_lean(root / "restored/robot.urdf", root / "again")
            assert (root / "lean/Robot.lean").read_bytes() == (
                root / "again/Robot.lean"
            ).read_bytes()
            result.update(
                primary_roundtrip=True,
                urdf_bytes_equal=True,
                asset_bytes_equal=b["asset_bytes_equal"],
                lean_source_equal=True,
                asset_count=a["asset_count"],
            )
            missing = []
            seen = set()

            def dependencies(key, logical):
                if (key, logical) in seen:
                    return
                seen.add((key, logical))
                for dep in resources[key].get("dependencies", []):
                    target = posixpath.normpath(
                        posixpath.join(
                            posixpath.dirname(logical),
                            posixpath.relpath(
                                dep["path"], posixpath.dirname(resources[key]["path"])
                            ),
                        )
                    )
                    file = (root / "restored" / target).resolve()
                    record = resources[dep["resource_key"]]
                    if (
                        not file.is_relative_to(root / "restored")
                        or not file.is_file()
                        or hashlib.sha256(file.read_bytes()).hexdigest()
                        != record.get("sha256")
                    ):
                        missing.append(
                            {"path": target, "resource_key": dep["resource_key"]}
                        )
                    dependencies(dep["resource_key"], target)

            if asset_case.get("complete"):
                for ref in asset_case["references"]:
                    dependencies(ref["resource_key"], ref["uri"])
                result["dependency_closure"] = (
                    "omitted_by_export" if missing else "preserved"
                )
                result["missing_dependencies"] = missing
                if not missing:
                    result["status"] = "passed"
            else:
                result["dependency_closure"] = "source_dependencies_unavailable"
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc)[-1800:])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inventory", type=Path)
    p.add_argument("assets", type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    inventory = json.loads(args.inventory.read_text())
    assets = json.loads(args.assets.read_text())
    assert assets["completed"], (
        "Wait for asset acquisition before measuring package failures"
    )
    asset_cases = {c["case_id"]: c for c in assets["cases"]}
    resources = assets["resources"]
    results = []
    from fluxkernel.robotics import lean_document

    report = {
        "implementation_sha256": hashlib.sha256(
            Path(lean_document.__file__).read_bytes()
        ).hexdigest(),
        "cases": results,
        "completed": False,
    }
    from fluxkernel.robotics import urdf_assets

    report["asset_implementation_sha256"] = hashlib.sha256(
        Path(urdf_assets.__file__).read_bytes()
    ).hexdigest()
    from fluxkernel.robotics import lean_runtime

    report["runtime_implementation_sha256"] = hashlib.sha256(
        Path(lean_runtime.__file__).read_bytes()
    ).hexdigest()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(check, c, asset_cases[c["case_id"]], resources)
            for c in inventory["cases"]
        ]
        for f in as_completed(futures):
            results.append(f.result())
            if len(results) % 25 == 0:
                print(
                    "package checked",
                    len(results),
                    "/",
                    len(inventory["cases"]),
                    flush=True,
                )
            args.output.write_text(json.dumps(report, indent=2))
    report.update(
        completed=True,
        total=len(results),
        passed=sum(c["status"] == "passed" for c in results),
        primary_passed=sum(bool(c.get("primary_roundtrip")) for c in results),
    )
    args.output.write_text(json.dumps(report, indent=2))
    print(
        "Complete package passed",
        report["passed"],
        "/",
        report["total"],
        "primary bytes passed",
        report["primary_passed"],
        flush=True,
    )


if __name__ == "__main__":
    main()
