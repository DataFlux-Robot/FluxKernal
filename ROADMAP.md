# Roadmap: earn repeat use before optimizing visibility

FluxKernel aims to become a useful substrate for agents that design physical
systems. A large community is an outcome of useful work, reliable delivery and
contribution opportunities. No star count or arbitrary-product capability is promised.

## v0.2 — install, inspect, reproduce

Implemented in this iteration:

- English and Chinese entry documentation, a bounded first example and a public
  recorded-results showcase.
- `fk doctor` with human and JSON diagnostics; no hidden network/model calls.
- `fk demo` and the Python reference API, explicitly labeled reference mode.
- Proof resources and independent verifier included in wheels and source archives.
- Writable run directories outside installed packages; original checkout history
  remains compatible.
- A fresh-environment distribution check, including actual CAD, Lean and rejection
  of a tampered output.
- Contribution templates and CI definitions for the core/platform and CAD/proof paths.

See `docs/releases/` for measured validation. A configured CI workflow is not the
same as a passing remote run; release records distinguish the two.

## v0.3 — bounded edits with frozen nominal constraints

Implemented: versioned inspection/preview/apply operations, pinned parent snapshots,
protected parameter patches, inherited contracts, verified CAD reuse, regenerated
manufacturing evidence, and a three-task regression runner. See
[the API guide](docs/AGENT_API.md). The numeric checkers are Python checks, separate
from the Lean plan theorem. Catalog replacement and physical validation remain open.

## Next gate — extend useful edits to qualified assemblies

Ship a bounded set of small engineering tasks: enclosure fit, shaft/bearing interface,
mounting bracket and fixture changes. For each task, publish the input, assumptions,
expected constraints, executable checks and baseline artifact set.

Acceptance criteria:

- An agent can request a local revision with stable part identities through a
  documented API, and inspect changed, reused and invalidated evidence.
- A failed operation leaves an actionable diagnostic and a recoverable parent.
- No required check can be turned into a pass by silently changing the requirement.
- Each published success is reproducible without a live model call; live-model cost,
  latency and failures are recorded separately.

## Next gate — interfaces and real manufacturing evidence

- Add interface types for mounting patterns, shaft fits, electrical connectors and
  material/process compatibility. Check incompatible connections explicitly.
- Replace catalog placeholders with sourced dimensions and provenance. Missing
  supplier evidence stays unresolved.
- Choose one affordable, physically testable assembly and one fixture. Measure fit
  and assembly outcomes against the exported design before broadening examples.
- Grow Lean coverage around translation correctness and composition contracts while
  keeping geometry, numerical approximations and external assumptions explicit.

## Next gate — an extension ecosystem

- Stabilize versioned agent operations, JSON schemas and diagnostic codes before
  adding an MCP or other transport adapter.
- Define external solver discovery and evidence contracts; require accepted/rejected
  examples for every new checker.
- Provide a reproducible evaluation runner for changes, using fixed tasks and budgets.
- Publish a compatibility policy, release notes and signed release provenance when
  distributing public packages.

## Public launch gate

The repository remains private until its owner explicitly changes that decision.
Before public launch, require clean-machine setup on supported platforms, validated
licenses/attributions, green distribution CI, a working issue triage path, private
vulnerability reporting and at least one external developer completing the quickstart
without maintainer intervention.

Track setup completion, time to first verified artifact, repeat use, successful
constraint-preserving revisions, reproducible failures and contributed adapters.
Stars are a secondary signal; do not buy them, gate features on them or invent users.
