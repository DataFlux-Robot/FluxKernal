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


def test_namespace_prefixes_and_scoped_declarations_survive_lean(tmp_path):
    raw = b"""<robot name="r" xmlns:ext="urn:outer"><link name="base"/>
      <ext:property ext:value="0.0010" xml:lang="en">a&amp;b</ext:property>
      <group xmlns:ext="urn:inner"><ext:item/></group></robot>"""
    path = tmp_path / "input.urdf"
    path.write_bytes(raw)
    to_lean(path, tmp_path / "lean")
    (tmp_path / "lean/source.urdf").unlink()
    from_lean(tmp_path / "lean", tmp_path / "out")
    generated = (tmp_path / "out/robot.urdf").read_bytes()
    assert tree(raw) == tree(generated)
    xml = ET.fromstring(generated)
    assert xml.find("{urn:outer}property").get("{urn:outer}value") == "0.0010"
    assert xml.find("group/{urn:inner}item") is not None


def test_undeclared_namespace_still_rejected():
    with pytest.raises(ValueError, match="Invalid URDF XML"):
        tree(b'<robot name="r"><ext:property/></robot>')


def test_plugin_is_metadata_and_obj_texture_closure_is_preserved(tmp_path):
    root = ET.parse(FIXTURE).getroot()
    g = root.find("link/visual/geometry")
    g.clear()
    ET.SubElement(g, "mesh", filename="meshes/shape.obj")
    ET.SubElement(
        ET.SubElement(root, "gazebo"),
        "plugin",
        name="runtime",
        filename="libgazebo_ros_control.so",
    )
    mesh = tmp_path / "meshes"
    mesh.mkdir()
    (mesh / "shape.obj").write_text(
        "mtllib surface.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    )
    (mesh / "surface.mtl").write_text(
        'newmtl shell\nmap_Kd -s 1 1 1 "shell texture.png"\n'
    )
    (mesh / "shell texture.png").write_bytes(b"authored byte-preservation fixture")
    f = tmp_path / "input.urdf"
    ET.ElementTree(root).write(f)
    result = to_lean(f, tmp_path / "lean")
    assert result["asset_count"] == 3
    from_lean(tmp_path / "lean", tmp_path / "out")
    for p in mesh.iterdir():
        assert p.read_bytes() == (tmp_path / "out/meshes" / p.name).read_bytes()
    assert (tmp_path / "out/robot.urdf").read_bytes() == f.read_bytes()
    to_lean(tmp_path / "out/robot.urdf", tmp_path / "again")
    assert (tmp_path / "lean/Robot.lean").read_bytes() == (
        tmp_path / "again/Robot.lean"
    ).read_bytes()
    (tmp_path / "lean/assets/meshes/shell texture.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed Lean document resource"):
        from_lean(tmp_path / "lean", tmp_path / "bad")


@pytest.mark.parametrize("extension", ["dae", "gltf", "glb"])
def test_texture_and_buffer_discovery(extension, tmp_path):
    import struct
    from fluxkernel.robotics.urdf_assets import records

    # Authored dependency fragments; this checks packaging, not geometry loading.
    if extension == "dae":
        raw = b'<COLLADA xmlns="urn:collada"><library_images><image><init_from>texture.bin</init_from></image></library_images></COLLADA>'
    else:
        raw = json.dumps(
            {
                "asset": {"version": "2.0"},
                "buffers": [{"uri": "buffer.bin"}],
                "images": [
                    {"uri": "texture.bin"},
                    {"uri": "data:image/png;base64,AAAA"},
                ],
            }
        ).encode()
        if extension == "glb":
            raw += b" " * (-len(raw) % 4)
            raw = (
                b"glTF"
                + struct.pack("<4I", 2, 20 + len(raw), len(raw), 0x4E4F534A)
                + raw
            )
    (tmp_path / ("mesh." + extension)).write_bytes(raw)
    (tmp_path / "texture.bin").write_bytes(b"texture")
    (tmp_path / "buffer.bin").write_bytes(b"vertices")
    xml = f'<robot name="r"><link name="base"><visual><geometry><mesh filename="mesh.{extension}"/></geometry></visual></link></robot>'.encode()
    found = dict(records(xml, tmp_path))
    assert set(found) == {"mesh." + extension, "texture.bin"} | (
        {"buffer.bin"} if extension != "dae" else set()
    )


@pytest.mark.parametrize(
    "dependency", ["../../outside.png", "https://example.com/file.png"]
)
def test_secondary_assets_cannot_escape_root(tmp_path, dependency):
    from fluxkernel.robotics.urdf_assets import records

    (tmp_path / "material.mtl").write_text("map_Kd " + dependency + "\n")
    xml = b'<robot name="r"><mesh filename="material.mtl"/></robot>'
    with pytest.raises(ValueError):
        records(xml, tmp_path)


def test_xacro_is_not_misreported_as_complete_asset_package(tmp_path):
    f = tmp_path / "template.urdf"
    f.write_text(
        '<robot name="r" xmlns:xacro="http://www.ros.org/wiki/xacro"><xacro:include filename="missing.xacro"/></robot>'
    )
    with pytest.raises(ValueError, match="Expand Xacro"):
        to_lean(f, tmp_path / "lean")
