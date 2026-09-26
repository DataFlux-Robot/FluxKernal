"""Behavioral checks for evidence integrity and actual Lean plan rejection."""
import copy
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from fluxkernel.store.objstore import Store
from fluxkernel.semantics.contracts import covers
from fluxkernel.demo.models import Design
from fluxkernel.demo.references import reference,equipment_parts
from fluxkernel.demo import manufacturing as m


def plan(depth=1):
    d=reference('phone');eq=equipment_parts() if depth else []
    return m.make_plan(d,eq,{p.id:{'valid_brep':True} for p in d.parts+eq},depth,'a'*64,'b'*64)


def test_store_rejects_mutated_object(tmp_path):
    s=Store(tmp_path);d=s.put_object('receipt',{'value':1});p=s._obj_path(d)
    obj=json.loads(p.read_text());obj['payload']['value']=2;p.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match='integrity'):s.get_object(d)


def test_store_rejects_mutated_blob(tmp_path):
    s=Store(tmp_path);d=s.put_blob(b'original');(s.blobs/d.replace(':','_')).write_bytes(b'changed')
    with pytest.raises(ValueError,match='integrity'):s.get_blob(d)


@pytest.mark.parametrize('requirement,guarantee,expected',[
    (['>',10],['=',10],False),(['>=',10],['=',10],True),
    (['<',10],['=',10],False),(['>',10],['>',10],True),
    (['>',10],['>=',11],True)])
def test_strict_bounds(requirement,guarantee,expected):
    assert covers(requirement,guarantee)[0]==expected


def test_plan_binds_receipts_to_occurrences():
    p=plan();assert m.validate(p)==[]
    p['steps'][-1]['deps']=p['steps'][-2]['deps']
    assert any('receipt does not describe' in e for e in m.validate(p))


def test_receipt_tampering_rejected():
    p=plan();next(iter(p['receipts'].values()))['physical_evidence']='forged'
    assert any('invalid receipt binding' in e for e in m.validate(p))


def test_image_binding_rejected():
    p=plan();p['image_sha256']='c'*64
    assert any('receipt does not describe' in e for e in m.validate(p))


def test_no_equipment_remains_open():
    assert any('machining needs' in e for e in m.validate(plan(0)))


@pytest.mark.skipif(not shutil.which('lake'),reason='Lean toolchain absent')
@pytest.mark.parametrize('mutation',['valid','self','forward','depth','route','orphan','no_machine'])
def test_actual_lean_rejects_invalid_graph(tmp_path,mutation):
    p=plan()
    if mutation=='self':p['steps'][2]['deps']=[p['steps'][2]['id']]
    if mutation=='forward':p['steps'][2]['deps']=['product']
    if mutation=='depth':p['steps'][2]['depth']=2
    if mutation=='route':
        machine=next(s for s in p['steps'] if s['route']=='machine');machine['deps']=[machine['deps'][0]]
    if mutation=='orphan':p['steps'][-1]['deps']=p['steps'][-1]['deps'][:1]
    if mutation=='no_machine':p=plan(0)
    target=tmp_path/'Plan.lean';target.write_text(m.lean_source(p))
    result=subprocess.run(['lake','env','lean',str(target)],cwd=m.ROOT,capture_output=True,text=True,timeout=90)
    assert (result.returncode==0)==(mutation=='valid'),result.stdout+result.stderr
    if mutation=='valid':assert 'sorryAx' not in result.stdout


def test_reserved_part_identity():
    d=reference('phone').model_dump();d['parts'][0]['id']='cell-bed'
    with pytest.raises(ValueError,match='reserved'):Design.model_validate(d)


def test_rejected_derivation_does_not_poison_same_content(tmp_path):
    from fluxkernel.core.dag import DAG
    from fluxkernel.core.objects import Node,Edge,Certificate,Obligation,ResourceVector
    dag=DAG(Store(tmp_path));node=Node(role='Part',kind='same-output')
    good=Edge(op='refine',inputs=[],transform={'name':'valid'},output='')
    good_id,nd=dag.commit_edge(good,node,Certificate(evidence=[{'check':'passed'}]),ResourceVector())
    bad=Edge(op='refine',inputs=[],transform={'name':'failed'},output='')
    bad_id,same=dag.commit_edge(bad,node,Certificate(obligations=[Obligation('fail','failed check',False)]),ResourceVector())
    assert same==nd and bad.state=='rejected'
    assert dag.node_state(nd)=='promoted'
    assert dag.lineage_of(nd)==good_id
    assert dag.store.names()[f'@derivation/{nd}/{bad_id}']==bad_id
    child=Edge(op='refine',inputs=[nd],transform={'name':'consume'},output='')
    dag.commit_edge(child,Node(role='Part',kind='child'),Certificate(evidence=[{'check':'passed'}]),ResourceVector())
    assert child.state=='promoted'


def test_reference_http_bundle_and_failure_modes(tmp_path,monkeypatch):
    import time,zipfile,io
    from fastapi.testclient import TestClient
    from fluxkernel.demo import server
    monkeypatch.setattr(server,'DATA',tmp_path)
    with TestClient(server.app) as client:
        assert client.post('/api/jobs',data={'mode':'reference','reference':'invalid'}).status_code==422
        assert client.post('/api/jobs',files={'image':('bad.png',b'not an image','image/png')}).status_code==400
        assert client.get('/api/jobs/not-an-id').status_code==404
        response=client.post('/api/jobs',data={'mode':'reference','reference':'phone'})
        assert response.status_code==200
        id=response.json()['id']
        for _ in range(150):
            s=client.get('/api/jobs/'+id).json()
            if s['state'] in ('complete','failed'):break
            time.sleep(.1)
        assert s['state']=='complete',s
        assert s['result']['proof']['accepted']
        assert s['result']['fluxkernel']['integrity_verified']
        assert s['result']['model']['mode']=='reference'
        assert client.get(f'/api/jobs/{id}/files/.fk/index.json').status_code==404
        # Later verification outputs must not leak into the immutable delivery.
        (tmp_path/id/'unexpected-secret.txt').write_text('not part of manifest')
        r=client.get(f'/api/jobs/{id}/bundle');assert r.status_code==200
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            names=z.namelist();assert 'verify.py' in names
            assert 'formal/FluxKernel/Closure.lean' in names
            assert 'unexpected-secret.txt' not in names
            assert len([n for n in names if n.endswith('.step')])==34
            assert all('api_key' not in z.read(n).decode(errors='ignore') for n in names if n.endswith('.json'))


def test_mutated_parent_cannot_supply_cached_geometry(tmp_path):
    import hashlib
    from fluxkernel.demo.pipeline import reusable_parent
    from fluxkernel.demo.models import Request
    parent=tmp_path/('a'*16);parent.mkdir();child=tmp_path/('b'*16);child.mkdir()
    files={'design.json':{'parts':[]},'equipment.json':[],
           'scene.json':{'product':[],'equipment':[]},'geometry-checks.json':{}}
    manifest={}
    for name,data in files.items():
        raw=json.dumps(data).encode();(parent/name).write_bytes(raw)
        manifest[name]=hashlib.sha256(raw).hexdigest()
    (parent/'manifest.json').write_text(json.dumps(manifest))
    assert reusable_parent(child,Request(parent=parent.name))['parts']=={}
    (parent/'design.json').write_text('{"parts":[{"id":"forged"}]}')
    with pytest.raises(ValueError,match='父版本证据已改变'):
        reusable_parent(child,Request(parent=parent.name))
