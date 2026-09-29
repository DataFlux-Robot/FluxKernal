# Offline Lean ↔ URDF acceptance

FluxKernel 0.12.1 permits online software installation and asset acquisition, then
performs `fk robot to-lean` / `fk robot from-lean` entirely from local files.
Install Python/FluxKernel and Lean 4.34.1 first; missing assets or a missing runtime
produce errors, not automatic downloads. The converter directly invokes the
preinstalled compiler and bundled serializer, bypassing Elan/Lake launchers.
For a portable toolchain, set `FK_LEAN_BIN` to its actual `bin/lean` and retain
the distribution's standard library. See [setup and commands](LOSSLESS_ROBOTS.md).

## Acceptance method

Linux libseccomp denies socket creation, connection and send syscalls in the test
process and descendants. Each run first verifies that a socket probe fails with
`EPERM`. This was enforced at the OS level, not simulated with a bad proxy or a
mocked HTTP client. `strace -f -e trace=network` captured the four native cases:
the only socket call was the deliberately denied harness probe. Conversion itself
made no traced network calls. The harness is a test tool, not a complete sandbox
for arbitrary untrusted code.

Tests also remove PATH tool entries and point `ELAN_HOME` at an empty directory,
using only `FK_LEAN_BIN` to identify the actual installed compiler. A separate
test verifies that a missing compiler never executes an Elan-style launcher.

## Results

| Enforced offline check | Result |
| --- | --- |
| Microduck, XGO Duck and both personalized variants | 4/4 accepted |
| Original sealed files restored byte-for-byte | 226 / 208 / 251 / 229 files respectively |
| Native → Lean → native → Lean | Identical Lean source for all four cases |
| Move Lean package before restoring | All four cases pass |
| Remove source XML from URDF-only Lean package, regenerate via real Lean | All four cases preserve the full XML information tree |
| Pinned Awesome Robot Descriptions document cases | 295/297 accepted |
| Pinned Awesome Robot Descriptions complete asset packages | 62/297 accepted |

The catalog counts match the preceding online-environment audit. The two document
failures are malformed/non-standalone source XML. The complete-package limitation
remains explicit: ROS package/other URIs, parent-relative paths, absent resources
and Xacro need further interoperability work. An offline runtime is not a claim
that all catalog robots are already supported; see the
[full audit](AWESOME_URDF_AUDIT.md) for the denominator and failure classification.

The follow-up [full-catalog bidirectional suite](BIDIRECTIONAL_CATALOG.md) expands
these checks into separate per-file direction results, edit propagation and
negative tests for every catalog case, with the same enforced offline execution.

The guarantee covers FluxKernel's canonical data-only Lean document package,
not arbitrary Lean programs or external Lake projects. No new physical correctness
theorem is claimed. Keep all asset and optional native sidecar files when moving
a package. Original XML is needed only for lexical byte identity (comments and
formatting), not for reconstruction of the complete parsed XML tree.

## Reproduce after online preparation

```bash
# Acquire the pinned corpus first, as documented in AWESOME_URDF_AUDIT.md.
python scripts/without_network.py python scripts/benchmark_awesome_urdf.py \
  .demo/awesome-urdf/inventory.json --output .demo/offline-documents --workers 4
python scripts/without_network.py python scripts/awesome_urdf_packages.py \
  .demo/awesome-urdf/inventory.json .demo/awesome-urdf/assets-final.json \
  --output .demo/offline-packages.json

# Accepts any list of already sealed native bundles:
python scripts/without_network.py python scripts/benchmark_offline_roundtrip.py \
  ./microduck-bundle ./xgoduck-bundle --output .demo/offline-native.json

# Fresh environment: online wheel/dependency installation, then enforced offline checks:
python -m build
python scripts/smoke_distribution.py \
  --wheel dist/fluxkernel-0.12.1-py3-none-any.whl --robot --offline
```

Archived evidence: [native cases](releases/2026-09-29-offline-urdf-evidence/native.json),
[documents](releases/2026-09-29-offline-urdf-evidence/documents.json),
[complete packages](releases/2026-09-29-offline-urdf-evidence/packages.json),
[network trace](releases/2026-09-29-offline-urdf-evidence/network.trace),
[tests](releases/2026-09-29-offline-urdf-evidence/tests.txt),
[installed-wheel check](releases/2026-09-29-offline-urdf-evidence/wheel.txt),
[runtime and artifact hashes](releases/2026-09-29-offline-urdf-evidence/receipt.json).
