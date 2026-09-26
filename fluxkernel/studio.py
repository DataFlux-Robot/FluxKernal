"""Small headless API for reproducible reference runs, with isolated CAD output.

Reference runs use curated designs, never an API or an image-inference fallback.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .runtime import data_dir


class StudioError(RuntimeError):
    """A run did not produce a complete artifact set."""


@dataclass(frozen=True)
class Run:
    id: str
    directory: str
    mode: str
    status: str
    proof_accepted: bool
    physical_status: str
    counts: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


def generate_reference(reference: str = "phone", *, output_dir: str | Path | None = None,
                       equipment_depth: int = 1, timeout: float = 300) -> Run:
    """Generate CAD + a checked plan without a model key. Each run gets a new ID.

    Missing Lean leaves the plan explicitly open. Missing CAD dependencies or
    failed geometry raise StudioError; partial evidence remains in the run folder.
    The worker isolates native CAD stdout and process state from calling agents.
    """
    if reference not in ("phone", "car", "aircraft"):
        raise ValueError("reference must be phone, car, or aircraft")
    if type(equipment_depth) is not int or equipment_depth not in (0, 1):
        raise ValueError("equipment_depth must be 0 or 1")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    root = Path(output_dir).expanduser().resolve() if output_dir is not None else data_dir()
    run = root / uuid.uuid4().hex[:16]
    run.mkdir(parents=True)
    command = [sys.executable, "-m", "fluxkernel.studio", "--run", str(run),
               "--reference", reference, "--equipment-depth", str(equipment_depth)]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        status = run / "status.json"
        record = json.loads(status.read_text(encoding="utf-8")) if status.is_file() else {"id": run.name, "events": []}
        record.update(state="failed", stage="failed", error="Reference worker exceeded its time limit")
        status.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        raise StudioError(f"Reference run timed out; partial evidence: {run}") from exc
    # Diagnostics are not added retroactively to the immutable manifest.
    (run / "worker.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode or not (run / "result.json").is_file():
        raise StudioError(f"Reference run failed; inspect {run / 'status.json'} and worker.log. "
                          "Install the demo extra and run `fk doctor --profile studio`.")
    status = json.loads((run / "status.json").read_text(encoding="utf-8"))
    if status["state"] != "complete":
        raise StudioError(f"Reference run is incomplete; inspect {run / 'status.json'}")
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    return Run(run.name, str(run), result["model"]["mode"], result["status"],
               result["proof"]["accepted"], result["physical_status"], result["counts"])


def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Internal isolated reference worker")
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--reference", required=True, choices=("phone", "car", "aircraft"))
    parser.add_argument("--equipment-depth", type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    from .demo.models import Request
    from .demo.pipeline import execute
    image = Path(__file__).parent / "demo/static/references" / (args.reference + ".jpg")
    execute(args.run, Request(mode="reference", reference=args.reference,
                             equipment_depth=args.equipment_depth), image.read_bytes())
    status = json.loads((args.run / "status.json").read_text(encoding="utf-8"))
    return 0 if status["state"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
