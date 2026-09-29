#!/usr/bin/env python3
"""Test every pinned catalog URDF in both directions, with separate asset results.

Run under without_network.py after acquisition. Never executes upstream code.
Document checks preserve all XML fields, but do not bind external asset files.
Complete-package checks use the public API and an independent dependency ledger.
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from fluxkernel.robotics import lean_document, lean_runtime, urdf_assets
from fluxkernel.robotics.lean_document import (
    Reader,
    from_lean,
    load,
    render_lean,
    source,
    to_lean,
    tree,
)

from awesome_urdf_packages import check as check_asset_closure


CHECKS = (
    "document_urdf_lean_urdf",
    "document_lean_urdf_lean",
    "document_lean_edit",
    "document_executable_rejected",
    "package_urdf_lean_urdf",
    "package_lean_urdf_lean",
    "package_xml_free",
    "package_stale_snapshot_rejected",
    "package_lean_edit",
    "package_asset_tamper_rejected",
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def xml_value(raw):
    """Independent namespace-expanded XML oracle, alongside the Expat tree."""

    def node(e):
        return [
            e.tag,
            sorted(e.attrib.items()),
            e.text or "",
            e.tail or "",
            [node(child) for child in e],
        ]

    return node(ET.fromstring(raw))


def changed_document(n, raw, case_id):
    """Explicit test perturbations only; never modify the source robot on disk."""
    changed = copy.deepcopy(n)
    expected = ET.fromstring(raw)
    name = "fk_roundtrip_" + case_id
    changed[1] = [[k, v] for k, v in changed[1] if k != "name"] + [["name", name]]
    expected.set("name", name)
    mass_value = "1.2345678901234567890123456789"

    def edit_mass(node):
        if isinstance(node, str):
            return False
        if node[0] == "mass" and any(k == "value" for k, _ in node[1]):
            node[1] = [[k, mass_value if k == "value" else v] for k, v in node[1]]
            return True
        return any(edit_mass(child) for child in node[2])

    numeric = edit_mass(changed)
    if numeric:
        next(e for e in expected.iter("mass") if "value" in e.attrib).set(
            "value", mass_value
        )
    return changed, xml_value(ET.tostring(expected)), numeric


def checked(result, key, operation):
    start = time.monotonic()
    try:
        details = operation() or {}
        result["checks"][key] = {"status": "passed", **details}
    except Exception as exc:
        result["checks"][key] = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[-1800:],
        }
    result["checks"][key]["elapsed_seconds"] = round(time.monotonic() - start, 3)


def rejected(operation, message):
    try:
        operation()
    except ValueError as exc:
        assert message in str(exc), f"Unexpected rejection: {exc}"
    else:
        raise AssertionError("Invalid input was accepted")


def documents(raw, case, directory, result):
    n = tree(raw)
    text = source(n, [], [], digest(raw))
    (directory / "Robot.lean").write_text(text)
    independent = xml_value(raw)

    def forward():
        assert Reader(text).read() == (n, [], [], digest(raw))
        output = render_lean(text)
        assert tree(output) == n, "Forward XML tree mismatch"
        assert xml_value(output) == independent, "Independent XML oracle mismatch"
        (directory / "lean-generated.urdf").write_bytes(output)
        return {
            "real_lean_executions": 1,
            "xml_tree_equal": True,
            "independent_xml_equal": True,
            "input_sha256": digest(raw),
            "lean_sha256": digest(text.encode()),
            "output_sha256": digest(output),
        }

    def reverse():
        # Fresh real Lean run from the on-disk term. Its temporary compiler root
        # contains no source.urdf or upstream XML; do not reuse forward's output.
        seed = (directory / "Robot.lean").read_text()
        value, assets, native, lexical = Reader(seed).read()
        output = render_lean(source(value, assets, native, lexical))
        assert xml_value(output) == independent
        back = source(tree(output), assets, native, lexical)
        assert back == seed, "Reverse Lean term changed"
        rerendered = render_lean(back)
        assert tree(rerendered) == value
        assert xml_value(rerendered) == independent
        return {
            "real_lean_executions": 2,
            "lean_term_bytes_equal": True,
            "original_xml_supplied_to_lean": False,
            "lexical_digest_preserved_as_binding": True,
        }

    def edit():
        modified, expected, numeric = changed_document(n, raw, case["case_id"])
        edited = source(modified, [], [], digest(raw))
        output = render_lean(edited)
        assert tree(output) == modified, "Lean edit failed to reach URDF"
        assert xml_value(output) == expected, "Independent edit oracle mismatch"
        assert tree(output) != n, "Stale original robot was returned"
        assert source(tree(output), [], [], digest(raw)) == edited
        return {
            "real_lean_executions": 1,
            "robot_name_changed": True,
            "long_decimal_mass_changed": numeric,
            "other_xml_fields_preserved": True,
        }

    checked(result, "document_urdf_lean_urdf", forward)
    checked(result, "document_lean_urdf_lean", reverse)
    checked(result, "document_lean_edit", edit)
    checked(
        result,
        "document_executable_rejected",
        lambda: rejected(
            lambda: Reader(text + '\n#eval IO.println "injected"\n').read(),
            "data-only FluxKernel Lean document",
        ),
    )


def packages(raw, case, asset_case, resources, result):
    # This independent check also checks secondary resources against the pinned
    # collector ledger, not just the converter's own resource table.
    closure = check_asset_closure(case, asset_case, resources)
    result["asset_closure"] = closure
    if closure["status"] != "passed":
        result["checks"]["package_urdf_lean_urdf"] = {
            "status": "failed",
            "error_type": closure.get("error_type", "IncompleteAssets"),
            "error": closure.get(
                "error", closure.get("dependency_closure", "Unknown failure")
            ),
        }
        return
    result["checks"]["package_urdf_lean_urdf"] = {
        "status": "passed",
        "urdf_bytes_equal": True,
        "asset_bytes_equal": True,
        "independent_dependency_closure": True,
        "asset_count": closure["asset_count"],
    }
    with tempfile.TemporaryDirectory(prefix="fk-catalog-bidirectional-") as tmp:
        root = Path(tmp)
        to_lean(case["file"], root / "original")
        shutil.move(root / "original", root / "relocated")
        package = root / "relocated"
        n, assets, native, lexical = load(package)
        initial = (package / "Robot.lean").read_bytes()

        def reverse():
            restored = from_lean(package, root / "restored")
            assert restored["asset_bytes_equal"]
            assert (root / "restored/robot.urdf").read_bytes() == raw
            to_lean(root / "restored/robot.urdf", root / "again")
            assert (root / "again/Robot.lean").read_bytes() == initial
            return {
                "lean_package_relocated": True,
                "lean_term_bytes_equal": True,
                "asset_bytes_equal": True,
            }

        checked(result, "package_lean_urdf_lean", reverse)
        (package / "source.urdf").unlink()

        def xml_free():
            restored = from_lean(package, root / "xml-free")
            assert not restored["lexical_bytes_restored"]
            assert xml_value((root / "xml-free/robot.urdf").read_bytes()) == xml_value(
                raw
            )
            to_lean(root / "xml-free/robot.urdf", root / "xml-free-lean")
            # Rendering changes XML formatting and its digest. Compare the full
            # value and resource bindings, not the now-different lexical snapshot.
            assert load(root / "xml-free-lean")[:3] == (n, assets, native)
            return {
                "source_xml_removed": True,
                "xml_information_equal": True,
                "lean_value_and_assets_equal": True,
                "lexical_identity_claimed": False,
            }

        checked(result, "package_xml_free", xml_free)
        modified, expected, numeric = changed_document(n, raw, case["case_id"])
        (package / "Robot.lean").write_text(source(modified, assets, native, lexical))
        (package / "source.urdf").write_bytes(raw)
        checked(
            result,
            "package_stale_snapshot_rejected",
            lambda: rejected(
                lambda: from_lean(package, root / "stale"),
                "Stale lexical URDF snapshot",
            ),
        )
        (package / "source.urdf").unlink()

        def edit():
            from_lean(package, root / "edited")
            assert xml_value((root / "edited/robot.urdf").read_bytes()) == expected
            to_lean(root / "edited/robot.urdf", root / "edited-lean")
            assert load(root / "edited-lean")[:3] == (modified, assets, native)
            return {
                "lean_edit_reached_urdf": True,
                "long_decimal_mass_changed": numeric,
                "asset_bytes_preserved": True,
            }

        checked(result, "package_lean_edit", edit)
        if assets:
            resource = package / "assets" / assets[0][0]
            resource.write_bytes(resource.read_bytes() + b"\nFK_TAMPER\n")
            checked(
                result,
                "package_asset_tamper_rejected",
                lambda: rejected(
                    lambda: from_lean(package, root / "tampered"),
                    "Changed Lean document resource",
                ),
            )
        else:
            result["checks"]["package_asset_tamper_rejected"] = {
                "status": "not_applicable",
                "reason": "Robot has no external assets",
            }


def check(case, asset_case, resources, output):
    directory = Path(output) / case["case_id"]
    directory.mkdir(parents=True, exist_ok=True)
    result = {
        k: case[k]
        for k in ("case_id", "entry_ids", "repository", "commit", "path", "sha256")
    }
    result["checks"] = {
        name: {"status": "blocked", "reason": "Prerequisite did not pass"}
        for name in CHECKS
    }
    start = time.monotonic()
    try:
        raw = Path(case["file"]).read_bytes()
        if digest(raw) != case["sha256"]:
            raise ValueError("Pinned source digest mismatch")
        try:
            documents(raw, case, directory, result)
        except Exception as exc:
            result["checks"]["document_urdf_lean_urdf"] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        try:
            packages(raw, case, asset_case, resources, result)
        except Exception as exc:
            result["package_setup_error"] = {
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        assert digest(Path(case["file"]).read_bytes()) == case["sha256"]
        result["source_unchanged"] = True
    except Exception as exc:
        result["input_error"] = {"error_type": type(exc).__name__, "error": str(exc)}
    for name, status in result["checks"].items():
        if status["status"] == "blocked":
            dependency = (
                "document_urdf_lean_urdf"
                if name.startswith("document_")
                else "package_urdf_lean_urdf"
            )
            status["blocked_by"] = dependency
            status["reason"] = result.get(
                "input_error",
                result.get("package_setup_error", result["checks"][dependency]),
            ).get("error", "Prerequisite did not pass")
    result["elapsed_seconds"] = round(time.monotonic() - start, 3)
    (directory / "result.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inventory", type=Path)
    p.add_argument("assets", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument(
        "--require-all",
        action="store_true",
        help="Exit nonzero if any applicable check is not passed",
    )
    args = p.parse_args()
    inventory = json.loads(args.inventory.read_text())
    assets = json.loads(args.assets.read_text())
    assert assets["completed"], (
        "Asset acquisition must finish before offline acceptance"
    )
    assert len({c["case_id"] for c in inventory["cases"]}) == len(inventory["cases"])
    asset_cases = {c["case_id"]: c for c in assets["cases"]}
    assert set(asset_cases) == {c["case_id"] for c in inventory["cases"]}
    pinned_resources_verified = 0
    for resource in assets["resources"].values():
        if resource["status"] == "downloaded":
            if digest(Path(resource["file"]).read_bytes()) != resource["sha256"]:
                raise ValueError("Pinned asset digest mismatch: " + resource["file"])
            pinned_resources_verified += 1
    args.output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "fk-catalog-bidirectional-v1",
        "catalog_commit": inventory["catalog_commit"],
        "catalog_entries": len(inventory["scopes"]),
        "total_cases": len(inventory["cases"]),
        "inventory_sha256": digest(args.inventory.read_bytes()),
        "assets_ledger_sha256": digest(args.assets.read_bytes()),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "implementations": {
            m.__name__: digest(Path(m.__file__).read_bytes())
            for m in (lean_document, lean_runtime, urdf_assets)
        },
        "harness_sha256": digest(Path(__file__).read_bytes()),
        "asset_check_sha256": digest(
            Path(__file__).with_name("awesome_urdf_packages.py").read_bytes()
        ),
        "document_scope": "Complete XML value, empty external-resource tables; not complete asset packages",
        "pinned_resources_verified": pinned_resources_verified,
        "model_calls": 0,
        "completed": False,
        "cases": [],
    }
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = [
            pool.submit(
                check, c, asset_cases[c["case_id"]], assets["resources"], args.output
            )
            for c in inventory["cases"]
        ]
        for future in as_completed(pending):
            report["cases"].append(future.result())
            print(f"checked {len(report['cases'])}/{report['total_cases']}", flush=True)
            (args.output / "report.json").write_text(json.dumps(report, indent=2))
    report["cases"].sort(key=lambda c: c["case_id"])
    assert {c["case_id"] for c in report["cases"]} == set(asset_cases)
    report["summary"] = {
        key: dict(Counter(c["checks"][key]["status"] for c in report["cases"]))
        for key in CHECKS
    }
    report["entries"] = []
    for scope in inventory["scopes"]:
        cases = [c for c in report["cases"] if scope["entry_id"] in c["entry_ids"]]
        assert cases, "Uncovered catalog entry: " + scope["name"]
        report["entries"].append(
            {
                "entry_id": scope["entry_id"],
                "name": scope["name"],
                "source_url": scope["url"],
                "case_count": len(cases),
                "checks": {
                    key: dict(Counter(c["checks"][key]["status"] for c in cases))
                    for key in CHECKS
                },
            }
        )
    report["completed"] = True
    report["all_applicable_passed"] = all(
        s["status"] in ("passed", "not_applicable")
        for c in report["cases"]
        for s in c["checks"].values()
    )
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    with (args.output / "catalog.md").open("w") as file:
        file.write("# Every catalog entry: bidirectional results\n\n")
        file.write(
            "Counts are passing files / inventoried files. Blocked checks do not count as passes.\n\n"
        )
        file.write(
            "| Robot | Files | Document U→L→U | Document L→U→L | Lean edits | Package U→L→U | Package L→U→L | XML-free package |\n"
        )
        file.write("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n")
        for entry in report["entries"]:
            keys = CHECKS[:3] + CHECKS[4:7]
            values = " | ".join(
                f"{entry['checks'][k].get('passed', 0)}/{entry['case_count']}"
                for k in keys
            )
            file.write(
                f"| [{entry['name']}]({entry['source_url']}) | {entry['case_count']} | {values} |\n"
            )
    with (args.output / "cases.csv").open("w", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["case_id", "repository", "path", *CHECKS, "errors"])
        for c in report["cases"]:
            writer.writerow(
                [
                    c["case_id"],
                    c["repository"],
                    c["path"],
                    *[c["checks"][k]["status"] for k in CHECKS],
                    json.dumps(
                        {
                            k: v
                            for k, v in c["checks"].items()
                            if v["status"] == "failed"
                        }
                    ),
                ]
            )
    print(json.dumps(report["summary"], indent=2), flush=True)
    if args.require_all and not report["all_applicable_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
