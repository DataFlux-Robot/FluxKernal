# Public robot document library acceptance — 2026-09-29

This release publishes a 295-case index and 220 licensed Lean/URDF source pairs.
The remaining 75 entries retain provenance and test status without redistributing
the model. See the [library](../../../robots/README.md) and its per-case notices.

## Executed checks

- [220 bundled documents](library-verification.json) passed source hashes,
  canonical data checks and actual local Lean execution; 75 indexed-only entries
  are reported separately. [Offline log](library-verification.log).
- [All 295 Lean values](local-generation.json) were reproduced byte-for-byte from
  the authorized local pinned corpus, with socket syscalls denied and zero model
  calls. [Build log](build-local.log). This does not grant redistribution rights.
- The documented G1 render command ran under the same network denial. [Log](render.log).
- [Focused tests](tests.txt) cover the published library, changed-source rejection,
  deterministic local materialization and onboarding.

Commands, after installing dependencies and the pinned Lean toolchain:

```bash
python scripts/without_network.py python scripts/robot_library.py verify --execute --output library-verification.json
python scripts/without_network.py python scripts/robot_library.py build-local --inventory .demo/awesome-urdf/inventory.json --output .demo/local-library
python scripts/without_network.py python scripts/robot_library.py render 0cca1c214e6157b37fab --output g1.urdf
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_robot_library.py tests/test_onboarding.py -q
```

These checks concern document preservation. The separate full-catalog audit still
records 295/297 document round trips and 62/297 complete asset-package round trips.
The promotional image is a generated concept illustration, not a test rendering.
