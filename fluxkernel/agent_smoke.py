"""Reproduce the agent workflow through a real stdio client, without an LLM."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


async def exercise(workspace, *, require_proof=False):
    from mcp import Client, StdioServerParameters
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('FK_MODEL_API_KEY', None)
    env['FK_MODEL_CONFIG'] = str(root/'unused-model-config.json')
    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'fluxkernel.agent_server', '--workspace', str(root)], env=env)
    checks = {}
    async with Client(params, read_timeout_seconds=360) as client:
        tools = (await client.list_tools()).tools
        checks['thirteen_tools_discovered'] = len(tools) == 13
        specs = {t.name: t for t in tools}
        checks['write_annotations'] = not specs['apply_revision'].annotations.read_only_hint
        resources = await client.list_resources()
        checks['schemas_discovered'] = len(resources.resources) == 2
        capabilities = await client.read_resource('fluxkernel://capabilities')
        checks['scope_declared'] = json.loads(capabilities.contents[0].text)['model_calls'] is False

        async def call(name, arguments=None, *, error=False):
            result = await client.call_tool(name, arguments or {})
            assert result.is_error is error, (name, result.content)
            assert isinstance(result.structured_content, dict)
            return result.structured_content

        tasks = await call('list_tasks')
        checks['three_authored_tasks'] = len(tasks['tasks']) == 3
        base = await call('create_task', {'task': 'enclosure'})
        state = await call('inspect_run', {'run_id': base['id']})
        patch = {'schema': 'fk-revision-v1', 'base_manifest_sha256': state['manifest_sha256'],
                 'edits': [{'part': 'housing', 'set': {'wall': 3}}]}
        preview = await call('preview_revision', {'run_id': base['id'], 'request': patch})
        checks['preview_no_cad'] = preview['accepted'] and not preview['geometry_evaluated']
        child = await call('apply_revision', {'run_id': base['id'], 'request': patch})
        checks['cad_reused'] = len(child['reuse']['reused']) == 23 and child['reuse']['rebuilt'] == ['housing']
        checks['cad_bytes_identical'] = all(
            (root/base['id']/f'cad/{part}.{ext}').read_bytes() == (root/child['id']/f'cad/{part}.{ext}').read_bytes()
            for part in child['reuse']['reused'] for ext in ('step', 'stl'))
        report = await call('read_report', {'run_id': child['id'], 'report': 'constraint-checks.json'})
        checks['verified_report'] = report['integrity'] == 'manifest-verified' and report['data']['accepted']
        artifacts = await call('list_artifacts', {'run_id': child['id']})
        checks['cad_artifacts_listed'] = any(a['name'] == 'cad/housing.step' for a in artifacts['artifacts'])
        rejected = await call('apply_revision', {'run_id': base['id'], 'request': {
            **patch, 'edits': [{'part': 'housing', 'set': {'wall': 5}}]}}, error=True)
        checks['rejection_archived_no_cad'] = rejected['state'] == 'rejected' and not (root/rejected['id']/'cad').exists()
        stale = await call('preview_revision', {'run_id': base['id'], 'request': {
            **patch, 'base_manifest_sha256': '0'*64}}, error=True)
        checks['stale_parent_rejected'] = stale['diagnostics'][0]['code'] == 'REV_STALE_PARENT'
        protected = await call('apply_revision', {'run_id': base['id'], 'request': {
            **patch, 'edits': [{'part': 'housing', 'set': {'route': 'catalog'}}]}}, error=True)
        checks['protected_field_rejected'] = protected['code'] == 'MCP_INVALID_ARGUMENT'
        published = await call('publish_asset', {'run_id':base['id'], 'request': {
            'base_manifest_sha256':state['manifest_sha256'], 'name':'enclosure-payload',
            'version':'1.0.0','category':'payload','kind':'component',
            'description':'Authored smoke-test payload envelope','parts':['payload']}})
        matches = await call('search_assets', {'query':{'category':'payload'}})
        checks['asset_discovered'] = matches['matches'][0]['asset_sha256'] == published['asset_sha256']
        instance = {'base_manifest_sha256':state['manifest_sha256'],
                    'asset_sha256':published['asset_sha256'],'prefix':'smoke',
                    'query':{'category':'payload'},'position':[100,0,0]}
        preflight = await call('preview_asset', {'run_id':base['id'],'request':instance})
        imported = await call('instantiate_asset', {'run_id':base['id'],'request':instance})
        checks['asset_instantiated'] = preflight['accepted'] and imported['ok']
        checks['asset_proof_not_inherited'] = imported['asset']['proof_reused'] is False
        after = await call('inspect_run', {'run_id': base['id']})
        checks['parent_unchanged'] = state['manifest_sha256'] == after['manifest_sha256']
        history = await call('list_runs', {'limit': 100})
        checks['history_retains_attempts'] = {base['id'], child['id'], rejected['id']} <= {r['id'] for r in history['runs']}
        checks['lean_accepted'] = bool(base['proof_accepted'] and child['run']['proof_accepted'])
        # Match a returned commitment against a real local artifact.
        cad = next(a for a in artifacts['artifacts'] if a['name'] == 'cad/housing.step')
        checks['artifact_commitment_matches'] = hashlib.sha256((root/child['id']/cad['name']).read_bytes()).hexdigest() == cad['sha256']
        cad_path = root/child['id']/cad['name']
        original = cad_path.read_bytes()
        try:
            cad_path.write_bytes(b'tampered CAD')
            tampered = await call('read_report', {'run_id': child['id'], 'report': 'proof.json'}, error=True)
            checks['tampered_artifact_rejected'] = tampered['code'] == 'REV_PARENT_CHANGED'
        finally:
            cad_path.write_bytes(original)
        if checks['lean_accepted']:
            verified = subprocess.run([sys.executable, str(root/child['id']/'verify.py'), str(root/child['id'])],
                                      capture_output=True, text=True, timeout=240)
            checks['independent_verifier'] = verified.returncode == 0
        elif require_proof:
            checks['independent_verifier'] = False
    required = {k: v for k, v in checks.items() if k != 'lean_accepted' or require_proof}
    return {'schema': 'fk-mcp-smoke-v1', 'accepted': all(required.values()), 'checks': checks,
            'model_calls': 0, 'physical_status': 'unverified',
            'runs': {'baseline': base['id'], 'revision': child['id'], 'rejected': rejected['id']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--require-proof', action='store_true')
    args = parser.parse_args()
    import anyio
    async def run():
        return await exercise(args.workspace, require_proof=args.require_proof)
    report = anyio.run(run)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
