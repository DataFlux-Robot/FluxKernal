# FluxKernal robot document library

**295 indexed Lean document cases · 220 bundled Lean sources · 75 indexed-only cases.**

[Browse every case](CATALOG.md) · [Machine-readable index](index.json) ·
[Bidirectional benchmark](../docs/BIDIRECTIONAL_CATALOG.md) ·
[Library acceptance](../docs/releases/2026-09-29-public-library-evidence/README.md)

The index covers every successful XML document in the 297-file pinned Awesome
Robot Descriptions audit. A case is a file/configuration, so several cases may
describe one robot. Each entry records its source repository, exact commit, source
path, URDF hash, Lean hash, license disposition and full-asset benchmark status.

## What is included

Each bundled case has:

- `Robot.lean`: the exact canonical data term used in the successful benchmark.
- `source.urdf`: the unmodified upstream XML, retaining original comments/notices.
- `LICENSE.txt`, optional upstream notices and `NOTICE.md`: model license,
  attribution, transformation statement and source links.

These are **complete XML document forms**. External geometry files are not bundled.
URI strings are retained; the empty external-resource table is explicit. Use the
document-library renderer below to regenerate XML. The complete-package
`fk robot from-lean` command additionally requires bound, locally available assets;
this library does not bypass that requirement or imply 295 complete asset packages.

## Run locally, without model tokens

Install FluxKernal's Python package and Lean 4.34.1 beforehand. These commands
perform no downloads and make no model calls:

```bash
python scripts/robot_library.py list --query "G1"
python scripts/robot_library.py verify
python scripts/robot_library.py verify --execute
python scripts/robot_library.py render 0cca1c214e6157b37fab --output ./g1.urdf
```

`verify` checks every bundled file and its source/Lean correspondence. `--execute`
also compiles and runs real Lean for each of the 220 bundled cases. The report
separately counts indexed-only entries, which are not treated as bundled successes.
On Linux, enforce offline operation with:

```bash
python scripts/without_network.py python scripts/robot_library.py verify --execute
```

## Reproduce all 295 from authorized local sources

The deterministic generator can reproduce the recorded Lean bytes for every index
entry, including indexed-only entries, from caller-supplied pinned URDF files:

```bash
python scripts/robot_library.py materialize CASE_ID \
  --urdf /path/to/authorized/source.urdf --output .demo/local-model

# After acquiring the pinned corpus for a permitted use:
python scripts/robot_library.py build-local \
  --inventory .demo/awesome-urdf/inventory.json --output .demo/local-library
```

The local builder verifies the original URDF hash and the resulting Lean hash.
It never fetches a model automatically. Generated local outputs stay outside the
published library; local possession or conversion does not grant redistribution
rights. Review the entry's upstream terms before using or sharing it.

## Licensing and scope

The converter is MIT-licensed. **Robot descriptions and their adapted Lean values
retain their individual upstream licenses.** GPL/LGPL and share-alike models are
not relicensed as MIT. Original source, the transformation program, notices and
links to the pinned upstream source tree are retained beside the adapted value.
See [third-party notices](../THIRD_PARTY_NOTICES.md).

Seventy-five cases are indexed only: they have noncommercial/custom restrictions,
missing or conflicting license scope, or redistribution obligations that still
need review. In particular, the Gundam source explicitly restricts redistribution.
The index's exact `distribution_note` is the disposition for each case. These
entries contain provenance and test metadata, not a redistributed model file.

The conversion suite passed 295 document round trips and 62 full asset-package
round trips. This library does not certify dynamics, physical manufacture or a
universal translation theorem. Its promotional illustration is distinct from the
measured file-level evidence.
