"""Resolve a preinstalled Lean distribution without invoking download launchers."""

import os
from pathlib import Path
import shutil
import subprocess

from ..runtime import assets_root


def lean_binary():
    """Return a real, version-matched compiler; never run elan or lake."""
    pin = (assets_root() / "lean-toolchain").read_text().strip()
    version = pin.rsplit(":v", 1)[-1]
    executable = "lean.exe" if os.name == "nt" else "lean"
    explicit = os.environ.get("FK_LEAN_BIN")
    if explicit:
        candidates = [Path(explicit).expanduser()]
    else:
        elan_home = Path(os.environ.get("ELAN_HOME", str(Path.home() / ".elan")))
        candidates = [
            elan_home
            / "toolchains"
            / pin.replace("/", "--").replace(":", "---")
            / "bin"
            / executable
        ]
        if found := shutil.which("lean"):
            candidates.append(Path(found))
    for candidate in candidates:
        binary = candidate.resolve()
        # Elan shims have no adjacent standard library. Never execute them even
        # for --version: that alone can install a toolchain on some machines.
        if (
            not binary.is_file()
            or not (binary.parent.parent / "lib/lean/Init.olean").is_file()
        ):
            continue
        result = subprocess.run(
            [str(binary), "--short-version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip() == version:
            return binary
    raise ValueError(
        f"Offline Lean runtime unavailable: need {pin}. Install it during setup "
        "or set FK_LEAN_BIN to the real compiler in a copied Lean distribution "
        "(including lib/lean). No download was attempted."
    )
