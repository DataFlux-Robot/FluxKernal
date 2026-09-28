# URDF import and Lean translation validation (v0.11)

The supported round trip is **URDF → native robot → checked URDF/MJCF**.
Lean checks the native structure and selected mechanism fields extracted from the
actual URDF output. `robot.json` remains the design authority. A `.lean` instance
alone is not a complete robot model and cannot reconstruct its meshes or frames.

## Use

```bash
python -m pip install -e '.[robot]'
fk robot import-urdf ./robot.urdf --output ./robot-runs --require-proof
# package:// references require explicit local resolution; no network fetching:
fk robot import-urdf ./robot.urdf --package my_description=/path/to/my_description \
  --output ./robot-runs --require-proof
fk robot inspect ./robot-runs/urdf-<id>
fk robot verify ./robot-runs/urdf-<id> --require-proof
fk robot check-projection ./robot-runs/urdf-<id>
```

Import automatically checks the native representation, generates both exchange
formats, attempts both real Lean proofs, and compares independent numerical FK with
MuJoCo consumers at three configurations. Consumer errors or failed comparisons abort
import and remove its incomplete directory. `--require-proof` additionally requires
Lean to succeed; an unavailable Lean installation is never reported as a proof.

A successful bundle contains `robot.json`, `robot.urdf`, `robot.xml`, `gen_urdf.py`,
`proof/RobotInstance.lean`, `proof/UrdfInstance.lean`, `exchange-proof.json`,
`projection-check.json`, source snapshots and content-addressed kernel objects.
`urdf-import.json` records losses and assumptions. Source files are provenance;
regeneration and native revisions do not reload the original URDF as authority.

## Supported import subset and design ledger

| Property | Handling |
| --- | --- |
| Units | URDF SI: metres, radians, kilograms, seconds, kg·m² |
| Structure | A single connected tree, 1–256 links |
| Joints | Fixed, revolute, continuous, prismatic; fixed joint names retained |
| Frames | Parent-local URDF xyz/RPY becomes native xyz/wxyz; joint anchor and reference start at zero |
| Axes | In joint/child frame; finite unit vectors required, no silent renormalization |
| Limits | Position, effort and velocity retained; continuous joints have no invented position bounds |
| Dynamics | Declared damping and friction retained; no actuator law inferred |
| Inertia | Explicit mass, COM and full symmetric inertia; principal-axis decomposition preserves the tensor numerically |
| Appearance / collision | Separate occurrences with independent origins; box, sphere, cylinder and triangle mesh |
| Mesh | Local triangular OBJ, binary/ASCII STL; positive scale baked into metre coordinates |
| Reuse | Identical resulting triangle assets share one native mesh; occurrences remain separate |
| Materials | Inline or named RGBA; textures and material-library semantics unsupported |
| References | Relative meshes confined to the URDF directory; package URIs confined to an explicit mapped root |
| Unspecified simulation values | `.002 s` timestep, `[0,0,-9.81]` gravity and placeholder collision friction, recorded as assumptions |

Geometry-bearing or movable links must have explicit positive-mass inertials. An
empty fixed frame may omit inertials; no density or mass is invented from its shape.
The importer does not infer actuator inventory, controller action order, a policy,
sensor semantics or manufacturing BOM. `deployment_ready=false` remains mandatory.

This adapter deliberately rejects mimic, floating/planar joints, transmissions,
closed loops, Gazebo/ROS extensions, xacro, unknown attributes/elements, unresolved
package URIs, remote meshes, textures and OBJ polygon faces. Expand xacro/triangulate
geometry explicitly first. Rename a link named `world` explicitly: MuJoCo reserves
that name and treats a URDF world frame specially. Path-like robot names are rejected.
Meshes are capped at 64 MiB each; XML at 16 MiB, with DTD/entities and NUL encodings
rejected. A rejected construct is a current adapter limitation, not a claim that
otherwise-valid URDF is invalid.

XML formatting and geometry/material occurrence names are not retained as semantics.
OBJ normals/UV and STL normals are dropped; indexed triangle geometry is retained.
Numeric import uses finite binary64 values, so the original decimal spelling is not
a lossless round-trip promise. Source bytes and mesh scale provenance are retained.

## What the new Lean certificate establishes

`formal/FluxKernel/Urdf.lean` defines a finite exact relation between independently
extracted native records and records parsed from the actual exported XML. A concrete
`by decide` proof and the checker's soundness theorem establish:

- the same link names and declared mass;
- the same joint names, parent/child links and joint types;
- preservation of each nonzero three-component joint axis;
- ordered finite bounds shifted by the native reference coordinate;
- preservation of declared effort/velocity values, with unknown values mapped to zero.

Decimal literals become exact rationals. Limit serialization subtracts decimal values
exactly, rather than rounding binary floating-point subtraction before certification.
For example native `[0.1, 0.3]` with reference `0.2` exports `[-0.1, 0.1]` exactly.
No `sorry` or `native_decide` is used. Tests execute Lean on changed output records
and require rejection; checking a copied native record against itself is insufficient.

**This is a translation certificate for that subset, not a theorem that the entire
URDF exporter or robot is correct.** The Python XML parser and native-record extraction
are part of the trusted input boundary. The certificate does not prove trigonometry,
frame transforms, inertia decomposition, full mesh geometry, continuous motion,
collision behavior, dynamics, hardware ratings or control safety.

Bundle verification binds the certificate to the native digest and actual XML bytes,
reconstructs the expected proof instance, checks the installed proof module, and can
re-run Lean. It also compares the current deterministic XML projection to catch drift
outside the finite theorem (including origin changes). That comparison is a software
integrity check, not an additional formal proof.

## Numerical and compatibility checks

Independent NumPy FK is compared with regenerated MJCF, regenerated URDF and a
consumer copy of the source URDF at reference / 35% / 65% configurations. The source
consumer copy changes only asset resolution/scale baking, geometry names and explicit
MuJoCo loading hints. The original XML and original asset bytes remain archived.
Checks cover body frames, COM, mass, world inertia and mesh bounds/centroids; they do
not prove complete surface topology or behavior at all configurations.

Ordinary URDF cannot preserve native controller contracts, free-base world placement,
physical evidence or source lineage. Importing a Microduck/XGO URDF therefore retains
its mechanism but does not restore those omitted native contracts.

Old v0.9/v0.10 bundles remain verifiable with an explicitly unavailable exchange
certificate. They are not retroactively labeled certified. A fresh native revision
or import produces both proofs. Existing private proof artifacts are not rewritten.
Public site implementation details remain intentionally abstracted.
