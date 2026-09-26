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
    args = parser.parse_args()
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
        spec = str(wheel) + ('[demo]' if args.studio else '')
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
        print(json.dumps({'wheel': wheel.name, 'isolated_install': True, 'core_workflow': 'passed',
                          'studio_and_independent_lean': 'passed' if args.studio else 'not requested'}))


if __name__ == '__main__':
    main()
