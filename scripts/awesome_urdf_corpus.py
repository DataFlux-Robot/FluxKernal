#!/usr/bin/env python3
"""Pin and enumerate every URDF-labelled scope in Awesome Robot Descriptions.

No upstream Python, Xacro or build scripts are executed. Inventory JSON retains
failed scopes rather than shrinking the denominator. Source downloads stay local.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import posixpath
import re
import subprocess
import time
from urllib.parse import urlparse, quote
from urllib.request import urlopen
from fluxkernel.robotics.sources import safe

CATALOG_COMMIT = "706eccf089099055241d7829f9a1d8108353fbce"


def resolved_url(url):
    # Reviewed same-robot corrections, not guessed alternatives. Keep original URL.
    if url.startswith(
        "https://github.com/agilexrobotics/Piper_ros/tree/ros-noetic-no-aloha/"
    ):
        return url.replace("/tree/ros-noetic-no-aloha/", "/tree/noetic/")
    if url.startswith(
        "https://github.com/limxdynamics/tron2-robot-description/tree/main/tron2/"
    ):
        return url.replace("/tree/main/tron2/", "/tree/main/tron2a/")
    if (
        url
        == "https://github.com/unitreerobotics/unitree_mujoco/tree/main/data/go1/urdf"
    ):
        return "https://github.com/unitreerobotics/unitree_ros/tree/master/robots/go1_description"
    return url


def catalog_snapshot(root):
    if (root / "catalog.json").exists():
        return json.loads((root / "catalog.json").read_text())
    raw = fetch(
        f"https://raw.githubusercontent.com/robot-descriptions/awesome-robot-descriptions/{CATALOG_COMMIT}/README.md",
        root / "README.md",
    ).decode()
    refs = dict(re.findall(r"^\[([^\]]+)\]:\s*(\S+)", raw, re.M))
    rows, category = [], ""
    for line in raw.splitlines():
        if line.startswith("### "):
            category = line[4:]
        if not line.startswith("|"):
            continue
        for match in re.finditer(r"\[URDF\](?:\(([^)]+)\)|\[([^\]]+)\])", line):
            rows.append(
                {
                    "name": line.strip("|").split("|")[0].strip(),
                    "category": category,
                    "url": match[1] or refs[match[2]],
                    "row": line,
                }
            )
    data = {"catalog_commit": CATALOG_COMMIT, "entries": rows}
    (root / "catalog.json").write_text(json.dumps(data, indent=2))
    return data


def api(endpoint):
    result = subprocess.run(
        ["gh", "api", endpoint], capture_output=True, text=True, timeout=120
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-800:])
    return json.loads(result.stdout)


def fetch(url, path):
    path = Path(path)
    if path.exists():
        return path.read_bytes()
    for attempt in range(3):
        try:
            with urlopen(url, timeout=90) as response:
                raw = response.read(64 * 1024 * 1024 + 1)
            if len(raw) > 64 * 1024 * 1024:
                raise ValueError("Download exceeds 64 MiB")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            return raw
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def replay(root, manifest):
    """Re-fetch the recorded revisions rather than resolving current branches."""
    report = json.loads(Path(manifest).read_text())
    contexts = {}
    for case in report["cases"]:
        repo, commit = case["repository"], case["commit"]
        if not re.fullmatch("[a-f0-9]{40}", commit):
            raise ValueError("Expected pinned full Git SHA")
        if (repo, commit) in contexts:
            continue
        if repo == "codeberg:upkie/cookie_description":
            folder = root / "cookie"
            if not folder.exists():
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--no-checkout",
                        "--depth",
                        "1",
                        "https://codeberg.org/upkie/cookie_description.git",
                        str(folder),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=180,
                )
                subprocess.run(
                    ["git", "fetch", "--depth", "1", "origin", commit],
                    cwd=folder,
                    check=True,
                    capture_output=True,
                    timeout=180,
                )
                subprocess.run(
                    ["git", "checkout", "--detach", commit],
                    cwd=folder,
                    check=True,
                    capture_output=True,
                    timeout=180,
                )
            if (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=folder, text=True
                ).strip()
                != commit
            ):
                raise ValueError("Existing Codeberg cache has a different revision")
            contexts[(repo, commit)] = (folder, None)
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("Invalid GitHub repository identity")
        folder = root / "sources" / (repo.replace("/", "--") + "--" + commit[:12])
        cache = None
        for existing in (root / "trees").glob("*.json"):
            data = json.loads(existing.read_text())
            if data["repository"] == repo and data["commit"] == commit:
                cache = existing
                break
        if cache is None:
            cache = (
                root
                / "trees"
                / (
                    hashlib.sha256((repo + "@" + commit).encode()).hexdigest()[:16]
                    + ".json"
                )
            )
            data = {
                "repository": repo,
                "requested_ref": commit,
                "commit": commit,
                "tree": api(f"repos/{repo}/git/trees/{commit}?recursive=1"),
            }
            if data["tree"].get("truncated"):
                raise ValueError("Pinned tree is truncated")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, indent=2))
        contexts[(repo, commit)] = (folder, cache)

    def download(case):
        row = dict(case)
        try:
            repo, commit = case["repository"], case["commit"]
            folder, cache = contexts[(repo, commit)]
            relative = case.get("resolved_path", case["path"])
            target = safe(folder, relative)
            raw = (
                target.read_bytes()
                if repo.startswith("codeberg:")
                else fetch(
                    f"https://raw.githubusercontent.com/{repo}/{commit}/{quote(relative)}",
                    target,
                )
            )
            if hashlib.sha256(raw).hexdigest() != case["sha256"]:
                raise ValueError("Pinned source SHA-256 differs")
            row.update(
                status="downloaded",
                file=str(target.resolve()),
                source_root=str(folder.resolve()),
                tree_cache=str(cache) if cache else None,
            )
        except Exception as exc:
            row.update(status="download_failed", error=str(exc))
        return row

    with ThreadPoolExecutor(max_workers=8) as pool:
        report["cases"] = list(pool.map(download, report["cases"]))
    for scope in report["scopes"]:
        if (scope.get("repository"), scope.get("commit")) in contexts:
            _, cache = contexts[(scope["repository"], scope["commit"])]
            scope["tree_cache"] = str(cache) if cache else None
    report["replayed_from"] = str(Path(manifest).resolve())
    (root / "inventory.json").write_text(json.dumps(report, indent=2))
    print(
        "Replayed",
        len(report["cases"]),
        "pinned URDF paths;",
        sum(c["status"] == "downloaded" for c in report["cases"]),
        "verified hashes",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--pinned",
        type=Path,
        help="Replay an archived inventory at exact commits and source hashes",
    )
    args = parser.parse_args()
    root = args.root
    root.mkdir(parents=True, exist_ok=True)
    if args.pinned:
        replay(root, args.pinned)
        return
    catalog = catalog_snapshot(root)
    groups = {}
    other = []
    for i, row in enumerate(catalog["entries"]):
        corrected = resolved_url(row["url"])
        url = urlparse(corrected)
        parts = url.path.strip("/").split("/")
        row = dict(row, entry_id=i)
        if corrected != row["url"]:
            row.update(
                resolved_url=corrected,
                resolution_note="Reviewed same-robot correction for stale catalog branch/path",
            )
        if url.hostname != "github.com":
            if row["url"] == "https://codeberg.org/upkie/cookie_description":
                folder = root / "cookie"
                try:
                    if not folder.exists():
                        subprocess.run(
                            [
                                "git",
                                "clone",
                                "--depth",
                                "1",
                                row["url"] + ".git",
                                str(folder),
                            ],
                            check=True,
                            capture_output=True,
                            timeout=180,
                        )
                    commit = subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=folder, text=True
                    ).strip()
                    paths = [
                        p
                        for p in subprocess.check_output(
                            ["git", "ls-tree", "-r", "--name-only", commit],
                            cwd=folder,
                            text=True,
                        ).splitlines()
                        if p.lower().endswith(".urdf")
                    ]
                    other.append(
                        dict(
                            row,
                            status="enumerated",
                            repository="codeberg:upkie/cookie_description",
                            commit=commit,
                            urdfs=paths,
                        )
                    )
                except Exception as exc:
                    other.append(dict(row, status="inventory_failed", error=str(exc)))
            else:
                other.append(dict(row, status="non_github_source"))
            continue
        repo = "/".join(parts[:2])
        ref = parts[3] if len(parts) > 3 else "HEAD"
        scope = "/".join(parts[4:])
        groups.setdefault((repo, ref), []).append(dict(row, scope=scope))

    def inventory(group):
        (repo, ref), rows = group
        key = hashlib.sha256(f"{repo}@{ref}".encode()).hexdigest()[:16]
        cache = root / "trees" / (key + ".json")
        try:
            if cache.exists():
                data = json.loads(cache.read_text())
            else:
                commit = api(f"repos/{repo}/commits/{quote(ref, safe='')}")
                tree = api(f"repos/{repo}/git/trees/{commit['sha']}?recursive=1")
                data = {
                    "repository": repo,
                    "requested_ref": ref,
                    "commit": commit["sha"],
                    "tree": tree,
                }
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data, indent=2))
            if data["tree"].get("truncated"):
                raise ValueError("Repository tree truncated; no completeness claim")
            paths = [e["path"] for e in data["tree"]["tree"] if e["type"] == "blob"]
            out = []
            for row in rows:
                scope = row["scope"].rstrip("/")
                urdfs = [
                    p
                    for p in paths
                    if p.lower().endswith(".urdf")
                    and (not scope or p == scope or p.startswith(scope + "/"))
                ]
                out.append(
                    dict(
                        row,
                        repository=repo,
                        commit=data["commit"],
                        tree_cache=str(cache),
                        urdfs=urdfs,
                        status=(
                            "enumerated_via_explicit_fallback"
                            if row.get("resolved_url")
                            else "enumerated"
                        )
                        if urdfs
                        else "no_urdf_in_linked_scope",
                    )
                )
            return out
        except Exception as exc:
            return [
                dict(row, repository=repo, status="inventory_failed", error=str(exc))
                for row in rows
            ]

    scopes = list(other)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(inventory, groups.items()):
            scopes.extend(result)
            print("inventoried", len(scopes), "/", len(catalog["entries"]), flush=True)
    cases = {}
    for scope in scopes:
        for path in scope.get("urdfs", []):
            identity = f"{scope['repository']}@{scope['commit']}:{path}"
            key = hashlib.sha256(identity.encode()).hexdigest()[:20]
            if key not in cases:
                cases[key] = {
                    "case_id": key,
                    "repository": scope["repository"],
                    "commit": scope["commit"],
                    "path": path,
                    "entry_ids": [],
                    "tree_cache": scope.get("tree_cache"),
                }
            cases[key]["entry_ids"].append(scope["entry_id"])
    report = {
        "catalog_commit": catalog["catalog_commit"],
        "scopes": sorted(scopes, key=lambda s: s["entry_id"]),
        "cases": list(cases.values()),
    }
    (root / "inventory.json").write_text(json.dumps(report, indent=2))

    def download(case):
        try:
            folder = (
                root
                / "sources"
                / (case["repository"].replace("/", "--") + "--" + case["commit"][:12])
            )
            if case["repository"].startswith("codeberg:"):
                folder = root / "cookie"
                target = safe(folder, case["path"])
                raw = target.read_bytes()
                return dict(
                    case,
                    status="downloaded",
                    file=str(target.resolve()),
                    source_root=str(folder.resolve()),
                    sha256=hashlib.sha256(raw).hexdigest(),
                )
            target = safe(folder, case["path"])
            raw = fetch(
                f"https://raw.githubusercontent.com/{case['repository']}/{case['commit']}/{quote(case['path'])}",
                target,
            )
            nodes = {
                e["path"]: e
                for e in json.loads(Path(case["tree_cache"]).read_text())["tree"][
                    "tree"
                ]
            }
            if nodes[case["path"]].get("mode") == "120000":
                relative = raw.decode().strip()
                resolved = posixpath.normpath(
                    posixpath.join(posixpath.dirname(case["path"]), relative)
                )
                if (
                    resolved not in nodes
                    or resolved.startswith("../")
                    or nodes[resolved].get("mode") == "120000"
                ):
                    raise ValueError(
                        "URDF symlink target escapes snapshot, is absent, or is another symlink"
                    )
                case = dict(
                    case,
                    git_mode="120000",
                    symlink_target=relative,
                    symlink_blob_sha256=hashlib.sha256(raw).hexdigest(),
                    resolved_path=resolved,
                )
                target = safe(folder, resolved)
                raw = fetch(
                    f"https://raw.githubusercontent.com/{case['repository']}/{case['commit']}/{quote(resolved)}",
                    target,
                )
            return dict(
                case,
                status="downloaded",
                file=str(target.resolve()),
                source_root=str(folder.resolve()),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        except Exception as exc:
            return dict(case, status="download_failed", error=str(exc))

    completed = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(download, c) for c in cases.values()]):
            completed.append(future.result())
            if len(completed) % 20 == 0:
                print("downloaded", len(completed), "/", len(cases), flush=True)
            report["cases"] = sorted(completed, key=lambda c: c["case_id"])
            (root / "inventory.json").write_text(json.dumps(report, indent=2))
    print(
        "Complete scopes", len(scopes), "unique URDF files", len(completed), flush=True
    )


if __name__ == "__main__":
    main()
