#!/usr/bin/env python3
"""Verify an extracted demo bundle. Standard library + pinned Lean required.

The manifest detects mutation relative to its recorded snapshot; it is not a
signed attestation and does not certify physical claims or supplier references.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(v):return sha(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
manifest=json.loads((root/'manifest.json').read_text())
for name,expected in manifest.items():
    p=(root/name).resolve()
    if root not in p.parents or not p.is_file() or sha(p.read_bytes())!=expected:
        raise SystemExit('Manifest mismatch: '+name)
p=json.loads((root/'manufacturing.json').read_text());proof=json.loads((root/'proof.json').read_text())
if digest(p)!=proof['plan_sha256']:raise SystemExit('Plan digest mismatch')
input_record=json.loads((root/'input.json').read_text())
if digest(input_record)!=p['request_sha256']:raise SystemExit('Frozen request binding mismatch')
if input_record['image_sha256']!=p['image_sha256']:raise SystemExit('Source image commitment mismatch')
if sha((root/'image.png').read_bytes())!=input_record['normalized_image_sha256']:
    raise SystemExit('Actual model image differs from the frozen input')
steps=p['steps'];pos={s['id']:i for i,s in enumerate(steps)}
if len(pos)!=len(steps):raise SystemExit('Duplicate occurrence')
rows=[]
for s in steps:
    r=p['receipts'][s['receipt']]
    if digest(r)!=s['receipt'] or any([r['id']!=s['id'],r['route']!=s['route'],r['dependencies']!=s['deps'],r['input_image_sha256']!=p['image_sha256'],r['request_sha256']!=p['request_sha256']]):
        raise SystemExit('Receipt binding mismatch: '+s['id'])
    deps=[pos.get(d,len(steps)) for d in s['deps']]
    rows.append('  ⟨.'+s['route']+', '+str(deps)+', '+str(s['depth'])+', '+json.dumps(s['receipt'])+'⟩')
source=('import FluxKernel.Closure\nopen FluxKernel\nset_option maxRecDepth 8192\n'
    'set_option maxHeartbeats 8000000\n'+'def plan : List Step := [\n'+',\n'.join(rows)+'\n]\n'
    +f"def policy : Policy := ⟨{p['policy']['equipment_depth']}⟩\n"
    +'theorem planAccepted : check policy plan = true := by decide\n'
    +'theorem manufacturingClosed : VerifiedPlan policy plan := check_sound policy plan planAccepted\n'
    +'#print axioms manufacturingClosed\n')
if source!=(root/'ManufacturingPlan.lean').read_text():raise SystemExit('Lean source differs from actual plan')
if sha(source.encode())!=proof['source_sha256']:raise SystemExit('Lean source hash mismatch')
if sha((root/'formal/FluxKernel/Closure.lean').read_bytes())!=proof['kernel_source_sha256']:raise SystemExit('Kernel source hash mismatch')
for cmd in [['lake','build'],['lake','env','lean','ManufacturingPlan.lean']]:
    result=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=120)
    print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr)
    if result.returncode or any(x in result.stdout for x in ['sorryAx','Lean.trustCompiler','_native.']):
        raise SystemExit('Lean rejected the plan or has unapproved dependencies')
print('PASS: manifest, occurrence receipts, JSON-to-Lean binding and Lean plan closure. Physical capability remains unverified.')
