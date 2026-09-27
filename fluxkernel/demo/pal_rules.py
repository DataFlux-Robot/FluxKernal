"""GLM-authored workflow declarations and deterministic symmetry compilation."""
from __future__ import annotations
import copy
from typing import Literal
from pydantic import Field
from .models import StrictModel,Design
from .constraints import evaluate

class Pair(StrictModel):
    source: str
    target: str

class Parameterization(StrictModel):
    part: str
    kind: Literal['wing','body']

class WorkflowPlan(StrictModel):
    symmetry: Literal['bilateral','partial','none','uncertain']
    axis: Literal['x','y','z']
    plane_offset: float=Field(ge=-100000,le=100000)
    confidence: float=Field(ge=0,le=1)
    rationale: str=Field(min_length=1,max_length=1600)
    visible_evidence: list[str]=Field(min_length=1,max_length=12)
    exceptions: list[str]=Field(max_length=64,description='Exact existing part IDs only, without labels or explanations; put explanations in rationale')
    pairs: list[Pair]=Field(max_length=32)
    parameterization: list[Parameterization]=Field(max_length=32)
    stages: list[Literal['proportions','connections','surfaces']]=Field(min_length=1,max_length=3)


def validate_plan(plan,design):
    plan=WorkflowPlan.model_validate(plan);parts={p.id:p for p in design.parts};seen=set()
    if plan.symmetry in ('none','uncertain') and plan.pairs:raise ValueError('No mirroring when symmetry is none or uncertain')
    if plan.symmetry in ('bilateral','partial') and not plan.pairs:raise ValueError('Active symmetry requires explicit part pairs')
    for pair in plan.pairs:
        if pair.source==pair.target or pair.source in seen or pair.target in seen:raise ValueError('Symmetry pairs must be disjoint, without cycles or self references')
        if pair.source not in parts or pair.target not in parts:raise ValueError('Unknown symmetry part')
        a,b=parts[pair.source],parts[pair.target]
        if a.route!=b.route or a.material!=b.material:raise ValueError('Symmetry cannot change route/material; pair compatible occurrences')
        if a.reflection not in (None,plan.axis):raise ValueError('Source reflection axis conflicts with this symmetry plane')
        if a.route=='catalog' and (a.shape not in ('box','cylinder','tube') or a.shape!=b.shape or a.size!=b.size or a.wall!=b.wall):
            raise ValueError('Catalog pairs require equal symmetric primitive envelopes; no catalog dimension changes')
        seen.update((pair.source,pair.target))
    invalid=set(plan.exceptions)-parts.keys();overlap=set(plan.exceptions)&seen
    if invalid or overlap:raise ValueError(f'Exceptions must be exact existing IDs, not descriptions. Unknown entries: {sorted(invalid)}; already mirrored: {sorted(overlap)}. Move explanations to rationale.')
    targets={p.target for p in plan.pairs};bound=set()
    for binding in plan.parameterization:
        if binding.part not in parts or binding.part in targets or binding.part in bound:raise ValueError('Parameterize unique independent source parts, not symmetry targets')
        part=parts[binding.part]
        if part.route=='catalog':raise ValueError('Cannot parameterize purchased geometry')
        shapes={'wing':{'wing','parametric_wing'},'body':{'fuselage','smooth_fuselage','fuselage_section','fuselage_nose','fuselage_tail','car_body','smooth_car_body','section_body'}}
        if part.shape not in shapes[binding.kind]:raise ValueError('Parameterization kind incompatible with existing recipe')
        bound.add(binding.part)
    if len(set(plan.stages))!=len(plan.stages):raise ValueError('Workflow stages must be unique')
    return plan


def compile_symmetry(design,plan,contract):
    value=design.model_dump();parts={p['id']:p for p in value['parts']};axis='xyz'.index(plan.axis)
    for pair in plan.pairs:
        source,target=parts[pair.source],parts[pair.target]
        if source['route']!='catalog':
            for key in ('shape','size','wall'):target[key]=copy.deepcopy(source[key])
            target.pop('parametric',None)
            if 'parametric' in source:target['parametric']=copy.deepcopy(source['parametric'])
            # S R S is a rotation; its axial Euler angles change sign except
            # around the mirror normal. Remaining S mirrors local geometry.
            target['reflection']=None if source.get('reflection')==plan.axis else plan.axis
        target['position']=source['position'].copy();target['position'][axis]=2*plan.plane_offset-source['position'][axis]
        target['rotation']=[a if i==axis else -a for i,a in enumerate(source['rotation'])]
        target['source']='selected'
    result=Design.model_validate(value)
    if not evaluate(result.model_dump(),contract)['accepted']:raise ValueError('Symmetry violates frozen nominal constraints')
    return result


def apply_workflow_action(design,action,contract,plan):
    from .perception import apply_action
    targets={p.target for p in plan.pairs}
    if any(e.get('part') in targets for e in action.get('edits',[]) if isinstance(e,dict)):
        raise ValueError('Symmetry targets are derived; edit their source occurrence only')
    changed=apply_action(design,action,{'schema':'fk-constraints-v1','rules':[]},parameter_kinds={p.part:p.kind for p in plan.parameterization})
    return compile_symmetry(changed,plan,contract)


def parameter_facts(design,previous=None):
    old={p.id:p.model_dump() for p in previous.parts} if previous else {};facts=[]
    for part in design.parts:
        data=part.model_dump();fields=('size','position','rotation','shape','parametric','reflection')
        facts.append({'part':part.id,'current':{k:data[k] for k in fields if k in data},
            'changed':{k:{'before':old[part.id].get(k),'after':data.get(k)} for k in fields if part.id in old and old[part.id].get(k)!=data.get(k)}})
    return {'units':'mm and degrees','authority':'Computed from current CAD recipes; numeric claims must agree with this table','parts':facts}


def plan_schema(design):
    schema=WorkflowPlan.model_json_schema();ids=[p.id for p in design.parts]
    schema['properties']['exceptions']['items']={'type':'string','enum':ids}
    for key in ('source','target'):schema['$defs']['Pair']['properties'][key]['enum']=ids
    schema['$defs']['Parameterization']['properties']['part']['enum']=ids
    return schema
