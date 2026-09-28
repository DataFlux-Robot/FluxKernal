# Cross-product assets

FluxKernel v0.8 shares **component, module and manufacturing-cell recipes** between
verified design runs. Matching uses functional categories, interface identifiers and
unit-aware capability intervals. It is independent of the product-family label:
an auxiliary controller can be reused between car, truck, aircraft and humanoid
subsystems when the declared requirements match.

This is recipe reuse with fresh destination evidence. It does not establish that a
road-vehicle component meets aviation requirements, or that an authored catalog
envelope is a purchasable supplier part. The current model has scalar intervals and
exact interface identifiers, not general interface geometry or certification rules.

## Reproduce the end-to-end test

```bash
python -m pip install -e '.[demo,agent]'
fk asset benchmark --output ./asset-evaluation --json
```

Install the pinned Lean toolchain as described in [Quickstart](QUICKSTART.md) for
the benchmark's fresh-proof and independent-verifier checks. Each invocation creates
an isolated campaign containing a library, four baseline subsystem runs, all accepted
and rejected attempts, verifier logs and `benchmark.json`. These are authored
three-part subsystem contexts, not whole-product reconstruction or GLM output.

| Case | Expected result |
| --- | --- |
| Car auxiliary controller → truck / aircraft / humanoid | Three compatible recipe instances |
| Car shaft template → humanoid, 10 → 16 mm | Geometry recomputed; old torque rating invalidated |
| Car bracket-and-shaft module → aircraft, rotated 90° | Internal nominal contract retained in module frame |
| Car machining-cell recipe → humanoid | Complete cell replaced, new manufacturing plan |
| Small cell → larger truck mounting blank | Rejected by declared work envelope |
| 18–30 V controller → 400–800 V requirement | Rejected |
| Adapted shaft using the original torque rating | Needs evidence; not instantiated |

## Python workflow

```python
from fluxkernel.assets import AssetLibrary, publish, prepare_instance
from fluxkernel.revision import snapshot
from fluxkernel.studio import apply_asset

library = AssetLibrary('./shared-assets')
# source/target are existing completed run directories. Select actual source IDs.
asset = publish(library, source, {
    'base_manifest_sha256': snapshot(source)['identity'],
    'name': 'aux-controller', 'version': '1.0.0', 'category': 'aux-control',
    'kind': 'component', 'description': 'Auxiliary control envelope',
    'parts': ['control'], 'origin': [0, 0, 25],
    'capabilities': {'voltage': {'unit': 'V', 'min': 18, 'max': 30}},
    'interfaces': {'bus': 'example-can-v1'},
})
query = {
    'category': 'aux-control',
    'requirements': {'voltage': {'unit': 'mV', 'min': 24000, 'max': 28000}},
    'interfaces': {'bus': 'example-can-v1'},
}
print(library.search(query))
request = {
    'base_manifest_sha256': snapshot(target)['identity'],
    'asset_sha256': asset['asset_sha256'], 'prefix': 'shared',
    'query': query, 'position': [0, 0, 25],
    'replace': {'control': 'control'},  # optional: source ID → existing target ID
}
preview = prepare_instance(library, target, request)[0]
if preview['accepted']:
    result = apply_asset(target, library.root, request, output_dir='./runs')
    print(result['state'], result['run']['proof_accepted'])
```

The example capability values are illustrative publisher declarations. Omit unknown
ratings; do not invent them from the image. Omitting `replace` inserts new occurrences
as `<prefix>-<source-id>`. Pose uses millimetres and XYZ Euler degrees. Publication
subtracts `origin` from source positions; it does not implicitly rotate source axes.

## CLI and MCP

```bash
fk schema asset-publish --json
fk schema asset-query --json
fk schema asset-instance --json
fk asset publish SOURCE_RUN --spec publish.json --library ./shared-assets
fk asset search --query query.json --library ./shared-assets
fk asset preview TARGET_RUN --request instance.json --library ./shared-assets
fk asset apply TARGET_RUN --request instance.json --library ./shared-assets --output ./runs
```

MCP exposes `publish_asset`, `search_assets`, `inspect_asset`, `preview_asset` and
`instantiate_asset`. The server owns its library at `WORKSPACE/.assets`; callers do
not choose arbitrary output/library paths. Read-only mode hides publication and
instantiation. Asset schemas are in the tool definitions, including nested fields.
The packaged [agent skill](../fluxkernel/demo/skills/fluxkernel-cross-product-assets/SKILL.md)
describes the workflow. A calling agent must load it; it is not automatically loaded
into the current GLM perception loop. No model/provider configuration changes here.

## Compatibility, adaptation and evidence

- `covers` requires the asset's range to contain the complete requested operating
  domain; `within` requires the asset range to fit inside the target bounds. Matching
  reports `compatible`, `needs-evidence` or `incompatible` and explicit reasons.
- Parameters bind to `size.0/1/2`, `position.0/1/2` or `wall`. Bounds and defaults are
  checked. Procurement dimensions and independent semantic-envelope scaling are
  prohibited. Geometric `measures` derive values from the actual adapted recipe.
- Any non-default parameter invalidates **all** declared capability/interface facts.
  Dimension changes are not evidence of retained torque, thermal or electrical ratings.
  Assets with unresolved assembly/frame drivers cannot be parameter-adapted.
- Nominal constraints fully inside an asset are remapped into an `asset-frame`
  constraint. They survive rigid transforms and later revisions. Cross-boundary
  constraints and source assembly drivers become visible reintegration obligations;
  they are not silently imported as functioning destination drivers. Target assembly
  occurrences cannot be replaced until their drivers are explicitly rebound.
- Equipment assets capture a complete recorded cell. Replacement is allowed for a
  depth-one machining target only. Work-envelope matching uses recipe-axis dimensions;
  it does not account for fixturing, setup, spindle performance, reach or rigidity.
- The original target is immutable. Instances produce new CAD, source/instance
  records, manufacturing dependencies and a new plan proof. Exact unchanged target
  CAD can retain the existing byte cache. Imported CAD is rebuilt, not copied from
  the source. No old application proof or visual acceptance transfers.
- The bundle verifier checks asset/source commitments, final instance recipes,
  nominal contracts and the new manufacturing plan. It does not independently
  certify the publisher's capability declarations or physical performance.

Library records are immutable SHA-256-addressed JSON, with name and semantic version
as descriptive metadata. Changing a definition produces a different identity; there
is no automatic upgrade or enforced unique name/version registry. Product geometry
is limited by the existing Part vocabulary. Ordinary revision/PAL workflows can
regenerate the default manufacturing cell; inspect that output before claiming the
equipment instance persists. Automatic supplier qualification, library selection in
`fk perceive`, and measured cross-product performance transfer remain future work.
