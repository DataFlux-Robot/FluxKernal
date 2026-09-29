"""Constructive examples; all geometry and checks come from these expressions."""

from .model import SCHEMA, const, op, square


def fourbar():
    def p(name):
        return {"param": name}

    t, a, b = p("phase"), p("span"), p("crank")
    denominator = op("add", const(1), square(t))
    u = op("div", op("sub", const(1), square(t)), denominator)
    v = op("div", op("mul", const(2), t), denominator)
    x, y = op("mul", b, u), op("mul", b, v)
    zero = const(0, "m")
    # Quartic implicit torus: (x²+y²+z²+R²-r²)² ≤ 4 R² (x²+y²).
    radial = op("add", square({"coord": 0}), square({"coord": 1}))
    major, minor = const(10, "mm"), op("div", p("pin"), const(2))
    torus_lhs = square(
        op(
            "sub",
            op("add", op("add", radial, square({"coord": 2})), square(major)),
            square(minor),
        )
    )
    torus_rhs = op("mul", op("mul", const(4), square(major)), radial)
    parameters = [
        ("phase", "1", "1/2", "1/10", "2"),
        ("span", "mm", "120", "80", "200"),
        ("crank", "mm", "60", "30", "75"),
        ("width", "mm", "10", "2", "20"),
        ("thickness", "mm", "4", "1", "10"),
        ("pin", "mm", "6", "2", "12"),
        ("load", "N", "5", "0", "100"),
    ]
    members = [
        ("base", "A", "B", a),
        ("input", "A", "D", b),
        ("coupler", "D", "C", a),
        ("output", "B", "C", b),
    ]

    def requirement(name, category, lhs, rhs, relation="le"):
        return {
            "id": name,
            "category": category,
            "lhs": lhs,
            "rhs": rhs,
            "relation": relation,
        }

    return {
        "schema": SCHEMA,
        "name": "Proof-carrying four-bar and mounting plate",
        "parameters": [
            dict(zip(("id", "unit", "default", "lower", "upper"), row))
            for row in parameters
        ],
        "points": [
            {"id": name, "position": position}
            for name, position in (
                ("A", [zero, zero, zero]),
                ("B", [a, zero, zero]),
                ("D", [x, y, zero]),
                ("C", [op("add", a, x), y, zero]),
            )
        ],
        "members": [
            {
                "id": name,
                "a": start,
                "b": end,
                "length": length,
                "width": p("width"),
                "thickness": p("thickness"),
            }
            for name, start, end, length in members
        ],
        "shapes": [
            {
                "id": "blank",
                "kind": "box",
                "lower": [const(-15, "mm"), const(-15, "mm"), zero],
                "upper": [const(15, "mm"), const(15, "mm"), p("thickness")],
            },
            {
                "id": "bore",
                "kind": "cylinder",
                "center": [zero, zero, zero],
                "radius": op("div", p("pin"), const(2)),
                "height": const(30, "mm"),
            },
            {"id": "plate", "kind": "difference", "a": "blank", "b": "bore"},
            {
                "id": "implicit_torus",
                "kind": "implicit",
                "lhs": torus_lhs,
                "rhs": torus_rhs,
                "relation": "le",
            },
        ],
        "ports": [
            {"id": "base_mount", "point": "A", "diameter": p("pin"), "bolt_count": 4},
            {
                "id": "plate_mount",
                "point": "A",
                "diameter": const(6, "mm"),
                "bolt_count": 4,
            },
        ],
        "mates": [{"id": "mount", "a": "base_mount", "b": "plate_mount"}],
        "requirements": [
            requirement("minimum_width", "manufacturing", const(8, "mm"), p("width")),
            requirement(
                "minimum_thickness", "manufacturing", const(3, "mm"), p("thickness")
            ),
            requirement(
                "mount_edge_margin",
                "manufacturing",
                op("add", op("div", p("pin"), const(2)), const(3, "mm")),
                const(15, "mm"),
            ),
            requirement(
                "nominal_axial_stress",
                "performance",
                op("div", p("load"), op("mul", p("width"), p("thickness"))),
                const(2_000_000, "Pa"),
            ),
            requirement("above_dead_center", "kinematic", const(1, "mm"), y, "lt"),
            requirement(
                "circle_parameterization",
                "kinematic",
                op("add", square(u), square(v)),
                const(1),
                "eq",
            ),
        ],
        "probes": [
            {
                "id": "torus_center_is_empty",
                "shape": "implicit_torus",
                "point": [zero, zero, zero],
                "inside": False,
            },
            {
                "id": "torus_ring_has_material",
                "shape": "implicit_torus",
                "point": [const(10, "mm"), zero, zero],
                "inside": True,
            },
            {
                "id": "bore_is_empty",
                "shape": "plate",
                "point": [zero, zero, const(1, "mm")],
                "inside": False,
            },
            {
                "id": "plate_has_material",
                "shape": "plate",
                "point": [const(10, "mm"), zero, const(1, "mm")],
                "inside": True,
            },
        ],
    }
