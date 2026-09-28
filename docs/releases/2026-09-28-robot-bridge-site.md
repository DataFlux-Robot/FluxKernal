# FluxKernel native robot bridge announcement — 2026-09-28

Status: **Published** over trusted public HTTPS through the existing Cloudflare setup.

- FluxKernel English/Chinese READMEs and native robot guide updated; repository remains private. Announcement commit: `1d85e98`.
- Published routes: `/technology/index.html` and `/technology/fluxkernel/index.html#robot-bridge`.
- Source commit in local FLUXLOOP_SITE: `30307790583c21d433a6c7dd4f5faf9d9f7a3eb6`.
- Pages repository: `ExuberantWitness/FLUXworkbench`, branch `gh-pages`, root `/`.
- Pages deployment: `4e6feb6e4fdd15b30a485e9f9d30580ffc900a02`; build `built`, empty error, exact commit match.
- Scope: two regenerated pages and seven new public evidence/image/license files. Existing product cases and all other published pages retain their baseline bytes.
- Claims: native design produces Lean structural evidence and URDF/MJCF projections. Microduck/XGO and additive variants have actual proof and numerical checks. General URDF import, bidirectional lossless conversion and formally proven export equivalence remain open.
- GLM personalization is labeled GLM-5.3-Flash, finite budget of at most three rounds per run, model-owned selection. No new model design run was performed for this publication.
- Public extracts contain verification summaries, rendered figures and source attribution. Raw prompts, credentials, private implementation and XGO hardware files were not exported.

## Validation

Typecheck, production build and full static export passed. The release payload was
assembled from the current Pages baseline with only the declared route/assets update.
The static audit passed 19 pages and 635 references. Local/live Chromium verified
8 page/viewport combinations, 12 product/equipment interactions, video playback,
and the new bridge at 1440/390/320 pixels including its evidence and attribution links.
Strict browser runs unset `NODE_TLS_REJECT_UNAUTHORIZED`; browser HTTPS errors were
not ignored. Independent httpx and SSL checks also performed trusted validation.

Thirty relevant published files match local SHA-256 hashes at both ordinary and
cache-busted URLs. Public TLS 1.3 passes hostname/certificate validation, with
Google Trust Services certificate SAN `*.datafluxdynamics.ltd`.

GitHub-origin certificate remains null, `https_enforced=false` and its origin
HTTPS-eligibility flag is false under the existing Cloudflare proxy. The primary
custom domain is valid and served by Pages. This is a successful public HTTPS
publication, not a claim that GitHub-origin HTTPS has been configured. No domain,
DNS, certificate or repository visibility settings were changed.

## Source state and reproduction

The website workspace had pre-existing unrelated tracked and untracked changes.
They were preserved. Only the requested page sources, stylesheet, new evidence
export/check scripts and their assets were committed for this task. The source
worktree therefore retains unrelated changes; the deployment worktree is clean.

Export evidence with `scripts/prepare-fluxkernel-robot-bridge.py ../fluxkernel`, then
follow `docs/GITHUB_PAGES_RELEASE_SOP.md` for build/static export. The scoped payload
uses the current deployment plus the rebuilt two HTML files and
`public/fluxkernel/native-robots/`. Never replace unrelated live routes from the
whole working-tree export without reviewing their diff.

Rollback: revert Pages commit `4e6feb6` on `gh-pages` and push normally.

Evidence is archived in [this directory](2026-09-28-robot-bridge-site-evidence/).
