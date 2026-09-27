"""Finite semantic geometry controls inspired by OpenVSP; no OpenVSP dependency."""
from __future__ import annotations
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Schema(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class WingParameters(Schema):
    kind: Literal['wing']='wing'
    span: float=Field(ge=10,le=100000)
    root_chord: float=Field(ge=1,le=100000)
    tip_chord: float=Field(ge=1,le=100000)
    sweep_deg: float=Field(ge=-70,le=70)
    dihedral_deg: float=Field(ge=-45,le=45)
    twist_deg: float=Field(ge=-30,le=30)
    thickness_ratio: float=Field(ge=.02,le=.3)

class Section(Schema):
    u: float=Field(ge=0,le=1)
    width: float=Field(ge=.4,le=100000)
    height: float=Field(ge=.4,le=100000)
    offset_y: float=Field(ge=-100000,le=100000)
    offset_z: float=Field(ge=-100000,le=100000)

class BodyParameters(Schema):
    kind: Literal['body']='body'
    length: float=Field(ge=1,le=100000)
    sections: list[Section]=Field(min_length=3,max_length=12)

    @model_validator(mode='after')
    def ordered(self):
        if self.sections[0].u!=0 or self.sections[-1].u!=1 or any(a.u>=b.u for a,b in zip(self.sections,self.sections[1:])):
            raise ValueError('Body sections must be strictly ordered, starting at u=0 and ending at u=1')
        return self


def wing_sections(p):
    """Closed symmetric four-digit thickness law; root at origin, outboard +Y.

    X points forward: leading edge x=0; trailing edge x=-chord. Positive sweep
    moves tip aft. Parameters describe a conceptual solid, not aerodynamic evidence.
    """
    sections=[]
    us=[(1-math.cos(math.pi*i/24))/2 for i in range(25)]
    for tip in (False,True):
        chord=p.tip_chord if tip else p.root_chord
        y=p.span if tip else 0;dx=-y*math.tan(math.radians(p.sweep_deg));dz=y*math.tan(math.radians(p.dihedral_deg))
        angle=math.radians(p.twist_deg if tip else 0);points=[]
        for u,sign in [(u,1) for u in us]+[(u,-1) for u in us[-2:0:-1]]:
            z=sign*5*p.thickness_ratio*chord*(.2969*math.sqrt(u)-.126*u-.3516*u*u+.2843*u**3-.1036*u**4)
            x=-u*chord
            points.append((dx+x*math.cos(angle)+z*math.sin(angle),y,dz-x*math.sin(angle)+z*math.cos(angle)))
        sections.append(points)
    return sections


def envelope(p):
    if isinstance(p,WingParameters):
        points=[v for section in wing_sections(p) for v in section]
        return [max(v[i] for v in points)-min(v[i] for v in points) for i in range(3)]
    return [p.length,
        max(s.offset_y+s.width/2 for s in p.sections)-min(s.offset_y-s.width/2 for s in p.sections),
        max(s.offset_z+s.height/2 for s in p.sections)-min(s.offset_z-s.height/2 for s in p.sections)]


def build_parametric(p):
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt,gp_Dir,gp_Ax2,gp_Elips
    # Ruled transitions keep section extents explicit and avoid spline overshoot.
    loft=BRepOffsetAPI_ThruSections(True,True,1e-6)
    if isinstance(p,WingParameters):
        for points in wing_sections(p):
            poly=BRepBuilderAPI_MakePolygon()
            for xyz in points:poly.Add(gp_Pnt(*xyz))
            poly.Close();loft.AddWire(poly.Wire())
    else:
        for s in p.sections:
            y,z=s.width/2,s.height/2
            axis=gp_Ax2(gp_Pnt((s.u-.5)*p.length,s.offset_y,s.offset_z),gp_Dir(1,0,0),gp_Dir(0,1,0) if y>=z else gp_Dir(0,0,1))
            wire=BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(gp_Elips(axis,max(y,z),min(y,z))).Edge()).Wire()
            loft.AddWire(wire)
    loft.Build()
    if not loft.IsDone():raise ValueError('Parametric loft failed')
    return loft.Shape()
