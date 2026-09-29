"""Conversion must not invoke toolchain installers, even if runtime is missing."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from fluxkernel.robotics import lean_runtime
from fluxkernel.robotics.lean_document import from_lean, to_lean, tree


def installed():
    try:
        return lean_runtime.lean_binary()
    except ValueError:
        pytest.skip("Preinstalled pinned Lean required")


def test_missing_runtime_never_executes_launcher(monkeypatch, tmp_path):
    launcher = tmp_path / "bin/lean"
    launcher.parent.mkdir()
    launcher.write_text("#!/bin/sh\nexit 99\n")
    launcher.chmod(0o755)
    monkeypatch.setenv("ELAN_HOME", str(tmp_path / "empty"))
    monkeypatch.setenv("PATH", str(launcher.parent))
    monkeypatch.delenv("FK_LEAN_BIN", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("A launcher was executed")

    monkeypatch.setattr(lean_runtime.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="No download was attempted"):
        lean_runtime.lean_binary()
    monkeypatch.setenv("FK_LEAN_BIN", str(launcher))
    with pytest.raises(ValueError, match="Offline Lean runtime unavailable"):
        lean_runtime.lean_binary()


def test_explicit_missing_runtime_does_not_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("FK_LEAN_BIN", str(tmp_path / "absent/bin/lean"))
    with pytest.raises(ValueError, match="Offline Lean runtime unavailable"):
        lean_runtime.lean_binary()


def test_wrong_version_rejected(monkeypatch, tmp_path):
    binary = tmp_path / "bin/lean"
    binary.parent.mkdir()
    binary.touch()
    stdlib = tmp_path / "lib/lean/Init.olean"
    stdlib.parent.mkdir(parents=True)
    stdlib.touch()
    monkeypatch.setenv("FK_LEAN_BIN", str(binary))
    monkeypatch.setattr(
        lean_runtime.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "0.0.0\n", ""),
    )
    with pytest.raises(ValueError, match="Offline Lean runtime unavailable"):
        lean_runtime.lean_binary()


def test_bidirectional_without_path_or_elan_home(monkeypatch, tmp_path):
    binary = installed()
    monkeypatch.setenv("FK_LEAN_BIN", str(binary))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setenv("ELAN_HOME", str(tmp_path / "empty-elan"))
    raw = b'<robot name="offline"><link name="base"/></robot>'
    input_path = tmp_path / "robot.urdf"
    input_path.write_bytes(raw)
    to_lean(input_path, tmp_path / "lean")
    from_lean(tmp_path / "lean", tmp_path / "exact")
    assert (tmp_path / "exact/robot.urdf").read_bytes() == raw
    (tmp_path / "lean/source.urdf").unlink()
    input_path.unlink()
    from_lean(tmp_path / "lean", tmp_path / "generated")
    assert tree((tmp_path / "generated/robot.urdf").read_bytes()) == tree(raw)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux seccomp test harness")
def test_real_roundtrip_with_kernel_network_denial(tmp_path):
    import ctypes.util

    if not ctypes.util.find_library("seccomp"):
        pytest.skip("libseccomp is required")
    binary = installed()
    repo = Path(__file__).resolve().parents[1]
    code = """
from pathlib import Path
import socket, errno
from fluxkernel.robotics.lean_document import to_lean, from_lean, tree
try:
    socket.socket()
except OSError as exc:
    assert exc.errno == errno.EPERM
else:
    raise AssertionError('Network is not denied')
p = Path('robot.urdf'); raw = b'<robot name="r"><link name="base"/></robot>'
p.write_bytes(raw)
to_lean(p, 'lean'); from_lean('lean', 'exact')
assert Path('exact/robot.urdf').read_bytes() == raw
Path('lean/source.urdf').unlink(); p.unlink()
from_lean('lean', 'regenerated')
assert tree(Path('regenerated/robot.urdf').read_bytes()) == tree(raw)
"""
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/without_network.py"),
            sys.executable,
            "-c",
            code,
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "FK_LEAN_BIN": str(binary),
            "PYTHONPATH": str(repo),
            "PATH": str(tmp_path / "empty-bin"),
            "ELAN_HOME": str(tmp_path / "empty-elan"),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"probe": "EPERM"' in result.stderr
