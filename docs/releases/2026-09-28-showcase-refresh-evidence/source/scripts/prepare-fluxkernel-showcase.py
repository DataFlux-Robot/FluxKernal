"""Export an allowlisted public showcase from private, recorded FluxKernel runs.
Usage: python scripts/prepare-fluxkernel-showcase.py /path/to/fluxkernel
No model calls, credentials, raw prompts, backend code or CAD bundles are exported.
"""
import argparse, hashlib, json, shutil
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',type=Path)
parser.add_argument('--car-run',type=Path)
parser.add_argument('--aircraft-run',type=Path)
args=parser.parse_args()
root=args.root.resolve()
out=Path(__file__).resolve().parents[1]/'public/fluxkernel'
out.mkdir(parents=True,exist_ok=True)
config=json.loads(Path(__file__).with_name('fluxkernel-showcase-cases.json').read_text())
cases=[(key,label,config[key]['run']) for key,label in [('phone','手机'),('car','汽车'),('aircraft','飞机')]]
part_keys=['id','name','group','route','size','material','source','purpose']
mesh_keys=['id','name','color','position','group','route']
release=[]
for key,label,run in cases:
    override=getattr(args,key+'_run',None)
    directory=(override if override else root/'.demo/runs'/run).resolve()
    run=directory.name
    assert run==config[key]['run'], 'Update the release manifest before changing a case run'
    result=json.loads((directory/'result.json').read_text())
    scene=json.loads((directory/'scene.json').read_text())
    assert result['model']['mode']=='live' and result['proof']['accepted']
    compact={}
    for view,meshes in scene.items():
        compact[view]=[]
        for mesh in meshes:
            # Indexed display mesh, rounded to 0.0001 mm. Triangle order/count
            # remain identical; original STEP/STL and proof inputs stay private.
            lookup={}; vertices=[]; indices=[]
            original=mesh['vertices']
            assert len(original)%9==0
            for offset in range(0,len(original),3):
                xyz=tuple(round(value,4) for value in original[offset:offset+3])
                if xyz not in lookup:
                    lookup[xyz]=len(vertices)//3;vertices.extend(xyz)
                indices.append(lookup[xyz])
            item={k:mesh[k] for k in mesh_keys}
            item.update(vertices=vertices,indices=indices)
            assert len(indices)==len(original)//3
            compact[view].append(item)
    data={
        'case':key,'label':label,'title':result['title'],'summary':result['summary'],
        'counts':result['counts'],'duration_s':result['duration_s'],
        'model':result['model']['model'],'version':config[key]['version'],
        'parts':[{k:p[k] for k in part_keys} for p in result['design']['parts']+result['equipment']],
        'scene':compact,'proof':{'accepted':bool(result['proof']['accepted']),'physical_status':'unverified'},
        'assumptions':result['design']['assumptions'],'gaps':result['gaps'],
    }
    pal=result.get('perception') or {}
    if pal.get('enabled'):
        assert pal['selected_round'] is not None, 'Never publish an unreviewed run as a new result'
        if not override: assert pal['selected_round']==config[key]['selected_round']
        image_dir=out/'perception'/key
        if image_dir.exists():
            for old in image_dir.glob('round-*.png'): old.unlink()
        rounds=[]
        for r in pal['rounds']:
            item={k:r[k] for k in ('round','state') if k in r}
            item['rejected_actions']=sum(not a.get('accepted',False) for a in r.get('action_attempts',[]))
            if r.get('review'):
                item['ratings']={k:r['review'][k] for k in ('silhouette','proportions','layout')}
                item['findings']=[{k:f[k] for k in ('severity','parts','observation')} for f in r['review']['findings']]
                item['independent_issues']=len(r['layout']['issues'])
            if r.get('view'):
                source=(directory/r['view']).resolve()
                assert source.is_relative_to(directory/'perception') and source.suffix=='.png'
                digest=hashlib.sha256(source.read_bytes()).hexdigest()[:12]
                image=out/'perception'/key/f"round-{r['round']:02d}-{digest}.png"
                image.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,image)
                item['image']='/fluxkernel/'+image.relative_to(out).as_posix()
            rounds.append(item)
        data['perception']={k:pal[k] for k in ('quality_status','selected_round','stop_reason','model_calls','max_rounds','reference_camera_aligned','physical_status')}
        data['perception']['rounds']=rounds
    target=out/f'{key}.json'
    target.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
    shutil.copy2(directory/'image.png',out/f'{key}-input.png')
    release.append({'case':key,'version':config[key]['version'],'asset_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'visual_status':pal.get('quality_status','not-evaluated'),'selected_round':pal.get('selected_round'),'reviewed_rounds':len(pal.get('rounds',[])),'max_rounds':pal.get('max_rounds'),'model':data['model']})
    print(key,round(target.stat().st_size/1024/1024,2),'MiB')
static=root/'fluxkernel/demo/static'
shutil.copy2(static/'references/sources.json',out/'photo-sources.json')
(out/'vendor').mkdir(exist_ok=True)
for name in ['three.module.js','three.core.js','OrbitControls.js','THREE-LICENSE.txt']:
    text=(static/'vendor'/name).read_text()
    if name=='OrbitControls.js':text=text.replace("from 'three'","from './three.module.js'")
    # Normalize trailing whitespace in the public vendored copy only.
    text='\n'.join(line.rstrip() for line in text.splitlines())+'\n'
    text=text.replace('\t\t\t \tmaterial =', '\t\t\t\tmaterial =')
    (out/'vendor'/name).write_text(text)
shutil.copy2(root/'.demo/investor-demo.mp4',out/'walkthrough.mp4')
(out/'release.json').write_text(json.dumps({
    'date':'2026-09-28','kind':'recorded-real-model-results','cases':release,
    'tests_passed':272,'revision':{'total_parts':40,'reused_parts':39,'changed_part':'back-cover'},
    'display_mesh':{'indexed':True,'coordinate_precision_mm':0.0001,'triangle_count_preserved':True},
    'scope':'Recorded model-selected concepts; no physical capability certification',
    'selection_note':'Most recent completed car and aircraft examples. The aircraft six-round follow-up failed before review and did not replace this model-selected result. Examples do not establish reliability.',
},ensure_ascii=False,indent=2)+'\n')
