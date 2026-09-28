# Robot personalization with a fixed mechanical platform

Status: v0.10 implements a bounded **additive head accessory** pilot for native
Microduck and XGO bundles. GLM-5.3-Flash owns design, visual review, revisions and
selection. Existing shells and internal hardware are preserved. This is not yet
shell replacement or a qualified installed upgrade.

## Run the pilot

```bash
python -m pip install -e '.[robot,personalize]'
fk robot import microduck --output ./robots --require-proof --json
# Use the directory returned by import; xgoduck is also supported.
fk robot zone ./robots/<bundle> --json
fk robot personalize ./robots/<bundle> \
  --brief 'A friendly, recognizable head-top accessory; retain the camera and mechanism' \
  --rounds 3 --output ./variants --require-proof --json
```

Configure the existing [GLM model connection](QUICKSTART.md) locally. The runtime
requires `glm-5.3-flash` and records provider-reported identity; there is no alternate
model or authored-design fallback. Credentials are not written into run artifacts.
A model-owned rejection returns a nonzero CLI exit and retains its evidence.

Open the returned directory's `index.html` for the offline review page. It contains
the baseline, candidate views, GLM findings/selection and links to STEP/STL, URDF and
sampled-clearance evidence. Run artifacts also include raw model responses, recipes,
workflow/skill snapshots and dependency versions. Every new workflow execution gets
a new identity; rejected attempts are retained.

`fk robot attach <bundle> --recipe recipe.json --output ./variants --require-proof`
applies an explicit data-only recipe without invoking a model. It is useful for
integration/testing; an authored recipe is not evidence of GLM generation.

## What the implementation checks

- A source-mesh ray intersection supplies a **geometric tangent frame**, not an
  inferred screw pattern or mechanically validated mount. The flat base proposes
  removable pad/adhesive attachment; fit to source curvature remains unresolved.
- Typed recipes expose an elliptical foot and up to eight box, ellipsoid or fin
  features, with optional bilateral mirroring. No generated Python is executed.
- Exact CAD checks require one connected valid positive-volume solid, no material
  below its datum, and fixed extent/added-mass search bounds. STEP is primary; STL
  is millimetres and the native OBJ is metres. A separate STEP read checks volume
  and creates a part snapshot.
- Original native bodies, meshes, geometry, joints, actuators, sensors and action
  order must remain unchanged. A fixed body and CAD-backed part node are appended.
  Mass, COM and inertia use solid CAD and nominal polymer density, not measured
  print mass. Generic numeric edits cannot override that part's CAD-derived body.
- The real platforms receive 31 sampled joint configurations. Convex-hull distance
  checks exclude the intended target contact and use a 0.2 mm penetration tolerance.
  This is neither continuous collision coverage nor an actual mounting-fit test.
- Fresh Lean evidence checks the existing finite native structure/controller
  contract. Frozen-part equality and geometry checks run in Python/CAD/MuJoCo;
  they are not Lean geometry theorems. The previous controller suitability is
  invalidated, and deployment remains false.

The budget is one to three candidate rounds, each with at most two plan and two
review calls, plus at most two final-selection calls: at most 14 calls for three
rounds. GLM sees its rejected recipes and exact diagnostics, as well as real whole
robot/head renders. It may select null. A selected `needs-review` verdict stays
visible and does not become visual acceptance merely through selection.

Camera field of view, cooling, curved-surface fit, adhesive retention, print process,
strength and walking behavior still require explicit validation. No slicing, printer
submission, robot control or hardware actuation occurs in this workflow.

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

## Next operators

The implemented `attach_part` is deliberately additive: body mass aggregates the
source shell and electronics, so replacing a shell without its own mass accounting
would be misleading. Next work is a `replace_part` operator with physical-part/BOM
mapping, verified mating features, reserved camera/cooling/wiring volumes and a
recorded subtraction/addition of shell mass properties. XGO particularly needs the
mapping between its coarse rigid-body meshes and physical covers.

Reusing a style recipe between platforms still requires a newly bound zone and
fresh evaluation. Reusing an STL does not establish mechanical compatibility.
Controller adaptation and real robot tests remain separate requirements.

The [robot-personalization skill](../fluxkernel/demo/skills/robot-personalization/SKILL.md)
is loaded in every model phase. The native robot remains the design source;
URDF/MJCF are derived projections. See [NATIVE_ROBOTS.md](NATIVE_ROBOTS.md) for the
base importer, formal scope and export losses.
