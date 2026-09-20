"""M-layer: parametric mechanism packages (layout+generators+recipes).

A mechanism is DATA + CODE + TESTS as an exchangeable unit: the JSON
declares params/schema/policies, the module computes layout (frames from
parameters — never hand-tuned coordinates), per-part geometry, and the
compose recipe.  `instantiate` expands it into ORDINARY DAG edges; the
kernel and verify stay mechanism-agnostic.
"""
