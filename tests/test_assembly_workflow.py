"""Synthetic geometry invariants; no test fixture is a live model result."""
import copy
import math
import numpy as np
import pytest
from fluxkernel.demo.models import Part
from fluxkernel.demo.assembly import AssemblyRules, Anchor, assembly_checks, anchor_world, matrix
from fluxkernel.demo.pal_rules import validate_plan, activate_plan, apply_workflow_action, compile_assembly
from fluxkernel.demo.perception import digest
from fluxkernel.demo.geometry import build
from test_pal_workflow import pair_design, plain_plan, wing, EMPTY


def body_design():
    d=pair_design()
    base=dict(name='Body',group='body',route='print',shape='fuselage',size=[100,30,30],position=[0,0,0],wall=1)
    d.parts=[Part(id='aft',**base),Part(id='front',**base),Part(id='fixture',name='Mount',group='mount',route='print',shape='box',size=[8,8,8],position=[100,50,0])]
    return d


def body_rules():
    return {'bodies':[{'id':'outer-body','profile':{'kind':'body','length':240,'sections':[
        {'u':u,'width':w,'height':w,'offset_y':0,'offset_z':0} for u,w in [(0,2),(.25,30),(.7,30),(1,2)]]},
        'position':[11,12,13],'rotation':[12,18,23],'members':[{'part':'aft','start':0,'end':.4},{'part':'front','start':.4,'end':1}]}],
        'attachments':[],'alignments':[]}


def plan_for(d,rules):
    p=plain_plan();p['assembly']=rules;return validate_plan(p,d)


def test_shared_body_partition_rebuilds_valid_solids_and_exact_seam():
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    d=body_design();p=plan_for(d,body_rules());result=activate_plan(d,p,EMPTY)
    for part in result.parts:assert BRepCheck_Analyzer(build(part)).IsValid()
    distance=BRepExtrema_DistShapeShape(build(result.parts[0]),build(result.parts[1]));distance.Perform()
    assert distance.Value()<1e-6
    report=assembly_checks(result);assert report['passed']
    assert report['measurements'][0]['seam_error_mm']<1e-8
    result.parts[0].position[0]+=5
    assert assembly_checks(result)['issues'][0]['code']=='BODY_SEAM'


@pytest.mark.parametrize('bad',['gap','overlap','catalog','repeat','target'])
def test_invalid_partition_rejected(bad):
    d=body_design();r=body_rules();p=plain_plan();p['assembly']=r
    if bad=='gap':r['bodies'][0]['members'][1]['start']=.5
    if bad=='overlap':r['bodies'][0]['members'][1]['start']=.3
    if bad=='catalog':d.parts[0].route='catalog';d.parts[0].catalog_ref='sku'
    if bad=='repeat':r['bodies'][0]['members'][1]['part']='aft'
    if bad=='target':p.update(symmetry='partial',pairs=[{'source':'aft','target':'front'}])
    with pytest.raises(ValueError):validate_plan(p,d)


def test_body_rule_action_changes_master_and_preserves_protected_fields():
    d=body_design();p=plan_for(d,body_rules());d=activate_plan(d,p,EMPTY)
    r=d.assembly.model_dump();r['bodies'][0]['profile']['length']=300
    a={'base_design_sha256':digest(d.model_dump()),'rationale':'Synthetic master profile edit','edits':[],'assembly':r}
    result=apply_workflow_action(d,a,EMPTY,p)
    assert result.parts[0].parametric.length==120 and result.parts[1].parametric.length==180
    assert assembly_checks(result)['passed']
    for before,after in zip(d.parts,result.parts):
        assert (before.id,before.route,before.material,before.catalog_ref)==(after.id,after.route,after.material,after.catalog_ref)
    a['edits']=[{'part':'aft','set':{'position':[0,0,0]}}]
    with pytest.raises(ValueError,match='derived'):apply_workflow_action(d,a,EMPTY,p)


def attached_wing():
    d=pair_design();d.parts[2]=Part(id='tip',name='Tip',group='wing',route='print',shape='box',size=[5,5,5],position=[0,0,0])
    p=plain_plan();p.update(symmetry='partial',axis='y',pairs=[{'source':'source','target':'target'}],
        parameterization=[{'part':'source','kind':'wing','parameters':wing().model_dump(),'position':[0,4,0],'rotation':[0,0,0]}],
        assembly={'bodies':[],'alignments':[], 'attachments':[{'parent':'target','child':'tip','parent_anchor':{'kind':'wing','u':1,'v':.5},'child_anchor':{'kind':'origin'}}]})
    p=validate_plan(p,d);return activate_plan(d,p,EMPTY),p


def test_attachment_updates_after_parent_parameter_change_and_mirror():
    d,p=attached_wing();old=d.parts[2].position.copy();params=wing().model_dump();params['span']=110
    action={'base_design_sha256':digest(d.model_dump()),'rationale':'Synthetic span change','edits':[{'part':'source','set':{'parametric':params}}]}
    result=apply_workflow_action(d,action,EMPTY,p)
    assert not np.allclose(old,result.parts[2].position)
    assert np.allclose(result.parts[2].position,anchor_world(result.parts[1],Anchor(kind='wing',u=1,v=.5)))
    checks=assembly_checks(result);assert checks['passed']
    assert checks['measurements'][0]['surface_gap_mm']<.1


def test_contact_checks_catch_zero_anchor_error_but_physical_gap():
    d=body_design();d.parts[0]=Part(id='aft',name='Tube',group='body',route='print',shape='tube',size=[30,30,60],position=[0,0,0],wall=1)
    # An off-surface cylinder axis anchor may align a small box inside the bore.
    r={'attachments':[{'parent':'aft','child':'fixture','parent_anchor':{'kind':'origin'},'child_anchor':{'kind':'origin'},'relation':'contact'}]}
    p=plan_for(d,r);result=activate_plan(d,p,EMPTY);checks=assembly_checks(result)
    assert checks['measurements'][0]['anchor_error_mm']==0
    assert checks['measurements'][0]['surface_gap_mm']>1
    row=checks['measurements'][0]
    assert np.allclose(np.array(row['closest_child_point_mm'])-row['closest_parent_point_mm'],row['gap_vector_parent_to_child_mm'])
    assert math.isclose(np.linalg.norm(row['gap_vector_parent_to_child_mm']),row['surface_gap_mm'],abs_tol=1e-6)
    assert any(i['code']=='ATTACHMENT_GAP' for i in checks['issues'])


def test_cycle_through_mirror_is_rejected():
    d,p=attached_wing();raw=p.model_dump();raw['assembly']['attachments'][0].update(parent='target',child='source')
    with pytest.raises(ValueError,match='cycle'):validate_plan(raw,d)


@pytest.mark.parametrize('axis',['x','-x','y','-y','z','-z'])
def test_axis_alignment_orients_actual_recipe_and_preserves_catalog(axis):
    d=body_design();d.parts[2]=Part(id='fixture',name='Catalog cylinder',group='core',route='catalog',catalog_ref='fixed-sku',shape='cylinder',size=[12,12,25],position=[1,2,3])
    r={'alignments':[{'part':'fixture','local_axis':'z','world_axis':axis,'roll_deg':17}]}
    result=activate_plan(d,plan_for(d,r),EMPTY)
    v=matrix(result.parts[2])[:,2];expected=np.zeros(3);expected['xyz'.index(axis[-1])]=-1 if axis.startswith('-') else 1
    assert np.allclose(v,expected) and assembly_checks(result)['passed']
    assert result.parts[2].size==[12,12,25] and result.parts[2].catalog_ref=='fixed-sku'


def test_assembly_compilation_obeys_frozen_constraints_and_stale_action():
    d=body_design();p=plan_for(d,body_rules())
    contract={'schema':'fk-constraints-v1','rules':[{'id':'length','kind':'dimension','part':'aft','measure':'x','max':50}]}
    with pytest.raises(ValueError):activate_plan(d,p,contract)
    action={'base_design_sha256':'0'*64,'rationale':'Stale','edits':[],'assembly':body_rules()}
    with pytest.raises(ValueError,match='Stale'):apply_workflow_action(d,action,EMPTY,p)


def test_assembly_plan_is_used_by_real_workflow_with_mock_provider(tmp_path,monkeypatch):
    from test_pal_workflow import provider, review, decision, image
    from fluxkernel.demo.pal_workflow import run
    d=body_design();p=plan_for(d,body_rules());expected=activate_plan(d,p,EMPTY)
    provider(monkeypatch,[p.model_dump(),review(expected,85),decision(0,'stop')])
    result,summary=run(d,image(),'Synthetic test',tmp_path,lambda *a:None,contract=EMPTY,rounds=1)
    assert result==expected and summary['workflow']=='glm-assembly-parametric-v2'
    assert (tmp_path/'perception/round-00/assembly-checks.json').is_file()
    assert 'assembly.py' in summary['sources_sha256']


@pytest.mark.parametrize('mode',['drop','downgrade'])
def test_contact_obligation_cannot_disappear_to_clear_a_check(mode):
    d,p=attached_wing();rules=d.assembly.model_dump()
    if mode=='drop':rules['attachments']=[]
    else:rules['attachments'][0]['relation']='placement'
    action={'base_design_sha256':digest(d.model_dump()),'rationale':'Invalid weakening','edits':[],'assembly':rules}
    with pytest.raises(ValueError,match='dropped/downgraded'):apply_workflow_action(d,action,EMPTY,p)


def test_master_edit_with_unchanged_valid_part_edit_is_not_false_noop():
    d=body_design();p=plan_for(d,body_rules());d=activate_plan(d,p,EMPTY)
    rules=d.assembly.model_dump();rules['bodies'][0]['profile']['length']=300
    action={'base_design_sha256':digest(d.model_dump()),'rationale':'Master update plus unchanged fixture','assembly':rules,
        'edits':[{'part':'fixture','set':{'wall':d.parts[2].wall}}]}
    result=apply_workflow_action(d,action,EMPTY,p)
    assert result.parts[0].parametric.length==120


def test_named_axis_claim_normalizes_only_notation_and_still_checks_value():
    from test_pal_workflow import review
    from fluxkernel.demo.pal_workflow import validate_review
    d=body_design();raw=review(d);raw['numeric_claims']=[{'part':'fixture','field':'position.y','value':50}]
    assert validate_review(raw,d).numeric_claims[0].field=='position.1'
    raw['numeric_claims'][0]['value']=51
    with pytest.raises(ValueError,match='Fact mismatch'):validate_review(raw,d)
    raw['numeric_claims'][0].update(field='position',value='y=50 explanatory text')
    with pytest.raises(ValueError,match='scalar field'):validate_review(raw,d)
