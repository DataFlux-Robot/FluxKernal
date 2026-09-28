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
    'schema': 'fluxkernel-public-robot-bridge-v2',
    'published': '2026-09-28',
    'local_tests_passed': 272,
    'capabilities': ['Scoped Lean 4 validation', 'URDF/MJCF export', 'Robot personalization'],
    'limitations': ['Not bidirectional lossless Lean/URDF conversion', 'No complete geometry or physical performance proof'],
    'physical_status': 'unverified',
    'personalization': {'model': 'glm-5.3-flash', 'max_rounds_per_run': 3, 'scope': 'Model-designed additive head accessory prototypes'},
    'robots': {}
}
for platform, fields in summary.items():
    checks = json.loads((source / platform / 'independent.json').read_text())
    assert checks['verification']['proof_reexecuted'] and checks['projection']['accepted'] and checks['parent_unchanged']
    # Public capability summary only; proof records and implementation stay private.
    public_fields = ('status', 'model', 'model_calls', 'max_rounds', 'selected_round', 'visual_status', 'added_mass_kg')
    result['robots'][platform] = {
        **{key: fields[key] for key in public_fields},
        'engineering_checks': 'passed', 'export_checks': 'passed',
        'mass_basis': 'Nominal CAD estimate; not measured printed mass',
        'interface_status': 'unverified', 'deployment_ready': False,
    }
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
