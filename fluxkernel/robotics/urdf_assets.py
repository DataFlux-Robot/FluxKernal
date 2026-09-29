"""Bound local geometry resources and their non-executable dependencies.

Plugin filenames name runtime libraries, not geometry assets. Xacro templates
must be expanded explicitly before claiming a complete robot asset package.
"""

import hashlib
import json
from pathlib import Path
import posixpath
import shlex
import struct
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from .sources import safe
from .urdf_import import xml_root


def references(raw):
    xml = xml_root(raw)
    if any(
        isinstance(e.tag, str) and e.tag.startswith("{http://www.ros.org/wiki/xacro}")
        for e in xml.iter()
    ):
        raise ValueError("Expand Xacro before creating a complete URDF asset package")
    return sorted(
        {
            e.get("filename")
            for e in xml.iter()
            if e.tag in ("mesh", "texture") and e.get("filename")
        }
    )


def dependencies(path, raw):
    extension = Path(path).suffix.lower()
    if extension in (".gltf", ".glb"):
        if extension == ".glb":
            if len(raw) < 20 or raw[:4] != b"glTF":
                raise ValueError("Invalid GLB header")
            version, total, length, kind = struct.unpack("<4I", raw[4:20])
            if (
                version != 2
                or total != len(raw)
                or kind != 0x4E4F534A
                or 20 + length > len(raw)
            ):
                raise ValueError("Invalid GLB JSON chunk")
            raw = raw[20 : 20 + length]
        data = json.loads(raw)
        return [
            item["uri"]
            for field in ("buffers", "images")
            for item in data.get(field, [])
            if item.get("uri") and not item["uri"].startswith("data:")
        ]
    if extension == ".dae":
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ValueError("DAE entity declarations unsupported")
        root = ET.fromstring(raw)
        return [
            e.text.strip()
            for e in root.findall(".//{*}library_images/{*}image/{*}init_from")
            if e.text and not e.text.strip().startswith("#")
        ]
    if extension in (".obj", ".mtl"):
        output = []
        for line in raw.decode().splitlines():
            stripped = line.strip()
            if extension == ".obj" and stripped.startswith("mtllib "):
                output.extend(shlex.split(stripped, comments=True)[1:])
            elif extension == ".mtl" and stripped.startswith(
                ("map_", "bump ", "disp ", "decal ")
            ):
                fields = shlex.split(stripped, comments=True)
                if len(fields) < 2:
                    raise ValueError("Missing material texture filename")
                output.append(fields[-1])
        return output
    return []


def records(raw, root):
    pending = list(references(raw))
    found = {}
    while pending:
        name = pending.pop()
        if name in found:
            continue
        if len(found) >= 10000:
            raise ValueError("Asset dependency count exceeds 10000")
        if ":" in name:
            raise ValueError("Lossless case packages require relative asset paths")
        asset = safe(root, name)
        if asset.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Asset exceeds 64 MiB")
        content = asset.read_bytes()
        found[name] = hashlib.sha256(content).hexdigest()
        for uri in dependencies(name, content):
            uri = unquote(uri)
            if ":" in uri or uri.startswith("/") or "\\" in uri:
                raise ValueError("External asset dependency unsupported")
            child = posixpath.normpath(posixpath.join(posixpath.dirname(name), uri))
            safe(root, child)
            pending.append(child)
    return [[name, found[name]] for name in sorted(found)]
