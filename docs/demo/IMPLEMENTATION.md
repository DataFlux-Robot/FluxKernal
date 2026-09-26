# Image-to-manufacturing demonstrator

Goal: upload a product image; inspect a candidate reconstruction with sourced
observations and explicit assumptions; recursively resolve product and one
equipment generation to catalog procurement and print/process plans; inspect
real CAD artifacts and a Lean-checked manufacturing dependency certificate.

Scope: conceptual engineering reconstruction, not certification of the original
product's hidden internals or physical performance. Unlimited print envelope is
an explicit initial capability; material/precision/support limits remain visible.

Implementation: FastAPI local app + offline browser assets, vision JSON planner,
constrained parametric OCP geometry backend, FluxKernel content-addressed DAG,
immutable job artifacts, Lean 4 closure/bootstrap checker and proof artifacts.
Live inference and curated replay are distinct modes. No model/config failure
may silently fall back to curated content. Original requirements/image and
capabilities are frozen per run; edits create child runs with provenance.

Acceptance:
- Phone, car and aircraft reference cases render and export individual STEP/STL.
- A new uploaded image goes through actual vision inference when configured.
- Product/component/equipment tree, manufacturing dependencies and BOM inspectable.
- Machine needs standard/printed constituents and precedes its product process.
- Lean checks actual job data; missing input, self-bootstrap, broken leaf and
  exceeded equipment depth are rejected. No sorry/native_decide/custom axioms.
- Evidence download contains image hash, model response, design, geometry,
  persisted FK graph, checker source hash, Lean proof/result, tests and assumptions.
- UI screenshot/browser tests and startup instructions supplied.
