"""Portable recipes: compatibility, isolation, evidence expiry and real reuse."""
import copy
import json
import shutil
from pathlib import Path
import pytest

pytest.importorskip('pydantic')
pytest.importorskip('OCP')
from fluxkernel.asset_models import Publish, Query, Instance
from fluxkernel.asset_api import asset_schema, inline_schema
from fluxkernel.assets import AssetLibrary, publish, assess, prepare_instance
from fluxkernel.asset_benchmark import fixture, generate_fixture
from fluxkernel.demo.constraints import evaluate, validate_contract
from fluxkernel.revision import snapshot, preview_revision, RevisionError
from fluxkernel.studio import apply_asset


@pytest.fixture(scope='module')
def baseline(tmp_path_factory):
    return Path(generate_fixture('car',tmp_path_factory.mktemp('asset-runs')).directory)


def spec(parent, **overrides):
    return {'base_manifest_sha256':snapshot(parent)['identity'], 'name':'shared-module',
            'version':'1.0.0','category':'mount','description':'Authored test fixture',
            'parts':['bracket','shaft'], **overrides}


def request(parent, identity, **overrides):
    return {'base_manifest_sha256':snapshot(parent)['identity'], 'asset_sha256':identity,
            'prefix':'reused','query':{'category':'mount'},'position':[0,100,50],
            'rotation':[0,0,90], **overrides}


def shaft_spec(parent):
    return spec(parent,parts=['shaft'],kind='component',origin=[50,0,0],
        parameters={'diameter':{'default':10,'min':8,'max':20,'bindings':[
            {'part':'shaft','field':'size.0'}, {'part':'shaft','field':'size.1'}]}},
        measures={'diameter':{'part':'shaft','field':'size.0'}},
        capabilities={'torque':{'unit':'Nm','min':0,'max':50}}, interfaces={'mount':'shaft-v1'})


@pytest.mark.parametrize('name,model',[('publish',Publish),('query',Query),('instance',Instance)])
def test_static_schemas_match_runtime(name,model):
    assert asset_schema(name)==model.model_json_schema()
    assert '$ref' not in json.dumps(inline_schema(name))


@pytest.mark.parametrize('value',[True,'10',float('nan'),float('inf')])
def test_invalid_numeric_capability(value):
    with pytest.raises(ValueError):
        Query.model_validate({'category':'mount','requirements':{'x':{'unit':'mm','min':0,'max':value}}})


@pytest.mark.parametrize('query,status',[
    ({'requirements':{'voltage':{'unit':'mV','min':24000,'max':28000}}},'compatible'),
    ({'requirements':{'voltage':{'unit':'V','min':24,'max':48}}},'incompatible'),
    ({'requirements':{'voltage':{'unit':'N','min':24,'max':28}}},'incompatible'),
    ({'requirements':{'torque':{'unit':'Nm','min':0,'max':30}}},'needs-evidence'),
    ({'interfaces':{'bus':'different'}},'incompatible'),
    ({'interfaces':{'missing':'can-v1'}},'needs-evidence'),
    ({'category':'not-mount'},'incompatible'),
])
def test_compatibility_requires_containment_and_known_evidence(baseline,tmp_path,query,status):
    library=AssetLibrary(tmp_path/'library')
    identity=publish(library,baseline,spec(baseline,parts=['control'],kind='component',
        capabilities={'voltage':{'unit':'V','min':18,'max':30}},interfaces={'bus':'can-v1'}))['asset_sha256']
    assert assess(library.read(identity),{'category':'mount',**query})['status']==status
    assert library.search({'category':'mount'})['matches'][0]['source_family']=='car'


def test_parameter_adaptation_recomputes_geometry_and_expires_claims(baseline,tmp_path):
    library=AssetLibrary(tmp_path/'library');identity=publish(library,baseline,shaft_spec(baseline))['asset_sha256']
    asset=library.read(identity)
    report=assess(asset,{'category':'mount','requirements':{'diameter':{'unit':'mm','min':16,'max':16,'relation':'within'}}},{'diameter':16})
    assert report['status']=='compatible' and report['properties']['diameter']['min']==16
    assert 'torque' not in report['properties'] and 'declared-interfaces' in report['invalidated_evidence']
    assert assess(asset,{'category':'mount','interfaces':{'mount':'shaft-v1'}},{'diameter':16})['status']=='needs-evidence'
    assert assess(asset,{'category':'mount','requirements':{'torque':{'unit':'Nm','min':0,'max':30}}},{'diameter':16})['status']=='needs-evidence'
    for parameters in ({'diameter':21},{'unknown':10},{'diameter':True}):
        with pytest.raises(ValueError):assess(asset,{'category':'mount'},parameters)
    asset['integration_obligations']=[{'kind':'assembly-driver-rebind'}]
    with pytest.raises(ValueError,match='rebinding'):assess(asset,{'category':'mount'},{'diameter':16})


def test_catalog_dimensions_cannot_be_parameterized(baseline,tmp_path):
    with pytest.raises(ValueError,match='Catalog dimensions'):
        publish(AssetLibrary(tmp_path/'library'),baseline,spec(baseline,parts=['control'],
            parameters={'width':{'default':50,'min':40,'max':60,'bindings':[{'part':'control','field':'size.0'}]}}))


def test_identity_and_namespace_guards(baseline,tmp_path):
    library=AssetLibrary(tmp_path/'library');identity=publish(library,baseline,spec(baseline))['asset_sha256']
    with pytest.raises(RevisionError):prepare_instance(library,baseline,request(baseline,identity,base_manifest_sha256='0'*64))
    with pytest.raises(ValueError,match='Replacement maps'):
        prepare_instance(library,baseline,request(baseline,identity,replace={'bracket':'absent'}))
    (library.root/(identity+'.json')).write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):library.read(identity)
    link=tmp_path/'link';link.symlink_to(library.root,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):AssetLibrary(link).search({'category':'mount'})
    with pytest.raises(ValueError,match='2 MiB'):library.put({'large':'x'*(2*1024*1024)})


def test_incompatible_target_reports_failed_constraint(baseline,tmp_path):
    library=AssetLibrary(tmp_path/'library');identity=publish(library,baseline,shaft_spec(baseline))['asset_sha256']
    report=prepare_instance(library,baseline,request(baseline,identity,position=[80,0,0],rotation=[0,0,0],replace={'shaft':'shaft'}))[0]
    assert not report['accepted'] and report['status']=='incompatible'
    assert any(i.get('constraint')=='mount-separation' for i in report['issues'])


def test_rotated_asset_contract_survives_future_revision(baseline,tmp_path):
    library=AssetLibrary(tmp_path/'library');identity=publish(library,baseline,spec(baseline))['asset_sha256']
    parent=snapshot(baseline)['identity'];req=request(baseline,identity)
    preview=prepare_instance(library,baseline,req)[0]
    assert preview['accepted'] and not preview['proof_reused']
    result=apply_asset(baseline,library.root,req,output_dir=tmp_path/'runs')
    assert result['ok'],result
    child=Path(result['directory']);snap=snapshot(child)
    assert snapshot(baseline)['identity']==parent
    assert result['run']['proof_accepted'] if shutil.which('lake') else True
    assert 'asset-source.json' in snap['files'] and 'asset-reuse.json' in snap['files']
    patch={'schema':'fk-revision-v1','base_manifest_sha256':snap['identity'],
        'edits':[{'part':'reused-shaft','set':{'position':[0,175,50]}}]}
    assert not preview_revision(child,patch)['accepted']
    with pytest.raises(ValueError,match='collides'):prepare_instance(library,child,request(child,identity))


@pytest.mark.parametrize('rotation',[[0,0,90],[30,20,-40],[0,90,0]])
def test_frame_preserves_local_measurements(rotation):
    from scipy.spatial.transform import Rotation
    local=fixture('car');world=copy.deepcopy(local['design']);r=Rotation.from_euler('xyz',rotation,degrees=True)
    for p in world['parts']:
        p['position']=(r.apply(p['position'])+[10,20,30]).tolist();p['rotation']=rotation
    frame={'id':'frame','kind':'asset-frame','position':[10,20,30],'rotation':rotation,
           'parts':[p['id'] for p in world['parts']],'rules':local['constraints']['rules']}
    contract={'schema':'fk-constraints-v1','rules':[frame]}
    assert evaluate(world,contract)['accepted']
    frame['parts'].append('missing');assert not evaluate(world,contract)['accepted']
    frame['parts'].pop();frame['rules'].append(copy.deepcopy(frame))
    with pytest.raises(ValueError,match='Nested frames'):validate_contract(contract)


def test_partial_equipment_publication_is_rejected(baseline,tmp_path):
    with pytest.raises(ValueError,match='complete recorded cell'):
        publish(AssetLibrary(tmp_path/'library'),baseline,spec(baseline,parts=['cell-bed'],kind='equipment'))


def test_agent_asset_roundtrip(baseline,tmp_path):
    pytest.importorskip('mcp')
    import anyio
    from mcp import Client
    from fluxkernel.agent_server import create_server
    from fluxkernel.agent_workspace import AgentWorkspace, WorkspaceError
    workspace=tmp_path/'workspace';workspace.mkdir();parent=workspace/baseline.name;shutil.copytree(baseline,parent)
    async def run():
        async with Client(create_server(AgentWorkspace(workspace))) as client:
            async def call(name,**args):
                result=await client.call_tool(name,args)
                assert not result.is_error,result.structured_content
                return result.structured_content
            published=await call('publish_asset',run_id=parent.name,request=spec(parent))
            identity=published['asset_sha256']
            assert (await call('search_assets',query={'category':'mount'}))['total']==1
            assert (await call('inspect_asset',asset_sha256=identity))['source']['family']=='car'
            req=request(parent,identity)
            assert (await call('preview_asset',run_id=parent.name,request=req))['accepted']
            assert (await call('instantiate_asset',run_id=parent.name,request=req))['ok']
    anyio.run(run)
    readonly=AgentWorkspace(workspace,read_only=True)
    with pytest.raises(WorkspaceError,match='read-only'):readonly.publish_asset(parent.name,spec(parent))
