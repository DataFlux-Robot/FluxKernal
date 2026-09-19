"""L3: recursive role ontology (impl plan v1.0 §3.2 — NOT a fixed level table).

Nodes carry `role`; there is no global level number. "How deep" a node is
derives from its path in the DAG (see semantics/goals.depth_of).

Key structural facts encoded here:
  - Resource (a machine/station) and System (an aircraft) are ISOMORPHIC
    objects: when a Line's requirement refines into a Resource spec and that
    Resource is decomposed as a System, the PRSI recursion edge holds —
    "machines that make machines" is the same type at different recursion
    rounds.
  - Medium (v1.2 §19) is a first-class role: shared physical media (DC bus,
    hydraulic fluid, primary structure, thermal field, EMI environment, time
    base). Media are REFERENCED through budget/effluent declarations, not
    decomposed.
  - Termination is built into the ontology of realize: a Part closes by one
    of procure | manufacture | decompose (three-way choice).
"""
from __future__ import annotations

from ..core.objects import ROLES

ROLE_DESC = {
    "Intent":    "demand / MRS — possibly vague, constraint domains",
    "System":    "a whole that decomposes: aircraft, production cell, machine",
    "Component": "subsystem with its own contract (wing, power module, spindle)",
    "Part":      "part geometry: 2D sketch -> 3D solid; closes via procure/manufacture/decompose",
    "Process":   "process plan: fabrication ops, DfAM evidence",
    "Line":      "production line: cells/operators as self-rooted nodes, flows",
    "Resource":  "machine/station demanded by a Line; isomorphic to System (PRSI recursion)",
    "Medium":    "shared physical medium: bus/fluid/structure/thermal/EMI/time (v1.2)",
}

# Legal parent-role -> child-role transitions for refine-family operators
# (refine/manufacture output families). compose checks children against the
# output node's role with the same table; abstract is always legal.
ROLE_TRANSITIONS: dict[str, set[str]] = {
    "Intent":    {"System", "Component", "Part", "Process", "Line"},
    "System":    {"System", "Component", "Part", "Resource"},
    "Component": {"Component", "Part", "Medium"},
    "Part":      {"Part", "Process"},          # manufacture: Part -> Process family
    "Process":   {"Process", "Line"},
    "Line":      {"Resource", "Line", "System", "Process"},
    "Resource":  {"System", "Component", "Part"},   # machine re-enters as a System
    "Medium":    set(),                        # media are referenced, not decomposed
}

# The three legal ways a Part goal may close (realize termination rule).
PART_TERMINATIONS = ("procure", "manufacture", "decompose")


def known(role: str) -> bool:
    return role in ROLES


def transition_legal(parent_role: str, child_role: str) -> bool:
    """Is child_role a legal refinement target under parent_role?

    Genesis (no parent) is always legal — checked by callers passing None.
    """
    if child_role not in ROLES:
        return False
    if parent_role is None:
        return True
    return child_role in ROLE_TRANSITIONS.get(parent_role, set())
