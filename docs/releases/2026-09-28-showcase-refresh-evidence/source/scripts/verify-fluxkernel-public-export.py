"""Check public disclosure boundaries and exact provenance of displayed geometry.
Usage: python scripts/verify-fluxkernel-public-export.py PRIVATE_KERNEL PUBLIC_DIR
Private run identifiers and source manifests are never written to the public export.
"""
import hashlib
import json
import sys
from pathlib import Path

kernel, public = map(Path, sys.argv[1:])
config = json.loads(Path(__file__).with_name('fluxkernel-showcase-cases.json').read_text())
release = json.loads((public/'release.json').read_text())
assert set(release) == {'date', 'kind', 'cases', 'tests_passed', 'revision', 'display_mesh', 'scope', 'selection_note'}
report = []
for name, record in config.items():
    source = kernel/'.demo/runs'/record['run']
    original = json.loads((source/'result.json').read_text())
    scene = json.loads((source/'scene.json').read_text())
    data = json.loads((public/f'{name}.json').read_text())
    assert set(data) <= {'case','label','title','summary','counts','duration_s','model','version','parts','scene','proof','assumptions','gaps','perception'}
    assert data['proof'] == {'accepted': True, 'physical_status': 'unverified'}
    assert original['proof']['accepted'] and original['model']['mode'] == 'live'
    assert data['model'] == original['model']['model'] == 'glm-5.3-flash'
    assert data['version'] == record['version']
    published_case=next(c for c in release['cases'] if c['case']==name)
    assert published_case['asset_sha256']==hashlib.sha256((public/f'{name}.json').read_bytes()).hexdigest()
    triangles = 0
    for group, original_meshes in scene.items():
        meshes = data['scene'][group]
        assert len(meshes) == len(original_meshes)
        for src, dst in zip(original_meshes, meshes):
            assert set(dst) == {'id','name','color','position','group','route','vertices','indices'}
            for key in ('id','name','color','position','group','route'): assert src[key] == dst[key]
            expanded = [v for i in dst['indices'] for v in dst['vertices'][i*3:i*3+3]]
            assert expanded == [round(v,4) for v in src['vertices']], (name,src['id'])
            triangles += len(dst['indices'])//3
    if 'perception' in data:
        pal, srcpal = data['perception'], original['perception']
        assert set(pal) == {'quality_status','selected_round','stop_reason','model_calls','max_rounds','reference_camera_aligned','physical_status','rounds'}
        for key in set(pal)-{'rounds'}: assert pal[key] == srcpal[key]
        assert pal['selected_round'] == record['selected_round']
        assert len(pal['rounds']) == len(srcpal['rounds'])
        for dst, src in zip(pal['rounds'], srcpal['rounds']):
            assert set(dst) <= {'round','state','rejected_actions','ratings','findings','independent_issues','image'}
            assert dst['round'] == src['round']
            path = public.parent / dst['image'].lstrip('/')
            assert path.read_bytes() == (source/src['view']).read_bytes()
            assert hashlib.sha256(path.read_bytes()).hexdigest()[:12] in path.name
        declared = next(c for c in release['cases'] if c['case'] == name)
        assert declared['version'] == data['version'] and declared['selected_round'] == pal['selected_round']
    report.append({'case':name,'version':data['version'],'triangles':triangles,'source_geometry_match':True})
bridge = json.loads((public/'native-robots/evidence.json').read_text())
assert set(bridge) == {'schema','published','local_tests_passed','capabilities','limitations','physical_status','personalization','robots'}
for robot in bridge['robots'].values():
    assert set(robot) == {'status','model','model_calls','max_rounds','selected_round','visual_status','added_mass_kg','engineering_checks','export_checks','mass_basis','interface_status','deployment_ready'}
# Scan all first-party public payloads; vendor and attribution licenses are not internals.
for path in public.rglob('*'):
    if path.suffix not in {'.json','.js'} or 'vendor' in path.parts: continue
    text = path.read_text()
    for forbidden in ('plan_sha256','native_sha256','workflow_commit','proof_reexecuted','robot.json','lean_scope','sources_sha256','parent_native_sha256','/home/exuber','BEGIN PRIVATE KEY'):
        assert forbidden not in text, (str(path),forbidden)
print(json.dumps({'cases':report,'public_disclosure_allowlist':'passed'},ensure_ascii=False,indent=2))
