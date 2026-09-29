# Third-party materials

FluxKernal's original converter and library tooling retain the repository's MIT
license. That license does not replace upstream licenses for robot model data.

## Robot document collection

`robots/index.json` records all 295 successful document cases from the pinned
Awesome Robot Descriptions audit. The 220 cases under `robots/models/` include
unmodified upstream URDFs, generated Lean representations and accompanying license
texts/notices. Each model's original license applies to the model and its adapted
Lean form. Consult its `NOTICE.md` and `LICENSE.txt` before reuse. Copyleft and
share-alike obligations continue to apply independently of the converter's MIT
license. Source and modification information are included per case.

The remaining 75 entries are provenance/test records only. Model bytes are not
bundled where distribution restrictions, unclear license scope or unresolved
release obligations remain. The presence of a repository on GitHub or in a robot
catalog is not itself a redistribution grant. All exact dispositions and pinned
source/license links are recorded in the [index](robots/index.json).

The collection contains XML robot descriptions, not third-party mesh or texture
files. Referencing an external URI does not license that external resource.

## Existing project assets

Bundled frontend/vendor files retain their in-file or adjacent license notices.
Historical benchmark evidence identifies its sources and contains measurements,
hashes and metadata. Promotional artwork provenance is recorded in
[`docs/media/ARTWORK.md`](docs/media/ARTWORK.md).
