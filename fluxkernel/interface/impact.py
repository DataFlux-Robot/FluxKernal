"""G3: change propagation — `fk impact <ref> --set set/key=value [--apply]`.

Lean semantics: change a hypothesis (parameter) and every dependent
theorem re-checks.  The ORIGINAL store is never mutated — the stored
source script is replayed in a SHADOW store with `(params-override ...)`
forms injected right after each affected `(params ...)` definition; old
promoted edges stay as history, the replay produces a fresh generation.

Without --apply the command is a dry run: it reports which forms consume
the parameter set and what the replay plan would be.
"""
from __future__ import annotations

import tempfile
import os
from pathlib import Path

from ..store.objstore import Store
from ..semantics.operators import Engine
from ..interface import fcad
from ..interface.runner import Runner


def _forms_consuming(forms: list, set_name: str) -> int:
    """Count forms referencing any '<set>/' parameter leaf."""
    hits = 0
    for f in forms:
        found = []

        def walk(v):
            if isinstance(v, list):
                if v and v[0] == "param" and len(v) > 1 \
                        and str(v[1]).startswith(set_name + "/"):
                    found.append(v[1])
                for x in v:
                    walk(x)
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x)
        walk(f)
        if found:
            hits += 1
    return hits


def replay_with_overrides(store: Store,
                          overrides: dict[str, dict[str, float]]) -> dict:
    """Shadow-store replay of the stored source script with parameter
    overrides.  Returns {'rc','open','verify','store_root','engine'} —
    the caller decides what to report; nothing here mutates `store`."""
    names = store.names()
    blob_d = names.get("@last-script")
    if not blob_d:
        raise KeyError("no stored script — run `fk run <script>` first")
    text = store.get_blob(blob_d).decode("utf-8")
    forms = fcad.parse(text)

    replay = []
    injected = []
    for f in forms:
        replay.append(f)
        if isinstance(f, list) and f and f[0] == "params" and len(f) > 1:
            set_name = str(f[1])
            for k, v in (overrides.get(set_name) or {}).items():
                replay.append(["params-override", set_name, k, float(v)])
                injected.append(f"{set_name}/{k}={v:g}")

    td = tempfile.mkdtemp(prefix="fk-impact-")
    eng = Engine(Store(os.path.join(td, ".fk")))
    rc = Runner(eng).run(replay)

    from ..semantics import goals as goalsview
    open_goals = [{"kind": g["kind"], "termination": g.get("termination")}
                  for g in goalsview.goals_view(eng.dag)["open"]]

    from .cli import verify_store
    problems = verify_store(eng)
    return {"rc": rc, "open": open_goals, "verify": problems,
            "store_root": td, "engine": eng, "injected": injected}


def parse_sets(pairs: list[str]) -> dict[str, dict[str, float]]:
    """['wing/span=3600', 'wing/t=3'] -> {'wing': {'span':3600,'t':3}}"""
    out: dict[str, dict[str, float]] = {}
    for p in pairs or []:
        if "=" not in p or "/" not in p:
            raise ValueError(f"bad --set {p!r}: want <set>/<key>=<value>")
        path, val = p.split("=", 1)
        set_name, key = path.rsplit("/", 1)
        out.setdefault(set_name.strip(), {})[key.strip()] = float(val)
    return out
