# Checked design definitions — acceptance, 2026-09-29

- **360 project tests passed**: [full log](full-tests.txt).
- **26 focused design tests passed**, including independent Lean rejection of
  false closure, false geometry membership and unmet thickness obligations:
  [final log](tests-final.txt).
- **Five exact-rational configurations received real Lean certificates**, and
  **15 invalid configurations were rejected**. Generation ran with Linux socket
  syscalls denied: [log](showcase.log), [full example and certificates](../../demos/design-definitions/README.md).
- Every published certificate was subsequently regenerated and checked again.
- The final wheel was installed in a clean environment outside the repository;
  core and design certification/verification passed with runtime network denied:
  [installed-wheel log](wheel-smoke-final.log).
- Browser checks exercised valid/invalid modes and mobile layout, with HTTP(S)
  requests blocked and no JavaScript errors: [browser receipt](browser-check.json).
- [Hashes and acceptance receipt](receipt.json) bind the implementation and artifacts.

Reproduce the design checks after installing dependencies and Lean:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_design.py -q
python scripts/without_network.py fk design demo --output design-demo
python scripts/smoke_distribution.py --wheel dist/fluxkernel-0.13.0-py3-none-any.whl --design --offline
```

The design certificates prove the generated finite expression obligations.
The separate parallelogram-family lemma is universally quantified over rational
parameters under its unit-circle assumption. Neither result establishes continuous
dynamics, global collision freedom or physical manufacturability. Python parsing,
elaboration and source binding remain part of the stated trust boundary.

## Existing URDF exchange regression

All **297** pinned files were retested in both directions under OS-level network
denial. Results remain **295 document round trips** and **62 complete asset-package
round trips**. Every per-case/per-check status matches the previous audit; the
three conversion-module hashes are unchanged. Two malformed/non-standalone XML
inputs and the previously documented asset-resolution limitations remain.
[Full report](urdf-regression.json) · [Offline log](urdf-regression.log).

```bash
python scripts/without_network.py python scripts/benchmark_urdf_bidirectional.py .demo/awesome-urdf/inventory.json .demo/awesome-urdf/assets-final.json --output urdf-regression --workers 4
```

The corpus and assets are acquired before the offline run. This report contains
metadata/results only; it does not redistribute restricted upstream models.
