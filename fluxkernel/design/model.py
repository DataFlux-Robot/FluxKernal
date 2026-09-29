"""Exact rational design DSL. No eval, arbitrary code, downloads or model calls.

The implemented mechanism semantics are point/bar distance constraints, not a
general rigid-body dynamics engine. CSG denotes point membership, not an SDF.
"""

from fractions import Fraction
import hashlib
import json
import re

SCHEMA = "fluxkernal-design-v1"
ZERO, LENGTH = (0, 0, 0), (1, 0, 0)
UNITS = {
    "1": (Fraction(1), ZERO),
    "m": (Fraction(1), LENGTH),
    "mm": (Fraction(1, 1000), LENGTH),
    "kg": (Fraction(1), (0, 1, 0)),
    "g": (Fraction(1, 1000), (0, 1, 0)),
    "s": (Fraction(1), (0, 0, 1)),
    "N": (Fraction(1), (1, 1, -2)),
    "Pa": (Fraction(1), (-1, 1, -2)),
}


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def rational(value):
    if type(value) not in (str, int) or len(str(value)) > 128:
        raise ValueError("Use bounded exact integer/decimal/fraction strings")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+|/\d+)?", str(value)):
        raise ValueError(
            "Use an integer, decimal or fraction; exponent notation is unsupported"
        )
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Invalid exact number") from exc
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 2048:
        raise ValueError("Exact number exceeds arithmetic budget")
    return result


def fields(record, expected):
    if not isinstance(record, dict) or set(record) != set(expected.split()):
        raise ValueError("Expected fields: " + expected)


def records(items):
    if not isinstance(items, list) or len(items) > 256:
        raise ValueError("Expected at most 256 records")
    result = {}
    for item in items:
        name = item.get("id") if isinstance(item, dict) else None
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_-]{0,63}", name
        ):
            raise ValueError("Invalid record ID")
        if name in result:
            raise ValueError("Duplicate record ID: " + name)
        result[name] = item
    return result


def const(value, unit="1"):
    return {"value": str(value), "unit": unit}


def op(name, a, b):
    return {"op": name, "args": [a, b]}


def square(a):
    return op("mul", a, a)


def distance_sq(a, b):
    terms = [square(op("sub", x, y)) for x, y in zip(a, b)]
    return op("add", op("add", terms[0], terms[1]), terms[2])


def atom(lhs, rhs, relation="le"):
    return {"lhs": lhs, "rhs": rhs, "relation": relation}


def combine(kind, predicates):
    result = predicates[0]
    for predicate in predicates[1:]:
        result = {kind: [result, predicate]}
    return result


class Design:
    def __init__(self, document):
        # Copy and cap the complete data input, including expression expansion.
        raw = canonical(document)
        if len(raw) > 2_000_000:
            raise ValueError("Design exceeds 2 MB")
        self.document = json.loads(raw)
        d = self.document
        fields(
            d,
            "schema name parameters points members shapes ports mates requirements probes",
        )
        if (
            d["schema"] != SCHEMA
            or not isinstance(d["name"], str)
            or not 0 < len(d["name"]) <= 128
        ):
            raise ValueError("Unsupported design schema or name")
        self.parameters = records(d["parameters"])
        self.points = records(d["points"])
        self.members = records(d["members"])
        self.shapes = records(d["shapes"])
        self.ports = records(d["ports"])
        self.clauses, self.predicates = [], []
        for p in self.parameters.values():
            fields(p, "id unit default lower upper")
            if p["unit"] not in UNITS:
                raise ValueError("Unknown parameter unit")
            lo, default, hi = (rational(p[k]) for k in ("lower", "default", "upper"))
            if not lo <= default <= hi:
                raise ValueError("Invalid parameter range: " + p["id"])
        for p in self.points.values():
            fields(p, "id position")
            self.vector(p["position"])
        for m in self.members.values():
            fields(m, "id a b length width thickness")
            if (
                m["a"] not in self.points
                or m["b"] not in self.points
                or m["a"] == m["b"]
            ):
                raise ValueError("Invalid member endpoints")
            for key in ("length", "width", "thickness"):
                self.dimension(m[key], LENGTH)
                self.clause(
                    "member:" + m["id"] + ":" + key,
                    "geometry",
                    const(0, "m"),
                    m[key],
                    "lt",
                )
            self.clause(
                "closure:" + m["id"],
                "kinematic",
                distance_sq(
                    self.points[m["a"]]["position"], self.points[m["b"]]["position"]
                ),
                square(m["length"]),
                "eq",
            )
        known = set()
        for s in d["shapes"]:
            kind = s.get("kind")
            if kind == "box":
                fields(s, "id kind lower upper")
                self.vector(s["lower"])
                self.vector(s["upper"])
                for i, (a, b) in enumerate(zip(s["lower"], s["upper"])):
                    self.clause(f"shape:{s['id']}:{i}", "geometry", a, b, "lt")
            elif kind in ("sphere", "cylinder"):
                fields(
                    s,
                    "id kind center radius" + (" height" if kind == "cylinder" else ""),
                )
                self.vector(s["center"])
                for key in ("radius", "height") if kind == "cylinder" else ("radius",):
                    self.dimension(s[key], LENGTH)
                    self.clause(
                        f"shape:{s['id']}:{key}",
                        "geometry",
                        const(0, "m"),
                        s[key],
                        "lt",
                    )
            elif kind in ("union", "intersection", "difference"):
                fields(s, "id kind a b")
                if s["a"] not in known or s["b"] not in known:
                    raise ValueError("CSG dependencies must precede their use")
            elif kind == "translate":
                fields(s, "id kind child offset")
                if s["child"] not in known:
                    raise ValueError("CSG dependencies must precede their use")
                self.vector(s["offset"])
            elif kind == "implicit":
                fields(s, "id kind lhs rhs relation")
                if s["relation"] not in ("eq", "le", "lt"):
                    raise ValueError("Unsupported implicit relation")
                if self.dimension(s["lhs"], coordinates=True) != self.dimension(
                    s["rhs"], coordinates=True
                ):
                    raise ValueError("Dimension mismatch in implicit field")
            else:
                raise ValueError("Unsupported shape kind")
            known.add(s["id"])
        for p in self.ports.values():
            fields(p, "id point diameter bolt_count")
            if (
                p["point"] not in self.points
                or type(p["bolt_count"]) is not int
                or not 1 <= p["bolt_count"] <= 256
            ):
                raise ValueError("Invalid port reference/count")
            self.dimension(p["diameter"], LENGTH)
            self.clause(
                "port:" + p["id"], "interface", const(0, "m"), p["diameter"], "lt"
            )
        for m in records(d["mates"]).values():
            fields(m, "id a b")
            if m["a"] not in self.ports or m["b"] not in self.ports or m["a"] == m["b"]:
                raise ValueError("Invalid mating ports")
            a, b = self.ports[m["a"]], self.ports[m["b"]]
            self.clause(
                "mate:" + m["id"] + ":diameter",
                "interface",
                a["diameter"],
                b["diameter"],
                "eq",
            )
            self.clause(
                "mate:" + m["id"] + ":count",
                "interface",
                const(a["bolt_count"]),
                const(b["bolt_count"]),
                "eq",
            )
            self.clause(
                "mate:" + m["id"] + ":position",
                "interface",
                distance_sq(
                    self.points[a["point"]]["position"],
                    self.points[b["point"]]["position"],
                ),
                square(const(0, "m")),
                "eq",
            )
        for r in records(d["requirements"]).values():
            fields(r, "id category lhs rhs relation")
            if r["category"] not in (
                "manufacturing",
                "kinematic",
                "interface",
                "performance",
            ):
                raise ValueError("Unsupported requirement category")
            self.clause(
                "requirement:" + r["id"],
                r["category"],
                r["lhs"],
                r["rhs"],
                r["relation"],
            )
        for p in records(d["probes"]).values():
            fields(p, "id shape point inside")
            if p["shape"] not in self.shapes or type(p["inside"]) is not bool:
                raise ValueError("Invalid geometry probe")
            self.vector(p["point"])
            predicate = self.membership(p["shape"], p["point"])
            if not p["inside"]:
                predicate = {"not": predicate}
            self.predicates.append({"id": p["id"], "predicate": predicate})
        if not self.clauses:
            raise ValueError("A design must declare checked obligations")
        if len(canonical([self.clauses, self.predicates])) > 4_000_000:
            raise ValueError("Expanded constraints exceed 4 MB")

    def dimension(self, expr, expected=None, depth=0, coordinates=False):
        if depth > 48 or not isinstance(expr, dict):
            raise ValueError("Invalid or overly deep expression")
        if set(expr) == {"coord"}:
            if (
                not coordinates
                or type(expr["coord"]) is not int
                or expr["coord"] not in (0, 1, 2)
            ):
                raise ValueError("Coordinates are scoped to implicit shape definitions")
            result = LENGTH
        elif set(expr) == {"param"}:
            if expr["param"] not in self.parameters:
                raise ValueError("Unknown parameter")
            result = UNITS[self.parameters[expr["param"]]["unit"]][1]
        elif set(expr) == {"value", "unit"}:
            rational(expr["value"])
            if expr["unit"] not in UNITS:
                raise ValueError("Unknown unit")
            result = UNITS[expr["unit"]][1]
        else:
            fields(expr, "op args")
            if (
                expr["op"] not in ("add", "sub", "mul", "div")
                or not isinstance(expr["args"], list)
                or len(expr["args"]) != 2
            ):
                raise ValueError("Invalid expression operation")
            a, b = [
                self.dimension(e, depth=depth + 1, coordinates=coordinates)
                for e in expr["args"]
            ]
            if expr["op"] in ("add", "sub"):
                if a != b:
                    raise ValueError("Dimension mismatch in addition/subtraction")
                result = a
            else:
                sign = 1 if expr["op"] == "mul" else -1
                result = tuple(x + sign * y for x, y in zip(a, b))
        if expected is not None and result != expected:
            raise ValueError("Dimension mismatch")
        return result

    def vector(self, values):
        if not isinstance(values, list) or len(values) != 3:
            raise ValueError("Expected a three-component position")
        for value in values:
            self.dimension(value, LENGTH)

    def clause(self, name, category, lhs, rhs, relation):
        if relation not in ("eq", "le", "lt"):
            raise ValueError("Unsupported relation")
        if self.dimension(lhs) != self.dimension(rhs):
            raise ValueError("Dimension mismatch in obligation: " + name)
        self.clauses.append(
            {"id": name, "category": category, **atom(lhs, rhs, relation)}
        )

    def environment(self, overrides=None):
        overrides = overrides or {}
        if set(overrides) - set(self.parameters):
            raise ValueError("Unknown parameter override")
        env = {}
        for name, p in self.parameters.items():
            v = rational(overrides.get(name, p["default"]))
            if not rational(p["lower"]) <= v <= rational(p["upper"]):
                raise ValueError("Parameter outside declared range: " + name)
            env[name] = v * UNITS[p["unit"]][0]
        return env

    def evaluate(self, expr, env):
        if "param" in expr:
            return env[expr["param"]]
        if "value" in expr:
            return rational(expr["value"]) * UNITS[expr["unit"]][0]
        a, b = [self.evaluate(e, env) for e in expr["args"]]
        if expr["op"] == "add":
            result = a + b
        elif expr["op"] == "sub":
            result = a - b
        elif expr["op"] == "mul":
            result = a * b
        else:
            if b == 0:
                raise ValueError("Division by zero")
            result = a / b
        if max(result.numerator.bit_length(), result.denominator.bit_length()) > 8192:
            raise ValueError("Expression exceeds arithmetic budget")
        return result

    def membership(self, name, point, depth=0, budget=None):
        budget = [4096] if budget is None else budget
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError("CSG expansion exceeds node budget")
        if depth > 24:
            raise ValueError("CSG expansion exceeds depth budget")
        s = self.shapes[name]
        kind = s["kind"]
        if kind == "implicit":

            def substitute(expr):
                if "coord" in expr:
                    return point[expr["coord"]]
                if "op" in expr:
                    return op(expr["op"], *(substitute(x) for x in expr["args"]))
                return expr

            return atom(substitute(s["lhs"]), substitute(s["rhs"]), s["relation"])
        if kind == "box":
            return combine(
                "and",
                [
                    p
                    for lo, x, hi in zip(s["lower"], point, s["upper"])
                    for p in (atom(lo, x), atom(x, hi))
                ],
            )
        if kind in ("sphere", "cylinder"):
            if kind == "sphere":
                return atom(distance_sq(point, s["center"]), square(s["radius"]))
            delta = [op("sub", a, b) for a, b in zip(point, s["center"])]
            radial = atom(
                op("add", square(delta[0]), square(delta[1])), square(s["radius"])
            )
            return {
                "and": [
                    radial,
                    atom(square(delta[2]), square(op("div", s["height"], const(2)))),
                ]
            }
        if kind == "translate":
            return self.membership(
                s["child"],
                [op("sub", x, y) for x, y in zip(point, s["offset"])],
                depth + 1,
                budget,
            )
        a, b = [self.membership(s[k], point, depth + 1, budget) for k in ("a", "b")]
        if kind == "difference":
            return {"and": [a, {"not": b}]}
        return {"or" if kind == "union" else "and": [a, b]}

    def predicate(self, p, env):
        if "lhs" in p:
            a, b = self.evaluate(p["lhs"], env), self.evaluate(p["rhs"], env)
            return {"eq": a == b, "le": a <= b, "lt": a < b}[p["relation"]]
        if "not" in p:
            return not self.predicate(p["not"], env)
        key = "and" if "and" in p else "or"
        # Evaluate both branches: invalid arithmetic cannot hide in a branch.
        values = [self.predicate(x, env) for x in p[key]]
        return all(values) if key == "and" else any(values)

    def check(self, overrides=None):
        env = self.environment(overrides)
        results = []
        for c in self.clauses:
            a, b = self.evaluate(c["lhs"], env), self.evaluate(c["rhs"], env)
            passed = self.predicate(c, env)
            results.append(
                {
                    "id": c["id"],
                    "category": c["category"],
                    "passed": passed,
                    "lhs_si": str(a),
                    "rhs_si": str(b),
                    "residual_si": str(a - b),
                }
            )
        for p in self.predicates:
            results.append(
                {
                    "id": "probe:" + p["id"],
                    "category": "geometry-membership",
                    "passed": self.predicate(p["predicate"], env),
                }
            )
        # Cyclomatic number of the undirected member graph, including isolates.
        groups = {k: k for k in self.points}

        def root(k):
            while groups[k] != k:
                k = groups[k]
            return k

        for m in self.members.values():
            groups[root(m["a"])] = root(m["b"])
        components = len({root(k) for k in groups})
        positions = {
            name: [str(self.evaluate(x, env)) for x in p["position"]]
            for name, p in self.points.items()
        }
        return {
            "schema": "fluxkernal-design-check-v1",
            "design_sha256": digest(self.document),
            "accepted": all(x["passed"] for x in results),
            "model_calls": 0,
            "parameters_si": {k: str(v) for k, v in env.items()},
            "positions_si": positions,
            "independent_cycles": len(self.members) - len(groups) + components,
            "checks": results,
            "proof": "not-run",
            "scope": "declared exact-rational instance",
            "not_proven": [
                "continuous dynamics",
                "global collision freedom",
                "material strength",
                "manufacturing process feasibility",
                "all parameter values",
            ],
        }
