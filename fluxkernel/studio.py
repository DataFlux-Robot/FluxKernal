"""Isolated reference generation, engineering tasks and local design revisions."""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .runtime import data_dir

TASKS = ('enclosure', 'shaft-fit', 'mounting-pitch')


class StudioError(RuntimeError):
    """A run did not produce a complete artifact set."""


@dataclass(frozen=True)
class Run:
    id: str
    directory: str
    mode: str
    status: str
    proof_accepted: bool
    physical_status: str
    counts: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


def _new_run(output_dir, timeout):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    root = Path(output_dir).expanduser().resolve() if output_dir is not None else data_dir()
    run = root / uuid.uuid4().hex[:16]
    run.mkdir(parents=True)
    return run


def _worker(run, arguments, timeout):
    command = [sys.executable, '-m', 'fluxkernel.studio', '--run', str(run), *arguments]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        status = run/'status.json'
        record = json.loads(status.read_text(encoding='utf-8')) if status.is_file() else {'id':run.name,'events':[]}
        record.update(state='failed', stage='failed', error='Worker exceeded its time limit')
        status.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        raise StudioError(f'Run timed out; partial evidence: {run}') from exc
    (run/'worker.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
    return proc.returncode


def _result(run):
    if not (run/'result.json').is_file() or not (run/'status.json').is_file():
        raise StudioError(f'Run failed; inspect {run}/status.json and worker.log. Run `fk doctor --profile studio`.')
    status = json.loads((run/'status.json').read_text(encoding='utf-8'))
    if status['state'] != 'complete':
        raise StudioError(f'Run is incomplete; inspect {run}/status.json')
    result = json.loads((run/'result.json').read_text(encoding='utf-8'))
    return Run(run.name, str(run), result['model']['mode'], result['status'],
               result['proof']['accepted'], result['physical_status'], result['counts'])


def generate_reference(reference='phone', *, output_dir=None, equipment_depth=1, timeout=300) -> Run:
    """Curated design without image inference; absent Lean leaves an open proof."""
    if reference not in ('phone','car','aircraft'):
        raise ValueError('reference must be phone, car, or aircraft')
    if type(equipment_depth) is not int or equipment_depth not in (0, 1):
        raise ValueError('equipment_depth must be 0 or 1')
    run = _new_run(output_dir, timeout)
    _worker(run, ['--reference',reference,'--equipment-depth',str(equipment_depth)], timeout)
    return _result(run)


def load_task(name):
    if name not in TASKS:
        raise ValueError('Unknown engineering task')
    return json.loads((Path(__file__).parent/'demo/tasks'/f'{name}.json').read_text(encoding='utf-8'))


def generate_task(name, *, output_dir=None, timeout=300) -> Run:
    """Build an authored fixture with a frozen numeric interface contract."""
    load_task(name)
    run = _new_run(output_dir, timeout)
    _worker(run, ['--task',name], timeout)
    return _result(run)


def apply_revision(parent, request, *, output_dir=None, timeout=300):
    """Apply a pinned local patch; rejections are archived, never overwrite a parent.

    Returns a versioned JSON report. `ok` describes execution and constraints;
    inspect `run.proof_accepted` separately for Lean and physical_status for scope.
    """
    parent = Path(parent).expanduser().resolve()
    encoded = json.dumps(request, ensure_ascii=False, indent=2, allow_nan=False)
    run = _new_run(output_dir if output_dir is not None else parent.parent, timeout)
    (run/'revision-request.json').write_text(encoded, encoding='utf-8')
    _worker(run, ['--revision-parent',str(parent)], timeout)
    report = {'schema':'fk-revision-result-v1','ok':False,'directory':str(run),'id':run.name}
    if (run/'revision-check.json').is_file():
        report['preview'] = json.loads((run/'revision-check.json').read_text(encoding='utf-8'))
    status = json.loads((run/'status.json').read_text(encoding='utf-8')) if (run/'status.json').exists() else {'state':'failed'}
    report['state'] = status['state']
    if status['state'] == 'complete':
        report.update(ok=True, run=_result(run).to_dict(),
                      reuse=json.loads((run/'reuse.json').read_text(encoding='utf-8')))
    elif status['state'] != 'rejected':
        report['error'] = status.get('error', 'Worker failed; inspect worker.log')
    return report


def refine_visual(parent, *, output_dir=None, rounds=3, timeout=1200):
    """Run real image/render feedback from a verified saved parent; uses model API."""
    from .revision import snapshot
    if type(rounds) is not int or not 1 <= rounds <= 8:
        raise ValueError('rounds must be 1..8')
    snap = snapshot(parent)
    run = _new_run(output_dir if output_dir is not None else snap['root'].parent, timeout)
    (run/'perception-request.json').write_text(json.dumps({
        'parent_manifest_sha256':snap['identity'],'rounds':rounds}),encoding='utf-8')
    _worker(run, ['--perception-parent',str(snap['root'])],timeout)
    return _result(run)


def apply_asset(parent,library,request,*,output_dir=None,timeout=300):
    parent=Path(parent).expanduser().resolve();run=_new_run(output_dir if output_dir is not None else parent.parent,timeout)
    (run/'asset-request.json').write_text(json.dumps({'library':str(Path(library).expanduser().absolute()),'request':request},ensure_ascii=False,allow_nan=False))
    _worker(run,['--asset-target',str(parent)],timeout)
    status=json.loads((run/'status.json').read_text()) if (run/'status.json').exists() else {'state':'failed'}
    result={'ok':status['state']=='complete','id':run.name,'directory':str(run),'state':status['state']}
    if (run/'asset-reuse.json').exists():result['asset']=json.loads((run/'asset-reuse.json').read_text())
    if result['ok']:result['run']=_result(run).to_dict()
    else:result['diagnostics']=status.get('diagnostics',[])
    return result


def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description='Internal isolated Studio worker')
    parser.add_argument('--run', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--reference', choices=('phone','car','aircraft'))
    mode.add_argument('--task', choices=TASKS)
    mode.add_argument('--revision-parent', type=Path)
    mode.add_argument('--perception-parent', type=Path)
    mode.add_argument('--asset-target', type=Path)
    mode.add_argument('--asset-fixture', choices=('car','truck','aircraft','humanoid'))
    parser.add_argument('--equipment-depth', type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    from .demo.models import Request
    from .demo.pipeline import execute, write_json
    if args.asset_target:
        from .assets import AssetLibrary,prepare_instance
        from .revision import read_json
        packet=json.loads((args.run/'asset-request.json').read_text());library=AssetLibrary(packet['library'])
        try:
            report,snap,candidate,contract,equipment_override=prepare_instance(library,args.asset_target,packet['request'])
        except (ValueError,OSError,KeyError) as exc:
            report={'accepted':False,'issues':[{'code':'ASSET_REJECTED','message':str(exc)}]}
        if not report['accepted']:
            write_json(args.run/'asset-reuse.json',report)
            write_json(args.run/'status.json',{'id':args.run.name,'state':'rejected','stage':'preflight','events':[],'diagnostics':report['issues']})
            return 2
        source=library.read(report['asset_sha256'])
        original=read_json(snap,'design.json');old_equipment=read_json(snap,'equipment.json');scene=read_json(snap,'scene.json')
        report['instance_request']=packet['request']
        imported=candidate['parts'] if packet['request'].get('destination','product')=='product' else equipment_override
        report['instance_recipes']={p['id']:p for p in imported if p['id'] in report['mapping'].values()}
        write_json(args.run/'asset-reuse.json',report);write_json(args.run/'asset-source.json',source)
        cache={'read':lambda name:snap['files'][name],'design':original,'constraints':read_json(snap,'constraints.json'),
               'parts':{p['id']:p for p in original['parts']+old_equipment},'meshes':{p['id']:p for p in scene['product']+scene['equipment']},'checks':read_json(snap,'geometry-checks.json')}
        before=read_json(snap,'input.json');depth=read_json(snap,'manufacturing.json')['policy']['equipment_depth']
        execute(args.run,Request(mode='revision',visual_rounds=0,parent=read_json(snap,'result.json')['id'],equipment_depth=depth,brief=before['request']['brief']),snap['files']['image.png'],original,
                design_override=candidate,constraint_contract=contract,parent_cache_override=cache,equipment_override=equipment_override,asset_reuse_record=report,
                revision_record={'schema':'fk-asset-parent-v1','base_manifest_sha256':snap['identity'],'asset_sha256':report['asset_sha256']})
    elif args.revision_parent or args.perception_parent:
        from .revision import prepare_revision, read_json, snapshot
        if args.revision_parent:
            request = json.loads((args.run/'revision-request.json').read_text(encoding='utf-8'))
            preview, snap, candidate, contract = prepare_revision(args.revision_parent, request)
            write_json(args.run/'revision-check.json', preview)
            if not preview['accepted']:
                write_json(args.run/'status.json', {'id':args.run.name,'state':'rejected','stage':'preflight',
                                                  'events':[],'diagnostics':preview['diagnostics']})
                return 2
        else:
            request = json.loads((args.run/'perception-request.json').read_text(encoding='utf-8'))
            snap = snapshot(args.perception_parent, request['parent_manifest_sha256'])
            candidate = read_json(snap,'design.json')
            contract = read_json(snap,'constraints.json') if 'constraints.json' in snap['files'] else {'schema':'fk-constraints-v1','rules':[]}
        original = read_json(snap,'design.json'); equipment = read_json(snap,'equipment.json')
        scene = read_json(snap,'scene.json')
        cache = {'read':lambda name:snap['files'][name], 'design':original, 'constraints':contract,
                 'parts':{p['id']:p for p in original['parts']+equipment},
                 'meshes':{p['id']:p for p in scene['product']+scene['equipment']},
                 'checks':read_json(snap,'geometry-checks.json')}
        before_input = read_json(snap,'input.json')
        depth = read_json(snap,'manufacturing.json')['policy']['equipment_depth']
        parent_id = read_json(snap,'result.json')['id']
        execute(args.run, Request(mode='live' if args.perception_parent else 'revision', parent=parent_id, equipment_depth=depth,
                                  visual_rounds=request.get('rounds',0),
                                  brief=before_input['request']['brief']), snap['files']['image.png'],
                original, design_override=candidate, constraint_contract=contract,
                parent_cache_override=cache,
                revision_record={'schema':'fk-revision-v1','base_manifest_sha256':snap['identity'],
                                 'edits':request['edits']} if args.revision_parent else {'schema':'fk-perception-parent-v1','base_manifest_sha256':snap['identity']})
    elif args.asset_fixture or args.task:
        import io
        from PIL import Image
        if args.asset_fixture:
            from .asset_benchmark import fixture
            task=fixture(args.asset_fixture)
        else:task = load_task(args.task)
        image = io.BytesIO(); Image.new('RGB',(32,32),'#dce4eb').save(image,'PNG')
        write_json(args.run/'task.json', {'id':args.asset_fixture or args.task,'schema':'fk-task-v1','input':'authored parametric subsystem fixture'})
        execute(args.run, Request(mode='fixture', brief=task['design']['title']), image.getvalue(),
                design_override=task['design'], constraint_contract=task['constraints'])
    else:
        image = Path(__file__).parent/'demo/static/references'/(args.reference+'.jpg')
        execute(args.run, Request(mode='reference', reference=args.reference,
                                 equipment_depth=args.equipment_depth), image.read_bytes())
    status = json.loads((args.run/'status.json').read_text(encoding='utf-8'))
    return 0 if status['state'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(_main())
