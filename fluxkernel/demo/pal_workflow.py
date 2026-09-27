"""GLM-authored PAL workflow. Host enforces contracts; GLM chooses designs."""
from __future__ import annotations
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Literal
from pydantic import Field
from . import perception as pal
from .models import StrictModel
from .parametric import WingParameters,BodyParameters
from .pal_rules import WorkflowPlan,validate_plan,compile_symmetry,apply_workflow_action,parameter_facts
from .perception_render import render_design

MODEL='glm-5.3-flash'
SKILL=Path(__file__).parent/'skills/fluxkernel-glm-pal'

class Claim(StrictModel):
    part: str
    field: str=Field(min_length=1,max_length=120)
    value: float | str

class Review(pal.Review):
    numeric_claims: list[Claim]=Field(min_length=1,max_length=24)

class Decision(StrictModel):
    selected_round: int=Field(ge=0)
    next_step: Literal['revise','stop']
    stage: Literal['proportions','connections','surfaces']
    reason: str=Field(min_length=1,max_length=1600)


def require_glm(cfg=None):
    cfg=cfg if cfg is not None else pal.vision.model_config()
    if cfg.get('model')!=MODEL:raise ValueError('This workflow requires glm-5.3-flash; no model fallback is allowed')
    return {**cfg,'required_model':MODEL}


def validate_review(raw,design):
    review=Review.model_validate(raw);parts={p.id:p.model_dump() for p in design.parts}
    if any(not set(f.parts)<=parts.keys() for f in review.findings):raise ValueError('Review references unknown part IDs')
    for claim in review.numeric_claims:
        if claim.part not in parts:raise ValueError('Numeric claim references unknown part')
        try:
            value=parts[claim.part]
            for key in claim.field.split('.'):value=value[int(key)] if isinstance(value,list) else value[key]
        except (KeyError,ValueError,IndexError,TypeError):raise ValueError(f'Unknown recipe fact {claim.part}.{claim.field}')
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            correct=isinstance(claim.value,(int,float)) and math.isclose(value,claim.value,rel_tol=1e-6,abs_tol=1e-6)
        else:correct=isinstance(value,str) and value==claim.value
        if not correct:raise ValueError(f'Fact mismatch: {claim.part}.{claim.field} is {value!r}, not {claim.value!r}; use current recipe facts')
    return review


def _action_schema(design):
    schema=pal.action_schema(design)
    properties=schema['properties']['edits']['items']['properties']['set']['properties']
    # Model receives these full object schemas separately to avoid unresolved $refs.
    properties['parametric']={'type':'object','description':'Complete wing or body object matching parameter_schemas; binding must be approved in workflow plan'}
    return schema


def run(design,image,brief,run,event,*,contract,rounds=3,deadline_s=900):
    if type(rounds) is not int or not 1<=rounds<=4:raise ValueError('Visual rounds must be 1..4')
    cfg=require_glm();root=run/'perception';root.mkdir(exist_ok=False)
    sources={}
    for name in ['pal_workflow.py','pal_rules.py','parametric.py','models.py','geometry.py','perception.py','perception_render.py']:
        content=Path(__file__).with_name(name).read_bytes();(root/name).write_bytes(content);sources[name]=hashlib.sha256(content).hexdigest()
    instructions=(SKILL/'SKILL.md').read_text()+'\n'+(SKILL/'references/parameters.md').read_text()
    (root/'skill.md').write_text(instructions);sources['skill.md']=hashlib.sha256(instructions.encode()).hexdigest()
    reference=root/'reference.png';reference.write_bytes(image);pal.save(root/'input-design.json',design.model_dump())
    calls=[];records=[];best=None;plan=None;candidate=design;stop='budget-exhausted';started=time.monotonic();failure=None
    max_calls=6*rounds  # plan(2), review+decision(4R), action(2(R-1))

    def ask(phase,payload,images,schema,directory,validate):
        feedback=None
        for attempt in range(2):
            if time.monotonic()-started>=deadline_s or len(calls)>=max_calls:raise TimeoutError('Workflow budget exhausted before next model request')
            label=phase if attempt==0 else phase+'-repair'
            event('perception',f'{MODEL} · {phase}'+(' · 自动纠错' if attempt else ''))
            try:
                raw=pal.model_json(cfg,instructions+'\nCurrent phase: '+phase+'\nReturn JSON only; use Chinese explanations.',
                    json.dumps({**payload,'validation_feedback':feedback},ensure_ascii=False),images,schema,directory,label,event,calls)
            finally:
                response_file=directory/(label+'-response.json')
                if calls and response_file.exists():calls[-1]['response_file']=response_file.relative_to(run).as_posix()
            try:return validate(raw)
            except (ValueError,TypeError,KeyError) as exc:
                feedback={'error':str(exc)[:6000],'rejected_response':raw}
                pal.save(directory/(label+'-rejected.json'),feedback)
                if attempt:raise
        raise AssertionError('Unreachable')

    try:
        baseline=root/'baseline';baseline.mkdir()
        base_render=render_design(design,baseline)
        planning=root/'planning';planning.mkdir()
        def check_plan(raw):
            value=validate_plan(raw,design)
            compile_symmetry(design,value,contract)
            return value
        plan=ask('plan',{'brief':brief,'design':design.model_dump(),'frozen_constraints':contract,
            'instruction':'Judge symmetry before any edit. Declare compatible source/target pairs and semantic parameter bindings; list explicit exceptions. Do not invent a new design.'},
            [reference,baseline/'views.png'],WorkflowPlan.model_json_schema(),planning,check_plan)
        pal.save(planning/'plan.json',plan.model_dump())
        # Deterministic interpretation of GLM's declaration, not a host design edit.
        candidate=compile_symmetry(design,plan,contract)
        pal.save(planning/'symmetry-activation.json',{'actor':MODEL,'operation':'compile-declared-mirrors','before':pal.digest(design.model_dump()),'after':pal.digest(candidate.model_dump()),'pairs':[p.model_dump() for p in plan.pairs]})
        stage=plan.stages[0]
        for index in range(rounds):
            directory=root/f'round-{index:02d}';directory.mkdir()
            record={'round':index,'state':'started','derived_from':best['round'] if best else None,'stage':stage,
                'design_sha256':pal.digest(candidate.model_dump())};records.append(record)
            pal.save(directory/'design.json',candidate.model_dump())
            if time.monotonic()-started>=deadline_s:raise TimeoutError('Workflow budget exhausted before render')
            rendering=render_design(candidate,directory)
            all_bounds=[base_render['actual_bounds_mm'],rendering['actual_bounds_mm']]
            if best:all_bounds.append(best['render']['actual_bounds_mm'])
            bounds=[[min(b[0][i] for b in all_bounds) for i in range(3)],[max(b[1][i] for b in all_bounds) for i in range(3)]]
            if bounds!=rendering['bounds_mm']:rendering=render_design(candidate,directory,bounds=bounds)
            images=[reference,directory/'views.png']
            if best:
                render_design(best['design'],directory/'retained-comparison',bounds=bounds)
                images.append(directory/'retained-comparison/views.png')
            facts=parameter_facts(candidate,best['design'] if best else design);pal.save(directory/'parameter-facts.json',facts)
            checks=pal.layout_checks(candidate);pal.save(directory/'layout-checks.json',checks)
            record['view']=f'perception/round-{index:02d}/views.png'
            record['render_frame']='union of baseline/current/retained; both comparison sheets share bounds'
            review=ask('review',{'brief':brief,'design':candidate.model_dump(),'current_parameter_facts':facts,
                'workflow':plan.model_dump(),'stage':stage,'layout_checks':checks,'prior_best_review':best['review'] if best else None,
                'instruction':'Read current facts first. Check visual appearance and supply exact numeric_claims; do not repeat obsolete values. Images: reference, current, retained if present.'},
                images,Review.model_json_schema(),directory,lambda raw:validate_review(raw,candidate))
            pal.save(directory/'review.json',review.model_dump())
            record.update(state='reviewed',review=review.model_dump(),layout=checks,rank=list(pal.rank(review,checks)))
            options=[index]+([best['round']] if best else [])
            decision_schema=Decision.model_json_schema();decision_schema['properties']['selected_round']['enum']=options
            def check_decision(raw):
                d=Decision.model_validate(raw)
                if d.selected_round not in options:raise ValueError('Select only the current or retained reviewed candidate')
                if d.stage not in plan.stages:raise ValueError('Choose a stage declared in the workflow plan')
                return d
            decision=ask('select',{'current':{'round':index,'review':record['review'],'layout':checks,'parameter_facts':facts},
                'retained':{'round':best['round'],'review':best['review'],'layout':best['layout']} if best else None,
                'workflow':plan.model_dump(),'remaining_candidate_revisions':rounds-index-1,
                'instruction':'You alone select which reviewed candidate to retain, and whether/where to revise next. Consider actual images and parameter changes. Host ranking is diagnostic only, not the selection rule.'},
                images,decision_schema,directory,check_decision)
            record['decision']=decision.model_dump();pal.save(directory/'decision.json',decision.model_dump())
            record['selected_when_reviewed']=decision.selected_round==index
            if decision.selected_round==index:best={**record,'design':candidate,'render':rendering}
            stage=decision.stage
            if decision.next_step=='stop':stop='model-stop';break
            if index==rounds-1:break
            action_directory=directory/'action';action_directory.mkdir()
            base=best['design'];attempts=[];record['action_attempts']=attempts
            def check_action(raw):
                try:
                    result=apply_workflow_action(base,raw,contract,plan)
                    # Reject invalid B-reps before they can be selected; model gets the error.
                    from .geometry import build
                    from OCP.BRepCheck import BRepCheck_Analyzer
                    for part in result.parts:
                        if not BRepCheck_Analyzer(build(part)).IsValid():raise ValueError(f'{part.id}: invalid candidate geometry')
                    attempts.append({'attempt':len(attempts),'accepted':True});return result
                except Exception as exc:
                    attempts.append({'attempt':len(attempts),'accepted':False,'error':str(exc)[:1500]})
                    raise ValueError(str(exc)) from exc
            candidate=ask('action',{'base_design_sha256':pal.digest(base.model_dump()),'design':base.model_dump(),
                'workflow':plan.model_dump(),'stage':stage,'selection_reason':decision.reason,'review':best['review'],
                'current_parameter_facts':parameter_facts(base),'last_candidate':record,'frozen_constraints':contract,
                'parameter_schemas':{'wing':WingParameters.model_json_schema(),'body':BodyParameters.model_json_schema()},
                'instruction':'Edit source occurrences only. Full semantic objects derive size/shape; adjust origin when upgrading a wing. Address the selected stage; no free code or hidden manual repairs.'},
                [reference,root/f"round-{best['round']:02d}"/'views.png'],_action_schema(base),action_directory,check_action)
            record['action_state']='accepted-for-evaluation'
    except Exception as exc:
        failure=str(exc).replace(cfg.get('api_key') or '\0','[REDACTED]')[:2000]
        pal.save(root/'error.json',{'type':type(exc).__name__,'error':failure});stop='workflow-failed'
        if records:records[-1]['error']=failure
    selected=best['design'] if best else design
    approved=bool(best and not best['layout']['issues'] and not any(f['severity'] in ('major','blocking') for f in best['review']['findings']) and min(best['review'][k] for k in ('silhouette','proportions','layout'))>=80)
    summary={'schema':'fk-perception-loop-v2','workflow':'glm-symmetry-parametric-v1','enabled':True,
        'model':MODEL,'decision_author':MODEL,'human_design_edits':False,'selection_policy':'GLM decision among reviewed current/retained candidates; host only validates',
        'sources_sha256':sources,'plan':plan.model_dump() if plan else None,'max_rounds':rounds,'rounds':records,
        'selected_round':best['round'] if best else None,'selected_design_sha256':pal.digest(selected.model_dump()),
        'stop_reason':stop,'error':failure,'quality_status':'model-threshold-met' if approved and not failure else 'needs-review',
        'reviewed':best is not None,'score_source':'model-judgment; not a calibrated similarity metric',
        'reference_camera_aligned':False,'physical_status':'unverified','calls':calls,'model_calls':len(calls),
        'elapsed_s':round(time.monotonic()-started,2),'action_retries_per_round':1}
    pal.save(root/'summary.json',summary);return selected,summary
