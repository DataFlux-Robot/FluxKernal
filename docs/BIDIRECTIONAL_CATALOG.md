# Bidirectional checks for the entire Awesome URDF catalog

This acceptance suite covers all **114 URDF-labelled entries and 297 distinct
URDF paths** in the pinned Awesome Robot Descriptions snapshot, across 75 source
repositories. It is not restricted to Microduck/XGO or to cases already known to
pass. The inventory and explicit stale-link corrections are documented in the
[original audit](AWESOME_URDF_AUDIT.md). Xacro/MJCF-only catalog entries are outside
this URDF snapshot. Every in-scope file receives a row, including malformed XML
and unresolved resources.

## Recorded results — 2026-09-29

The full run used the harness at `d1e0393`, verified all 3,395 previously acquired
resource hashes and reexecuted every case under enforced network denial. All 297
source URDF hashes remained unchanged. The report is complete and its
`all_applicable_passed` field is **false**, because the failures below remain.

| Check | Passed | Failed | Blocked | Not applicable |
| --- | ---: | ---: | ---: | ---: |
| Document URDF → Lean → URDF | 295 | 2 | 0 | 0 |
| Document Lean → URDF → Lean | 295 | 0 | 2 | 0 |
| Lean edit reaches URDF, independently checked | 295 | 0 | 2 | 0 |
| Injected executable Lean rejected | 295 | 0 | 2 | 0 |
| Complete package URDF → Lean → URDF | 62 | 235 | 0 | 0 |
| Complete package Lean → URDF → Lean | 62 | 0 | 235 | 0 |
| Package reconstruction without original XML | 62 | 0 | 235 | 0 |
| Stale XML snapshot rejected after Lean edit | 62 | 0 | 235 | 0 |
| Package edit survives reimport, assets unchanged | 62 | 0 | 235 | 0 |
| Corrupted bound asset rejected | 47 | 0 | 235 | 15 |

The two XML failures are Berkeley Humanoid's multi-root `urdf/gazebo.urdf` fragment
and Roboschool Fetch's undeclared `sensor:` prefix. Neither can seed a valid reverse
document conversion. The 235 complete-package failures retain the earlier first
blockers: 206 URI references, 17 parent-relative paths, 8 absent relative resources,
2 unexpanded Xacro templates and those 2 invalid XML documents. Their complete
package reverse checks are blocked, not counted as passes. Every valid document
still receives both document directions regardless of its asset-package status.

All accepted complete packages survived the stronger checks. Fifteen contain no
external assets, so there is no bound mesh/texture to corrupt in those cases.
No additional document loss, stale-output acceptance or edit-propagation failure
was observed in this snapshot. Physical and simulator validity are outside these
counts. The converter's general resource compatibility remains unfinished.

**Review every robot and every file:**

- [All 114 catalog entries](releases/2026-09-29-bidirectional-catalog-evidence/catalog.md)
- [All 297 per-file direction results](releases/2026-09-29-bidirectional-catalog-evidence/cases.csv)
- [Detailed checks and blockers](releases/2026-09-29-bidirectional-catalog-evidence/report.json)
- [Network trace summary](releases/2026-09-29-bidirectional-catalog-evidence/network-summary.txt)
  and [complete compressed trace](releases/2026-09-29-bidirectional-catalog-evidence/network.trace.gz)
- [27 related regression tests](releases/2026-09-29-bidirectional-catalog-evidence/tests.txt),
  [10 passing CI jobs](releases/2026-09-29-bidirectional-catalog-evidence/ci.json),
  and [content-hash receipt](releases/2026-09-29-bidirectional-catalog-evidence/receipt.json)

The trace contains one network syscall: the intentionally denied harness probe.
No conversion network syscalls were observed. The new regression tests include a
fake renderer that always returns the original XML: unchanged round trips pass,
but the edit-propagation check correctly rejects it. This guards against mistaking
snapshot replay for a working conversion.

The installed CAD Viewer still lacks `agent:start`; its attempted handoff failed
([log](releases/2026-09-29-bidirectional-catalog-evidence/viewer.txt)). This run therefore
adds no interactive visual acceptance claim. Robot geometry is not modified by
the benchmark, and third-party model files remain in the local pinned corpus.

## What each case tests

1. **URDF → Lean → URDF:** parse the original document, construct its complete
   Lean XML value, execute real Lean, compare every element/attribute/text value.
   A second, namespace-expanded ElementTree oracle checks the result independently
   of the converter's Expat representation.
2. **Lean → URDF → Lean:** start a fresh Lean execution from the saved data term,
   rebuild its entire value from the rendered URDF, require identical Lean source,
   then execute the reconstructed term again. No original XML is supplied to the
   Lean execution. The lexical digest is retained as an opaque binding here;
   this document-only test does not assert possession of its external snapshot.
3. **Lean edit propagation:** change the robot name and, when present, one mass
   to a long decimal string. Execute the changed Lean term and check the expected
   XML using both oracles. Returning the old robot must fail. These are temporary
   test perturbations, not robot design changes or claims of physical validity.
4. **Executable rejection:** adding arbitrary Lean commands to the data document
   must be rejected by the canonical parser before execution.
5. **Public complete-package API in both directions:** use `to_lean` / `from_lean`,
   including original URDF byte equality, asset byte equality and exact Lean return
   trip. Check secondary resource closure against the independently acquired ledger.
6. **Relocation and XML-free reconstruction:** move the package, remove its XML
   snapshot, export URDF from Lean, reimport it, compare the full Lean value and
   resource bindings. Newly serialized XML has a different lexical digest, so this
   check deliberately does not claim identical original formatting or comments.
7. **Stale snapshot and asset corruption:** a changed Lean value paired with old
   XML must be rejected. Once that snapshot is removed, the edit must reach URDF
   and survive reimport without changing assets. Corrupting one bound resource
   must be rejected; robots without external resources are explicitly marked
   `not_applicable` for this last test.

The document lane preserves mesh URIs as XML values but uses empty external
resource tables. It cannot establish complete asset packaging. Complete-package
checks keep the existing strict API and do not rewrite URDF paths, delete plugins,
substitute geometry or silently repair upstream files to obtain a pass.

## Reproduction

Install dependencies and acquire the pinned URDFs/assets while online, following
the [offline setup](LOSSLESS_ROBOTS.md#online-setup-offline-conversion) and
[catalog acquisition commands](AWESOME_URDF_AUDIT.md#evidence-and-reproduction).
Then run the entire suite with OS-enforced network denial:

```bash
python scripts/without_network.py python scripts/benchmark_urdf_bidirectional.py \
  .demo/awesome-urdf/inventory.json .demo/awesome-urdf/assets-final.json \
  --output .demo/awesome-urdf/bidirectional --workers 4
```

Use a new output directory for every run. The harness verifies source and acquired
resource hashes, records runtime/harness hashes, never resumes cached successes,
and checks that every inventory case and catalog entry appears in the final report.
It makes no model calls and executes no upstream Python or Xacro generators.
`scripts/without_network.py` uses Linux libseccomp; installation may use the network,
but the test process and descendants cannot create sockets or send network requests.

Outputs are `report.json`, a per-file `cases.csv`, an all-entry `catalog.md` table,
and each case's Lean document, Lean-generated URDF and detailed result. `completed`
means all inputs received a disposition. `all_applicable_passed` is a separate
boolean. Add `--require-all` to fail the command if any applicable check fails or
is blocked. A malformed URDF cannot seed a valid reverse conversion; its forward
failure and reverse blocker remain in the denominator. The same rule applies when
an asset package cannot be constructed because of missing or unsupported references.

This suite evaluates data preservation and rejection behavior. It does not prove
robot dynamics, certify manufacturing feasibility, or establish a general Lean
theorem about arbitrary URDF programs.
