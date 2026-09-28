"""Generate exchange formats from the native IR, never from upstream XML.

Ledger: body transforms are parent-local; joint anchor is body-local. URDF child
frames are shifted to hinge anchors; visuals and COM are shifted accordingly.
Root pose/freejoint belongs to the simulation world and is omitted from URDF.
URDF effort/velocity 0 for unknown limits means display-only, not actuator ratings.
"""

import math
from decimal import Decimal, localcontext
import xml.etree.ElementTree as ET
from pathlib import Path
from .native import validate, write


def nums(v):
    return " ".join(format(float(x), ".17g") for x in v)


def quatmat(q):
    import numpy as np

    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def rpy(q):
    m = quatmat(q)
    cy = math.hypot(m[0, 0], m[1, 0])
    y = math.atan2(-m[2, 0], cy)
    return (
        [math.atan2(m[2, 1], m[2, 2]), y, math.atan2(m[1, 0], m[0, 0])]
        if cy > 1e-12
        else [math.atan2(-m[1, 2], m[1, 1]), y, 0]
    )


def save(root, path):
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def mjcf(r, path):
    validate(r)
    root = ET.Element("mujoco", model=r["name"])
    ET.SubElement(root, "compiler", angle="radian", autolimits="true")
    ET.SubElement(
        root,
        "option",
        timestep=str(r["simulation"]["timestep"]),
        gravity=nums(r["simulation"]["gravity"]),
    )
    asset = ET.SubElement(root, "asset")
    for m in r["meshes"]:
        ET.SubElement(asset, "mesh", name=m["name"], file=m["file"])
    world = ET.SubElement(root, "worldbody")
    nodes = {0: world}
    for i, b in enumerate(r["bodies"], 1):
        body = ET.SubElement(
            nodes[b["parent"]],
            "body",
            name=b["name"],
            pos=nums(b["position"]),
            quat=nums(b["quaternion"]),
        )
        nodes[i] = body
        if b["mass"] > 0:
            ET.SubElement(
                body,
                "inertial",
                pos=nums(b["inertial_position"]),
                quat=nums(b["inertial_quaternion"]),
                mass=str(b["mass"]),
                diaginertia=nums(b["principal_inertia"]),
            )
        for j in [j for j in r["joints"] if j["body"] == i]:
            if j["kind"] == "free":
                ET.SubElement(body, "freejoint", name=j["name"])
                continue
            attrs = {
                "name": j["name"],
                "type": j["kind"],
                "pos": nums(j["position"]),
                "axis": nums(j["axis"]),
                "limited": str(j["limited"]).lower(),
                "damping": str(j["damping"]),
                "armature": str(j["armature"]),
                "frictionloss": str(j["frictionloss"]),
            }
            if j["limited"]:
                attrs["range"] = nums(j["range"])
            if j["reference"] is not None:
                attrs["ref"] = str(j["reference"])
            ET.SubElement(body, "joint", **attrs)
        for g in [g for g in r["geometries"] if g["body"] == i]:
            attrs = {
                "name": g["name"],
                "type": g["kind"],
                "pos": nums(g["position"]),
                "quat": nums(g["quaternion"]),
                "rgba": nums(g["rgba"]),
                "group": str(g["group"]),
                "contype": str(g["contype"]),
                "conaffinity": str(g["conaffinity"]),
                "friction": nums(g["friction"]),
                "margin": str(g["margin"]),
                "gap": str(g["gap"]),
                "mass": "0",
            }
            if g["kind"] == "mesh":
                attrs["mesh"] = g["mesh"]
            else:
                attrs["size"] = nums(g["size"])
            ET.SubElement(body, "geom", **attrs)
        for s in [s for s in r["sites"] if s["body"] == i]:
            ET.SubElement(
                body,
                "site",
                name=s["name"],
                pos=nums(s["position"]),
                quat=nums(s["quaternion"]),
                size=nums(s["size"]),
            )
    sensors = ET.SubElement(root, "sensor")
    for s in r["sensors"]:
        attrs = {"name": s["name"]}
        if s["kind"].startswith("frame"):
            attrs.update(objtype=s["object_type"], objname=s["object"])
        else:
            attrs[s["object_type"]] = s["object"]
        ET.SubElement(sensors, s["kind"], **attrs)
    act = ET.SubElement(root, "actuator")
    for a in r["actuators"]:
        ET.SubElement(
            act,
            "general",
            name=a["name"],
            joint=a["joint"],
            gear=nums(a["gear"]),
            gaintype="fixed",
            biastype="affine",
            gainprm=nums(a["gain"]),
            biasprm=nums(a["bias"]),
            ctrllimited=str(a["ctrllimited"]).lower(),
            forcelimited=str(a["forcelimited"]).lower(),
            ctrlrange=nums(a["ctrlrange"]),
            forcerange=nums(a["forcerange"]),
        )
    save(root, path)
    return {
        "format": "mjcf",
        "authority": "robot.json",
        "scope": "kinematics, inertials, geometry, basic joint actuation and sensors",
        "not_preserved": [
            "upstream training environment and BAM Python actuator wrapper",
            "policy weights and calibration",
            "contact solver settings, exclusions/pairs and simulation options beyond timestep/gravity",
            "materials/textures beyond RGBA and site display shape",
        ],
        "physical_status": "unverified",
    }


def shifted_decimal(value, reference):
    # Decimal strings express the native contract exactly; float subtraction would
    # silently round the range and break exact translation validation.
    with localcontext() as context:
        context.prec = 800
        result = Decimal(str(value)) - Decimal(str(reference))
    if not math.isfinite(float(result)):
        raise ValueError("URDF shifted limit overflows consumer float range")
    return format(result, "f")


def urdf_xml(r):
    import numpy as np

    validate(r)
    root = ET.Element("robot", name=r["name"])
    mj = ET.SubElement(root, "mujoco")
    ET.SubElement(
        mj, "compiler", fusestatic="false", discardvisual="false", strippath="false"
    )
    offsets = {0: np.zeros(3)}
    joint_for = {}
    for i, b in enumerate(r["bodies"], 1):
        js = [j for j in r["joints"] if j["body"] == i and j["kind"] != "free"]
        if len(js) > 1 or any(j["kind"] == "ball" for j in js):
            raise ValueError("URDF tree projection needs one hinge/slide per body")
        if b["parent"] == 0 and js:
            raise ValueError("URDF projection cannot drop a root joint")
        if any(j["kind"] == "slide" and not j["limited"] for j in js):
            raise ValueError("URDF prismatic joint needs finite limits")
        joint_for[i] = js[0] if js else None
        offsets[i] = np.array(js[0]["position"] if js else [0, 0, 0])
        link = ET.SubElement(root, "link", name=b["name"])
        if b["mass"] > 0:
            inert = ET.SubElement(link, "inertial")
            ET.SubElement(
                inert,
                "origin",
                xyz=nums(np.array(b["inertial_position"]) - offsets[i]),
                rpy=nums(rpy(b["inertial_quaternion"])),
            )
            ET.SubElement(inert, "mass", value=str(b["mass"]))
            v = b["principal_inertia"]
            ET.SubElement(
                inert,
                "inertia",
                ixx=str(v[0]),
                iyy=str(v[1]),
                izz=str(v[2]),
                ixy="0",
                ixz="0",
                iyz="0",
            )
        for g in [g for g in r["geometries"] if g["body"] == i]:
            tags = ["collision"] if g["contype"] or g["conaffinity"] else ["visual"]
            # Noncontact helper collision meshes (group 3) are retained as visual,
            # but are not promoted into collision geometry in this projection.
            for tag in tags:
                e = ET.SubElement(link, tag, name=g["name"])
                ET.SubElement(
                    e,
                    "origin",
                    xyz=nums(np.array(g["position"]) - offsets[i]),
                    rpy=nums(rpy(g["quaternion"])),
                )
                geom = ET.SubElement(e, "geometry")
                size = g["size"]
                if g["kind"] == "mesh":
                    ET.SubElement(
                        geom,
                        "mesh",
                        filename=next(
                            m["file"] for m in r["meshes"] if m["name"] == g["mesh"]
                        ),
                        scale="1 1 1",
                    )
                elif g["kind"] == "box":
                    ET.SubElement(geom, "box", size=nums([2 * x for x in size]))
                elif g["kind"] == "sphere":
                    ET.SubElement(geom, "sphere", radius=str(size[0]))
                elif g["kind"] == "cylinder":
                    ET.SubElement(
                        geom, "cylinder", radius=str(size[0]), length=str(2 * size[1])
                    )
                else:
                    raise ValueError(
                        "URDF does not represent this geometry without explicit conversion: "
                        + g["kind"]
                    )
                if tag == "visual":
                    ET.SubElement(
                        ET.SubElement(e, "material", name=g["name"] + "-color"),
                        "color",
                        rgba=nums(g["rgba"]),
                    )
    for i, b in enumerate(r["bodies"], 1):
        if b["parent"] == 0:
            continue
        j = joint_for[i]
        kind = (
            ("revolute" if j["limited"] else "continuous")
            if j and j["kind"] == "hinge"
            else "prismatic"
            if j
            else "fixed"
        )
        e = ET.SubElement(
            root,
            "joint",
            name=j["name"] if j else b.get("fixed_joint_name", b["name"] + "-fixed"),
            type=kind,
        )
        ET.SubElement(e, "parent", link=r["bodies"][b["parent"] - 1]["name"])
        ET.SubElement(e, "child", link=b["name"])
        origin = (
            np.array(b["position"])
            + quatmat(b["quaternion"]) @ offsets[i]
            - offsets[b["parent"]]
        )
        ET.SubElement(e, "origin", xyz=nums(origin), rpy=nums(rpy(b["quaternion"])))
        if j:
            ET.SubElement(e, "axis", xyz=" ".join(str(x) for x in j["axis"]))
            limits = {
                "effort": str(j.get("effort_limit") or 0),
                "velocity": str(j.get("velocity_limit") or 0),
            }
            if j["limited"]:
                limits.update(
                    lower=shifted_decimal(j["range"][0], j["reference"]),
                    upper=shifted_decimal(j["range"][1], j["reference"]),
                )
            ET.SubElement(e, "limit", **limits)
            ET.SubElement(
                e,
                "dynamics",
                damping=str(j["damping"]),
                friction=str(j["frictionloss"]),
            )
    return root


def urdf(r, path):
    save(urdf_xml(r), path)
    report = {
        "format": "urdf",
        "authority": "robot.json",
        "purpose": "visualization and kinematic exchange; not deployment",
        "losses": [
            "root world pose and freejoint",
            "native source/evidence/requirements/manufacturing contracts",
            "actuator law and controller binding",
            "sensor semantics and collision masks",
        ],
        "limit_policy": "declared effort/velocity limits preserved; unknown values exported as zero, not drive-ready",
        "coordinate_mapping": "URDF q = native q - native reference; link origin shifted to native joint anchor",
    }
    write(Path(path).with_suffix(".projection.json"), report)
    return report
