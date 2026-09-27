"""PAL regressions: actual rendering and geometry, mocked network responses."""
import base64
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from fluxkernel.demo import perception as pal
from fluxkernel.demo.models import Design,Part,Request
from fluxkernel.demo.perception_render import render_view,render_design
from fluxkernel.studio import load_task


@pytest.fixture
def design():return Design.model_validate(load_task('enclosure')['design'])


@pytest.fixture
def fake_config(monkeypatch):
    monkeypatch.setattr(pal.vision,'model_config',lambda:{'model':'test-vlm','api_key':'test-private-key'})


def review(score,major=True):
    return {'silhouette':score,'proportions':score,'layout':score,'reference_limitations':'Single reference view',
            'findings':[{'severity':'major','parts':['housing'],'observation':'Clearance/appearance needs adjustment',
                         'suggested_change':'Adjust housing wall'}] if major else []}


def action(design,wall=3):
    return {'base_design_sha256':pal.digest(design.model_dump()),'rationale':'Adjust housing',
            'edits':[{'part':'housing','set':{'wall':wall}}]}


def install_responses(monkeypatch,responses):
    calls=[]
    def call(cfg,messages,schema,event):
        calls.append(messages)
        value=responses.pop(0)
        if isinstance(value,Exception):raise value
        return json.dumps(value),{'usage':{'input_tokens':10,'output_tokens':10},'content':[{'type':'text','text':json.dumps(value)}]}
    monkeypatch.setattr(pal.vision,'_call',call)
    return calls


def image_bytes():
    import io
    from PIL import Image
    b=io.BytesIO();Image.new('RGB',(40,40),'white').save(b,'PNG');return b.getvalue()


def test_depth_buffer_not_triangle_order():
    # Looking from +X: near plane x=1 must obscure the far plane x=-1.
    far=np.array([[[-1,-2,-2],[-1,2,-2],[-1,0,2]]],dtype=float)
    near=far.copy();near[:,:,0]=1
    meshes=[{'color':'#ff0000','triangles':far},{'color':'#0000ff','triangles':near}]
    a,mask=render_view(meshes,'front',pixels=128)
    b,_=render_view(list(reversed(meshes)),'front',pixels=128)
    assert np.array_equal(np.array(a),np.array(b))
    pixel=np.array(a)[64,64]
    assert pixel[2]>pixel[0] and np.array(mask)[64,64]==255


@pytest.mark.parametrize('shape,size',[('smooth_fuselage',[38000,3950,3950]),('smooth_car_body',[5050,1940,1200]),('fuselage_section',[11000,3950,3950]),('fuselage_nose',[9500,3950,3950]),('fuselage_tail',[9000,3600,3600])])
def test_smooth_body_exports_one_valid_solid(tmp_path,shape,size):
    from fluxkernel.demo.geometry import artifacts
    from fluxkernel.store.objstore import Store
    p=Part(id='body',name='body',group='body',route='print',shape=shape,size=size,position=[0,0,0],wall=8)
    mesh,checks,refs=artifacts(p,tmp_path,Store(tmp_path/'.fk'))
    assert checks['valid_brep'] and checks['solid_count']==1
    assert checks['volume_mm3']>0 and set(refs)=={'step','stl'}


def test_render_produces_four_real_views(design,tmp_path):
    report=render_design(design,tmp_path)
    assert report['triangle_count']>0
    assert set(report['frame_coverage'])=={'iso','front','side','top'}
    assert all(v>0 for v in report['frame_coverage'].values())
    assert (tmp_path/'views.png').is_file()


@pytest.mark.parametrize('field,value',[('route','catalog'),('material','steel'),('catalog_ref','invented'),('id','different')])
def test_action_cannot_rewrite_protected_fields(design,field,value):
    request=action(design);request['edits'][0]['set']={field:value}
    with pytest.raises(ValueError,match='Protected'):pal.apply_action(design,request,load_task('enclosure')['constraints'])


def test_action_preserves_requirements_and_contract(design):
    contract=load_task('enclosure')['constraints'];before=copy.deepcopy(contract)
    changed=pal.apply_action(design,action(design),contract)
    assert changed.requirements==design.requirements and contract==before
    assert changed.parts[0].wall==3
    with pytest.raises(ValueError,match='constraint'):pal.apply_action(design,action(design,5),contract)
    request=action(design);request['base_design_sha256']='0'*64
    with pytest.raises(ValueError,match='Stale'):pal.apply_action(design,request,contract)


def test_catalog_resize_rejected_but_pose_allowed(design):
    request=action(design);request['edits']=[{'part':'payload','set':{'size':[10,10,10]}}]
    with pytest.raises(ValueError,match='Catalog'):pal.apply_action(design,request,{'schema':'fk-constraints-v1','rules':[]})
    request['edits'][0]['set']={'rotation':[0,0,90]}
    assert pal.apply_action(design,request,{'schema':'fk-constraints-v1','rules':[]}).parts[1].rotation==[0,0,90]


def test_regression_keeps_best_reviewed_candidate(design,tmp_path,monkeypatch,fake_config):
    calls=install_responses(monkeypatch,[review(70),action(design),review(30)])
    selected,summary=pal.run_loop(design,image_bytes(),'retain requirements',tmp_path,lambda *a:None,
                                contract=load_task('enclosure')['constraints'],rounds=2)
    assert selected==design and summary['selected_round']==0
    assert summary['quality_status']=='needs-review' and summary['model_calls']==3
    assert len(calls[0][1]['images'])==2 and len(calls[2][1]['images'])==3
    assert base64.b64decode(calls[0][1]['images'][1])==(tmp_path/'perception/round-00/views.png').read_bytes()
    assert summary['rounds'][1]['selected_when_reviewed'] is False


def test_review_failure_is_not_synthetic_acceptance(design,tmp_path,monkeypatch,fake_config):
    install_responses(monkeypatch,[RuntimeError('provider failure test-private-key')])
    selected,summary=pal.run_loop(design,image_bytes(),'brief',tmp_path,lambda *a:None,
                                 contract=load_task('enclosure')['constraints'],rounds=3)
    assert selected==design and not summary['reviewed']
    assert summary['quality_status']=='needs-review' and summary['selected_round'] is None
    assert 'test-private-key' not in (tmp_path/'perception/summary.json').read_text()


def test_valid_review_threshold_stops_early(design,tmp_path,monkeypatch,fake_config):
    install_responses(monkeypatch,[review(85,major=False)])
    _,summary=pal.run_loop(design,image_bytes(),'brief',tmp_path,lambda *a:None,
                           contract=load_task('enclosure')['constraints'],rounds=3)
    assert summary['model_calls']==1 and summary['stop_reason']=='review-threshold'
    assert summary['quality_status']=='model-threshold-met'


def test_bad_action_archived_parent_retained(design,tmp_path,monkeypatch,fake_config):
    install_responses(monkeypatch,[review(70),action(design,5),action(design,5)])
    selected,summary=pal.run_loop(design,image_bytes(),'brief',tmp_path,lambda *a:None,
                                 contract=load_task('enclosure')['constraints'],rounds=3)
    assert selected==design and summary['rounds'][0]['action_state']=='rejected'
    assert (tmp_path/'perception/round-00/action.json').is_file()
    assert summary['quality_status']=='needs-review'


def test_engine_orientation_check_uses_actual_euler_convention():
    from fluxkernel.demo.references import reference
    d=reference('aircraft');engine=next(p for p in d.parts if p.shape=='cylinder')
    engine.id='engine-check';engine.rotation=[90,0,0]
    assert any(c['code']=='AIRCRAFT_ENGINE_AXIS' for c in pal.layout_checks(d)['issues'])
    engine.rotation=[0,90,0]
    assert not any(engine.id in c['parts'] for c in pal.layout_checks(d)['issues'] if c['code']=='AIRCRAFT_ENGINE_AXIS')


def test_live_pipeline_routes_through_visual_loop(design,tmp_path,monkeypatch,fake_config):
    from fluxkernel.demo.pipeline import execute
    monkeypatch.setattr(pal.vision,'plan',lambda *a:(design,{'mode':'live','model':'test-vlm','attempts':1}))
    install_responses(monkeypatch,[review(65)])
    execute(tmp_path,Request(mode='live',visual_rounds=1),image_bytes())
    result=json.loads((tmp_path/'result.json').read_text())
    assert result['perception']['enabled'] and result['perception']['model_calls']==1
    assert result['perception']['quality_status']=='needs-review'
    assert result['status'] in ('needs-review','open')
    assert json.loads((tmp_path/'design.json').read_text())==json.loads((tmp_path/'perception/round-00/design.json').read_text())
    assert 'perception/round-00/views.png' in json.loads((tmp_path/'manifest.json').read_text())
    # Even a recomputed file manifest cannot make a wrong selected design agree.
    import hashlib,subprocess,sys
    visual=tmp_path/'perception/summary.json'
    data=json.loads(visual.read_text());data['selected_design_sha256']='0'*64
    visual.write_text(json.dumps(data))
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    manifest['perception/summary.json']=hashlib.sha256(visual.read_bytes()).hexdigest()
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    checked=subprocess.run([sys.executable,str(tmp_path/'verify.py'),str(tmp_path)],capture_output=True,text=True)
    assert checked.returncode and 'Visual selection differs' in checked.stderr


def test_rejected_action_gets_one_feedback_repair(design,tmp_path,monkeypatch,fake_config):
    calls=install_responses(monkeypatch,[review(60),action(design,5),action(design,3),review(85,major=False)])
    changed,summary=pal.run_loop(design,image_bytes(),'brief',tmp_path,lambda *a:None,
                                contract=load_task('enclosure')['constraints'],rounds=2)
    assert changed.parts[0].wall==3 and summary['selected_round']==1
    assert summary['model_calls']==4
    assert summary['rounds'][0]['action_attempts'][0]['accepted'] is False
    assert 'rejected_action_feedback' in calls[2][1]['content']
    assert (tmp_path/'perception/round-00/action-00-rejected.json').is_file()


@pytest.mark.parametrize('value',[[True,0,0],[float('nan'),0,0],['1',0,0]])
def test_action_rejects_nonfinite_or_coerced_vectors(design,value):
    request=action(design);request['edits'][0]['set']={'position':value}
    with pytest.raises(ValueError,match='finite numeric'):
        pal.apply_action(design,request,load_task('enclosure')['constraints'])


def test_action_reports_all_errors_for_one_repair(design):
    request=action(design);request['edits']=[
        {'part':'missing','set':{'wall':3}},
        {'part':'payload','set':{'size':[10,10,10]}},
        {'part':'housing','set':{'route':'catalog'}}]
    with pytest.raises(ValueError) as caught:
        pal.apply_action(design,request,load_task('enclosure')['constraints'])
    assert all(word in str(caught.value) for word in ['missing','payload','housing','size','Protected'])
    assert 'payload' in pal.action_schema(design)['properties']['edits']['items']['properties']['part']['enum']
