"""L0: dumb content-addressed object store + append-only edge log.

No parsing, no solving, no scheduling here. Objects addressed by digest;
names are mutable refs living in index.json (names are NOT identity).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..core.canon import canonical_bytes, digest_of, blob_digest, check_digest_format


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.blobs = self.root / "blobs"
        self.log_path = self.root / "edges.log"
        self.index_path = self.root / "index.json"
        for d in (self.objects, self.blobs):
            d.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index({})
        self.log_path.touch(exist_ok=True)

    # ---- object I/O ----
    def _obj_path(self, digest: str) -> Path:
        safe = digest.replace(":", "_")
        return self.objects / f"{safe}.json"

    def put_object(self, kind: str, payload: dict) -> str:
        d = digest_of(kind, payload)
        p = self._obj_path(d)
        if not p.exists():
            p.write_bytes(canonical_bytes({"kind": kind, "digest": d, "payload": payload}))
        return d

    def get_object(self, digest: str) -> dict:
        p = self._obj_path(digest)
        if not p.exists():
            raise KeyError(f"object not found: {digest}")
        return json.loads(p.read_bytes().decode("utf-8"))

    def has_object(self, digest: str) -> bool:
        return self._obj_path(digest).exists()

    def list_objects(self, kind: str | None = None) -> list[str]:
        """All object digests (optionally filtered by kind). For read-only scans."""
        prefix = f"fk1_{kind}_" if kind else "fk1_"
        suffix = ".json"
        return [p.name[:-len(suffix)].replace("_", ":", 2)
                for p in self.objects.iterdir()
                if p.name.startswith(prefix) and p.name.endswith(suffix)]

    def put_blob(self, data: bytes) -> str:
        d = blob_digest(data)
        p = self.blobs / d.replace(":", "_")
        if not p.exists():
            p.write_bytes(data)
        return d

    def get_blob(self, digest: str) -> bytes:
        return (self.blobs / digest.replace(":", "_")).read_bytes()

    # ---- edge log (append-only) ----
    def append_edge(self, edge_digest: str, record: dict) -> None:
        line = json.dumps({"ts": time.time(), "edge": edge_digest,
                           "record": record}, sort_keys=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_edge_log(self) -> list:
        out = []
        with open(self.log_path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
        return out

    # ---- name index ----
    def _read_index(self) -> dict:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, idx: dict) -> None:
        self.index_path.write_text(json.dumps(idx, indent=1, sort_keys=True),
                                   encoding="utf-8")

    def bind_name(self, name: str, digest: str) -> None:
        idx = self._read_index()
        idx[name] = digest
        self._write_index(idx)

    def resolve(self, name_or_digest: str) -> str:
        if check_digest_format(name_or_digest):
            return name_or_digest
        idx = self._read_index()
        if name_or_digest not in idx:
            raise KeyError(f"unknown name: {name_or_digest}")
        return idx[name_or_digest]

    def names(self) -> dict:
        return self._read_index()
