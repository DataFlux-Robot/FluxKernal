"""Regenerate and kernel-check finite design obligations with installed Lean.

JSON decoding/elaboration and the binding hashes remain in the Python trust
boundary. Supplied Lean programs and stored success flags are never executed.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from ..robotics.lean_runtime import lean_binary
from ..runtime import assets_root
from .model import Design, UNITS, canonical, digest, rational

MODULE = "formal/FluxKernel/Design.lean"


def rat(value):
    q = rational(value) if isinstance(value, (str, int)) else value
    return f"(({q.numerator} : Rat) / ({q.denominator} : Rat))"


def dim(value):
    return "⟨" + ", ".join(str(x) for x in value) + "⟩"


def expression(e, design):
    if "param" in e:
        return f"(.parameter {list(design.parameters).index(e['param'])})"
    if "value" in e:
        scale, dimension = UNITS[e["unit"]]
        return f"(.literal {rat(rational(e['value']) * scale)} {dim(dimension)})"
    a, b = (expression(x, design) for x in e["args"])
    return f"(.{e['op']} {a} {b})"


def clause(c, design):
    return f"⟨{expression(c['lhs'], design)}, {expression(c['rhs'], design)}, .{c['relation']}⟩"


def predicate(p, design):
    if "lhs" in p:
        return f"(.atom {clause(p, design)})"
    if "not" in p:
        return f"(.not {predicate(p['not'], design)})"
    key = "and" if "and" in p else "or"
    a, b = (predicate(x, design) for x in p[key])
    return f"(.{key} {a} {b})"


def source(design, overrides=None):
    env = design.environment(overrides)
    parameters = []
    for name, p in design.parameters.items():
        scale, dimension = UNITS[p["unit"]]
        parameters.append(
            f"⟨⟨{rat(env[name])}, {dim(dimension)}⟩, {rat(rational(p['lower']) * scale)}, {rat(rational(p['upper']) * scale)}⟩"
        )
    clauses = [clause(c, design) for c in design.clauses]
    predicates = [predicate(p["predicate"], design) for p in design.predicates]
    return (
        "import FluxKernel.Design\nopen FluxKernel.Design\n"
        "set_option maxRecDepth 16384\nset_option maxHeartbeats 16000000\n"
        f'def designDigest : String := "{digest(design.document)}"\n'
        + "def design : Model := ⟨["
        + ",\n".join(parameters)
        + "], ["
        + ",\n".join(clauses)
        + "], ["
        + ",\n".join(predicates)
        + "]⟩\n"
        + "theorem accepted : check design = true := by decide +kernel\n"
        + "theorem obligationsHold : Valid design := check_sound design accepted\n"
        + "#print axioms obligationsHold\n#print axioms parallelogram_family\n"
    )


def execute(text):
    compiler = lean_binary()
    module = (assets_root() / MODULE).read_bytes()
    with tempfile.TemporaryDirectory(prefix="fk-design-proof-") as temporary:
        root = Path(temporary)
        (root / "FluxKernel").mkdir()
        (root / "FluxKernel/Design.lean").write_bytes(module)
        (root / "Instance.lean").write_bytes(text.encode("utf-8"))
        env = {**os.environ, "LEAN_PATH": str(root)}
        logs = []
        for arguments in (
            ["-o", "FluxKernel/Design.olean", "FluxKernel/Design.lean"],
            ["Instance.lean"],
        ):
            result = subprocess.run(
                [str(compiler), *arguments],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            logs.append(result.stdout + result.stderr)
            if result.returncode:
                raise ValueError(
                    "Lean rejected design obligations:\n" + "\n".join(logs)[-4000:]
                )
    return {
        "accepted": True,
        "module_sha256": hashlib.sha256(module).hexdigest(),
        "instance_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "log": "\n".join(logs),
        "scope": "exact expression constraints and CSG probes at the specified parameters",
        "trust_boundary": "Python schema validation/elaboration, JSON-to-Lean binding, installed Lean toolchain",
    }


def certify(document, output, overrides=None):
    design = Design(document)
    inputs = {k: str(rational(v)) for k, v in (overrides or {}).items()}
    report = design.check(inputs)
    if not report["accepted"]:
        failed = [c["id"] for c in report["checks"] if not c["passed"]]
        raise ValueError("Unmet design obligations: " + ", ".join(failed))
    text = source(design, inputs)
    proof = execute(text)
    report["proof"] = proof
    report["inputs_sha256"] = digest(inputs)
    output = Path(output)
    # Finish proof before creating any user-visible output; never overwrite.
    output.mkdir(parents=True, exist_ok=False)
    for name, data in (
        ("design.json", design.document),
        ("inputs.json", inputs),
        ("report.json", report),
    ):
        (output / name).write_bytes(canonical(data) + b"\n")
    (output / "Instance.lean").write_bytes(text.encode("utf-8"))
    shutil.copyfile(assets_root() / MODULE, output / "Design.lean")
    return report


def verify(directory, document=None, overrides=None):
    root = Path(directory)
    saved = json.loads((root / "design.json").read_text(encoding="utf-8"))
    inputs = json.loads((root / "inputs.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "report.json").read_text(encoding="utf-8"))
    if document is not None and digest(document) != digest(saved):
        raise ValueError("Stale certificate: design changed")
    if overrides is not None and digest(
        {k: str(rational(v)) for k, v in overrides.items()}
    ) != digest(inputs):
        raise ValueError("Stale certificate: parameter inputs changed")
    design = Design(saved)
    report = design.check(inputs)
    if (
        not report["accepted"]
        or receipt["design_sha256"] != digest(saved)
        or receipt["inputs_sha256"] != digest(inputs)
    ):
        raise ValueError("Invalid certificate binding or unmet obligations")
    text = source(design, inputs)
    if (root / "Instance.lean").read_text(encoding="utf-8") != text:
        raise ValueError("Changed proof source; arbitrary Lean is never executed")
    if (root / "Design.lean").read_bytes() != (assets_root() / MODULE).read_bytes():
        raise ValueError("Changed proof module")
    proof = execute(text)
    report["proof"], report["inputs_sha256"] = proof, digest(inputs)
    if canonical(receipt) != canonical(report):
        raise ValueError("Changed certificate receipt")
    return report
