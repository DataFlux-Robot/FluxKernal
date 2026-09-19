"""Strategy layer: `fk watch <script.fcad>` — save-to-rebuild preview.

Rebuilds the script into the workspace .fk store whenever its mtime changes
and rewrites a SELF-CONTAINED preview page (STL embedded base64, canvas
software renderer — no CDN, no XHR, works from file://). No GUI in the
kernel (anti-scope); this is a projection.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from .preview import render_page


def run_watch(a) -> int:
    script = Path(a.script).resolve()
    if not script.is_file():
        sys.exit(f"fatal: script not found: {script}")
    preview = Path.cwd() / ".fk-preview"
    preview.mkdir(exist_ok=True)
    fk_exe = Path(sys.executable).parent / ("fk.exe" if os.name == "nt" else "fk")
    fk_cmd = [str(fk_exe)] if fk_exe.exists() else [sys.executable, "-m",
                                                     "fluxkernel.interface.cli"]
    mtime_last = None
    print(f"watching {script.name} — save the file to rebuild; Ctrl+C to stop")
    try:
        while True:
            m = script.stat().st_mtime
            if m != mtime_last:
                mtime_last = m
                print(f"[{time.strftime('%H:%M:%S')}] rebuilding…")
                r = subprocess.run(fk_cmd + ["run", str(script)],
                                   capture_output=True, text=True)
                tail = (r.stdout or "").strip().splitlines()
                for line in tail[-6:]:
                    print("  " + line)
                page = preview / "index.html"
                stl = _newest_promoted_stl()
                if stl:
                    page.write_text(render_page(stl, f"fk watch — {script.name}"),
                                    encoding="utf-8")
                    print(f"  preview: file:///{page.as_posix()}")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nwatch stopped")
        return 0


def _newest_promoted_stl() -> bytes | None:
    """STL bytes of the most recently promoted solid (or None)."""
    from ..store.objstore import Store
    store = Store(Path.cwd() / ".fk")
    for rec in reversed(store.read_edge_log()):
        if rec["record"].get("state") != "promoted":
            continue
        try:
            payload = store.get_object(rec["record"]["output"])["payload"]
        except KeyError:
            continue
        stl = ((payload.get("ground") or {}).get("blobs") or {}).get("stl")
        if stl:
            return store.get_blob(stl)
    return None
