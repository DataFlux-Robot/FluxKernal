# Benchmark architecture

**English** | [简体中文](ARCHITECTURE.zh-CN.md)

MechanogenesisBench is an evaluator-facing protocol, not an agent or a product
runtime. A participant receives a public task view and guidance level, then
runs as an external process. The participant emits a content-addressed MRS
bundle, proposed artifacts, construction/experiment receipts and a resource
declaration. A task-owned evaluator uses its private view to produce decisions;
the benchmark verifier independently checks hashes, lineage, budgets, evidence
tier and promotion predicates.

```text
public task + guidance
        |
        v
third-party agent process -----> content-addressed submission
                                        |
private evaluator bundle -------------->+----> evaluator decision
                                              |
task + submission + decision ---------------->+----> verifier + vector score
```

## Trust boundary

The participant and its declared receipts are untrusted. The task package,
private evaluator bundle and verifier are benchmark-owned. The current runner
offers only process isolation and is therefore suitable for development and
conformance tests, not hostile or competition-grade execution.

Task and evaluator identities are separate. Public task material contributes
to the task-package digest; private evaluator material contributes to an
evaluator digest. A completed run is bound to both, preventing a later evaluator
change from silently preserving an old result.

## Canonical checks

The current executable slice checks:

- schema and content-addressed MRS objects;
- process and world lineage across generations;
- exact integer material closure for construction receipts;
- evaluator/artifact binding;
- evidence-tier ceilings;
- vector resource budgets;
- exact agreement between acceptance flags and promotion predicates;
- bounded recursive-credit conditions for the recursive track.

Lean modules formalize selected finite protocol implications. Python performs
runtime parsing, task execution and concrete verification. The two layers must
agree, but neither asserts that a physical model is faithful or that a receipt
corresponds to a real event without independent evidence.

## Tracks and comparison classes

- `fixed_engine`: the research/execution system remains fixed.
- `open_system`: the system may synthesize intermediate languages/programs and
  use declared external tools.
- `recursive_learner`: the submission additionally attempts a bounded linked
  successor-generation claim.

Guidance levels run from G1 (substantial decomposition and protocol hints) to
G5 (mission and access only). Results are comparable only within the same task,
track, guidance, evidence tier and budget vector.

## Vector scoring

A scalar can let speed hide material waste or let a simulation score masquerade
as hardware evidence. The benchmark therefore retains capability, robustness,
autonomy, time, monetary cost, energy, material, human intervention and bounded
recursive credit as distinct coordinates. Any leaderboard policy belongs above
this verification kernel and must state its trade-offs.
