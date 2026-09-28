"""Import/export semantics, actual Lean translation checks and hostile inputs."""

import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import pytest

pytest.importorskip("mujoco")
import numpy as np
from fluxkernel.robotics.urdf_import import import_urdf, mesh_obj, mesh_path
from fluxkernel.robotics.native import read, digest, plant
from fluxkernel.robotics.bundle import verify, revise, seal, finish
from fluxkernel.robotics.validation import check_projection, forward
from fluxkernel.robotics.projection import quatmat, urdf_xml
from fluxkernel.robotics.exchange_proof import source as exchange_source

FIXTURE = Path(__file__).parent / "fixtures/urdf/mechanism.urdf"


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    return Path(import_urdf(FIXTURE, tmp_path_factory.mktemp("urdf"))["directory"])


def test_roundtrip_real_lean_and_independent_consumers(imported, tmp_path):
    checked = verify(imported, rerun_proof=bool(shutil.which("lake")))
    if shutil.which("lake"):
        assert (
            checked["exchange"]["accepted"] and checked["exchange"]["proof_reexecuted"]
        )
    assert check_projection(imported)["accepted"]
    r = read(imported)
    assert len(r["bodies"]) == 5 and len(r["joints"]) == 3 and not r["actuators"]
    xml = ET.parse(imported / "robot.urdf").getroot()
    assert xml.find("joint[@name='mount_to_base']").get("type") == "fixed"
    assert xml.find("joint[@name='spin']").get("type") == "continuous"
    shoulder = xml.find("joint[@name='shoulder']/limit")
    assert (
        float(shoulder.get("effort")) == 12.5 and float(shoulder.get("velocity")) == 2.4
    )
    body = next(b for b in r["bodies"] if b["name"] == "base")
    R = quatmat(body["inertial_quaternion"])
    actual = R @ np.diag(body["principal_inertia"]) @ R.T
    # Source inertial tensor, independently transformed using elementary rotations.
    x, y, z = 0.2, -0.3, 0.4
    rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    rot = rz @ ry @ rx
    np.testing.assert_allclose(
        actual,
        rot
        @ np.array([[0.03, 0.002, -0.001], [0.002, 0.04, 0.003], [-0.001, 0.003, 0.05]])
        @ rot.T,
        atol=1e-14,
    )
    second = Path(import_urdf(imported / "robot.urdf", tmp_path)["directory"])
    assert check_projection(second)["accepted"]
    rr = read(second)
    for a, b in zip(r["bodies"], rr["bodies"]):
        assert a["name"] == b["name"] and a["parent"] == b["parent"]
    for fraction in [0.0, 0.17, 0.5, 0.83, 1.0]:
        pos = {
            j["name"]: j["range"][0] + fraction * (j["range"][1] - j["range"][0])
            if j["limited"]
            else fraction * 3
            for j in r["joints"]
        }
        for key, t in forward(r, pos).items():
            np.testing.assert_allclose(t, forward(rr, pos)[key], atol=1e-12)


def test_revision_and_standalone_native_export(imported, tmp_path):
    before = read(imported)
    result = revise(
        imported,
        {
            "base_native_sha256": digest(before),
            "edits": [
                {"kind": "joint", "name": "shoulder", "set": {"range": [-0.5, 1.0]}}
            ],
        },
        tmp_path,
    )
    child = Path(result["directory"])
    assert digest(read(imported)) == digest(before)
    assert (
        verify(child)["exchange"]["available"] and check_projection(child)["accepted"]
    )
    assert (
        next(j for j in read(child)["joints"] if j["name"] == "shoulder")[
            "effort_limit"
        ]
        == 12.5
    )
    # Delete upstream only in a scratch copy of the generator inputs: authority is native.
    scratch = tmp_path / "standalone"
    scratch.mkdir()
    shutil.copytree(child / "meshes", scratch / "meshes")
    (scratch / "robot.json").write_bytes((child / "robot.json").read_bytes())
    assert ET.tostring(urdf_xml(read(scratch))) == ET.tostring(urdf_xml(read(child)))


@pytest.mark.parametrize(
    "change",
    ["axis", "type", "parent", "lower", "effort", "velocity", "mass", "missing-link"],
)
def test_actual_lean_rejects_changed_export(imported, change):
    if not shutil.which("lake"):
        pytest.skip("Lean unavailable")
    xml = ET.parse(imported / "robot.urdf").getroot()
    j = xml.find("joint[@name='shoulder']")
    if change == "axis":
        j.find("axis").set("xyz", "0 -1 0")
    elif change == "type":
        j.set("type", "prismatic")
    elif change == "parent":
        j.find("parent").set("link", "mount")
    elif change in ("lower", "effort", "velocity"):
        j.find("limit").set(change, "0.123")
    elif change == "mass":
        xml.find("link[@name='base']/inertial/mass").set("value", "9")
    else:
        xml.remove(xml.find("link[@name='mount']"))
    file = imported / "proof/NegativeExchange.lean"
    file.write_text(exchange_source(read(imported), ET.tostring(xml)))
    try:
        p = subprocess.run(
            ["lake", "env", "lean", file.name],
            cwd=file.parent,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert p.returncode != 0 and "error:" in p.stdout
    finally:
        file.unlink()


def test_resealed_tamper_cannot_bypass_native_binding(imported, tmp_path):
    target = tmp_path / "tampered"
    shutil.copytree(imported, target)
    xml = ET.parse(target / "robot.urdf")
    xml.getroot().find("joint[@name='shoulder']/origin").set("xyz", "10 0 0")
    xml.write(target / "robot.urdf")
    # Even if a local manifest and digest are recomputed, pose drift is rejected.
    import hashlib

    p = target / "exchange-proof.json"
    report = json.loads(p.read_text())
    report["urdf_sha256"] = hashlib.sha256(
        (target / "robot.urdf").read_bytes()
    ).hexdigest()
    p.write_text(json.dumps(report))
    seal(target)
    with pytest.raises(ValueError, match="current native projection"):
        verify(target)


def test_exact_reference_shift_is_proved(imported, tmp_path):
    r = read(imported)
    j = next(j for j in r["joints"] if j["name"] == "shoulder")
    j["reference"] = 0.2
    j["range"] = [0.1, 0.3]
    r["controller"]["plant_sha256"] = plant(r)
    root = tmp_path / "shift"
    root.mkdir()
    shutil.copytree(imported / "meshes", root / "meshes")
    result = finish(r, root)
    assert result["exchange_proof_accepted"] if shutil.which("lake") else True
    xml = ET.parse(root / "robot.urdf")
    limit = xml.find("joint[@name='shoulder']/limit")
    assert limit.get("lower") == "-0.1" and limit.get("upper") == "0.1"


@pytest.mark.parametrize(
    "change",
    [
        "mimic",
        "transmission",
        "gazebo",
        "cycle",
        "duplicate",
        "missing-inertia",
        "axis",
        "limits",
        "effort",
        "tensor",
        "nan",
        "doctype",
        "floating",
        "unknown-attribute",
        "continuous-bounds",
    ],
)
def test_import_fails_closed_and_leaves_no_partial_bundle(tmp_path, change):
    tree = ET.parse(FIXTURE).getroot()
    joint = tree.find("joint[@name='shoulder']")
    if change == "mimic":
        ET.SubElement(joint, "mimic", joint="spin")
    elif change in ("transmission", "gazebo"):
        ET.SubElement(tree, change)
    elif change == "cycle":
        joint.find("parent").set("link", "carriage")
    elif change == "duplicate":
        tree.append(copy.deepcopy(tree.find("link")))
    elif change == "missing-inertia":
        link = tree.find("link[@name='arm']")
        link.remove(link.find("inertial"))
    elif change == "axis":
        joint.find("axis").set("xyz", "0 2 0")
    elif change == "limits":
        joint.find("limit").set("lower", "3")
    elif change == "effort":
        joint.find("limit").set("effort", "-1")
    elif change == "tensor":
        tree.find("link[@name='arm']/inertial/inertia").set("ixx", "-1")
    elif change == "nan":
        joint.find("origin").set("xyz", "NaN 0 0")
    elif change == "floating":
        joint.set("type", "floating")
    elif change == "unknown-attribute":
        joint.set("mystery", "12")
    elif change == "continuous-bounds":
        tree.find("joint[@name='spin']/limit").set("lower", "-1")
    raw = ET.tostring(tree)
    if change == "doctype":
        raw = b'<!DOCTYPE robot [<!ENTITY a "b">]>' + raw
    path = tmp_path / "input.urdf"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        import_urdf(path, tmp_path / "out")
    assert not list((tmp_path / "out").iterdir())


def test_mesh_package_scale_and_missing_package(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    # Tetrahedron, authored fixture geometry only.
    obj = b"v 0 0 0\nv 100 0 0\nv 0 100 0\nv 0 0 100\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n"
    (package / "shape.obj").write_bytes(obj)
    tree = ET.parse(FIXTURE).getroot()
    g = tree.find("link[@name='arm']/visual/geometry")
    g.clear()
    ET.SubElement(
        g, "mesh", filename="package://fixture/shape.obj", scale=".001 .002 .003"
    )
    source = tmp_path / "robot.urdf"
    treefile = ET.ElementTree(tree)
    treefile.write(source)
    with pytest.raises(ValueError, match="package"):
        import_urdf(source, tmp_path / "bad")
    root = Path(
        import_urdf(source, tmp_path / "good", {"fixture": package})["directory"]
    )
    assert check_projection(root)["accepted"]
    r = read(root)
    raw = (root / r["meshes"][0]["file"]).read_text()
    points = np.array(
        [
            [float(x) for x in l.split()[1:]]
            for l in raw.splitlines()
            if l.startswith("v ")
        ]
    )
    np.testing.assert_allclose(points.max(axis=0), [0.1, 0.2, 0.3])
    assert (root / "upstream/input.urdf").read_bytes() == source.read_bytes()


def test_stl_triangle_geometry_and_mesh_path_boundary(tmp_path):
    raw = (
        b"\0" * 80
        + struct.pack("<I", 1)
        + struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)
    )
    cooked, nv, nf = mesh_obj(raw, ".stl", [0.001, 0.002, 0.003])
    assert nv == 3 and nf == 1 and b"v 0.001 0 0" in cooked
    ascii_stl = b"solid x\n facet normal 0 0 1\n outer loop\n vertex 0 0 0\n vertex 1 0 0\n vertex 0 1 0\n endloop\n endfacet\nendsolid x\n"
    assert mesh_obj(ascii_stl, ".stl", [0.001, 0.002, 0.003])[0] == cooked
    outside = tmp_path / "outside.obj"
    outside.write_bytes(cooked)
    base = tmp_path / "inside"
    base.mkdir()
    for uri in [
        "../outside.obj",
        "https://example.com/m.obj",
        str(outside),
        "package://pkg/../outside.obj",
    ]:
        with pytest.raises(ValueError):
            mesh_path(uri, base, {"pkg": base})


def test_encoded_dtd_and_path_robot_name_rejected(tmp_path):
    from fluxkernel.robotics.urdf_import import xml_root

    with pytest.raises(ValueError):
        xml_root('<!DOCTYPE robot [<!ENTITY a "b">]><robot name="x"/>'.encode("utf-16"))
    for robot_name in ("../escape", "/absolute", "a\\b", ".."):
        xml = ET.parse(FIXTURE)
        xml.getroot().set("name", robot_name)
        path = tmp_path / "bad.urdf"
        xml.write(path)
        with pytest.raises(ValueError, match="filesystem path"):
            import_urdf(path, tmp_path / "out")
        assert not list((tmp_path / "out").iterdir())


def test_shared_mesh_is_one_native_asset(tmp_path):
    tree = ET.parse(FIXTURE)
    link = tree.getroot().find("link[@name='arm']")
    g = link.find("visual/geometry")
    g.clear()
    ET.SubElement(g, "mesh", filename="tetra.obj")
    collision = ET.SubElement(link, "collision")
    collision.append(copy.deepcopy(g))
    (tmp_path / "tetra.obj").write_text(
        "v 0 0 0\nv .1 0 0\nv 0 .1 0\nv 0 0 .1\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n"
    )
    path = tmp_path / "shared.urdf"
    tree.write(path)
    root = Path(import_urdf(path, tmp_path / "out")["directory"])
    r = read(root)
    assert len(r["meshes"]) == 1
    occurrences = [g for g in r["geometries"] if g["kind"] == "mesh"]
    assert len(occurrences) == 2 and occurrences[0]["mesh"] == occurrences[1]["mesh"]
    assert {g["contype"] for g in occurrences} == {0, 1}
    assert check_projection(root)["accepted"]


def test_reserved_consumer_world_name_is_explicit_failure(tmp_path):
    tree = ET.parse(FIXTURE)
    tree.getroot().find("link[@name='mount']").set("name", "world")
    tree.getroot().find("joint[@name='mount_to_base']/parent").set("link", "world")
    file = tmp_path / "world.urdf"
    tree.write(file)
    with pytest.raises(ValueError, match="reserves link name"):
        import_urdf(file, tmp_path / "out")
