"""Published library integrity and rejection of changed local inputs."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def library(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("robot_library")


def test_published_library_is_complete_and_license_dispositions_are_explicit(library):
    data, entries = library.registry(library.DEFAULT_LIBRARY)
    assert len(entries) == 295
    assert data["bundled"] == 220 and data["indexed_only"] == 75
    for entry in entries.values():
        if entry["distribution"] == "bundled":
            library.checked_source(library.DEFAULT_LIBRARY, entry)
            assert {"Robot.lean", "source.urdf", "LICENSE.txt", "NOTICE.md"} <= set(
                entry["files"]
            )
        else:
            assert entry["distribution_note"]
            assert not entry["files"]
            assert not (library.DEFAULT_LIBRARY / "models" / entry["id"]).exists()


def test_library_rejects_wrong_pinned_source_and_does_not_create_output(
    library, tmp_path
):
    _, entries = library.registry(library.DEFAULT_LIBRARY)
    entry = next(iter(entries.values()))
    raw = tmp_path / "wrong.urdf"
    raw.write_bytes(b'<robot name="not_the_pinned_source"/>')
    with pytest.raises(ValueError, match="pinned library case"):
        library.materialize(entry, raw, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_local_materialization_matches_tested_lean(library, tmp_path):
    _, entries = library.registry(library.DEFAULT_LIBRARY)
    entry = next(e for e in entries.values() if e["distribution"] == "bundled")
    original = library.DEFAULT_LIBRARY / entry["directory"]
    library.materialize(entry, original / "source.urdf", tmp_path / "local")
    assert (tmp_path / "local/Robot.lean").read_bytes() == (
        original / "Robot.lean"
    ).read_bytes()
    assert json.loads((tmp_path / "local/ORIGIN.json").read_text())["id"] == entry["id"]
