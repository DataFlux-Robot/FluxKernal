"""Cross-product asset operations; no implicit model calls."""
import json
from pathlib import Path

def command(args):
    from ..studio import StudioError
    try:
        from ..assets import AssetLibrary,publish,prepare_instance
        from ..studio import apply_asset
        lib=AssetLibrary(args.library) if hasattr(args,'library') else None
        read=lambda path:json.loads(Path(path).read_text())
        if args.asset_command=='publish':result=publish(lib,args.source,read(args.spec))
        elif args.asset_command=='search':result=lib.search(read(args.query),args.limit)
        elif args.asset_command=='inspect':result=lib.read(args.identity)
        elif args.asset_command=='preview':result=prepare_instance(lib,args.target,read(args.request))[0]
        elif args.asset_command=='apply':result=apply_asset(args.target,args.library,read(args.request),output_dir=args.output)
        else:
            from ..asset_benchmark import run_asset_benchmark
            result=run_asset_benchmark(args.output)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        if result.get('accepted') is False or result.get('ok') is False:return 2
        if getattr(args,'require_proof',False) and not result['run']['proof_accepted']:return 1
        return 0
    except (StudioError,ImportError,ValueError,OSError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));return 1

def register(sub):
    root=sub.add_parser('asset',help='Share, match and instantiate cross-product design assets')
    modes=root.add_subparsers(dest='asset_command',required=True)
    for name in ('publish','search','inspect','preview','apply','benchmark'):
        p=modes.add_parser(name);p.set_defaults(fn=command)
        if name!='benchmark':p.add_argument('--library',required=True)
        if name=='apply':p.add_argument('--require-proof',action='store_true')
        p.add_argument('--json',action='store_true')
        if name=='publish':p.add_argument('source');p.add_argument('--spec',required=True)
        if name=='search':p.add_argument('--query',required=True);p.add_argument('--limit',type=int,default=20)
        if name=='inspect':p.add_argument('identity')
        if name in ('preview','apply'):p.add_argument('target');p.add_argument('--request',required=True)
        if name in ('apply','benchmark'):p.add_argument('--output',required=True)
