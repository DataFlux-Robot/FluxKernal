"""Bind the native robot digest to a Lean checked finite obligation instance."""

import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from .native import digest, plant
from ..runtime import copy_proof_project


def quoted(s):
    return json.dumps(s, ensure_ascii=False)


def q(x):
    f = Fraction(str(x))
    return f"⟨{f.numerator}, {f.denominator}⟩"


def source(r):
    bodies = ",\n".join(
        f"⟨{quoted(b['name'])}, {b['parent']}, {q(b['mass'])}⟩" for b in r["bodies"]
    )
    driven = {a["joint"] for a in r["actuators"]}
    joints = ",\n".join(
        f"⟨{quoted(j['name'])}, {j['body']}, {str(j['limited']).lower()}, {q(j['range'][0])}, {q(j['range'][1])}, {str(j['name'] in driven).lower()}⟩"
        for j in r["joints"]
    )
    names = [j["name"] for j in r["joints"]]
    actions = [
        names.index(n) if n in names else len(names)
        for n in r["controller"]["action_joints"]
    ]
    return (
        "import FluxKernel.Robot\nopen FluxKernel.Robot\nset_option maxRecDepth 16384\nset_option maxHeartbeats 16000000\n"
        + f"def nativeDigest : String := {quoted(digest(r))}\n"
        + f"def robot : Model := ⟨{quoted(plant(r))}, {quoted(r['controller']['plant_sha256'])}, [{bodies}], [{joints}], {actions}⟩\n"
        + "theorem robotAccepted : check robot = true := by decide\n"
        + "theorem robotWellFormed : Valid robot := check_sound robot robotAccepted\n#print axioms robotWellFormed\n"
    )


def prove(r, directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    copy_proof_project(root)
    text = source(r)
    (root / "RobotInstance.lean").write_text(text)
    try:
        built = subprocess.run(
            ["lake", "build"], cwd=root, capture_output=True, text=True, timeout=120
        )
        result = (
            subprocess.run(
                ["lake", "env", "lean", "RobotInstance.lean"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if built.returncode == 0
            else built
        )
        log = built.stdout + built.stderr + result.stdout + result.stderr
        accepted = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as e:
        log = type(e).__name__
        accepted = False
    (root / "check.log").write_text(log)
    return {
        "schema": "fk-robot-proof-v1",
        "accepted": accepted,
        "native_sha256": digest(r),
        "lean_source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "scope": [
            "unique body/joint names",
            "acyclic ordered body parents",
            "nonnegative declared mass",
            "joint references and ordered limits",
            "unique and complete driven-joint coverage",
            "controller bound to this plant digest",
        ],
        "not_proven": [
            "mesh geometry",
            "floating point calculations",
            "kinematic projection equivalence",
            "physical stability",
            "manufacturability",
            "policy execution safety",
        ],
    }
