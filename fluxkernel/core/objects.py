"""Core object model: Node / Edge / Certificate / ResourceVector.

These are the ONLY trusted data types (L1). They contain no geometry knowledge;
geometry lives in L2 solver plugins and appears here only as projection refs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Edge lifecycle: proposed -> executed -> evidenced -> verified -> promoted
# Any failure -> rejected (kept forever, retrievable, never referable as input)
EDGE_STATES = ("proposed", "executed", "evidenced", "verified", "promoted", "rejected")

OPS = ("refine", "compose", "abstract", "evaluate")


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
                                 ("time_s", "energy_j", "material_g", "cost", "human_s", "failures")})


@dataclass
class Obligation:
    """A finite, machine-checkable claim attached to an edge."""
    id: str            # e.g. "input-verified", "level-descent", "solver-converged"
    prop: str          # human/Lean-readable proposition text
    holds: Optional[bool] = None   # None = undischarged
    checker: str = ""              # who discharged it: "core", "sketch2d", ...
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


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
    kind: str                    # e.g. "intent", "function-arch", "sketch", "part", "assembly", "process", "line"
    level: str                   # Intent|Function|Skeleton|Part|Assembly|Process|Line|MetaLine
    spec: dict = field(default_factory=dict)      # constraints, requirements, interfaces
    params: dict = field(default_factory=dict)    # free parameter domains or values
    variants: list = field(default_factory=list)  # unresolved alternatives (variant space)
    ground: Optional[dict] = None                 # projection refs: {type, blobs, mass_props...}
    evidence: list = field(default_factory=list)
    lineage: list = field(default_factory=list)   # edge digests that produced/refined this node
    supersedes: list = field(default_factory=list)  # for abstract/re-branch

    def payload(self) -> dict:
        d = asdict(self)
        # lineage is derived metadata (recoverable from the edge log), never identity
        d.pop("lineage", None)
        return d


@dataclass
class Edge:
    """A registered transformation: (inputs, transform) -> output + certificate + resources.

    This is the PIPE-shaped object: ProducedBy(output; inputs, transform) is
    established by the digest identity of this record plus its certificate.
    """
    op: str                                   # refine | compose | abstract | evaluate
    inputs: list                              # list[node digest]  (t_k)
    transform: dict                           # {name, args}       (delta_k)
    output: str                               # node digest        (o_k)
    certificate: dict = field(default_factory=dict)
    resources: dict = field(default_factory=ResourceVector().to_dict)
    state: str = "proposed"
    reason: str = ""                          # for abstract edges / rejected notes

    def payload(self) -> dict:
        d = asdict(self)
        d.pop("state", None)  # state is lifecycle metadata, not identity
        d.pop("reason", None)
        return d
