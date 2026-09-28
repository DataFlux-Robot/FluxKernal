"""Fetch pinned model data only. Never execute upstream Python/firmware."""

import hashlib
import json
from pathlib import Path, PurePosixPath
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

PROFILES = {
    "microduck": {
        "repo": "pollen-robotics/microduck_rl",
        "commit": "1e79c29c97d8b38aee9eefde77a545860ba7658e",
        "directory": "src/mjlab_microduck/robot/microduck",
        "entry": "robot_walk.xml",
        "servo": "xl330",
    },
    "xgoduck": {
        "repo": "LuwuDynamics/xgoduck_rl",
        "commit": "326d77a1122870bdefa2c36403937502c958e69c",
        "directory": "src/mjlab_microduck/robot/xgoduck",
        "entry": "robot_walk.xml",
        "servo": "hls1910",
    },
}


def fetch(url, limit=64 * 1024 * 1024):
    with urlopen(
        Request(url, headers={"User-Agent": "FluxKernel robot importer"}), timeout=90
    ) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Source exceeds byte limit")
    return raw


def safe(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or not path.parts:
        raise ValueError("Unsafe relative path")
    target = Path(root) / relative
    if any(p.is_symlink() for p in [target, *target.parents]):
        raise ValueError("Symlink source path")
    if not target.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("Path escapes source root")
    return target


def download(name, output):
    profile = PROFILES[name]
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    tree = json.loads(
        fetch(
            f"https://api.github.com/repos/{profile['repo']}/git/trees/{profile['commit']}?recursive=1"
        )
    )
    if tree.get("truncated"):
        raise ValueError("Truncated upstream tree")
    prefix = profile["directory"] + "/"
    entries = [
        e
        for e in tree["tree"]
        if e["type"] == "blob"
        and (
            e["path"] in ("LICENSE", "README.md")
            or (
                e["path"].startswith(prefix)
                and PurePosixPath(e["path"]).suffix.lower()
                in (".xml", ".stl", ".obj", ".json")
                and "/urdf/" not in e["path"]
            )
        )
    ]
    if (
        not entries
        or len(entries) > 200
        or sum(e.get("size", 0) for e in entries) > 256 * 1024 * 1024
    ):
        raise ValueError("Model source budget exceeded")

    def get(e):
        if e.get("mode") != "100644":
            raise ValueError("Expected regular model file")
        path = safe(root, e["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (
            path.read_bytes()
            if path.exists()
            else fetch(
                f"https://raw.githubusercontent.com/{profile['repo']}/{profile['commit']}/{e['path']}"
            )
        )
        git_hash = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw
        ).hexdigest()
        if git_hash != e["sha"]:
            raise ValueError("Upstream blob identity mismatch: " + e["path"])
        path.write_bytes(raw)
        return e["path"], {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob": git_hash,
            "bytes": len(raw),
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        files = dict(pool.map(get, entries))
    record = {
        **profile,
        "files": files,
        "license": "Upstream repository Apache-2.0; retain LICENSE; third-party/hardware rights require separate review",
    }
    (root / "source.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


HARDWARE = {
    "repo": "LuwuDynamics/xgoduck_hardware",
    "commit": "a8f3356dd416c9a9bd47f5de68fb7a67eab829b6",
}


def hardware_inventory(output):
    """Separate physical source inventory; never infer CAD-body/BOM equivalence."""
    import zipfile, xml.etree.ElementTree as ET

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    tree = json.loads(
        fetch(
            f"https://api.github.com/repos/{HARDWARE['repo']}/git/trees/{HARDWARE['commit']}?recursive=1"
        )
    )
    if tree.get("truncated"):
        raise ValueError("Truncated hardware tree")
    entries = [
        e
        for e in tree["tree"]
        if e["type"] == "blob"
        and (
            e["path"].startswith("structure/")
            or e["path"]
            in [
                "bom.xlsx",
                "PCBA/BOM.xlsx",
                "PCBA/ArduinoUnoQ.step",
                "Assembly_Guide.pdf",
                "readme.md",
            ]
        )
    ]
    if (
        not entries
        or len(entries) > 200
        or sum(e.get("size", 0) for e in entries) > 256 * 1024 * 1024
    ):
        raise ValueError("Hardware source budget exceeded")

    def get(e):
        if e.get("mode") != "100644":
            raise ValueError("Expected regular hardware source")
        path = safe(root, e["path"])
        raw = (
            path.read_bytes()
            if path.exists()
            else fetch(
                f"https://raw.githubusercontent.com/{HARDWARE['repo']}/{HARDWARE['commit']}/{e['path']}"
            )
        )
        if (
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            != e["sha"]
        ):
            raise ValueError("Hardware source changed")
        path = safe(root, e["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {
            "file": "hardware/" + e["path"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob": e["sha"],
            "quantity_hint": 2 if Path(e["path"]).name.startswith("2x_") else None,
            "quantity_source": "filename convention in upstream readme"
            if Path(e["path"]).name.startswith("2x_")
            else "not-established",
            "route": "unclassified",
            "rigid_body_mapping": None,
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        items = list(pool.map(get, entries))
    sheets = {}
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for relative in ["bom.xlsx", "PCBA/BOM.xlsx"]:
        with zipfile.ZipFile(root / relative) as z:
            if sum(i.file_size for i in z.infolist()) > 16 * 1024 * 1024:
                raise ValueError("Oversized BOM worksheet")
            strings = []
            if "xl/sharedStrings.xml" in z.namelist():
                strings = [
                    "".join(e.itertext())
                    for e in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(
                        "s:si", ns
                    )
                ]
            rows = []
            for file in z.namelist():
                if not file.startswith("xl/worksheets/sheet") or not file.endswith(
                    ".xml"
                ):
                    continue
                for row in ET.fromstring(z.read(file)).findall(".//s:row", ns):
                    cells = {}
                    for cell in row.findall("s:c", ns):
                        v = cell.find("s:v", ns)
                        value = v.text if v is not None else "".join(cell.itertext())
                        if cell.get("t") == "s" and value:
                            value = strings[int(value)]
                        formula = cell.find("s:f", ns)
                        cells[cell.get("r")] = (
                            value
                            if formula is None
                            else {
                                "formula_not_executed": formula.text,
                                "cached_value": value,
                            }
                        )
                    if cells:
                        rows.append({"worksheet": file, "cells": cells})
            sheets[relative] = rows
    return {
        "source": HARDWARE,
        "items": items,
        "bom_source_rows": sheets,
        "license_status": "No repository-level LICENSE at pinned revision; redistribution rights not inferred",
        "status": "source-inventory-only",
        "open": [
            "Rigid-body-to-physical-part mapping",
            "material/process classification",
            "supplier qualification",
            "assembly and manufacturing validation",
        ],
    }
