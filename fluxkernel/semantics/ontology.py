"""L3: level ontology — an extensible registry, not hardcoded numbers.

Higher rank = more concrete. refine must descend (rank increases);
abstract ascends; compose outputs at the registered composition level.
New domains = new registry entries; the kernel engine never changes.
"""
from __future__ import annotations

LEVELS = {
    "Intent":    {"rank": 0, "desc": "demand / MRS — possibly vague, constraint domains"},
    "Function":  {"rank": 1, "desc": "functional architecture + functional interfaces"},
    "Skeleton":  {"rank": 2, "desc": "geometric architecture: layout curves, frames, motion chains (1D)"},
    "Part":      {"rank": 3, "desc": "part geometry: 2D sketch -> 3D solid"},
    "Assembly":  {"rank": 4, "desc": "composed parts, mates, closed-loop joint graphs"},
    "Process":   {"rank": 5, "desc": "process plan: fabrication ops, DfAM evidence"},
    "Line":      {"rank": 6, "desc": "production line: cells/operators as self-rooted nodes, flows"},
    "MetaLine":  {"rank": 7, "desc": "the line that makes lines — PRSI recursion layer"},
}


def rank(level: str) -> int:
    if level not in LEVELS:
        raise KeyError(f"unknown level: {level}")
    return LEVELS[level]["rank"]


def known(level: str) -> bool:
    return level in LEVELS
