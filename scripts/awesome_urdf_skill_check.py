#!/usr/bin/env python3
"""Generate explicit corpus URDF targets using the installed URDF skill.

Run only our generated Python wrappers, never upstream generator scripts. Keep
skill acceptance separate from conversion equality and asset-closure results.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inventory", type=Path)
    p.add_argument("lean_results", type=Path)
    p.add_argument("--urdf-tool", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    cases = json.loads(args.inventory.read_text())["cases"]

    def check(case):
        lean = args.lean_results / case["case_id"] / "Robot.lean"
        if not lean.exists():
            return {
                "case_id": case["case_id"],
                "status": "not_generated_document_failed",
            }
        folder = Path(case["file"]).parent
        script = folder / ("fk_gen_" + case["case_id"] + ".py")
        target = folder / ("fk_checked_" + case["case_id"] + ".urdf")
        script.write_text(
            "from pathlib import Path\nfrom fluxkernel.robotics.lean_document import Reader,source,render_lean\n"
            f"LEAN=Path({str(lean.resolve())!r})\n"
            "def gen_urdf():\n    return render_lean(source(*Reader(LEAN.read_text()).read())).decode()\n"
        )
        run = subprocess.run(
            [sys.executable, str(args.urdf_tool), str(script), "-o", str(target)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        return {
            "case_id": case["case_id"],
            "status": "passed" if run.returncode == 0 else "rejected",
            "file": str(target),
            "generator": str(script),
            "log": (run.stdout + run.stderr)[-2500:],
        }

    report = {
        "scope": "Installed skill subset, not full URDF or physical validation",
        "cases": [],
        "completed": False,
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(check, c) for c in cases]):
            report["cases"].append(f.result())
            if len(report["cases"]) % 25 == 0:
                print(
                    "skill checked", len(report["cases"]), "/", len(cases), flush=True
                )
            args.output.write_text(json.dumps(report, indent=2))
    report["completed"] = True
    args.output.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
