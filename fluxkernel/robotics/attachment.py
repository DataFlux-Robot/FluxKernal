"""Native additive parts with frozen source mechanisms and explicit interface gaps."""

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from .native import read, write, digest, plant
from .bundle import finish, verify, seal


def zone(bundle, target=None):
    import numpy as np
    from scipy.spatial.transform import Rotation
    from .validation import forward, transform

    root = Path(bundle)
    verify(root)
    r = read(root)
    target = target or {"microduck": "top_head_shell", "xgoduck": "head_roll"}.get(
        r["name"]
    )
    geoms = [g for g in r["geometries"] if g["mesh"] == target and g["group"] != 3]
    if len(geoms) != 1:
        raise ValueError("Need exactly one named exterior mesh occurrence")
    g = geoms[0]
    mesh = next(m for m in r["meshes"] if m["name"] == target)
    vertices = np.array(
        [
            [float(x) for x in line.split()[1:4]]
            for line in (root / mesh["file"]).read_text().splitlines()
            if line.startswith("v ")
        ]
    )
    frames = forward(
        r,
        {
            j["name"]: j["reference"]
            for j in r["joints"]
            if j["kind"] in ("hinge", "slide")
        },
    )
    body = frames[g["body"]]
    pose = body @ transform(g["position"], g["quaternion"])
    points = vertices @ pose[:3, :3].T + pose[:3, 3]
    lo = points.min(0)
    hi = points.max(0)
    # Intersect a vertical ray at the source XY center with its topmost triangle.
    # This establishes a geometric datum, not a qualified mounting interface.
    center = (lo + hi) / 2
    faces = [
        [int(v.split("/")[0]) - 1 for v in line.split()[1:4]]
        for line in (root / mesh["file"]).read_text().splitlines()
        if line.startswith("f ")
    ]
    hits = []
    for index, face in enumerate(faces):
        triangle = points[face]
        matrix = np.vstack([triangle[:, :2].T, np.ones(3)])
        if abs(np.linalg.det(matrix)) < 1e-14:
            continue
        weights = np.linalg.solve(matrix, np.r_[center[:2], 1.0])
        if np.min(weights) < -1e-8:
            continue
        point = weights @ triangle
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        normal /= np.linalg.norm(normal)
        if normal[2] < 0:
            normal = -normal
        hits.append((float(point[2]), index, point, normal))
    if not hits:
        raise ValueError(
            "Source top-center has no surface; an explicit mount adapter is required"
        )
    _, face_index, origin, normal = max(hits, key=lambda h: h[0])
    if normal[2] < 0.5:
        raise ValueError("Source surface is too steep for this pilot")
    x_axis = np.array([1.0, 0.0, 0.0]) - normal[0] * normal
    x_axis /= np.linalg.norm(x_axis)
    world_rotation = np.column_stack([x_axis, np.cross(normal, x_axis), normal])
    local = body[:3, :3].T @ (origin - body[:3, 3])
    q = Rotation.from_matrix(body[:3, :3].T @ world_rotation).as_quat().tolist()
    contract = {
        "schema": "fk-customization-zone-v1",
        "parent_native_sha256": digest(r),
        "target_geometry": g["name"],
        "target_mesh_sha256": mesh["sha256"],
        "parent_body": r["bodies"][g["body"] - 1]["name"],
        "parent_body_index": g["body"],
        "position": local.tolist(),
        "quaternion": [q[3], *q[:3]],
        "frame": "metres, wxyz; +Z source surface normal, +X projected rest-pose forward, +Y left tangent",
        "source_triangle": face_index,
        "surface_normal_world": normal.tolist(),
        "contact_origin_world_m": origin.tolist(),
        "source_bounds_world_m": [lo.tolist(), hi.tolist()],
        "max_extent_mm": [
            min(80.0, float((hi[0] - lo[0]) * 1000)),
            min(80.0, float((hi[1] - lo[1]) * 1000)),
            35.0,
        ],
        "max_added_mass_kg": sum(b["mass"] for b in r["bodies"]) * 0.02,
        "budget_basis": "Pilot design search bounds, not an experimentally validated control envelope",
        "interface_status": "unverified",
        "mounting_assumption": "Removable adhesive/pad prototype at the top-center surface tangent; curvature fit, adhesive and assembly not qualified",
        "frozen": [
            "original bodies",
            "original geometry",
            "joints",
            "actuators",
            "sensors",
            "sites",
            "action order",
        ],
        "open": [
            "Attachment curvature and retention",
            "Camera field of view and cooling",
            "Print process and actual mass",
            "Controller and physical validation",
        ],
    }
    return {**contract, "zone_sha256": digest(contract)}


def guards(parent, child):
    checks = {
        key: child[key] == parent[key]
        for key in ("joints", "actuators", "sensors", "sites", "simulation")
    }
    checks["original_bodies"] = (
        child["bodies"][: len(parent["bodies"])] == parent["bodies"]
    )
    checks["original_geometry"] = (
        child["geometries"][: len(parent["geometries"])] == parent["geometries"]
    )
    checks["original_meshes"] = (
        child["meshes"][: len(parent["meshes"])] == parent["meshes"]
    )
    checks["one_fixed_part"] = len(child["bodies"]) == len(parent["bodies"]) + 1
    checks["action_order"] = (
        child["controller"]["action_joints"] == parent["controller"]["action_joints"]
    )
    return {
        "accepted": all(checks.values()),
        "checks": checks,
        "scope": "Exact native record equality; nominal Python checks, not a Lean geometry theorem",
    }


def motion_check(root, original_count, target_geometry):
    import mujoco as mj

    r = read(root)
    model = mj.MjModel.from_xml_path(str(Path(root) / "robot.xml"))
    added = mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, r["geometries"][-1]["name"])
    joints = [j for j in r["joints"] if j["kind"] in ("hinge", "slide")]
    poses = [{}] + [{j["name"]: v} for j in joints if j["limited"] for v in j["range"]]
    poses += [
        {
            j["name"]: j["range"][0] + f * (j["range"][1] - j["range"][0])
            for j in joints
            if j["limited"]
        }
        for f in (0.35, 0.65)
    ]
    rows = []
    for n, pose in enumerate(poses):
        data = mj.MjData(model)
        for name, value in pose.items():
            data.qpos[
                model.jnt_qposadr[mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, name)]
            ] = value
        mj.mj_forward(model, data)
        worst = 1.0
        nearest = None
        for g in r["geometries"][:original_count]:
            if g["group"] == 3 or g["name"] == target_geometry:
                continue
            i = mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, g["name"])
            distance = float(mj.mj_geomDistance(model, data, added, i, 0.1, None))
            if distance < worst:
                worst = distance
                nearest = g["name"]
        rows.append(
            {
                "pose": n,
                "minimum_distance_m": worst,
                "nearest_geometry": nearest,
                "accepted": worst >= -0.0002,
            }
        )
    return {
        "accepted": all(x["accepted"] for x in rows),
        "poses": rows,
        "tolerance_m": 0.0002,
        "scope": "Sampled convex-hull mesh distances against original visible geometry; target contact excluded. Not continuous collision, camera visibility or real fit validation.",
    }


def attach(parent, recipe, output, target=None):
    from .part_geometry import checked

    parent = Path(parent)
    verify(parent)
    before = read(parent)
    contract = zone(parent, target)
    recipe = checked(recipe).model_dump()
    if recipe["zone_sha256"] != contract["zone_sha256"]:
        raise ValueError("Stale or incorrect customization zone")
    part_name = "custom_" + recipe["name"]
    if any(b["name"] == part_name for b in before["bodies"]):
        raise ValueError("Part name already exists")
    root = Path(output).expanduser().resolve() / (
        before["name"] + "-part-" + uuid.uuid4().hex[:8]
    )
    root.mkdir(parents=True)
    write(root / "request.json", recipe)
    write(root / "zone.json", contract)
    cad = root / "cad" / part_name
    cad.mkdir(parents=True)
    try:
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "fluxkernel.robotics.part_geometry",
                str(root / "request.json"),
                str(cad),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        (root / "cad-build.log").write_text("CAD worker exceeded the fixed 120 second budget")
        raise ValueError("CAD worker exceeded the fixed 120 second budget; simplify the recipe") from exc
    (root / "cad-build.log").write_text(p.stdout + p.stderr)
    if p.returncode:
        raise ValueError(
            "Part CAD rejected: "
            + (
                p.stderr.strip().splitlines()[-1]
                if p.stderr.strip()
                else "worker failed"
            )
        )
    prop = json.loads((cad / "properties.json").read_text())
    lo, hi = prop["bbox_mm"]
    extent = contract["max_extent_mm"]
    if (
        any(
            lo[i] < -extent[i] / 2 - 1e-5 or hi[i] > extent[i] / 2 + 1e-5
            for i in (0, 1)
        )
        or hi[2] > extent[2] + 1e-5
    ):
        raise ValueError("Part exceeds frozen customization extent")
    if prop["mass_kg"] > contract["max_added_mass_kg"]:
        raise ValueError("Part exceeds experimental added-mass budget")
    for folder in ("meshes", "upstream", "hardware"):
        if (parent / folder).exists():
            shutil.copytree(parent / folder, root / folder)
    if (parent / "cad").exists():
        shutil.copytree(parent / "cad", root / "cad", dirs_exist_ok=True)
    child = copy.deepcopy(before)
    idx = len(child["bodies"]) + 1
    child["bodies"].append(
        {
            "name": part_name,
            "parent": contract["parent_body_index"],
            "position": contract["position"],
            "quaternion": contract["quaternion"],
            "mass": prop["mass_kg"],
            "inertial_position": prop["inertial_position"],
            "inertial_quaternion": prop["inertial_quaternion"],
            "principal_inertia": prop["principal_inertia"],
            "manufacturing": {
                "route": "print-candidate",
                "material": recipe["material"],
                "qualification": "unverified",
            },
            "inertial_source": prop["mass_basis"],
        }
    )
    mesh_file = "meshes/" + part_name + ".obj"
    shutil.copyfile(cad / "part.obj", root / mesh_file)
    mesh = {
        "name": part_name,
        "file": mesh_file,
        "sha256": hashlib.sha256((root / mesh_file).read_bytes()).hexdigest(),
        "vertices": prop["vertices"],
        "faces": prop["faces"],
    }
    child["meshes"].append(mesh)
    for collision in (False, True):
        child["geometries"].append(
            {
                "name": part_name + ("_collision" if collision else "_visual"),
                "body": idx,
                "kind": "mesh",
                "position": [0.0, 0.0, 0.0],
                "quaternion": [1.0, 0.0, 0.0, 0.0],
                "size": [0.0, 0.0, 0.0],
                "mesh": part_name,
                "rgba": [*recipe["color_rgb"], 1.0],
                "group": 3 if collision else 2,
                "contype": 1 if collision else 0,
                "conaffinity": 1 if collision else 0,
                "friction": [1.0, 0.005, 0.0001],
                "margin": 0.0,
                "gap": 0.0,
            }
        )
    files = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in cad.iterdir()
        if p.is_file()
    }
    child.setdefault("custom_parts", []).append(
        {
            "body": part_name,
            "recipe": recipe,
            "zone": contract,
            "artifacts": files,
            "interface_status": "unverified",
        }
    )
    child["controller"]["plant_sha256"] = plant(child)
    child["controller"]["status"] = "requires-revalidation"
    child["controller"]["deployment_ready"] = False
    child["lineage"].append(
        {
            "parent_native_sha256": digest(before),
            "operation": "attach_part",
            "recipe_sha256": digest(recipe),
            "invalidated": [
                "source dynamics equivalence",
                "policy suitability",
                "physical integration",
            ],
        }
    )
    for req in child["requirements"]:
        if req["id"] == "preserve-source-structure":
            req["status"] = "superseded-by-native-attachment"
    frozen = guards(before, child)
    if not frozen["accepted"]:
        raise ValueError("Frozen mechanism changed")
    write(root / "parent-native.json", before)
    write(root / "attachment-checks.json", frozen)
    result = finish(child, root)
    motion = motion_check(root, len(before["geometries"]), contract["target_geometry"])
    write(root / "motion-checks.json", motion)
    seal(root)
    return {
        **result,
        "accepted": motion["accepted"],
        "motion_passed": motion["accepted"],
        "motion_summary": {
            "minimum_distance_m": min(x["minimum_distance_m"] for x in motion["poses"]),
            "violations": [x for x in motion["poses"] if not x["accepted"]][:8],
        },
        "part_body": part_name,
        "added_mass_kg": prop["mass_kg"],
        "interface_status": "unverified",
        "recipe_sha256": digest(recipe),
    }
