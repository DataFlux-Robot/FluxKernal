"""Strategy layer: `fk watch <script.fcad>` — save-to-rebuild preview.

Rebuilds the script into a scratch .fk store whenever its mtime changes and
serves a static three.js page (meta-refresh) that displays the newest
exported STL. No GUI in the kernel (anti-scope); this is a projection.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>fk watch</title>
<meta http-equiv="refresh" content="2">
<style>body{margin:0;background:#111;color:#ccc;font:13px monospace}</style>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"}}</script>
</head><body>
<div id="info">fk watch — newest STL</div>
<script type="module">
import * as THREE from 'three';
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x181818);
const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.1, 10000);
camera.position.set(120, 90, 120);
const renderer = new THREE.WebGLRenderer();
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
scene.add(new THREE.AmbientLight(0xffffff, 0.5));
const dl = new THREE.DirectionalLight(0xffffff, 1.0); dl.position.set(1, 2, 1.5);
scene.add(dl);
const loader = new THREE.STLLoader();
loader.load('preview.stl?ts=' + Date.now(), g => {
  g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({color:0x7fb3d5, metalness:.3, roughness:.5}));
  g.computeBoundingBox();
  const c = g.boundingBox.getCenter(new THREE.Vector3());
  mesh.position.sub(c);
  scene.add(mesh);
  const s = g.boundingBox.getSize(new THREE.Vector3()).length();
  camera.position.set(s, s*0.7, s); camera.lookAt(0, 0, 0);
});
(function animate(){ requestAnimationFrame(animate);
  renderer.render(scene, camera); })();
</script></body></html>
"""


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
                _export_newest_stl(preview)
                (preview / "index.html").write_text(_PAGE, encoding="utf-8")
                print(f"  preview: file:///{(preview / 'index.html').as_posix()}")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nwatch stopped")
        return 0


def _export_newest_stl(preview: Path):
    """Copy the STL of the most recently promoted solid into the preview dir."""
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
            shutil.copyfile(store.blobs / stl.replace(":", "_"),
                            preview / "preview.stl")
            return
