# Proof Package

## Claim

Original ambition: an arbitrary product image can be decomposed, including its manufacturing equipment, until all leaves are standard components or readily printable parts, and the resulting product can actually be manufactured.

That physical claim is **not established** by a photograph, a planning model, or the current CAD recipes. Hidden geometry, materials, tolerances, suppliers, assembly access and process performance are not determined by one image.

The implemented, corrected claim is: for any finite list of manufacturing occurrences $S$ and equipment-depth policy $P$, if `check P S = true`, then `VerifiedPlan P S`. This comprises an inductive finite construction derivation, checked route types, and product-root coverage. Every dependency index is strictly earlier than its consumer; every depth is at most the supplied budget; the only dependency-free routes are declared seed capabilities and catalog candidates. In this demo, equipment occurrences have depth one and their constituent routes include both printed and catalog occurrences.

## Status

**PROVABLE AFTER WEAKENING / EXTRA ASSUMPTION** relative to the original physical ambition. The corrected structural statement is fully proved in Lean 4, with no `sorry`, `native_decide`, or project-defined axioms.

## Assumptions

- An external initial capability $K_0$ supplies material-specific additive processes, feedstock, power, support removal and basic assembly. Unlimited envelope is an explicit modeling assumption, not an observed printer capability.
- Catalog references identify procurement candidates. Supplier authenticity, availability and dimensional accuracy remain open.
- Python validates receipt hashes and their binding to occurrence identity, dependencies, input image and request. Hashing and JSON-to-Lean translation belong to the trusted application boundary; Lean does not prove SHA-256 correctness or receipt truth.
- OpenCascade validates generated solids. This is geometry evidence, not a physical manufacturing theorem.
- Lean 4.34.1's kernel is trusted. The soundness theorem reports the standard logical axiom `propext`; no physical facts are introduced as axioms.

## Notation

- $S=[s_0,\ldots,s_{n-1}]$ is the ordered list of unique manufacturing occurrences. Repeated identical geometries may have distinct occurrences.
- $D_i$ is the list of dependency indices of $s_i$.
- $d_i\in\mathbb{N}$ is its declared equipment expansion depth; $P$ supplies the maximum.
- `StepValid P i s` conjoins $\forall j\in D_i,\ j<i$, route-local conditions, a nonempty receipt reference and the depth bound.
- `Closed P S` is an inductively constructed list of valid steps. It includes an empty base derivation, but the complete `check` rejects an empty product plan.
- `typedRoutes` checks seed inputs for printing, printed blank plus equipment inputs for machining, and printed plus catalog constituents for equipment.
- `rootCovered` checks that the last occurrence is assembly and each occurrence is reachable from it through dependencies. Reachability is fuel-bounded by $n$.

## Proof Strategy

Induction on the suffix of a checked list, maintaining an already closed prefix. Boolean acceptance yields decidable propositions, which construct the corresponding inductive derivation.

## Dependency Map

1. `append_checked` uses induction, `Bool.and_eq_true_iff`, `of_decide_eq_true`, list append associativity and length arithmetic.
2. `check_sound` separates the three Boolean checks and invokes `append_checked` on an empty prefix.
3. `no_self_bootstrap` combines the earlier-dependency property with irreflexivity of natural-number strict order.
4. `depth_bounded` projects the final conjunct of `StepValid`.
5. Each generated `ManufacturingPlan.lean` contains its actual occurrence data and proves acceptance by kernel reduction using `decide`, then invokes `check_sound`.

## Proof

1. Let a prefix $B$ satisfy `Closed P B`, and let the remaining suffix $R$ satisfy `checkFrom P B.length R = true`. If $R=[]$, concatenation leaves $B$, so the existing derivation suffices.
2. For $R=s::R'$, conjunction acceptance gives `decide (StepValid P B.length s) = true` and acceptance of the remaining suffix at index $|B|+1$. `of_decide_eq_true` yields the actual proposition `StepValid P B.length s`.
3. Apply `Closed.snoc` to the prefix derivation and this proposition. This constructs `Closed P (B ++ [s])`. Since $|B++[s]|=|B|+1$, the induction hypothesis applies to $R'$. Associativity identifies the result with `Closed P (B ++ (s :: R'))`.
4. With $B=[]$, acceptance of `checkFrom P 0 S` therefore constructs `Closed P S`. The other two conjuncts of `check P S = true` supply route-type and root-coverage equalities. These three values construct `VerifiedPlan P S`.
5. For a valid occurrence at index $i$, membership $i\in D_i$ would imply $i<i$, contradicting `Nat.lt_irrefl`. More generally, every edge decreases indices, so a dependency cycle would require a finite chain of strict decreases returning to its start. The separately exposed Lean lemma proves the direct self-use case; the decreasing-index property is carried by the closure derivation for all edges.
6. The depth bound is already a conjunct of each step's validity, so projection proves `depth_bounded` without additional assumptions. ∎

## Corrections or Missing Assumptions

Conditional graph closure does not establish correct geometry reconstruction, supplier qualification, material/process suitability, collision-free assembly, machining access, or final product function. The UI calls it “条件化闭合” and displays physical validation as unresolved. Machined-part exports are currently blanks; there is no qualified toolpath or finished-hole geometry claim.

## Open Risks

The finite recipe vocabulary and equipment generator provide conceptual manufacturing proposals. They do not constitute automatic reverse engineering of arbitrary hidden assemblies. Route selection is model-generated, and the demonstration prompt requests a machining operation to exercise equipment expansion. This is an explicit design choice, not visual evidence that the photographed product used that process.

A later physical theorem would require calibrated process capabilities, supplier evidence and verified interfaces, followed by experiment. Current proof obligations must not be relabeled as proof of that stronger theorem.

## Reproduction

Run `lake build`; then `lake env lean .demo/runs/<run>/ManufacturingPlan.lean`. Run `env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_demo.py` for acceptance and negative cases. The evidence bundle contains a standalone Lean project and manifest verifier.
