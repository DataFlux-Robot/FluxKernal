"""L1: parameter system — expression evaluation + single-source bindings.

Deliberately NOT Turing-complete: arithmetic (+ - * /), min/max/sqrt/abs/
ceil/floor and a terminating `if` only.  Anything richer belongs in a
policy or a mechanism generator, never here.

Single source rule: every parameter has exactly one definition —
  (a) the node's own `params` dict,
  (b) a parent's flow-down, or
  (c) a named parameter-set node referenced by path ("wing/span").
Contract-bound midpoints are NOT definitions (they stay solver surrogates
inside sketch2d).  No global variables.

Every numeric leaf a transform consumes resolves through `resolve_*` here,
and every resolution emits a param-bindings evidence entry
{param, expr, value, source} — each number in the DAG traces back to its
definition (Lean: every term traces to an axiom or hypothesis).
"""
from __future__ import annotations

import math

from .objects import Node


class ParamError(ValueError):
    """Carries a repair hint: which parameter, why it failed, what to fix."""


# --------------------------------------------------------------- language --
def _op_add(*a):
    return sum(a)


def _op_sub(a, b):
    return a - b


def _op_mul(*a):
    v = 1.0
    for x in a:
        v *= x
    return v


def _op_div(a, b):
    if b == 0:
        raise ParamError("division by zero in parameter expression")
    return a / b


EXPR_OPS = {
    "+": _op_add, "-": _op_sub, "*": _op_mul, "/": _op_div,
    "min": lambda *a: min(a), "max": lambda *a: max(a),
    "sqrt": math.sqrt, "abs": abs, "ceil": math.ceil, "floor": math.floor,
    "if": lambda c, a, b: a if c else b,
}

_PATOMIC = (int, float)


def expr_text(sexp) -> str:
    """Canonical text of an expression/atom for the bindings evidence."""
    if isinstance(sexp, _PATOMIC) and not isinstance(sexp, bool):
        return f"{float(sexp):g}"
    if isinstance(sexp, str):
        return sexp
    if isinstance(sexp, (list, tuple)):
        return "(" + " ".join(expr_text(x) for x in sexp) + ")"
    return repr(sexp)


def collect_refs(sexp, out: set | None = None) -> set:
    """All parameter names an expression tree references."""
    out = set() if out is None else out
    if isinstance(sexp, str):
        out.add(sexp)
    elif isinstance(sexp, (list, tuple)):
        for x in sexp:
            collect_refs(x, out)
    return out


def eval_sexp(sexp, lookup):
    """Evaluate an expression tree.  Strings are parameter references —
    the DSL's bare symbols (chord, wing/span) resolve via `lookup`."""
    if isinstance(sexp, (list, tuple)) and len(sexp) == 2             and sexp[0] in ("expr", ":expr"):
        return eval_sexp(sexp[1], lookup)
    if isinstance(sexp, bool):
        return 1.0 if sexp else 0.0
    if isinstance(sexp, _PATOMIC):
        return float(sexp)
    if isinstance(sexp, str):
        v = lookup(sexp)
        if v is None:
            raise ParamError(f"unknown parameter {sexp!r} — declare it on "
                             f"the node params, a parent, or a params set")
        return float(v)
    if isinstance(sexp, (list, tuple)) and sexp:
        head = sexp[0]
        if isinstance(head, str) and head in EXPR_OPS and head not in ("abs",):
            args = [eval_sexp(a, lookup) for a in sexp[1:]]
            try:
                return float(EXPR_OPS[head](*args))
            except ParamError:
                raise
            except Exception as e:
                raise ParamError(f"eval error in {expr_text(sexp)}: {e}")
        raise ParamError(f"not an expression: {expr_text(sexp)} "
                         f"(head {head!r} not in {sorted(EXPR_OPS)})")
    raise ParamError(f"bad expression atom: {sexp!r}")


# ------------------------------------------------------ single definitions --
def resolve_param_values(defs: dict) -> dict:
    """Resolve a params dict in dependency order.  Values may be numbers,
    ["param", name] or ["expr", [...]].  Cycles raise ParamError naming
    the cycle (repair hint)."""
    defs = dict(defs or {})
    graph = {}
    for k, v in defs.items():
        if isinstance(v, (list, tuple)) and v and v[0] in ("param", ":param"):
            src = v[1] if len(v) > 1 else k
            graph[k] = set() if src == k else {src}   # self-ref = a hole
        elif isinstance(v, (list, tuple)):
            graph[k] = collect_refs(v)
        else:
            graph[k] = set()

    values: dict = {}
    state = {}          # name -> 0 visiting, 1 done

    def visit(name, stack):
        if state.get(name) == 1:
            return
        if state.get(name) == 0:
            cycle = stack[stack.index(name):] + [name]
            raise ParamError("param-cycle: " + " -> ".join(cycle) +
                             " — reparameterize one of them")
        state[name] = 0
        v = defs.get(name)
        if v is None:
            state[name] = 1
            return  # external reference, resolved by lookup at use time
        for dep in sorted(graph.get(name, ())):
            if dep in defs:
                visit(dep, stack + [name])
        if isinstance(v, (list, tuple)) and v and v[0] in ("param", ":param"):
            src = v[1] if len(v) > 1 else name
            if src == name:
                state[name] = 1
                return  # definition hole (sorry): stays unresolved by design
            values[name] = float(values[src])
        elif isinstance(v, (list, tuple)):
            values[name] = eval_sexp(v, lambda n: values.get(n))
        elif isinstance(v, _PATOMIC) and not isinstance(v, bool):
            values[name] = float(v)
        else:
            values[name] = v
        state[name] = 1

    for name in sorted(defs):
        visit(name, [])
    return values


# ------------------------------------------------------------- resolution --
def make_lookup(payload: dict, store, resolved_local: dict):
    """name -> value, in single-source order: local node params, then
    path refs ("<params-node>/<key>") resolved through the store."""
    def lookup(name: str):
        if name in resolved_local:
            v = resolved_local[name]
            return v if isinstance(v, _PATOMIC) else None
        if "/" in name and store is not None:
            node_name, key = name.split("/", 1)
            try:
                p = store.get_object(store.resolve(node_name))["payload"]
            except KeyError:
                raise ParamError(f"unknown params set {node_name!r} "
                                 f"(in {name!r})")
            v = (p.get("params") or {}).get(key)
            if v is None:
                raise ParamError(f"params set {node_name!r} has no {key!r}")
            if isinstance(v, _PATOMIC):
                return float(v)
            vals = resolve_param_values({key: v})
            return vals.get(key)
        return None
    return lookup


def resolve_deep(value, lookup, bindings: list, seen: set, depth: int = 0):
    """Recursively replace param/expr forms with numbers, in place-safe
    (returns a new structure).  Records bindings as (name, expr, value)."""
    if depth > 32:
        raise ParamError("parameter nesting too deep (max 32)")
    if isinstance(value, (list, tuple)):
        if value and value[0] in ("param", ":param"):
            name = value[1] if len(value) > 1 else "?"
            v = lookup(name)
            if v is not None:
                key = (name, "param")
                if key not in seen:
                    seen.add(key)
                    bindings.append({"param": name, "expr": name,
                                     "value": float(v), "source": "params"})
                return float(v)
            return list(value)          # unresolved hole → solver territory
        if value and value[0] in ("expr", ":expr"):
            v = eval_sexp(value[1], lookup)
            txt = expr_text(value[1])
            key = ("expr", txt)
            if key not in seen:
                seen.add(key)
                bindings.append({"param": "", "expr": txt,
                                 "value": float(v), "source": "expr"})
            return float(v)
        return [resolve_deep(v, lookup, bindings, seen, depth + 1)
                for v in value]
    if isinstance(value, dict):
        return {k: resolve_deep(v, lookup, bindings, seen, depth + 1)
                for k, v in value.items()}
    return value


def resolve_transform(transform: dict, payload: dict, store):
    """Resolve a transform's args against the input node's parameter
    context.  Returns (new_transform, bindings).  Definition-carrying
    transforms (param-perturb) must NOT be routed through here."""
    local = resolve_param_values(payload.get("params") or {})
    lookup = make_lookup(payload, store, local)
    bindings: list = []
    seen: set = set()
    args = transform.get("args") or {}
    resolved = resolve_deep(args, lookup, bindings, seen)
    return {**transform, "args": resolved}, bindings


def bindings_evidence(bindings: list) -> list:
    if not bindings:
        return []
    return [{"solver": "core/params", "tier": 0,
             "param-bindings": bindings}]


# ----------------------------------------------------------- params nodes --
def params_node_payload(name: str, defs: dict) -> dict:
    """A named parameter set is an ordinary content-addressed node
    (kind=params); path references ('wing/span') resolve through it."""
    return {"kind": "params", "params": dict(defs or {}), "spec": {}}
