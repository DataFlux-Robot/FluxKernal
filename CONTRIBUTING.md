# Contributing to FluxKernel

Start with a reproducible engineering problem: a missing recipe, a rejected valid
plan, an accepted invalid plan, an installation failure, or an operation an agent
cannot express. The repository currently requires collaborator access.

## Development setup

Use Python 3.12+ and a virtual environment:

```bash
python -m pip install -e '.[demo,dev]'
lake build
python -m pytest -q
```

For documentation and dependency-free CLI work, install `.[dev]` and run
`python -m pytest tests/test_onboarding.py -q`. The full suite needs the CAD extras
and pinned Lean toolchain. Tests must not require a paid API key.

Before changing the proof project, read [PROOF_PACKAGE.md](PROOF_PACKAGE.md).
Before changing solver behavior, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Keep changes reviewable

1. Describe a concrete input, current behavior and expected behavior.
2. Keep the smallest fixture that demonstrates the problem. For geometry, record
   dimensions, units, material assumptions and the failing operation.
3. Preserve the distinction between proposed designs, checked plans and physical
   evidence. A fake catalog match or a proof bypass is not a successful fallback.
4. Add a regression check when behavior or integrity changes. Test the rejected
   case as well as the accepted one when modifying a checker.
5. Run the relevant checks and state their results in the pull request.

For packaging changes also run:

```bash
python -m build
python scripts/smoke_distribution.py
python scripts/smoke_distribution.py --studio
```

The wheel smoke test executes outside the checkout. A source-only success does not
prove that the release artifact works.

## Extension ideas with bounded scope

- A new geometric recipe with valid B-rep, STEP/STL and degenerate-input rejection.
- A catalog adapter that retains source, dimensions, retrieval time and qualification
  status, with an offline fixture for tests.
- A process checker with explicit inputs, uncertainty and evidence provenance.
- A CLI or documentation fix that reduces setup steps on a supported platform.
- An agent-facing operation that preserves parent identities and immutable evidence.

See [ROADMAP.md](ROADMAP.md) for milestones. Large API or theorem changes should
start with a short design issue. Do not add model providers, cloud dependencies or
frameworks without a runnable use case.

## Contribution behavior

Discuss the design and evidence respectfully. Credit contributors and upstream
work. Do not post credentials, private product drawings or unreleased customer data.
Disagreements should be resolved with reproducible cases and clearly stated limits.

New contributions use the repository's MIT license; preserve third-party notices
and identify the source and rights for contributed reference images or CAD files.
