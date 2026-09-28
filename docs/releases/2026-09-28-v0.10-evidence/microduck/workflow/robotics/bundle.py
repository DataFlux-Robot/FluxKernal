"""Immutable native robot packages, kernel objects and bounded revisions."""

import copy
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from .native import read, write, validate, plant, digest, from_mujoco
from .sources import PROFILES, download, safe
from .projection import mjcf, urdf
from .proof import prove, source
from ..core.objects import Node, Edge, Certificate, Obligation
from ..store.objstore import Store


def register(r, root):
    store = Store(root / ".fk")
    nodes = []
    for m in r["meshes"]:
        blob = store.put_blob(safe(root, m["file"]).read_bytes())
        node = Node(
            role="Part",
            kind="robot-mesh",
            params={"sha256": m["sha256"]},
            ground={"type": "mesh", "blob": blob, "units": "m"},
        )
        d = store.put_object("node", node.payload())
        store.bind_name("mesh/" + m["name"], d)
    for i, b in enumerate(r["bodies"], 1):
        ground = {
            "type": "native-rigid-body",
            "body": b,
            "joints": [j for j in r["joints"] if j["body"] == i],
            "geometry": [g for g in r["geometries"] if g["body"] == i],
            "mesh_nodes": {
                g["mesh"]: store.resolve("mesh/" + g["mesh"])
                for g in r["geometries"]
                if g["body"] == i and g["mesh"]
            },
        }
        node = Node(
            role="Component",
            kind="rigid-body",
            spec={"not_responsible": ["manufacturing qualification"]},
            ground=ground,
        )
        d = store.put_object("node", node.payload())
        nodes.append(d)
        store.bind_name("body/" + b["name"], d)
    for i, item in enumerate(r.get("manufacturing", {}).get("items", [])):
        blob = store.put_blob(safe(root, item["file"]).read_bytes())
        node = Node(
            role="Part",
            kind="hardware-source-item",
            params=item,
            ground={"type": "source-file", "blob": blob},
        )
        store.bind_name("hardware/" + str(i), store.put_object("node", node.payload()))
    for part in r.get("custom_parts", []):
        blobs = {
            file: store.put_blob(safe(root, file).read_bytes())
            for file in part["artifacts"]
        }
        node = Node(
            role="Part",
            kind="parametric-robot-accessory",
            params=part,
            ground={
                "type": "cad-recipe",
                "blobs": blobs,
                "units": {"step": "mm", "stl": "mm", "recipe": "mm", "obj": "m"},
                "interface_status": "unverified",
            },
        )
        store.bind_name(
            "custom-part/" + part["body"], store.put_object("node", node.payload())
        )
    robot_ref = store.put_object("robot", r)
    system = Node(
        role="System",
        kind="robot",
        spec={"goals": r["requirements"]},
        ground={"type": "native-robot", "robot_ref": robot_ref, "body_nodes": nodes},
    )
    root_ref = store.put_object("node", system.payload())
    store.bind_name("robot", root_ref)
    mind = Node(
        role="Component",
        kind="controller-contract",
        facet="MIND",
        spec={"plant_ref": root_ref},
        params=r["controller"],
    )
    controller = store.put_object("node", mind.payload())
    store.bind_name("controller", controller)
    cert = Certificate(
        obligations=[
            Obligation(
                "native-structure", "Native structure checked", True, "native-validator"
            ),
            Obligation(
                "physical-integration",
                "Actual robot and controller validated",
                None,
                "unperformed",
            ),
        ]
    )
    edge = Edge(
        op="compose",
        inputs=nodes,
        transform={"name": "native-robot-assembly", "native_sha256": digest(r)},
        output=root_ref,
        certificate=cert.to_dict(),
        state="evidenced",
        reason="Physical integration obligation remains open",
    )
    e = store.put_object("edge", edge.payload())
    store.append_edge(e, edge.__dict__)
    return {
        "root": root_ref,
        "robot_object": robot_ref,
        "controller": controller,
        "bodies": nodes,
        "edge": e,
        "state": "evidenced",
        "promoted": False,
    }


def seal(root):
    files = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
        and ".lake" not in p.parts
        and "__pycache__" not in p.parts
        and p.name != "manifest.json"
    }
    write(root / "manifest.json", files)


def finish(r, root):
    validate(r)
    write(root / "robot.json", r)
    write(root / "native-checks.json", validate(r))
    write(root / "kernel.json", register(r, root))
    write(root / "mjcf.projection.json", mjcf(r, root / "robot.xml"))
    urdf(r, root / "robot.urdf")
    # Explicit skill-compatible generator: the native document remains authority.
    (root / "gen_urdf.py").write_text(
        "from pathlib import Path\nfrom fluxkernel.robotics.native import read\nfrom fluxkernel.robotics.projection import urdf_xml\ndef gen_urdf():\n    return urdf_xml(read(Path(__file__).parent))\n"
    )
    proof = prove(r, root / "proof")
    write(root / "proof.json", proof)
    seal(root)
    return {
        "directory": str(root.resolve()),
        "native_sha256": digest(r),
        "name": r["name"],
        "bodies": len(r["bodies"]),
        "joints": len(r["joints"]),
        "actuators": len(r["actuators"]),
        "meshes": len(r["meshes"]),
        "mass_kg": sum(b["mass"] for b in r["bodies"]),
        "proof_accepted": proof["accepted"],
        "deployment_ready": False,
    }


def import_robot(name, output, source_dir=None, include_hardware=False):
    import mujoco

    profile = PROFILES[name]
    base = Path(output).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    root = base / (name + "-" + uuid.uuid4().hex[:8])
    root.mkdir()
    upstream = root / "upstream"
    if source_dir:
        src = Path(source_dir)
        record = json.loads((src / "source.json").read_text())
        if any(record.get(k) != v for k, v in profile.items()):
            raise ValueError("Source profile/commit mismatch")
        for relative, meta in record["files"].items():
            raw = safe(src, relative).read_bytes()
            if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
                raise ValueError("Changed source snapshot")
            dst = safe(upstream, relative)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw)
        write(upstream / "source.json", record)
    else:
        record = download(name, upstream)
    entry = upstream / profile["directory"] / profile["entry"]
    model = mujoco.MjModel.from_xml_path(str(entry))
    r = from_mujoco(
        model,
        {
            "name": name,
            **profile,
            "source_manifest_sha256": digest(record),
            "mujoco_version": mujoco.__version__,
        },
        root / "meshes",
    )
    if include_hardware:
        if name != "xgoduck":
            raise ValueError(
                "No pinned Microduck manufacturing BOM adapter; use its source mesh assets"
            )
        from .sources import hardware_inventory

        r["manufacturing"] = hardware_inventory(root / "hardware")
    return finish(r, root)


def verify(root, rerun_proof=False):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    for relative, expected in manifest.items():
        if hashlib.sha256(safe(root, relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Artifact changed: " + relative)
    r = read(root)
    proof = json.loads((root / "proof.json").read_text())
    if proof["native_sha256"] != digest(r) or (
        root / "proof/RobotInstance.lean"
    ).read_text() != source(r):
        raise ValueError("Native/Lean binding mismatch")
    if proof["lean_source_sha256"] != hashlib.sha256(source(r).encode()).hexdigest():
        raise ValueError("Lean source hash mismatch")
    from ..runtime import assets_root, PROOF_FILES

    for name in PROOF_FILES:
        if (root / "proof" / name).read_bytes() != (assets_root() / name).read_bytes():
            raise ValueError("Proof checker differs from installed version")
    store = Store(root / ".fk")
    k = json.loads((root / "kernel.json").read_text())
    for ref in store.list_objects():
        store.get_object(ref)
    for ref in store.names().values():
        store.get_object(ref)
    if store.get_object(k["robot_object"])["payload"] != r:
        raise ValueError("Kernel robot differs from native design")
    if store.get_object(k["controller"])["payload"]["spec"]["plant_ref"] != k["root"]:
        raise ValueError("Kernel controller plant mismatch")
    if store.get_object(k["controller"])["payload"]["params"] != r["controller"]:
        raise ValueError("Kernel controller contract differs from native design")
    system = store.get_object(k["root"])["payload"]["ground"]
    if (
        system["robot_ref"] != k["robot_object"]
        or system["body_nodes"] != k["bodies"]
        or len(k["bodies"]) != len(r["bodies"])
    ):
        raise ValueError("Kernel assembly mismatch")
    for i, (body, ref) in enumerate(zip(r["bodies"], k["bodies"]), 1):
        ground = store.get_object(ref)["payload"]["ground"]
        if (
            ground["body"] != body
            or ground["joints"] != [j for j in r["joints"] if j["body"] == i]
            or ground["geometry"] != [g for g in r["geometries"] if g["body"] == i]
        ):
            raise ValueError("Kernel body differs from native design")
    for m in r["meshes"]:
        n = store.get_object(store.resolve("mesh/" + m["name"]))["payload"]
        store.get_blob(n["ground"]["blob"])
    if rerun_proof:
        import subprocess

        p = subprocess.run(
            ["lake", "env", "lean", "RobotInstance.lean"],
            cwd=root / "proof",
            capture_output=True,
            text=True,
            timeout=120,
        )
        if p.returncode:
            raise ValueError("Lean recheck failed")
    return {
        "accepted": True,
        "native_sha256": digest(r),
        "proof_accepted": proof["accepted"],
        "proof_reexecuted": rerun_proof,
        "physical_status": "unverified",
    }


def revise(parent, patch, output):
    parent = Path(parent)
    verify(parent)
    r = read(parent)
    if set(patch) != {"base_native_sha256", "edits"} or patch[
        "base_native_sha256"
    ] != digest(r):
        raise ValueError("Patch must pin the native parent")
    if not isinstance(patch["edits"], list) or not 1 <= len(patch["edits"]) <= 32:
        raise ValueError("Expected 1..32 bounded edits")
    child = copy.deepcopy(r)
    fields = {
        "body": {"mass", "position", "principal_inertia", "inertial_position"},
        "joint": {"range", "position", "axis"},
    }
    for edit in patch["edits"]:
        if (
            set(edit) != {"kind", "name", "set"}
            or edit["kind"] not in fields
            or not edit["set"]
            or not set(edit["set"]) <= fields[edit["kind"]]
        ):
            raise ValueError("Unsupported native edit")
        items = child["bodies"] if edit["kind"] == "body" else child["joints"]
        item = next((b for b in items if b["name"] == edit["name"]), None)
        if item is None:
            raise ValueError("Unknown native occurrence")
        if edit["kind"] == "body" and edit["name"] in {
            p["body"] for p in child.get("custom_parts", [])
        }:
            raise ValueError(
                "CAD-backed custom parts require regeneration; numeric body overrides are prohibited"
            )
        item.update(edit["set"])
    child["lineage"].append(
        {
            "parent_native_sha256": digest(r),
            "patch": patch,
            "invalidated": [
                "source dynamics equivalence",
                "policy suitability",
                "physical integration",
            ],
        }
    )
    child["controller"]["plant_sha256"] = plant(child)
    child["controller"]["status"] = "requires-revalidation"
    child["controller"]["deployment_ready"] = False
    for requirement in child["requirements"]:
        if requirement["id"] == "preserve-source-structure":
            requirement["status"] = "superseded-by-native-revision"
    validate(child)
    root = Path(output).expanduser().resolve() / (
        r["name"] + "-" + uuid.uuid4().hex[:8]
    )
    root.mkdir(parents=True)
    shutil.copytree(parent / "meshes", root / "meshes")
    shutil.copytree(parent / "upstream", root / "upstream")
    if (parent / "hardware").exists():
        shutil.copytree(parent / "hardware", root / "hardware")
    if (parent / "cad").exists():
        shutil.copytree(parent / "cad", root / "cad")
    write(root / "parent-native.json", r)
    return finish(child, root)
