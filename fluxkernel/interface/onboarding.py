"""Dependency-light onboarding commands. Diagnostics never call model APIs."""
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..runtime import assets_root, data_dir


def version() -> str:
    try:
        return importlib.metadata.version("fluxkernel")
    except importlib.metadata.PackageNotFoundError:
        return "0.5.0 (source checkout)"


def diagnose(profile: str = "core") -> dict:
    if profile not in ("core", "studio", "proof", "live", "agent"):
        raise ValueError("unknown diagnostic profile")
    checks = []

    def add(name, ok, detail, fix=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fix": fix if not ok else ""})

    add("python", sys.version_info >= (3, 12), sys.version.split()[0], "Use Python 3.12 or newer.")
    try:
        root = assets_root()
        add("resources", all((root / p).is_file() for p in (
            "formal/FluxKernel/Closure.lean", "formal/FluxKernel.lean", "lakefile.toml",
            "lean-toolchain", "scripts/verify_demo_bundle.py", "examples/hello.fcad")),
            "Canonical proof project and examples", "Reinstall FluxKernel from a complete distribution.")
    except FileNotFoundError:
        root = None
        add("resources", False, "Bundled resources missing", "Reinstall FluxKernel.")
    if profile in ("studio", "live", "agent"):
        for module, distribution in [("fastapi", "fastapi"), ("uvicorn", "uvicorn"),
                                     ("httpx", "httpx"), ("PIL", "pillow"),
                                     ("pydantic", "pydantic"), ("multipart", "python-multipart"),
                                     ("numpy", "numpy"), ("scipy", "scipy"), ("OCP", "cadquery-ocp")]:
            present = importlib.util.find_spec(module) is not None
            try:
                installed = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                installed = "not installed"
            add(module, present, installed, 'Install the demo extra: python -m pip install -e ".[demo]"')
    if profile == "agent":
        try:
            sdk = importlib.metadata.version('mcp')
            supported = sdk.split('.')[0] == '2' and int(sdk.split('.')[1]) >= 2
        except (importlib.metadata.PackageNotFoundError, ValueError):
            sdk, supported = 'not installed or unsupported', False
        add('mcp', supported, sdk, 'Install the agent extra: python -m pip install -e ".[demo,agent]"')
    if profile in ("proof", "live", "agent"):
        pinned = (root / "lean-toolchain").read_text().strip() if root else "unknown"
        ready = False
        if shutil.which("elan") and shutil.which("lake"):
            try:
                # `which` resolves an installed toolchain; it does not install one.
                proc = subprocess.run(["elan", "which", "lean"], capture_output=True, text=True,
                                      timeout=10, env={**os.environ, "ELAN_TOOLCHAIN": pinned})
                ready = proc.returncode == 0 and Path(proc.stdout.strip()).is_file()
            except (OSError, subprocess.TimeoutExpired):
                pass
        add("lean", ready, pinned, f"Install elan, then run: elan toolchain install {pinned}")
    if profile == "live":
        path = Path(os.getenv("FK_MODEL_CONFIG", str(Path.home() / ".config/fluxkernel/model.json")))
        try:
            config = json.loads(path.read_text()) if path.is_file() else {}
            provider = config.get("provider", "anthropic")
            configured = (bool(config.get("api_key", os.getenv("FK_MODEL_API_KEY", "")))
                          if provider == "anthropic" else provider == "ollama")
            add("model", configured, "Configuration present; connectivity and vision capability are not probed.",
                "Set FK_MODEL_API_KEY or configure the private model.json; see docs/QUICKSTART.md.")
        except (ValueError, OSError, AttributeError):
            add("model", False, "Model configuration is not valid JSON object data.",
                "Repair the private configuration file; no configuration values are printed.")
    return {"schema": "fluxkernel-doctor-v1", "version": version(), "profile": profile,
            "ok": all(c["ok"] for c in checks), "checks": checks, "data_directory": str(data_dir()),
            "note": "No API calls or automatic toolchain installs. A doctor pass is not a design or physics check."}


def cmd_doctor(args):
    report = diagnose(args.profile)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"FluxKernel {report['version']} / {args.profile}")
        for check in report["checks"]:
            print(f"{'PASS' if check['ok'] else 'FAIL'}  {check['name']}: {check['detail']}")
            if check["fix"]:
                print(f"      {check['fix']}")
        print(f"Runs: {report['data_directory']}\n{report['note']}")
    return 0 if report["ok"] else 1


def cmd_example(args):
    target = Path(args.output)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write((assets_root() / "examples/hello.fcad").read_text(encoding="utf-8"))
    except FileExistsError:
        print(f"Refusing to overwrite {target}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Cannot write example: {exc}", file=sys.stderr)
        return 1
    print(f"Created {target}. Run: fk init, then fk run {target}, then fk verify.")
    return 0


def cmd_demo(args):
    from ..studio import generate_reference, StudioError
    try:
        result = generate_reference(args.reference, output_dir=args.output, equipment_depth=args.equipment_depth)
    except (StudioError, OSError, ValueError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"Reference run: {result.id} (no model inference)\nArtifacts: {result.directory}")
        print(f"Product parts: {result.counts['parts']} / equipment parts: {result.counts['equipment_parts']}")
        print(f"Plan: {result.status} / physical performance: {result.physical_status}")
        print(f"Recheck: python {Path(result.directory) / 'verify.py'} {result.directory}")
    return 1 if args.require_proof and not result.proof_accepted else 0
