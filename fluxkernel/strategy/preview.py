"""Self-contained STL preview page (file://-safe, zero dependencies).

Why not three.js + CDN: module scripts and XHR/fetch of local files are
blocked by browsers on file:// origins, and the CDN needs network. Instead
the STL is embedded as base64 and rendered by a small canvas software
renderer (painter's algorithm + backface culling, drag to rotate, wheel to
zoom). Coarse-mesh STLs (a few thousand triangles) run at full interactivity.
"""
from __future__ import annotations

import base64

_PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
body{margin:0;background:#14171c;overflow:hidden}
canvas{display:block;cursor:grab}
canvas:active{cursor:grabbing}
#hud{position:fixed;left:12px;top:10px;color:#7fa8c9;font:12px monospace;
     user-select:none;pointer-events:none;line-height:1.7}
#hud b{color:#b7d9f0;font-weight:600}
</style></head>
<body>
<div id="hud"><b>__TITLE__</b><br>__LEGEND__<br>drag = rotate &nbsp; wheel = zoom</div>
<canvas id="c"></canvas>
<script>
"use strict";
const B64 = "__B64__";
const LABELS = __LABELS__;

function abFromB64(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

// ---- parse STL (binary, or ASCII fallback) ----
const buf = abFromB64(B64);
const dv = new DataView(buf);
let verts, norms, n;
const head = new Uint8Array(buf, 0, Math.min(5, buf.byteLength));
const isAscii = head[0] === 115 && head[1] === 111 && head[2] === 108 &&
                head[3] === 105 && head[4] === 100;   // "solid"
if (isAscii) {
  const text = new TextDecoder().decode(buf);
  const nums = [];
  let re = /vertex\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)/g, m2;
  while ((m2 = re.exec(text)) !== null)
    nums.push(+m2[1], +m2[2], +m2[3]);
  n = nums.length / 9;
  verts = new Float32Array(nums);
  norms = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    // Newell-normal of the triangle
    const a = i * 9;
    const ux = verts[a+3]-verts[a], uy = verts[a+4]-verts[a+1], uz = verts[a+5]-verts[a+2];
    const vx = verts[a+6]-verts[a], vy = verts[a+7]-verts[a+1], vz = verts[a+8]-verts[a+2];
    let nx = uy*vz-uz*vy, ny = uz*vx-ux*vz, nz = ux*vy-uy*vx;
    const L = Math.hypot(nx, ny, nz) || 1;
    norms[i*3] = nx/L; norms[i*3+1] = ny/L; norms[i*3+2] = nz/L;
  }
} else {
  n = dv.getUint32(80, true);
  verts = new Float32Array(n * 9);
  norms = new Float32Array(n * 3);
  let o = 84;
  for (let i = 0; i < n; i++) {
    norms[i * 3] = dv.getFloat32(o, true);
    norms[i * 3 + 1] = dv.getFloat32(o + 4, true);
    norms[i * 3 + 2] = dv.getFloat32(o + 8, true);
    for (let v = 0; v < 9; v++) verts[i * 9 + v] = dv.getFloat32(o + 12 + v * 4, true);
    o += 50;
  }
}

// ---- reorient for viewing: world +Y (fuselage axis) -> screen +X ----
(function () {
  for (let i = 0; i < verts.length; i += 3) {
    const x = verts[i], y = verts[i + 1], z = verts[i + 2];
    verts[i] = y; verts[i + 1] = z; verts[i + 2] = x;
  }
  for (let i = 0; i < norms.length; i += 3) {
    const x = norms[i], y = norms[i + 1], z = norms[i + 2];
    norms[i] = y; norms[i + 1] = z; norms[i + 2] = x;
  }
})();

// ---- bbox / center ----
let mn = [1e30, 1e30, 1e30], mx = [-1e30, -1e30, -1e30];
for (let i = 0; i < verts.length; i += 3)
  for (let k = 0; k < 3; k++) {
    const c = verts[i + k];
    if (c < mn[k]) mn[k] = c;
    if (c > mx[k]) mx[k] = c;
  }
const cx = (mn[0] + mx[0]) / 2, cy = (mn[1] + mx[1]) / 2, cz = (mn[2] + mx[2]) / 2;
const spanX = (mx[0] - mn[0]) || 1, spanY = (mx[1] - mn[1]) || 1;

// ---- camera ----
let theta = 0.55, phi = 0.3, zoom = 1;
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const rot = new Float32Array(verts.length);
const rnorm = new Float32Array(norms.length);
const idx = new Int32Array(n);
const depth = new Float32Array(n);
const L = [0.5, 0.72, 0.48];

function draw() {
  const w = canvas.width, h = canvas.height;
  ctx.fillStyle = "#14171c";
  ctx.fillRect(0, 0, w, h);
  const ct = Math.cos(theta), st = Math.sin(theta);
  const cp = Math.cos(phi), sp = Math.sin(phi);
  const scale = Math.min(w / spanX, h / spanY) * 0.82 * zoom;
  for (let i = 0; i < verts.length; i += 3) {
    const x = verts[i] - cx, y = verts[i + 1] - cy, z = verts[i + 2] - cz;
    const x1 = ct * x + st * z, z1 = -st * x + ct * z;
    rot[i] = x1;
    rot[i + 1] = cp * y - sp * z1;
    rot[i + 2] = sp * y + cp * z1;
  }
  for (let i = 0; i < norms.length; i += 3) {
    const x = norms[i], y = norms[i + 1], z = norms[i + 2];
    const x1 = ct * x + st * z, z1 = -st * x + ct * z;
    rnorm[i] = x1;
    rnorm[i + 1] = cp * y - sp * z1;
    rnorm[i + 2] = sp * y + cp * z1;
  }
  let m = 0;
  for (let t = 0; t < n; t++) {
    if (rnorm[t * 3 + 2] <= 0) continue;      // backface cull (+z toward viewer)
    const a = t * 9;
    depth[m] = rot[a + 2] + rot[a + 5] + rot[a + 8];  // larger = farther
    idx[m++] = t;
  }
  const order = Array.prototype.slice.call(idx.subarray(0, m));
  order.sort((p, q) => depth[q] - depth[p]);  // far first
  for (let k = 0; k < order.length; k++) {
    const t = order[k];
    const a = t * 9;
    const nx = rnorm[t * 3], ny = rnorm[t * 3 + 1], nz = rnorm[t * 3 + 2];
    let sh = 0.5 + 0.5 * Math.max(0, nx * L[0] + ny * L[1] + nz * L[2]);
    const r = Math.round(148 * sh + 20), g = Math.round(196 * sh + 25),
          b = Math.round(232 * sh + 30);
    ctx.fillStyle = "rgb(" + r + "," + g + "," + b + ")";
    ctx.beginPath();
    ctx.moveTo(rot[a] * scale + w / 2, h / 2 - rot[a + 1] * scale);
    ctx.lineTo(rot[a + 3] * scale + w / 2, h / 2 - rot[a + 4] * scale);
    ctx.lineTo(rot[a + 6] * scale + w / 2, h / 2 - rot[a + 7] * scale);
    ctx.closePath();
    ctx.fill();
    ctx.lineWidth = 0.6;
    ctx.strokeStyle = "rgba(10,15,22,0.35)";
    ctx.stroke();
  }
  // group labels (world coords -> same permutation+rotation -> screen)
  if (LABELS.length) {
    ctx.font = (12 * devicePixelRatio) + "px monospace";
    ctx.textAlign = "center";
    for (const item of LABELS) {
      const txt = item[0], p = item[1];
      // permuted coords (x,y,z)->(y,z,x), made relative to the permuted center
      const x = p[1] - cx, y = p[2] - cy, z = p[0] - cz;
      const x1 = ct * x + st * z, z1 = -st * x + ct * z;
      const sy = cp * y - sp * z1, sz = sp * y + cp * z1;
      const sx = x1 * scale + w / 2, syp = h / 2 - sy * scale;
      const lead = (item[2] || 26) * devicePixelRatio;
      ctx.strokeStyle = "rgba(127,168,201,0.55)";
      ctx.lineWidth = devicePixelRatio;
      ctx.beginPath();
      ctx.moveTo(sx, syp);
      ctx.lineTo(sx, syp - lead);
      ctx.stroke();
      ctx.fillStyle = "#9fc3e6";
      ctx.fillText(txt, sx, syp - lead - 6 * devicePixelRatio);
    }
  }
}

function resize() {
  canvas.width = innerWidth * devicePixelRatio;
  canvas.height = innerHeight * devicePixelRatio;
  draw();
}
addEventListener("resize", resize);

let dragging = false, px = 0, py = 0;
canvas.addEventListener("pointerdown", e => { dragging = true; px = e.clientX; py = e.clientY; });
addEventListener("pointerup", () => dragging = false);
addEventListener("pointermove", e => {
  if (!dragging) return;
  theta += (e.clientX - px) * 0.008;
  phi = Math.max(-1.45, Math.min(1.45, phi + (e.clientY - py) * 0.008));
  px = e.clientX; py = e.clientY;
  draw();
});
canvas.addEventListener("wheel", e => {
  e.preventDefault();
  zoom = Math.max(0.2, Math.min(8, zoom * Math.exp(-e.deltaY * 0.0012)));
  draw();
}, { passive: false });

resize();
</script>
</body></html>
"""


def render_page(stl_bytes: bytes, title: str, legend: str = "",
                labels: list | None = None) -> str:
    """Self-contained preview HTML with the STL embedded as base64.
    labels: [(text, [world_x, world_y, world_z]), ...] drawn on the canvas."""
    import json
    b64 = base64.b64encode(stl_bytes).decode("ascii")
    return (_PAGE.replace("__TITLE__", title.replace("&", "&amp;")
                          .replace("<", "&lt;"))
            .replace("__LEGEND__", legend.replace("&", "&amp;")
                     .replace("<", "&lt;"))
            .replace("__LABELS__", json.dumps(labels or []))
            .replace("__B64__", b64))
