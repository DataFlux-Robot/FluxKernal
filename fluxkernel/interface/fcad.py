"""L4: the .fcad DSL — S-expressions, item mode (the LLM-facing surface).

Grammar (impl plan §5, extended by v1.1/v1.2):

  top-level:
    (term <name> "<operational definition>")
    (node  <name> :role <R> :kind <k> :spec <spec> :params (...) :variants (...))
    (goal  <name> :kind <k> :spec <spec>)              ; = node :role Intent
    (edge  <name> :op <op> :in (<ref> ...) :out <name> :transform (<t> :k v ...) ...)
    (refine|compose|integrate|manufacture|abstract|eval|exact|procure ...)  ; op sugar
  spec:
    (contract (goals ...) (semantics ...) (assumes ...) (guarantees ...)
              (budget ...) (effluent ...) (forbidden ...) (not-responsible ...)
              (time-scale ...) (param-bounds ...) (param-checks ...) ...extras)
    (sketch (pts (p0 (param hw) 0) ...) (constraints (fix p3 0 0) ...))
    (<free-form alist>)                                 ; legacy/extras
  bounds:
    (qty (>= 22) (<= 29))            interval
    (qty (<= 50 :medium <node>))     one-sided + medium reference (v1.2 §19)

No variables, no control flow. Numbers are atoms, strings are double-quoted,
parameter holes are (param <name>) = sorry. Every form = one operator call =
one DAG commit; a failed form marks its edge rejected and the script CONTINUES
(failure trajectories are training assets), exit code stays non-zero.
"""
from __future__ import annotations

import re

from ..semantics import contracts
from ..semantics.contracts import ContractError


# ---------------------------------------------------------------- lexer ----
_TOKEN = re.compile(r'\s*(?:("[^"]*")|([()\[\]])|(;[^\n]*)|([^\s()\[\]";]+))')


class FcadError(Exception):
    def __init__(self, code: str, msg: str):
        self.code = code
        super().__init__(f"[{code}] {msg}")


def tokenize(text: str) -> list:
    toks, i = [], 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        if not m:
            if text[i] in " \t\r\n":
                i += 1
                continue
            raise FcadError("S1", f"unexpected character {text[i]!r} at offset {i}")
        i = m.end()
        s = m.group(0).strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith('"'):
            toks.append(("str", s[1:-1]))
        elif s in "()[]":
            toks.append((s, s))
        else:
            toks.append(("atom", s))
    return toks


def _atom(s: str):
    if s == "t" or s == "#t":
        return True
    if s == "nil" or s == "#f":
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def parse(text: str) -> list:
    """Top-level forms, each a nested Python list (symbols are plain strings)."""
    toks = tokenize(text)
    pos = 0

    def read():
        nonlocal pos
        if pos >= len(toks):
            raise FcadError("S1", "unexpected end of input")
        kind, val = toks[pos]
        pos += 1
        if kind in ("(", "["):
            out = []
            while True:
                if pos >= len(toks):
                    raise FcadError("S1", "unclosed parenthesis")
                if toks[pos][0] in (")", "]"):
                    pos += 1
                    return out
                out.append(read())
        if kind in (")", "]"):
            raise FcadError("S1", "unbalanced closing parenthesis")
        if kind == "str":
            return val
        s = val
        if s.startswith(":"):
            return ":" + s[1:]          # keyword marker
        return _atom(s)

    forms = []
    while pos < len(toks):
        forms.append(read())
    return forms


# ------------------------------------------------------------- utilities ---
def split_kwargs(form: list) -> tuple[list, dict]:
    """[(head) :k v :k2 v2 positional...] -> (positional, {k: v})."""
    positional, kwargs = [], {}
    rest = list(form)
    i = 0
    while i < len(rest):
        v = rest[i]
        if isinstance(v, str) and v.startswith(":"):
            if i + 1 >= len(rest):
                raise FcadError("S1", f"keyword {v} without a value")
            kwargs[v[1:]] = rest[i + 1]
            i += 2
        else:
            positional.append(v)
            i += 1
    return positional, kwargs


def _is_keyword(x) -> bool:
    return isinstance(x, str) and x.startswith(":")


# ---------------------------------------------------------------- bounds ---
def bound_from(cons: list, store=None):
    """One constraint sexpr -> bound. (>= 22) | (<= 50 :medium bus) | (= 28)."""
    if not cons or not isinstance(cons[0], str) or cons[0] not in (">=", "<=", "=", "<", ">"):
        raise FcadError("S1", f"bad bound constraint: {cons!r}")
    out = {"op": cons[0], "value": float(cons[1]) if len(cons) > 1 else None}
    if len(cons) > 2 and cons[2] == ":medium":
        ref = cons[3] if len(cons) > 3 else None
        out["medium"] = _resolve_ref(ref, store)
    if out["value"] is None:
        raise FcadError("S1", f"bound without a value: {cons!r}")
    return out


def _resolve_ref(ref, store):
    if ref is None or not isinstance(ref, str):
        return None
    if store is not None:
        try:
            return store.resolve(ref)
        except KeyError:
            return ref
    return ref


def bounds_map(pairs: list, store=None) -> dict:
    """((qty (>= a) (<= b)) ...) -> {qty: interval-or-op-bound}."""
    out = {}
    for entry in pairs:
        if not isinstance(entry, list) or not entry:
            raise FcadError("S1", f"bad qty/bounds entry: {entry!r}")
        qty, cons_list = entry[0], entry[1:]
        cons = [c for c in cons_list if isinstance(c, list)]
        if len(cons) == 1:
            out[qty] = bound_from(cons[0], store)
        else:
            iv: dict = {}
            medium = None
            for c in cons:
                b = bound_from(c, store)
                iv[b["op"] if b["op"] != "<" else "<="] = b["value"]
                medium = medium or b.get("medium")
            if medium:
                iv["medium"] = medium
            out[qty] = iv
    return out


# ----------------------------------------------------------------- specs ---
_CONTRACT_HEADS = {"goals": "goals", "semantics": "semantics", "assumes": "assumes",
                   "guarantees": "guarantees", "budget": "budget",
                   "effluent": "effluent", "forbidden": "forbidden",
                   "not-responsible": "not_responsible", "time-scale": "time_scale",
                   "param-bounds": "param_bounds", "param-checks": "param_checks"}


def spec_from_sexpr(sexpr, store=None) -> dict:
    """Build a node.spec dict from a spec sexpr (contract | medium | sketch | alist)."""
    if not isinstance(sexpr, list) or not sexpr:
        return _plain_value(sexpr, store)
    head = sexpr[0]
    if head == "contract":
        return _contract(sexpr[1:], store)
    if head == "medium":
        return _medium_spec(sexpr[1:], store)
    if head == "sketch":
        return {"sketch": _sketch(sexpr[1:])}
    return _alist(sexpr, store)


def _medium_spec(sections: list, store) -> dict:
    """(medium (capacity (power_w (<= 100))) (margin 0.2) (state ...) (degradation ...))
    -> {capacity: {...}, margin: float, state: {...}, degradation: {...}}  (v1.2 §19)"""
    out: dict = {"capacity": {}, "margin": 0.2, "state": {}, "degradation": {}}
    for sec in sections:
        if not isinstance(sec, list) or not sec:
            continue
        key = sec[0]
        if key == "capacity":
            out["capacity"] = bounds_map(sec[1:], store)
        elif key == "margin":
            out["margin"] = float(sec[1]) if len(sec) > 1 else 0.2
        elif key in ("state", "degradation"):
            out[key] = {e[0]: _plain_value(e[1], store)
                        for e in sec[1:] if isinstance(e, list) and len(e) == 2}
    return out


def _contract(sections: list, store) -> dict:
    spec: dict = {}
    for sec in sections:
        if not isinstance(sec, list) or not sec:
            raise FcadError("S1", f"bad contract section: {sec!r}")
        key = _CONTRACT_HEADS.get(sec[0])
        if key is None:
            spec[sec[0]] = _plain_value(sec[1:], store)   # extra slot, passed through
            continue
        body = sec[1:]
        if key == "semantics":
            digests = []
            for name in body:
                d = _resolve_term(name, store)
                if d is None:
                    raise FcadError("T2", f"term not registered: {name}")
                digests.append(d)
            spec[key] = digests
        elif key in ("goals", "assumes", "guarantees"):
            spec[key] = [_contract_entry(e, key, store) for e in body]
        elif key == "forbidden":
            spec[key] = [_forbidden_entry(e) for e in body]
        elif key in ("budget", "effluent"):
            spec[key] = bounds_map(body, store)
        elif key == "not_responsible":
            spec[key] = [v for v in body if isinstance(v, str)]
        elif key == "time_scale":
            spec[key] = body[0] if len(body) == 1 and isinstance(body[0], str) else \
                [v for v in body if isinstance(v, str)]
        elif key == "param_bounds":
            spec[key] = {q: iv for q, iv in bounds_map(body).items()}
        elif key == "param_checks":
            spec[key] = {e[0]: e[1] for e in body
                         if isinstance(e, list) and len(e) == 2}
    return spec


def _contract_entry(e, slot: str, store) -> dict:
    if not isinstance(e, list) or len(e) < 2:
        raise FcadError("S1", f"bad {slot} entry: {e!r}")
    entry = {"id": e[0], "stmt": e[1]}
    rest = e[2:]
    i = 0
    while i < len(rest):
        k = rest[i]
        if k == ":falsifiable":
            entry["falsifiable"] = bool(rest[i + 1])
            i += 2
        elif k == ":measure":
            entry["measure"] = rest[i + 1]
            i += 2
        elif k == ":bounds":
            entry["bounds"] = bounds_map(rest[i + 1], store)
            i += 2
        elif k == ":terms":
            terms = []
            for t in rest[i + 1]:
                d = _resolve_term(t, store)
                if d is None:
                    raise FcadError("T2", f"term not registered: {t}")
                terms.append(t)
            entry["terms"] = terms
            i += 2
        elif isinstance(k, str) and k.startswith(":"):
            entry[k[1:]] = _plain_value(rest[i + 1], store) if i + 1 < len(rest) else None
            i += 2
        else:
            i += 1
    return entry


def _forbidden_entry(e) -> dict:
    if not isinstance(e, list) or len(e) < 2:
        raise FcadError("S1", f"bad forbidden entry: {e!r}")
    pos, kw = split_kwargs(e)
    return {"id": pos[0], "stmt": pos[1],
            "check": kw.get("check", "inspection")}


def _resolve_term(name, store):
    if not isinstance(name, str):
        return None
    if name.startswith("fk1:"):
        return name
    if store is None:
        return None
    idx = store.names()
    d = idx.get(contracts.TERM_PREFIX + name)
    return d


def _sketch(body: list) -> dict:
    out = {"pts": {}, "constraints": []}
    for sec in body:
        if not isinstance(sec, list) or not sec:
            continue
        if sec[0] == "pts":
            for p in sec[1:]:
                if isinstance(p, list) and len(p) == 3:
                    out["pts"][p[0]] = [_plain_value(c, None) if isinstance(c, list)
                                        else c for c in p[1:]]
        elif sec[0] == "constraints":
            out["constraints"] = [list(c) for c in sec[1:] if isinstance(c, list)]
    return out


def _alist(sexpr: list, store) -> dict:
    """((k v) (k2 v2)) -> dict; falls back to {'<head>': [...]} shapes."""
    out = {}
    for e in sexpr[1:]:
        if isinstance(e, list) and len(e) >= 2 and isinstance(e[0], str) \
                and not e[0].startswith(":"):
            out[e[0]] = _plain_value(e[1], store) if len(e) == 2 else \
                [_plain_value(x, store) for x in e[1:]]
        else:
            return {str(sexpr[0]): [_plain_value(x, store) for x in sexpr[1:]]}
    return out


def _plain_value(v, store):
    if isinstance(v, list):
        if v and v[0] == "param":
            return ["param", v[1]] if len(v) > 1 else ["param", "?"]
        return [_plain_value(x, store) for x in v]
    return v


# --------------------------------------------------------------- printer ---
def to_sexpstr(v, indent: int = 0) -> str:
    if isinstance(v, list):
        if v and v[0] == "param":
            return f"(param {v[1]})"
        # keyword pairs render FLAT: [":k", val] -> ":k <val>" (DSL convention)
        if len(v) == 2 and isinstance(v[0], str) and v[0].startswith(":"):
            return f"{v[0]} {to_sexpstr(v[1])}"
        inner = " ".join(to_sexpstr(x) for x in v)
        return f"({inner})"
    if isinstance(v, bool):
        return "t" if v else "nil"
    if v is None:
        return "nil"
    if isinstance(v, str):
        if v.startswith("fk1:") or re.fullmatch(r"[\w./-]+", v):
            return v
        return json_quote(v)
    return str(v)


def json_quote(s: str) -> str:
    import json
    return json.dumps(s, ensure_ascii=False)


# --------------------------------------------------------- expect parser ---
_EXPECT_RE = re.compile(r"\s*([A-Za-z_][\w.-]*)\s*(>=|<=|>|<|=)\s*(-?\d+(?:\.\d+)?)")


def parse_expect(text: str) -> dict:
    """"range-margin>0, lift-to-drag>14" -> {"range-margin": [">", 0], ...}"""
    out = {}
    for m in _EXPECT_RE.finditer(text or ""):
        out[m.group(1)] = [m.group(2), float(m.group(3))]
    return out


def expect_from_sexpr(pairs: list) -> dict:
    """((range-margin-km (> 0)) ...) -> {"range-margin-km": [">", 0]}"""
    out = {}
    for e in pairs:
        if isinstance(e, list) and len(e) == 2 and isinstance(e[1], list):
            out[e[0]] = [e[1][0], float(e[1][1])]
    return out


def resources_from_sexpr(v) -> dict:
    """((:time-s 2.5) (:cost 0)) -> {"time_s": 2.5, "cost": 0}"""
    if not isinstance(v, list):
        return {}
    flat = []
    for e in v:
        if isinstance(e, list):
            flat.extend(e)
    pos, kw = split_kwargs(flat)
    return {k.replace("-", "_"): val for k, val in kw.items()}


def flowdown_from_sexpr(v, store) -> dict:
    """((wing :budget ((mass_g (<= 2200))) :guarantees ((gw1 ...))) ...) ->
    {slot: {"budget": {...}, "guarantees": [...], "assumes": [...]}}"""
    out = {}
    for e in v if isinstance(v, list) else []:
        if not isinstance(e, list) or not e:
            continue
        pos, kw = split_kwargs(e)
        slot = pos[0] if pos else None
        if slot is None:
            continue
        entry = {}
        if isinstance(kw.get("budget"), list):
            entry["budget"] = bounds_map(kw["budget"], store)
        if isinstance(kw.get("guarantees"), list):
            entry["guarantees"] = [_contract_entry(g, "guarantees", store)
                                   for g in kw["guarantees"] if isinstance(g, list)]
        if isinstance(kw.get("assumes"), list):
            entry["assumes"] = [_contract_entry(a, "assumes", store)
                                for a in kw["assumes"] if isinstance(a, list)]
        out[slot] = entry
    return out


def params_from_sexpr(v) -> dict:
    """((mtow (param mtow)) (ff 0.4)) -> {"mtow": ["param","mtow"], "ff": 0.4}"""
    out = {}
    for e in v if isinstance(v, list) else []:
        if isinstance(e, list) and len(e) == 2:
            out[e[0]] = _plain_value(e[1], None)
    return out


def pairs_to_map(v, store=None) -> dict:
    """((slot value) ...) -> {slot: plain} for roles/kinds maps."""
    out = {}
    for e in v if isinstance(v, list) else []:
        if isinstance(e, list) and len(e) == 2:
            out[e[0]] = _plain_value(e[1], store)
    return out
