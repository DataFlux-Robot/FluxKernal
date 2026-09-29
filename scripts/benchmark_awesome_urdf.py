#!/usr/bin/env python3
"""Run every inventoried URDF through real Lean; retain each failure explicitly.

Document preservation is distinct from asset packaging and simulator acceptance.
The document lane removes dependence on the lexical snapshot by invoking Lean on
the full value and comparing its output tree and regenerated Lean source directly.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import traceback


def check(case, output, package):
    from fluxkernel.robotics.lean_document import (
        Reader,
        render_lean,
        source,
        tree,
        to_lean,
        from_lean,
    )
    from fluxkernel.robotics.urdf_import import xml_root

    directory = Path(output) / case["case_id"]
    directory.mkdir(parents=True, exist_ok=True)
    result = {
        "case_id": case["case_id"],
        "entry_ids": case["entry_ids"],
        "source_sha256": case.get("sha256"),
        "path": case["path"],
        "repository": case["repository"],
        "commit": case["commit"],
    }
    start = time.monotonic()
    try:
        raw = Path(case["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case["sha256"]
        n = tree(raw)
        text = source(n, [], [], case["sha256"])
        assert Reader(text).read() == (n, [], [], case["sha256"])
        rendered = render_lean(text)
        assert tree(rendered) == n, "Lean changed XML information"
        assert source(tree(rendered), [], [], case["sha256"]) == text, (
            "Lean return trip differs"
        )
        (directory / "Robot.lean").write_text(text)
        (directory / "lean-generated.urdf").write_bytes(rendered)
        xml = xml_root(raw)
        result["document"] = {
            "status": "passed",
            "lean_executed": True,
            "complete_tree_equal": True,
            "lean_source_equal": True,
            "source_xml_needed": False,
            "links": len(xml.findall("link")),
            "joints": len(xml.findall("joint")),
            "has_unexpanded_expression": b"${" in raw or b"$(find" in raw,
            "lean_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
    except Exception as exc:
        result["document"] = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[-2500:],
        }
        (directory / "failure.txt").write_text(traceback.format_exc())
    if package:
        try:
            with tempfile.TemporaryDirectory(prefix="fk-awesome-") as tmp:
                tmp = Path(tmp)
                a = to_lean(case["file"], tmp / "lean")
                b = from_lean(tmp / "lean", tmp / "restored")
                assert (tmp / "restored/robot.urdf").read_bytes() == raw
                to_lean(tmp / "restored/robot.urdf", tmp / "again")
                assert (tmp / "lean/Robot.lean").read_bytes() == (
                    tmp / "again/Robot.lean"
                ).read_bytes()
                result["package"] = {
                    "status": "passed",
                    "asset_count": a["asset_count"],
                    "urdf_bytes_equal": True,
                    "asset_bytes_equal": b["asset_bytes_equal"],
                    "lean_source_equal": True,
                }
        except Exception as exc:
            result["package"] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[-1500:],
            }
    result["elapsed_seconds"] = time.monotonic() - start
    (directory / "result.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--packages", action="store_true")
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "catalog_commit": inventory["catalog_commit"],
        "catalog_entries": len(inventory["scopes"]),
        "unique_urdf_files": len(inventory["cases"]),
        "model_calls": 0,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "cases": [],
        "scope": "Full XML information preservation; not physical or complete simulator verification",
    }
    from fluxkernel.robotics import lean_document

    report["implementation_sha256"] = hashlib.sha256(
        Path(lean_document.__file__).read_bytes()
    ).hexdigest()
    from fluxkernel.robotics import urdf_assets

    report["asset_implementation_sha256"] = hashlib.sha256(
        Path(urdf_assets.__file__).read_bytes()
    ).hexdigest()
    from fluxkernel.robotics import lean_runtime

    report["runtime_implementation_sha256"] = hashlib.sha256(
        Path(lean_runtime.__file__).read_bytes()
    ).hexdigest()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = []
        for case in inventory["cases"]:
            # Reexecute even when output exists: source hashes alone do not bind
            # the runtime, compiler, assets or benchmark implementation.
            pending.append(pool.submit(check, case, str(args.output), args.packages))
        for future in as_completed(pending):
            report["cases"].append(future.result())
            if len(report["cases"]) % 10 == 0:
                print(
                    "checked",
                    len(report["cases"]),
                    "/",
                    len(inventory["cases"]),
                    flush=True,
                )
            (args.output / "report.json").write_text(json.dumps(report, indent=2))
    report["cases"].sort(key=lambda c: c["case_id"])
    report["document_passed"] = sum(
        c["document"]["status"] == "passed" for c in report["cases"]
    )
    report["package_passed"] = sum(
        c.get("package", {}).get("status") == "passed" for c in report["cases"]
    )
    report["completed"] = len(report["cases"]) == len(inventory["cases"])
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    print(
        "Completed",
        report["completed"],
        "document passed",
        report["document_passed"],
        "/",
        report["unique_urdf_files"],
        flush=True,
    )


if __name__ == "__main__":
    main()
