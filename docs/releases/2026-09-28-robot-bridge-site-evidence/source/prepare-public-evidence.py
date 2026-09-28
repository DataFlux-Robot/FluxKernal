"""Export only public, path-free robot bridge evidence and attributed renders."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

kernel = Path(sys.argv[1]).resolve()
source = kernel / 'docs/releases/2026-09-28-v0.10-evidence'
output = Path(__file__).resolve().parents[1] / 'public/fluxkernel/native-robots'
output.mkdir(parents=True, exist_ok=True)
summary = json.loads((source / 'summary.json').read_text())
result = {
    'schema': 'fluxkernel-public-robot-bridge-v1',
    'published': '2026-09-28',
    'design_authority': 'FluxKernel native robot.json; Lean and URDF/MJCF are generated branches',
    'workflow_commit': '2b90ae3650ea474a2df891994467171fe8e22a49',
    'local_tests_passed': 272,
    'lean_scope': ['unique body/joint identities', 'acyclic ordered parents', 'nonnegative declared mass', 'joint references and ordered limits', 'driven-joint coverage', 'controller plant binding'],
    'numerical_projection_scope': 'Three configurations compare frames, COM, mass, inertia and mesh bounds/centroids; not a formal equivalence theorem',
    'not_implemented': ['bidirectional lossless Lean/URDF conversion', 'general URDF import interface', 'Lean proof of kinematic export equivalence'],
    'physical_status': 'unverified',
    'personalization': {'model': 'glm-5.3-flash', 'max_rounds_per_run': 3, 'model_owns': ['geometry', 'symmetry', 'revision', 'review', 'selection'], 'development_runs': 10, 'archived_provider_responses': 45, 'scope': 'Additive head accessory. Final two runs are a frozen workflow; earlier debugging, rejected, interrupted and superseded runs retained privately.'},
    'robots': {}
}
for platform, fields in summary.items():
    checks = json.loads((source / platform / 'independent.json').read_text())
    assert checks['verification']['proof_reexecuted'] and checks['projection']['accepted'] and checks['parent_unchanged']
    result['robots'][platform] = {**fields, 'verification': checks, 'mass_basis': 'Uniform solid CAD and nominal polymer density; not measured printed mass', 'interface_status': 'unverified', 'deployment_ready': False}
    shutil.copyfile(source / platform / 'head.png', output / f'{platform}-head.png')
    shutil.copyfile(source / f'{platform}-source-LICENSE.txt', output / f'{platform}-LICENSE.txt')
(output / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
(output / 'sources.json').write_text(json.dumps({
    'microduck': {'repository': 'https://github.com/pollen-robotics/microduck_rl', 'commit': '1e79c29c97d8b38aee9eefde77a545860ba7658e', 'license': 'Apache-2.0', 'notice': 'microduck-LICENSE.txt'},
    'xgoduck': {'repository': 'https://github.com/LuwuDynamics/xgoduck_rl', 'commit': '326d77a1122870bdefa2c36403937502c958e69c', 'license': 'Apache-2.0', 'notice': 'xgoduck-LICENSE.txt'},
    'render_attribution': 'Renders derive from the pinned RL models with a new GLM-designed additive accessory. Separate XGO hardware source files are not distributed.'
},indent=2)+'\n')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file() and p.name!='manifest.json'}
(output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f'Exported {len(manifest)} public evidence files to {output}')
