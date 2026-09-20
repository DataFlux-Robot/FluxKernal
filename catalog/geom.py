"""V3 catalog representative geometry.

Each generator builds a REPRESENTATIVE envelope of a catalog item class
(flange motor, linear rail, leadscrew, control board) — dimensions from
the entry's geometry params.  These are honest envelopes for layout and
interference, explicitly NOT manufacturer models; every grounded node
carries tier "catalog-representative" and, per the spec red line, the
mass stays the CATALOG mass — the envelope never feeds strength or
performance calculations.
"""
from __future__ import annotations


def _cyl(r, h, axis=(0, 0, 1), at=(0, 0, 0)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    return BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(*at), gp_Dir(*axis)), r, h).Shape()


def _box(dx, dy, dz, at=(0, 0, 0)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    return BRepPrimAPI_MakeBox(gp_Pnt(*at),
                               gp_Pnt(at[0] + dx, at[1] + dy, at[2] + dz)).Shape()


def _fuse(a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    mk = BRepAlgoAPI_Fuse(a, b)
    mk.Build()
    return mk.Shape()


def motor(p):
    """Flange motor: body cylinder + front shaft + rear encoder cap."""
    flange = float(p.get("flange", 80))
    length = float(p.get("length", 115))
    shaft = float(p.get("shaft", 12))
    body = _cyl(flange / 2, length)
    shaft_s = _cyl(shaft / 2, length * 0.35, at=(0, 0, length))
    enc = _cyl(flange * 0.32, length * 0.12, at=(0, 0, -length * 0.12))
    return _fuse(_fuse(body, shaft_s), enc)


def rail(p):
    """Linear guide rail: prismatic strip with bolt bosses."""
    length = float(p.get("length", 1800))
    w = float(p.get("width", 23))
    h = float(p.get("height", 20))
    strip = _box(length, w, h)
    bosses = _box(length, w * 0.5, h * 0.6, at=(0, w * 0.25, h))
    return _fuse(strip, bosses)


def screw(p):
    """Lead screw: cylinder + nut block."""
    dia = float(p.get("dia", 8))
    length = float(p.get("length", 1500))
    body = _cyl(dia / 2, length, axis=(1, 0, 0))
    nut = _box(38, 38, 20, at=(length * 0.5 - 19, -19, dia / 2 - 6))
    return _fuse(body, nut)


def board(p):
    """Control board: PCB plate + connector box + heatsink block."""
    w = float(p.get("width", 120))
    l = float(p.get("length", 160))
    pcb = _box(l, w, 2)
    conn = _box(30, w * 0.8, 12, at=(0, w * 0.1, 2))
    hs = _box(40, 40, 22, at=(l * 0.45, w * 0.25, 2))
    return _fuse(_fuse(pcb, conn), hs)
