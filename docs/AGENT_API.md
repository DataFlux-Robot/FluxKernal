# Local revision API v1

A revision changes named numeric parameters in a verified parent snapshot. It cannot
rewrite requirements, manufacturing routes, part identities, material selections,
catalog data or the frozen numeric contract. This is a bounded local editing API,
not a model agent, arbitrary CAD program runner or public multi-user service.

Install the `demo` extra for preview and execution. `fk schema revision`, inspection
and the standalone nominal check module do not need a geometry engine.

## Complete example

```python
from fluxkernel.studio import generate_task, apply_revision
from fluxkernel.revision import inspect_run, preview_revision

base = generate_task("enclosure", output_dir="./runs")
state = inspect_run(base.directory)
patch = {
    "schema": "fk-revision-v1",
    "base_manifest_sha256": state["manifest_sha256"],
    "edits": [{"part": "housing", "set": {"wall": 3.0}}],
}
preview = preview_revision(base.directory, patch)
if preview["accepted"]:
    result = apply_revision(base.directory, patch)
    print(result["state"], result.get("reuse"))
    if result["ok"]:
        print(result["run"]["proof_accepted"])
else:
    print(preview["diagnostics"])
```

This example changes one housing, preserves 23 product/equipment entities, and
reruns the manufacturing plan and proof. A wall of 5 mm is rejected because the
frozen wall bound and payload clearance fail. No model or API credential is used.

## CLI

```bash
fk task enclosure --output ./runs --require-proof --json
fk inspect ./runs/<id> --json
fk schema revision
fk revise ./runs/<id> --patch change.json --preview --json
fk revise ./runs/<id> --patch change.json --require-proof --json
fk benchmark --output ./revision-evaluation
```

Copy the actual `manifest_sha256` from inspection into `change.json`; never use the
placeholder below as a real digest:

```json
{
  "schema": "fk-revision-v1",
  "base_manifest_sha256": "<64-character SHA-256 from fk inspect>",
  "edits": [{"part": "housing", "set": {"wall": 3.0}}]
}
```

`size`, `position`, and `rotation` are three-element arrays; `wall` is a number.
Dimensions/positions are millimetres and rotations are XYZ degrees. Whole-vector
updates avoid ambiguous array-index patch behavior. At most 64 distinct part edits
are accepted; unknown fields and non-finite numbers are rejected. Catalog parts
cannot be resized; they need a qualified replacement workflow outside API v1.

CLI exit codes: **0** = accepted preflight or completed execution, **2** = rejected
revision, **1** = execution/configuration error or missing required proof. Add
`--require-proof` to require Lean acceptance for a completed execution. A successful
preview has `geometry_evaluated: false`: it has not built B-reps or run Lean yet.

## What happens to evidence?

1. Read and verify the parent manifest and its committed files. The request pins the
   exact manifest bytes, detecting stale or altered parents.
2. Copy the design and apply only the allowed local edits. Edited observations become
   design selections, never new claims about the original image.
3. Evaluate the inherited contract and derive equipment dimensions again. Report
   changed/reusable parts, affected manufacturing descendants and failed checks.
4. Revalidate the request and snapshot in the isolated worker. Unchanged STEP/STL,
   meshes and geometry-check records are reused only from the verified snapshot.
5. Rebuild changed CAD, all input-bound manufacturing receipts, the plan and Lean
   evidence. A reused solid is not a reused proof of the changed manufacturing plan.
6. Write a new run directory. A rejected attempt contains its request, diagnostics
   and status but no fabricated CAD result. The parent remains available.

The same contract inheritance also applies to the older model-driven Studio revision
path: it cannot silently drop the numeric contract when modifying a fixture.

`apply_revision` returns `fk-revision-result-v1`. `ok` means the worker completed with
its declared nominal constraints satisfied; inspect `run.proof_accepted` and
`run.physical_status` separately. Worker timeouts raise `StudioError` and mark their
partial run as failed. Invalid non-JSON Python inputs may raise `ValueError` before
an attempt can be serialized.

## Constraint vocabulary v1

| Kind | Check | Explicit limits |
| --- | --- | --- |
| `dimension` | Inclusive range for `size.x/y/z` or constructive `wall` | Wall only on shell/frame/tube recipes |
| `inside-shell` | Minimum of six nominal gaps from a box to a shell cavity | Unrotated box/shell; includes floor and open-top plane |
| `radial-fit` | Sleeve bore minus shaft diameter, plus coaxial/axial-span checks | Unrotated Z-axis cylinder/tube; diametric, not radial, clearance |
| `axis-distance` | Absolute center separation along X, Y or Z | Does not verify holes, orthogonal alignment or full mating geometry |

Comparison tolerance is `1e-9` mm for floating-point arithmetic, not a manufacturing
precision claim. Unsupported rotated fits fail explicitly. Numeric constraints are
checked by Python and independently rechecked by the exported bundle verifier. Both
the contract and checker-source hashes are bound into the frozen input and receipts.
**They are not part of the Lean theorem.** Lean separately checks the finite
manufacturing plan under declared external assumptions.

An older run without `constraints.json` has coverage
`no-numeric-constraints-declared`. Its original text requirements remain unchanged
by a local patch, but they have not become executable engineering checks.

## Diagnostics

| Code | Meaning / recovery |
| --- | --- |
| `REV_STALE_PARENT` | Inspect the intended parent again; decide whether to rebase the edit |
| `REV_PARENT_CHANGED` | A committed artifact was modified; restore a trusted snapshot |
| `REV_PARENT_INVALID` | Missing/invalid manifest, design or contract data |
| `REV_PARENT_TOO_LARGE` | Snapshot exceeds the current 512 MiB limit |
| `REV_REQUEST_INVALID` | Schema, identity, vector or numeric value is invalid |
| `REV_PROTECTED_FIELD` | Edit attempts to change something outside the numeric vocabulary |
| `REV_CATALOG_IMMUTABLE` | Purchased geometry needs sourced replacement data |
| `REV_UNKNOWN_PART` | Named product part does not exist in this parent |
| `REV_GEOMETRY_PARAMETERS` | Candidate violates the finite recipe schema |
| `REV_CONSTRAINT_FAILED` | A named frozen interface requirement fails |

Schema identifiers are versioned. New incompatible operations require a new version;
existing diagnostic meanings are not repurposed. No remote transport or external
plugin ABI is promised by this local API.

## Reproducible task suite

`fk benchmark` runs enclosure clearance, shaft/sleeve fit and mounting-datum spacing.
For each authored fixture it generates a baseline, applies a valid patch, rejects an
invalid patch, compares reused CAD byte-for-byte, checks parent/contract preservation,
requires Lean and runs the independent bundle verifier. Reports retain all run paths
and individual check results. Repeated evaluations create new run IDs and summary files.

These are regression tasks for specific nominal constraints. They do not measure a
model's ability to infer an arbitrary product, satisfy an unseen requirement or build
physical hardware. There are no model calls and no claimed physical test results.

## Trust and portability

A manifest is an integrity snapshot, not a signed attestation. Trust in its originating
requirements must come from outside the patch operation. The exported verifier checks
the child's declared contract and its binding to the plan; validating inheritance
against an independently trusted parent also requires that parent snapshot.

The prototype assumes local filesystem ownership. It is not an access-control boundary
against another process that can rewrite all files. Parent snapshots are limited to
4,096 manifest entries and 512 MiB, and reject missing or escaping artifact paths.
