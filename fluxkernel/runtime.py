"""Portable resource and writable-data locations; standard library only."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

PROOF_FILES = (
    "formal/FluxKernel/Closure.lean", "formal/FluxKernel/Robot.lean", "formal/FluxKernel.lean",
    "lean-toolchain", "lakefile.toml",
)


def assets_root() -> Path:
    package = Path(__file__).resolve().parent
    bundled = package / "_assets"
    if bundled.is_dir():
        return bundled
    checkout = package.parent
    if (checkout / "formal/FluxKernel/Closure.lean").is_file():
        return checkout
    raise FileNotFoundError("FluxKernel proof resources are missing; reinstall the package.")


def data_dir() -> Path:
    """Respect explicit configuration, preserve checkout runs, otherwise use user data."""
    if value := os.environ.get("FK_DEMO_DATA"):
        return Path(value).expanduser().resolve()
    checkout = Path(__file__).resolve().parent.parent
    if (checkout / "pyproject.toml").is_file() and (checkout / "formal").is_dir():
        return checkout / ".demo" / "runs"
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return base.expanduser().resolve() / "fluxkernel" / "runs"


def copy_proof_project(destination: Path) -> None:
    root = assets_root()
    for name in PROOF_FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
