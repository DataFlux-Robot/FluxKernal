"""JSON-first interface for bounded, versioned agent operations."""
import json
from pathlib import Path


def emit(value, as_json):
    # Both forms remain machine-readable; --json is explicit for agent callers.
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_schema(args):
    from ..revision import revision_schema
    from ..asset_api import asset_schema
    emit(revision_schema() if args.name=='revision' else asset_schema(args.name.removeprefix('asset-')), True)
    return 0


def cmd_inspect(args):
    from ..revision import inspect_run, RevisionError
    try:
        report = inspect_run(args.parent)
    except RevisionError as exc:
        emit({'ok':False,'code':exc.code,'error':str(exc)}, args.json)
        return 1
    emit(report, args.json)
    return 0


def cmd_task(args):
    from ..studio import generate_task, StudioError
    try:
        result = generate_task(args.name, output_dir=args.output)
        emit(result.to_dict(), args.json)
        return 1 if args.require_proof and not result.proof_accepted else 0
    except (StudioError, ValueError, OSError, ImportError) as exc:
        emit({'ok':False,'error':str(exc)}, args.json)
        return 1


def cmd_revise(args):
    from ..revision import preview_revision
    from ..studio import apply_revision, StudioError
    try:
        request = json.loads(Path(args.patch).read_text(encoding='utf-8'))
        result = preview_revision(args.parent, request) if args.preview else apply_revision(args.parent, request)
        emit(result, args.json)
        if args.preview:
            return 0 if result['accepted'] else 2
        if result['state'] == 'rejected': return 2
        if not result['ok']: return 1
        return 1 if args.require_proof and not result['run']['proof_accepted'] else 0
    except (StudioError, ValueError, OSError, ImportError) as exc:
        emit({'ok':False,'error':str(exc)}, args.json)
        return 1


def cmd_benchmark(args):
    from ..benchmark import run_benchmark
    from ..studio import StudioError
    try:
        report = run_benchmark(args.output)
    except (StudioError, ValueError, OSError, ImportError) as exc:
        emit({'schema':'fk-revision-benchmark-v1','accepted':False,'error':str(exc)}, args.json)
        return 1
    if args.json:
        emit(report, True)
    else:
        for case in report['cases']:
            print(f"{'PASS' if case['accepted'] else 'FAIL'} {case['task']}: {sum(case['checks'].values())}/{len(case['checks'])} checks")
        print(f"Report: {report['report_path']}\nModel calls: 0; physical testing: not performed")
    return 0 if report['accepted'] else 1


def cmd_perceive(args):
    from ..studio import refine_visual, StudioError
    try:
        run = refine_visual(args.parent,output_dir=args.output,rounds=args.rounds,timeout=1500)
        summary = json.loads((Path(run.directory)/'perception/summary.json').read_text())
        emit({**run.to_dict(),'perception':summary},args.json)
        return 1 if args.require_proof and not run.proof_accepted else 0
    except (StudioError,ValueError,OSError,ImportError) as exc:
        emit({'ok':False,'error':str(exc)},args.json)
        return 1


def register(sub):
    from .asset_cli import register as register_assets
    register_assets(sub)
    from ..studio import TASKS
    p = sub.add_parser('perceive', help='run real image/render feedback on a saved parent (model API calls)')
    p.add_argument('parent'); p.add_argument('--rounds',type=int,choices=range(1,9),default=3)
    p.add_argument('--output'); p.add_argument('--json',action='store_true')
    p.add_argument('--require-proof',action='store_true'); p.set_defaults(fn=cmd_perceive)
    p = sub.add_parser('schema', help='print a versioned agent request schema')
    p.add_argument('name', choices=('revision','asset-publish','asset-query','asset-instance')); p.add_argument('--json',action='store_true'); p.set_defaults(fn=cmd_schema)
    p = sub.add_parser('inspect', help='verify and inspect a completed Studio run')
    p.add_argument('parent'); p.add_argument('--json', action='store_true'); p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser('task', help='build a frozen engineering fixture without a model')
    p.add_argument('name', choices=TASKS); p.add_argument('--output')
    p.add_argument('--json', action='store_true'); p.add_argument('--require-proof', action='store_true')
    p.set_defaults(fn=cmd_task)
    p = sub.add_parser('revise', help='preview/apply a pinned parameter patch; preserve constraints')
    p.add_argument('parent'); p.add_argument('--patch', required=True)
    p.add_argument('--preview', action='store_true'); p.add_argument('--json', action='store_true')
    p.add_argument('--require-proof', action='store_true'); p.set_defaults(fn=cmd_revise)
    p = sub.add_parser('benchmark', help='run the three curated CAD + Lean revision tasks')
    p.add_argument('--output', required=True); p.add_argument('--json', action='store_true')
    p.set_defaults(fn=cmd_benchmark)
