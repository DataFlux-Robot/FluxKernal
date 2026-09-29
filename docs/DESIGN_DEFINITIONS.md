# Executable design definitions

FluxKernal adds a **checked design-definition layer** alongside its existing
URDF ↔ Lean document exchange. `fk design` owns the new `fluxkernal-design-v1`
schema; `fk robot to-lean` and `fk robot from-lean` retain their existing behavior.
Extended designs are not silently projected into URDF, MJCF, USD or SDFormat.

The implemented advantage is explicit design relationships and locally replayable
proof obligations. It is not a claim to have replaced these ecosystems or to be a
strict expressive superset of extensible formats such as USD.

## What runs today

| Definition | Executed semantics | Demonstration |
| --- | --- | --- |
| Closed member graph | Exact squared endpoint distance equals declared bar length squared; cycles allowed | Four-bar linkage, one independent cycle |
| Dimensioned parameters | Exact rationals, SI conversion, length/mass/time dimensional analysis, declared bounds | Reject adding metres to seconds; `6 mm = 0.006 m` |
| Derived geometry | Parameters remain expressions, not just baked coordinates | One phase parameter moves linked points and preserves rod lengths |
| Implicit geometry | Analytic inequalities in scoped x/y/z coordinates, plus sphere, box, z-axis cylinder, translation and CSG | Quartic torus and a plate with a cylindrical bore |
| Assembly interfaces | Port location, diameter and bolt-count compatibility | Reject an 8 mm mount paired with a 6 mm interface |
| Design requirements | Equality and order constraints classified by purpose | Reject insufficient thickness and excessive declared nominal axial stress |
| Checked evidence | Real Lean kernel reevaluates exact expressions and membership predicates | Modified dimensions, inputs, proof files or receipts invalidate the corresponding certificate |
| Parametric family theorem | Universally quantified rational algebra, under an explicit unit-circle assumption | Four bar lengths for every member of the declared parallelogram family |

Point/bar constraints do not yet supply arbitrary 3D rigid-body joints, constraint
solving, reaction forces, actuation, branch selection or continuous dynamics. Ports
check the listed attributes; orientation, thread standards and detailed bolt
patterns are not implied. The stress check uses the declared `force / area` formula;
it does not certify the material or the real loading condition.

## Try it offline

Install FluxKernal and the pinned Lean toolchain once, then:

```bash
fk design example --output fourbar.json
fk design check fourbar.json
fk design certify fourbar.json --output certificate
fk design verify certificate --design fourbar.json

# This intentionally exits nonzero: a manufacturing requirement is violated.
fk design check fourbar.json --param thickness=2

# This intentionally exits nonzero: the certificate is for different inputs.
fk design verify certificate --design fourbar.json --param phase=3/4

# Generates self-contained HTML, five real Lean certificates and 15 rejected cases.
fk design demo --output design-demo
```

Open `design-demo/index.html` locally. The controls select five recorded rational
configurations and four design modes; they do not invoke a model or a server.
The display is a 2D view of the example and a plate cross-section, not a general
CAD renderer. The torus definition and membership probes are in the source/evidence.
`check` runs exact Python arithmetic; `certify` and `verify` require real Lean.

On Linux, enforce no networking in the command and its child processes:

```bash
python scripts/without_network.py fk design demo --output design-demo-offline
```

The installed compiler is invoked directly. The design commands do not launch
Elan/Lake, download resources or call a model API. Existing URDF conversion remains
separate:

```bash
fk robot to-lean robot.urdf --output robot-lean
fk robot from-lean robot-lean --output robot-restored
```

The existing asset/URI compatibility boundaries still apply. Native v1 robot
imports still reject unsupported equality loops. New closed member graphs live in
the design layer; there is no new claim that ordinary URDF carries them.

## Data and expression semantics

Generate `fourbar.json` to see every required field. Unknown fields, duplicate
record identities, malformed expressions, unsupported units and dangling references
are errors; they are not silently discarded.

The top-level fields are `schema`, `name`, `parameters`, `points`, `members`,
`shapes`, `ports`, `mates`, `requirements`, and `probes`. Parameters declare an ID,
unit, default and inclusive lower/upper bounds. Numbers are integer, decimal or
fraction strings; binary floats and exponent notation are rejected. Overrides use
the declared parameter unit, so `--param thickness=2` means 2 mm in this example.

```json
{"value": "6", "unit": "mm"}
{"param": "thickness"}
{"op": "mul", "args": [{"param": "width"}, {"param": "thickness"}]}
```

The four binary operations are `add`, `sub`, `mul`, and `div`. Addition/subtraction
require identical dimensions. Multiplication/division compose dimensions. Division
by zero is rejected, including inside negated/otherwise satisfied geometry
predicates. Supported unit spellings: `1`, `m`, `mm`, `kg`, `g`, `s`, `N`, `Pa`.
All values normalize to exact rational SI quantities.

Point positions have three length expressions. A member names two distinct points
and length/width/thickness expressions. Positive sizes and exact distance closure
are automatic obligations. The schema accepts cycles in this member graph while
requiring the CSG dependency graph to be acyclic.

An implicit shape uses `lhs`, `rhs`, and `relation` (`eq`, `le`, or `lt`). Only
within those expressions, `{"coord": 0}`, `{"coord": 1}`, and `{"coord": 2}`
denote local x/y/z, each with length dimension. Coordinate substitution creates the
same checked expression language used for other obligations. For example the torus
is defined directly by:

\[
(x^2+y^2+z^2+R^2-r^2)^2 \leq 4R^2(x^2+y^2).
\]

This is an **implicit membership field**, not a signed-distance field. CSG union,
intersection and difference implement logical OR, AND and AND-NOT; difference
removes the boundary of its subtracted operand. Primitive boundaries are included.
There is no tessellation, topology, smoothness or global collision certificate.
Lean checks the specified point probes, not every point in space. Rational fields
may be undefined at some coordinates; undefined probes fail, and global field
totality is not currently established.

## What the Lean proof actually says

The installed [Design.lean](../formal/FluxKernel/Design.lean) module defines:

- Dimensioned expressions and an exact rational evaluator.
- Parameter bounds, equalities/inequalities and geometric predicates.
- `check_sound`: an accepted compiled instance satisfies its declared obligations.
- `parallelogram_family`: for all rational `a,b,u,v` with `u²+v²=1`, points
  `(0,0)`, `(a,0)`, `(a+b*u,b*v)` and `(b*u,b*v)` have squared bar lengths
  `a²,b²,a²,b²` respectively.

Instance certificates use `by decide +kernel`, not supplied success flags or
`native_decide`. The family theorem uses Lean's `grind` proof tactic. Their recorded
axiom dependencies are the usual `propext`, `Classical.choice`, and `Quot.sound`;
they do not use `sorryAx` or `Lean.ofReduceBool`.

The family theorem is a separate reusable lemma. It does not automatically prove
arbitrary designs correct, nor prove every parameter override nonsingular or safe.
The example's rational phase parameterization is checked at each certified frame;
the five certificates are not a continuum motion proof.

**Trust boundary:** JSON parsing, schema checks, elaboration into Lean expressions
and source-hash binding are implemented in Python and are not yet formally proved.
Lean verifies the generated expression instance. `verify` regenerates that instance,
recomputes the design checks and reruns Lean, instead of trusting stored status bits
or executing a supplied `.lean` file. The certificate is content-bound evidence,
not an authenticated author signature. Re-certification can establish new evidence
for a new design; it cannot make an old certificate apply to changed inputs.

## Relationship to other formats

Here SDF means **SDFormat**, the robotics scene format; signed-distance fields are
a separate geometric concept.

| Ecosystem | Existing strengths acknowledged | Added FluxKernal layer in this release |
| --- | --- | --- |
| URDF | Robot link/joint trees, inertial and geometry exchange | Cyclic member definitions, derived dimensional relationships and checked requirements |
| MuJoCo / MJCF | Dynamics, equality/loop constraints, tendons, contacts and simulation-oriented modeling | Design/manufacturing/interface obligations and replayable exact Lean certificates, independent of a simulation run |
| OpenUSD | Broad geometry schemas, composition, instancing, variants, relationships and extensibility | An explicit checked design DSL connecting parameters, implicit sets and declared engineering requirements |
| SDFormat | Robots/worlds, geometry, joints, sensors, physics and plugins | The same design-obligation and evidence layer, with no SDFormat backend claimed |

These systems can be extended with additional schemas, plugins or external
validators. Consequently this table is not a proof of exclusive representability
or a strict language hierarchy. FluxKernal does not currently match their complete
geometry coverage, simulation fidelity, scene composition or ecosystem support.

Primary references: [MuJoCo equality constraints](https://mujoco.readthedocs.io/en/stable/computation/index.html#equality),
[MJCF reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html),
[OpenUSD introduction and extensibility](https://openusd.org/release/intro.html),
[SDFormat specification](https://sdformat.org/spec/).

## Next boundaries to implement

General rigid-body/frame constraints and a numerical solver; backend-specific
MJCF/USD/SDFormat projections with explicit loss ledgers; CAD/mesh realization of
implicit fields; formally verified elaboration and certified interval reasoning
over parameter domains. Existing exchange guarantees must retain their regression
gates as these are introduced.
