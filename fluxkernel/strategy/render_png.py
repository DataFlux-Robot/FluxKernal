"""Offline four-view PNG rendering of the honest DAG geometry (P7/V2).

`fk render --png` is the PERCEPTION INPUT CHANNEL of the perception-action
loop: machine-readable images a VLM (fk review) or a human can judge.
Same mesh pipeline as the preview page (strategy/scene.py), same palette;
matplotlib Agg backend, no display, no network.

Views are defined over the FluxKernel world frame (x = span, y = fore-aft,
z = up):  iso  — three-quarter from front-right-top
          front — looking from the nose (+y toward -y)
          top   — looking down
          right — looking from the +x tip
"""
from __future__ import annotations

VIEWS = {"iso": (30, -60), "front": (0, -90), "top": (90, -90), "right": (0, 0)}
_LIGHT = (0.42, 0.66, 0.62)


def _shade(base, nx, ny, nz):
    ln = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
    d = max(0.0, (nx * _LIGHT[0] + ny * _LIGHT[1] + nz * _LIGHT[2]) / ln)
    sh = 0.35 + 0.65 * d
    return (min(1, base[0] / 255 * sh), min(1, base[1] / 255 * sh),
            min(1, base[2] / 255 * sh))


def render_views(tri_groups, out_prefix, views=None, width=1280, height=880,
                 title="", theme="dark"):
    """tri_groups: [((r,g,b), [(nx,ny,nz, x1..z3), ...]), ...].
    Writes <prefix>_<view>.png per view; returns the path list."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    views = views or list(VIEWS)
    paths = []
    lo = [1e30] * 3
    hi = [-1e30] * 3
    for _, tris in tri_groups:
        for t in tris:
            xs, ys, zs = t[3:6], t[6:9], t[9:12]
            lo[0] = min(lo[0], xs[0], xs[1], xs[2])
            hi[0] = max(hi[0], xs[0], xs[1], xs[2])
            lo[1] = min(lo[1], ys[0], ys[1], ys[2])
            hi[1] = max(hi[1], ys[0], ys[1], ys[2])
            lo[2] = min(lo[2], zs[0], zs[1], zs[2])
            hi[2] = max(hi[2], zs[0], zs[1], zs[2])
    if lo[0] > hi[0]:
        return []

    from pathlib import Path
    prefix = Path(out_prefix)
    if prefix.suffix == ".png":        # --png truck_iso.png -> truck_iso_*.png
        prefix = prefix.with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for view in views:
        elev, azim = VIEWS[view]
        bg = "#f4f2ec" if theme == "light" else "#14171c"
        fg = "#3a3f46" if theme == "light" else "#7fa8c9"
        fig = plt.figure(figsize=(width / 100, height / 100), dpi=100)
        ax = fig.add_subplot(111, projection="3d")
        ax.set_facecolor(bg)
        fig.patch.set_facecolor(bg)
        for base, tris in tri_groups:
            polys, cols = [], []
            for t in tris:
                polys.append([list(t[3:6]), list(t[6:9]), list(t[9:12])])
                cols.append(_shade(base, t[0], t[1], t[2]))
            pc = Poly3DCollection(
                polys, facecolors=cols,
                edgecolors=("#26384a" if theme == "light" else "#c8d8e8"),
                linewidths=0.25 if theme == "light" else 0.15)
            ax.add_collection3d(pc)
        ax.set_xlim(lo[0], hi[0])
        ax.set_ylim(lo[1], hi[1])
        ax.set_zlim(lo[2], hi[2])
        ax.set_box_aspect((hi[0] - lo[0] or 1, hi[1] - lo[1] or 1,
                           hi[2] - lo[2] or 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        import math
        span = max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) or 1.0
        unit = 10 ** math.floor(math.log10(span / 6))
        ax.set_title(f"{title} · {view} view · scale grid {unit:g} mm"
                     if title else f"{view} view · scale grid {unit:g} mm",
                     color=fg, fontsize=10)
        p = prefix.parent / f"{prefix.name}_{view}.png"
        fig.savefig(p, facecolor=fig.get_facecolor())
        plt.close(fig)
        paths.append(str(p))
    return paths
