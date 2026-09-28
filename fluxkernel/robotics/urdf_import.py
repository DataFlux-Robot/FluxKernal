"""Strict, offline URDF tree import. Source XML is provenance, not design authority.

Ledger: URDF SI/RPY origins become parent-local wxyz body frames. A movable
joint's child frame is its joint frame, so native anchors and reference are zero.
Inertia is diagonalized in its own frame; visual and collision origins stay separate.
No actuator/controller or physical validation is inferred from joint limits.
"""

import copy
import hashlib
import math
import re
import shutil
import struct
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from .native import SCHEMA, plant, validate, write
from .projection import quatmat, save


def xml_root(raw):
    if (
        b"\x00" in raw
        or len(raw) > 16 * 1024 * 1024
        or re.search(rb"<!\s*(DOCTYPE|ENTITY)", raw, re.I)
    ):
        raise ValueError("URDF XML size/declaration unsupported")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("Invalid URDF XML") from exc
    if root.tag != "robot":
        raise ValueError(
            "Expected URDF robot root; expand xacro explicitly before import"
        )
    return root


def allowed(e, children=(), attrs=()):
    if set(e.attrib) - set(attrs) or any(c.tag not in children for c in e):
        raise ValueError(f"Unsupported URDF element/attribute in {e.tag}")


def one(e, tag, required=False):
    xs = e.findall(tag)
    if len(xs) > 1 or (required and not xs):
        raise ValueError(f"Expected one {tag} in {e.tag}")
    return xs[0] if xs else None


def numbers(text, count):
    try:
        values = [float(x) for x in text.split()]
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid numeric URDF field") from exc
    if len(values) != count or not all(math.isfinite(x) for x in values):
        raise ValueError("URDF field must contain finite numbers")
    return values


def scalar(e, key, default=None):
    if e is None or key not in e.attrib:
        if default is None:
            raise ValueError(f"Missing URDF numeric field: {key}")
        return default
    return numbers(e.get(key), 1)[0]


def name(e):
    n = e.get("name", "")
    if not n or any(c.isspace() or ord(c) < 32 for c in n):
        raise ValueError("URDF names must be nonempty and contain no whitespace")
    return n


def origin(e):
    o = one(e, "origin")
    if o is None:
        return [0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]
    allowed(o, attrs=("xyz", "rpy"))
    p = numbers(o.get("xyz", "0 0 0"), 3)
    roll, pitch, yaw = numbers(o.get("rpy", "0 0 0"), 3)
    cr, cp, cy = [math.cos(v / 2) for v in (roll, pitch, yaw)]
    sr, sp, sy = [math.sin(v / 2) for v in (roll, pitch, yaw)]
    return p, [
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]


def mesh_path(uri, source_dir, packages):
    if uri.startswith("package://"):
        package, sep, relative = uri[10:].partition("/")
        if not sep or package not in packages:
            raise ValueError(
                "Unresolved URDF package URI; pass an explicit --package NAME=DIR"
            )
        base = Path(packages[package]).resolve()
    elif "://" in uri or Path(uri).is_absolute() or "\\" in uri:
        raise ValueError(
            "Mesh must use a relative path or explicitly mapped package URI"
        )
    else:
        base, relative = source_dir.resolve(), uri
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("Mesh path escapes its declared root or does not exist")
    if (
        path.suffix.lower() not in (".obj", ".stl")
        or path.stat().st_size > 64 * 1024 * 1024
    ):
        raise ValueError("Supported mesh subset: local OBJ/STL up to 64 MiB")
    return path


def mesh_obj(raw, suffix, scale):
    """Preserve triangle geometry, bake positive SI scale, drop shading attributes."""
    vertices, faces = [], []
    if suffix == ".obj":
        for line in raw.decode("utf-8").splitlines():
            fields = line.partition("#")[0].split()
            if not fields:
                continue
            if fields[0] == "v":
                vertices.append(numbers(" ".join(fields[1:]), 3))
            elif fields[0] == "f":
                ids = []
                for field in fields[1:]:
                    i = int(field.split("/")[0])
                    idx = i - 1 if i > 0 else len(vertices) + i
                    if i == 0 or not 0 <= idx < len(vertices):
                        raise ValueError("OBJ face reference out of range")
                    ids.append(idx)
                if len(ids) < 3:
                    raise ValueError("OBJ face needs at least three vertices")
                if len(ids) != 3:
                    raise ValueError("Triangulate OBJ polygon faces before import")
                faces.append(ids)
            elif fields[0] not in ("vn", "vt", "o", "g", "s"):
                raise ValueError(
                    "Unsupported OBJ attribute/material; geometry-only triangular OBJ required"
                )
    else:
        binary = len(raw) >= 84 and 84 + 50 * struct.unpack_from("<I", raw, 80)[
            0
        ] == len(raw)
        if binary:
            for offset in range(84, len(raw), 50):
                values = struct.unpack_from("<12fH", raw, offset)
                vertices.extend([list(values[i : i + 3]) for i in (3, 6, 9)])
        else:
            text = raw.decode("ascii")
            if (
                not text.lstrip().lower().startswith("solid")
                or "endsolid" not in text.lower()
            ):
                raise ValueError("Invalid ASCII STL")
            vertices = [
                numbers(m.group(1), 3)
                for m in re.finditer(r"^\s*vertex\s+(.+)$", text, re.M)
            ]
        if len(vertices) % 3:
            raise ValueError("STL must contain complete triangles")
        faces = [list(range(i, i + 3)) for i in range(0, len(vertices), 3)]
    if (
        not vertices
        or not faces
        or not all(math.isfinite(v) for xyz in vertices for v in xyz)
    ):
        raise ValueError("Mesh must contain finite triangle geometry")
    scaled = [[v * s for v, s in zip(xyz, scale)] for xyz in vertices]
    if not all(math.isfinite(v) for xyz in scaled for v in xyz):
        raise ValueError("Scaled mesh overflow")
    # STL repeats shared vertices; deduplicate to make downstream mesh loading stable.
    unique, lookup, mapping = [], {}, []
    for xyz in scaled:
        key = tuple(xyz)
        if key not in lookup:
            lookup[key] = len(unique)
            unique.append(xyz)
        mapping.append(lookup[key])
    lines = ["# FluxKernel imported mesh; metres; source shading omitted"]
    lines += ["v " + " ".join(format(v, ".17g") for v in xyz) for xyz in unique]
    lines += ["f " + " ".join(str(mapping[i] + 1) for i in face) for face in faces]
    return ("\n".join(lines) + "\n").encode(), len(unique), len(faces)


def from_urdf(path, root, packages=None):
    import numpy as np
    import mujoco as mj

    path, root = Path(path).resolve(), Path(root)
    packages = packages or {}
    raw = path.read_bytes()
    document = xml_root(raw)
    allowed(document, ("link", "joint", "material", "mujoco"), ("name", "version"))
    robot_name = name(document)
    if robot_name in (".", "..") or "/" in robot_name or "\\" in robot_name:
        raise ValueError("Robot name must not be a filesystem path")
    hint = one(document, "mujoco")
    if hint is not None:
        allowed(hint, ("compiler",))
        c = one(hint, "compiler", True)
        allowed(c, attrs=("fusestatic", "discardvisual", "strippath"))
        if any(v not in ("true", "false") for v in c.attrib.values()):
            raise ValueError("Unsupported MuJoCo URDF compiler hint")
    materials = {}

    def color(e):
        allowed(e, ("color",), ("name",))
        c = one(e, "color")
        if c is None:
            if e.get("name") not in materials:
                raise ValueError("Unknown URDF material reference")
            return materials[e.get("name")]
        allowed(c, attrs=("rgba",))
        rgba = numbers(c.get("rgba"), 4)
        if not all(0 <= v <= 1 for v in rgba):
            raise ValueError("URDF color outside [0,1]")
        return rgba

    for material in document.findall("material"):
        n = name(material)
        if n in materials:
            raise ValueError("Duplicate material name")
        materials[n] = color(material)
    links = {}
    for link in document.findall("link"):
        allowed(link, ("inertial", "visual", "collision"), ("name",))
        n = name(link)
        if n in links:
            raise ValueError("Duplicate link name")
        if n == "world":
            raise ValueError(
                "MuJoCo reserves link name 'world'; rename that frame explicitly before import"
            )
        links[n] = link
    if not 1 <= len(links) <= 256:
        raise ValueError("URDF requires 1..256 links")
    incoming, joint_names = {}, set()
    for joint in document.findall("joint"):
        allowed(
            joint,
            ("parent", "child", "origin", "axis", "limit", "dynamics"),
            ("name", "type"),
        )
        n = name(joint)
        kind = joint.get("type")
        if n in joint_names or kind not in (
            "fixed",
            "revolute",
            "continuous",
            "prismatic",
        ):
            raise ValueError(
                "Duplicate joint or unsupported joint type (mimic/planar/floating unsupported)"
            )
        joint_names.add(n)
        parent, child = one(joint, "parent", True), one(joint, "child", True)
        allowed(parent, attrs=("link",))
        allowed(child, attrs=("link",))
        a, b = parent.get("link"), child.get("link")
        if a not in links or b not in links or a == b or b in incoming:
            raise ValueError("Invalid joint parent/child or multiple parents")
        incoming[b] = (a, joint)
    roots = set(links) - set(incoming)
    if len(roots) != 1 or len(incoming) != len(links) - 1:
        raise ValueError("URDF must be a connected tree with one root")
    order = [next(iter(roots))]
    for parent in order:
        order.extend(n for n, (p, _) in incoming.items() if p == parent)
    if len(order) != len(links):
        raise ValueError("URDF has a cycle or disconnected links")
    indices = {n: i for i, n in enumerate(order, 1)}
    bodies, joints, geoms, meshes, source_assets = [], [], [], [], []
    mesh_cache = {}
    (root / "meshes").mkdir(parents=True, exist_ok=True)
    (root / "upstream/assets").mkdir(parents=True, exist_ok=True)
    (root / "upstream/input.urdf").write_bytes(raw)
    consumer = copy.deepcopy(document)
    consumer_links = {e.get("name"): e for e in consumer.findall("link")}
    for n in order:
        link = links[n]
        parent, joint = incoming.get(n, (None, None))
        position, quaternion = (
            origin(joint)
            if joint is not None
            else ([0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0])
        )
        body = {
            "name": n,
            "parent": indices[parent] if parent else 0,
            "position": position,
            "quaternion": quaternion,
            "mass": 0.0,
            "inertial_position": [0.0, 0.0, 0.0],
            "inertial_quaternion": [1.0, 0.0, 0.0, 0.0],
            "principal_inertia": [0.0, 0.0, 0.0],
            "inertial_source": "declared URDF; not measured",
            "manufacturing": {
                "route": "unresolved",
                "reason": "URDF link is not a physical BOM",
            },
        }
        inert = one(link, "inertial")
        if inert is not None:
            allowed(inert, ("origin", "mass", "inertia"))
            mass, tensor = one(inert, "mass", True), one(inert, "inertia", True)
            allowed(mass, attrs=("value",))
            allowed(tensor, attrs=("ixx", "iyy", "izz", "ixy", "ixz", "iyz"))
            body["mass"] = scalar(mass, "value")
            if body["mass"] <= 0:
                raise ValueError("Declared inertial mass must be positive")
            ip, iq = origin(inert)
            xx, yy, zz, xy, xz, yz = [
                scalar(tensor, k) for k in ("ixx", "iyy", "izz", "ixy", "ixz", "iyz")
            ]
            values, basis = np.linalg.eigh([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]])
            if np.linalg.det(basis) < 0:
                basis[:, 0] *= -1
            rotation = quatmat(iq) @ basis
            principal_q = np.zeros(4)
            mj.mju_mat2Quat(principal_q, rotation.ravel())
            body.update(
                inertial_position=ip,
                inertial_quaternion=principal_q.tolist(),
                principal_inertia=values.tolist(),
            )
        elif (
            link.findall("visual")
            or link.findall("collision")
            or (joint is not None and joint.get("type") != "fixed")
        ):
            raise ValueError(
                "Import policy: geometry-bearing or movable links require explicit inertials"
            )
        if joint is not None:
            kind = joint.get("type")
            if kind == "fixed":
                if any(
                    joint.find(t) is not None for t in ("axis", "limit", "dynamics")
                ):
                    raise ValueError("Unsupported motion fields on fixed joint")
                body["fixed_joint_name"] = joint.get("name")
            else:
                axis = one(joint, "axis")
                if axis is not None:
                    allowed(axis, attrs=("xyz",))
                av = numbers(axis.get("xyz") if axis is not None else "1 0 0", 3)
                if abs(sum(x * x for x in av) - 1) >= 1e-7:
                    raise ValueError(
                        "URDF joint axis must be normalized (no silent normalization)"
                    )
                limit = one(joint, "limit", kind != "continuous")
                if limit is not None:
                    allowed(limit, attrs=("lower", "upper", "effort", "velocity"))
                if (
                    kind == "continuous"
                    and limit is not None
                    and {"lower", "upper"} & set(limit.attrib)
                ):
                    raise ValueError(
                        "Continuous joint must not declare finite position limits"
                    )
                lower, upper = (
                    (0.0, 0.0)
                    if kind == "continuous"
                    else (scalar(limit, "lower"), scalar(limit, "upper"))
                )
                dynamics = one(joint, "dynamics")
                if dynamics is not None:
                    allowed(dynamics, attrs=("damping", "friction"))
                joints.append(
                    {
                        "name": joint.get("name"),
                        "body": indices[n],
                        "kind": "slide" if kind == "prismatic" else "hinge",
                        "position": [0.0, 0.0, 0.0],
                        "axis": av,
                        "limited": kind != "continuous",
                        "range": [lower, upper],
                        "reference": 0.0,
                        "damping": scalar(dynamics, "damping", 0.0),
                        "frictionloss": scalar(dynamics, "friction", 0.0),
                        "armature": 0.0,
                        "effort_limit": scalar(limit, "effort")
                        if limit is not None
                        else None,
                        "velocity_limit": scalar(limit, "velocity")
                        if limit is not None
                        else None,
                    }
                )
        bodies.append(body)
        for role in ("visual", "collision"):
            for ordinal, e in enumerate(link.findall(role)):
                allowed(
                    e,
                    ("origin", "geometry", "material")
                    if role == "visual"
                    else ("origin", "geometry"),
                    ("name",),
                )
                consumer_e = consumer_links[n].findall(role)[ordinal]
                gname = f"urdf-{indices[n]}-{role}-{ordinal}"
                consumer_e.set("name", gname)
                gp, gq = origin(e)
                geometry = one(e, "geometry", True)
                allowed(geometry, ("box", "sphere", "cylinder", "mesh"))
                if len(geometry) != 1:
                    raise ValueError("Geometry requires exactly one shape")
                shape = geometry[0]
                kind = shape.tag
                g = {
                    "name": gname,
                    "body": indices[n],
                    "kind": kind,
                    "position": gp,
                    "quaternion": gq,
                    "size": [0.0, 0.0, 0.0],
                    "mesh": None,
                    "rgba": [0.7, 0.7, 0.7, 1.0],
                    "group": 2 if role == "visual" else 3,
                    "contype": int(role == "collision"),
                    "conaffinity": int(role == "collision"),
                    "friction": [1.0, 0.005, 0.0001],
                    "margin": 0.0,
                    "gap": 0.0,
                }
                material = one(e, "material")
                if material is not None:
                    g["rgba"] = color(material)
                if kind == "box":
                    allowed(shape, attrs=("size",))
                    size = numbers(shape.get("size"), 3)
                    g["size"] = [v / 2 for v in size]
                elif kind == "sphere":
                    allowed(shape, attrs=("radius",))
                    size = [scalar(shape, "radius")]
                    g["size"][0] = size[0]
                elif kind == "cylinder":
                    allowed(shape, attrs=("radius", "length"))
                    size = [scalar(shape, "radius"), scalar(shape, "length")]
                    g["size"] = [size[0], size[1] / 2, 0.0]
                else:
                    allowed(shape, attrs=("filename", "scale"))
                    size = numbers(shape.get("scale", "1 1 1"), 3)
                    if min(size) <= 0:
                        raise ValueError("Mesh scale must be positive")
                    uri = shape.get("filename", "")
                    asset = mesh_path(uri, path.parent, packages)
                    original = asset.read_bytes()
                    cooked, nv, nf = mesh_obj(original, asset.suffix.lower(), size)
                    mesh_hash = hashlib.sha256(cooked).hexdigest()
                    if mesh_hash not in mesh_cache:
                        idx = len(meshes)
                        filename = f"mesh-{idx}.obj"
                        meshname = f"urdf-mesh-{idx}"
                        (root / "meshes" / filename).write_bytes(cooked)
                        meshes.append(
                            {
                                "name": meshname,
                                "file": "meshes/" + filename,
                                "sha256": mesh_hash,
                                "vertices": nv,
                                "faces": nf,
                            }
                        )
                        mesh_cache[mesh_hash] = (filename, meshname)
                    filename, meshname = mesh_cache[mesh_hash]
                    snapshot = f"assets/{len(source_assets)}{asset.suffix.lower()}"
                    (root / "upstream" / snapshot).write_bytes(original)
                    source_assets.append(
                        {
                            "uri": uri,
                            "file": snapshot,
                            "sha256": hashlib.sha256(original).hexdigest(),
                            "scale": size,
                        }
                    )
                    g["mesh"] = meshname
                    cs = consumer_e.find("geometry/mesh")
                    cs.set("filename", "../meshes/" + filename)
                    cs.set("scale", "1 1 1")
                if min(size) <= 0:
                    raise ValueError("Geometry dimensions must be positive")
                geoms.append(g)
    if len(geoms) > 4096:
        raise ValueError("Too many URDF geometries")
    for hint in consumer.findall("mujoco"):
        consumer.remove(hint)
    ET.SubElement(
        ET.SubElement(consumer, "mujoco"),
        "compiler",
        fusestatic="false",
        discardvisual="false",
        strippath="false",
    )
    save(consumer, root / "upstream/consumer.urdf")
    profile = {
        "name": robot_name,
        "format": "urdf",
        "directory": ".",
        "entry": "consumer.urdf",
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "assets": source_assets,
    }
    r = {
        "schema": SCHEMA,
        "name": robot_name,
        "units": {
            "length": "m",
            "mass": "kg",
            "angle": "rad",
            "time": "s",
            "quaternion": "wxyz",
        },
        "source": profile,
        "bodies": bodies,
        "joints": joints,
        "geometries": geoms,
        "meshes": meshes,
        "actuators": [],
        "sites": [],
        "sensors": [],
        "simulation": {"timestep": 0.002, "gravity": [0.0, 0.0, -9.81]},
        "requirements": [
            {
                "id": "preserve-source-structure",
                "status": "imported-awaiting-projection-check",
            },
            {"id": "physical-performance", "status": "open"},
            {"id": "manufacturing-qualification", "status": "open"},
        ],
        "controller": {
            "platform": robot_name,
            "servo_family": "unknown",
            "action_joints": [],
            "observation_contract": "not-imported",
            "runtime_calibration": "not-imported",
            "policy_weights": "not-imported",
            "deployment_ready": False,
        },
        "lineage": [],
        "physical_status": "unverified",
    }
    r["controller"]["plant_sha256"] = plant(r)
    validate(r)
    write(
        root / "urdf-import.json",
        {
            "schema": "fk-urdf-import-v1",
            "source": profile,
            "scope": "fixed/revolute/continuous/prismatic trees, explicit inertials, separate geometry, declared limits",
            "assumptions": [
                "SI units follow URDF",
                "Simulation defaults .002 s, gravity [0,0,-9.81]; not specified by URDF",
                "Collision friction defaults are placeholders; no actuator law inferred",
            ],
            "losses": [
                "XML ordering/formatting, geometry/material occurrence names",
                "OBJ normals/UV and STL normals; triangle geometry retained",
            ],
            "physical_status": "unverified",
        },
    )
    return r


def import_urdf(path, output, packages=None):
    from .bundle import finish, seal
    from .validation import check_projection

    base = Path(output).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    root = base / ("urdf-" + uuid.uuid4().hex[:8])
    root.mkdir()
    try:
        r = from_urdf(path, root, packages)
        result = finish(r, root)
        checked = check_projection(root)
        if not checked["accepted"]:
            raise ValueError("URDF import failed independent projection checks")
        write(root / "projection-check.json", checked)
        seal(root)
        result["projection_accepted"] = True
        return result
    except Exception:
        shutil.rmtree(root)
        raise
