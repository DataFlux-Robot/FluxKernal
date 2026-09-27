# Geometry and workflow contract

Coordinates are millimetres, angles degrees. World X is longitudinal/forward, Y lateral,
Z up. All normal part rotations apply local X, then Y, then Z; position is translation.
Source IDs are existing occurrences. Targets keep their IDs and procurement references.

## Symmetry

`axis` is the **normal** of the mirror plane: axis=y means the XZ plane, y=plane_offset.
The declared source controls target geometry and pose. Rotation uses S R S plus an
actual local reflection, rather than merely negating a translation. Each occurrence
can appear in at most one pair; no chains/cycles. Only listed pairs are constrained.
Exceptions and unpaired occurrences remain independently editable. Catalog pairing
is limited to identical box/cylinder/tube envelopes with pose-only mirroring.
The declaration is frozen during a run; if it is wrong, stop and request a fresh plan.

## Wing

Upgrade a fabricated `wing` to `parametric_wing` by setting the full `parametric` object:
kind=wing, span, root_chord, tip_chord, sweep_deg, dihedral_deg, twist_deg, thickness_ratio.
`span` is one source wing's semispan. Local origin is the **root leading edge**, local
+Y goes toward the tip, and the trailing edge is at negative X. Positive sweep moves
the tip aft; positive dihedral raises the tip. Twist applies about local Y at the tip.
The root has zero twist. Thickness uses a closed symmetric four-digit airfoil law and
ruled root/tip sections; it is a concept solid, not an aerodynamic analysis result.
Switching from the old centered wing changes the origin convention: explicitly choose
its position to attach the new root to the fuselage. Mirror the opposite side with
rules instead of independently guessing rotations. Size is derived from the sections.

## Section body

Upgrade a fabricated fuselage/car body family to `section_body` using kind=body,
length and 3–12 strictly ordered sections. Each section has u (0..1), width, height,
offset_y, offset_z. First u=0 is local x=-length/2 (aft), final u=1 is x=+length/2 (forward).
Each section is an ellipse. Width and height must be at least 0.4 mm. Connections are
ruled, capped solids with finite end sections. There is no promised uniform wall or
smooth curvature continuity. Elliptical sections alone cannot create wheel arches.

## Actions and assessment

Set semantic parameters as a complete object; do not also set size or shape. The tool
derives these fields and validates limits. Part pose/wall edits remain finite operations;
`wall` does not hollow the new concept solids. No free Python execution, part insertion,
material substitution or procurement resizing is available in this workflow.

Structured review claims use a part ID, dot path and value, e.g. size.0 or
parametric.root_chord. Values must match the provided current recipe, not a previous
round. These checks catch structured factual contradictions but do not prove every
sentence of free-text visual critique. Frame expansion is recorded and both candidates
are re-rendered at the same scale; frame clipping is not a structural defect.

Official references used to design this vocabulary (not code copied or backend used):
- https://openvsp.org/api_docs/latest/group___x_sec.html
- https://www.nasa.gov/reference/openvsp-wings/
- https://vspu.larc.nasa.gov/training-content/chapter-1-vspfundamentals/wings/wing-planform/
