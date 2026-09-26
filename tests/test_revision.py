"""Local revisions: immutable parents, protected contracts, real CAD and proof paths."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
import pytest
from fluxkernel.revision import inspect_run, preview_revision, snapshot, RevisionError
from fluxkernel.studio import generate_task, load_task, apply_revision


@pytest.fixture(scope='module')
def baseline(tmp_path_factory):
    return Path(generate_task('enclosure',output_dir=tmp_path_factory.mktemp('revision-runs')).directory)


def request(parent, edits=None):
    return {'schema':'fk-revision-v1','base_manifest_sha256':inspect_run(parent)['manifest_sha256'],
            'edits':edits if edits is not None else load_task('enclosure')['valid_edits']}


def test_preview_is_readonly_and_reports_invalidation(baseline):
    before={p.name for p in baseline.parent.iterdir()}
    report=preview_revision(baseline,request(baseline))
    assert report['accepted'] and report['changed']==['housing']
    assert 'product' in report['structural_dependents']
    assert report['evidence']['proof_reused'] is False
    assert not report['geometry_evaluated']
    assert before=={p.name for p in baseline.parent.iterdir()}


def test_apply_reuses_exact_geometry_and_preserves_parent(baseline):
    parent=snapshot(baseline)
    patch=request(baseline)
    result=apply_revision(baseline,patch)
    assert result['ok']
    child=Path(result['directory'])
    assert result['reuse']['rebuilt']==['housing']
    assert len(result['reuse']['reused'])==23
    for part in result['reuse']['reused']:
        for ext in ('step','stl'):
            assert (child/f'cad/{part}.{ext}').read_bytes()==parent['files'][f'cad/{part}.{ext}']
    assert (child/'constraints.json').read_bytes()==parent['files']['constraints.json']
    assert json.loads((child/'design.json').read_text())['requirements']==json.loads(parent['files']['design.json'])['requirements']
    assert snapshot(baseline)['identity']==parent['identity']
    if shutil.which('lake'):assert result['run']['proof_accepted']
    assert json.loads((child/'proof.json').read_text())['plan_sha256']!=json.loads(parent['files']['proof.json'])['plan_sha256']
    # The child is itself a complete, usable revision parent.
    assert preview_revision(child,request(child,[{'part':'housing','set':{'wall':3.5}}]))['accepted']


@pytest.mark.parametrize('edits,code', [
    ([{'part':'housing','set':{'wall':5}}],'REV_CONSTRAINT_FAILED'),
    ([{'part':'payload','set':{'size':[60,40,10]}}],'REV_CATALOG_IMMUTABLE'),
    ([{'part':'missing','set':{'wall':2}}],'REV_UNKNOWN_PART'),
    ([{'part':'housing','set':{'wall':40}}],'REV_GEOMETRY_PARAMETERS'),
    ([{'part':'housing','set':{'route':'catalog'}}],'REV_PROTECTED_FIELD')])
def test_rejected_attempt_is_archived_without_cad(baseline,edits,code):
    result=apply_revision(baseline,request(baseline,edits))
    assert result['state']=='rejected' and not result['ok']
    assert any(d['code']==code for d in result['preview']['diagnostics'])
    child=Path(result['directory'])
    assert (child/'revision-request.json').is_file()
    assert not (child/'cad').exists() and not (child/'result.json').exists()
    assert inspect_run(baseline)['manifest_sha256']==request(baseline)['base_manifest_sha256']


def test_stale_manifest_is_rejected_before_execution(baseline):
    patch=request(baseline);patch['base_manifest_sha256']='0'*64
    report=preview_revision(baseline,patch)
    assert not report['accepted'] and report['diagnostics'][0]['code']=='REV_STALE_PARENT'


def test_tampered_cad_cannot_supply_reuse(baseline,tmp_path):
    parent=tmp_path/'parent';shutil.copytree(baseline,parent)
    patch=request(parent)
    (parent/'cad/lid.step').write_bytes(b'forged')
    report=preview_revision(parent,patch)
    assert report['diagnostics'][0]['code']=='REV_PARENT_CHANGED'


def test_manifest_path_escape_is_rejected(baseline,tmp_path):
    parent=tmp_path/'parent';shutil.copytree(baseline,parent)
    outside=tmp_path/'outside';outside.write_bytes(b'outside')
    manifest=json.loads((parent/'manifest.json').read_text())
    manifest['../outside']=hashlib.sha256(b'outside').hexdigest()
    (parent/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(RevisionError):snapshot(parent)


def test_bundle_checker_is_bound_beyond_its_manifest(baseline,tmp_path):
    parent=tmp_path/'bundle';shutil.copytree(baseline,parent)
    checker=parent/'constraint_checker.py';checker.write_bytes(checker.read_bytes()+b'\n# changed checker\n')
    manifest=json.loads((parent/'manifest.json').read_text())
    manifest['constraint_checker.py']=hashlib.sha256(checker.read_bytes()).hexdigest()
    (parent/'manifest.json').write_text(json.dumps(manifest))
    result=subprocess.run([sys.executable,str(parent/'verify.py'),str(parent)],capture_output=True,text=True)
    assert result.returncode != 0 and 'Constraint checker differs' in result.stderr


def test_machining_dimensions_propagate_to_equipment(baseline):
    report=preview_revision(baseline,request(baseline,[{'part':'carrier','set':{'size':[300,50,2]}}]))
    assert report['accepted']
    assert 'cell-bed' in report['equipment_changed']
    assert 'machine-cell' in report['structural_dependents']


def test_freeform_legacy_revision_cannot_discard_numeric_contract(baseline,tmp_path):
    from fluxkernel.demo.pipeline import execute
    from fluxkernel.demo.models import Request
    from fluxkernel.demo import pipeline
    original=json.loads((baseline/'design.json').read_text())
    changed=copy.deepcopy(original);changed['parts'][0]['wall']=5
    run=baseline.parent/('f'*16);run.mkdir(exist_ok=True)
    execute(run,Request(mode='revision',parent=baseline.name), (baseline/'image.png').read_bytes(),
            original,design_override=changed)
    state=json.loads((run/'status.json').read_text())
    assert state['state']=='failed' and 'Frozen nominal constraints' in state['error']
    assert not (run/'cad').exists()
