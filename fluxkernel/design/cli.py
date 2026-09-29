"""Offline design definitions and proof certificates."""

import json
from pathlib import Path
import subprocess


def parameters(items):
    result = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator or not value or key in result:
            raise ValueError(
                "Use unique --param NAME=EXACT_NUMBER values in declared units"
            )
        result[key] = value
    return result


def read(path):
    if Path(path).stat().st_size > 2_000_000:
        raise ValueError("Design JSON exceeds 2 MB")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field: " + key)
            result[key] = value
        return result

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)


def command(args):
    try:
        from .model import Design
        from .examples import fourbar
        from .proof import certify, verify

        if args.operation == "example":
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as output:
                json.dump(fourbar(), output, ensure_ascii=False, indent=2)
            result = {"accepted": True, "output": str(path), "model_calls": 0}
        elif args.operation == "demo":
            from .showcase import generate

            result = generate(args.output)
        elif args.operation == "verify":
            result = verify(
                args.directory,
                read(args.design) if args.design else None,
                parameters(args.param) if args.param else None,
            )
        else:
            document = read(args.design)
            inputs = parameters(args.param)
            result = (
                certify(document, args.output, inputs)
                if args.operation == "certify"
                else Design(document).check(inputs)
            )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["accepted"] else 1
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        RecursionError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False))
        return 1


def register(sub):
    p = sub.add_parser(
        "design", help="dimensioned design definitions and offline Lean obligations"
    )
    commands = p.add_subparsers(dest="operation", required=True)
    p = commands.add_parser("example", help="write the four-bar/CSG design example")
    p.add_argument("--output", required=True)
    p.set_defaults(fn=command)
    for operation in ("check", "certify"):
        p = commands.add_parser(operation)
        p.add_argument("design")
        p.add_argument("--param", action="append", default=[])
        if operation == "certify":
            p.add_argument("--output", required=True)
        p.set_defaults(fn=command)
    p = commands.add_parser(
        "verify", help="regenerate proof, rejecting stale or modified evidence"
    )
    p.add_argument("directory")
    p.add_argument("--design", help="compare against the current design JSON")
    p.add_argument("--param", action="append", default=[])
    p.set_defaults(fn=command)
    p = commands.add_parser(
        "demo", help="build a local interactive evidence showcase; real Lean required"
    )
    p.add_argument("--output", required=True)
    p.set_defaults(fn=command)
