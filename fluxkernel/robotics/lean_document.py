"""Lossless case-oriented Lean/URDF document packages.

Robot.lean is a complete data-only XML tree, executed by the installed Lean
renderer. Numeric lexemes are strings; frames/inertia are never recomputed.
Assets and optional sealed native files are hash-bound resources. source.urdf
retains lexical formatting only, and is accepted only after tree equivalence.
Arbitrary Lean programs and package build scripts are never executed.
"""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ..runtime import assets_root, copy_proof_project
from .sources import safe
from .urdf_import import xml_root

MODULE = "formal/FluxKernel/UrdfDocument.lean"
PREFIX = (
    "import FluxKernel.UrdfDocument\nopen FluxKernel.UrdfDocument\n"
    "set_option maxRecDepth 16384\nset_option maxHeartbeats 16000000\n"
    "def robotDocument : Document := ⟨\n"
)
SUFFIX = "\n⟩\ndef main : IO Unit := IO.print (render robotDocument.root)\n"
MAX_BYTES = 16 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def tree(raw):
    def node(e, depth=0):
        if depth > 128:
            raise ValueError("XML tree depth exceeds 128")
        # Namespace expansion cannot be serialized as a literal XML tag name.
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.-]*", e.tag) or any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.-]*", k) for k in e.attrib
        ):
            raise ValueError("Namespaced XML is outside the lossless case adapter")
        children = []
        if e.text:
            children.append(e.text)
        for child in e:
            children.append(node(child, depth + 1))
            if child.tail:
                children.append(child.tail)
        return [e.tag, list(map(list, e.attrib.items())), children]

    return node(xml_root(raw))


def quote(s):
    return json.dumps(s, ensure_ascii=False)


def node_source(n):
    if isinstance(n, str):
        return ".text " + quote(n)
    tag, attrs, children = n
    a = ", ".join(f"({quote(k)}, {quote(v)})" for k, v in attrs)
    c = ",\n".join(node_source(child) for child in children)
    return f".element {quote(tag)} [{a}] [{c}]"


def source(n, assets, native, lexical_digest):
    def resources(items):
        return "[" + ",\n".join(f"⟨{quote(k)}, {quote(v)}⟩" for k, v in items) + "]"

    return (
        PREFIX
        + node_source(n)
        + ",\n"
        + resources(assets)
        + ",\n"
        + resources(native)
        + ",\n"
        + quote(lexical_digest)
        + SUFFIX
    )


class Reader:
    """Parse only the generated constructors, never evaluate supplied Lean code."""

    def __init__(self, text):
        if (
            len(text.encode()) > MAX_BYTES
            or not text.startswith(PREFIX)
            or not text.endswith(SUFFIX)
        ):
            raise ValueError("Expected a data-only FluxKernel Lean document")
        self.text = text[len(PREFIX) : -len(SUFFIX)]
        self.i = 0

    def take(self, token):
        self.ws()
        if not self.text.startswith(token, self.i):
            raise ValueError("Unsupported Lean document syntax")
        self.i += len(token)

    def ws(self):
        while self.i < len(self.text) and self.text[self.i].isspace():
            self.i += 1

    def string(self):
        self.ws()
        try:
            s, length = json.JSONDecoder().raw_decode(self.text[self.i :])
        except ValueError as exc:
            raise ValueError("Invalid Lean string") from exc
        if not isinstance(s, str):
            raise ValueError("Expected a string literal")
        self.i += length
        return s

    def items(self, parse):
        self.take("[")
        out = []
        self.ws()
        while not self.text.startswith("]", self.i):
            if out:
                self.take(",")
            out.append(parse())
            self.ws()
        self.take("]")
        return out

    def pair(self, start="(", end=")"):
        self.take(start)
        k = self.string()
        self.take(",")
        v = self.string()
        self.take(end)
        return [k, v]

    def node(self, depth=0):
        if depth > 128:
            raise ValueError("XML tree depth exceeds 128")
        self.ws()
        if self.text.startswith(".text", self.i):
            self.take(".text")
            return self.string()
        self.take(".element")
        return [
            self.string(),
            self.items(self.pair),
            self.items(lambda: self.node(depth + 1)),
        ]

    def read(self):
        n = self.node()
        self.take(",")
        assets = self.items(lambda: self.pair("⟨", "⟩"))
        self.take(",")
        native = self.items(lambda: self.pair("⟨", "⟩"))
        self.take(",")
        lexical_digest = self.string()
        self.ws()
        if self.i != len(self.text):
            raise ValueError("Trailing Lean source")
        return n, assets, native, lexical_digest


def load(root):
    root = Path(root)
    text = (root / "Robot.lean").read_text()
    n, assets, native, lexical_digest = Reader(text).read()
    if not re.fullmatch(r"[a-f0-9]{64}", lexical_digest):
        raise ValueError("Invalid lexical digest")
    if text != source(n, assets, native, lexical_digest):
        raise ValueError("Noncanonical Lean source; regenerate the data document")
    for folder, records in [("assets", assets), ("native", native)]:
        if len({k for k, _ in records}) != len(records):
            raise ValueError("Duplicate resource path")
        for name, expected in records:
            if not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise ValueError("Invalid resource digest")
            if sha(safe(root / folder, name).read_bytes()) != expected:
                raise ValueError("Changed Lean document resource: " + name)
    return n, assets, native, lexical_digest


def render_lean(text):
    # Only installed project files and a locally regenerated data-only term run.
    with tempfile.TemporaryDirectory(prefix="fk-lean-document-") as tmp:
        root = Path(tmp)
        copy_proof_project(root)
        target = root / MODULE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((assets_root() / MODULE).read_bytes())
        (root / "Robot.lean").write_text(text)
        built = subprocess.run(
            ["lake", "build", "FluxKernel.UrdfDocument"],
            cwd=root,
            capture_output=True,
            timeout=120,
        )
        if built.returncode:
            raise ValueError(
                "Lean document build failed: "
                + built.stderr.decode(errors="replace")[-2000:]
            )
        run = subprocess.run(
            ["lake", "env", "lean", "--run", "Robot.lean"],
            cwd=root,
            capture_output=True,
            timeout=120,
        )
        if run.returncode:
            raise ValueError(
                "Lean document evaluation failed: "
                + (run.stdout + run.stderr).decode(errors="replace")[-2000:]
            )
        return run.stdout


def to_lean(input_path, output):
    """Convert a URDF file or sealed native bundle into a complete Lean package."""
    from .bundle import verify

    path, output = Path(input_path).resolve(), Path(output).resolve()
    bundle = path if path.is_dir() else None
    if bundle:
        verify(bundle)
        path = bundle / "robot.urdf"
    raw = path.read_bytes()
    n = tree(raw)
    assets = []
    for name in sorted(
        {e.get("filename") for e in xml_root(raw).iter() if e.get("filename")}
    ):
        # No URI rewrite, mesh rescaling or OBJ/STL conversion in this path.
        if ":" in name:
            raise ValueError("Lossless case packages require relative asset paths")
        asset = safe(path.parent, name)
        if asset.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Asset exceeds 64 MiB")
        assets.append([name, sha(asset.read_bytes())])
    native = []
    if bundle:
        files = json.loads((bundle / "manifest.json").read_text())
        for name in sorted({*files, "manifest.json"}):
            native.append([name, sha(safe(bundle, name).read_bytes())])
    text = source(n, assets, native, sha(raw))
    # This also enforces constructor grammar and bounded depth on generated terms.
    if Reader(text).read() != (n, assets, native, sha(raw)):
        raise ValueError("Lean data encoding changed")
    rendered = render_lean(text)
    if tree(rendered) != n:
        raise ValueError("Lean renderer changed the XML information tree")
    output.mkdir(parents=True, exist_ok=False)
    try:
        (output / "Robot.lean").write_text(text)
        (output / "source.urdf").write_bytes(raw)
        for folder, records, base in [
            ("assets", assets, path.parent),
            ("native", native, bundle),
        ]:
            for name, _ in records:
                dest = safe(output / folder, name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(safe(base, name), dest)
        result = {
            "schema": "fk-lean-document-v1",
            "accepted": True,
            "directory": str(output),
            "lean_executed": True,
            "lean_sha256": sha(text.encode()),
            "source_urdf_sha256": sha(raw),
            "xml_information_equal": True,
            "asset_count": len(assets),
            "native_file_count": len(native),
            "physical_status": "unverified",
        }
        (output / "conversion.json").write_text(json.dumps(result, indent=2))
        return result
    except Exception:
        shutil.rmtree(output)
        raise


def from_lean(package, output):
    """Execute a checked data-only Lean term and restore exact bound resources."""
    from .bundle import verify

    package, output = Path(package).resolve(), Path(output).resolve()
    n, assets, native, lexical_digest = load(package)
    raw = render_lean(source(n, assets, native, lexical_digest))
    if tree(raw) != n:
        raise ValueError("Lean output differs from its document")
    lexical = package / "source.urdf"
    exact = lexical.exists()
    if exact:
        original = lexical.read_bytes()
        if sha(original) != lexical_digest:
            raise ValueError("Changed lexical URDF snapshot")
        if tree(original) != n:
            raise ValueError("Stale lexical URDF snapshot; it differs from Lean")
        raw = original
    # Require all referenced files in the Lean resource table, not just a folder.
    referenced = {e.get("filename") for e in xml_root(raw).iter() if e.get("filename")}
    if referenced != {name for name, _ in assets}:
        raise ValueError("Lean asset inventory differs from XML references")
    if native:
        verify(package / "native")
        if tree((package / "native/robot.urdf").read_bytes()) != n:
            raise ValueError("Native sidecar is bound to a different URDF")
        native_raw = (package / "native/robot.urdf").read_bytes()
        if sha(native_raw) != lexical_digest:
            raise ValueError("Native URDF differs from the lexical digest")
        raw = native_raw
        exact = True
    output.mkdir(parents=True, exist_ok=False)
    try:
        if native:
            for name, _ in native:
                dest = safe(output, name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(safe(package / "native", name), dest)
            # Restoring a sealed bundle must never overwrite any sealed bytes.
            if (output / "robot.urdf").read_bytes() != raw:
                raise ValueError("Lexical XML differs from sealed native bytes")
            verify(output)
        else:
            for name, _ in assets:
                dest = safe(output, name)
                # Never allow assets to overwrite the URDF or generator.
                if name in {"robot.urdf", "gen_urdf.py", "lean-rendered.urdf"}:
                    raise ValueError("Reserved output asset path")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(safe(package / "assets", name), dest)
            (output / "robot.urdf").write_bytes(raw)
            # A re-runnable generator retains the Lean package as its authority.
            (output / "gen_urdf.py").write_text(
                "from pathlib import Path\nfrom xml.etree.ElementTree import fromstring\n"
                "from fluxkernel.robotics.lean_document import load, source, render_lean\n"
                f"PACKAGE=Path({str(package)!r})\n"
                "def gen_urdf():\n    return fromstring(render_lean(source(*load(PACKAGE))))\n"
            )
        for name, expected in assets:
            if sha(safe(output, name).read_bytes()) != expected:
                raise ValueError("Restored asset differs from Lean manifest")
        return {
            "accepted": True,
            "directory": str(output),
            "lean_executed": True,
            "xml_information_equal": True,
            "lexical_bytes_restored": exact,
            "asset_bytes_equal": True,
            "native_bundle_restored": bool(native),
            "native_file_count": len(native),
            "physical_status": "unverified",
        }
    except Exception:
        shutil.rmtree(output)
        raise
