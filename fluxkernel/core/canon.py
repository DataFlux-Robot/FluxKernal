"""Canonical encoding and content addressing.

Design rule: identity = hash of canonical bytes. There is exactly ONE canonical
serialization per object (deterministic JSON). The .fcad text form is a human
projection; objects are digested on their canonical JSON bytes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA = "fk1"


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic serialization: sorted keys, tight separators, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest_of(kind: str, payload: dict) -> str:
    """Domain-separated content digest: fk1:<kind>:<sha256>."""
    h = hashlib.sha256()
    h.update(f"{SCHEMA}:{kind}:".encode("utf-8"))
    h.update(canonical_bytes(payload))
    return f"{SCHEMA}:{kind}:{h.hexdigest()}"


def blob_digest(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(f"{SCHEMA}:blob:".encode("utf-8"))
    h.update(data)
    return f"{SCHEMA}:blob:{h.hexdigest()}"


def check_digest_format(d: str) -> bool:
    parts = d.split(":")
    return len(parts) == 3 and parts[0] == SCHEMA and len(parts[2]) == 64
