"""fk review (P7a): the pixel channel as SOFT obligations.

Takes `fk render`'s four-view PNGs of the honest DAG geometry, the
declared intent (goal node's goals/guarantees statements), optionally a
reference image (`--vs`, P7e reverse-engineering loop), and asks an
external VLM "does this look like what the DAG claims?".  The answer is
archived on a `review` edge.

Red lines (spec P7 §B.5), enforced structurally:
- VLM output becomes obligations of class "soft" ONLY — Engine.review()
  hardcodes oclass="soft"; there is no parameter or env var that can
  make it hard;
- `fk verify` never re-runs the VLM: review edges are schema-checked
  (soft-only, evidence present) by verify_store and otherwise skipped;
- the endpoint is external configuration (FK_VLM_BASE_URL, FK_VLM_API_KEY,
  FK_VLM_MODEL) — strategy layer only, the L0/L1 zero-dependency
  discipline is untouched.
"""
from __future__ import annotations

import base64
import json
import os
import math
import re
import tempfile as _tf
import urllib.request

PROMPT = """You are reviewing an engineering CAD render against the declared intent.

The images are four views (iso, front, top, right) of the CURRENT design
produced by a fail-closed CAD kernel: every visible part is real grounded
geometry from the design graph — nothing is drawn that is not declared.
Colors: steel blue = Part, amber = Component, brick red = Resource,
teal = catalog-representative envelope.

Declared intent: {intent}
{vs_block}
Judge ONLY from what is visible. Report discrepancies such as: missing
parts named in the intent, parts stacked at the origin instead of in
position, structurally implausible proportions, or a render that does not
read as the claimed object class.  Do NOT invent issues you cannot see.

Reply with STRICT JSON only — an array (possibly empty) of objects:
[{{"id": "visual-review-001", "prop": "<short claim>", "holds": false,
   "detail": "<what you see and why it disagrees with the intent>"}}]
Use "holds": true for confirmed-OK checks worth recording. No prose
outside the JSON array."""


def _intent_of(payload: dict) -> str:
    spec = payload.get("spec") or {}
    lines = []
    for g in spec.get("goals") or []:
        if g.get("stmt"):
            lines.append(f"- goal: {g['stmt']}")
    for g in spec.get("guarantees") or []:
        if g.get("stmt"):
            lines.append(f"- guarantee: {g['stmt']}")
    return "\n".join(lines) or "(no explicit goal statements on this node)"


def _data_url(path: str) -> str:
    raw = open(path, "rb").read()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def call_vlm(prompt: str, image_paths: list[str],
             base_url: str, api_key: str, model: str,
             timeout: int = 120) -> list[dict]:
    """OpenAI-compatible chat completion with image inputs -> findings list.
    Stdlib only (urllib): strategy layer, no new dependencies."""
    content = [{"type": "text", "text": prompt}]
    for p in image_paths:
        content.append({"type": "image_url", "image_url": {"url": _data_url(p)}})
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode("utf-8"))
    text = resp["choices"][0]["message"]["content"]
    # strict-JSON extraction: first [...] or {...} block in the reply
    m = re.search(r"\[.*\]|\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"VLM reply is not JSON: {text[:200]}")
    data = json.loads(m.group(0))
    if isinstance(data, dict):
        data = data.get("findings") or [data]
    out = []
    for f in data:
        if not isinstance(f, dict) or "prop" not in f:
            continue
        f["checker"] = f"vlm/{model}"
        out.append(f)
    return out


def run_review(eng, a) -> int:
    from ..strategy import scene, render_png

    t_d, t_node = eng.dag.get_node(a.ref)
    intent = _intent_of(t_node.payload())

    parts = scene.collect_grounded(eng)
    if not parts:
        print("fatal: no grounded geometry to review")
        return 2
    tri_groups = [(scene.role_color(p), scene.mesh_shape(s))
                  for _, p, s in parts]
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp(prefix="fk-review-"))
    pngs = render_png.render_views(tri_groups, tmp / "review",
                                   title=str(a.ref))
    if not pngs:
        print("fatal: render failed")
        return 2

    vs = getattr(a, "vs", "") or ""
    images = list(pngs) + ([vs] if vs else [])
    vs_block = ("\nA reference image is included FIRST-hand for comparison "
                "(reverse-engineering mode): judge how the render matches "
                "the reference.\n" if vs else "")

    base = os.environ.get("FK_VLM_BASE_URL", "")
    key = os.environ.get("FK_VLM_API_KEY", "")
    model = os.environ.get("FK_VLM_MODEL", "")
    if not (base and model):
        # L1.2 meta-rule: perception unavailable != perception passed.
        # Archive a REJECTED review edge so the case stays open
        # (perception-missing) instead of silently skipping station 5.
        eng.review(a.ref, [], {
            "model": "none", "images": [str(p) for p in pngs], "vs": vs,
            "intent": intent[:500], "views": ["iso", "front", "top", "right"],
            "out": None, "state": "rejected",
            "reason": "vlm-unavailable: FK_VLM_BASE_URL/FK_VLM_MODEL not configured"})
        print("PERCEPTION-MISSING: fk review needs FK_VLM_BASE_URL and "
              "FK_VLM_MODEL — rejected review edge archived; the case "
              "stays OPEN until perception runs (or :waive with a reason)")
        return 2
    try:
        findings = call_vlm(PROMPT.format(intent=intent, vs_block=vs_block),
                            images, base, key, model)
    except Exception as e:                       # noqa: BLE001 — report, don't crash
        # L1.2: VLM call failure archives a rejected review edge too
        eng.review(a.ref, [], {
            "model": model, "images": [str(p) for p in pngs], "vs": vs,
            "intent": intent[:500], "views": ["iso", "front", "top", "right"],
            "out": None, "state": "rejected",
            "reason": f"vlm-unavailable: {e}"})
        print(f"PERCEPTION-MISSING: VLM call failed ({e}) — rejected "
              f"review edge archived; case stays OPEN")
        return 2

    res = eng.review(a.ref, findings, {
        "model": model, "images": [str(p) for p in pngs], "vs": vs,
        "intent": intent[:500], "views": ["iso", "front", "top", "right"],
        "out": None})
    issues = [f for f in findings if not f.get("holds", False)]
    print(json.dumps({"review": findings,
                      "edge": res.get("edge", ""), "state": res["state"],
                      "render_paths": [str(p) for p in pngs]},
                     ensure_ascii=False, indent=1))
    print(f"review edge {res['state']}: {len(findings)} findings "
          f"({len(issues)} issues) — soft obligations, never gate")
    return 0


def _selftest_image(out_path):
    """Built-in known-answer test image: a circle with a MISSING WEDGE
    (the analogue of the missing-tail test).  A working VLM reports the
    gap; an unavailable/degenerate one cannot."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        fig, ax = plt.subplots(figsize=(4, 4), dpi=100)
        fig.patch.set_facecolor("white")
        th = np.linspace(0.35, 2 * math.pi - 0.15, 200)
        ax.plot(np.cos(th), np.sin(th), lw=14, color="#2a4d69",
                solid_capstyle="round")
        ax.plot([math.cos(0.35) * 0.2, math.cos(0.35)], [math.sin(0.35) * 0.2,
                 math.sin(0.35)], lw=14, color="#2a4d69")
        ax.set_xlim(-1.4, 1.4); ax.set_ylim(-1.4, 1.4)
        ax.set_aspect("equal"); ax.axis("off")
        fig.savefig(out_path, facecolor="white")
        plt.close(fig)
        return True
    except Exception:
        return False


def run_selftest() -> int:
    """fk review --selftest: call the configured VLM with a known-answer
    image (a circle with a missing wedge).  PASS requires: JSON parses,
    findings non-empty.  Any failure is an ERROR — never a silent skip."""
    base = os.environ.get("FK_VLM_BASE_URL", "")
    key = os.environ.get("FK_VLM_API_KEY", "")
    model = os.environ.get("FK_VLM_MODEL", "")
    if not (base and model):
        print("SELFTEST ERROR: FK_VLM_BASE_URL / FK_VLM_MODEL not "
              "configured — selftest cannot run, and perception is NOT "
              "available (fix the environment; do not skip)")
        return 2
    import tempfile
    from pathlib import Path as _P
    tmp = _P(_tf.mkdtemp(prefix="fk-selftest-"))
    img = tmp / "known_answer.png"
    if not _selftest_image(str(img)):
        print("SELFTEST ERROR: could not render the built-in test image")
        return 2
    prompt = ("This image shows a shape. Reply with STRICT JSON only: "
              '[{"id": "selftest", "prop": "<what you see>", '
              '"holds": false, "detail": "<defects you observe>"}] — '
              "report any defect you can observe (gap, missing part, "
              "incomplete shape). No prose outside the JSON.")
    try:
        findings = call_vlm(prompt, [str(img)], base, key, model)
    except Exception as e:                        # noqa: BLE001
        print(f"SELFTEST ERROR: VLM call failed: {e}")
        return 2
    if not findings:
        print("SELFTEST ERROR: VLM returned an empty finding list for a "
              "known-defect image — the endpoint is not usable for "
              "perception (do not skip; fix the endpoint)")
        return 2
    print(f"SELFTEST PASS: {model} returned {len(findings)} finding(s) "
          f"on the known-answer image — perception channel usable")
    return 0
