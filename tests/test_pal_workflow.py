"""Rules/workflow invariants; providers below are explicitly mocked, never live."""
import copy
import io
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from fluxkernel.demo.models import Part,Design,Request
from fluxkernel.demo.parametric import WingParameters,BodyParameters,envelope
from fluxkernel.demo.pal_rules import validate_plan,compile_symmetry,apply_workflow_action,parameter_facts
from fluxkernel.demo import perception as pal
from fluxkernel.demo import pal_workflow as workflow
from fluxkernel.demo.geometry import build,artifacts
from fluxkernel.studio import load_task

EMPTY={'schema':'fk-constraints-v1','rules':[]}

def plain_plan():
    return {'symmetry':'uncertain','axis':'y','plane_offset':0,'confidence':.3,'rationale':'Insufficient image evidence',
            'visible_evidence':['Only one surface is visible'],'exceptions':[],'pairs':[],'parameterization':[],'stages':['proportions','connections']}

def pair_design():
    d=Design.model_validate(load_task('enclosure')['design'])
    base={'name':'Wing','group':'wings','route':'print','shape':'wing','size':[50,80,4],
          'position':[10,60,25],'rotation':[12,8,27],'wall':1,'material':'petg'}
    d.parts=[Part(id='source',**base),Part(id='target',**{**base,'position':[10,-50,25]}),d.parts[1]]
    return d

def paired(d=None):
    p=plain_plan();p.update(symmetry='partial',confidence=.8,pairs=[{'source':'source','target':'target'}],
                           parameterization=[{'part':'source','kind':'wing'}])
    return validate_plan(p,d or pair_design())

def wing():return WingParameters(span=80,root_chord=50,tip_chord=20,sweep_deg=23,dihedral_deg=6,twist_deg=-4,thickness_ratio=.12)

def image():
    b=io.BytesIO();Image.new('RGB',(30,30),'white').save(b,'PNG');return b.getvalue()

def review(design,score=65):
    p=design.parts[0]
    return {'silhouette':score,'proportions':score,'layout':score,'reference_limitations':'Mock review',
            'findings':[] if score>=80 else [{'severity':'major','parts':[p.id],'observation':'Mock visible problem','suggested_change':'Change wall'}],
            'numeric_claims':[{'part':p.id,'field':'wall','value':p.wall}]}

def decision(index=0,step='revise'):return {'selected_round':index,'next_step':step,'stage':'proportions','reason':'Mock GLM selection'}

def provider(monkeypatch,responses):
    calls=[]
    monkeypatch.setattr(pal.vision,'model_config',lambda:{'model':workflow.MODEL,'api_key':'private-test-key'})
    def call(cfg,messages,schema,event):
        calls.append({'messages':messages,'schema':schema})
        value=responses.pop(0)
        if isinstance(value,Exception):raise value
        if callable(value):value=value(messages)
        return json.dumps(value),{'model':workflow.MODEL,'usage':{'input_tokens':1,'output_tokens':1},'content':[]}
    monkeypatch.setattr(pal.vision,'_call',call);return calls


def test_old_recipe_dump_preserves_bundle_identity():
    raw=load_task('enclosure')['design'];d=Design.model_validate(raw)
    assert all('parametric' not in p and 'reflection' not in p for p in d.model_dump()['parts'])
    assert d==Design.model_validate(d.model_dump())

@pytest.mark.parametrize('axis',['x','y','z'])
def test_mirror_is_actual_world_reflection_with_rotations(axis):
    from fluxkernel.demo.perception_render import mesh_design
    from scipy.spatial import cKDTree
    d=pair_design();p=plain_plan();p.update(symmetry='partial',axis=axis,plane_offset=7,pairs=[{'source':'source','target':'target'}])
    compiled=compile_symmetry(d,validate_plan(p,d),EMPTY)
    meshes=mesh_design(compiled);a=meshes[0]['triangles'].reshape(-1,3).copy();b=meshes[1]['triangles'].reshape(-1,3)
    a[:,'xyz'.index(axis)]=14-a[:,'xyz'.index(axis)]
    assert cKDTree(b).query(a)[0].max()<1e-6
    assert compiled.parts[1].id=='target' and compiled.parts[1].route==d.parts[1].route


def test_unknown_symmetry_does_not_change_geometry():
    d=pair_design();assert compile_symmetry(d,validate_plan(plain_plan(),d),EMPTY)==d

@pytest.mark.parametrize('mutation',['cycle','unknown','exception','catalog'])
def test_invalid_symmetry_plan_rejected(mutation):
    d=pair_design();p=paired(d).model_dump()
    if mutation=='cycle':p['pairs'].append({'source':'target','target':'source'})
    if mutation=='unknown':p['pairs'][0]['target']='missing'
    if mutation=='exception':p['exceptions']=['target']
    if mutation=='catalog':d.parts[1].route='catalog';d.parts[1].catalog_ref='example'
    with pytest.raises(ValueError):validate_plan(p,d)


def test_parameter_action_drives_both_real_wings_and_protects_targets(tmp_path):
    from fluxkernel.store.objstore import Store
    d=pair_design();p=paired(d)
    a={'base_design_sha256':pal.digest(d.model_dump()),'rationale':'Mock wing controls',
       'edits':[{'part':'source','set':{'parametric':wing().model_dump(),'position':[10,4,25],'rotation':[0,0,0]}}]}
    result=apply_workflow_action(d,a,EMPTY,p)
    assert result.parts[0].parametric==result.parts[1].parametric==wing()
    assert result.parts[0].size==envelope(wing()) and result.parts[1].position==[10,-4,25]
    for part in result.parts[:2]:
        _,checks,refs=artifacts(part,tmp_path,Store(tmp_path/'.fk'));assert checks['valid_brep'] and checks['solid_count']==1 and set(refs)=={'step','stl'}
    a['edits'][0]['part']='target'
    with pytest.raises(ValueError,match='targets'):apply_workflow_action(d,a,EMPTY,p)


def test_catalog_pair_preserves_specification_and_geometry():
    d=pair_design()
    for part in d.parts[:2]:part.route='catalog';part.catalog_ref=part.id+'-SKU';part.shape='box'
    p=plain_plan();p.update(symmetry='partial',pairs=[{'source':'source','target':'target'}])
    result=compile_symmetry(d,validate_plan(p,d),EMPTY)
    for before,after in zip(d.parts,result.parts):
        assert before.size==after.size and before.catalog_ref==after.catalog_ref and after.reflection is None


def test_section_body_controls_geometry_and_rejects_unsorted_sections(tmp_path):
    from fluxkernel.store.objstore import Store
    p=BodyParameters(length=300,sections=[{'u':u,'width':w,'height':h,'offset_y':0,'offset_z':z} for u,w,h,z in [(0,4,4,0),(.5,60,70,4),(1,8,8,0)]])
    part=Part(id='body',name='Body',group='body',route='print',shape='section_body',size=envelope(p),position=[0,0,0],parametric=p)
    _,checks,_=artifacts(part,tmp_path,Store(tmp_path/'.fk'));assert checks['valid_brep'] and checks['solid_count']==1
    raw=p.model_dump();raw['sections'].reverse()
    with pytest.raises(ValueError):BodyParameters.model_validate(raw)


def test_numeric_review_rejects_stale_values():
    d=pair_design();r=review(d);r['numeric_claims']=[{'part':'source','field':'size.0','value':15500}]
    with pytest.raises(ValueError,match='Fact mismatch'):workflow.validate_review(r,d)
    r['numeric_claims'][0]['value']=50;assert workflow.validate_review(r,d)


def test_workflow_glm_selects_over_higher_score_and_skill_is_in_every_phase(tmp_path,monkeypatch):
    d=Design.model_validate(load_task('enclosure')['design']);changed=d.model_copy(deep=True);changed.parts[0].wall=3
    a={'base_design_sha256':pal.digest(d.model_dump()),'rationale':'Mock edit','edits':[{'part':d.parts[0].id,'set':{'wall':3}}]}
    calls=provider(monkeypatch,[plain_plan(),review(d),decision(),a,review(changed,90),decision(0,'stop')])
    result,s=pal.run_loop(d,image(),'brief',tmp_path,lambda *a:None,contract=load_task('enclosure')['constraints'],rounds=2)
    assert result==d and s['selected_round']==0 and s['model_calls']==6 and s['decision_author']==workflow.MODEL
    assert s['quality_status']=='needs-review' and s['stop_reason']=='model-stop'
    assert all('GLM-only perception' in c['messages'][0]['content'] for c in calls)
    assert 'changed' in calls[4]['messages'][1]['content']
    assert (tmp_path/'perception/round-01/retained-comparison/views.png').exists()
    assert len(calls[4]['messages'][1]['images'])==3
    assert all(c['reported_model']==workflow.MODEL for c in s['calls'])


def test_invalid_review_gets_model_repair_and_no_synthetic_score(tmp_path,monkeypatch):
    d=Design.model_validate(load_task('enclosure')['design']);bad=review(d);bad['numeric_claims'][0]['value']=9999
    calls=provider(monkeypatch,[plain_plan(),bad,review(d,90),decision(0,'stop')])
    _,s=pal.run_loop(d,image(),'brief',tmp_path,lambda *a:None,contract=EMPTY,rounds=1)
    assert s['quality_status']=='model-threshold-met' and s['model_calls']==4
    assert 'Fact mismatch' in calls[2]['messages'][1]['content']
    assert (tmp_path/'perception/round-00/review-rejected.json').exists()


def test_wrong_model_is_refused_without_calls(tmp_path,monkeypatch):
    d=Design.model_validate(load_task('enclosure')['design'])
    monkeypatch.setattr(pal.vision,'model_config',lambda:{'model':'other-model'})
    with pytest.raises(ValueError,match='requires'):pal.run_loop(d,image(),'brief',tmp_path,lambda *a:None,contract=EMPTY)
    assert not (tmp_path/'perception').exists()


def test_failure_is_archived_without_host_repair(tmp_path,monkeypatch):
    d=Design.model_validate(load_task('enclosure')['design']);provider(monkeypatch,[RuntimeError('failure private-test-key')])
    selected,s=pal.run_loop(d,image(),'brief',tmp_path,lambda *a:None,contract=EMPTY)
    assert selected==d and s['selected_round'] is None and not s['reviewed']
    assert s['stop_reason']=='workflow-failed' and s['quality_status']=='needs-review'
    assert 'private-test-key' not in (tmp_path/'perception/summary.json').read_text()


def test_default_live_pipeline_uses_rule_workflow(tmp_path,monkeypatch):
    from fluxkernel.demo.pipeline import execute
    d=Design.model_validate(load_task('enclosure')['design'])
    provider(monkeypatch,[plain_plan(),review(d,85),decision(0,'stop')])
    monkeypatch.setattr(pal.vision,'plan',lambda *a:(d,{'mode':'live','model':workflow.MODEL,'attempts':1}))
    execute(tmp_path,Request(mode='live',visual_rounds=1),image())
    result=json.loads((tmp_path/'result.json').read_text());s=result['perception']
    assert s['workflow']=='glm-assembly-parametric-v2' and s['model_calls']==3
    assert 'perception/skill.md' in json.loads((tmp_path/'manifest.json').read_text())


def test_model_repairs_its_own_invalid_declaration(tmp_path,monkeypatch):
    d=Design.model_validate(load_task('enclosure')['design']);invalid=plain_plan();invalid.update(symmetry='bilateral',pairs=[{'source':'housing','target':'missing'}])
    calls=provider(monkeypatch,[invalid,plain_plan(),review(d,85),decision(0,'stop')])
    _,s=pal.run_loop(d,image(),'brief',tmp_path,lambda *a:None,contract=EMPTY,rounds=1)
    assert s['model_calls']==4 and 'Unknown symmetry part' in calls[1]['messages'][1]['content']
    assert s['plan']['symmetry']=='uncertain'
    assert (tmp_path/'perception/planning/plan-rejected.json').exists()


def test_provider_mismatch_stops_without_model_fallback(tmp_path,monkeypatch):
    d=Design.model_validate(load_task('enclosure')['design'])
    provider(monkeypatch,[])
    monkeypatch.setattr(pal.vision,'_call',lambda *a:(json.dumps(plain_plan()),{'model':'other-model','usage':{}}))
    selected,s=pal.run_loop(d,image(),'brief',tmp_path,lambda *a:None,contract=EMPTY,rounds=1)
    assert selected==d and s['model_calls']==1 and not s['reviewed']
    assert s['calls'][0]['reported_model']=='other-model' and s['calls'][0]['state']=='failed'


def test_nominal_constraint_checked_after_complete_mirror_compilation():
    d=pair_design();p=paired(d);contract={'schema':'fk-constraints-v1','rules':[{'id':'wall','kind':'dimension','part':'target','measure':'wall','min':.5,'max':1.5}]}
    a={'base_design_sha256':pal.digest(d.model_dump()),'rationale':'Mock invalid derived wall','edits':[{'part':'source','set':{'wall':2}}]}
    with pytest.raises(ValueError,match='frozen'):apply_workflow_action(d,a,contract,p)
    assert d.parts[0].wall==1 and d.parts[1].wall==1


def test_exception_schema_and_errors_require_exact_part_ids():
    from fluxkernel.demo.pal_rules import plan_schema
    d=pair_design();schema=plan_schema(d)
    assert set(schema['properties']['exceptions']['items']['enum'])=={p.id for p in d.parts}
    plan=plain_plan();plan['exceptions']=['source: visual explanation']
    with pytest.raises(ValueError,match='Move explanations'):validate_plan(plan,d)


def test_invalid_json_enters_automatic_model_repair(tmp_path,monkeypatch):
    d=Design.model_validate(load_task('enclosure')['design']);calls=provider(monkeypatch,[plain_plan(),review(d,85),decision(0,'stop')])
    good=pal.vision._call;count=0
    def malformed_first(*args):
        nonlocal count
        count+=1
        if count==1:return '{invalid json}',{'model':workflow.MODEL,'content':[{'type':'text','text':'{invalid json}'}]}
        return good(*args)
    monkeypatch.setattr(pal.vision,'_call',malformed_first)
    _,s=pal.run_loop(d,image(),'brief',tmp_path,lambda *a:None,contract=EMPTY,rounds=1)
    assert s['model_calls']==4 and s['reviewed'] and s['quality_status']=='model-threshold-met'
    assert '{invalid json}' in calls[0]['messages'][1]['content']
    assert (tmp_path/'perception/planning/plan-rejected.json').exists()
