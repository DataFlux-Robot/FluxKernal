"""Core object model: Node / Edge / Certificate / Obligation / ResourceVector.

The ONLY trusted data types (L1). Zero geometry knowledge, zero third-party
imports. Geometry lives in L2 solver plugins and appears here only as
projection refs.

Frozen decisions (impl plan v1.0 §4 + addendum v1.1 §16 + v1.2 §18/§25):
  - Node carries `role` (recursive role ontology, NOT a global level number);
    "how deep" is derived from the DAG path, never stored.
  - Node carries `facet` BODY|MIND (v1.1 co-design); MIND nodes must declare
    `spec["plant_ref"]` (validated in L3, not here).
  - Node.spec is a CONTRACT (v1.2): nine slots
    goals/semantics/assumes/guarantees/budget/effluent/forbidden/
    not_responsible/time_scale. Medium nodes instead carry
    {capacity, margin, state, degradation}. Core only transports the dict;
    schema validation and contract arithmetic live in L3 semantics/contracts.
  - Obligation has class hard|soft (v1.2 §21): hard obligations gate the
    fail-closed lifecycle; soft ones never gate, they only feed the evidence
    vector for policy layers (fk evolve).
  - Edge.ops include exact/procure/manufacture/integrate; integrate carries
    `coverage` {goal_digest: evidence_ref} (v1.1 §13).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Edge lifecycle: proposed -> executed -> evidenced -> verified -> promoted
# Any failure -> rejected (kept forever, retrievable, never referable as input).
# Lint-gated nodes never rise above proposed (v1.2 §18): recorded via reason.
EDGE_STATES = ("proposed", "executed", "evidenced", "verified", "promoted", "rejected")

OPS = ("refine", "compose", "abstract", "evaluate", "exact", "procure",
       "manufacture", "integrate")

ROLES = ("Intent", "System", "Component", "Part", "Process", "Line", "Resource", "Medium")
FACETS = ("BODY", "MIND")

# The nine contract slots of a v1.2 spec (Medium nodes use capacity/state/...).
CONTRACT_SLOTS = ("goals", "semantics", "assumes", "guarantees", "budget",
                  "effluent", "forbidden", "not_responsible", "time_scale")


@dataclass
class ResourceVector:
    """c(P; mu): common-ancestor incremental accounting."""
    time_s: float = 0.0
    energy_j: float = 0.0
    material_g: float = 0.0
    cost: float = 0.0
    human_s: float = 0.0
    failures: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ResourceVector":
        return ResourceVector(**{k: d.get(k, 0) for k in
                                 ("time_s", "energy_j", "material_g", "cost",
                                  "human_s", "failures")})


@dataclass
class Obligation:
    """A finite, machine-checkable claim attached to an edge.

    oclass "hard": decidable (contract arithmetic, forbidden states, discrete
    protocol properties) -> checked in kernel/bench; failure rejects the edge.
    oclass "soft": not decidable-as-true, only comparable (mass/cost/fuel) ->
    never gates, feeds the evidence vector for policy layers.
    """
    id: str                       # e.g. "ag-coverage", "medium-capacity", "solver-converged"
    prop: str                     # human/Lean-readable proposition text
    holds: Optional[bool] = None  # None = undischarged
    checker: str = ""             # who discharged it: "core", "contracts", "sketch2d", ...
    detail: str = ""
    oclass: str = "hard"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["class"] = d.pop("oclass")   # serialized key per v1.2 §21
        return d

    @staticmethod
    def from_dict(d: dict) -> "Obligation":
        return Obligation(id=d["id"], prop=d.get("prop", ""), holds=d.get("holds"),
                          checker=d.get("checker", ""), detail=d.get("detail", ""),
                          oclass=d.get("class", "hard"))


@dataclass
class Certificate:
    obligations: list = field(default_factory=list)   # list[Obligation]
    evaluator: str = ""        # digest or id of evaluator identity (separate from executor)
    evidence: list = field(default_factory=list)      # list[dict] from solvers
    executor: str = ""

    def to_dict(self) -> dict:
        return {"obligations": [o.to_dict() if hasattr(o, "to_dict") else o
                                for o in self.obligations],
                "evaluator": self.evaluator, "evidence": self.evidence,
                "executor": self.executor}


@dataclass
class Node:
    """A design state at some abstraction level. May be UNGROUNDED (a design space).

    ground is None while the node is a partially-specified space (the 'not yet
    collapsed' state); evaluation projects it to concrete geometry/process/layout.
    """
    role: str                                  # ROLES; "depth" is path-derived, never stored
    kind: str                                  # free type name: "aircraft","wing","motor","milling-op"
    facet: str = "BODY"                        # FACETS; MIND => spec must carry plant_ref (L3 checks)
    spec: dict = field(default_factory=dict)   # CONTRACT (v1.2) or Medium capacity/state/degradation
    params: dict = field(default_factory=dict) # values or ["param", name] holes (= sorry)
    variants: list = field(default_factory=list)  # unresolved alternatives (variant space)
    ground: Optional[dict] = None              # projection refs {type, blobs, volume_mm3, ...}
    evidence: list = field(default_factory=list)
    lineage: list = field(default_factory=list)   # edge digests (derived metadata, not identity)
    supersedes: list = field(default_factory=list)  # node digests this branch replaces

    def payload(self) -> dict:
        d = asdict(self)
        # lineage is derived metadata (recoverable from the edge log), never identity
        d.pop("lineage", None)
        return d


@dataclass
class Edge:
    """A registered transformation: (inputs, transform) -> output + certificate + resources.

    PIPE-shaped: ProducedBy(output; inputs, transform) is established by the
    digest identity of this record plus its certificate.
    """
    op: str                                       # OPS
    inputs: list                                  # list[node digest]  (t_k)
    transform: dict                               # {name, args}       (delta_k)
    output: str                                   # node digest        (o_k)
    coverage: dict = field(default_factory=dict)  # integrate: {goal_digest: evidence_ref}
    certificate: dict = field(default_factory=dict)
    resources: dict = field(default_factory=ResourceVector().to_dict)
    state: str = "proposed"
    reason: str = ""                              # diagnostic code + note when capped/rejected

    def payload(self) -> dict:
        d = asdict(self)
        d.pop("state", None)   # lifecycle metadata, not identity
        d.pop("reason", None)
        return d
