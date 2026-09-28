"""Complete Lean document round trips, independent reconstruction and stale bindings."""

import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import pytest

from fluxkernel.robotics.lean_document import (
    Reader,
    from_lean,
    load,
    source,
    to_lean,
    tree,
)

FIXTURE = Path(__file__).parent / "fixtures/urdf/mechanism.urdf"
pytestmark = pytest.mark.skipif(not shutil.which("lake"), reason="Lean required")


@pytest.fixture
def package(tmp_path):
    directory = tmp_path / "lean"
    to_lean(FIXTURE, directory)
    return directory


def test_both_directions_byte_exact_and_real_lean(package, tmp_path):
    restored = tmp_path / "restored"
    result = from_lean(package, restored)
    assert result["lean_executed"] and result["lexical_bytes_restored"]
    assert (restored / "robot.urdf").read_bytes() == FIXTURE.read_bytes()
    to_lean(restored / "robot.urdf", tmp_path / "again")
    assert (package / "Robot.lean").read_bytes() == (
        tmp_path / "again/Robot.lean"
    ).read_bytes()


def test_no_original_urdf_needed_and_lean_values_control_export(package, tmp_path):
    n, assets, native, fingerprint = load(package)
    (package / "source.urdf").unlink()

    # Edit the actual Lean document's inertial mass; no URDF input survives here.
    def edit(node):
        if isinstance(node, str):
            return
        if node[0] == "mass":
            node[1] = [["value", "1.2345678901234567890123456789"]]
        for child in node[2]:
            edit(child)

    edit(n)
    (package / "Robot.lean").write_text(source(n, assets, native, fingerprint))
    result = from_lean(package, tmp_path / "out")
    assert not result["lexical_bytes_restored"]
    raw = (tmp_path / "out/robot.urdf").read_bytes()
    assert tree(raw) == n
    assert b"1.2345678901234567890123456789" in raw


def test_exact_mesh_asset_bytes_and_tamper(tmp_path):
    pytest.importorskip("numpy")
    root = ET.parse(FIXTURE).getroot()
    mesh = tmp_path / "tri.obj"
    mesh.write_bytes(b"# exact asset comment\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    g = root.find("link/visual/geometry")
    g.clear()
    ET.SubElement(g, "mesh", filename="tri.obj", scale="0.0010 0.0020 0.0030")
    urdf = tmp_path / "input.urdf"
    ET.ElementTree(root).write(urdf)
    to_lean(urdf, tmp_path / "lean")
    from_lean(tmp_path / "lean", tmp_path / "out")
    assert (tmp_path / "out/tri.obj").read_bytes() == mesh.read_bytes()
    (tmp_path / "lean/assets/tri.obj").write_text("changed")
    with pytest.raises(ValueError, match="Changed Lean document resource"):
        from_lean(tmp_path / "lean", tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("mutation", ["value", "comment", "executable", "path"])
def test_tampered_packages_fail_closed(package, tmp_path, mutation):
    if mutation == "comment":
        p = package / "source.urdf"
        p.write_bytes(p.read_bytes() + b"<!-- altered -->")
    elif mutation == "value":
        p = package / "Robot.lean"
        p.write_text(p.read_text().replace('("name", "', '("name", "changed-', 1))
    elif mutation == "executable":
        p = package / "Robot.lean"
        p.write_text(p.read_text() + '\n#eval IO.println "untrusted execution"\n')
    else:
        n, _, native, fingerprint = load(package)
        (package / "Robot.lean").write_text(
            source(n, [["../escape", "0" * 64]], native, fingerprint)
        )
    with pytest.raises(ValueError):
        from_lean(package, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_escaped_attribute_text_and_decimal_lexemes(tmp_path):
    raw = b'<robot name="a&amp;b&quot;c&#9;&#10;&#13;"><link name="base"/><extra value="-0.00000000000000000001">a&amp;b&lt;c</extra></robot>'
    p = tmp_path / "source.urdf"
    p.write_bytes(raw)
    to_lean(p, tmp_path / "lean")
    (tmp_path / "lean/source.urdf").unlink()
    from_lean(tmp_path / "lean", tmp_path / "out")
    assert tree((tmp_path / "out/robot.urdf").read_bytes()) == tree(raw)


def test_native_controller_and_every_sealed_file_restored(tmp_path):
    pytest.importorskip("mujoco")
    from fluxkernel.robotics.urdf_import import import_urdf
    from fluxkernel.robotics.bundle import verify

    native = Path(import_urdf(FIXTURE, tmp_path / "input")["directory"])
    to_lean(native, tmp_path / "lean")
    # Native snapshot can supply exact lexical bytes, without source.urdf.
    (tmp_path / "lean/source.urdf").unlink()
    result = from_lean(tmp_path / "lean", tmp_path / "restored")
    assert result["native_bundle_restored"]
    files = json.loads((native / "manifest.json").read_text())
    for name in [*files, "manifest.json"]:
        assert (native / name).read_bytes() == (
            tmp_path / "restored" / name
        ).read_bytes()
    assert verify(tmp_path / "restored", True)["proof_accepted"]
    to_lean(tmp_path / "restored", tmp_path / "again")
    assert (tmp_path / "again/Robot.lean").read_bytes() == (
        tmp_path / "lean/Robot.lean"
    ).read_bytes()


def test_reserved_asset_and_depth_limits(tmp_path):
    raw = b'<robot name="r"><link name="a"/></robot>'
    n = tree(raw)
    text = source(n, [], [], hashlib.sha256(raw).hexdigest())
    assert Reader(text).read()[0] == n
    with pytest.raises(ValueError, match="depth"):
        tree(b"<robot>" + b"<a>" * 130 + b"</a>" * 130 + b"</robot>")
    pkg = tmp_path / "lean"
    (pkg / "assets").mkdir(parents=True)
    raw = b'<robot><mesh filename="gen_urdf.py"/></robot>'
    (pkg / "assets/gen_urdf.py").write_bytes(b"asset")
    (pkg / "Robot.lean").write_text(
        source(
            tree(raw),
            [["gen_urdf.py", hashlib.sha256(b"asset").hexdigest()]],
            [],
            hashlib.sha256(raw).hexdigest(),
        )
    )
    with pytest.raises(ValueError, match="Reserved"):
        from_lean(pkg, tmp_path / "out")
    assert not (tmp_path / "out").exists()
