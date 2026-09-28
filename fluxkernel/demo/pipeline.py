from __future__ import annotations
import hashlib
import io
import json
import shutil
import time
from pathlib import Path
from PIL import Image
from fluxkernel.store.objstore import Store
from . import vision, geometry, manufacturing
from .models import Request
from .references import reference, equipment_parts


def write_json(path, data):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False));tmp.replace(path)


def normalize_image(data):
    if len(data)>15*1024*1024: raise ValueError('图片不能超过15MB')
    with Image.open(io.BytesIO(data)) as im:
        if im.width*im.height>20_000_000: raise ValueError('图片像素不能超过2000万')
        im=im.convert('RGB');im.thumbnail((1280,1280))
        buf=io.BytesIO();im.save(buf,'PNG');return buf.getvalue()


def reusable_parent(run, request):
    """Load a verified checkpoint; never reuse artifacts from a mutated parent."""
    if not request.parent: return None
    root=run.parent/request.parent
    manifest=json.loads((root/'manifest.json').read_text())
    def read(name):
        data=(root/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=manifest.get(name):
            raise ValueError('父版本证据已改变，不能复用：'+name)
        return data
    design=json.loads(read('design.json'));equipment=json.loads(read('equipment.json'))
    scenes=json.loads(read('scene.json'));checks=json.loads(read('geometry-checks.json'))
    contract=json.loads(read('constraints.json')) if 'constraints.json' in manifest else {'schema':'fk-constraints-v1','rules':[]}
    return {'read':read,'design':design,'constraints':contract,'parts':{p['id']:p for p in design['parts']+equipment},
            'meshes':{p['id']:p for p in scenes['product']+scenes['equipment']},'checks':checks}


def execute(run: Path, request: Request, image: bytes, previous=None, *,
            design_override=None, constraint_contract=None, parent_cache_override=None,
            revision_record=None, asset_reuse_record=None, equipment_override=None):
    start=time.monotonic(); events=[]
    def event(stage,message):
        events.append({'stage':stage,'message':message,'elapsed_s':round(time.monotonic()-start,1)})
        write_json(run/'status.json',{'id':run.name,'state':'running','stage':stage,'events':events})
    try:
        parent_cache=parent_cache_override if parent_cache_override is not None else reusable_parent(run,request)
        if parent_cache:
            if previous is not None and previous != parent_cache['design']:
                raise ValueError('Parent design changed before revision execution')
            previous=parent_cache['design']
            inherited=parent_cache['constraints']
            extended=asset_reuse_record is not None and constraint_contract is not None and constraint_contract['rules'][:len(inherited['rules'])]==inherited['rules']
            if constraint_contract is not None and constraint_contract != inherited and not extended:
                raise ValueError('A revision cannot replace the parent constraint contract')
            if not extended:constraint_contract=inherited
        event('input','锁定参考图片、需求与一轮设备展开预算')
        normalized=normalize_image(image);(run/'image.png').write_bytes(normalized)
        image_hash=hashlib.sha256(image).hexdigest()
        input_record={'request':request.model_dump(),'image_sha256':image_hash,
            'normalized_image_sha256':hashlib.sha256(normalized).hexdigest(),
            'interpretation':'functional architecture and key exterior reconstruction; hidden internals remain hypotheses',
            'initial_capability':{'unlimited_envelope':True,
                'available_material_processes':['pla','petg','abs','aluminum','steel'],
                'supplied_externally':['feedstock','power','support removal','basic assembly'],
                'status':'explicit demonstration assumptions; not measured capabilities'}}
        from .constraints import evaluate, validate_contract
        constraint_contract = constraint_contract if constraint_contract is not None else {'schema':'fk-constraints-v1','rules':[]}
        validate_contract(constraint_contract)
        input_record['constraints_sha256']=manufacturing.digest(constraint_contract)
        constraint_checker_source=Path(__file__).with_name('constraints.py').read_bytes()
        input_record['constraint_checker_sha256']=hashlib.sha256(constraint_checker_source).hexdigest()
        if revision_record is not None:
            input_record['revision']=revision_record
        if asset_reuse_record is not None:
            input_record['asset_reuse_sha256']=manufacturing.digest(asset_reuse_record)
            input_record['asset_sha256']=asset_reuse_record['asset_sha256']
        if request.mode in ('fixture','revision'):
            input_record['interpretation']='explicit parametric design; no image inference or model call'
        write_json(run/'input.json',input_record)
        write_json(run/'constraints.json',constraint_contract)
        if request.mode=='live' and request.visual_rounds:
            from .pal_workflow import require_glm
            require_glm()
        if request.mode in ('fixture','revision'):
            if design_override is None: raise ValueError('Explicit design input is required')
            from .models import Design
            design=Design.model_validate(design_override)
            model={'mode':request.mode,'model':'local-parameters-v1','elapsed_s':0}
            event('design','Explicit parametric design; no model call')
        elif request.mode=='reference':
            if not request.reference: raise ValueError('参考回放需要选择案例')
            design=reference(request.reference)
            model={'mode':'reference','model':'curated-reference','elapsed_s':0}
            event('vision','离线参考回放 · 未调用视觉模型')
        elif design_override is not None:
            from .models import Design
            if not parent_cache or design_override != parent_cache['design']:
                raise ValueError('Visual refinement must start from the verified parent design')
            design=Design.model_validate(design_override)
            cfg=vision.model_config()
            model={'mode':'live','model':cfg['model'],'provider':cfg['provider'],
                   'attempts':0,'initial_design':'verified-parent','elapsed_s':0}
        else:
            design,model=vision.plan(normalized,request.brief,run,event,previous)
        perception={'enabled':False,'quality_status':'not-evaluated','model_calls':0}
        if request.mode=='live' and request.visual_rounds:
            from .perception import run_loop
            design,perception=run_loop(design,normalized,request.brief,run,event,
                                      contract=constraint_contract,rounds=request.visual_rounds)
            model['perception_calls']=perception['model_calls']
            model['total_calls']=model.get('attempts',0)+perception['model_calls']
            model['elapsed_s']=round(model.get('elapsed_s',0)+perception['elapsed_s'],2)
            for token_kind in ('input_tokens','output_tokens'):
                model[token_kind]=(model.get(token_kind) or 0)+sum(c.get('usage',{}).get(token_kind,0) for c in perception['calls'])
        write_json(run/'design.json',design.model_dump());write_json(run/'model.json',model)
        constraint_report=evaluate(design.model_dump(),constraint_contract)
        write_json(run/'constraint-checks.json',constraint_report)
        if not constraint_report['accepted']:
            raise ValueError('Frozen nominal constraints failed: '+', '.join(c['id'] for c in constraint_report['checks'] if not c['passed']))
        before={p['id']:p for p in (previous or {}).get('parts',[])}
        after={p.id:p.model_dump() for p in design.parts}
        write_json(run/'trajectory.json',{'parent':request.parent,'input':input_record,
            'model':model,'action':'revise-design' if previous else 'image-to-design',
            'added':sorted(after.keys()-before.keys()),'removed':sorted(before.keys()-after.keys()),
            'changed':[k for k in before.keys()&after.keys() if before[k]!=after[k]],
            'unchanged':[k for k in before.keys()&after.keys() if before[k]==after[k]],
            'evaluation':'construction and plan checks; user acceptance and physical validation pending'})
        event('decompose',f'候选产品架构：{len(design.parts)} 个具名零件 / {len(set(p.group for p in design.parts))} 个子系统')
        equipment=equipment_parts([p for p in design.parts if p.route=='machine']) if any(p.route=='machine' for p in design.parts) and request.equipment_depth else []
        if equipment_override is not None:
            from .models import Part
            equipment=[Part.model_validate(p) for p in equipment_override]
        write_json(run/'equipment.json',[p.model_dump() for p in equipment])
        event('equipment',f'设备展开：{len(equipment)} 个标准与打印部件' if equipment else '本轮没有展开加工设备')
        store=Store(run/'.fk');artifact_dir=run/'cad';artifact_dir.mkdir(exist_ok=True)
        scene=[];cell_scene=[];checks={};blobs={};reused=[]
        for i,p in enumerate(design.parts+equipment):
            if parent_cache and parent_cache['parts'].get(p.id)==p.model_dump():
                event('geometry',f'校验并复用父版本未变零件：{p.name}')
                mesh=parent_cache['meshes'][p.id];check=parent_cache['checks'][p.id];refs={}
                for ext in ('step','stl'):
                    data=parent_cache['read'](f'cad/{p.id}.{ext}')
                    (artifact_dir/f'{p.id}.{ext}').write_bytes(data)
                    refs[ext]=store.put_blob(data)
                reused.append(p.id)
            else:
                event('geometry',f'生成并检查 B-rep / STEP / STL：{p.name} ({i+1}/{len(design.parts)+len(equipment)})')
                mesh,check,refs=geometry.artifacts(p,artifact_dir,store)
            (scene if i<len(design.parts) else cell_scene).append(mesh)
            checks[p.id]=check;blobs[p.id]=refs
        write_json(run/'geometry-checks.json',checks)
        write_json(run/'reuse.json',{'parent':request.parent,'reused':reused,
            'rebuilt':[p.id for p in design.parts+equipment if p.id not in reused],
            **({'asset':asset_reuse_record} if asset_reuse_record is not None else {})})
        write_json(run/'scene.json',{'product':scene,'equipment':cell_scene})
        plan=manufacturing.make_plan(design,equipment,checks,request.equipment_depth,image_hash,manufacturing.digest(input_record))
        write_json(run/'manufacturing.json',plan)
        event('formal','Lean 4 正在检查当前计划的闭合、设备启动顺序与展开深度')
        proof=manufacturing.prove(plan,run)
        fk=None
        if not manufacturing.validate(plan):
            event('integrity','将生产边与证据写入 FluxKernel 内容寻址存储，复检对象与连接')
            fk=manufacturing.persist_fk(plan,store,checks,blobs)
            write_json(run/'fluxkernel.json',fk)
        # A checked route graph remains conditional on physical assumptions.
        gaps=list(design.unresolved)
        if perception['quality_status']!='model-threshold-met':
            gaps.append('外观质量尚未通过视觉评审门槛；Lean通过不代表图片重构质量合格')
        gaps.extend(['标准件型号与布局包络尚需供应商资料核实',
            '打印局部厚度、支撑、材料性能与后加工精度尚需验证',
            '加工设备为参数化概念方案，未验证实际刚度、行程与加工能力'])
        result={'id':run.name,'title':design.title,'family':design.family,'summary':design.summary,
            'model':model,'proof':proof,'fluxkernel':fk,'design':design.model_dump(),
            'equipment':[p.model_dump() for p in equipment],
            'counts':{'parts':len(design.parts),'equipment_parts':len(equipment),
                'catalog':sum(p.route=='catalog' for p in design.parts+equipment),
                'print':sum(p.route=='print' for p in design.parts+equipment),
                'machine':sum(p.route=='machine' for p in design.parts),
                'steps':len(plan['steps'])},
            'status':('needs-review' if perception['enabled'] and perception['quality_status']=='needs-review' else 'conditional-closure') if proof['accepted'] else 'open',
            'perception':perception,
            'physical_status':'unverified','gaps':list(dict.fromkeys(gaps)),
            'constraints':constraint_report,
            'duration_s':round(time.monotonic()-start,2),'image_sha256':image_hash,
            'parent':request.parent,'geometry_reused':len(reused)}
        write_json(run/'result.json',result)
        evidence=run/'formal/FluxKernel';evidence.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(manufacturing.ROOT/'scripts/verify_demo_bundle.py',run/'verify.py')
        (run/'constraint_checker.py').write_bytes(constraint_checker_source)
        (run/'README.txt').write_text('FluxKernel conditional manufacturing plan\n'
            'Extract this ZIP, install elan/Lean, then run: python verify.py\n'
            'STEP/STL files are concept geometry; catalog parts are envelopes and machined parts are blanks.\n'
            'A passing Lean check verifies the finite plan, not physical performance or supplier authenticity.\n'
            'model-response-*.json is the actual API output; model-request-*.json records prompts without credentials.\n')
        manifest={str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in run.rglob('*') if p.is_file() and p.name not in ('status.json','manifest.json')
            and '.lake' not in p.relative_to(run).parts}
        write_json(run/'manifest.json',manifest)
        events.append({'stage':'complete','message':('候选方案已保存；外观仍需改进，制造计划单独检查' if perception['enabled'] and perception['quality_status']=='needs-review' else '条件化制造路线已通过检查') if proof['accepted'] else '方案已生成，检查发现未闭合项',
                       'elapsed_s':round(time.monotonic()-start,1)})
        write_json(run/'status.json',{'id':run.name,'state':'complete','events':events,'stage':'complete'})
    except Exception as exc:
        # Never store headers, keys, or a raw HTTP request in public artifacts.
        message=str(exc)
        try: cfg=vision.model_config()
        except (ValueError,OSError,TypeError): cfg={}
        if cfg.get('api_key'): message=message.replace(cfg['api_key'],'[REDACTED]')
        write_json(run/'status.json',{'id':run.name,'state':'failed','stage':'failed',
            'error':message[:2000],'events':events})
