# Lossless Lean ↔ URDF cases (v0.12)

Microduck and XGO Duck can now travel through a **complete Lean document package**
and return with the same URDF, meshes and sealed native files. The older finite
Lean proof instances remain separate: a proof certificate is not a complete robot.

## Commands

Install `.[robot]` and the pinned Lean toolchain. Output directories must be new.

```bash
# Complete native bundle: retain control contracts, source identity, BOM and proofs.
fk robot to-lean ./microduck-bundle --output ./microduck-lean
fk robot from-lean ./microduck-lean --output ./microduck-restored
fk robot verify ./microduck-restored --require-proof
fk robot check-projection ./microduck-restored

# URDF-only input: preserve what this document actually contains.
fk robot to-lean ./robot.urdf --output ./robot-lean
fk robot from-lean ./robot-lean --output ./robot-restored
```

Both conversion commands execute the installed Lean renderer and fail if Lean is
unavailable or its output changes the XML information tree. They do not call a model.

## Representation and losslessness ledger

`Robot.lean` contains a `Document` with recursive `Node.element` / `Node.text`
constructors, ordered attribute records, nested elements and text. Thus origins,
joint axes and limits, all inertial tensor entries, visual/collision occurrences,
material fields and mesh scale/URIs are present in the Lean value. Decimal strings
retain their original spelling and precision; this route never converts RPY to
quaternions, diagonalizes inertia or rewrites meshes. URDF SI units and all frame
conventions are inherited unchanged. No dimensions, signs or physical data are
inferred. This XML-level representation complements the native design/proof model;
it does not give every XML attribute a physical theorem.

| Level | Guarantee and mechanism |
| --- | --- |
| URDF information | Full parsed element/attribute/text tree equality after actual Lean rendering, including exact numeric lexemes |
| Mesh/texture assets | Original relative references and bytes; SHA-256 resource list in the Lean document |
| Lexical XML | Original bytes, including formatting/comments/declaration, retained in `source.urdf`; its digest and parsed tree must match Lean before reuse |
| Full native model | Optional `native/` sidecar restores every manifest-covered file plus the manifest itself byte-for-byte, including controller/BOM/source/evidence fields |
| Lean return trip | For an unchanged complete package, converting restored URDF/native files back produces the same `Robot.lean` bytes |

The original XML is **not needed for semantic reconstruction**: removing
`source.urdf` from a URDF-only package still allows Lean to produce the whole robot.
Without that lexical snapshot, whitespace, comments, quote style and the XML
declaration are not promised byte-identical. With it, the original URDF bytes are
restored only after independent equality checking. A native sidecar can also supply
the original sealed URDF bytes after the same check.

Ordinary URDF cannot carry FluxKernel's controller contracts, BOM and proof history.
Those fields are preserved in the bound native sidecar, not invented from plain
URDF or hidden inside a claim that ordinary URDF expresses them. Meshes similarly
remain external assets, as in a normal robot description package.

## Editing and trust boundary

The canonical constructor subset is parsed without executing user code. It is
regenerated into a temporary project using the installed Lean module; supplied
package build scripts, arbitrary `#eval`, imports and IO programs are rejected.
Changes to referenced resources, missing resources and stale XML/native bindings
fail closed. SHA-256 binds content; it does not authenticate an author.

A standalone Lean document can be edited within this constructor subset. Remove
an obsolete lexical snapshot before exporting an intentional semantic edit. Native
sidecars cannot accompany incompatible edits: make a native revision and generate
a fresh package. Otherwise old control contracts could incorrectly attach to a
changed mechanism. The tests change an exact long decimal in Lean with no original
XML present and verify the newly rendered value.

The full-document route is for the local relative-asset descriptions used by these
cases. Namespaced XML, DTD/entities, remote/package URIs and excessive XML depth or
size are rejected explicitly. XML-extension data is retained, but no unsupported
simulator semantics are claimed merely because the data survives. The separate
`import-urdf` command has the stricter native semantic subset documented in
[URDF_BRIDGE.md](URDF_BRIDGE.md).

The Python XML parser, constructor reader, file hashing and equality checks remain
trusted software. Lean executes the serializer; this release does **not** prove a
general XML parser/serializer round-trip theorem or physical correctness. Existing
structural and mechanism-field certificates continue to have their stated scope.

## Reproduce case acceptance

```bash
python scripts/benchmark_lossless_robots.py \
  --input microduck=/path/to/microduck-bundle \
  --input xgoduck=/path/to/xgoduck-bundle \
  --output ./lossless-cases
```

The benchmark checks both directions, all sealed bytes, unchanged source files,
actual proof reexecution, numerical consumers and an additional standalone export
with neither original XML nor a native sidecar. Full models stay local; the private
release record stores hashes, results and reproducible Lean data documents.
