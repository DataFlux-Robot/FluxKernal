"""Native robot IR. SI, parent-local body frames, wxyz quaternions.

URDF/MJCF are projections; native robot.json is the design authority. Source bytes
are provenance, never silently reloaded to generate a changed native design.
"""

import hashlib
import json
import math
from pathlib import Path
from .sources import safe

SCHEMA = "fk-robot-v1"


def canonical(data):
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest(data):
    return hashlib.sha256(canonical(data)).hexdigest()


def write(path, data):
    Path(path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )


def plant(robot):
    return digest(
        {
            k: robot[k]
            for k in (
                "units",
                "bodies",
                "joints",
                "geometries",
                "meshes",
                "actuators",
                "sites",
                "sensors",
                "simulation",
            )
        }
    )


def vector(v, n):
    return (
        isinstance(v, list)
        and len(v) == n
        and all(type(x) in (int, float) and math.isfinite(x) for x in v)
    )


def validate(r):
    if r.get("schema") != SCHEMA:
        raise ValueError("Unsupported native robot schema")
    if r["units"] != {
        "length": "m",
        "mass": "kg",
        "angle": "rad",
        "time": "s",
        "quaternion": "wxyz",
    }:
        raise ValueError("Native units must be explicit SI/wxyz")
    bodies = r["bodies"]
    joints = r["joints"]
    checks = []

    def check(condition, code):
        if not condition:
            raise ValueError(code)
        checks.append(code)

    check(0 < len(bodies) <= 256, "body-count")
    for records, kind in [
        (bodies, "body"),
        (joints, "joint"),
        (r["geometries"], "geometry"),
        (r["meshes"], "mesh"),
        (r["sites"], "site"),
        (r["actuators"], "actuator"),
        (r["sensors"], "sensor"),
    ]:
        names = [p["name"] for p in records]
        check(
            len(names) == len(set(names))
            and all(isinstance(n, str) and n for n in names),
            kind + "-identity",
        )
    for i, b in enumerate(bodies, 1):
        check(type(b["parent"]) is int and 0 <= b["parent"] < i, "parent-precedes")
        check(
            type(b["mass"]) in (int, float)
            and math.isfinite(b["mass"])
            and b["mass"] >= 0,
            "nonnegative-mass",
        )
        for field, n in [
            ("position", 3),
            ("quaternion", 4),
            ("inertial_position", 3),
            ("inertial_quaternion", 4),
            ("principal_inertia", 3),
        ]:
            check(vector(b[field], n), "body-" + field)
        for key in ["quaternion", "inertial_quaternion"]:
            check(abs(sum(x * x for x in b[key]) - 1) < 1e-7, "unit-" + key)
        inertia = b["principal_inertia"]
        check(
            min(inertia) >= 0 and 2 * max(inertia) <= sum(inertia) + 1e-12,
            "principal-inertia-realizable",
        )
        check(
            (b["mass"] == 0 and max(inertia) == 0)
            or (b["mass"] > 0 and min(inertia) > 0),
            "mass-inertia-consistent",
        )
    check(sum(b["parent"] == 0 for b in bodies) == 1, "single-root")
    for j in joints:
        check(type(j["body"]) is int and 1 <= j["body"] <= len(bodies), "joint-body")
        check(j["kind"] in ["hinge", "slide", "free", "ball"], "joint-kind")
        check(
            vector(j["axis"], 3) and vector(j["position"], 3) and vector(j["range"], 2),
            "joint-vectors",
        )
        check(
            type(j["limited"]) is bool
            and (not j["limited"] or j["range"][0] <= j["range"][1]),
            "ordered-limits",
        )
        if j["kind"] in ("hinge", "slide"):
            check(abs(sum(x * x for x in j["axis"]) - 1) < 1e-7, "unit-joint-axis")
        for field in ("damping", "frictionloss", "armature"):
            check(vector([j[field]], 1) and j[field] >= 0, "joint-" + field)
        check(
            j["reference"] is None
            if j["kind"] in ("free", "ball")
            else vector([j["reference"]], 1),
            "joint-reference",
        )
        if j["kind"] == "free":
            check(bodies[j["body"] - 1]["parent"] == 0, "free-joint-root")
        for field in ("effort_limit", "velocity_limit"):
            value = j.get(field)
            check(
                value is None or (vector([value], 1) and value >= 0), "joint-" + field
            )
    fixed_names = [b["fixed_joint_name"] for b in bodies if "fixed_joint_name" in b]
    check(
        all(isinstance(n, str) and n for n in fixed_names)
        and len(set(fixed_names)) == len(fixed_names)
        and not set(fixed_names) & {j["name"] for j in joints},
        "fixed-joint-identity",
    )
    for b in bodies:
        if "fixed_joint_name" in b:
            check(
                b["parent"] != 0
                and not any(j["body"] == bodies.index(b) + 1 for j in joints),
                "fixed-joint-body",
            )
    for g in r["geometries"]:
        check(type(g["body"]) is int and 1 <= g["body"] <= len(bodies), "geometry-body")
        check(
            vector(g["position"], 3)
            and vector(g["quaternion"], 4)
            and vector(g["size"], 3),
            "geometry-frame",
        )
        check(
            abs(sum(x * x for x in g["quaternion"]) - 1) < 1e-7,
            "unit-geometry-quaternion",
        )
        check(
            vector(g["rgba"], 4) and all(0 <= x <= 1 for x in g["rgba"]),
            "geometry-color",
        )
        check(vector(g["friction"], 3) and min(g["friction"]) >= 0, "geometry-friction")
        check(vector([g["margin"], g["gap"]], 2), "geometry-contact")
        check(
            all(
                type(g[k]) is int and g[k] >= 0
                for k in ("group", "contype", "conaffinity")
            ),
            "geometry-masks",
        )
        if g["kind"] == "mesh":
            check(g["mesh"] in [m["name"] for m in r["meshes"]], "geometry-mesh")
    for site in r["sites"]:
        check(
            type(site["body"]) is int and 1 <= site["body"] <= len(bodies), "site-body"
        )
        check(
            vector(site["position"], 3)
            and vector(site["quaternion"], 4)
            and vector(site["size"], 3),
            "site-frame",
        )
        check(
            abs(sum(x * x for x in site["quaternion"]) - 1) < 1e-7,
            "unit-site-quaternion",
        )
    references = {
        "body": bodies,
        "xbody": bodies,
        "joint": joints,
        "site": r["sites"],
        "geom": r["geometries"],
        "actuator": r["actuators"],
    }
    for sensor in r["sensors"]:
        check(
            sensor["object_type"] in references
            and sensor["object"]
            in [x["name"] for x in references[sensor["object_type"]]],
            "sensor-reference",
        )
    for actuator in r["actuators"]:
        for key, size in [
            ("gear", 6),
            ("gain", 10),
            ("bias", 10),
            ("ctrlrange", 2),
            ("forcerange", 2),
        ]:
            check(vector(actuator[key], size), "actuator-" + key)
        for flag, key in [("ctrllimited", "ctrlrange"), ("forcelimited", "forcerange")]:
            check(
                type(actuator[flag]) is bool
                and (not actuator[flag] or actuator[key][0] <= actuator[key][1]),
                "actuator-limits",
            )
    check(
        vector([r["simulation"]["timestep"]], 1)
        and r["simulation"]["timestep"] > 0
        and vector(r["simulation"]["gravity"], 3),
        "simulation-options",
    )
    check(
        r["controller"]["deployment_ready"] is False
        and r["physical_status"] == "unverified",
        "physical-evidence-required",
    )
    names = [j["name"] for j in joints]
    actions = [a["joint"] for a in r["actuators"]]
    check(
        len(actions) == len(set(actions)) and all(n in names for n in actions),
        "actuator-joint-coverage",
    )
    check(r["controller"]["action_joints"] == actions, "controller-action-order")
    check(r["controller"]["plant_sha256"] == plant(r), "controller-plant-binding")
    return {
        "accepted": True,
        "checks": sorted(set(checks)),
        "scope": "native structure and declared controller binding",
        "physical_status": "unverified",
    }


def from_mujoco(model, profile, mesh_dir):
    import mujoco as mj

    def name(kind, i):
        return mj.mj_id2name(model, kind, i) or f"{kind.name.lower()}_{i}"

    def arr(a):
        return a.tolist()

    if model.ntendon or model.neq or model.nflex:
        raise ValueError(
            "Tendons, equality loops and deformables require a future native adapter; refusing loss"
        )
    bodies = [
        {
            "name": name(mj.mjtObj.mjOBJ_BODY, i),
            "parent": int(model.body_parentid[i]),
            "position": arr(model.body_pos[i]),
            "quaternion": arr(model.body_quat[i]),
            "mass": float(model.body_mass[i]),
            "inertial_position": arr(model.body_ipos[i]),
            "inertial_quaternion": arr(model.body_iquat[i]),
            "principal_inertia": arr(model.body_inertia[i]),
            "manufacturing": {
                "route": "unresolved",
                "reason": "A simulated rigid body can aggregate multiple printed and purchased parts",
            },
            "inertial_source": "upstream compiled model; not measured",
        }
        for i in range(1, model.nbody)
    ]
    joints = []
    for i in range(model.njnt):
        kind = mj.mjtJoint(int(model.jnt_type[i])).name.removeprefix("mjJNT_").lower()
        d = int(model.jnt_dofadr[i])
        q = int(model.jnt_qposadr[i])
        joints.append(
            {
                "name": name(mj.mjtObj.mjOBJ_JOINT, i),
                "body": int(model.jnt_bodyid[i]),
                "kind": kind,
                "position": arr(model.jnt_pos[i]),
                "axis": arr(model.jnt_axis[i]),
                "limited": bool(model.jnt_limited[i]),
                "range": arr(model.jnt_range[i]),
                "reference": float(model.qpos0[q])
                if kind in ("hinge", "slide")
                else None,
                "damping": float(model.dof_damping[d]),
                "frictionloss": float(model.dof_frictionloss[d]),
                "armature": float(model.dof_armature[d]),
                "velocity_limit": None,
            }
        )
    meshes = []
    mesh_dir = Path(mesh_dir)
    mesh_dir.mkdir(parents=True, exist_ok=True)
    for i in range(model.nmesh):
        start = int(model.mesh_vertadr[i])
        count = int(model.mesh_vertnum[i])
        fstart = int(model.mesh_faceadr[i])
        fc = int(model.mesh_facenum[i])
        lines = [
            "# FluxKernel compiled mesh; coordinates in metres in compiled mesh frame"
        ]
        lines += [
            "v " + " ".join(format(float(v), ".17g") for v in p)
            for p in model.mesh_vert[start : start + count]
        ]
        lines += [
            "f " + " ".join(str(int(v) + 1) for v in p)
            for p in model.mesh_face[fstart : fstart + fc]
        ]
        raw = ("\n".join(lines) + "\n").encode()
        path = f"mesh-{i}.obj"
        (mesh_dir / path).write_bytes(raw)
        meshes.append(
            {
                "name": name(mj.mjtObj.mjOBJ_MESH, i),
                "file": "meshes/" + path,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "vertices": count,
                "faces": fc,
            }
        )
    geoms = []
    for i in range(model.ngeom):
        if int(model.geom_bodyid[i]) == 0:
            raise ValueError(
                "Import robot model separately from world/environment geometry"
            )
        kind = mj.mjtGeom(int(model.geom_type[i])).name.removeprefix("mjGEOM_").lower()
        mat = int(model.geom_matid[i])
        rgba = arr(model.mat_rgba[mat]) if mat >= 0 else arr(model.geom_rgba[i])
        geoms.append(
            {
                "name": name(mj.mjtObj.mjOBJ_GEOM, i),
                "body": int(model.geom_bodyid[i]),
                "kind": kind,
                "position": arr(model.geom_pos[i]),
                "quaternion": arr(model.geom_quat[i]),
                "size": arr(model.geom_size[i]),
                "mesh": name(mj.mjtObj.mjOBJ_MESH, int(model.geom_dataid[i]))
                if kind == "mesh"
                else None,
                "rgba": rgba,
                "group": int(model.geom_group[i]),
                "contype": int(model.geom_contype[i]),
                "conaffinity": int(model.geom_conaffinity[i]),
                "friction": arr(model.geom_friction[i]),
                "margin": float(model.geom_margin[i]),
                "gap": float(model.geom_gap[i]),
            }
        )
    acts = []
    for i in range(model.nu):
        if model.actuator_trntype[i] != mj.mjtTrn.mjTRN_JOINT:
            raise ValueError("Only joint transmissions supported")
        if (
            model.actuator_dyntype[i] != mj.mjtDyn.mjDYN_NONE
            or model.actuator_gaintype[i] != mj.mjtGain.mjGAIN_FIXED
            or model.actuator_biastype[i] != mj.mjtBias.mjBIAS_AFFINE
        ):
            raise ValueError("Unsupported actuator law")
        acts.append(
            {
                "name": name(mj.mjtObj.mjOBJ_ACTUATOR, i),
                "joint": name(mj.mjtObj.mjOBJ_JOINT, int(model.actuator_trnid[i, 0])),
                "gear": arr(model.actuator_gear[i]),
                "gain": arr(model.actuator_gainprm[i]),
                "bias": arr(model.actuator_biasprm[i]),
                "ctrlrange": arr(model.actuator_ctrlrange[i]),
                "forcerange": arr(model.actuator_forcerange[i]),
                "ctrllimited": bool(model.actuator_ctrllimited[i]),
                "forcelimited": bool(model.actuator_forcelimited[i]),
            }
        )
    sites = [
        {
            "name": name(mj.mjtObj.mjOBJ_SITE, i),
            "body": int(model.site_bodyid[i]),
            "position": arr(model.site_pos[i]),
            "quaternion": arr(model.site_quat[i]),
            "size": arr(model.site_size[i]),
        }
        for i in range(model.nsite)
    ]
    # Sensors are native typed references, not raw XML retained as the authority.
    sensors = []
    for i in range(model.nsensor):
        kind = (
            mj.mjtSensor(int(model.sensor_type[i])).name.removeprefix("mjSENS_").lower()
        )
        objtype = mj.mjtObj(int(model.sensor_objtype[i]))
        obj = name(objtype, int(model.sensor_objid[i]))
        sensors.append(
            {
                "name": name(mj.mjtObj.mjOBJ_SENSOR, i),
                "kind": kind,
                "object_type": objtype.name.removeprefix("mjOBJ_").lower(),
                "object": obj,
            }
        )
    r = {
        "schema": SCHEMA,
        "name": profile["name"],
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
        "actuators": acts,
        "sites": sites,
        "sensors": sensors,
        "simulation": {
            "timestep": float(model.opt.timestep),
            "gravity": arr(model.opt.gravity),
        },
        "requirements": [
            {"id": "preserve-source-structure", "status": "checked-on-import"},
            {"id": "physical-performance", "status": "open"},
            {"id": "manufacturing-qualification", "status": "open"},
        ],
        "controller": {
            "platform": profile["name"],
            "servo_family": profile.get("servo", "unknown"),
            "action_joints": [a["joint"] for a in acts],
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
    return r


def read(bundle):
    root = Path(bundle)
    r = json.loads((root / "robot.json").read_text())
    validate(r)
    for m in r["meshes"]:
        if (
            hashlib.sha256(safe(root, m["file"]).read_bytes()).hexdigest()
            != m["sha256"]
        ):
            raise ValueError("Mesh content changed")
    for item in r.get("manufacturing", {}).get("items", []):
        if (
            hashlib.sha256(safe(root, item["file"]).read_bytes()).hexdigest()
            != item["sha256"]
        ):
            raise ValueError("Hardware source content changed")
    for part in r.get("custom_parts", []):
        for file, expected in part["artifacts"].items():
            if hashlib.sha256(safe(root, file).read_bytes()).hexdigest() != expected:
                raise ValueError("Custom part CAD artifact changed")
    return r
