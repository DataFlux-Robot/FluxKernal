"""L1: the DAG — commit discipline, exact linking, lifecycle, promotion.

The trusted core's other half. Knows nothing about geometry.
Fail-closed: any failed HARD obligation -> rejected; rejected edges exist as
evidence but can never be referenced as inputs. Soft obligations never gate
(v1.2 §21) — they ride along in the evidence vector for policy layers.

Lint gate (v1.2 §18): nodes failing the five objectivity rules (or noun
resolution) may exist but never rise above `proposed`. The rules themselves
live in L3; the kernel accepts them as injected promotion gates so L1 stays
knowledge-free (dependency direction L3 -> L1 only).

Identity vs metadata: node digests never include lineage. Lineage is recorded
in the store index as @lineage/<node_digest> -> producing edge digest.
"""
from __future__ import annotations

from ..core.objects import (Edge, Node, Certificate, ResourceVector, Obligation)
from ..store.objstore import Store

LINEAGE_PREFIX = "@lineage/"


class DagError(Exception):
    def __init__(self, code: str, msg: str):
        self.code = code          # typed diagnostic code (I1, C0, ...)
        super().__init__(f"[{code}] {msg}")


class DAG:
    def __init__(self, store: Store):
        self.store = store
        self._gates: list = []    # fn(node_payload: dict) -> list[str] failed rule ids

    # ---- promotion gates (L3 injects lint rules; kernel stays knowledge-free) ----
    def add_promotion_gate(self, fn) -> None:
        self._gates.append(fn)

    # ---- node helpers ----
    def put_node(self, node: Node, name: str | None = None) -> str:
        d = self.store.put_object("node", node.payload())
        if name:
            self.store.bind_name(name, d)
        return d

    def get_node(self, ref: str) -> tuple[str, Node]:
        d = self.store.resolve(ref)
        obj = self.store.get_object(d)
        if obj["kind"] != "node":
            raise DagError("T2", f"{ref} is not a node")
        payload = dict(obj["payload"])
        payload.setdefault("lineage", [])
        return d, Node(**payload)

    def get_obj(self, ref: str) -> dict:
        """Raw object envelope {kind, digest, payload} for any object type."""
        d = self.store.resolve(ref)
        return self.store.get_object(d)

    def iter_nodes(self) -> list[tuple[str, dict]]:
        """All committed nodes as (digest, payload). For scans (goals/risks/ledger)."""
        out = []
        for d in self.store.list_objects("node"):
            out.append((d, self.store.get_object(d)["payload"]))
        return out

    def iter_edges(self) -> list[tuple[str, dict]]:
        out = []
        for d in self.store.list_objects("edge"):
            out.append((d, self.store.get_object(d)["payload"]))
        return out

    def get_edge(self, ref: str) -> tuple[str, Edge]:
        d = self.store.resolve(ref)
        obj = self.store.get_object(d)
        if obj["kind"] != "edge":
            raise DagError("T2", f"{ref} is not an edge")
        e = Edge(**obj["payload"])
        return d, e

    def lineage_of(self, node_digest: str) -> str | None:
        idx = self.store.names()
        return idx.get(LINEAGE_PREFIX + node_digest)

    def producing_edge(self, node_digest: str) -> dict | None:
        e = self.lineage_of(node_digest)
        if not e:
            return None
        return self.store.get_object(e)["payload"]

    def node_state(self, node_digest: str) -> str:
        """Lifecycle state of a node = state of its producing edge
        ("genesis" if it has none)."""
        pe = self.producing_edge(node_digest)
        return pe["state"] if pe else "genesis"

    # ---- commit ----
    def commit_edge(self, edge: Edge, node: Node, cert: Certificate,
                    resources: ResourceVector,
                    edge_name: str | None = None,
                    node_name: str | None = None) -> tuple[str, str]:
        """Lifecycle: proposed -> executed -> evidenced -> verified -> promoted,
        fail-closed. Lint-gated nodes cap at proposed; failed hard obligations
        reject. Rejected edges/nodes are still committed (they are evidence —
        'informative failures') but can never be referenced downstream.

        Returns (edge_digest, node_digest).
        """
        reject = None

        # -- exact link (o_i = t_{i+1} enforced structurally) --
        for i in edge.inputs:
            if not self.store.has_object(i):
                reject = f"I1: input digest missing: {i}"
                break
            obj = self.store.get_object(i)
            if obj["kind"] != "node":
                reject = f"I2: input is not a node: {i}"
                break
        # -- inputs (except genesis seeds) must come from promoted edges --
        if reject is None:
            for i in edge.inputs:
                pe = self.producing_edge(i)
                if pe is not None and pe.get("state") != "promoted":
                    reject = (f"I3: input {i[:40]}… produced by non-promoted "
                              f"edge ({pe.get('state')})")
                    break

        # -- lint gates: contract-incomplete nodes never rise above proposed --
        gate_failures: list[str] = []
        if reject is None:
            for gate in self._gates:
                gate_failures.extend(gate(node.payload()))

        if reject is None and not gate_failures:
            edge.state = "executed"
            if cert.evidence:
                edge.state = "evidenced"
            hard_un = [o.id for o in cert.obligations
                       if getattr(o, "oclass", "hard") == "hard" and o.holds is not True]
            if not hard_un:
                edge.state = "verified"
                if cert.evidence:
                    edge.state = "promoted"
            else:
                reject = "C0: undischarged obligations: " + ",".join(hard_un)
        elif gate_failures and reject is None:
            # Node exists (with its certificate recorded) but is unsettled risk:
            # never above proposed, surfaced by `fk risks`.
            edge.state = "proposed"
            edge.reason = "L*: " + ",".join(sorted(set(gate_failures)))

        if reject is not None:
            edge.state = "rejected"
            edge.reason = reject

        edge.certificate = cert.to_dict()
        edge.resources = resources.to_dict()

        node_d = self.put_node(node, node_name)
        edge.output = node_d
        edge_d = self.store.put_object(
            "edge", {**edge.payload(), "state": edge.state, "reason": edge.reason})
        if edge_name:
            self.store.bind_name(edge_name, edge_d)
        # lineage as store metadata (not identity)
        self.store.bind_name(LINEAGE_PREFIX + node_d, edge_d)
        self.store.append_edge(edge_d, {"op": edge.op, "output": node_d,
                                        "state": edge.state, "reason": edge.reason})
        return edge_d, node_d
