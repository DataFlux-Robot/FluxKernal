# Awesome Robot Descriptions robustness audit

Date: 2026-09-29. Runtime: FluxKernel 0.12.1.

All **114 URDF-labelled catalog entries** were inventoried at
[catalog commit 706eccf](https://github.com/robot-descriptions/awesome-robot-descriptions/blob/706eccf089099055241d7829f9a1d8108353fbce/README.md).
Their linked file/directory/repository scopes contain **297 distinct URDF paths
across 75 repositories**. Paths shared by multiple catalog entries are tested once
and attributed to every relevant entry. This is a snapshot of those scopes, not
every URDF ever published by those robot vendors. Xacro/MJCF-only entries are outside
the denominator. Two build-system submodules in scope were inspected and contain
no additional URDF files.

## Results

| Check | Result | Meaning |
| --- | ---: | --- |
| Catalog entry coverage | 114/114 | Every linked URDF scope received a recorded disposition |
| Pinned source acquisition | 297/297 | Source hashes verified, including an explicitly resolved Git symlink |
| Original document round trip | 274/297 | Before namespace support was repaired; one failure was the acquisition alias |
| Final document round trip | **295/297** | Real Lean execution, whole XML tree equality, same Lean data on return, no original XML needed for reconstruction |
| Complete geometry package before resource fixes | 56/297 | Measured after namespace repair; includes independent checking for missing secondary resource files |
| Final complete geometry package | **62/297** | Exact URDF, mesh, material, texture and buffer bytes plus identical Lean return trip |
| URDF skill generation check | 188 passed / 107 rejected / 2 not generated | An additional validator with its own supported subset; not equivalent to either round-trip check |

At catalog-entry level, 113/114 entries have at least one successful document case;
112/114 have all their inventoried document cases pass. For complete packages,
24/114 have at least one passing case and 19/114 have every case pass. A folder may
contain many configurations or templates, so file counts are not robot counts.

The asset collector obtained **3,395 pinned resources (2.250 GB)**, including OBJ
material files, COLLADA textures and glTF/GLB buffers/images. Its conservative
dependency resolver found complete local closures for 256/297 inputs; 41 have
missing or ambiguous references or invalid source documents. Those availability
results are separate from the converter's ability to package the resources.
All 3,395 scheduled resource downloads succeeded; unresolved references were
retained as failures and were not silently removed from the case denominator.

This audit made **zero model calls** and executed no upstream Python, Xacro,
firmware or build generators. It validates description preservation and bounded
resource packaging. It does not certify dynamics, physical feasibility, arbitrary
simulator acceptance or robot deployment. The complete-document Lean serializer
is executed; this is not a new proof of a general XML round-trip theorem.

## Remaining complete-package failures

| First blocking condition | URDF paths |
| --- | ---: |
| `package://` and other URI references need explicit resolution | 206 |
| Parent-directory asset references need a bounded source-root layout | 17 |
| A referenced relative resource is absent at the declared location | 8 |
| Unexpanded Xacro requires an explicit expansion stage | 2 |
| Source XML is not a standalone well-formed document | 2 |
| **Total not passing complete-package conversion** | **235** |

These are the first observed blockers, not mutually exclusive descriptions of
all defects in each file. The asset collector may locate a resource through an
explicitly recorded unique suffix; the public converter is tested on the original
paths and does not receive a silently rewritten URDF or relaxed filesystem root.

The two source-XML cases are:

- Berkeley Humanoid's `urdf/gazebo.urdf`, a multi-root Gazebo fragment. Other robot
  files in that entry were still tested.
- Roboschool Fetch's `robots/fetch.urdf`, which uses an undeclared `sensor:` prefix.

Seven stale catalog links were resolved explicitly to the same robot's upstream
source: the PiPER branch, five TRON2 paths and Go1's repository path. The original
URLs, corrected URLs and exact commits remain in the inventory. TALOS's
`urdf/pyrene.urdf` is a Git symlink; the initial raw download exposed its target
string as XML. The final acquisition resolves its in-repository target explicitly
and records both identities. It is not counted as a repaired converter bug.

## Fixes driven by this audit

1. Preserve namespace prefixes, declarations and scoped bindings in the complete
   Lean tree. This fixes 20 document failures and also retains unused declarations
   previously discarded by XML namespace expansion.
2. Treat Gazebo plugin filenames as runtime metadata. They are not geometry assets
   and are not fetched or executed. Runtime-library deployment remains unverified.
3. Recursively bind OBJ/MTL, COLLADA, glTF and GLB dependencies. Six cases that passed
   direct-mesh checks but lost material/texture/buffer files now pass the complete
   closure check: PR2, Minitaur, three Laikago variants and Perseverance.
4. Reject unexpanded Xacro in complete asset packages instead of treating an
   incomplete template as a deployable robot. Document-only preservation remains
   separately testable.
5. Avoid repeatedly copying the remaining Lean source while reading each string
   literal. This reduces parser allocation without changing the grammar.

The next interoperability work is package-name resolution and explicit asset-root
handling. These should retain original URDF bytes and bindings while providing a
separate consumer-resolved view. Silently deleting plugins, replacing mesh paths
inside the only source document, or weakening path checks would not establish
losslessness.

The same 297 local inputs were subsequently rerun under enforced network denial
with the direct, preinstalled Lean runtime. See [offline conversion](OFFLINE_URDF.md)
for that separate acceptance run. Online catalog/asset acquisition is a preparation
step, not part of the offline conversion workflow.

## Evidence and reproduction

- [All 114 catalog entries](releases/2026-09-29-awesome-urdf-evidence/catalog-results.md)
- [All 297 file results](releases/2026-09-29-awesome-urdf-evidence/cases.csv)
- [Pinned inventory](releases/2026-09-29-awesome-urdf-evidence/inventory.json)
- [Final document results](releases/2026-09-29-awesome-urdf-evidence/documents-final.json)
- [Final package results](releases/2026-09-29-awesome-urdf-evidence/packages-final.json)
- [Dependency acquisition](releases/2026-09-29-awesome-urdf-evidence/assets.json)
- [Independent skill checks](releases/2026-09-29-awesome-urdf-evidence/skill.json)
- [323 tests](releases/2026-09-29-awesome-urdf-evidence/tests.txt) and
  [installed-wheel smoke](releases/2026-09-29-awesome-urdf-evidence/wheel.txt)
- [Microduck/XGO four-case regression](releases/2026-09-29-awesome-urdf-evidence/native-regression.json)

Use Python 3.12+, `.[robot]`, the pinned Lean toolchain and authenticated `gh` for
GitHub tree queries. Original assets remain local, with repository and content
identities recorded; this evidence directory does not redistribute mesh models or
claim rights under a single blanket license.

```bash
# Exact snapshot replay; no moving-branch substitution:
python scripts/awesome_urdf_corpus.py .demo/awesome-replay \
  --pinned docs/releases/2026-09-29-awesome-urdf-evidence/inventory.json
python scripts/awesome_urdf_assets.py .demo/awesome-replay/inventory.json \
  --output .demo/awesome-replay/assets.json
python scripts/benchmark_awesome_urdf.py .demo/awesome-replay/inventory.json \
  --output .demo/awesome-replay/documents --workers 4
python scripts/awesome_urdf_packages.py .demo/awesome-replay/inventory.json \
  .demo/awesome-replay/assets.json --output .demo/awesome-replay/packages.json
```

Use a fresh output directory for a changed implementation. The installed URDF
skill's generation check is optional for reproduction and is invoked through
`scripts/awesome_urdf_skill_check.py --urdf-tool /path/to/skill/scripts/urdf` with
the inventory, document-results directory and `--output` report. Its 107 rejections
include source constraints, unexpanded expressions, resource layout and unsupported
joint forms; they are not automatically classified as lossless-converter errors.
The local CAD Viewer startup failed because its installed package lacks
`agent:start`, so no new interactive visual acceptance is claimed.
