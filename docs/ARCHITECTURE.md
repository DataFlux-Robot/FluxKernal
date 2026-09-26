# Architecture and extension guide

FluxKernel has two connected entry paths: the general refinement-graph kernel and
Studio's bounded image-to-manufacturing pipeline. They share content-addressed
storage and explicit evidence, but do not yet expose one unified stable agent API.

| Layer | Location | Responsibility |
| --- | --- | --- |
| L0 | `fluxkernel/store/` | Canonical objects, blobs and name bindings |
| L1 | `fluxkernel/core/` | DAG lifecycle, certificates and graph integrity |
| L2 | `fluxkernel/solvers/` | Fallible domain computations and evidence |
| L3 | `fluxkernel/semantics/` | Design operations, contracts, goals and policies |
| L4 | `fluxkernel/interface/` | `.fcad`, CLI and diagnostics |
| Studio | `fluxkernel/demo/` | Image planning, finite CAD recipes, runs and web UI |
| Headless entry | `fluxkernel/studio.py` | Isolated curated reference generation |
| Formal plan | `formal/FluxKernel/Closure.lean` | Finite-plan checker and soundness theorem |

`core/` and `store/` may only import the standard library and internal modules;
the test suite enforces this. Keep OCP, image handling and provider clients out of
those layers. Lean checks the concrete Studio plan, not every Python operation.

## Add a solver

The current registry is explicit and in-process. Built-ins use
`@register("transform-name")` in `fluxkernel/solvers/registry.py`; modules are loaded
by `load_plugins()` in `semantics/operators.py`. There is no automatic external
plugin discovery or compatibility promise yet.

A solver receives `(node_specs, args, ctx)` and returns:

```python
fields, evidence, obligations
```

`fields` describes candidate output content. Evidence should record the computation,
input assumptions and fidelity. Obligations identify checks and their actual result.
Use `solvers/mission.py` for a small existing implementation. Do not promote a
candidate by treating unavailable tools, missing data or a numerical exception as a
passed obligation. Test through an Engine operation so lifecycle gates are exercised.

## Add a Studio geometry recipe

Update `demo/models.py`'s finite shape vocabulary and validation, implement it in
`demo/geometry.py`, and update the model schema/instructions in `demo/vision.py`.
The planner returns data, never executable CAD source. Test valid B-rep construction,
positive volume, STEP/STL output, unit conventions and invalid input rejection.

Include at least one reference fixture. Use `visible` only for supported observations;
hidden components and chosen architecture belong to `inferred` or `selected`.

## Change manufacturing semantics

`demo/manufacturing.py` binds receipts to occurrences and translates the actual plan
into Lean data. Changes must preserve agreement between Python validation,
JSON-to-Lean translation, `formal/FluxKernel/Closure.lean` and the standalone verifier
at `scripts/verify_demo_bundle.py`.

Cover positive and negative cases, including forward/self dependencies, missing
machining equipment, depth overflow, orphan occurrences and altered receipts.
Record precisely what the theorem establishes and which assumptions remain external.

## Resource packaging

Proofs and examples have one canonical source in the repository. `setup.py` copies
those sources into `fluxkernel/_assets/` during a wheel build. `MANIFEST.in` includes
them in the source archive, so building a wheel from an sdist also works.

`runtime.assets_root()` resolves installed resources or the editable source tree.
A proof run copies its project into its own writable run directory. `.lake` build
outputs are excluded from the immutable artifact manifest. Core installation does
not import optional CAD or web dependencies.

## Current limits

The Studio recipes, one-generation equipment concept and fixed reference cases are
bounded prototypes. Revision has explicit parent tracking but is not yet a general
transactional agent API. Native solver plugins run in-process with the engine and
are not a security sandbox. Physical tests, catalog qualification, richer assembly
interfaces and robust process feasibility are separate roadmap work.
