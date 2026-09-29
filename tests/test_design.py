"""Design intent, independent Lean rejection, and certificate invalidation."""

import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from fluxkernel.design.examples import fourbar
from fluxkernel.design.model import Design, const, op, rational
from fluxkernel.design import proof
from fluxkernel.robotics.lean_runtime import lean_binary


@pytest.fixture
def lean():
    try:
        return lean_binary()
    except ValueError:
        pytest.skip("Preinstalled pinned Lean required")


@pytest.mark.parametrize("phase", ["1/10", "1/4", "1/2", "1", "2"])
def test_closed_chain_motion_and_independent_distances(phase):
    r = Design(fourbar()).check({"phase": phase})
    assert r["accepted"] and r["independent_cycles"] == 1
    points = {
        name: tuple(float(Fraction(v)) for v in values)
        for name, values in r["positions_si"].items()
    }
    # An independent floating-point geometry check, separate from the DSL evaluator.
    for a, b, length in (
        ("A", "B", 0.12),
        ("B", "C", 0.06),
        ("C", "D", 0.12),
        ("D", "A", 0.06),
    ):
        assert math.dist(points[a], points[b]) == pytest.approx(length, abs=1e-12)
    assert all(
        c["residual_si"] == "0" for c in r["checks"] if c["id"].startswith("closure:")
    )


@pytest.mark.parametrize(
    "inputs,failed",
    [
        ({"thickness": "2"}, "requirement:minimum_thickness"),
        ({"pin": "8"}, "mate:mount:diameter"),
        ({"load": "100"}, "requirement:nominal_axial_stress"),
    ],
)
def test_declared_intent_rejects_geometrically_representable_designs(inputs, failed):
    r = Design(fourbar()).check(inputs)
    assert not r["accepted"]
    assert any(c["id"] == failed and not c["passed"] for c in r["checks"])


def test_broken_closed_chain_is_rejected():
    d = fourbar()
    d["members"][1]["length"] = const(65, "mm")
    r = Design(d).check()
    assert not r["accepted"]
    assert any(c["id"] == "closure:input" and not c["passed"] for c in r["checks"])


def test_equivalent_units_and_dimensional_errors():
    d = fourbar()
    d["ports"][1]["diameter"] = const("0.006", "m")
    assert Design(d).check()["accepted"]
    d["ports"][1]["diameter"] = const(6, "kg")
    with pytest.raises(ValueError, match="Dimension mismatch"):
        Design(d)
    d = fourbar()
    d["requirements"][0]["lhs"] = op("add", const(1, "m"), const(1, "s"))
    with pytest.raises(ValueError, match="Dimension mismatch"):
        Design(d)


@pytest.mark.parametrize(
    "value", [1.5, True, "1/0", "NaN", "1e10000000", "__import__('os')"]
)
def test_exact_number_input_is_bounded_and_not_code(value):
    with pytest.raises(ValueError):
        rational(value)


def test_schema_unknown_fields_dangling_references_and_csg_cycles_rejected():
    d = fourbar()
    d["unchecked_constraints"] = []
    with pytest.raises(ValueError, match="Expected fields"):
        Design(d)
    d = fourbar()
    d["members"][0]["b"] = "missing"
    with pytest.raises(ValueError, match="endpoints"):
        Design(d)
    d = fourbar()
    next(s for s in d["shapes"] if s["id"] == "plate")["a"] = "plate"
    with pytest.raises(ValueError, match="dependencies"):
        Design(d)


def test_csg_membership_boundaries_translation_and_invalid_arithmetic():
    d = fourbar()
    d["shapes"].append(
        {
            "id": "shifted",
            "kind": "translate",
            "child": "plate",
            "offset": [const(100, "mm"), const(0, "m"), const(0, "m")],
        }
    )
    m = Design(d)
    env = m.environment()

    def at(x):
        return [const(x, "mm"), const(0, "m"), const(1, "mm")]

    assert not m.predicate(m.membership("plate", at(0)), env)
    assert not m.predicate(m.membership("plate", at(3)), env)  # bore boundary removed
    assert m.predicate(m.membership("plate", at(15)), env)  # blank boundary retained
    assert not m.predicate(m.membership("plate", at(16)), env)
    assert m.predicate(m.membership("shifted", at(110)), env)
    assert not m.predicate(m.membership("shifted", at(100)), env)
    p = {
        "not": {"lhs": op("div", const(1), const(0)), "rhs": const(0), "relation": "eq"}
    }
    with pytest.raises(ValueError, match="Division by zero"):
        m.predicate(p, env)


def test_ranges_and_unknown_overrides_are_not_ignored():
    m = Design(fourbar())
    with pytest.raises(ValueError, match="outside declared range"):
        m.check({"phase": "100"})
    with pytest.raises(ValueError, match="Unknown parameter"):
        m.check({"typo": "5"})


def test_implicit_quartic_shape_matches_independent_torus_cross_section():
    m = Design(fourbar())
    env = m.environment()
    for x, y, z in ((0, 0, 0), (10, 0, 0), (10, 0, 4), (14, 0, 0), (0, 10, 2)):
        point = [const(v, "mm") for v in (x, y, z)]
        expected = (math.hypot(x, y) - 10) ** 2 + z * z <= 3**2
        assert m.predicate(m.membership("implicit_torus", point), env) == expected
    d = fourbar()
    d["points"][0]["position"][0] = {"coord": 0}
    with pytest.raises(ValueError, match="scoped"):
        Design(d)


def test_lean_certificate_and_stale_model_or_parameter_rejection(lean, tmp_path):
    d = fourbar()
    r = proof.certify(d, tmp_path / "certificate", {"phase": "1/2"})
    assert r["proof"]["accepted"] and "sorryAx" not in r["proof"]["log"]
    assert "Lean.ofReduceBool" not in r["proof"]["log"]
    assert proof.verify(tmp_path / "certificate", d, {"phase": "2/4"})["accepted"]
    changed = copy.deepcopy(d)
    changed["parameters"][1]["default"] = "130"
    with pytest.raises(ValueError, match="design changed"):
        proof.verify(tmp_path / "certificate", changed)
    with pytest.raises(ValueError, match="inputs changed"):
        proof.verify(tmp_path / "certificate", d, {"phase": "3/4"})
    path = tmp_path / "certificate/Instance.lean"
    path.write_text(path.read_text() + '\n#eval IO.println "untrusted"\n')
    with pytest.raises(ValueError, match="arbitrary Lean"):
        proof.verify(tmp_path / "certificate")


@pytest.mark.parametrize("change", ["closure", "probe", "thin"])
def test_lean_independently_rejects_false_obligations_even_if_python_gate_bypassed(
    lean, change
):
    d = fourbar()
    inputs = {}
    if change == "closure":
        d["members"][1]["length"] = const(65, "mm")
    elif change == "probe":
        d["probes"][0]["inside"] = True
    else:
        inputs = {"thickness": "2"}
    # Go straight to Lean generation: Python check() and certify() are bypassed.
    with pytest.raises(ValueError, match="Lean rejected"):
        proof.execute(proof.source(Design(d), inputs))


def test_cli_duplicate_json_fields_rejected(tmp_path):
    from fluxkernel.design.cli import read

    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"a", "schema":"b"}')
    with pytest.raises(ValueError, match="Duplicate JSON"):
        read(path)


def test_example_cli_requires_no_workspace_or_model_account(tmp_path):
    env = __import__("os").environ.copy()
    repo = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(repo)
    command = [sys.executable, "-m", "fluxkernel.interface.cli", "design"]
    created = subprocess.run(
        command + ["example", "--output", "design.json"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    checked = subprocess.run(
        command + ["check", "design.json", "--param", "pin=8"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 1
    assert json.loads(checked.stdout)["accepted"] is False
