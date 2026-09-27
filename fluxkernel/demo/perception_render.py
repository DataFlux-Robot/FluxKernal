"""Deterministic orthographic CAD rendering, using real tessellated B-reps.

A depth buffer handles occlusion. Views use Studio's X-longitudinal, Y-lateral,
Z-up convention. These are diagnostic views, not an estimated reference camera.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from .geometry import build
from fluxkernel.strategy.scene import mesh_shape

VIEWS = {'iso': (1.3,-1.7,1.1), 'side': (0,-1,0), 'top': (0,0,1), 'front': (1,0,0)}


def mesh_design(design):
    meshes=[]
    for part in design.parts:
        shape=build(part)
        triangles=mesh_shape(shape,linear=max(max(part.size)/1200,.1),angular=.22)
        meshes.append({'id':part.id,'color':part.color,
                       'triangles':np.asarray([t[3:] for t in triangles],dtype=float).reshape(-1,3,3)})
    return meshes


def render_view(meshes, view, *, bounds=None, pixels=448):
    eye=np.asarray(VIEWS[view],dtype=float);eye/=np.linalg.norm(eye)
    up=np.array([0,1,0] if view=='top' else [0,0,1],dtype=float)
    right=np.cross(up,eye);right/=np.linalg.norm(right);up=np.cross(eye,right)
    transform=np.stack([right,up,eye],axis=1)
    points=np.concatenate([m['triangles'].reshape(-1,3) for m in meshes])
    lo,hi=(points.min(axis=0),points.max(axis=0)) if bounds is None else (np.array(bounds[0]),np.array(bounds[1]))
    center=(lo+hi)/2
    # Freeze scale/center across the loop; changing the design cannot zoom away errors.
    span=max(float(np.linalg.norm(hi-lo)),1)
    scale=(pixels-36)/span
    rgb=np.full((pixels,pixels,3),244,dtype=np.uint8)
    depth=np.full((pixels,pixels),-np.inf)
    mask=np.zeros((pixels,pixels),dtype=np.uint8)
    for mesh in meshes:
        color=np.array([int(mesh['color'][i:i+2],16) for i in (1,3,5)])
        for world in mesh['triangles']:
            t=(world-center)@transform
            xy=t[:,:2]*[scale,-scale]+pixels/2
            low=np.maximum(np.floor(xy.min(axis=0)).astype(int),0)
            high=np.minimum(np.ceil(xy.max(axis=0)).astype(int),pixels-1)
            if np.any(high<low):continue
            x,y=np.meshgrid(np.arange(low[0],high[0]+1)+.5,np.arange(low[1],high[1]+1)+.5)
            a,b,c=xy
            denom=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denom)<1e-10:continue
            u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denom
            v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denom
            w=1-u-v;z=u*t[0,2]+v*t[1,2]+w*t[2,2]
            sl=(slice(low[1],high[1]+1),slice(low[0],high[0]+1))
            hit=(u>=-1e-8)&(v>=-1e-8)&(w>=-1e-8)&(z>depth[sl])
            normal=np.cross(world[1]-world[0],world[2]-world[0]);normal/=max(np.linalg.norm(normal),1e-20)
            shade=.48+.52*abs(float(normal@np.array([.35,-.45,.82])))
            rgb[sl][hit]=np.clip(color*shade,0,255).astype(np.uint8)
            depth[sl][hit]=z[hit];mask[sl][hit]=255
    image=Image.fromarray(rgb)
    ImageDraw.Draw(image).text((10,10),f'{view.upper()} | X length / Y width / Z up',fill='#202d38')
    return image,Image.fromarray(mask)


def render_design(design, directory, bounds=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    meshes=mesh_design(design)
    points=np.concatenate([m['triangles'].reshape(-1,3) for m in meshes])
    actual=[points.min(axis=0).tolist(),points.max(axis=0).tolist()]
    bounds=bounds or actual
    board=Image.new('RGB',(896,896),'#f4f4f4');files=[];coverage={};clipped={}
    for index,view in enumerate(VIEWS):
        image,mask=render_view(meshes,view,bounds=bounds)
        eye=np.array(VIEWS[view],dtype=float);eye/=np.linalg.norm(eye)
        up=np.array([0,1,0] if view=='top' else [0,0,1],dtype=float)
        right=np.cross(up,eye);right/=np.linalg.norm(right);up=np.cross(eye,right)
        center=(np.array(bounds[0])+np.array(bounds[1]))/2
        span=max(float(np.linalg.norm(np.array(bounds[1])-np.array(bounds[0]))),1)
        projected=(points-center)@np.stack([right,up],axis=1)*(448-36)/span+224
        clipped[view]=round(float(np.any((projected<0)|(projected>447),axis=1).mean()),6)
        image.save(directory/f'{view}.png');mask.save(directory/f'{view}-mask.png')
        board.paste(image,((index%2)*448,(index//2)*448))
        files.append(f'{view}.png');coverage[view]=round(float((np.asarray(mask)>0).mean()),6)
    board.save(directory/'views.png')
    report={'schema':'fk-perception-render-v1','views':files,'board':'views.png',
            'camera':'fixed orthographic diagnostic views; not reference-camera alignment',
            'bounds_mm':bounds,'actual_bounds_mm':actual,'frame_coverage':coverage,'clipped_vertex_fraction':clipped,
            'triangle_count':sum(len(m['triangles']) for m in meshes)}
    (directory/'render.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
