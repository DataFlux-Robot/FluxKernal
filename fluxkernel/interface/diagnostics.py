"""L4: typed diagnostic codes — the LLM reward-shaping ladder (append-only!).

Error hierarchy (impl plan §2): syntax < type < undischarged obligation <
eval-metric-miss < missing physical evidence. The code table ONLY EVER GROWS;
renumbering or reusing a code for a different meaning is forbidden.
"""
from __future__ import annotations

# code -> (rank, human explanation)
CODES: dict[str, tuple[int, str]] = {
    "S1": (0, "syntax error in .fcad or CLI argument"),
    "T2": (1, "type error: unknown role/kind or wrong object type"),
    "U1": (2, "under-constrained: sketch/system has residual DOF"),
    "O2": (2, "over-constrained: conflicting constraints"),
    "I1": (3, "exact-link broken: input digest missing"),
    "I2": (3, "exact-link broken: input is not a node"),
    "I3": (3, "fail-closed: input produced by a non-promoted edge"),
    "C0": (4, "undischarged hard obligation -> rejected"),
    "E1": (5, "solver/eval plugin failed or produced no evidence"),
    "M1": (6, "metric missed the declared expectation"),
    # ---- v1.2 contract-native additions (append-only) ----
    "K1": (4, "contract conflict: contradictory intervals exposed at compose "
              "(before detailed design)"),
    "G2": (4, "medium over capacity: Σbudget > capacity×(1−margin)"),
    "G3": (4, "effluent not absorbed: worst-case emission exceeds downstream tolerance"),
    "T3": (4, "time scales mixed without explicit stratification"),
    "U2": (4, "interface union inconsistent across merged subtrees (integrate)"),
    "L1": (2, "lint: input space not bounded (assumes lack numeric bounds)"),
    "L2": (2, "lint: guarantees not decidable / goals not falsifiable+measured"),
    "L3": (2, "lint: fault modes not enumerated (forbidden list incomplete)"),
    "L4": (2, "lint: spec noun does not resolve to the term registry"),
    "L5": (2, "lint: time scale missing or not single/stratified"),
    "L6": (2, "lint: free parameter lacks a range or a checker"),
    "L7": (2, "case: Part-leaf-heavy store without a case-contract"),
    "L8": (2, "case: whole-vehicle compose with no :machine chain "
             "and no case-contract"),
    # ---- v1.1 co-design addition ----
    "P1": (4, "plant-model-current failed: MIND evidence built on a stale BODY"),
}


def explain(code: str) -> str:
    return CODES.get(code, (99, "unknown code"))[1]


def rank(code: str) -> int:
    return CODES.get(code, (99,))[0]


def codes_in_reason(reason: str) -> list[str]:
    """Extract diagnostic codes from an edge reason string."""
    import re
    return re.findall(r"\b([STUOICEMKGLP]\d)\b", reason or "")


def worst_code(reason: str) -> str | None:
    found = codes_in_reason(reason)
    return max(found, key=rank) if found else None
