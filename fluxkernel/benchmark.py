"""Small curated revision regression suite, not a general intelligence benchmark."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from .revision import inspect_run, preview_revision, snapshot
from .studio import TASKS, generate_task, load_task, apply_revision


def run_benchmark(output_dir):
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic(); cases = []
    for name in TASKS:
        task = load_task(name)
        baseline = generate_task(name, output_dir=root/'runs')
        parent = Path(baseline.directory)
        identity = inspect_run(parent)['manifest_sha256']
        patch = {'schema':'fk-revision-v1','base_manifest_sha256':identity,'edits':task['valid_edits']}
        preview = preview_revision(parent, patch)
        changed = apply_revision(parent, patch)
        rejected = apply_revision(parent, {**patch,'edits':task['invalid_edits']})
        tests = {'baseline_lean':baseline.proof_accepted,
                 'valid_preflight':preview['accepted'],
                 'valid_run':changed['ok'],
                 'invalid_rejected':rejected['state']=='rejected',
                 'rejection_has_no_cad':not (Path(rejected['directory'])/'cad').exists(),
                 'parent_unchanged':snapshot(parent)['identity']==identity}
        if changed['ok']:
            child = Path(changed['directory'])
            tests['child_lean'] = changed['run']['proof_accepted']
            tests['reuse_agrees_with_preview'] = sorted(changed['reuse']['reused']) == sorted(preview['unchanged'])
            tests['cad_reuse_exact'] = all((parent/f'cad/{part}.{ext}').read_bytes() == (child/f'cad/{part}.{ext}').read_bytes()
                                           for part in changed['reuse']['reused'] for ext in ('step','stl'))
            tests['contract_preserved'] = (parent/'constraints.json').read_bytes() == (child/'constraints.json').read_bytes()
            tests['requirements_preserved'] = json.loads((parent/'design.json').read_text())['requirements'] == json.loads((child/'design.json').read_text())['requirements']
            tests['proof_rebuilt'] = json.loads((parent/'proof.json').read_text())['plan_sha256'] != json.loads((child/'proof.json').read_text())['plan_sha256']
            checked = subprocess.run([sys.executable, str(child/'verify.py'), str(child)], capture_output=True, text=True, timeout=240)
            tests['independent_bundle_verifier'] = checked.returncode == 0
        cases.append({'task':name,'accepted':all(tests.values()),'checks':tests,
                      'baseline':baseline.to_dict(),'revision':changed,'rejected':rejected})
    report = {'schema':'fk-revision-benchmark-v1','kind':'curated-regression-suite',
              'accepted':all(c['accepted'] for c in cases),'cases':cases,
              'elapsed_s':round(time.monotonic()-started,2),'model_calls':0,
              'scope':'Three authored nominal-interface tasks; no physical testing or general image benchmark'}
    path = root/'benchmark.json'
    if path.exists():
        # Each invocation owns a distinct summary; prior benchmark evidence survives.
        import uuid
        path = root/f'benchmark-{uuid.uuid4().hex[:8]}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return {**report,'report_path':str(path)}
