# 2026-09-28 — FluxKernel public disclosure and current product cases

Published: https://www.datafluxdynamics.ltd/technology/fluxkernel/index.html

Scope: the FluxKernel page, its technology overview card, and their public case data.
The exact deployment retains all 19 existing routes; unrelated source changes were
preserved and excluded by overlaying only these paths on the current Pages baseline.

- Source implementation: `b794a34a18eb04ed7f238e9b3c07ebb629c433fe`.
- Pages repository: `ExuberantWitness/FLUXworkbench`, `gh-pages`, root `/`.
- Previous Pages commit: `4e6feb6e4fdd15b30a485e9f9d30580ffc900a02`.
- Published Pages commit: `09158f3dc6f60c87848d6457a410f0c133444180`; matching build `built`, error empty.

## Public information boundary

Lean 4 remains visible as a capability, with limited verification scope and physical
validation caveats. Internal data-model names, rule enumeration, proof/checker records,
source/workflow commitments and native-model digests were removed from page copy and
public JSON. Robot summaries use an explicit field allowlist. Private proof execution,
engineering evidence and the private FluxKernel repository are unchanged.

This reduces information in the current public payload. Previously published Git
history, downloaded copies and third-party caches are not erased by this release.
Public geometry remains intentionally viewable/downloadable for the interactive demo.

## Current display and actual run selection

| Case | Workflow | Recorded run (private provenance) | Budget / actual reviews | GLM selected | Status |
| --- | --- | --- | --- | --- | --- |
| Car | v0.6 | `d88574fcd83a4b9a` | 3 / 3 | Third review | needs-review |
| Aircraft | v0.7 | `0e14ac62392a42d5` | 3 / 2 | Second review | model-threshold-met |

Both use `glm-5.3-flash`. The most recent completed runs supply the displayed CAD,
with no manual geometry edits or candidate-selection override. The aircraft's later
six-round attempt failed before review and did not supersede the completed result;
this is disclosed in the public release summary. These are examples, not reliability
statistics. Aircraft model acceptance is not human acceptance or flight validation.
The car remains visually rough. Phone remains an explicitly labeled early recording.

The initial page now loads the updated aircraft. The 47-second old video is collapsed
under a clearly labeled historical archive. Real model identity, budget, actual reviews,
selected round and quality status remain visible. A private explicit case manifest
replaces the old v0.5 defaults. Content digests of public case files drive the existing
viewer cache version; review images have content-addressed filenames.

## Verification

- TypeScript typecheck and production build passed; static HTML regenerated.
- Exact payload audit: 19 routes, 635 references, no errors.
- Public-export verification: every indexed triangle reconstructed to the private
  source at display precision; all selected review PNG bytes match source runs.
  Triangle totals including equipment: phone 3,968; car 11,356; aircraft 46,266.
- Public field allowlists and forbidden internal identifiers passed.
- Local and live browser checks: 1440 / 768 / 390 / 320 pixels, eight route/viewport
  checks, twelve product/equipment interaction checks, no browser errors. Three more
  viewport checks cover robot images, capability boundaries and public summary links.
- 29 deployed files matched byte-for-byte at ordinary URLs, published version URLs
  and cache-busted URLs. All 19 live routes returned 200.
- Trusted TLS 1.3; Google Trust Services WE1; SAN includes `*.datafluxdynamics.ltd`;
  certificate expires 2026-12-27. No disabled certificate checks used.
- GitHub health reports the primary custom domain valid, proxied by Cloudflare and
  served by Pages. Origin `https_enforced=false`, no approved Pages certificate field,
  `is_https_eligible=false`. DNS/Pages settings unchanged. Status: **Published** over
  the existing trusted Cloudflare HTTPS endpoint; no claim of origin HTTPS enforcement.

The displayed 272 software tests are retained v0.10 runtime evidence, not newly run
engine tests for this website-only change. The release made no model calls.

Use the website release SOP in `FLUXLOOP_SITE/docs/GITHUB_PAGES_RELEASE_SOP.md`. Export and disclosure gates are
`scripts/prepare-fluxkernel-showcase.py`, `scripts/prepare-fluxkernel-robot-bridge.py`,
and `scripts/verify-fluxkernel-public-export.py`. Evidence is archived privately in
FluxKernel's matching `2026-09-28-showcase-refresh-evidence` directory.

Rollback, if needed: revert the published Pages commit and push normally; note that
reverting the whole change would restore the old public technical details.
