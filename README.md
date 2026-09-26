<div align="center">

# FluxKernel

**An evidence-carrying design and manufacturing kernel for AI agents.**

Turn a product reference into named parts, CAD artifacts, manufacturing dependencies,
and a plan whose stated closure conditions can be checked by Lean 4.

[Interactive showcase](https://www.datafluxdynamics.ltd/technology/fluxkernel/) · [Quickstart](docs/QUICKSTART.md) · [中文](README.zh-CN.md) · [Contribute](CONTRIBUTING.md)

</div>

> **Development preview.** This repository currently requires access. A checked
> manufacturing plan is conditional on its declared inputs; it is not a certificate
> of physical manufacturability, supplier availability, or product performance.

## See the workflow

[![FluxKernel Studio — product and equipment exploration](docs/media/studio.png)](https://www.datafluxdynamics.ltd/technology/fluxkernel/)

**Image + requirements → candidate parts → STEP/STL → manufacturing equipment → evidence.**

- **Keep design state.** Parts have stable names and content identities; revisions retain history and reuse unchanged geometry after checking its integrity.
- **Include the equipment.** A machined part depends on a blank and a manufacturing cell. The demo expands one equipment generation into purchased candidates and printed structures.
- **Check the actual plan.** Lean checks dependency ordering, route rules, depth limits, and coverage for that run. Missing tools and rejected proofs leave an open result.
- **Take the evidence with you.** Each completed run contains CAD files, assumptions, receipts, a manifest, and an independent verifier.
- **Start without a model account.** Curated phone, car, and aircraft references run locally. Reference mode is always labeled and does not perform image inference.

## Start with the kernel — no CAD or model dependencies

Python **3.12+** is required. From a checkout:

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
fk doctor

mkdir my-first-design
cd my-first-design
fk example
fk init
fk run hello.fcad
fk show housing-v2 --json
fk verify
```

The example records two housing parameter sets with different content identities.
`fk verify` checks recorded store integrity; it does not run a physics simulation.

## Generate a complete reference design

From the repository root, with the same environment active:

```bash
python -m pip install -e '.[demo]'
fk doctor --profile studio
fk demo --reference phone --output ./runs --json
fk-studio
```

Open **http://127.0.0.1:8740**. Without model credentials, select **参考架构回放**
(curated reference mode) in Studio. To browse command-line runs in Studio, point
`FK_DEMO_DATA` to the same output folder before starting the server.

The CLI writes a new run directory containing individual STEP/STL parts and a
manufacturing plan. With the pinned Lean toolchain installed, the plan is checked;
without it, CAD is still generated and the proof remains explicitly open.
Use `--require-proof` when an agent or CI job must fail unless Lean accepts the plan.

For Lean installation, live image generation, configuration and troubleshooting,
see the [quickstart](docs/QUICKSTART.md). The project is not published to PyPI yet;
install from a checkout or a built wheel, not an assumed public package listing.

## Use it from Python

```python
from fluxkernel.studio import generate_reference

run = generate_reference("phone", output_dir="./runs")
print(run.directory)
print(run.proof_accepted)  # False means unproven; never silently promoted.
print(run.to_dict())      # Includes reference mode and physical_status.
```

This API isolates native CAD output in a worker process and creates a fresh run
for every call. It uses curated references; the local Studio provides live image
planning through the configured Anthropic-compatible or Ollama backend.

## What is verified?

| Layer | Current evidence | What remains outside it |
| --- | --- | --- |
| Image interpretation | Explicit visible / inferred / selected labels | Hidden internal structure and accurate dimensions |
| Geometry | Constructive B-rep checks and independent STEP/STL | Fit, strength, fatigue, thermal behavior and function |
| Manufacturing plan | Receipt binding; Lean checks finite dependency closure and route rules | True equipment capability and actual process qualification |
| Procurement | Named specification/model candidates and envelopes | Verified supplier data, inventory and exact interfaces |
| Revision | Parent identity, changed-part records, verified geometry reuse | User acceptance and improvement of real-world performance |

Unlimited printer size is an explicit demonstration assumption. Materials,
precision, post-processing, power and assembly still need evidence. The core
refinement graph uses Python checks; the concrete manufacturing-plan checker uses
Lean. See [PROOF_PACKAGE.md](PROOF_PACKAGE.md) for the exact theorem and boundaries.

## Architecture and extension points

```text
Agent / Studio / fk CLI / .fcad
              │
    stateful design operators
              │
    solver evidence + contracts
              │
    content-addressed graph + store
              │
    CAD / receipts / plan / Lean / manifest
```

The core and store have no third-party dependencies. Geometry, process and catalog
solvers live outside that trusted storage layer. Start with the
[architecture and extension guide](docs/ARCHITECTURE.md) before adding a solver,
geometry recipe or checker.

## Develop

```bash
python -m pip install -e '.[demo,dev]'
lake build
python -m pytest -q
python -m build
python scripts/smoke_distribution.py --studio
```

CI covers the dependency-free kernel on Linux, macOS and Windows, plus CAD and
real Lean checks on Linux. The distribution smoke test installs a wheel into a
fresh environment and runs outside the source tree. See the [roadmap](ROADMAP.md)
and [contributing guide](CONTRIBUTING.md) for scoped work and acceptance criteria.

## License

[MIT](LICENSE). Vendored Three.js retains its [upstream license](fluxkernel/demo/static/vendor/THREE-LICENSE.txt).
Reference image attribution is recorded in [sources.json](fluxkernel/demo/static/references/sources.json).
