"""Immutable manufacturing occurrences, receipts, real Lean checks and FK DAG."""
from __future__ import annotations
import hashlib
import json
import subprocess
from pathlib import Path
from fluxkernel.core.objects import Node, Edge, Certificate, Obligation, ResourceVector
from fluxkernel.semantics.operators import Engine
from fluxkernel.semantics import contracts
from fluxkernel.interface.cli import verify_store
from fluxkernel.runtime import assets_root, copy_proof_project

ROOT=assets_root()


def digest(value):
    data=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def make_plan(design, equipment, checks, depth, image_hash, brief_hash):
    steps=[];receipts={}; lookup={}
    def add(id,name,route,deps,level,detail,part=None):
        receipt={'id':id,'route':route,'input_image_sha256':image_hash,'request_sha256':brief_hash,
            'dependencies':deps,'detail':detail,'scope':'concept-manufacturing-plan',
            'physical_evidence':'not-established'}
        if part: receipt['recipe']=part.model_dump();receipt['geometry']=checks[part.id]
        rh=digest(receipt);receipts[rh]=receipt
        step={'id':id,'name':name,'route':route,'deps':list(deps),'depth':level,'receipt':rh}
        lookup[id]=len(steps);steps.append(step)
        return id
    seed=add('seed-printer','K₀ · 给定打印与基础装配能力','seed',[],0,
        {'unlimited_envelope':True,'available_material_processes':['pla','petg','abs','aluminum','steel'],
         'materials_used':sorted({p.material for p in design.parts+equipment if p.route!='catalog'}),
         'assumption':'Material-specific processes, power, feedstock, support removal and manual assembly are supplied externally. No equipment capability has been physically demonstrated.'})
    cell=None
    if equipment:
        edeps=[]
        for p in equipment:
            route='catalog' if p.route=='catalog' else 'print'
            edeps.append(add(p.id,p.name,route,[] if route=='catalog' else [seed],1,
                {'catalog_ref':p.catalog_ref,'catalog_qualification':'pending' if route=='catalog' else None},p))
        cell=add('machine-cell','M₁ · 定制钻铣设备','equipment',edeps,1,
            {'capability':'drilling/milling concept','rigidity_runout_accuracy':'not-established',
             'manufacturing_generation':1})
    leaves=[]
    for p in design.parts:
        if p.route=='catalog':
            leaf=add(p.id,p.name,'catalog',[],0,{'catalog_ref':p.catalog_ref,'supplier_qualification':'pending'},p)
        elif p.route=='print':
            leaf=add(p.id,p.name,'print',[seed],0,{'process':'material-specific additive manufacturing'},p)
        else:
            blank=add(p.id+'-blank',p.name+' · 打印毛坯','print',[seed],0,
                {'process':'print near-net blank','finish_stock':'selected in concept recipe'},p)
            # A depth=0 plan with machining remains explicitly invalid; never
            # silently procure a whole machine or rewrite a machined part to print.
            leaf=add(p.id,p.name,'machine',[blank]+([cell] if cell else []),0,
                {'operation':'drill/mill mating features','machine':cell,'fixture':'cell-fixture',
                 'toolpath':'pending','metrology':'pending'},p)
        leaves.append(leaf)
    groups=[]
    for group in dict.fromkeys(p.group for p in design.parts):
        deps=[p.id for p in design.parts if p.group==group]
        gid='assembly-'+hashlib.sha256(group.encode()).hexdigest()[:8]
        groups.append(add(gid,group,'assemble',deps,0,{'joining':'declared assembly plan; access/fit pending'}))
    add('product',design.title,'assemble',groups,0,{'requirements':design.requirements,
        'requirement_status':'candidate coverage; physical/functional satisfaction not established'})
    return {'schema':'fk-manufacturing-1','policy':{'equipment_depth':depth},
            'image_sha256':image_hash,'request_sha256':brief_hash,'steps':steps,'receipts':receipts}


def validate(plan):
    issues=[];steps=plan['steps'];positions={s['id']:i for i,s in enumerate(steps)}
    if len(positions)!=len(steps): issues.append('duplicate occurrence identity')
    for i,s in enumerate(steps):
        if s['receipt'] not in plan['receipts'] or digest(plan['receipts'].get(s['receipt']))!=s['receipt']:
            issues.append(f"{s['id']}: invalid receipt binding")
        receipt=plan['receipts'].get(s['receipt'],{})
        if (receipt.get('id')!=s['id'] or receipt.get('route')!=s['route'] or
            receipt.get('dependencies')!=s['deps'] or
            receipt.get('input_image_sha256')!=plan['image_sha256'] or
            receipt.get('request_sha256')!=plan['request_sha256']):
            issues.append(f"{s['id']}: receipt does not describe this occurrence/input")
        if s['route'] not in ('seed','catalog','print','machine','equipment','assemble'):
            issues.append(f"{s['id']}: unknown route")
        if not isinstance(s['depth'],int) or s['depth']<0:
            issues.append(f"{s['id']}: invalid generation")
        if s['depth']>plan['policy']['equipment_depth']: issues.append(f"{s['id']}: equipment depth exceeded")
        for dep in s['deps']:
            if dep not in positions or positions[dep]>=i: issues.append(f"{s['id']}: dependency not available: {dep}")
        routes=[steps[positions[d]]['route'] for d in s['deps'] if d in positions]
        if s['route'] in ('seed','catalog') and s['deps']: issues.append(f"{s['id']}: primitive has dependencies")
        if s['route']=='print' and 'seed' not in routes: issues.append(f"{s['id']}: no initial printing capability")
        if s['route']=='machine' and not {'print','equipment'}<=set(routes): issues.append(f"{s['id']}: machining needs blank and built equipment")
        if s['route']=='equipment' and not {'print','catalog'}<=set(routes): issues.append(f"{s['id']}: equipment constituents incomplete")
        if s['route']=='assemble' and not s['deps']: issues.append(f"{s['id']}: empty assembly")
    if not steps or steps[-1]['id']!='product': issues.append('missing product root')
    seen=set(); pending=['product']
    while pending:
        id=pending.pop()
        if id in seen or id not in positions: continue
        seen.add(id);pending.extend(steps[positions[id]]['deps'])
    if set(positions)-seen: issues.append('orphan manufacturing occurrences')
    return issues


def lean_source(plan):
    positions={s['id']:i for i,s in enumerate(plan['steps'])}
    rows=[]
    for s in plan['steps']:
        deps=[positions.get(d,len(plan['steps'])) for d in s['deps']]
        rows.append('  ⟨.'+s['route']+', '+str(deps)+', '+str(s['depth'])+', '+json.dumps(s['receipt'])+'⟩')
    # Source data literal and theorem share the exact receipt references.
    return ('import FluxKernel.Closure\nopen FluxKernel\nset_option maxRecDepth 8192\n'
        'set_option maxHeartbeats 8000000\n'
        +'def plan : List Step := [\n'+',\n'.join(rows)+'\n]\n'
        +f"def policy : Policy := ⟨{plan['policy']['equipment_depth']}⟩\n"
        +'theorem planAccepted : check policy plan = true := by decide\n'
        +'theorem manufacturingClosed : VerifiedPlan policy plan := check_sound policy plan planAccepted\n'
        +'#print axioms manufacturingClosed\n')


def prove(plan, directory):
    directory=Path(directory).resolve()
    copy_proof_project(directory)
    source=lean_source(plan);target=directory/'ManufacturingPlan.lean';target.write_text(source)
    issues=validate(plan)
    try:
        build=subprocess.run(['lake','build'],cwd=directory,capture_output=True,text=True,timeout=120)
        if build.returncode:
            proc=build
        else:
            proc=subprocess.run(['lake','env','lean',target.name],cwd=directory,capture_output=True,text=True,timeout=90)
        log=build.stdout+build.stderr+(proc.stdout+proc.stderr if proc is not build else '')
        accepted=proc.returncode==0 and not issues
        if proc.returncode: issues.append('Lean rejected the plan or its proof project could not be built; see lean-check.log')
    except (OSError,subprocess.TimeoutExpired) as exc:
        log=f'Lean unavailable or timed out: {type(exc).__name__}';accepted=False
        issues.append('Lean unavailable or timed out; install the pinned toolchain and rerun verification')
    (directory/'lean-check.log').write_text(log)
    if 'sorryAx' in log or 'Lean.trustCompiler' in log or '_native.' in log:
        accepted=False;issues.append('unapproved proof dependency')
    result={'accepted':accepted,'checker':'Lean 4.34.1','plan_sha256':digest(plan),
        'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'kernel_source_sha256':hashlib.sha256((ROOT/'formal/FluxKernel/Closure.lean').read_bytes()).hexdigest(),
        'issues':issues,'scope':['finite manufacturing closure','earlier dependencies/no self-bootstrap',
            'bounded equipment generation','typed manufacturing routes','all occurrences used by product'],
        'excluded':['physical manufacturability','catalog authenticity/availability','functional performance',
            'image-to-design fidelity','truth of external capability assumptions'],
        'axioms_log':log[-2000:]}
    (directory/'proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def persist_fk(plan, store, checks, blobs):
    eng=Engine(store,load=False)
    term=contracts.put_term(store,'plan-closure','finite manufacturing plan under declared external assumptions')
    nodes={}
    for step in plan['steps']:
        receipt=plan['receipts'][step['receipt']]
        receipt_digest=store.put_object('receipt',receipt)
        part=receipt.get('recipe');ground=None
        if part:
            ground={'type':'demo-concept','blobs':blobs[part['id']],
                'volume_mm3':checks[part['id']]['volume_mm3'],'recipe':part}
        spec={'goals':[{'id':'plan','stmt':'record manufacturing derivation','falsifiable':True,'measure':'Lean plan checker'}],
            'semantics':[term],'assumes':[{'id':'external','stmt':'declared capability assumptions','bounds':{'equipment_depth':['<=',1]}}],
            'guarantees':[{'id':'record','stmt':'receipt-bound plan step','bounds':{'receipt_count':['=',1]}}],
            'budget':{},'effluent':{},'forbidden':[{'id':'cycle','stmt':'self-bootstrap','check':'reachability'}],
            'not_responsible':['physical validation'],'time_scale':'design-plan'}
        role='Resource' if step['route'] in ('seed','equipment') else 'Component' if step['route']=='assemble' else 'Part'
        node=Node(role=role,kind=step['id'],spec=spec,params={'receipt':step['receipt'],'route':step['route']},ground=ground)
        ids=[nodes[x] for x in step['deps'] if x in nodes]
        valid=len(ids)==len(step['deps'])
        cert=Certificate(obligations=[Obligation('receipt-bound','receipt stored',True,checker='demo-receipt'),
            Obligation('dependencies-available','all inputs available',valid,checker='demo-plan'),
            Obligation('physical-validation','physical validation pending',False,checker='external',oclass='soft')],
            evidence=[{'receipt':receipt_digest,'scope':'plan-only'}],evaluator='demo-checker',executor='demo')
        edge=Edge(op='compose' if step['route'] in ('assemble','equipment') else 'manufacture',
            inputs=ids,transform={'name':step['route'],'args':{'occurrence':step['id']}},output='')
        ed,nd=eng.dag.commit_edge(edge,node,cert,ResourceVector(),edge_name='step/'+step['id'],node_name=step['id'])
        nodes[step['id']]=nd
        if edge.state!='promoted': raise ValueError(f"FK record rejected: {step['id']}: {edge.reason}")
    problems=verify_store(eng)
    if problems: raise ValueError('FK integrity check failed: '+str(problems))
    return {'nodes':nodes,'edges':len(plan['steps']),'integrity_verified':True,'store':'.fk'}
