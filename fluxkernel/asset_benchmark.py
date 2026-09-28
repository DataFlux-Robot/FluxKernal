"""Authored cross-product subsystem regression; no whole-product/image claims."""
import json
import subprocess
import sys
import time
from pathlib import Path
from .assets import AssetLibrary,publish,prepare_instance
from .revision import snapshot,read_json
from .studio import _new_run,_worker,_result,apply_asset

FAMILIES=('car','truck','aircraft','humanoid')

def fixture(family):
    if family not in FAMILIES:raise ValueError('Unknown asset fixture family')
    from .demo.models import Part,Design
    width={'car':40,'truck':100,'aircraft':36,'humanoid':32}[family]
    parts=[Part(id='control',name='Example auxiliary controller',group='Auxiliary electronics',route='catalog',shape='box',size=[50,30,12],position=[0,0,25],material='catalog',catalog_ref='EXAMPLE-24V-CAN: authored test envelope, not a supplier part'),
           Part(id='bracket',name='Mounting blank',group='Mounting',route='machine',shape='box',size=[width,24,6],position=[0,0,0],material='aluminum'),
           Part(id='shaft',name='Nominal shaft',group='Mounting',route='print',shape='cylinder',size=[10,10,40],position=[50,0,0],material='steel')]
    design=Design(title=family+' subsystem reuse fixture',family=family,summary='Authored subsystem context for testing shared assets; not a complete vehicle/robot or image reconstruction.',
        observations=[{'text':'Geometry and capabilities are authored regression data.','source':'selected'}],
        assumptions=['All capability intervals are declared test data, not measured or supplier-qualified.'],
        requirements=['Retain nominal mounting dimensions and target identities.'],parts=parts,
        unresolved=['Physical integration, load cases, supplier data and domain qualification remain unverified.'])
    contract={'schema':'fk-constraints-v1','rules':[
        {'id':'blank-thickness','kind':'dimension','part':'bracket','measure':'size.z','min':4,'max':10},
        {'id':'shaft-diameter','kind':'dimension','part':'shaft','measure':'size.x','min':8,'max':20},
        {'id':'mount-separation','kind':'axis-distance','first':'bracket','second':'shaft','axis':'x','min':50,'max':50}]}
    return {'design':design.model_dump(),'constraints':contract}

def generate_fixture(family,output):
    run=_new_run(output,300);_worker(run,['--asset-fixture',family],300);return _result(run)

def run_asset_benchmark(output):
    root=Path(output).expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    # Every invocation has an isolated campaign; no results are overwritten.
    import uuid
    root=root/('assets-'+uuid.uuid4().hex[:8]);root.mkdir()
    lib=AssetLibrary(root/'library');started=time.monotonic();bases={f:generate_fixture(f,root/'runs') for f in FAMILIES}
    source=Path(bases['car'].directory);snap=snapshot(source)
    def publish_spec(name,parts,category,**kw):
        return publish(lib,source,{'base_manifest_sha256':snap['identity'],'name':name,'version':'1.0.0','category':category,'description':'Authored cross-product subsystem test data','parts':parts,**kw})['asset_sha256']
    control=publish_spec('aux-control',['control'],'aux-control',kind='component',origin=[0,0,25],capabilities={'voltage':{'unit':'V','min':18,'max':30}},interfaces={'bus':'example-can-v1'})
    shaft=publish_spec('shaft-template',['shaft'],'shaft',kind='component',origin=[50,0,0],
        parameters={'diameter':{'default':10,'min':8,'max':20,'bindings':[{'part':'shaft','field':'size.0'},{'part':'shaft','field':'size.1'}]}},
        measures={'diameter':{'part':'shaft','field':'size.0'}},capabilities={'torque':{'unit':'Nm','min':0,'max':50}})
    module=publish_spec('mount-module',['bracket','shaft'],'mount-module')
    cell=publish_spec('cell-recipe',[p['id'] for p in read_json(snap,'equipment.json')],'drill-mill-cell',kind='equipment',
        capabilities={f'work_{a}':{'unit':'mm','min':0,'max':n} for a,n in zip('xyz',(40,24,6))})
    rows=[]
    def exercise(label,family,identity,query,expected=True,**kw):
        target=Path(bases[family].directory);before=snapshot(target)['identity']
        req={'base_manifest_sha256':before,'asset_sha256':identity,'prefix':'shared','query':query,**kw}
        preview=prepare_instance(lib,target,req)[0]
        result=apply_asset(target,lib.root,req,output_dir=root/'runs')
        tests={'expected_preview':preview['accepted']==expected,'expected_execution':result['ok']==expected,'parent_unchanged':snapshot(target)['identity']==before}
        if expected:
            child=Path(result['directory']);after=snapshot(child);design=read_json(after,'design.json')
            tests['target_family_retained']=design['family']==family
            tests['requirements_retained']=design['requirements']==read_json(snapshot(target),'design.json')['requirements']
            tests['new_lean_proof']=result['run']['proof_accepted'] and read_json(after,'proof.json')['plan_sha256']!=read_json(snapshot(target),'proof.json')['plan_sha256']
            checked=subprocess.run([sys.executable,str(child/'verify.py'),str(child)],capture_output=True,text=True,timeout=180)
            tests['independent_verifier']=checked.returncode==0
            (root/(label+'-verify.txt')).write_text(checked.stdout+checked.stderr)
        else:tests['no_rejected_cad']=not (Path(result['directory'])/'cad').exists()
        rows.append({'label':label,'target_family':family,'accepted':all(tests.values()),'checks':tests,'preview':preview,'run':result})
    q={'category':'aux-control','requirements':{'voltage':{'unit':'mV','min':24000,'max':28000}},'interfaces':{'bus':'example-can-v1'}}
    for family in ('truck','aircraft','humanoid'):
        exercise('control-to-'+family,family,control,q,replace={'control':'control'},position=[0,0,25])
    exercise('adapt-shaft-to-humanoid','humanoid',shaft,{'category':'shaft','requirements':{'diameter':{'unit':'mm','min':16,'max':16,'relation':'within'}}},parameters={'diameter':16},replace={'shaft':'shaft'},position=[50,0,0])
    exercise('rotated-module-to-aircraft','aircraft',module,{'category':'mount-module'},position=[0,100,50],rotation=[0,0,90])
    exercise('equipment-to-humanoid','humanoid',cell,{'category':'drill-mill-cell'},destination='equipment')
    exercise('reject-undersized-cell','truck',cell,{'category':'drill-mill-cell'},expected=False,destination='equipment')
    exercise('reject-high-voltage','truck',control,{'category':'aux-control','requirements':{'voltage':{'unit':'V','min':400,'max':800}}},expected=False)
    exercise('reject-stale-torque','humanoid',shaft,{'category':'shaft','requirements':{'torque':{'unit':'Nm','min':0,'max':30}}},parameters={'diameter':16},expected=False)
    result={'schema':'fk-asset-benchmark-v1','accepted':all(r['accepted'] for r in rows),'cases':rows,'baselines':{k:v.to_dict() for k,v in bases.items()},
            'assets':{'controller':control,'shaft':shaft,'mount_module':module,'equipment':cell},'model_calls':0,'elapsed_s':round(time.monotonic()-started,2),
            'scope':'Four authored subsystem contexts, not whole-product designs. Declared compatibility, geometry and fresh plan proofs; no physical qualification.'}
    path=root/'benchmark.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2));return {**result,'report_path':str(path)}
