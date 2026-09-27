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
Local +Y must point OUTBOARD after reflection and rotation. An unrotated source on
the negative-Y side needs reflection=y (or an appropriate pose); merely translating
it to negative Y leaves the wing pointing inward. Plan parameterization entries may
initialize parameters, position, rotation and reflection; actions may edit reflection
on fabricated sources. A source reflection must match the mirror normal.

## Assembly rules: whole profile first, partitions second

The plan has optional `assembly` with `bodies`, `attachments`, `alignments` lists.
The resulting design stores these rules. An action can replace the COMPLETE assembly
object (not a partial patch); `edits: []` is valid when changing assembly alone.
Unchanged rules must be retained explicitly. These declarations are GLM decisions.
During a run, previously declared contact children cannot be dropped or downgraded to
placement to bypass checks; they may be reparented. Axis-part and shared-body-member
coverage must also be retained, though directions, profiles and partitions may change.
If the initial declarations themselves are wrong, stop and explicitly replan in a new run.

`bodies`: each group has id, profile (a full BodyParameters object), world position,
world XYZ rotation, and ordered members [{part,start,end},...]. Start/end are fractions
of the overall profile, partitioning exactly [0,1] without gaps/overlaps, aft to forward.
Members must be existing fabricated body-family parts, not mirror targets or separately
parameterized parts. Shared cuts interpolate the same ellipse, so neighbors have an
identical boundary; each member becomes a capped concept solid with its original ID,
material and route. Change the group profile/pose/cuts instead of editing member
size/position/rotation/shape. This repairs poor body segmentation without losing
manufacturing identities. It does NOT ensure tangent continuity or hollow interiors.

`attachments`: each has parent, child, parent_anchor, child_anchor, relation.
The child's translation is derived so these two anchors coincide after both local
reflection and rotation. The child's rotation remains editable unless axis-aligned.
One parent per child; no cycles even through mirror edges. Body members and mirror
targets cannot be attachment children. Choose a source attachment, then mirror its
counterpart. Parameters changing the parent move the child automatically.
relation=contact requests an independent actual B-rep distance check (gap <=0.1mm);
relation=placement only checks anchors, appropriate for deliberately nested/offset
components and NOT a claim of mechanical contact. Contact may include overlap; there
is no general penetration solver. Unspecified relationships remain unassessed.
Checks report actual nearest parent/child points and the parent-to-child gap vector
in world coordinates, also for placement relations. Use this evidence to determine
which anchor coordinate or component dimension matters; an axial change cannot
necessarily fix a radial gap. Placement gap measurements are information, not errors.

Anchors use kind, u/v/w fractions (0..1), angle_deg; defaults u=v=w=.5, angle=0:
- origin: the recipe's local origin, ignores fractions.
- wing: requires semantic wing; u=0 root, u=1 tip; v=0 leading edge, v=1 trailing
  edge. The anchor lies on the mean chord plane, interpolating twist and sweep.
- body: requires section_body; u is local body station; v=0 centerline, v=1 ellipse
  surface; angle 0 points +Y, 90 points +Z. On a partition, u refers to that member.
- box: box/shell/frame local coordinates ((u-.5)*sizeX,(v-.5)*sizeY,(w-.5)*sizeZ).
  For a frame/shell, some points are empty space: check actual contact evidence.
- cylinder: cylinder/tube; u is axial fraction (-Z to +Z), v radial fraction;
  angle 0 points +X, 90 points +Y. Axis points may be inside a tube's empty bore.

`alignments`: each has part, local_axis (x/y/z), world_axis (x/y/z/-x/-y/-z),
roll_deg. The tool derives rotation, including reflection. Choose correct semantic
axis (tube/cylinder local Z), world direction and roll; do not also edit that part's
rotation. Catalog size remains frozen. Groups derive member rotations themselves.

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
Use scalar fields, not whole vectors or explanatory text as values. Named Cartesian
aliases position.x/y/z, size.x/y/z and rotation.x/y/z are accepted and normalized to
indices 0/1/2, with exactly the same value check. Other paths use numeric list indices.

Official references used to design this vocabulary (not code copied or backend used):
- https://openvsp.org/api_docs/latest/group___x_sec.html
- https://www.nasa.gov/reference/openvsp-wings/
- https://vspu.larc.nasa.gov/training-content/chapter-1-vspfundamentals/wings/wing-planform/
