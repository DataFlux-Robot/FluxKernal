"""Nominal interface checks run without CAD, a model or a Lean installation."""
import copy
import math
import pytest
from fluxkernel.demo.constraints import evaluate, validate_contract
from fluxkernel.studio import TASKS, load_task
from fluxkernel.revision import validate_request, RevisionError


@pytest.mark.parametrize('name', TASKS)
def test_authored_task_and_positive_negative_edits(name):
    task = load_task(name)
    assert evaluate(task['design'],task['constraints'])['accepted']
    for key,expected in [('valid_edits',True),('invalid_edits',False)]:
        design = copy.deepcopy(task['design'])
        parts = {p['id']:p for p in design['parts']}
        for edit in task[key]: parts[edit['part']].update(edit['set'])
        assert evaluate(design,task['constraints'])['accepted'] is expected


@pytest.mark.parametrize('name,part', [('enclosure','housing'),('shaft-fit','shaft')])
def test_unsupported_rotations_cannot_pass(name,part):
    task = load_task(name)
    next(p for p in task['design']['parts'] if p['id']==part)['rotation']=[0,0,15]
    assert not evaluate(task['design'],task['constraints'])['accepted']


def test_shifted_or_short_shaft_cannot_claim_fit():
    for change in [{'position':[1,0,0]}, {'size':[9.8,9.8,4]}]:
        task = load_task('shaft-fit')
        task['design']['parts'][0].update(change)
        assert not evaluate(task['design'],task['constraints'])['accepted']


@pytest.mark.parametrize('value', [float('nan'),float('inf'),True])
def test_invalid_numeric_geometry_is_not_ignored(value):
    task = load_task('enclosure');task['design']['parts'][0]['position'][1]=value
    with pytest.raises(ValueError): evaluate(task['design'],task['constraints'])


@pytest.mark.parametrize('mutation', ['unknown','duplicate','extra','nan','reverse'])
def test_contract_schema_rejects_ambiguous_rules(mutation):
    task = load_task('enclosure'); contract=task['constraints']; rule=contract['rules'][0]
    if mutation=='unknown':rule['kind']='fake-checker'
    if mutation=='duplicate':contract['rules'].append(copy.deepcopy(rule))
    if mutation=='extra':rule['ignore_failure']=True
    if mutation=='nan':rule['min']=float('nan')
    if mutation=='reverse':rule['max']=rule['min']-1
    with pytest.raises(ValueError):validate_contract(contract)


@pytest.mark.parametrize('fields', [{'route':'catalog'},{'requirements':[]},{'id':'new-id'},{'material':'steel'}])
def test_revision_protocol_protects_identity_routes_and_requirements(fields):
    patch={'schema':'fk-revision-v1','base_manifest_sha256':'a'*64,'edits':[{'part':'housing','set':fields}]}
    with pytest.raises(RevisionError,match='Only size'):validate_request(patch)


def test_revision_protocol_rejects_contract_replacement():
    patch={'schema':'fk-revision-v1','base_manifest_sha256':'a'*64,'edits':[], 'constraints':{'rules':[]}}
    with pytest.raises(RevisionError):validate_request(patch)


def test_vacuous_contract_is_explicitly_uncovered():
    report=evaluate(load_task('enclosure')['design'],{'schema':'fk-constraints-v1','rules':[]})
    assert report['coverage']=='no-numeric-constraints-declared'
    assert report['physical_validation']=='not-performed'
