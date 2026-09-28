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
    parser.add_argument('--robot', action='store_true', help='Exercise native robot IR and projections from the installed wheel')
    parser.add_argument('--personalize', action='store_true', help='Exercise finite accessory CAD and native attachment; implies --robot, no model calls')
    args = parser.parse_args()
    args.robot = args.robot or args.personalize
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
        extras = (['demo','agent'] if args.agent else ['demo'] if args.studio else []) + (['robot'] if args.robot else [])
        if args.personalize: extras.append('personalize')
        spec = str(wheel) + ('['+','.join(extras)+']' if extras else '')
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
        if not args.studio and not args.robot:
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
        if args.robot:
            run([python, '-c', """
from pathlib import Path
import mujoco
from fluxkernel.robotics.native import from_mujoco
from fluxkernel.robotics.bundle import finish,verify
from fluxkernel.robotics.validation import check_projection
root=Path('native-smoke');root.mkdir();(root/'upstream').mkdir()
xml='<mujoco><worldbody><body name="base"><geom type="box" size=".1 .1 .1" mass="1"/><body name="arm" pos=".2 0 0"><joint name="hinge"/><geom type="box" size=".1 .02 .02" mass=".1"/></body></body></worldbody></mujoco>'
(root/'upstream/robot.xml').write_text(xml)
r=from_mujoco(mujoco.MjModel.from_xml_string(xml),{'name':'smoke','directory':'.','entry':'robot.xml'},root/'meshes')
result=finish(r,root)
assert result['proof_accepted']
assert verify(root,True)['accepted']
assert check_projection(root)['accepted']
"""])
        if args.agent:
            agent = json.loads(run([python, '-m', 'fluxkernel.agent_smoke', '--workspace',
                                   str(work/'agent-runs'), '--require-proof']))
            assert agent['accepted'] and agent['model_calls'] == 0
        if args.personalize:
            run([python, '-c', '''
from pathlib import Path
import mujoco
from fluxkernel.robotics.native import from_mujoco
from fluxkernel.robotics.bundle import finish,verify
from fluxkernel.robotics.attachment import zone,attach
from fluxkernel.robotics.validation import check_projection
from fluxkernel.robotics import personalize
assert (Path(personalize.__file__).parents[1]/'demo/skills/robot-personalization/SKILL.md').is_file()
root=Path('accessory-smoke');root.mkdir();(root/'upstream').mkdir()
xml='<mujoco><asset><mesh name="cap" vertex="-.02 -.02 -.02 .02 -.02 -.02 -.02 .02 -.02 .02 .02 -.02 -.02 -.02 .02 .02 -.02 .02 -.02 .02 .02 .02 .02 .02"/></asset><worldbody><body name="head"><geom type="mesh" mesh="cap" group="2" mass="1"/></body></worldbody></mujoco>'
(root/'upstream/robot.xml').write_text(xml)
r=from_mujoco(mujoco.MjModel.from_xml_string(xml),{'name':'fixture','directory':'.','entry':'robot.xml'},root/'meshes')
finish(r,root)
z=zone(root,'cap')
recipe={'schema_version':'fk-robot-part-v1','zone_sha256':z['zone_sha256'],'name':'fixture','rationale':'Authored package test; no model calls','symmetry':'none','material':'pla','color_rgb':[.2,.7,.9],'base_size_mm':[16.,16.,2.],'features':[{'shape':'ellipsoid','size_mm':[8.,8.,10.],'center_mm':[0.,0.,6.],'rotation_deg':[0.,0.,0.]}]}
result=attach(root,recipe,Path('variants'),'cap')
assert result['accepted'] and result['proof_accepted'] and not result['deployment_ready']
assert verify(result['directory'],True)['accepted']
assert check_projection(result['directory'])['accepted']
assert (Path(result['directory'])/'cad/custom_fixture/part.step').is_file()
'''])
        print(json.dumps({'wheel': wheel.name, 'isolated_install': True, 'native_robot': 'passed' if args.robot else 'not requested', 'core_workflow': 'passed',
                          'accessory_cad_fixture': 'passed' if args.personalize else 'not requested',
                          'studio_and_independent_lean': 'passed' if args.studio else 'not requested',
                          'mcp_stdio_workflow': 'passed' if args.agent else 'not requested'}))


if __name__ == '__main__':
    main()
