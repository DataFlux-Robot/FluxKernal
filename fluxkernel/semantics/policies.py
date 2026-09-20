"""M2: code-as-policy — external rule library feeding the C0 channel.

A policy is a content-addressed declaration (policies/<id>.json) plus a
check module (policies/<id>.py) returning obligations in EXACTLY the
certificate schema.  The kernel's adjudication logic does not change one
line: a hard policy that returns holds=False rejects the edge through
the ordinary C0 gate; soft ones only join the evidence vector.

Applicability: payload kind / role / spec.archetype (stamped by the
archetype loader).  Every fired policy records its digest in the
obligation checker — `fk verify` and reviewers can pin the version.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path


def policy_dirs() -> list[Path]:
    dirs = []
    env = os.environ.get("FK_POLICY_DIR")
    if env:
        dirs.append(Path(env))
    dirs.append(Path(__file__).resolve().parents[2] / "policies")
    dirs.append(Path.cwd() / "policies")
    return [d for d in dirs if d.is_dir()]


_CACHE: dict[str, dict] = {}


def load_policies() -> dict[str, dict]:
    """All declared policies, id -> declaration (with content digests)."""
    if _CACHE:
        return _CACHE
    out: dict[str, dict] = {}
    for d in policy_dirs():
        for f in sorted(d.glob("*.json")):
            try:
                pol = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            pol.setdefault("id", f.stem)
            pol["_dir"] = str(d)
            code = d / (pol.get("check", "") or "")
            h = hashlib.sha256()
            h.update(f.read_bytes())
            if code.is_file():
                h.update(code.read_bytes())
            pol["_digest"] = h.hexdigest()
            out[pol["id"]] = pol
    _CACHE.update(out)
    return out


def applicable(payload: dict, pol: dict) -> bool:
    ap = pol.get("applies_to") or {}
    kinds = ap.get("kinds") or []
    roles = ap.get("roles") or []
    arch = ap.get("within_archetype")
    spec = payload.get("spec") or {}
    if arch and spec.get("archetype") != arch:
        return False
    if kinds and payload.get("kind") not in kinds:
        return False
    if roles and payload.get("role") not in roles:
        return False
    return bool(kinds or roles or arch)


def _import_check(pol: dict):
    code = Path(pol["_dir"]) / pol.get("check", "")
    if not code.is_file():
        raise ImportError(f"policy {pol['id']}: check module missing: {code}")
    mod_name = f"fk_policy_{pol['id'].replace('-', '_')}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, code)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[mod_name] = mod
    return mod


def policy_obligations(payload: dict, ctx: dict | None = None) -> list[dict]:
    """Run every applicable policy; normalize outputs to obligations with
    the policy digest pinned in the checker field."""
    out: list[dict] = []
    spec = payload.get("spec") or {}
    ctx = ctx or {}
    ctx = {**ctx,
           "params": {**(spec.get("archetype_params") or {}),
                      **(payload.get("params") or {})}}
    for pid, pol in sorted(load_policies().items()):
        if not applicable(payload, pol):
            continue
        try:
            mod = _import_check(pol)
            res = mod.main(payload, ctx)
        except Exception as e:      # a broken policy is a finding, not a crash
            out.append({"id": f"policy:{pid}", "prop": "policy executes",
                        "holds": False, "class": pol.get("class", "hard"),
                        "checker": f"policy:{pid}@{pol['_digest'][:12]}",
                        "detail": f"policy error: {e}"})
            continue
        results = res if isinstance(res, list) else ([res] if res else [])
        for r in results:
            o = dict(r)
            o.setdefault("id", f"policy:{pid}")
            o.setdefault("class", pol.get("class", "hard"))
            o.setdefault("holds", True)
            o.setdefault("prop", pol.get("statement", pid))
            o["checker"] = f"policy:{pid}@{pol['_digest'][:12]}"
            out.append(o)
    return out
