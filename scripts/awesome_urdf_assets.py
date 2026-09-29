#!/usr/bin/env python3
"""Resolve and fetch referenced mesh/texture bytes from pinned corpus snapshots.

Resolution decisions are recorded, never written into the source URDF. Missing
or ambiguous references remain failures. Does not execute upstream code.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import posixpath
import re
import shlex
import struct
import subprocess
from urllib.parse import quote, unquote
import xml.etree.ElementTree as ET

from awesome_urdf_corpus import fetch
from fluxkernel.robotics.sources import safe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    contexts = {}
    cases = []
    jobs = {}
    for case in inventory["cases"]:
        key = case["repository"] + "@" + case["commit"]
        if key not in contexts:
            root = Path(case["source_root"])
            paths = (
                [
                    e["path"]
                    for e in json.loads(Path(case["tree_cache"]).read_text())["tree"][
                        "tree"
                    ]
                    if e["type"] == "blob"
                ]
                if case.get("tree_cache")
                else subprocess.check_output(
                    ["git", "ls-tree", "-r", "--name-only", case["commit"]],
                    cwd=root,
                    text=True,
                ).splitlines()
            )
            contexts[key] = dict(
                repository=case["repository"],
                commit=case["commit"],
                root=root,
                paths=set(paths),
            )
        ctx = contexts[key]
        row = {"case_id": case["case_id"], "references": []}
        try:
            xml = ET.parse(case["file"]).getroot()
            uris = sorted(
                {
                    e.get("filename")
                    for e in xml.iter()
                    if e.tag in ("mesh", "texture") and e.get("filename")
                }
            )
            for uri in uris:
                try:
                    path, method = resolve(
                        ctx, case.get("resolved_path", case["path"]), uri
                    )
                    row["references"].append(
                        dict(
                            uri=uri,
                            path=path,
                            resolution=method,
                            resource_key=key + ":" + path,
                        )
                    )
                    jobs[(key, path)] = ctx
                except Exception as exc:
                    row["references"].append(dict(uri=uri, error=str(exc)))
        except Exception as exc:
            row["error"] = str(exc)
        cases.append(row)
    resources = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        pending = {
            pool.submit(download, ctx, path): (key, path)
            for (key, path), ctx in jobs.items()
        }
        while pending:
            future = next(as_completed(pending))
            key, path = pending.pop(future)
            result = future.result()
            resources[key + ":" + path] = result
            if len(resources) % 100 == 0:
                print(
                    "resources", len(resources), "remaining", len(pending), flush=True
                )
            if result["status"] == "downloaded":
                ctx = contexts[key]
                try:
                    dependencies = secondary(Path(result["file"]))
                    for uri in dependencies:
                        try:
                            dep, method = resolve(ctx, path, uri)
                            result.setdefault("dependencies", []).append(
                                {
                                    "uri": uri,
                                    "path": dep,
                                    "resolution": method,
                                    "resource_key": key + ":" + dep,
                                }
                            )
                            if (key, dep) not in jobs:
                                jobs[(key, dep)] = ctx
                                pending[pool.submit(download, ctx, dep)] = (key, dep)
                        except Exception as exc:
                            result.setdefault("dependency_errors", []).append(
                                {"uri": uri, "error": str(exc)}
                            )
                except Exception as exc:
                    result["dependency_parse_error"] = str(exc)
            if len(resources) % 50 == 0:
                args.output.write_text(
                    json.dumps(
                        {"cases": cases, "resources": resources, "completed": False},
                        indent=2,
                    )
                )
    for row in cases:
        seen = set()

        def available(key):
            if key in seen:
                return True
            seen.add(key)
            r = resources.get(key, {})
            return (
                r.get("status") == "downloaded"
                and not r.get("dependency_errors")
                and not r.get("dependency_parse_error")
                and all(available(d["resource_key"]) for d in r.get("dependencies", []))
            )

        row["complete"] = not row.get("error") and all(
            "resource_key" in ref and available(ref["resource_key"])
            for ref in row["references"]
        )
    args.output.write_text(
        json.dumps(
            {"cases": cases, "resources": resources, "completed": True}, indent=2
        )
    )
    print(
        "Finished",
        len(resources),
        "resources;",
        sum(c["complete"] for c in cases),
        "complete cases",
        flush=True,
    )


def resolve(ctx, source, uri):
    uri = unquote(uri.strip())
    paths = ctx["paths"]
    if uri.startswith("package://"):
        package, sep, relative = uri[10:].partition("/")
        if not sep or not package or ".." in relative.split("/"):
            raise ValueError("Invalid package URI")
        candidates = [
            p
            for p in paths
            if p == package + "/" + relative
            or p.endswith("/" + package + "/" + relative)
        ]
        if len(candidates) == 1:
            return candidates[0], "package-directory"
        if relative in paths:
            return relative, "repository-package-root"
        candidates = [p for p in paths if p.endswith("/" + relative)]
        if len(candidates) == 1:
            return candidates[0], "unique-package-suffix"
        raise ValueError(
            "Package reference missing or ambiguous: "
            + str(len(candidates))
            + " candidates"
        )
    if "://" in uri or uri.startswith("/") or "\\" in uri:
        raise ValueError("External or absolute URI unresolved")
    candidate = posixpath.normpath(posixpath.join(posixpath.dirname(source), uri))
    if candidate in paths and not candidate.startswith("../"):
        return candidate, "source-relative"
    if uri in paths:
        return uri, "repository-relative"
    # Legacy publishers sometimes use cwd-relative filenames. Record this recovery.
    suffix = uri.lstrip("./")
    candidates = [p for p in paths if p.endswith("/" + suffix)]
    if len(candidates) == 1:
        return candidates[0], "unique-relative-suffix"
    raise ValueError(
        "Relative reference missing or ambiguous: "
        + str(len(candidates))
        + " candidates"
    )


def download(ctx, path):
    file = safe(ctx["root"], path)
    result = {
        "repository": ctx["repository"],
        "commit": ctx["commit"],
        "path": path,
        "file": str(file.resolve()),
    }
    try:
        if ctx["repository"].startswith("codeberg:"):
            raw = file.read_bytes()
        else:
            raw = fetch(
                f"https://raw.githubusercontent.com/{ctx['repository']}/{ctx['commit']}/{quote(path)}",
                file,
            )
        if raw.startswith(b"version https://git-lfs.github.com/spec/v1"):
            expected = re.search(rb"oid sha256:([a-f0-9]{64})", raw)
            if not expected:
                raise ValueError("Malformed Git LFS pointer")
            payload = fetch(
                f"https://media.githubusercontent.com/media/{ctx['repository']}/{ctx['commit']}/{quote(path)}",
                file.with_name(file.name + ".lfs-payload"),
            )
            if hashlib.sha256(payload).hexdigest() != expected[1].decode():
                raise ValueError("LFS payload digest differs")
            result["lfs_pointer_sha256"] = hashlib.sha256(raw).hexdigest()
            file.write_bytes(payload)
            file.with_name(file.name + ".lfs-payload").unlink()
            raw = payload
        result.update(
            status="downloaded", sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)
        )
    except Exception as exc:
        result.update(status="failed", error=str(exc))
    return result


def secondary(path):
    suffix = path.suffix.lower()
    if suffix in (".gltf", ".glb"):
        raw = path.read_bytes()
        if suffix == ".glb":
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
        model = json.loads(raw)
        return [
            item["uri"]
            for field in ("buffers", "images")
            for item in model.get(field, [])
            if item.get("uri") and not item["uri"].startswith("data:")
        ]
    if suffix == ".dae":
        root = ET.fromstring(path.read_bytes())
        return [
            e.text.strip()
            for e in root.findall(".//{*}library_images/{*}image/{*}init_from")
            if e.text and not e.text.strip().startswith("#")
        ]
    if suffix == ".obj":
        return [
            v
            for line in path.read_text(errors="strict").splitlines()
            if line.strip().startswith("mtllib ")
            for v in shlex.split(line.strip())[1:]
        ]
    if suffix == ".mtl":
        return [
            shlex.split(line.strip())[-1]
            for line in path.read_text().splitlines()
            if line.strip().startswith(("map_", "bump ", "disp ", "decal "))
        ]
    return []


if __name__ == "__main__":
    main()
