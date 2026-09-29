"""The catalog harness must detect stale output and retain invalid source cases."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def benchmark(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("benchmark_urdf_bidirectional")


def case_for(benchmark, path, raw):
    path.write_bytes(raw)
    return {
        "case_id": "fixture",
        "entry_ids": [0],
        "repository": "fixture",
        "commit": "fixture",
        "path": path.name,
        "file": str(path),
        "sha256": benchmark.digest(raw),
    }


def test_harness_catches_stale_renderer_despite_unchanged_roundtrips(
    benchmark, monkeypatch, tmp_path
):
    raw = b'<robot name="r"><link name="base"><inertial><mass value="1"/></inertial></link></robot>'
    case = case_for(benchmark, tmp_path / "robot.urdf", raw)
    # A fake converter replaying the original URDF passes unchanged round trips
    # but must fail the independently checked Lean-edit path.
    monkeypatch.setattr(benchmark, "render_lean", lambda _: raw)
    result = {"checks": {}}
    benchmark.documents(raw, case, tmp_path, result)
    assert result["checks"]["document_urdf_lean_urdf"]["status"] == "passed"
    assert result["checks"]["document_lean_urdf_lean"]["status"] == "passed"
    assert result["checks"]["document_lean_edit"]["status"] == "failed"


def test_invalid_source_is_retained_with_blocked_reverse(benchmark, tmp_path):
    case = case_for(
        benchmark, tmp_path / "broken.urdf", b'<robot name="r"><ext:unknown/></robot>'
    )
    result = benchmark.check(case, {"complete": False}, {}, tmp_path / "results")
    assert set(result["checks"]) == set(benchmark.CHECKS)
    assert result["checks"]["document_urdf_lean_urdf"]["status"] == "failed"
    assert result["checks"]["document_lean_urdf_lean"]["status"] == "blocked"
    assert result["checks"]["package_urdf_lean_urdf"]["status"] == "failed"
    assert result["source_unchanged"]
    assert (tmp_path / "results/fixture/result.json").exists()


def test_real_lean_all_directions_xml_free_edits_and_asset_tamper(benchmark, tmp_path):
    try:
        benchmark.lean_runtime.lean_binary()
    except ValueError:
        pytest.skip("Pinned Lean required")
    raw = b"""<robot name="r" xmlns:ext="urn:test"><link name="base">
<inertial><mass value="1.0000"/></inertial><visual><geometry>
<mesh filename="mesh.obj"/></geometry></visual></link><ext:metadata value="1e-07"/></robot>"""
    (tmp_path / "mesh.obj").write_bytes(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    case = case_for(benchmark, tmp_path / "robot.urdf", raw)
    result = benchmark.check(
        case,
        {
            "complete": True,
            "references": [{"uri": "mesh.obj", "resource_key": "mesh"}],
        },
        {"mesh": {"dependencies": []}},
        tmp_path / "results",
    )
    assert all(c["status"] == "passed" for c in result["checks"].values()), result
    assert result["checks"]["document_lean_edit"]["long_decimal_mass_changed"]
    assert (tmp_path / "robot.urdf").read_bytes() == raw
