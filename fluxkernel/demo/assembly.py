"""Model-declared body partitions, attachment anchors and axis constraints.

No aircraft dimensions or part IDs live here. All design choices come from the
model. Constraints establish declared relationships, not recovered physical truth.
"""
from __future__ import annotations

import math
import warnings
from typing import Literal
import numpy as np
from pydantic import Field
from scipy.spatial.transform import Rotation
from .parametric import Schema, BodyParameters, WingParameters, Section, envelope


class BodyMember(Schema):
    part: str
    start: float = Field(ge=0, lt=1)
    end: float = Field(gt=0, le=1)


class BodyGroup(Schema):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,47}$')
    profile: BodyParameters
    position: list[float] = Field(min_length=3, max_length=3)
    rotation: list[float] = Field(min_length=3, max_length=3)
    members: list[BodyMember] = Field(min_length=2, max_length=16)


class Anchor(Schema):
    kind: Literal['origin', 'wing', 'body', 'box', 'cylinder']
    u: float = Field(default=0.5, ge=0, le=1)
    v: float = Field(default=0.5, ge=0, le=1)
    w: float = Field(default=0.5, ge=0, le=1)
    angle_deg: float = Field(default=0, ge=-360, le=360)


class Attachment(Schema):
    parent: str
    child: str
    parent_anchor: Anchor
    child_anchor: Anchor
    relation: Literal['contact', 'placement'] = 'contact'


class Alignment(Schema):
    part: str
    local_axis: Literal['x', 'y', 'z']
    world_axis: Literal['x', 'y', 'z', '-x', '-y', '-z']
    roll_deg: float = Field(default=0, ge=-180, le=180)


class AssemblyRules(Schema):
    bodies: list[BodyGroup] = Field(default_factory=list, max_length=8)
    attachments: list[Attachment] = Field(default_factory=list, max_length=48)
    alignments: list[Alignment] = Field(default_factory=list, max_length=32)


def matrix(part):
    r = Rotation.from_euler('xyz', part.rotation, degrees=True).as_matrix()
    if part.reflection:
        s = np.eye(3); s['xyz'.index(part.reflection), 'xyz'.index(part.reflection)] = -1
        r = r @ s
    return r


def section_at(profile, u):
    for a, b in zip(profile.sections, profile.sections[1:]):
        if a.u <= u <= b.u:
            t = (u-a.u)/(b.u-a.u)
            return Section(u=u, **{k: getattr(a, k)*(1-t)+getattr(b, k)*t
                for k in ('width', 'height', 'offset_y', 'offset_z')})
    raise ValueError('Section station outside profile')


def anchor_local(part, anchor):
    u, v, w = anchor.u, anchor.v, anchor.w
    if anchor.kind == 'origin': return np.zeros(3)
    if anchor.kind == 'wing' and isinstance(part.parametric, WingParameters):
        p = part.parametric
        # Ruled interpolation between corresponding root/tip chord points.
        tip_x, tip_z = -v*p.tip_chord*math.cos(math.radians(p.twist_deg)), v*p.tip_chord*math.sin(math.radians(p.twist_deg))
        return np.array([(1-u)*(-v*p.root_chord)+u*(tip_x-p.span*math.tan(math.radians(p.sweep_deg))),
            u*p.span, u*(tip_z+p.span*math.tan(math.radians(p.dihedral_deg)))])
    if anchor.kind == 'body' and isinstance(part.parametric, BodyParameters):
        s = section_at(part.parametric, u); a = math.radians(anchor.angle_deg)
        return np.array([(u-.5)*part.parametric.length, s.offset_y+v*s.width/2*math.cos(a), s.offset_z+v*s.height/2*math.sin(a)])
    if anchor.kind == 'box' and part.shape in ('box', 'shell', 'frame'):
        return np.array([(u-.5)*part.size[0], (v-.5)*part.size[1], (w-.5)*part.size[2]])
    if anchor.kind == 'cylinder' and part.shape in ('cylinder', 'tube'):
        a = math.radians(anchor.angle_deg)
        return np.array([v*part.size[0]/2*math.cos(a), v*part.size[1]/2*math.sin(a), (u-.5)*part.size[2]])
    raise ValueError(f'{part.id}: anchor {anchor.kind} incompatible with {part.shape}; initialize semantic parameters first')


def anchor_world(part, anchor):
    return np.array(part.position)+matrix(part) @ anchor_local(part, anchor)


def dependency_order(ids, attachments, pairs):
    edges = {i: set() for i in ids}
    for a in attachments: edges[a.child].add(a.parent)
    for p in pairs: edges[p.target].add(p.source)
    ordered = []
    while edges:
        ready = [i for i, deps in edges.items() if not deps]
        if not ready: raise ValueError('Assembly/mirror dependency cycle; choose an acyclic parent hierarchy')
        ordered.extend(ready)
        for i in ready: del edges[i]
        for deps in edges.values(): deps.difference_update(ready)
    return ordered


def validate_rules(design, rules, pairs=()):
    parts = {p.id: p for p in design.parts}; targets = {p.target for p in pairs}
    body_parts = set(); names = set()
    for body in rules.bodies:
        if body.id in names: raise ValueError('Body group IDs must be unique')
        names.add(body.id)
        previous = 0.0
        for m in body.members:
            if m.part not in parts or m.part in body_parts or m.part in targets:
                raise ValueError('Body members must be unique existing independent occurrences')
            p = parts[m.part]
            if p.route == 'catalog' or p.shape not in ('fuselage', 'smooth_fuselage', 'fuselage_section', 'fuselage_nose', 'fuselage_tail', 'car_body', 'smooth_car_body', 'section_body'):
                raise ValueError('Body groups require fabricated body-family parts; procurement geometry is protected')
            if m.end <= m.start or abs(m.start-previous) > 1e-9:
                raise ValueError('Body members must partition [0,1] in order without gaps or overlap')
            previous = m.end; body_parts.add(m.part)
        if abs(previous-1) > 1e-9: raise ValueError('Body partition must end at 1')
    children = set()
    for a in rules.attachments:
        if a.parent not in parts or a.child not in parts or a.parent == a.child:
            raise ValueError('Attachment requires distinct existing parent and child IDs')
        if a.child in children or a.child in targets or a.child in body_parts:
            raise ValueError('Attachment child must have one driver, not a mirror target or body-group member')
        children.add(a.child)
    aligned = set()
    for a in rules.alignments:
        if a.part not in parts or a.part in aligned or a.part in targets or a.part in body_parts:
            raise ValueError('Axis alignment requires a unique independent part outside body groups')
        aligned.add(a.part)
    dependency_order(parts, rules.attachments, pairs)
    return rules


def compile_bodies(design, rules):
    parts = {p.id: p for p in design.parts}
    for body in rules.bodies:
        r = Rotation.from_euler('xyz', body.rotation, degrees=True)
        for m in body.members:
            stations = [m.start]+[s.u for s in body.profile.sections if m.start < s.u < m.end]+[m.end]
            if len(stations) == 2: stations.insert(1, (m.start+m.end)/2)
            sections = [section_at(body.profile, u).model_copy(update={'u': (u-m.start)/(m.end-m.start)}) for u in stations]
            params = BodyParameters(length=body.profile.length*(m.end-m.start), sections=sections)
            part = parts[m.part]
            part.parametric = params; part.shape = 'section_body'; part.size = envelope(params)
            part.position = (np.array(body.position)+r.apply([((m.start+m.end)/2-.5)*body.profile.length, 0, 0])).tolist()
            part.rotation = body.rotation.copy(); part.reflection = None; part.source = 'selected'


def apply_alignment(part, alignment):
    v = np.zeros(3); v['xyz'.index(alignment.local_axis)] = -1 if part.reflection == alignment.local_axis else 1
    axis = alignment.world_axis; w = np.zeros(3); w['xyz'.index(axis[-1])] = -1 if axis.startswith('-') else 1
    cross = np.cross(v, w); dot = float(np.dot(v, w))
    if dot < -0.999999:
        perpendicular = np.eye(3)[('xyz'.index(alignment.local_axis)+1)%3]
        r = Rotation.from_rotvec(math.pi*perpendicular)
    elif np.linalg.norm(cross) < 1e-12: r = Rotation.identity()
    else: r = Rotation.from_rotvec(cross/np.linalg.norm(cross)*math.acos(dot))
    r = Rotation.from_rotvec(w*math.radians(alignment.roll_deg))*r
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        part.rotation = r.as_euler('xyz', degrees=True).tolist()
    part.source = 'selected'


def assembly_checks(design, pairs=()):
    """Check compiled geometry independently of the model's review and ratings."""
    rules = design.assembly
    if rules is None: return {'schema': 'fk-assembly-checks-v1', 'passed': True, 'issues': [], 'measurements': [], 'declared_contacts': 0, 'scope': 'No assembly rules declared; connectivity unassessed'}
    from .geometry import build
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    parts = {p.id: p for p in design.parts}; shapes = {}; issues = []; measurements = []
    def issue(code, ids, detail): issues.append({'code': code, 'parts': ids, 'detail': detail})
    def gap_between(parent, child):
        for p in (parent, child):
            if p.id not in shapes: shapes[p.id] = build(p)
        distance = BRepExtrema_DistShapeShape(shapes[parent.id], shapes[child.id]); distance.Perform()
        if not distance.IsDone(): raise ValueError('B-rep contact distance failed')
        return distance.Value()
    mirrors = {p.source: p.target for p in pairs}
    for a in rules.attachments:
        parent, child = parts[a.parent], parts[a.child]
        residual = float(np.linalg.norm(anchor_world(parent, a.parent_anchor)-anchor_world(child, a.child_anchor)))
        row = {'kind': a.relation, 'parent': a.parent, 'child': a.child, 'anchor_error_mm': residual}
        if residual > 1e-5: issue('ATTACHMENT_ANCHOR', [a.parent, a.child], f'Anchor error {residual:.6g} mm')
        if a.relation == 'contact':
            gap = gap_between(parent, child); row['surface_gap_mm'] = gap
            if gap > 0.1: issue('ATTACHMENT_GAP', [a.parent, a.child], f'Declared contact has surface gap {gap:.6g} mm (limit 0.1 mm)')
            if a.child in mirrors:
                other_parent = parts[mirrors.get(a.parent, a.parent)]; other_child = parts[mirrors[a.child]]
                other_gap = gap_between(other_parent, other_child)
                measurements.append({'kind': 'mirrored_contact', 'parent': other_parent.id, 'child': other_child.id, 'surface_gap_mm': other_gap})
                if other_gap > .1: issue('MIRRORED_ATTACHMENT_GAP', [other_parent.id, other_child.id], f'Mirrored contact gap {other_gap:.6g} mm (limit 0.1 mm)')
        measurements.append(row)
    for a in rules.alignments:
        direction = matrix(parts[a.part])[:, 'xyz'.index(a.local_axis)]
        expected = np.zeros(3); expected['xyz'.index(a.world_axis[-1])] = -1 if a.world_axis.startswith('-') else 1
        error = math.degrees(math.acos(float(np.clip(np.dot(direction, expected), -1, 1))))
        measurements.append({'kind': 'axis', 'part': a.part, 'axis_error_deg': error})
        if error > 1e-5: issue('DECLARED_AXIS', [a.part], f'Axis error {error:.6g} degrees')
    for body in rules.bodies:
        for left, right in zip(body.members, body.members[1:]):
            p, q = parts[left.part], parts[right.part]; error = 0.0
            for angle in range(0, 360, 45):
                error = max(error, float(np.linalg.norm(anchor_world(p, Anchor(kind='body', u=1, v=1, angle_deg=angle))-anchor_world(q, Anchor(kind='body', u=0, v=1, angle_deg=angle)))))
            measurements.append({'kind': 'body_seam', 'parent': p.id, 'child': q.id, 'seam_error_mm': error})
            if error > 1e-5: issue('BODY_SEAM', [p.id, q.id], f'Boundary mismatch {error:.6g} mm')
    return {'schema': 'fk-assembly-checks-v1', 'passed': not issues, 'issues': issues, 'measurements': measurements,
        'declared_contacts': sum(a.relation == 'contact' for a in rules.attachments),
        'scope': 'Declared anchor, axis, body-seam and contact distances only. Contact can include overlap; no penetration, smoothness, strength or full assembly certification. Undeclared relationships are unassessed.'}
