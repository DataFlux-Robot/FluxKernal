"""Cross-product recipe reuse with explicit compatibility and evidence invalidation.

No models are called. Compatibility is conditional on declared capability data,
not a supplier/physical certification. Old application proofs are never inherited.
"""
from __future__ import annotations
import copy
import json
import math
import re
from pathlib import Path
from .revision import snapshot,read_json,sha,RevisionError
from .asset_models import Publish,Instance,Query

EMPTY={'schema':'fk-constraints-v1','rules':[]}
UNITS={'mm':('length',1),'cm':('length',10),'m':('length',1000),
       'N':('force',1),'kN':('force',1000),'Nm':('torque',1),'Nmm':('torque',.001),
       'V':('voltage',1),'mV':('voltage',.001),'A':('current',1),'mA':('current',.001),
       'kg':('mass',1),'g':('mass',.001),'W':('power',1),'kW':('power',1000),
       'rpm':('speed',1),'C':('temperature',1),'1':('dimensionless',1)}
PART_REFS={'dimension':('part',),'inside-shell':('container','item'),
           'radial-fit':('shaft','sleeve'),'axis-distance':('first','second')}


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(value):return sha(canonical(value))
def get_field(part,field):
    if field=='wall':return part[field]
    key,index=field.split('.');return part[key][int(index)]
def set_field(part,field,value):
    if field=='wall':part[field]=value
    else:
        key,index=field.split('.');part[key][int(index)]=value


class AssetLibrary:
    def __init__(self,directory):self.root=Path(directory).expanduser().absolute()
    def _check_root(self):
        if self.root.is_symlink():raise ValueError('Asset library cannot be a symlink')
    def read(self,identity):
        self._check_root()
        if not re.fullmatch('[a-f0-9]{64}',identity):raise ValueError('Asset identity must be SHA-256')
        path=self.root/(identity+'.json')
        if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError('Invalid asset file')
        raw=path.read_bytes()
        if sha(raw)!=identity:raise ValueError('Asset content hash mismatch')
        data=json.loads(raw)
        if data.get('schema')!='fk-design-asset-v1':raise ValueError('Unsupported asset schema')
        return data
    def put(self,record):
        self._check_root();self.root.mkdir(parents=True,exist_ok=True)
        raw=canonical(record)
        if len(raw)>2*1024*1024:raise ValueError('Asset exceeds the 2 MiB entry limit')
        identity=sha(raw);path=self.root/(identity+'.json')
        # Atomic publication: readers see either a complete entry or no entry.
        import os,tempfile
        fd,temp=tempfile.mkstemp(dir=self.root,prefix='.asset-')
        try:
            with os.fdopen(fd,'wb') as f:f.write(raw)
            try:os.link(temp,path)
            except FileExistsError:self.read(identity)
        finally:Path(temp).unlink(missing_ok=True)
        return identity
    def entries(self):
        self._check_root()
        for p in sorted(self.root.glob('*.json')):
            if re.fullmatch('[a-f0-9]{64}',p.stem):yield p.stem,self.read(p.stem)
    def search(self,query,limit=20):
        q=Query.model_validate(query)
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('Limit must be 1..100')
        rows=[]
        for ident,asset in self.entries():
            if asset['definition']['category']!=q.category:continue
            result=assess(asset,q.model_dump())
            rows.append({'asset_sha256':ident,'name':asset['definition']['name'],'version':asset['definition']['version'],
                         'source_family':asset['source']['family'],**result})
        rows.sort(key=lambda r:({'compatible':0,'needs-evidence':1,'incompatible':2}[r['status']],r['asset_sha256']))
        return {'matches':rows[:limit],'total':len(rows),'truncated':len(rows)>limit,
                'scope':'Declared interfaces/capabilities and nominal geometry only; no physical qualification'}


def publish(library,source,request):
    from .demo.models import Part
    spec=Publish.model_validate(request);snap=snapshot(source,spec.base_manifest_sha256)
    design=read_json(snap,'design.json');equipment=read_json(snap,'equipment.json')
    pool=equipment if spec.kind=='equipment' else design['parts'];lookup={p['id']:p for p in pool}
    selected=set(spec.parts)
    if len(selected)!=len(spec.parts) or not selected<=lookup.keys():raise ValueError('Select unique existing parts from the declared product/equipment pool')
    if spec.kind=='equipment' and selected!=lookup.keys():raise ValueError('Equipment assets must capture the complete recorded cell recipe')
    if spec.kind=='component' and len(selected)!=1:raise ValueError('A component has exactly one occurrence')
    parts=[copy.deepcopy(lookup[i]) for i in spec.parts]
    for p in parts:p['position']=[v-o for v,o in zip(p['position'],spec.origin)]
    lookup={p['id']:p for p in parts};controlled=set()
    for name,par in spec.parameters.items():
        for b in par.bindings:
            if b.part not in lookup:raise ValueError('Parameter references a part outside the asset')
            p=lookup[b.part]
            if p['route']=='catalog' and not b.field.startswith('position.'):raise ValueError('Catalog dimensions are immutable')
            if p.get('parametric') and b.field.startswith('size.'):raise ValueError('Semantic envelopes cannot be resized independently')
            if (b.part,b.field) in controlled:raise ValueError('Each field may have only one parameter driver')
            controlled.add((b.part,b.field))
            if not math.isclose(get_field(p,b.field),par.default*b.factor+b.offset,abs_tol=1e-7,rel_tol=1e-9):raise ValueError('Parameter default does not reproduce the source recipe')
    if set(spec.capabilities)&set(spec.measures):raise ValueError('Declared and measured properties cannot share a name')
    for measure in spec.measures.values():
        if measure.part not in lookup:raise ValueError('Measure references unknown asset part')
        if measure.field=='wall' and lookup[measure.part]['shape'] not in ('shell','tube','frame'):raise ValueError('No uniform-wall measurement exists for this recipe')
    for fact in spec.capabilities.values():
        if fact.unit not in UNITS:raise ValueError('Unsupported capability unit')
    for p in parts:Part.model_validate(p)
    # Preserve closed nominal relationships; explicitly expose boundary obligations.
    internal=[];boundary=[]
    contract=read_json(snap,'constraints.json') if 'constraints.json' in snap['files'] else EMPTY
    if spec.kind!='equipment':
        for rule in contract['rules']:
            if rule['kind']=='asset-frame':
                # Existing instantiated assets retain their original framed contract.
                if set(rule['parts'])&selected:boundary.append({'kind':'prior-asset-frame-rebind','rule':rule})
                continue
            refs={rule[k] for k in PART_REFS[rule['kind']]}
            if refs<=selected:internal.append(rule)
            elif refs&selected:boundary.append({'kind':'nominal-constraint','rule':rule})
    assembly=design.get('assembly') if spec.kind!='equipment' else None
    if assembly:
        for body in assembly['bodies']:
            refs={m['part'] for m in body['members']}
            if refs&selected and not refs<=selected:raise ValueError('Select the whole shared body group; partial partitions are not standalone templates')
        # Geometry snapshot and relations are separate: dynamic drivers need explicit rebinding.
        for key in ('bodies','attachments','alignments'):
            for rule in assembly[key]:
                refs={m['part'] for m in rule['members']} if key=='bodies' else {rule['parent'],rule['child']} if key=='attachments' else {rule['part']}
                if refs&selected:boundary.append({'kind':'assembly-driver-rebind','type':key,'rule':rule})
    record={'schema':'fk-design-asset-v1','definition':spec.model_dump(),'parts':parts,
            'constraints':{'schema':'fk-constraints-v1','rules':internal},'integration_obligations':boundary,
            'source':{'manifest_sha256':snap['identity'],'family':design['family'],'title':design['title'],
                      'part_recipe_sha256':{i:digest(next(p for p in pool if p['id']==i)) for i in spec.parts}},
            'evidence':{'capabilities':'publisher-declared','geometry':'source run content-verified',
                        'physical_status':'unverified','old_proof_inherited':False,
                        'adaptation_range':'publisher-declared, not a physically validated envelope'}}
    identity=library.put(record)
    return {'asset_sha256':identity,'name':spec.name,'version':spec.version,'parts':len(parts),'physical_status':'unverified'}


def adapted_parts(asset,parameters):
    from .demo.models import Part
    spec=Publish.model_validate(asset['definition']);parts=copy.deepcopy(asset['parts']);lookup={p['id']:p for p in parts}
    if not parameters.keys()<=spec.parameters.keys():raise ValueError('Unknown adaptation parameter')
    changed=False
    for name,par in spec.parameters.items():
        value=parameters.get(name,par.default)
        if type(value) not in (int,float) or not math.isfinite(value) or not par.min<=value<=par.max:raise ValueError('Adaptation parameter out of bounds: '+name)
        changed|=value!=par.default
        for b in par.bindings:
            if lookup[b.part]['route']=='catalog' and not b.field.startswith('position.'):raise ValueError('Catalog dimensions are immutable')
            set_field(lookup[b.part],b.field,value*b.factor+b.offset)
    if changed and any(o['kind'] in ('assembly-driver-rebind','prior-asset-frame-rebind') for o in asset['integration_obligations']):
        raise ValueError('Adaptation requires explicit rebinding of inherited assembly/frame drivers')
    for p in parts:Part.model_validate(p)
    from .demo.constraints import evaluate
    checks=evaluate({'parts':parts},asset['constraints'])
    if not checks['accepted']:raise ValueError('Adaptation violates preserved asset nominal constraints')
    return parts,changed


def assess(asset,query,parameters=None):
    q=Query.model_validate(query);spec=Publish.model_validate(asset['definition']);parts,changed=adapted_parts(asset,parameters or {})
    props={} if changed else {k:v.model_dump() for k,v in spec.capabilities.items()}
    lookup={p['id']:p for p in parts}
    for name,m in spec.measures.items():
        value=get_field(lookup[m.part],m.field);props[name]={'unit':m.unit,'min':value,'max':value}
    issues=[]
    if q.category!=spec.category:issues.append({'code':'category-mismatch','status':'incompatible'})
    for name,req in q.requirements.items():
        value=props.get(name)
        if value is None:
            issues.append({'code':'missing-or-invalidated-property','property':name,'status':'needs-evidence'});continue
        if req.unit not in UNITS or value['unit'] not in UNITS or UNITS[req.unit][0]!=UNITS[value['unit']][0]:
            issues.append({'code':'unit-mismatch','property':name,'status':'incompatible'});continue
        factor=UNITS[value['unit']][1]/UNITS[req.unit][1];lo=value['min']*factor;hi=value['max']*factor
        eps=1e-9*max(1,abs(lo),abs(hi),abs(req.min),abs(req.max))
        ok=(lo<=req.min+eps and hi>=req.max-eps) if req.relation=='covers' else (lo>=req.min-eps and hi<=req.max+eps)
        if not ok:issues.append({'code':'range-not-contained','property':name,'status':'incompatible','actual':{'unit':req.unit,'min':lo,'max':hi},'required':req.model_dump()})
    for name,value in q.interfaces.items():
        actual=spec.interfaces.get(name) if not changed else None
        if actual is None:issues.append({'code':'missing-or-invalidated-interface','interface':name,'status':'needs-evidence'})
        elif actual!=value:issues.append({'code':'interface-mismatch','interface':name,'status':'incompatible'})
    status='incompatible' if any(i['status']=='incompatible' for i in issues) else 'needs-evidence' if issues else 'compatible'
    return {'status':status,'reuse_mode':'adapted-recipe' if changed else 'direct-recipe','issues':issues,
            'properties':props,'invalidated_evidence':(['declared-capabilities','declared-interfaces'] if changed else [])+['source-application-proof','source-visual-acceptance'],
            'integration_obligations':asset['integration_obligations'],'physical_status':'unverified'}


def prepare_instance(library,target,request):
    from .demo.models import Design,Part
    from .demo.constraints import evaluate
    from scipy.spatial.transform import Rotation
    import numpy as np
    req=Instance.model_validate(request);snap=snapshot(target,req.base_manifest_sha256);asset=library.read(req.asset_sha256)
    check=assess(asset,req.query.model_dump(),req.parameters)
    report={'schema':'fk-asset-preview-v1','accepted':False,'asset_sha256':req.asset_sha256,'base_manifest_sha256':snap['identity'],**check}
    if check['status']!='compatible':return report,snap,None,None,None
    if (asset['definition']['kind']=='equipment')!=(req.destination=='equipment'):raise ValueError('Equipment assets require the equipment destination; product assets require product destination')
    parts,_=adapted_parts(asset,req.parameters);original=read_json(snap,'design.json');design=copy.deepcopy(original)
    equipment=read_json(snap,'equipment.json');pool=equipment if req.destination=='equipment' else design['parts']
    if req.destination=='equipment':
        if req.replace:raise ValueError('Equipment replaces the whole cell; individual replacement map is not supported')
        if read_json(snap,'manufacturing.json')['policy']['equipment_depth']!=1:raise ValueError('Target policy does not permit an equipment generation')
        machines=[p for p in design['parts'] if p['route']=='machine']
        if not machines:raise ValueError('Target has no machining requirement')
        # These are recipe-axis envelope assumptions, never a setup/rigidity proof.
        auto={'category':req.query.category,'requirements':{f'work_{axis}':{'unit':'mm','min':0,'max':max(p['size'][i] for p in machines),'relation':'covers'} for i,axis in enumerate('xyz')}}
        capacity=assess(asset,auto,req.parameters);report['equipment_capacity']=capacity
        if capacity['status']!='compatible':report.update(status=capacity['status'],issues=report['issues']+capacity['issues']);return report,snap,None,None,None
    source_ids={p['id'] for p in parts};target_ids={p['id'] for p in pool}
    if not req.replace.keys()<=source_ids or not set(req.replace.values())<=target_ids or len(set(req.replace.values()))!=len(req.replace):raise ValueError('Replacement maps unique source parts to existing destination IDs')
    mapping={p['id']:req.replace.get(p['id'],req.prefix+'-'+p['id']) for p in parts}
    remaining=[p for p in pool if p['id'] not in req.replace.values()] if req.destination=='product' else []
    occupied={p['id'] for p in remaining}|({p['id'] for p in design['parts']} if req.destination=='equipment' else {p['id'] for p in equipment})
    if len(set(mapping.values()))!=len(mapping) or occupied&set(mapping.values()):raise ValueError('Asset namespace collides with destination occurrences')
    if req.replace and original.get('assembly'):
        # Avoid silently breaking a driven occurrence's anchors/whole-body profile.
        asm=original['assembly'];driven={m['part'] for b in asm['bodies'] for m in b['members']}|{p for a in asm['attachments'] for p in (a['parent'],a['child'])}|{a['part'] for a in asm['alignments']}
        if driven&set(req.replace.values()):raise ValueError('Replacement touches assembly drivers; rebind the assembly explicitly before replacing')
    rotation=Rotation.from_euler('xyz',req.rotation,degrees=True)
    for p in parts:
        p['id']=mapping[p['id']];p['group']=req.prefix+' / '+p['group']
        p['position']=(rotation.apply(p['position'])+np.array(req.position)).tolist()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            p['rotation']=(rotation*Rotation.from_euler('xyz',p['rotation'],degrees=True)).as_euler('xyz',degrees=True).tolist()
        p['source']='selected';Part.model_validate(p)
    contract=read_json(snap,'constraints.json') if 'constraints.json' in snap['files'] else copy.deepcopy(EMPTY)
    asset_rules=[]
    for rule in asset['constraints']['rules']:
        r=copy.deepcopy(rule);r['id']=req.prefix+'-'+r['id']
        for key in PART_REFS[r['kind']]:r[key]=mapping[r[key]]
        asset_rules.append(r)
    if req.destination=='product':
        design['parts']=remaining+parts;design=Design.model_validate(design).model_dump()
        frame={'id':req.prefix+'-asset-contract','kind':'asset-frame','position':req.position,'rotation':req.rotation,'parts':list(mapping.values()),'rules':asset_rules}
        contract=copy.deepcopy(contract)
        if asset_rules:contract['rules'].append(frame)
        checks=evaluate(design,contract);internal=evaluate(design,{'schema':EMPTY['schema'],'rules':[frame]})
    else:
        checks=evaluate(design,contract);internal=evaluate({'parts':parts},{'schema':EMPTY['schema'],'rules':asset_rules});equipment=parts
        if not {'print','catalog'}<={p['route'] for p in equipment} or any(p['route']=='machine' for p in equipment):raise ValueError('Equipment closure requires printed and purchased constituents, without recursive machining')
    report.update(accepted=checks['accepted'] and internal['accepted'],target_checks=checks,asset_checks=internal,
                  mapping=mapping,new_occurrences=len(parts),source_family=asset['source']['family'],target_family=design['family'],
                  proof_reused=False,cad_policy='Rebuild imported CAD in destination coordinates; retain exact unchanged target CAD only')
    if not report['accepted']:
        report['status']='incompatible'
        report['issues'] += [{'code':'nominal-constraint-failed','scope':scope,'constraint':c['id'],'detail':c['detail'],'status':'incompatible'}
                             for scope,result in [('target',checks),('asset',internal)] for c in result['checks'] if not c['passed']]
    return report,snap,design,contract,equipment if req.destination=='equipment' else None
