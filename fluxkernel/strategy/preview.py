"""Self-contained STL preview page (file://-safe, zero dependencies).

Why not three.js + CDN: module scripts and XHR/fetch of local files are
blocked by browsers on file:// origins, and the CDN needs network. Instead
the STL is embedded as base64 and rendered by a small canvas software
renderer (painter's algorithm + backface culling, drag to rotate, wheel to
zoom). Coarse-mesh STLs (a few thousand triangles) run at full interactivity.

V2 (P7): Lambert + ambient lighting, per-part role palette (shape index
rides the STL uint16 attribute field), ground grid, world-axis triad and
a scale bar — enough shading for a human or a VLM to judge "does this
look like the thing the DAG claims".
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
const SHAPE_COLORS = __SHAPE_COLORS__;

function abFromB64(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

// ---- parse STL (binary, or ASCII fallback) ----
const buf = abFromB64(B64);
const dv = new DataView(buf);
let verts, norms, attr, n;
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
  attr = new Uint16Array(n);
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
  attr = new Uint16Array(n);
  let o = 84;
  for (let i = 0; i < n; i++) {
    norms[i * 3] = dv.getFloat32(o, true);
    norms[i * 3 + 1] = dv.getFloat32(o + 4, true);
    norms[i * 3 + 2] = dv.getFloat32(o + 8, true);
    for (let v = 0; v < 9; v++) verts[i * 9 + v] = dv.getFloat32(o + 12 + v * 4, true);
    attr[i] = dv.getUint16(o + 48, true);          // shape index (V2)
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
const span2 = Math.max(mx[0]-mn[0], mx[1]-mn[1]) || 1;

// ---- camera ----
let theta = 0.55, phi = 0.3, zoom = 1;
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const rot = new Float32Array(verts.length);
const rnorm = new Float32Array(norms.length);
const idx = new Int32Array(n);
const depth = new Float32Array(n);
const L = [0.42, 0.66, 0.62];
const LN = Math.hypot(L[0], L[1], L[2]);

function proj(x, y, z, ct, st, cp, sp, scale, w, h) {
  // world-permuted point (relative to center) -> screen
  const x1 = ct * x + st * z, z1 = -st * x + ct * z;
  const sy = cp * y - sp * z1, sz = sp * y + cp * z1;
  return [x1 * scale + w / 2, h / 2 - sy * scale, sz];
}

function niceStep(target) {
  const p = Math.pow(10, Math.floor(Math.log10(target)));
  for (const m of [1, 2, 5, 10]) if (m * p >= target) return m * p;
  return 10 * p;
}

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

  // ---- ground grid on the world floor (z = world min) ----
  // permuted coords: world (x,y,z) -> (y,z,x); floor z=const -> screen y=const
  const floorY = mn[1] - span2 * 0.04;
  const gstep = niceStep(span2 / 10);
  const gx0 = mn[0] - gstep, gx1 = mx[0] + gstep;
  const gz0 = mn[2] - gstep, gz1 = mx[2] + gstep;
  ctx.strokeStyle = "rgba(94,124,152,0.22)";
  ctx.lineWidth = devicePixelRatio;
  ctx.beginPath();
  for (let gx = Math.floor(gx0 / gstep) * gstep; gx <= gx1; gx += gstep) {
    const a = proj(gx - cx, floorY - cy, gz0 - cz, ct, st, cp, sp, scale, w, h);
    const b = proj(gx - cx, floorY - cy, gz1 - cz, ct, st, cp, sp, scale, w, h);
    ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
  }
  for (let gz = Math.floor(gz0 / gstep) * gstep; gz <= gz1; gz += gstep) {
    const a = proj(gx0 - cx, floorY - cy, gz - cz, ct, st, cp, sp, scale, w, h);
    const b = proj(gx1 - cx, floorY - cy, gz - cz, ct, st, cp, sp, scale, w, h);
    ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
  }
  ctx.stroke();

  // ---- triangles: painter's algorithm, Lambert + ambient per part ----
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
    const sh = 0.35 + 0.65 * Math.max(0,
        (nx * L[0] + ny * L[1] + nz * L[2]) / LN);
    const base = SHAPE_COLORS[attr[t]] || SHAPE_COLORS[SHAPE_COLORS.length - 1] || [148, 196, 232];
    ctx.fillStyle = "rgb(" + Math.round(base[0] * sh) + "," +
        Math.round(base[1] * sh) + "," + Math.round(base[2] * sh) + ")";
    ctx.beginPath();
    ctx.moveTo(rot[a] * scale + w / 2, h / 2 - rot[a + 1] * scale);
    ctx.lineTo(rot[a + 3] * scale + w / 2, h / 2 - rot[a + 4] * scale);
    ctx.lineTo(rot[a + 6] * scale + w / 2, h / 2 - rot[a + 7] * scale);
    ctx.closePath();
    ctx.fill();
    ctx.lineWidth = 0.6;
    ctx.strokeStyle = "rgba(10,15,22,0.3)";
    ctx.stroke();
  }

  // ---- world-axis triad at the origin ----
  const ax = span2 * 0.11;
  const axes = [["x", [ax, 0, 0], "#d98a7a"], ["y", [0, ax, 0], "#9fd98a"],
                ["z", [0, 0, ax], "#8aa8d9"]];
  ctx.font = (11 * devicePixelRatio) + "px monospace";
  for (const [nm2, dir, col] of axes) {
    const o2 = proj(-cx, -cy, -cz, ct, st, cp, sp, scale, w, h);
    const p2 = proj(dir[1] - cx, dir[2] - cy, dir[0] - cz, ct, st, cp, sp, scale, w, h);
    ctx.strokeStyle = col;
    ctx.lineWidth = 1.6 * devicePixelRatio;
    ctx.beginPath();
    ctx.moveTo(o2[0], o2[1]);
    ctx.lineTo(p2[0], p2[1]);
    ctx.stroke();
    ctx.fillStyle = col;
    ctx.fillText(nm2, p2[0] + 4, p2[1] + 4);
  }

  // ---- scale bar (bottom-left) ----
  const targetPx = w * 0.16;
  let unit = niceStep(targetPx / scale);
  let pxLen = unit * scale;
  const bx = 24 * devicePixelRatio, by = h - 30 * devicePixelRatio;
  ctx.strokeStyle = "#7fa8c9";
  ctx.lineWidth = devicePixelRatio;
  ctx.beginPath();
  ctx.moveTo(bx, by); ctx.lineTo(bx + pxLen, by);
  ctx.moveTo(bx, by - 5); ctx.lineTo(bx, by + 5);
  ctx.moveTo(bx + pxLen, by - 5); ctx.lineTo(bx + pxLen, by + 5);
  ctx.stroke();
  ctx.fillStyle = "#7fa8c9";
  ctx.font = (11 * devicePixelRatio) + "px monospace";
  ctx.textAlign = "left";
  ctx.fillText((unit >= 1000 ? unit / 1000 + " m" : unit + " mm"), bx, by - 9);
  ctx.textAlign = "center";

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
                labels: list | None = None,
                shape_colors: list | None = None) -> str:
    """Self-contained preview HTML with the STL embedded as base64.
    labels: [(text, [world_x, world_y, world_z]), ...] drawn on the canvas.
    shape_colors: [[r, g, b], ...] indexed by the STL uint16 attribute."""
    import json
    b64 = base64.b64encode(stl_bytes).decode("ascii")
    return (_PAGE.replace("__TITLE__", title.replace("&", "&amp;")
                          .replace("<", "&lt;"))
            .replace("__LEGEND__", legend.replace("&", "&amp;")
                     .replace("<", "&lt;"))
            .replace("__LABELS__", json.dumps(labels or []))
            .replace("__SHAPE_COLORS__",
                     json.dumps(shape_colors or [[148, 196, 232]]))
            .replace("__B64__", b64))
