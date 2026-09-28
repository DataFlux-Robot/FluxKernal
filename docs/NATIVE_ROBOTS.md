# Native robots: Microduck and XGO

FluxKernel owns a versioned robot design document (`fk-robot-v1`) and stores its
assembly, rigid bodies, mesh assets, controller contract and hardware inventory as
content-addressed kernel objects. `robot.json` is the authority. URDF and MJCF are
regenerated exchange projections, including after a native revision; the generator
does not reload upstream XML. The importer executes no upstream Python or firmware.

This is a deterministic source conversion, with zero model calls. It does not alter
the GLM-5.3-Flash image-design PAL or claim a live model customization experiment.

## What was converted

| Pinned upstream model | Rigid bodies | Articulated joints | Free base joints | Mesh assets | Declared mass |
| --- | ---: | ---: | ---: | ---: | ---: |
| Microduck | 15 | 14 | 1 | 38 | 0.73724318 kg |
| XGO Duck | 15 | 14 | 1 | 15 | 0.7999999893 kg |

Masses are values from the upstream compiled models, not measurements. Mesh count,
rigid-body count, actuator count and physical BOM quantity are different concepts.
The walking models do not establish the full physical robot's servo/BOM inventory.

An optional XGO adapter preserves 32 hardware source files and raw rows from
`bom.xlsx` (12 rows) and `PCBA/BOM.xlsx` (25 rows), including headers. These are not
37 deduplicated BOM components. Spreadsheet formulas are retained without execution.
Filename quantity hints are explicitly labeled; unspecified quantities stay unknown.
Mapping physical parts to simulated rigid bodies, materials, suppliers and process
qualification remain open obligations. Hardware files stay in the local bundle;
this distribution contains the fetching adapter, not copies of the hardware assets.

## Native design and proof boundary

```text
Pinned model + source identity       Physical BOM / CAD inventory
               │                              │
               └──────── native robot ────────┘
                         robot.json
                              │
        ┌─────────────────────┼─────────────────────┐
   Kernel graph         Lean instance          Projections
 bodies / meshes       finite obligations     URDF / MJCF
 controller / sources          │                    │
        └────────────── manifest + verification ────┘
```

The native representation carries information outside ordinary URDF's mechanism
exchange scope: source identities, requirements, evidence state, manufacturing
obligations, controller-to-plant binding, immutable revisions and invalidated claims.
This is the sense in which it is richer than URDF. Lean checks selected propositions
about that data; it does not replace CAD geometry, dynamics engines or robot middleware.

The actual Lean 4 module is [`formal/FluxKernel/Robot.lean`](../formal/FluxKernel/Robot.lean).
Each bundle contains concrete body, joint and action records and a `by decide` proof.
It checks unique body/joint identities, acyclic parent ordering, nonnegative declared
mass, joint references, ordered limits, driven-joint coverage, and controller binding
to the plant fingerprint. Decimal values become exact integer/positive-denominator
pairs. There is no `sorry` or `native_decide` in this checker.

The Python validator additionally checks SI/wxyz units, normalized frames, inertia
realizability, sensor references, actuator vectors and finite numeric inputs. Lean
does **not** currently prove these additional checks, SHA-256 correctness, mesh
geometry, floating-point projection equivalence, stability or manufacturing feasibility.
The bridge recomputes the generated Lean source from the native document and checks
the proof project against the installed version before rechecking it.

Every assembly retains an open physical-integration obligation and `promoted=false`.
Controller weights, observation contracts and hardware calibration are not imported;
`deployment_ready=false` is enforced. Microduck XL330 and XGO HLS1910 contracts are
separate. Similar joint names do not establish policy transfer.

## Reproduce

Python 3.12+ and the repository's pinned Lean launcher are needed for proof-required
runs. The optional robot extra supplies MuJoCo, NumPy (via MuJoCo) and Pillow. The
core remains dependency-free.

```bash
python -m pip install -e '.[robot]'
lake build
fk robot import microduck --output ./robot-runs --require-proof
fk robot import xgoduck --output ./robot-runs --include-hardware --require-proof
fk robot inspect ./robot-runs/<bundle>
fk robot verify ./robot-runs/<bundle> --require-proof
fk robot check-projection ./robot-runs/<bundle>
fk robot compare ./robot-runs/<microduck-bundle> ./robot-runs/<xgo-bundle>
```

Each import creates a new directory; `--source` can reuse an already downloaded,
verified local snapshot. Cached manifests are local provenance records, not a
cryptographic signature from upstream. Online fetching verifies Git blob identities
against the pinned tree; bundle verification checks content hashes, not network trust.

A complete two-model regression, with optional offscreen four-view rendering:

```bash
python scripts/benchmark_native_robots.py --output ./robot-evaluation \
  --include-hardware --render
```

Rendering uses the source rest pose, no policy and no simulation rollout. Linux
headless rendering needs EGL; omit `--render` to run the numeric/Lean checks without
a graphics context. The benchmark requires Lean; robot fixture tests run in CI
without downloading upstream repositories.

## Revise the native design

`fk robot revise` accepts a pinned parent and up to 32 edits. Body mass, position,
principal inertia and COM offset, plus joint range, anchor and axis are currently
editable. Parent topology, source identity, controller order and source manufacturing
claims are outside this numeric patch vocabulary. Example authoring code:

```python
import json
from pathlib import Path
from fluxkernel.robotics.native import read, digest
from fluxkernel.robotics.bundle import revise

parent = Path("robot-runs/<bundle>")
r = read(parent)
body = r["bodies"][0]
patch = {
    "base_native_sha256": digest(r),
    "edits": [{"kind": "body", "name": body["name"],
               "set": {"mass": body["mass"] * 1.02}}],
}
# An authored parameter example, not a physical recommendation or GLM design.
Path("patch.json").write_text(json.dumps(patch, indent=2))
child = revise(parent, patch, "robot-runs")
print(child)
```

Equivalent CLI: `fk robot revise <parent> --patch patch.json --output ./robot-runs
--require-proof`. The parent stays unchanged; the child receives a new native hash,
kernel objects, projections and proof. Source-equivalence and policy/physical
suitability evidence expire. Rebinding the structural controller contract to the new
plant does not retrain or approve the old controller.

## Exchange semantics and numeric checks

Native body frames are parent-local. Joint anchors are body-local. Quaternions use
wxyz, distances metres, angles radians, masses kilograms, inertias kg·m². Compiled
mesh vertices are exported in metres with the compiled geometry transforms; applying
upstream mesh transforms a second time would be incorrect.

The URDF projection shifts child frames to joint anchors and shifts visuals/inertials
accordingly. `q_urdf = q_native - reference`. It omits the world root pose/free joint;
the consumer supplies its world placement. `gen_urdf.py` is the skill-compatible Python
entry point and reads the native authority. Unknown effort/velocity limits are written
as zero with an explicit **display/kinematic exchange only** loss report; these are
not physical actuator ratings.

URDF does not carry the native evidence/requirements, controller law, sensor semantics
or collision masks. Unsupported ball/multiple joints, root articulated joints and
unsupported primitive conversions fail instead of silently dropping information.
MJCF preserves the implemented kinematic/inertial/geometry/basic actuator/sensor subset;
it does not reproduce training environments, BAM wrappers, solver/contact overrides,
textures, calibration or policy weights. The native importer rejects tendons, equality
loops and deformables until an appropriate adapter exists.

`check-projection` checks three configurations (reference, 35% and 65% of limits).
An independent NumPy FK implementation is compared with MuJoCo loading the original
model, regenerated MJCF and URDF. It compares body frames, COM, mass, world inertia
and mesh vertex bounds/centroids. This is numerical regression, not a theorem or a
full mesh-topology/dynamics equivalence proof. Source comparison is intentionally
omitted for revised models, whose source equivalence has expired.

## Source pins and attribution

- [Microduck RL](https://github.com/pollen-robotics/microduck_rl/tree/1e79c29c97d8b38aee9eefde77a545860ba7658e): Apache-2.0, model source; see also [Microduck](https://github.com/pollen-robotics/microduck).
- [XGO RL](https://github.com/LuwuDynamics/xgoduck_rl/tree/326d77a1122870bdefa2c36403937502c958e69c): Apache-2.0, model source.
- [XGO hardware](https://github.com/LuwuDynamics/xgoduck_hardware/tree/a8f3356dd416c9a9bd47f5de68fb7a67eab829b6): no repository-level LICENSE at the inspected pin; availability does not establish redistribution rights.
- [FluxWeave](https://github.com/DataFlux-Robot/FluxWeave/tree/d39f272c68db1fe10bfe04f5f31b762e753c9731): inspected `FluxhWeave_Assembler_V3.py` and `stl_metadata.py`, particularly separate part transforms, attachment points and axes. This informed frame handling; no implementation was copied.

The imported RL source LICENSE and README are retained in each bundle. Rendered
figures in release evidence derive from those pinned RL models. No runtime/firmware,
Anything2Robot code, policy weights or unaudited Workbench generator was copied.

## Remaining work toward consumer customization

The imported mesh assets do not recover parametric CAD construction history. Native
numeric revisions are available; arbitrary shell remodeling, remeshing and topology
edits need additional geometry operators. The existing cross-product recipe catalog
is not yet an automatic robot morphology or policy transfer system.

Next acceptance gates are physical BOM-to-body mapping, parameterized replaceable
modules and validated mounting interfaces, complete runtime/observation/calibration
contracts, regression simulation with the actual actuator model, and measured assembly
and control tests. These gates remain open in the model rather than being replaced by
formal-structure acceptance. See [v0.9 evidence](releases/2026-09-28-v0.9.md).
