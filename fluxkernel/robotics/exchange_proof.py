"""Check actual URDF mechanism records against native declarations with Lean 4.

This is translation validation of a finite scalar/topology subset. It does not
prove the Python parser/exporter, frame algebra, numerical FK or mesh semantics.
"""

import hashlib
import subprocess
from pathlib import Path
from .native import digest
from .proof import q, quoted
from .urdf_import import xml_root, one
from ..runtime import assets_root

CHECKER = "formal/FluxKernel/Urdf.lean"
KINDS = {"fixed": 0, "revolute": 1, "continuous": 2, "prismatic": 3}


def native_records(r):
    links = [(b["name"], b["mass"]) for b in r["bodies"]]
    joints = []
    for i, b in enumerate(r["bodies"], 1):
        if b["parent"] == 0:
            continue
        js = [j for j in r["joints"] if j["body"] == i and j["kind"] != "free"]
        if len(js) > 1:
            raise ValueError("Multiple native joints per URDF link unsupported")
        j = js[0] if js else None
        kind = (
            ("revolute" if j["limited"] else "continuous")
            if j and j["kind"] == "hinge"
            else "prismatic"
            if j
            else "fixed"
        )
        joints.append(
            (
                j["name"] if j else b.get("fixed_joint_name", b["name"] + "-fixed"),
                r["bodies"][b["parent"] - 1]["name"],
                b["name"],
                KINDS[kind],
                j["axis"] if j else [],
                j["range"][0] if j else 0,
                j["range"][1] if j else 0,
                j["reference"] if j else 0,
                (j.get("effort_limit") or 0) if j else 0,
                (j.get("velocity_limit") or 0) if j else 0,
            )
        )
    return sorted(links), sorted(joints)


def urdf_records(raw):
    root = xml_root(raw)
    links = []
    for b in root.findall("link"):
        inert = one(b, "inertial")
        m = one(inert, "mass", True) if inert is not None else None
        links.append((b.attrib["name"], m.attrib["value"] if m is not None else "0"))
    joints = []
    for j in root.findall("joint"):
        kind = KINDS[j.attrib["type"]]
        limit = one(j, "limit", kind in (1, 3))
        axis = one(j, "axis", kind != 0)
        joints.append(
            (
                j.attrib["name"],
                one(j, "parent", True).attrib["link"],
                one(j, "child", True).attrib["link"],
                kind,
                axis.attrib["xyz"].split() if axis is not None else [],
                limit.get("lower", "0") if limit is not None else "0",
                limit.get("upper", "0") if limit is not None else "0",
                "0",
                limit.get("effort", "0") if limit is not None else "0",
                limit.get("velocity", "0") if limit is not None else "0",
            )
        )
    return sorted(links), sorted(joints)


def mechanism(records):
    links, joints = records
    ls = ",\n".join(f"⟨{quoted(n)}, {q(m)}⟩" for n, m in links)
    js = []
    for n, parent, child, kind, axis, lo, hi, ref, effort, velocity in joints:
        av = "[" + ", ".join(q(x) for x in axis) + "]"
        js.append(
            "⟨"
            + ", ".join(
                [
                    quoted(n),
                    quoted(parent),
                    quoted(child),
                    str(kind),
                    av,
                    q(lo),
                    q(hi),
                    q(ref),
                    q(effort),
                    q(velocity),
                ]
            )
            + "⟩"
        )
    return "⟨[" + ls + "], [" + ",\n".join(js) + "]⟩"


def source(r, raw):
    return (
        "import FluxKernel.Urdf\nopen FluxKernel.Robot.Urdf\n"
        "set_option maxRecDepth 16384\nset_option maxHeartbeats 16000000\n"
        f"def nativeMechanism : Mechanism := {mechanism(native_records(r))}\n"
        f"def exportedMechanism : Mechanism := {mechanism(urdf_records(raw))}\n"
        "theorem exchangeAccepted : check nativeMechanism exportedMechanism = true := by decide\n"
        "theorem mechanismPreserved : Preserved nativeMechanism exportedMechanism :=\n"
        "  check_sound _ _ exchangeAccepted\n#print axioms mechanismPreserved\n"
    )


def prove(r, urdf_path, directory):
    directory = Path(directory)
    raw = Path(urdf_path).read_bytes()
    target = directory / CHECKER
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((assets_root() / CHECKER).read_bytes())
    text = source(r, raw)
    (directory / "UrdfInstance.lean").write_text(text)
    accepted = False
    try:
        built = subprocess.run(
            ["lake", "build", "FluxKernel.Urdf"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=120,
        )
        checked = (
            subprocess.run(
                ["lake", "env", "lean", "UrdfInstance.lean"],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if built.returncode == 0
            else built
        )
        log = built.stdout + built.stderr + checked.stdout + checked.stderr
        accepted = checked.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        log = type(exc).__name__
    (directory / "exchange.log").write_text(log)
    return {
        "schema": "fk-urdf-proof-v1",
        "accepted": accepted,
        "native_sha256": digest(r),
        "urdf_sha256": hashlib.sha256(raw).hexdigest(),
        "lean_source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "scope": [
            "link names and declared mass",
            "joint names, parent/child and type",
            "nonzero axis preserved as exact decimal rationals",
            "finite limits shifted by native reference; exact rational arithmetic",
            "declared effort/velocity limits preserved (unknown maps to zero)",
        ],
        "not_proven": [
            "XML parser correctness",
            "coordinate-transform equivalence",
            "mesh/inertia geometry",
            "continuous motion or dynamics",
            "hardware capability",
        ],
        "physical_status": "unverified",
    }


def verify(r, root, rerun=False):
    import json

    root = Path(root)
    proofdir = root / "proof"
    raw = (root / "robot.urdf").read_bytes()
    record = json.loads((root / "exchange-proof.json").read_text())
    text = source(r, raw)
    if (
        record["native_sha256"] != digest(r)
        or record["urdf_sha256"] != hashlib.sha256(raw).hexdigest()
        or record["lean_source_sha256"] != hashlib.sha256(text.encode()).hexdigest()
        or (proofdir / "UrdfInstance.lean").read_text() != text
    ):
        raise ValueError("URDF/Lean exchange binding mismatch")
    if (proofdir / CHECKER).read_bytes() != (assets_root() / CHECKER).read_bytes():
        raise ValueError("URDF proof checker differs from installed version")
    # Binding alone is insufficient: compare independently extracted finite records.
    # Lean proves the shifted ranges; deterministic regeneration covers XML fields
    # outside that theorem, and cannot promote them to formally proved properties.
    from .projection import urdf_xml
    import xml.etree.ElementTree as ET

    expected = ET.canonicalize(
        ET.tostring(urdf_xml(r), encoding="unicode"), strip_text=True
    )
    if ET.canonicalize(raw.decode(), strip_text=True) != expected:
        raise ValueError("URDF differs from current native projection")
    if rerun:
        built = subprocess.run(
            ["lake", "build", "FluxKernel.Urdf"],
            cwd=proofdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        checked = subprocess.run(
            ["lake", "env", "lean", "UrdfInstance.lean"],
            cwd=proofdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if built.returncode or checked.returncode:
            raise ValueError("Lean URDF exchange recheck failed")
    return {
        "available": True,
        "accepted": bool(record["accepted"]) if not rerun else True,
        "proof_reexecuted": rerun,
        "physical_status": "unverified",
    }
