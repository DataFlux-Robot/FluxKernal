"""Independent numeric forward-kinematics and projection consumer checks."""

from pathlib import Path
import numpy as np
from .native import read
from .projection import quatmat


def transform(p, q):
    m = np.eye(4)
    m[:3, :3] = quatmat(q)
    m[:3, 3] = p
    return m


def forward(r, positions):
    matrices = {0: np.eye(4)}
    for i, b in enumerate(r["bodies"], 1):
        t = transform(b["position"], b["quaternion"])
        for j in [j for j in r["joints"] if j["body"] == i and j["kind"] != "free"]:
            value = positions[j["name"]] - j["reference"]
            axis = np.array(j["axis"])
            p = np.array(j["position"])
            m = np.eye(4)
            if j["kind"] == "hinge":
                x, y, z = axis
                k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
                rot = np.eye(3) + np.sin(value) * k + (1 - np.cos(value)) * (k @ k)
                m[:3, :3] = rot
                m[:3, 3] = p - rot @ p
            elif j["kind"] == "slide":
                m[:3, 3] = axis * value
            else:
                raise ValueError("Unsupported numeric FK joint")
            t = t @ m
        matrices[i] = matrices[b["parent"]] @ t
    return matrices


def check_projection(bundle):
    import mujoco as mj
    from .bundle import verify

    root = Path(bundle)
    verify(root)
    r = read(root)
    exported = mj.MjModel.from_xml_path(str(root / "robot.xml"))
    urdf = mj.MjModel.from_xml_path(str(root / "robot.urdf"))
    models = [("native-mjcf", exported), ("urdf", urdf)]
    original_path = root / "upstream" / r["source"]["directory"] / r["source"]["entry"]
    if not r["lineage"]:
        models.append(("upstream", mj.MjModel.from_xml_path(str(original_path))))
    mesh_vertices = {
        m["name"]: np.array(
            [
                [float(x) for x in line.split()[1:4]]
                for line in (root / m["file"]).read_text().splitlines()
                if line.startswith("v ")
            ]
        )
        for m in r["meshes"]
    }
    rows = []
    for fraction in [None, 0.35, 0.65]:
        pos = {
            j["name"]: j["reference"]
            if fraction is None
            else j["range"][0] + fraction * (j["range"][1] - j["range"][0])
            if j["limited"]
            else j["reference"] + 0.2
            for j in r["joints"]
            if j["kind"] in ("hinge", "slide")
        }
        native = forward(r, pos)
        for label, model in models:
            data = mj.MjData(model)
            for j in r["joints"]:
                if j["kind"] not in ("hinge", "slide"):
                    continue
                idx = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, j["name"])
                if idx < 0:
                    raise ValueError("Joint missing from projection")
                data.qpos[model.jnt_qposadr[idx]] = pos[j["name"]] - (
                    j["reference"] if label == "urdf" else 0
                )
            mj.mj_forward(model, data)
            world_to_root = np.linalg.inv(native[1]) if label == "urdf" else np.eye(4)
            errors = []
            inertia_errors = []
            mass_errors = []
            for i, b in enumerate(r["bodies"], 1):
                idx = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, b["name"])
                if idx < 0:
                    raise ValueError("Body missing from projection")
                expected = world_to_root @ native[i]
                if label == "urdf":
                    js = [
                        j for j in r["joints"] if j["body"] == i and j["kind"] != "free"
                    ]
                    offset = js[0]["position"] if js else [0, 0, 0]
                    expected = expected @ transform(offset, [1, 0, 0, 0])
                actual = np.eye(4)
                actual[:3, :3] = data.xmat[idx].reshape(3, 3)
                actual[:3, 3] = data.xpos[idx]
                errors.append(float(np.max(np.abs(actual - expected))))
                com = (
                    world_to_root
                    @ native[i]
                    @ transform(b["inertial_position"], b["inertial_quaternion"])
                )
                errors.append(float(np.max(np.abs(com[:3, 3] - data.xipos[idx]))))
                inertia = com[:3, :3] @ np.diag(b["principal_inertia"]) @ com[:3, :3].T
                actual_rot = data.ximat[idx].reshape(3, 3)
                actual_inertia = (
                    actual_rot @ np.diag(model.body_inertia[idx]) @ actual_rot.T
                )
                inertia_errors.append(float(np.max(np.abs(inertia - actual_inertia))))
                mass_errors.append(abs(float(model.body_mass[idx]) - b["mass"]))
            mesh_errors = []
            for gi, g in enumerate(r["geometries"]):
                if g["kind"] != "mesh":
                    continue
                idx = (
                    gi
                    if label == "upstream"
                    else mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, g["name"])
                )
                if idx < 0:
                    raise ValueError("Geometry missing from projection")
                expected = (
                    world_to_root
                    @ native[g["body"]]
                    @ transform(g["position"], g["quaternion"])
                )
                points = mesh_vertices[g["mesh"]] @ expected[:3, :3].T + expected[:3, 3]
                mi = int(model.geom_dataid[idx])
                start = int(model.mesh_vertadr[mi])
                count = int(model.mesh_vertnum[mi])
                actual = (
                    model.mesh_vert[start : start + count]
                    @ data.geom_xmat[idx].reshape(3, 3).T
                    + data.geom_xpos[idx]
                )
                for f in (np.min, np.max, np.mean):
                    mesh_errors.append(
                        float(np.max(np.abs(f(points, axis=0) - f(actual, axis=0))))
                    )
            rows.append(
                {
                    "consumer": label,
                    "pose_fraction": fraction,
                    "max_frame_error": max(errors),
                    "max_mass_error_kg": max(mass_errors),
                    "max_inertia_error_kg_m2": max(inertia_errors),
                    "max_mesh_moment_error_m": max(mesh_errors, default=0),
                    "accepted": max(mesh_errors, default=0) < 1e-6
                    and max(errors) < 1e-7
                    and max(mass_errors) < 1e-10
                    and max(inertia_errors) < 1e-9,
                }
            )
    return {
        "schema": "fk-robot-projection-check-v1",
        "accepted": all(r["accepted"] for r in rows),
        "checks": rows,
        "scope": "three deterministic FK poses, COM, mass, inertia and mesh bounds/centroids; not locomotion or dynamics equivalence",
        "physical_status": "unverified",
    }
