"""L1: the DAG — commit discipline, exact linking, lifecycle, promotion.

This is the trusted core's other half. It knows nothing about geometry.
Fail-closed: any failed obligation -> rejected; rejected edges exist as
evidence but can never be referenced as inputs.

Identity vs metadata: node digests never include lineage. Lineage is recorded
in the store index as @lineage/<node_digest> -> producing edge digest.
"""
from __future__ import annotations

from ..core.objects import Edge, Node, Certificate, ResourceVector
from ..store.objstore import Store

LINEAGE_PREFIX = "@lineage/"


class DagError(Exception):
    def __init__(self, code: str, msg: str):
        self.code = code          # typed diagnostic code (I1, C0, ...)
        super().__init__(f"[{code}] {msg}")


class DAG:
    def __init__(self, store: Store):
        self.store = store

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
        return d, Node(**{**obj["payload"], "lineage": []})

    def lineage_of(self, node_digest: str) -> str | None:
        idx = self.store.names()
        return idx.get(LINEAGE_PREFIX + node_digest)

    def producing_edge(self, node_digest: str) -> dict | None:
        e = self.lineage_of(node_digest)
        if not e:
            return None
        return self.store.get_object(e)["payload"]

    # ---- commit ----
    def commit_edge(self, edge: Edge, node: Node, cert: Certificate,
                    resources: ResourceVector,
                    edge_name: str | None = None,
                    node_name: str | None = None) -> tuple[str, str]:
        """Lifecycle: executed -> evidenced -> verified -> promoted, fail-closed.

        Returns (edge_digest, node_digest). Rejected edges/nodes are still
        committed (they are evidence — 'informative failures') but can never
        be referenced as inputs downstream.
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
                    reject = f"I3: input {i[:40]}… produced by non-promoted edge ({pe.get('state')})"
                    break

        if reject is None:
            edge.state = "executed"
            if cert.evidence:
                edge.state = "evidenced"
            undischarged = [o.id for o in cert.obligations if o.holds is not True]
            if not undischarged:
                edge.state = "verified"
                if cert.evidence:
                    edge.state = "promoted"
            else:
                reject = "C0: undischarged obligations: " + ",".join(undischarged)

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
