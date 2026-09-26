"""Versioned local parameter revisions with pinned parents and frozen contracts.

Public functions return JSON-compatible reports. Preflight never executes CAD or
calls a model. Applying a revision uses the isolated Studio worker.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

PATCH_FIELDS = {'size', 'position', 'rotation', 'wall'}
SCHEMA = 'fk-revision-v1'


class RevisionError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(directory, expected=None):
    """Read a content-verified snapshot once; later filesystem edits cannot change it."""
    root = Path(directory).expanduser().resolve()
    try:
        raw = (root/'manifest.json').read_bytes()
        identity = sha(raw)
        if expected is not None and identity != expected:
            raise RevisionError('REV_STALE_PARENT', 'Parent manifest differs from the requested base')
        manifest = json.loads(raw)
        if not isinstance(manifest, dict) or not 1 <= len(manifest) <= 4096:
            raise RevisionError('REV_PARENT_INVALID', 'Invalid or oversized parent manifest')
        files = {}; total = 0
        for name, checksum in manifest.items():
            if not isinstance(name, str) or not isinstance(checksum, str) or not re.fullmatch('[a-f0-9]{64}', checksum):
                raise RevisionError('REV_PARENT_INVALID', 'Malformed artifact commitment')
            path = (root/name).resolve()
            if not path.is_relative_to(root) or path == root or not path.is_file():
                raise RevisionError('REV_PARENT_INVALID', 'Artifact escapes or is missing from parent')
            total += path.stat().st_size
            if total > 512*1024*1024:
                raise RevisionError('REV_PARENT_TOO_LARGE', 'Revision snapshot exceeds 512 MiB')
            data = path.read_bytes()
            if sha(data) != checksum:
                raise RevisionError('REV_PARENT_CHANGED', f'Artifact integrity failed: {name}')
            files[name] = data
        required = {'design.json','equipment.json','scene.json','geometry-checks.json',
                    'manufacturing.json','input.json','result.json','image.png'}
        if not required <= files.keys():
            raise RevisionError('REV_PARENT_INVALID', 'Parent is not a complete design run')
        return {'root': root, 'identity': identity, 'files': files}
    except RevisionError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise RevisionError('REV_PARENT_INVALID', 'Cannot read a complete parent manifest') from exc


def read_json(snap, name):
    return json.loads(snap['files'][name])


def inspect_run(directory):
    snap = snapshot(directory)
    try:
        design = read_json(snap, 'design.json')
        contract = read_json(snap, 'constraints.json') if 'constraints.json' in snap['files'] else {'schema':'fk-constraints-v1','rules':[]}
        from .demo.constraints import evaluate
        checks = evaluate(design, contract)
        return {'schema':'fk-inspection-v1','directory':str(snap['root']),
                'manifest_sha256':snap['identity'],'title':design['title'],
                'parts':design['parts'],'constraints':contract,'constraint_checks':checks,
                'requirements':design['requirements'],'physical_status':'unverified'}
    except (KeyError, ValueError, TypeError) as exc:
        raise RevisionError('REV_PARENT_INVALID', 'Parent design or constraints are malformed') from exc


def revision_schema():
    vector = {'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3}
    return {'$schema':'https://json-schema.org/draft/2020-12/schema',
            'title':'FluxKernel local revision v1','type':'object','additionalProperties':False,
            'required':['schema','base_manifest_sha256','edits'],
            'properties':{'schema':{'const':SCHEMA},
                'base_manifest_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'},
                'edits':{'type':'array','minItems':1,'maxItems':64,'items':{
                    'type':'object','additionalProperties':False,'required':['part','set'],
                    'properties':{'part':{'type':'string','pattern':'^[a-z][a-z0-9_-]{0,47}$'},
                        'set':{'type':'object','additionalProperties':False,'minProperties':1,
                               'properties':{'size':vector,'position':vector,'rotation':vector,
                                             'wall':{'type':'number','minimum':0.4,'maximum':1000}}}}}}}}


def validate_request(request):
    from .demo.constraints import number
    if not isinstance(request, dict) or set(request) != {'schema','base_manifest_sha256','edits'} or request['schema'] != SCHEMA:
        raise RevisionError('REV_REQUEST_INVALID', 'Expected fk-revision-v1 with only base_manifest_sha256 and edits')
    if not isinstance(request['base_manifest_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', request['base_manifest_sha256']):
        raise RevisionError('REV_REQUEST_INVALID', 'Expected a pinned SHA-256 parent manifest')
    edits = request['edits']
    if not isinstance(edits, list) or not 1 <= len(edits) <= 64:
        raise RevisionError('REV_REQUEST_INVALID', 'Expected 1..64 local edits')
    seen = set()
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'part','set'} or not isinstance(edit['part'], str):
            raise RevisionError('REV_REQUEST_INVALID', 'Each edit needs a part and a set object')
        if not re.fullmatch('[a-z][a-z0-9_-]{0,47}', edit['part']):
            raise RevisionError('REV_REQUEST_INVALID', 'Part identity is malformed')
        if edit['part'] in seen:
            raise RevisionError('REV_REQUEST_INVALID', 'A part may appear only once per request')
        seen.add(edit['part'])
        fields = edit['set']
        if not isinstance(fields, dict) or not fields or not fields.keys() <= PATCH_FIELDS:
            raise RevisionError('REV_PROTECTED_FIELD', 'Only size, position, rotation and wall may change')
        for key, value in fields.items():
            if key == 'wall':
                valid = number(value) and 0.4 <= value <= 1000
            else:
                valid = isinstance(value, list) and len(value) == 3 and all(number(v) for v in value)
            if not valid:
                raise RevisionError('REV_REQUEST_INVALID', 'Patch values must be finite numeric dimensions')


def prepare_revision(directory, request):
    """Internal: return a preflight report and verified input snapshot/candidate."""
    from .demo.models import Design
    from .demo.constraints import evaluate
    from .demo.references import equipment_parts
    report = {'schema':'fk-revision-preview-v1','accepted':False,'stage':'preflight',
              'geometry_evaluated':False,'physical_status':'unverified','diagnostics':[]}
    snap = None; candidate = None; contract = None
    try:
        validate_request(request)
        snap = snapshot(directory, request['base_manifest_sha256'])
        original = read_json(snap, 'design.json')
        candidate = copy.deepcopy(original)
        by_id = {p['id']:p for p in candidate['parts']}
        for edit in request['edits']:
            if edit['part'] not in by_id:
                raise RevisionError('REV_UNKNOWN_PART', f"Unknown product part: {edit['part']}")
            part = by_id[edit['part']]
            if part['route'] == 'catalog':
                raise RevisionError('REV_CATALOG_IMMUTABLE', 'Catalog geometry needs a qualified replacement, not a local resize')
            if any(part[field] != value for field,value in edit['set'].items()):
                part.update(copy.deepcopy(edit['set']))
                part['source'] = 'selected'
        try:
            candidate = Design.model_validate(candidate).model_dump()
        except ValueError as exc:
            raise RevisionError('REV_GEOMETRY_PARAMETERS', str(exc)[:1200]) from exc
        contract = read_json(snap, 'constraints.json') if 'constraints.json' in snap['files'] else {'schema':'fk-constraints-v1','rules':[]}
        before_checks, after_checks = evaluate(original, contract), evaluate(candidate, contract)
        old_equipment = read_json(snap, 'equipment.json')
        depth = read_json(snap, 'manufacturing.json')['policy']['equipment_depth']
        machine_parts = [p for p in Design.model_validate(candidate).parts if p.route == 'machine']
        new_equipment = [p.model_dump() for p in equipment_parts(machine_parts)] if machine_parts and depth else []
        old = {p['id']:p for p in original['parts'] + old_equipment}
        new = {p['id']:p for p in candidate['parts'] + new_equipment}
        changed = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
        unchanged = sorted(k for k in old.keys() & new.keys() if old[k] == new[k])
        affected = set(changed)
        steps = read_json(snap, 'manufacturing.json')['steps']
        for part in changed:
            if part in by_id and by_id[part]['route'] == 'machine': affected.add(part+'-blank')
        while True:
            expanded = affected | {s['id'] for s in steps if set(s['deps']) & affected}
            if expanded == affected: break
            affected = expanded
        report.update(base_manifest_sha256=snap['identity'], constraints_before=before_checks,
                      constraints_after=after_checks, changed=changed, unchanged=unchanged,
                      added=sorted(new.keys()-old.keys()), removed=sorted(old.keys()-new.keys()),
                      equipment_changed=sorted(k for k in changed if k.startswith('cell-')),
                      structural_dependents=sorted(affected),
                      evidence={'reuse_candidates':unchanged,
                                'regenerate':['manufacturing.json','ManufacturingPlan.lean','proof.json','constraint-checks.json'],
                                'receipts':'all input-bound receipts regenerated','proof_reused':False})
        for check in after_checks['checks']:
            if not check['passed']:
                report['diagnostics'].append({'code':'REV_CONSTRAINT_FAILED','constraint':check['id'],
                                              'message':check['detail']})
        report['accepted'] = after_checks['accepted']
    except RevisionError as exc:
        report['diagnostics'].append({'code':exc.code,'message':str(exc)})
    except (KeyError, ValueError, TypeError) as exc:
        report['diagnostics'].append({'code':'REV_PARENT_INVALID','message':'Invalid parent design or constraint data'})
    return report, snap, candidate, contract


def preview_revision(directory, request):
    return prepare_revision(directory, request)[0]
