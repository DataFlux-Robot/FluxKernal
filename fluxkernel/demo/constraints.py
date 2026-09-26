"""Versioned nominal geometry checks. Standard library, also shipped in bundles.

These checks cover declared dimensions/envelopes only, not tolerance stacks,
material behavior or physical assembly. EPS is a numerical comparison tolerance.
"""
from __future__ import annotations

import math

SCHEMA = 'fk-constraints-v1'
EPS = 1e-9
FIELDS = {'dimension': {'part', 'measure', 'min', 'max'},
          'inside-shell': {'container', 'item', 'min'},
          'radial-fit': {'shaft', 'sleeve', 'min', 'max'},
          'axis-distance': {'first', 'second', 'axis', 'min', 'max'}}


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_contract(contract):
    if not isinstance(contract, dict) or set(contract) != {'schema', 'rules'} or contract['schema'] != SCHEMA:
        raise ValueError('Invalid constraint schema')
    rules = contract['rules']
    if not isinstance(rules, list) or len(rules) > 128:
        raise ValueError('Expected at most 128 constraint rules')
    ids = set()
    for rule in rules:
        if not isinstance(rule, dict) or rule.get('kind') not in FIELDS:
            raise ValueError('Unknown constraint kind')
        if set(rule) != {'id', 'kind'} | FIELDS[rule['kind']]:
            raise ValueError('Constraint fields must match the declared rule kind')
        ident = rule['id']
        if not isinstance(ident, str) or not 1 <= len(ident) <= 80 or ident in ids:
            raise ValueError('Constraint IDs must be nonempty and unique')
        ids.add(ident)
        if not number(rule['min']) or ('max' in rule and (not number(rule['max']) or rule['max'] < rule['min'])):
            raise ValueError('Constraint bounds must be finite and ordered')
        if rule['kind'] != 'dimension' and rule['min'] < 0:
            raise ValueError('Clearances and distances cannot have negative minimums')
        for key in FIELDS[rule['kind']] - {'min', 'max'}:
            if not isinstance(rule[key], str) or not rule[key]:
                raise ValueError('Constraint references must be strings')
        if rule['kind'] == 'dimension' and rule['measure'] not in ('size.x', 'size.y', 'size.z', 'wall'):
            raise ValueError('Unsupported dimension measure')
        if rule['kind'] == 'axis-distance' and rule['axis'] not in ('x', 'y', 'z'):
            raise ValueError('Unsupported distance axis')
    return contract


def evaluate(design, contract):
    validate_contract(contract)
    ids = set()
    for part in design['parts']:
        if part['id'] in ids:
            raise ValueError('Duplicate part identity')
        ids.add(part['id'])
        for field in ('size','position','rotation'):
            values = part[field]
            if not isinstance(values,list) or len(values) != 3 or not all(number(v) for v in values):
                raise ValueError('Geometry inputs must be finite three-dimensional vectors')
        if min(part['size']) <= 0 or not number(part['wall']) or part['wall'] <= 0:
            raise ValueError('Geometry dimensions must be positive and finite')
    parts = {p['id']: p for p in design['parts']}
    checks = []
    for rule in contract['rules']:
        value = None
        detail = ''
        try:
            kind = rule['kind']
            if kind == 'dimension':
                part = parts[rule['part']]
                if rule['measure'] == 'wall' and part['shape'] not in ('shell','tube','frame'):
                    raise ValueError('No uniform-wall measurement exists for this recipe')
                value = part['wall'] if rule['measure'] == 'wall' else part['size']['xyz'.index(rule['measure'][-1])]
            elif kind == 'inside-shell':
                outer, inner = parts[rule['container']], parts[rule['item']]
                if outer['shape'] != 'shell' or inner['shape'] != 'box':
                    raise ValueError('Requires a shell container and a box envelope')
                if any(abs(v) > EPS for p in (outer, inner) for v in p['rotation']):
                    raise ValueError('Rotated containment is not supported by this checker')
                gaps = []
                for axis in range(3):
                    bottom = outer['position'][axis] - outer['size'][axis]/2 + outer['wall']
                    top = outer['position'][axis] + outer['size'][axis]/2 - (outer['wall'] if axis < 2 else 0)
                    gaps += [inner['position'][axis] - inner['size'][axis]/2 - bottom,
                             top - inner['position'][axis] - inner['size'][axis]/2]
                value = min(gaps)
                detail = 'Minimum nominal gap to cavity walls, floor and open-top plane'
            elif kind == 'radial-fit':
                shaft, sleeve = parts[rule['shaft']], parts[rule['sleeve']]
                if shaft['shape'] != 'cylinder' or sleeve['shape'] != 'tube':
                    raise ValueError('Requires a cylinder shaft and a tube sleeve')
                if any(abs(v) > EPS for p in (shaft, sleeve) for v in p['rotation']):
                    raise ValueError('Only unrotated, coaxial Z-axis fits are supported')
                if any(abs(shaft['position'][a] - sleeve['position'][a]) > EPS for a in (0, 1)):
                    raise ValueError('Shaft and sleeve are not coaxial')
                if abs(shaft['position'][2]-sleeve['position'][2]) + sleeve['size'][2]/2 > shaft['size'][2]/2 + EPS:
                    raise ValueError('Shaft does not cover the sleeve axial span')
                value = sleeve['size'][0] - 2*sleeve['wall'] - shaft['size'][0]
                detail = 'Nominal diametric clearance; no tolerance or running-performance claim'
            else:
                first, second = parts[rule['first']], parts[rule['second']]
                axis = 'xyz'.index(rule['axis'])
                value = abs(first['position'][axis] - second['position'][axis])
                detail = 'Center-to-center separation on the declared world axis only'
            if not number(value):
                raise ValueError('Non-finite measured dimension')
            passed = value >= rule['min'] - EPS and ('max' not in rule or value <= rule['max'] + EPS)
            if not passed:
                detail = f"Measured {value:.9g} mm is outside the frozen bounds"
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            passed = False
            detail = str(exc)
        checks.append({'id': rule['id'], 'kind': rule['kind'], 'passed': passed,
                       'value_mm': value, 'min_mm': rule['min'], 'max_mm': rule.get('max'), 'detail': detail})
    return {'schema': 'fk-constraint-report-v1', 'accepted': all(c['passed'] for c in checks),
            'coverage': 'declared-nominal-constraints' if checks else 'no-numeric-constraints-declared',
            'checks': checks, 'physical_validation': 'not-performed'}
