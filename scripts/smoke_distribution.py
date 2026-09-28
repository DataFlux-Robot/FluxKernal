#!/usr/bin/env python3
"""Install the built wheel in a fresh environment and exercise it outside the repo.
Run `python -m build` first; --studio also generates CAD and rechecks actual Lean.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path)
    parser.add_argument('--studio', action='store_true')
    parser.add_argument('--agent', action='store_true', help='Also exercise a real MCP stdio client; implies --studio')
    args = parser.parse_args()
    args.studio = args.studio or args.agent
    wheels = sorted((Path(__file__).resolve().parents[1] / 'dist').glob('fluxkernel-*.whl'))
    wheel = (args.wheel or (wheels[-1] if wheels else Path('missing.whl'))).resolve()
    if not wheel.is_file(): parser.error('Build a wheel first: python -m build')
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('FK_MODEL_API_KEY', None)
    with tempfile.TemporaryDirectory(prefix='fk-wheel-smoke-') as directory:
        # macOS /var aliases /private/var; Windows TEMP can use an 8.3 name.
        work = Path(directory).resolve(); environment = work / 'venv'
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        fk = environment / ('Scripts/fk.exe' if os.name == 'nt' else 'bin/fk')
        env['FK_MODEL_CONFIG'] = str(work / 'no-model-config.json')
        env['FK_DEMO_DATA'] = str(work / 'runs')
        spec = str(wheel) + ('[demo,agent]' if args.agent else '[demo]' if args.studio else '')
        def run(command):
            p = subprocess.run([str(x) for x in command], cwd=work, env=env,
                               capture_output=True, text=True, timeout=600)
            if p.returncode:
                raise RuntimeError(f'{command[0]} failed ({p.returncode})\n{p.stdout}\n{p.stderr}')
            return p.stdout
        installer = ([shutil.which('uv'), 'pip', 'install', '--python', python, spec]
                     if shutil.which('uv') else [python, '-m', 'pip', 'install', spec])
        run(installer)
        installed = run([python, '-c', 'from fluxkernel.runtime import assets_root; print(assets_root())']).strip()
        assert Path(installed).resolve().is_relative_to(environment.resolve()) and Path(installed).name == '_assets', installed
        report = json.loads(run([fk, 'doctor', '--json']))
        assert report['ok']
        schema = json.loads(run([fk, 'schema', 'revision']))
        assert schema['properties']['schema']['const'] == 'fk-revision-v1'
        for name in ('publish','query','instance'):
            asset_schema = json.loads(run([fk, 'schema', 'asset-'+name, '--json']))
            assert asset_schema['type'] == 'object'
        if not args.studio:
            run([python, '-c', "import importlib.util; assert importlib.util.find_spec('OCP') is None; assert importlib.util.find_spec('numpy') is None"])
        for command in [('example',), ('init',), ('run', 'hello.fcad'), ('verify',)]:
            run([fk, *command])
        one = json.loads(run([fk, 'show', 'housing-v1', '--json']))
        two = json.loads(run([fk, 'show', 'housing-v2', '--json']))
        assert one != two
        if args.studio:
            result = json.loads(run([fk, 'demo', '--reference', 'phone', '--require-proof', '--json']))
            assert result['mode'] == 'reference' and result['proof_accepted']
            output = Path(result['directory'])
            manifest = json.loads((output / 'manifest.json').read_text())
            assert not any('.lake' in Path(name).parts for name in manifest)
            assert len(list((output / 'cad').glob('*.step'))) == result['counts']['parts'] + result['counts']['equipment_parts']
            run([python, output / 'verify.py', output])
            # A changed artifact must fail independent verification.
            (output / 'image.png').write_bytes(b'tampered')
            rejected = subprocess.run([str(python), str(output / 'verify.py'), str(output)],
                                      cwd=work, env=env, capture_output=True, text=True, timeout=30)
            assert rejected.returncode != 0 and 'Manifest mismatch' in rejected.stderr
            benchmark = json.loads(run([fk, 'benchmark', '--output', str(work/'benchmark'), '--json']))
            assert benchmark['accepted'] and benchmark['model_calls'] == 0
            assert len(benchmark['cases']) == 3
            # Exercise the shipped PAL renderer/selection with a declared mock, no API.
            run([python, '-c', '''
from pathlib import Path
from fluxkernel.demo.models import Design
from fluxkernel.studio import load_task
from fluxkernel.demo import perception as p
from PIL import Image
import io,json
root=Path('pal-package-check');root.mkdir()
image=io.BytesIO();Image.new('RGB',(32,32),'white').save(image,'PNG')
p.vision.model_config=lambda:{'model':'glm-5.3-flash','api_key':''}
review={'silhouette':85,'proportions':85,'layout':85,'reference_limitations':'Mock integration test','findings':[]}
review['numeric_claims']=[{'part':'housing','field':'wall','value':2}]
plan={'symmetry':'uncertain','axis':'y','plane_offset':0,'confidence':.1,'rationale':'Mock package test','visible_evidence':['Mock'],'exceptions':[],'pairs':[],'parameterization':[],'stages':['proportions']}
decision={'selected_round':0,'next_step':'stop','stage':'proportions','reason':'Mock package test'}
responses=iter([plan,review,decision])
p.vision._call=lambda *a:(json.dumps(next(responses)),{'usage':{},'model':'glm-5.3-flash'})
design=Design.model_validate(load_task('enclosure')['design'])
chosen,report=p.run_loop(design,image.getvalue(),'fixture',root,lambda *a:None,contract=load_task('enclosure')['constraints'],rounds=1)
assert chosen==design and report['reviewed'] and report['quality_status']=='model-threshold-met'
assert (root/'perception/round-00/views.png').exists()
assert report['model_calls']==3 and (root/'perception/skill.md').exists()
'''])
        if args.agent:
            agent = json.loads(run([python, '-m', 'fluxkernel.agent_smoke', '--workspace',
                                   str(work/'agent-runs'), '--require-proof']))
            assert agent['accepted'] and agent['model_calls'] == 0
        print(json.dumps({'wheel': wheel.name, 'isolated_install': True, 'core_workflow': 'passed',
                          'studio_and_independent_lean': 'passed' if args.studio else 'not requested',
                          'mcp_stdio_workflow': 'passed' if args.agent else 'not requested'}))


if __name__ == '__main__':
    main()
