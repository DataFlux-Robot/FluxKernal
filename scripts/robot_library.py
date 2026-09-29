#!/usr/bin/env python3
"""Browse, verify and render the pinned robot document library without model calls.

All commands are local. Indexed-only entries require caller-supplied, authorized
source files. Geometry assets are outside this document library.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path

from fluxkernel.robotics.lean_document import Reader, render_lean, source, tree
from fluxkernel.robotics.sources import safe

DEFAULT_LIBRARY = Path(__file__).resolve().parents[1] / "robots"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def registry(root):
    data = json.loads((root / "index.json").read_text())
    if data.get("schema") != "fluxkernal-robot-library-v1":
        raise ValueError("Unsupported robot library schema")
    entries = {e["id"]: e for e in data["entries"]}
    if len(entries) != len(data["entries"]):
        raise ValueError("Duplicate library ID")
    return data, entries


def checked_source(root, entry):
    if entry["distribution"] != "bundled":
        raise ValueError(
            "Indexed-only entry: supply an authorized local URDF with materialize"
        )
    directory = safe(root, entry["directory"])
    for name, expected in entry["files"].items():
        if sha(safe(directory, name).read_bytes()) != expected:
            raise ValueError("Changed library file: " + name)
    raw = (directory / "source.urdf").read_bytes()
    text = (directory / "Robot.lean").read_text()
    if sha(raw) != entry["source_sha256"] or sha(text.encode()) != entry["lean_sha256"]:
        raise ValueError("Library provenance hash mismatch")
    value, assets, native, lexical = Reader(text).read()
    if source(value, assets, native, lexical) != text:
        raise ValueError("Noncanonical Lean document")
    if assets or native or lexical != sha(raw) or value != tree(raw):
        raise ValueError("Document library value or scope mismatch")
    return text, raw


def verify_one(arguments):
    root, entry, execute = arguments
    result = {"id": entry["id"], "distribution": entry["distribution"]}
    if entry["distribution"] != "bundled":
        return {
            **result,
            "status": "indexed_only",
            "reason": entry["distribution_note"],
        }
    try:
        text, raw = checked_source(root, entry)
        if execute:
            output = render_lean(source(*Reader(text).read()))
            if tree(output) != tree(raw):
                raise ValueError("Lean renderer changed the model document")
        return {**result, "status": "passed", "lean_executed": execute}
    except Exception as exc:
        return {**result, "status": "failed", "error": str(exc)}


def materialize(entry, urdf, output):
    raw = Path(urdf).read_bytes()
    if sha(raw) != entry["source_sha256"]:
        raise ValueError("Source does not match the pinned library case")
    text = source(tree(raw), [], [], sha(raw))
    if sha(text.encode()) != entry["lean_sha256"]:
        raise ValueError("Generated Lean differs from the tested library value")
    output.mkdir(parents=True, exist_ok=False)
    (output / "Robot.lean").write_text(text)
    (output / "source.urdf").write_bytes(raw)
    (output / "ORIGIN.json").write_text(json.dumps(entry, indent=2))
    (output / "NOTICE.md").write_text(
        "# Locally generated document\n\nSource: "
        + entry["source_url"]
        + "\n\nUpstream license: "
        + entry["license"]
        + "\n\nGenerated locally from a caller-supplied source. Source rights and notices "
        "remain applicable. Local generation does not authorize redistribution. "
        "External geometry resources are not included.\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--query", default="")
    listing.add_argument("--json", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument(
        "--execute",
        action="store_true",
        help="Compile and run real local Lean for every bundled entry",
    )
    verify.add_argument("--workers", type=int, default=4)
    verify.add_argument("--output", type=Path)
    render = commands.add_parser("render")
    render.add_argument("case_id")
    render.add_argument("--output", type=Path, required=True)
    local = commands.add_parser("materialize")
    local.add_argument("case_id")
    local.add_argument("--urdf", type=Path, required=True)
    local.add_argument("--output", type=Path, required=True)
    bulk = commands.add_parser("build-local")
    bulk.add_argument(
        "--inventory",
        type=Path,
        required=True,
        help="Local pinned corpus inventory; no downloads",
    )
    bulk.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _, entries = registry(args.library)
    if args.command == "list":
        selected = [
            e
            for e in entries.values()
            if args.query.lower()
            in (" ".join(e["robots"]) + " " + e["catalog_path"]).lower()
        ]
        if args.json:
            print(json.dumps(selected, indent=2))
        else:
            for entry in selected:
                print(
                    entry["id"],
                    " / ".join(entry["robots"]),
                    entry["distribution"],
                    entry["license"],
                )
    elif args.command == "verify":
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            cases = list(
                pool.map(
                    verify_one,
                    [(args.library, e, args.execute) for e in entries.values()],
                )
            )
        result = {
            "accepted": all(c["status"] != "failed" for c in cases),
            "indexed": len(cases),
            "bundled_passed": sum(c["status"] == "passed" for c in cases),
            "indexed_only": sum(c["status"] == "indexed_only" for c in cases),
            "lean_executed": args.execute,
            "cases": cases,
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2))
        print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))
        if not result["accepted"]:
            raise SystemExit(1)
    elif args.command == "render":
        text, raw = checked_source(args.library, entries[args.case_id])
        output = render_lean(source(*Reader(text).read()))
        if tree(output) != tree(raw):
            raise ValueError("Rendered document differs")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as file:
            file.write(output)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "scope": "document-only",
                    "lean_executed": True,
                    "model_calls": 0,
                }
            )
        )
    elif args.command == "materialize":
        materialize(entries[args.case_id], args.urdf, args.output)
        print(json.dumps({"output": str(args.output), "model_calls": 0}))
    else:
        inventory = json.loads(args.inventory.read_text())
        cases = {c["case_id"]: c for c in inventory["cases"]}
        args.output.mkdir(parents=True, exist_ok=False)
        for key, entry in entries.items():
            materialize(entry, Path(cases[key]["file"]), args.output / key)
        print(
            json.dumps(
                {
                    "generated": len(entries),
                    "output": str(args.output),
                    "model_calls": 0,
                }
            )
        )


if __name__ == "__main__":
    main()
