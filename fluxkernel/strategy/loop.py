"""fk iterate (P7b): the perception-action loop driver.

    fk iterate design.fcad --budget 50 [--agent "cmd"] [--no-vlm]

Each round: run the script in a FRESH store (history stays clean, the
working .fk is never touched by the loop), gather the two feedback
channels, hand them to an external editing agent over a JSON
stdin/stdout turn protocol, and repeat with the edited script.

Channel A (structured): open goals, rejected edges with repair hints,
medium ledger pressure.
Channel B (pixels): fk render four-view PNGs + fk review (VLM) soft
issues — skipped with an explicit note when no VLM endpoint is
configured.

Red lines (spec P7 §B.5): the budget cap and the stall detector are
NOT configurable — 5 consecutive rounds without an OPEN-goals decrease
stop the loop with a deadlock report; every intermediate rejection is
archived in that round's store (failures are assets).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STALL_ROUNDS = 5          # hardcoded — the anti-oscillation red line


def _run_round(script_text: str, workdir: Path, want_vlm: bool) -> dict:
    """One action->feedback round in a fresh store.  Returns channel A+B."""
    from fluxkernel.store.objstore import Store
    from fluxkernel.semantics.operators import Engine
    from fluxkernel.interface.runner import Runner
    from fluxkernel.solvers.feature3d import _silence_occt_messenger
    _silence_occt_messenger()
    eng = Engine(Store(workdir / ".fk"))
    rc = Runner(eng).run(script_text)

    from fluxkernel.semantics import goals as goalsview
    gv = goalsview.goals_view(eng.dag)
    rejected = [{"op": r.get("op"), "reason": r.get("reason", ""),
                 "output": r.get("output", "")} for r in gv["rejected"]]

    renders, review = [], []
    grounded = 0
    try:
        from . import scene
        parts = scene.collect_grounded(eng)
        grounded = len(parts)
        if parts:
            from . import render_png
            tri = [(scene.role_color(p), scene.mesh_shape(s))
                   for _, p, s in parts]
            renders = render_png.render_views(tri, workdir / "render",
                                               title="iterate")
    except Exception as e:                        # noqa: BLE001 — report
        renders = [f"render failed: {e}"]
    renders_ok = bool(renders) and isinstance(renders[0], str) \
        and not renders[0].startswith("render failed")
    if want_vlm and os.environ.get("FK_VLM_BASE_URL") and renders_ok \
            and grounded:
        try:
            from .review import run_review
            class _A:
                pass
            a = _A()
            a.ref = _intent_root(eng)
            a.vs = ""
            run_review(eng, a)
            # the findings ride the review edge — channel B payload
            for _, e2 in eng.dag.iter_edges():
                if e2.get("op") == "review" and e2.get("state") == "promoted":
                    review = [o.get("prop", "") + ": " + o.get("detail", "")
                              for o in (e2.get("certificate") or {})
                              .get("obligations", [])
                              if o.get("holds") is False]
                    break
        except Exception as e:                    # noqa: BLE001
            review = [f"review skipped: {e}"]
    # C8: score prices what the case-contract prices (design-gaps D2)
    case_reqs = len(gv.get("case", []))
    score = (1.0 / (1.0 + len(gv.get("open", [])))
             + 1.0 / (1.0 + case_reqs)
             + 0.5 / (1.0 + len(review)))
    return {"rc": rc, "score": round(score, 4),
            "open_goals": len(gv.get("open", [])),
            "open_case_requires": case_reqs,
            "open": [{"kind": g.get("kind"), "role": g.get("role"),
                      "termination": g.get("termination")}
                     for g in gv.get("open", [])][:20],
            "rejected": rejected, "render_paths": renders,
            "review_issues": review, "grounded_parts": grounded}


def _intent_root(eng) -> str:
    for name, d in eng.store.names().items():
        try:
            p = eng.store.get_object(d)["payload"]
        except KeyError:
            continue
        if p.get("role") == "Intent":
            return name
    return sorted(eng.store.names())[0]


def run_iterate(a) -> int:
    script = Path(a.script).read_text(encoding="utf-8")
    budget = max(1, int(getattr(a, "budget", 50) or 50))
    agent_cmd = getattr(a, "agent", "") or ""
    want_vlm = not getattr(a, "no_vlm", False)
    if budget > 50:
        budget = 50                      # the cap is not negotiable either
    best_open = None
    no_progress = 0
    trajectory = []
    work = Path(tempfile.mkdtemp(prefix="fk-iterate-"))
    try:
        for rnd in range(1, budget + 1):
            rd = work / f"round{rnd:03d}"
            rd.mkdir()
            fb = _run_round(script, rd, want_vlm)
            fb["round"] = rnd
            trajectory.append({k: fb[k] for k in
                               ("round", "rc", "open_goals",
                                "grounded_parts")})
            print(f"round {rnd:02d}: rc={fb['rc']} score={fb.get('score', 0):.3f} "
                  f"open={fb['open_goals']} case={fb.get('open_case_requires', 0)} "
                  f"grounded={fb['grounded_parts']} "
                  f"rejected={len(fb['rejected'])}")
            if fb["open_goals"] == 0 and fb["rc"] in (0, 1) and \
                    all("expect-met" not in r.get("reason", "")
                        for r in fb["rejected"] if r.get("op") == "eval") \
                    and not [r for r in fb["rejected"]
                             if r.get("op") != "eval"]:
                print(f"SUCCESS at round {rnd}: OPEN GOALS (0)")
                (work / "trajectory.json").write_text(
                    json.dumps(trajectory, indent=1), encoding="utf-8")
                return 0
            # stall detector — hardcoded red line
            if best_open is None or fb["open_goals"] < best_open:
                best_open = fb["open_goals"]
                no_progress = 0
            else:
                no_progress += 1
                if no_progress >= STALL_ROUNDS:
                    print(f"DEADLOCK: {STALL_ROUNDS} rounds without an "
                          f"open-goal decrease (best {best_open})")
                    break
            if not agent_cmd:
                print(json.dumps(fb, ensure_ascii=False, default=str)[:4000])
                print("no --agent given — feedback above, stopping")
                break
            payload = json.dumps(
                {"script": script, **{k: fb[k] for k in
                 ("open", "rejected", "render_paths", "review_issues")}},
                ensure_ascii=False, default=str)
            try:
                proc = subprocess.run(
                    agent_cmd, input=payload, capture_output=True,
                    text=True, timeout=300, shell=True)
                reply = json.loads(proc.stdout.strip().splitlines()[-1])
                new_script = reply.get("edit") or script
            except Exception as e:                    # noqa: BLE001
                print(f"agent turn failed: {e}")
                break
            if new_script == script:
                no_progress += 1        # an agent echoing the same edit is
                if no_progress >= STALL_ROUNDS:  # an oscillator too
                    print("DEADLOCK: agent returns the same script")
                    break
            script = new_script
        (work / "trajectory.json").write_text(
            json.dumps(trajectory, indent=1), encoding="utf-8")
        print(f"stopped at budget/budget-exhausted; trajectory: "
              f"{work / 'trajectory.json'}")
        return 1
    finally:
        # keep the trajectory + stores for audit (failures are assets);
        # caller may inspect the temp dir path printed above
        pass
