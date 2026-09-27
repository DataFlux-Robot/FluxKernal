# GLM-only, rule-based perception–action workflow (v0.6)

The live Studio path and `fk perceive` now run the same workflow: GLM-5.3-Flash
judges symmetry, declares rules and parameterization, reviews actual CAD, proposes
edits, selects the retained candidate and decides whether to continue. The host
provides deterministic tools and validation. No other model supplies design edits
or chooses the visually preferred candidate.

```bash
fk perceive ./runs/<verified-parent> --rounds 3 --output ./visual-runs --require-proof --json
```

These are real API calls. Configure the existing private model settings for
`glm-5.3-flash`; another configured/reported model fails explicitly. New live images
first use GLM's existing occurrence planner; saved-parent refinement skips that step.
Symmetry is judged before refinement edits, not before the saved parent existed.
Fixture/reference/numeric revision modes remain model-free. Studio permits 0 rounds
(disabled), 1 review round, or up to 4 review rounds. Three remains the default.

## Skill and workflow

The packaged [skill](../fluxkernel/demo/skills/fluxkernel-glm-pal/SKILL.md) and its
[parameter conventions](../fluxkernel/demo/skills/fluxkernel-glm-pal/references/parameters.md)
are loaded into every GLM planning, review, action and selection request. They are
runtime instructions, not merely a document for a human operator. The wheel ships
both resources; the run archives their exact bytes and implementation source hashes.

1. Render the untouched parent. GLM returns symmetry evidence/confidence,
   bilateral/partial/none/uncertain mode, plane, disjoint source/target IDs,
   exceptions, semantic parameter bindings and refinement stages.
2. Validate and compile its declared mirrors. Unknown/uncertain symmetry leaves
   geometry unchanged. Only declared pairs are mirrored. Unpaired components remain
   editable. This compiled design is the first reviewed candidate; the untouched
   baseline has its own saved design/render and is not mislabelled as a GLM revision.
3. Render actual B-reps; supply current recipe facts and before/after differences.
   Compare current and retained candidates in a common frame encompassing both and
   the baseline. Frame expansion is recorded, not ranked as a structural defect.
4. GLM reviews silhouette, proportions and layout. Structured numeric claims must
   match current recipe fields. This catches stale structured numbers; it does not
   prove that every free-text sentence is correct or resolve camera ambiguity.
5. GLM chooses the current or retained reviewed candidate, the next stage and whether
   to stop. The host's old lexicographic score remains diagnostic metadata only.
6. GLM proposes bounded edits. Validate the whole action, compile mirrored targets,
   check frozen nominal constraints and construct geometry. Review again before any
   new candidate can be selected. A validation rejection gets one model repair.

At most `6 * rounds` requests are available: plan/review/selection/action, each with
at most one validation repair. Three rounds normally use 9 requests; at most 18,
plus up to 3 initial planning requests for a new image. The 900-second loop budget
prevents starting new requests after expiry; an in-flight call can overrun it.
Provider/render failures retain the last GLM-selected reviewed candidate, or return
an explicitly unreviewed original when none exists. There is no model/replay fallback.

## Symmetry and semantic geometry

Mirrors use an actual local geometric reflection and a conjugated rotation/translated
pose. Negating only Y or Euler yaw is insufficient. Targets retain identities,
materials, routes and procurement references. Editing a derived target directly is
rejected. Catalog pairs require compatible identical symmetric primitive envelopes;
the compiler changes their poses, never their procurement dimensions.

GLM can bind fabricated wing/body occurrences to:

- **Parametric wing:** semispan, root/tip chord, sweep, dihedral, tip twist and thickness
  ratio. The local origin is the root leading edge. The opposite wing can be derived
  exactly through a mirror rule. Size is derived from the sections.
- **Section body:** length and 3–12 elliptical sections with longitudinal fraction,
  width/height and lateral/vertical offsets. Section order and envelope bounds are
  validated. The body is capped and uses ruled transitions.

These are concept solids, not validated thin-walled production parts. Section bodies
are not generally curvature-continuous; elliptical sections cannot cut wheel arches.
The new wing uses a symmetric four-digit thickness distribution and a root/tip loft.
No aerodynamic solver or manufacturing qualification is implied. Frozen constraints
still apply after all derived occurrences are compiled.

This design is **inspired by OpenVSP**, not an OpenVSP binding or a claim of its feature
coverage. References: [XSec API](https://openvsp.org/api_docs/latest/group___x_sec.html),
[NASA wing documentation](https://www.nasa.gov/reference/openvsp-wings/),
[wing planform](https://vspu.larc.nasa.gov/training-content/chapter-1-vspfundamentals/wings/wing-planform/).
No OpenVSP source code was copied into these recipes.

## Evidence and acceptance

A run records the skill/implementation snapshots, untouched parent, GLM plan,
mirror compilation identities, current facts/differences, four-view renders,
requests/responses (with hashes and provider-reported model), validation failures,
GLM selection reasons, candidate lineage and final selection. The bundle verifier
binds the selection chain and archived responses to the final design and checks the
actual manufacturing plan with Lean separately.

`human_design_edits: false` describes this execution path, not a signed attestation
that an external operator could never tamper with a bundle. Hashes detect changes
relative to their recorded manifest. Model identity is requested and provider-reported,
not independent inspection of the provider's internal weights.

The quality threshold requires no current independent diagnostic issues, no model
blocking/major findings and three model ratings at least 80. It is a model threshold,
not calibrated image similarity, human approval or physical certification. Camera
pose is still unestimated, hidden internals remain hypotheses and layout checks are
not a general collision/attachment solver. The legacy aircraft body-envelope check
covers the named fuselage recipes; the new general section_body recipe has no
collision/attachment coverage. All other outcomes remain `needs-review`.

The v0.5 runner remains `run_legacy_loop` for historical regression tests only; live
Studio/CLI use v0.6. Existing recorded cases keep their original workflow identity.
A website backend update does not automatically replace public recorded cases.

## Testing without intervening in a design

Unit/package tests use explicit mock providers to verify actual reflection, protected
procurement dimensions, semantic B-reps, stale-fact rejection, model-only selection,
failure preservation and runtime skill delivery. Real GLM runs must be separately
identified. Freeze the implementation before running a live validation; do not inject
hand-written geometry, patch a candidate, replace a failed response or override GLM's
selection. Report failures and limitations alongside any improvements.
