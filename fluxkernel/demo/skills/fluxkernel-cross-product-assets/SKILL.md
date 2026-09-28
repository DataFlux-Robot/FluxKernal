---
name: fluxkernel-cross-product-assets
description: Publish, match and instantiate FluxKernel component, module and equipment recipes across product families using the asset CLI or MCP tools.
---

# Cross-product recipe reuse

Use functional categories and declared interfaces to find assets. A car, truck,
aircraft or humanoid label alone establishes neither compatibility nor incompatibility.
When driving live image designs for this project, GLM-5.3-Flash makes asset choices
and design adaptations; the host supplies tools and checks. This skill is guidance
for the calling agent, not an automatic asset-selection stage in `fk perceive`.

1. Inspect the target with `inspect_run`. Preserve its requirements and obtain its
   manifest digest. Specify required ranges, units and interfaces from the target;
   do not relax them to make an available asset pass. Unknown ratings remain unknown.
2. Use `search_assets` and `inspect_asset`. `covers` means an asset's capability
   contains the required operating interval; `within` means its value/range fits
   inside the allowed envelope. A partial interval overlap is insufficient.
3. Choose direct reuse or named bounded parameters. Inspect integration obligations,
   including links to excluded parts and assembly drivers needing rebinding. Any
   parameter change expires declared capabilities and interfaces; only geometric
   measures are recalculated. Do not infer new load/electrical ratings from size.
4. Call `preview_asset` with pinned asset SHA-256, target manifest, namespace,
   rigid pose and optional source-to-target replacement IDs. Equipment replaces a
   complete recorded cell; declared work ranges must cover target machining envelopes.
   A compatible preview means declared nominal checks passed, not physical integration.
5. Call `instantiate_asset` only after accepted preflight. Read `asset-reuse.json`,
   `constraint-checks.json`, `geometry-checks.json`, `manufacturing.json` and `proof.json`.
   Imported geometry and plan evidence belong to the new run. Check `proof_accepted`
   separately from `ok`, and keep unresolved interface and physical obligations visible.
   Inspect history before retrying a timed-out write; instantiation is not idempotent.
6. Publish reusable recipes from verified runs with `publish_asset`: select a whole
   component, module or equipment cell, declare its local origin, parameter bindings,
   geometric measures and known interfaces. Record capabilities as publisher declarations.
   Never label authored/example procurement envelopes as supplier-qualified stock.

For CLI clients, use `fk schema asset-publish`, `fk schema asset-query` and
`fk schema asset-instance`; commands are `fk asset publish/search/inspect/preview/apply`.
All asset operations are deterministic and make no model calls themselves.

If requirements are missing or incompatible, retain the rejection and ask the
calling design workflow to resolve them. Limit retries to the caller's iteration
budget. Do not copy source application proof or visual acceptance into the target.
The original target remains unchanged; ordinary later revisions may regenerate the
default manufacturing cell, so inspect the resulting equipment rather than assuming
the reused cell persists across every workflow.
