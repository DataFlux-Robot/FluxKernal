"""Manufacturing estimates, frozen mechanisms and model-owned prototype selection."""

import copy
import math
import shutil
from pathlib import Path
import pytest

pytest.importorskip("build123d")
mj = pytest.importorskip("mujoco")
from fluxkernel.robotics.native import from_mujoco, read, digest
from fluxkernel.robotics.bundle import finish, verify, revise
from fluxkernel.robotics.attachment import zone, attach, guards
from fluxkernel.robotics.part_geometry import generate, checked, export
from fluxkernel.robotics.validation import check_projection

XML = """<mujoco><asset><mesh name="cap" vertex="-.02 -.02 -.02 .02 -.02 -.02 -.02 .02 -.02 .02 .02 -.02 -.02 -.02 .02 .02 -.02 .02 -.02 .02 .02 .02 .02 .02"/></asset>
<worldbody><body name="base"><freejoint/><inertial pos="0 0 0" mass="1" diaginertia=".01 .01 .01"/><geom type="box" size=".03 .03 .03"/>
<body name="head" pos="0 0 .15"><inertial pos="0 0 0" mass=".1" diaginertia=".001 .001 .001"/><joint name="neck" range="-20 20"/><geom name="cover" type="mesh" mesh="cap" contype="0" conaffinity="0" group="2"/></body></body></worldbody><actuator><position name="servo" joint="neck" kp="1"/></actuator></mujoco>"""


def recipe(z):
    return {
        "schema_version": "fk-robot-part-v1",
        "zone_sha256": z["zone_sha256"],
        "name": "fixture",
        "rationale": "Authored regression only",
        "symmetry": "bilateral",
        "material": "pla",
        "color_rgb": [0.2, 0.7, 0.9],
        "base_size_mm": [16.0, 16.0, 2.0],
        "features": [
            {
                "shape": "ellipsoid",
                "size_mm": [8.0, 8.0, 10.0],
                "center_mm": [0.0, 0.0, 6.0],
                "rotation_deg": [0.0, 0.0, 0.0],
            }
        ],
    }


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    root = tmp_path_factory.mktemp("accessory-base")
    (root / "upstream").mkdir()
    (root / "upstream/robot.xml").write_text(XML)
    r = from_mujoco(
        mj.MjModel.from_xml_string(XML),
        {"name": "fixture", "directory": ".", "entry": "robot.xml"},
        root / "meshes",
    )
    finish(r, root)
    return root


def test_attach_keeps_source_and_updates_native_and_store(baseline, tmp_path):
    before = read(baseline)
    z = zone(baseline, "cap")
    result = attach(baseline, recipe(z), tmp_path, "cap")
    root = Path(result["directory"])
    after = read(root)
    assert result["accepted"] and guards(before, after)["accepted"]
    assert digest(read(baseline)) == digest(before)
    assert (
        after["controller"]["status"] == "requires-revalidation"
        and not after["controller"]["deployment_ready"]
    )
    assert after["controller"]["plant_sha256"] != before["controller"]["plant_sha256"]
    assert verify(root, bool(shutil.which("lake")))["accepted"]
    assert check_projection(root)["accepted"]
    assert (
        len(after["custom_parts"]) == 1
        and (root / "cad/custom_fixture/part.step").exists()
    )
    assert after["custom_parts"][0]["zone"]["interface_status"] == "unverified"
    patch = {
        "base_native_sha256": digest(after),
        "edits": [{"kind": "body", "name": "custom_fixture", "set": {"mass": 0.01}}],
    }
    with pytest.raises(ValueError, match="CAD-backed"):
        revise(root, patch, tmp_path)
    artifact = root / next(iter(after["custom_parts"][0]["artifacts"]))
    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="artifact changed"):
        read(root)


def test_stale_zone_rejected_before_geometry(baseline, tmp_path):
    r = recipe(zone(baseline, "cap"))
    r["zone_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Stale"):
        attach(baseline, r, tmp_path, "cap")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case", ["nan", "protected", "below", "disconnected", "asymmetric-source"]
)
def test_recipe_failures(case):
    r = recipe({"zone_sha256": "0" * 64})
    if case == "nan":
        r["color_rgb"][0] = float("nan")
    elif case == "protected":
        r["joint_axis"] = [1, 0, 0]
    elif case == "below":
        r["features"][0]["center_mm"][2] = -10
    elif case == "disconnected":
        r["features"][0]["center_mm"][2] = 25
    elif case == "asymmetric-source":
        r["features"][0]["center_mm"][1] = -5
    if case in ("nan", "protected", "asymmetric-source"):
        with pytest.raises(ValueError):
            checked(r)
    elif case == "disconnected":
        with pytest.raises(ValueError, match="connected"):
            generate(r)
    else:
        # Below-plane CAD also disconnects this fixture; either rejection is correct.
        with pytest.raises(ValueError):
            generate(r)


def test_cad_mass_and_inertia_have_correct_si_units(tmp_path):
    r = recipe({"zone_sha256": "0" * 64})
    r["base_size_mm"] = [20.0, 20.0, 2.0]
    r["features"] = [
        {
            "shape": "box",
            "size_mm": [2.0, 2.0, 1.0],
            "center_mm": [0.0, 0.0, 1.0],
            "rotation_deg": [0.0, 0.0, 0.0],
        }
    ]
    p = export(r, tmp_path)
    mass = math.pi * 10**2 * 2 * 1240e-9
    assert p["mass_kg"] == pytest.approx(mass, rel=1e-7)
    assert p["principal_inertia"] == pytest.approx(
        [mass * (3 * 10**2 + 2**2) / 12 * 1e-6] * 2 + [mass * 10**2 / 2 * 1e-6],
        rel=1e-6,
    )


def test_frozen_checker_rejects_mechanism_changes(baseline):
    r = read(baseline)
    child = copy.deepcopy(r)
    child["bodies"].append(copy.deepcopy(r["bodies"][-1]))
    child["joints"][0]["axis"] = [1, 0, 0]
    assert not guards(r, child)["accepted"]


def test_glm_protocol_uses_reviewed_selection_and_labels_mock(
    baseline, tmp_path, monkeypatch
):
    from fluxkernel.robotics import personalize as pal
    from PIL import Image

    def fake_render(bundle, output, **kwargs):
        Image.new("RGB", (32, 32), "gray").save(output)

    monkeypatch.setattr(pal, "render", fake_render)

    def fake_step(path, output):
        fake_render(None, output)
        import json

        p = json.loads(Path(path).with_name("properties.json").read_text())
        return {"accepted": True, "volume_mm3": p["volume_mm3"], "mode": "mock"}

    monkeypatch.setattr(pal, "render_step", fake_step)
    z = zone(baseline, "cap")
    r = recipe(z)
    labels = []

    def provider(cfg, system, prompt, images, schema, directory, label, event, calls):
        labels.append(label)
        calls.append({"state": "mock", "kind": label})
        assert "GLM-5.3-Flash owns" in system
        if label == "plan-0":
            invalid = copy.deepcopy(r)
            invalid["features"][0]["center_mm"][1] = -5.0
            return invalid
        if label.startswith("plan"):
            assert '"proposed_recipe"' in prompt and '-5.0' in prompt
            assert "Y >= 0" in prompt
            return r
        if label.startswith("review"):
            return {
                "recipe_sha256": digest(r),
                "verdict": "needs-review",
                "findings": ["Mock judgement"],
                "next_step": "stop",
                "reason": "Mock test",
            }
        return {"selected_round": 0, "reason": "Model selection fixture"}

    out = pal.run(
        baseline,
        "Fixture",
        tmp_path,
        1,
        target="cap",
        require_proof=bool(shutil.which("lake")),
        provider=provider,
        config={"model": "glm-5.3-flash"},
    )
    assert (
        out["mode"] == "mock"
        and out["selected_round"] == 0
        and out["visual_status"] == "needs-review"
    )
    assert labels == ["plan-0", "plan-1", "review-0", "select-0"]
    assert not out["deployment_ready"]
    with pytest.raises(ValueError, match="requires glm"):
        pal.run(baseline, "Fixture", tmp_path, config={"model": "other"})


@pytest.mark.parametrize(
    "text",
    [
        '{"x":1} {"x":2}',
        '```json\n{"x":1}\n```\n```json\n{"x":2}\n```',
        '```json\n{"x":',
        "[1,2]",
    ],
)
def test_transport_decoder_rejects_ambiguous_or_truncated_data(text):
    from fluxkernel.robotics.personalize import decode_response

    with pytest.raises(ValueError):
        decode_response(text)


def test_transport_decoder_keeps_values_exact():
    from fluxkernel.robotics.personalize import decode_response

    assert decode_response(
        'Explanation\n```json\n{"size":[1.2,3,4],"note":"unchanged"}\n```'
    ) == {"size": [1.2, 3, 4], "note": "unchanged"}


def test_trimmed_curved_step_roundtrip_uses_adaptive_mass_properties(tmp_path, monkeypatch):
    from fluxkernel.robotics import render as rendering
    # Exercise independent primary STEP read without depending on an OpenGL driver.
    def check_camera(root, *args, **kwargs):
        model = mj.MjModel.from_xml_path(str(root / "robot.xml"))
        assert 0.01 < model.stat.extent < 0.05
    monkeypatch.setattr(rendering, "render", check_camera)
    r = recipe({"zone_sha256": "0" * 64})
    r["features"][0].update(size_mm=[9., 7., 12.], center_mm=[0., 0., 7.], rotation_deg=[0., 17., 0.])
    p = export(r, tmp_path)
    back = rendering.render_step(tmp_path / "part.step", tmp_path / "snapshot.png")
    assert back["accepted"] and back["solids"] == 1
    assert back["volume_mm3"] == pytest.approx(p["volume_mm3"], rel=1e-5)
