"""Native robot operations; upstream fetch is explicit on import."""

import json
from pathlib import Path


def command(args):
    try:
        from .bundle import import_robot, verify, revise
        from .native import read, digest

        if args.operation == "import":
            result = import_robot(
                args.profile, args.output, args.source, args.include_hardware
            )
        elif args.operation == "verify":
            result = verify(args.bundle, args.require_proof)
        elif args.operation == "revise":
            result = revise(
                args.bundle, json.loads(Path(args.patch).read_text()), args.output
            )
        elif args.operation == "inspect":
            result = verify(args.bundle)
            result["robot"] = read(args.bundle)
        elif args.operation == "compare":
            verify(args.bundle)
            verify(args.other)
            a = read(args.bundle)
            b = read(args.other)
            result = {
                "same_design": digest(a) == digest(b),
                "same_action_order": a["controller"]["action_joints"]
                == b["controller"]["action_joints"],
                "same_plant": a["controller"]["plant_sha256"]
                == b["controller"]["plant_sha256"],
                "same_servo_family": a["controller"]["servo_family"]
                == b["controller"]["servo_family"],
                "policy_transfer_approved": False,
                "reason": "No imported policy, observation contract or physical validation",
            }
        else:
            from .validation import check_projection

            result = check_projection(args.bundle)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return (
            1
            if result.get("accepted") is False
            or (
                getattr(args, "require_proof", False)
                and not result.get("proof_accepted", True)
            )
            else 0
        )
    except (ValueError, OSError, KeyError, ImportError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False))
        return 1


def register(sub):
    p = sub.add_parser(
        "robot", help="Native robot assets, formal structure and URDF/MJCF projections"
    )
    modes = p.add_subparsers(dest="operation", required=True)
    for name in [
        "import",
        "inspect",
        "verify",
        "revise",
        "compare",
        "check-projection",
    ]:
        p = modes.add_parser(name)
        p.set_defaults(fn=command)
        p.add_argument("--json", action="store_true")
        if name == "import":
            p.add_argument("profile", choices=("microduck", "xgoduck"))
            p.add_argument(
                "--source",
                help="Verified local upstream snapshot; otherwise fetch pinned sources",
            )
            p.add_argument(
                "--include-hardware",
                action="store_true",
                help="XGO physical source inventory and BOM, separate from rigid bodies",
            )
        else:
            p.add_argument("bundle")
        if name in ("import", "revise"):
            p.add_argument("--output", required=True)
        if name in ("import", "revise", "verify"):
            p.add_argument("--require-proof", action="store_true")
        if name == "revise":
            p.add_argument("--patch", required=True)
        if name == "compare":
            p.add_argument("other")
