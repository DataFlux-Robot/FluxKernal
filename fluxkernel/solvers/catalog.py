"""L2 plugin: the standard-parts catalog — the Mathlib of this system
(impl plan §2: `exact lemma` closes goals directly from the library).

Catalog entries are JSON files under catalog/ (repo root, FK_CATALOG_DIR, or
./catalog). Entry shape:
  {"name": "...", "kind": "motor", "supplier": "...", "tier": 1,
   "bounds": {"torque_nm": {">=": 50}, "rpm": {">=": 12000}},
   "ground": {...optional projection...}}

Query grammar: "torque_nm>=50 rpm>=12000" — every predicate must be covered
by the entry's bounds (entry interval must admit the demanded value).
"""
from __future__ import annotations

import json
import os
import re
import glob
from pathlib import Path

from .registry import register

_Q = re.compile(r"([A-Za-z_][\w.-]*)\s*(>=|<=|>|<|=)\s*(-?\d+(?:\.\d+)?)")


def catalog_dirs() -> list[Path]:
    dirs = []
    env = os.environ.get("FK_CATALOG_DIR")
    if env:
        dirs.append(Path(env))
    dirs.append(Path(__file__).resolve().parents[2] / "catalog")
    dirs.append(Path.cwd() / "catalog")
    return [d for d in dirs if d.is_dir()] or [Path(__file__).resolve().parents[2] / "catalog"]


def load_entries() -> list[dict]:
    out = []
    for d in catalog_dirs():
        for f in sorted(glob.glob(str(d / "*.json"))):
            try:
                data = json.loads(Path(f).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            entries = data if isinstance(data, list) else data.get("entries", [data])
            for e in entries:
                if isinstance(e, dict) and e.get("name"):
                    out.append(e)
    # de-dup by name (first dir wins)
    seen = {}
    for e in out:
        seen.setdefault(e["name"], e)
    return list(seen.values())


def parse_query(q: str) -> list[tuple[str, str, float]]:
    return [(m.group(1), m.group(2), float(m.group(3))) for m in _Q.finditer(q or "")]


def _entry_admits(entry: dict, qty: str, op: str, value: float) -> bool:
    b = (entry.get("bounds") or {}).get(qty)
    if b is None:
        return False
    if isinstance(b, (list, tuple)) and len(b) == 2:
        b = {b[0]: b[1]}
    if not isinstance(b, dict):
        return False
    lo, hi = b.get(">="), b.get("<=")
    if "=" in b:                       # exact-match bound admits only that value
        lo = hi = float(b["="])
    if lo is None and hi is None:
        return False
    ok = True
    if op in (">=", ">"):
        ok = ok and (hi is None or hi >= value) and (lo is not None or hi is not None)
    if op in ("<=", "<"):
        ok = ok and (lo is None or lo <= value)
    if op == "=":
        ok = ok and (lo is None or lo <= value) and (hi is None or hi >= value)
    return ok


def search(query: str) -> list[dict]:
    preds = parse_query(query)
    entries = load_entries()
    if not preds:
        return entries
    return [e for e in entries
            if all(_entry_admits(e, q, op, v) for q, op, v in preds)]


@register("catalog-match")
def catalog_match(node_specs, args, ctx):
    query = args.get("match", "") or ""
    src = args.get("from", "catalog")
    hits = search(query) if src in ("catalog", "archive") else []
    if not hits:
        raise ValueError(f"no catalog hit for {query!r} (from {src})")
    best = hits[0]
    guarantees = [{"id": f"cat-{i}", "stmt": f"{q} {op} {v:g}",
                   "bounds": {q: (best.get("bounds") or {}).get(q, [op, v])}}
                  for i, (q, op, v) in enumerate(parse_query(query))]
    fields = {"kind": best.get("kind", "part"),
              "spec": {"guarantees": guarantees,
                       "catalog_entry": best["name"],
                       "tier": best.get("tier", 1)},
              "ground": best.get("ground")}
    evidence = [{"solver": "catalog", "entry": best["name"],
                 "tier": best.get("tier", 1), "supplier": best.get("supplier", ""),
                 "matched": [f"{q}{op}{v:g}" for q, op, v in parse_query(query)]}]
    obligations = [{"id": "catalog-hit", "prop": f"entry {best['name']} satisfies {query!r}",
                    "holds": True, "checker": "catalog", "detail": ""}]
    return fields, evidence, obligations
