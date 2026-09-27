# Studio perception–action loop

Live Studio runs now render their actual CAD, compare those renders with the input
image through the configured vision model, apply bounded local edits, and evaluate
again. A successful model request or a valid solid is no longer treated as visual
acceptance. The manufacturing-plan proof remains a separate result.

## Run it

Install the existing `demo` extra and configure the image-capable model as described
in [Quickstart](QUICKSTART.md). In Studio, choose the visual budget before generating:

- **3 rounds** (default): baseline review plus up to two candidate revisions.
- **4 rounds**: up to three candidate revisions.
- **1 round**: review only; no automatic edit.
- **0 rounds**: explicitly disable visual evaluation.

Reference/fixture/local numeric revision modes do not call the visual model.
Existing runs do not acquire an evaluation retroactively. To refine a saved run:

```bash
fk perceive ./runs/<parent-id> --rounds 3 --output ./visual-runs --require-proof --json
```

```python
from fluxkernel.studio import refine_visual
run = refine_visual("./runs/<parent-id>", output_dir="./visual-runs", rounds=3)
```

This **makes real model API calls**, creates a new directory, verifies/pins the parent
manifest, and preserves its image, requirements, catalog dimensions and numeric
contract. A new live upload first runs the existing image planner; a saved-parent
refinement starts from its verified design without another initial planning call.
The existing MCP fixture tools remain model-free; the live loop is available through
Studio, this CLI and the Python API.

## One round

1. Construct each part through the finite B-rep recipes. Tessellate that geometry
   and render ISO, side, top and front views with a depth buffer. Studio coordinates
   are X longitudinal, Y lateral, Z up. The evaluation frame stays fixed across rounds.
2. Run narrow independent checks: aircraft engine-axis alignment, longitudinal
   interval overlap of unrotated fuselage segments, and geometry outside the fixed
   render frame. These are **not** a general collision or assembly solver.
3. Send the reference image and actual four-view sheet to the vision model. Later
   rounds also include the current best candidate's sheet. Require structured
   silhouette/proportion/layout ratings and findings tied to existing part IDs.
4. Ask for a local edit against the exact design digest. Requirements, part IDs,
   part count, materials, routes and procurement references are protected. Purchased
   dimensions cannot change; purchased part poses may change.
5. Validate the edit and frozen constraints. On rejection, record the invalid action
   and return its error for **one** repair attempt. No silent partial application.
6. Render and review the candidate in the next round. Keep the best actually reviewed
   design. Export its CAD and regenerate the manufacturing plan and Lean evidence.

Allowed actions are size, position, rotation and wall edits, plus explicit recipe
changes within the fuselage family and `car_body` → `smooth_car_body`. The original
low-poly recipes remain unchanged. New smooth recipes include a complete fuselage,
a constant-section middle, a nose taper toward +X, and a tail taper toward -X. These
are concept surfaces with capped hollow solids, not production tooling surfaces or
validated airframes. They do not add wheel arches or a general surface editor.

## Selection and stopping

Candidate ranking is lexicographic: fewer independent diagnostic failures, fewer
model-reported blocking findings, fewer major findings, then a weighted visual score
(40% silhouette, 30% proportions, 30% layout). This policy can favor fixing a known
axis error even if the model's visual rating drops. The recorded components remain
visible; do not claim universal monotonic improvement.

The model review threshold requires no independent failures, no blocking/major
findings, and all three ratings at least 80. `model-threshold-met` means exactly
that; it is not calibrated similarity, human acceptance or a physical certificate.
Otherwise the result remains `needs-review`, even if Lean accepts its plan.

Model ratings vary and should only be interpreted within the recorded run. No
reference-camera pose has been estimated, no segmentation ground truth is available,
and no reference-image IoU or objective likeness percentage is claimed. Orthographic
views help identify geometry faults but do not reproduce the source perspective.

The loop limits rounds to four. At most `3 * rounds - 2` review/action requests are
made (including one action repair per transition), plus up to three initial planner
requests for a new image. Requests are not started after the 900-second loop budget;
an in-flight call can extend beyond that boundary. Worker/client limits remain
separate. No rollback is implied by client cancellation.

## Evidence and UI

Each run keeps:

- `perception/reference.png` and a copy of the loop/render implementation.
- Per-round `design.json`, four renders, silhouette masks, render metadata, narrow
  layout checks and declared numeric checks.
- Review/action request metadata with image hashes and raw model responses/usage.
- Rejected actions with validation errors and any corrective response.
- `perception/summary.json`: candidates, selection, stop reason and actual API calls.

Images and reports enter the bundle manifest. The independent bundle verifier also
checks that the selected candidate digest/design agrees with final `design.json`.
It does not turn the model's visual opinion into a Lean theorem. Studio displays
candidate sheets, scores, retained round and unresolved quality separately from
manufacturing-plan proof status.

On reviewer/API/render failure, retain the best reviewed candidate and explicitly
record the failure. If none was reviewed, retain the initial design as **unreviewed**.
There are no invented scores and no reference replay fallback. Native CAD execution
and supplier/physical claims retain their existing limitations.

## Tests and interpretation

Automated tests use explicitly mocked model responses to cover image delivery,
render depth, recipe export, action protection, rejection/repair, regression retention,
failure handling, stopping and pipeline integration. Installed-wheel checks also
exercise rendering and selection with a mock provider. Separate real GLM runs must
be identified as such in release evidence; a mock test is never a model-quality result.

The old website cases remain earlier recorded outputs until an explicitly reviewed
site release replaces them. A new backend version does not improve their stored
meshes automatically.
