# Robot personalization with a fixed mechanical platform

Status: source review and integration design, 2026-09-28. This document does not
claim an implemented personalization generator, a new GLM run, or validated printed
parts. The existing native robot importer/revision/export implementation is described
in [NATIVE_ROBOTS.md](NATIVE_ROBOTS.md).

## Findings from Anything2Robot

Reviewed commit: `38ef55a6a7ed965b2e3b6958ba82fd9a67e77aa5`.

The [README](https://github.com/g-ch/anything2robot/blob/38ef55a6a7ed965b2e3b6958ba82fd9a67e77aa5/README.md)
expects a previously generated STL and joint positions/axes. Image/text-to-3D is an
upstream input stage, not supplied by this repository. Its design pipeline performs
mesh decomposition, actuator/layout optimization, joint connections, motion
interference removal and export. Watertightness and destruction checks are separate
steps. FEA is optional, disabled by default, and requires a working Ansys integration.
See the inspected [entry point](https://github.com/g-ch/anything2robot/blob/38ef55a6a7ed965b2e3b6958ba82fd9a67e77aa5/script/auto_design.py).

The entry point retries some failures by enlarging the model. A retrofit adapter
must not inherit that behavior: changing scale would break the existing robot's
mounts and motor locations. Likewise, free actuator selection is inappropriate when
retaining Microduck's or XGO's existing motors.

Its [license](https://github.com/g-ch/anything2robot/blob/38ef55a6a7ed965b2e3b6958ba82fd9a67e77aa5/LICENSE)
requires prior written permission for commercial use and expressly includes internal
for-profit product development. An isolated process or private repository does not
change those stated restrictions. Obtain the relevant authorization before using
this implementation in the commercial pipeline, or develop the required geometry
operators independently. This review copied no implementation and ran no upstream
program. Existing byte-identical Workbench code identified in
[ROBOT_PLATFORM_SOURCES.json](ROBOT_PLATFORM_SOURCES.json) is not a separate licensing
basis.

## Actual native assets available now

Inspection of the imported native documents found:

| Platform | Native body | Relevant mesh assets | Personalization implication |
| --- | --- | --- | --- |
| Microduck | `jaw_soft` | `top_head_shell`, `bottom_head_shell`, `face_part` | Separate named exterior meshes provide useful initial targets |
| Microduck | `trunk_base` | `left_shell`, `right_shell` | Candidate torso covers, with internal hardware retained |
| XGO | `neck_pitch` | `head_pitch` | Mechanism asset; do not treat it as a cosmetic cover by name alone |
| XGO | `yaw_roll_motion` | `head_yaw` | Mechanism asset requiring physical-part mapping |
| XGO | `jaw_soft` | `head_roll` | Coarser head asset; split/map physical shell and internal parts first |

These names establish source geometry identity, not mounting dimensions or complete
physical BOM semantics. Microduck's `jaw_soft` also contains camera, motor, PCB and
speaker meshes. Replacing the entire rigid body would accidentally replace internal
hardware. The replacement target must be a specific exterior part occurrence.

Body-level mass/inertia aggregate multiple physical components. Replacing one shell
requires its previous mass/inertia to be known or separately estimated and labeled;
the system cannot subtract a whole-body mass as if it belonged to that shell.

## First bounded product slice

Begin with removable head shells/masks and torso accessories. Preserve the existing
actuator identities, articulated topology, joint axes/anchors, travel limits and
mechanical mounting references. A fixed base platform is a constraint on design,
not a guarantee that its original walking policy still works after changing mass.

Start the shell-replacement prototype on Microduck, where exterior meshes are
separate. For XGO, first establish shell/BOM correspondence or use an independently
validated attachment interface. Defer leg lengths, load-bearing link changes and
foot contact geometry until their dynamics and controller adaptations are in scope.

Each target needs an explicit `CustomizationZone` contract:

- Pinned native parent, body and geometry occurrence identities.
- Named mount frame and interface source, with unresolved dimensions kept unknown.
- Frozen mating geometry and reserved space for camera view, wiring, speakers,
  cooling, screws and maintenance access.
- Editable exterior region and allowed geometry recipe operations.
- Material/process assumptions and mass/inertia estimates with provenance.
- Motion/collision test configurations and a declaration of their coverage limits.

Mounting interfaces cannot be invented from a bounding box. A shared style recipe
can be reused across platforms, while each platform supplies its own verified
mechanical adapter. Reusing the same STL is not a compatibility argument.

## Proposed GLM-only design loop

```text
User style/image + pinned native robot + customization-zone contract
    -> GLM-5.3-Flash selects a target and bounded geometry recipe
    -> deterministic CAD engine builds candidate STEP/STL
    -> host checks mating preservation, geometry and configured motion clearances
    -> render candidate in the complete robot, including relevant joint poses
    -> GLM reviews actual renders and diagnostic evidence, then revises or rejects
    -> bounded selection with complete accepted/rejected history
    -> new native variant, fresh proof, projections and manufacturing evidence
```

Proposed pilot budget: at most three candidate rounds, configurable and recorded.
GLM makes the design edits and final candidate selection. The host supplies finite
operators, enforces immutable constraints and reports failed checks. A human/Codex
must not silently repair the model's candidate and attribute the result to GLM.
Model/API failure must remain visible rather than falling back to an authored design.

The existing general product PAL cannot be directly reused without a robot-specific
contract: it plans whole products and includes assumptions that do not fit shell
retrofits. Add a dedicated workflow/skill and typed part operations. Do not feed the
whole robot into that planner and then hope it preserves the existing mechanisms.

## Required native operators and evidence

The current `fk robot revise` only changes bounded body/joint numbers. It does not
add or replace meshes, construct shells, or identify mounting holes. Proposed new
operators are:

1. `attach_part`: append a named fixed part with explicit body-local placement,
   geometry, mass properties and its mechanical interface reference.
2. `replace_part`: replace only the selected geometry occurrence, preserve locked
   mating features and internal hardware, and update aggregate mass properties with
   a recorded derivation and assumptions.
3. `evaluate_variant`: run the declared geometric/motion checks, generate render
   evidence, and compare against the pinned parent without changing that parent.

After either change, bind the new native design and invalidate previous controller
suitability evidence. Generate URDF/MJCF from this native variant; do not make an
external URDF the new source of truth.

Lean can be extended to verify source binding, required obligations, permitted edit
scope and preserved interface declarations. Actual geometry checks, mass estimation,
strength analysis and robot experiments have separate evaluators. Current Lean robot
proofs do not already establish the proposed customization-zone checks.

A demonstration result should include the whole-robot view, the individual part,
STEP/STL, parent-to-child diff, interface evidence, estimated mass/COM/inertia changes,
GLM transcript and budget, fresh structural proof, and explicit unresolved assembly
and control obligations. A printable candidate and a validated installed upgrade are
separate release states.
