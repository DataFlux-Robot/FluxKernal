"""Native robot authority, exchange semantics and kernel-checked negative cases."""

import json
import shutil
import subprocess
import pytest

mj = pytest.importorskip("mujoco")
from fluxkernel.robotics.native import from_mujoco, validate, plant, read, digest
from fluxkernel.robotics.bundle import finish, verify, revise
from fluxkernel.robotics.proof import source
from fluxkernel.robotics.projection import urdf_xml
from fluxkernel.robotics.sources import safe
from fluxkernel.robotics.validation import check_projection

XML = """<mujoco><compiler angle="radian"/>
<worldbody><body name="base" pos="0.2 0.1 0.4" quat="0.9238795325 0 0 0.3826834324"><freejoint name="root"/>
<inertial pos="0 0 0" mass="1" diaginertia="0.1 0.1 0.1"/><geom name="base_vis" type="box" size=".1 .1 .1" contype="0" conaffinity="0"/>
<body name="arm" pos=".1 .2 0"><inertial pos=".04 0 0" mass=".1" diaginertia=".01 .01 .01"/>
<joint name="hinge" pos=".02 .01 0" axis="0 0 1" range="-1 1" ref=".2"/>
<geom name="arm_vis" type="box" size=".1 .02 .02" contype="0" conaffinity="0"/>
</body></body></worldbody><actuator><position name="motor" joint="hinge" kp="1" forcerange="-1 1"/></actuator></mujoco>"""


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("native")
    src = root / "upstream"
    src.mkdir()
    (src / "robot.xml").write_text(XML)
    r = from_mujoco(
        mj.MjModel.from_xml_string(XML),
        {"name": "fixture", "directory": ".", "entry": "robot.xml"},
        root / "meshes",
    )
    finish(r, root)
    return root


def test_real_kernel_and_projection(bundle):
    assert verify(bundle, rerun_proof=bool(shutil.which("lake")))["accepted"]
    assert check_projection(bundle)["accepted"]
    k = json.loads((bundle / "kernel.json").read_text())
    assert not k["promoted"]
    assert read(bundle)["controller"]["deployment_ready"] is False


@pytest.mark.parametrize(
    "case", ["cycle", "mass", "limits", "action-order", "plant", "inertia", "nan"]
)
def test_native_rejects_invalid_models(bundle, case):
    r = read(bundle)
    if case == "cycle":
        r["bodies"][1]["parent"] = 2
    elif case == "mass":
        r["bodies"][0]["mass"] = -1
    elif case == "limits":
        r["joints"][1]["range"] = [1, -1]
    elif case == "action-order":
        r["controller"]["action_joints"] = ["missing"]
    elif case == "plant":
        r["controller"]["plant_sha256"] = "0" * 64
    elif case == "inertia":
        r["bodies"][0]["principal_inertia"] = [1, 1, 10]
    elif case == "nan":
        r["bodies"][0]["mass"] = float("nan")
    with pytest.raises(ValueError):
        validate(r)


@pytest.mark.parametrize(
    "case",
    ["cycle", "mass", "limits", "duplicate-action", "missing-action", "wrong-plant"],
)
def test_lean_itself_rejects_invalid_instance(bundle, tmp_path, case):
    if not shutil.which("lake"):
        pytest.skip("Lean not installed")
    r = read(bundle)
    if case == "cycle":
        r["bodies"][1]["parent"] = 2
    elif case == "mass":
        r["bodies"][0]["mass"] = -1
    elif case == "limits":
        r["joints"][1]["range"] = [1, -1]
    elif case == "duplicate-action":
        r["controller"]["action_joints"] = ["hinge", "hinge"]
    elif case == "missing-action":
        r["controller"]["action_joints"] = []
    r["controller"]["plant_sha256"] = "wrong" if case == "wrong-plant" else plant(r)
    proofdir = bundle / "proof"
    file = proofdir / ("Negative-" + case + ".lean")
    file.write_text(source(r))
    try:
        p = subprocess.run(
            ["lake", "env", "lean", file.name],
            cwd=proofdir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert p.returncode != 0 and "error:" in p.stdout
    finally:
        file.unlink()


def test_native_edit_rebuilds_proof_and_invalidates_old_evidence(bundle, tmp_path):
    before = read(bundle)
    patch = {
        "base_native_sha256": digest(before),
        "edits": [{"kind": "body", "name": "arm", "set": {"mass": 0.12}}],
    }
    result = revise(bundle, patch, tmp_path)
    after = read(result["directory"])
    assert digest(read(bundle)) == digest(before)
    assert after["bodies"][1]["mass"] == 0.12
    assert after["controller"]["plant_sha256"] != before["controller"]["plant_sha256"]
    assert after["controller"]["status"] == "requires-revalidation"
    assert result["proof_accepted"] if shutil.which("lake") else True
    assert check_projection(result["directory"])["accepted"]
    patch["base_native_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="pin"):
        revise(bundle, patch, tmp_path)


def test_tampered_bundle_rejected(bundle, tmp_path):
    root = tmp_path / "tampered"
    shutil.copytree(bundle, root)
    (root / "robot.json").write_text("{}")
    with pytest.raises(ValueError, match="Artifact changed"):
        verify(root)


@pytest.mark.parametrize(
    "path", ["../outside", "/absolute", "x/../../outside", "x\\..\\outside"]
)
def test_source_paths_cannot_escape(tmp_path, path):
    with pytest.raises(ValueError):
        safe(tmp_path, path)


def test_unsupported_urdf_topology_cannot_silently_drop_joints(bundle):
    r = read(bundle)
    r["joints"][1]["kind"] = "ball"
    r["joints"][1]["reference"] = None
    r["controller"]["plant_sha256"] = plant(r)
    with pytest.raises(ValueError, match="one hinge"):
        urdf_xml(r)


def test_native_projection_needs_no_upstream_xml(bundle, tmp_path):
    from fluxkernel.robotics.projection import mjcf, urdf

    r = read(bundle)
    shutil.copytree(bundle / "meshes", tmp_path / "meshes")
    mjcf(r, tmp_path / "robot.xml")
    urdf(r, tmp_path / "robot.urdf")
    assert not (tmp_path / "upstream").exists()
    assert mj.MjModel.from_xml_path(str(tmp_path / "robot.xml")).nbody == 3
    assert mj.MjModel.from_xml_path(str(tmp_path / "robot.urdf")).njnt == 1


@pytest.mark.parametrize(
    "case", ["deploy", "sensor", "actuator", "geometry-quaternion", "timestep"]
)
def test_native_rejects_unverified_or_invalid_contracts(bundle, case):
    r = read(bundle)
    if case == "deploy":
        r["controller"]["deployment_ready"] = True
    elif case == "sensor":
        r["sensors"] = [
            {"name": "bad", "kind": "gyro", "object_type": "site", "object": "missing"}
        ]
    elif case == "actuator":
        r["actuators"][0]["gain"][0] = float("nan")
    elif case == "geometry-quaternion":
        r["geometries"][0]["quaternion"] = [0, 0, 0, 0]
    elif case == "timestep":
        r["simulation"]["timestep"] = -1
    with pytest.raises(ValueError):
        validate(r)


def test_urdf_mesh_paths_load_in_fresh_process(tmp_path):
    import sys
    from fluxkernel.robotics.projection import urdf

    xml = XML.replace(
        "<worldbody>",
        '<asset><mesh name="tetra" vertex="0 0 0 .1 0 0 0 .1 0 0 0 .1"/></asset><worldbody>',
    )
    xml = xml.replace(
        'name="base_vis" type="box" size=".1 .1 .1"',
        'name="base_vis" type="mesh" mesh="tetra"',
    )
    r = from_mujoco(
        mj.MjModel.from_xml_string(xml), {"name": "mesh-fixture"}, tmp_path / "meshes"
    )
    urdf(r, tmp_path / "robot.urdf")
    p = subprocess.run(
        [
            sys.executable,
            "-c",
            "import mujoco,sys; m=mujoco.MjModel.from_xml_path(sys.argv[1]); assert m.nmesh==1",
            str(tmp_path / "robot.urdf"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert p.returncode == 0, p.stderr


def test_generated_bytecode_is_not_a_sealed_design_artifact(bundle, tmp_path):
    from fluxkernel.robotics.bundle import seal

    root = tmp_path / "copy"
    shutil.copytree(bundle, root)
    cache = root / "__pycache__"
    cache.mkdir(exist_ok=True)
    bytecode = cache / "gen_urdf.pyc"
    bytecode.write_bytes(b"old cache")
    seal(root)
    bytecode.write_bytes(b"rebuilt interpreter cache")
    assert verify(root)["accepted"]
    assert not any(
        "__pycache__" in p for p in json.loads((root / "manifest.json").read_text())
    )
