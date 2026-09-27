"""Constrained constructive geometry; no model-generated code is executed."""
from __future__ import annotations
import math
from pathlib import Path
from .models import Part


def _box(x,y,z,cx=0,cy=0,cz=0):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    return BRepPrimAPI_MakeBox(gp_Pnt(cx-x/2,cy-y/2,cz-z/2),x,y,z).Shape()


def _cut(a,b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    op=BRepAlgoAPI_Cut(a,b);op.Build()
    if not op.IsDone(): raise ValueError('Boolean cut failed')
    return op.Shape()


def _loft(x,y,z,wall=0,car=False,smooth=False,section=None):
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt
    # Polygonal, ruled loft is robust and explicitly a concept surface.
    stations=[(-.5,.30,.40),(-.34,.90,.83),(-.12,1,1),(.22,.95,.94),(.5,.40,.48)]
    if car: stations=[(-.5,.8,.45),(-.30,1,.6),(-.13,.85,1),(.23,.85,1),(.5,.88,.6)]
    if smooth and not car:
        stations=[(-.5,.04,.04),(-.36,.65,.7),(-.24,1,1),(.28,1,1),(.43,.6,.65),(.5,.035,.035)]
    if section=='fuselage_section':stations=[(-.5,1,1),(.5,1,1)]
    elif section=='fuselage_nose':stations=[(-.5,1,1),(.05,1,1),(.35,.7,.7),(.5,.04,.04)]
    elif section=='fuselage_tail':stations=[(-.5,.04,.04),(-.25,.5,.5),(.25,.9,.9),(.5,1,1)]
    mk=BRepOffsetAPI_ThruSections(True,not smooth,1e-6)
    for fx,fy,fz in stations:
        if smooth:
            from OCP.gp import gp_Elips,gp_Ax2,gp_Dir
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeWire
            ry,rz=y*fy/2-wall,z*fz/2-wall
            axis=gp_Ax2(gp_Pnt(fx*x,0,0),gp_Dir(1,0,0),gp_Dir(0,1,0) if ry>=rz else gp_Dir(0,0,1))
            ellipse=gp_Elips(axis,max(ry,rz),min(ry,rz))
            mk.AddWire(BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(ellipse).Edge()).Wire())
            continue
        poly=BRepBuilderAPI_MakePolygon()
        for i in range(8):
            t=2*math.pi*i/8
            poly.Add(gp_Pnt(fx*x, math.cos(t)*(y*fy/2-wall),math.sin(t)*(z*fz/2-wall)))
        poly.Close();mk.AddWire(poly.Wire())
    mk.Build()
    if not mk.IsDone(): raise ValueError('Loft failed')
    return mk.Shape()


def build(part: Part):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform,BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.gp import gp_Pnt,gp_Trsf,gp_Vec,gp_Ax1,gp_Dir
    x,y,z=part.size;w=part.wall
    if part.shape=='box': shape=_box(x,y,z)
    elif part.shape=='shell':
        shape=_cut(_box(x,y,z),_box(x-2*w,y-2*w,z,cx=0,cy=0,cz=w))
    elif part.shape=='frame':
        shape=_cut(_box(x,y,z),_box(x-2*w,y-2*w,z+2))
    elif part.shape in ('cylinder','tube'):
        shape=BRepPrimAPI_MakeCylinder(x/2,z).Shape()
        if part.shape=='tube': shape=_cut(shape,BRepPrimAPI_MakeCylinder(x/2-w,z).Shape())
        tr=gp_Trsf();tr.SetTranslation(gp_Vec(0,0,-z/2));shape=BRepBuilderAPI_Transform(shape,tr,True).Shape()
    elif part.shape=='wing':
        poly=BRepBuilderAPI_MakePolygon()
        for xx,yy in [(-x/2,-y/2),(x/2,-y/2),(x*.2,y/2),(-x*.2,y/2)]:
            poly.Add(gp_Pnt(xx,yy,-z/2))
        poly.Close();face=BRepBuilderAPI_MakeFace(poly.Wire()).Face()
        shape=BRepPrimAPI_MakePrism(face,gp_Vec(0,0,z)).Shape()
    else:
        shape=_loft(x,y,z,car=part.shape.endswith('car_body'),smooth=part.shape.startswith(('smooth_','fuselage_')),section=part.shape)
        # Scaled inner loft leaves finite end walls; true volume checked below.
        if min(x,y,z)>12*w:
            inner=_loft(x-4*w,y-4*w,z-4*w,car=part.shape.endswith('car_body'),smooth=part.shape.startswith(('smooth_','fuselage_')),section=part.shape)
            shape=_cut(shape,inner)
    if not BRepCheck_Analyzer(shape).IsValid(): raise ValueError(f'{part.id}: invalid B-rep')
    for axis,angle in zip([(1,0,0),(0,1,0),(0,0,1)],part.rotation):
        if angle:
            tr=gp_Trsf();tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(*axis)),math.radians(angle))
            shape=BRepBuilderAPI_Transform(shape,tr,True).Shape()
    tr=gp_Trsf();tr.SetTranslation(gp_Vec(*part.position));shape=BRepBuilderAPI_Transform(shape,tr,True).Shape()
    return shape


def artifacts(part: Part, directory: Path, store):
    from fluxkernel.solvers.feature3d import _write_blobs, _props
    from fluxkernel.strategy.scene import mesh_shape
    from types import SimpleNamespace
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID
    shape=build(part);props=_props(shape)
    if props['volume_mm3']<=0: raise ValueError(f'{part.id}: non-positive solid volume')
    ex=TopExp_Explorer(shape,TopAbs_SOLID);solids=0
    while ex.More(): solids+=1;ex.Next()
    if solids!=1: raise ValueError(f'{part.id}: expected one solid, got {solids}')
    blobs=_write_blobs(shape,SimpleNamespace(store=store),**({'linear':max(max(part.size)/1200,.1),'angular':.22} if part.shape.startswith(('smooth_','fuselage_')) else {}))
    if set(blobs)!= {'step','stl'}: raise ValueError('STEP/STL export did not complete')
    for ext,digest in blobs.items(): (directory/f'{part.id}.{ext}').write_bytes(store.get_blob(digest))
    triangles=mesh_shape(shape,linear=max(max(part.size)/2000,0.1),angular=0.3)
    vertices=[]
    for t in triangles: vertices.extend(round(v,4) for v in t[3:])
    # Constructive checks are specific to supported recipes, not a bbox wall claim.
    analytic_wall=part.wall if part.shape in ('shell','tube','frame') else None
    check={'valid_brep':True,'solid_count':solids,'volume_mm3':round(props['volume_mm3'],3),
        'bbox_mm':props['bbox'],'analytic_wall_mm':analytic_wall,
        'wall_evidence':'constructive-uniform-wall' if analytic_wall else 'requires-local-thickness-validation',
        'print_process':'material-specific additive process, unlimited envelope assumed',
        'physical_validation':'not-performed','geometry_kind':'catalog-envelope' if part.route=='catalog' else 'concept-design'}
    return {'id':part.id,'name':part.name,'vertices':vertices,'color':part.color,
            'position':part.position,'group':part.group,'route':part.route},check,blobs
