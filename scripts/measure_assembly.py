"""Read-only fixed-pair geometry evaluation; never edits or selects candidates."""
import argparse
import hashlib
import json
from pathlib import Path
from fluxkernel.demo.models import Design
from fluxkernel.demo.geometry import build
from fluxkernel.demo.perception import layout_checks
from OCP.BRepExtrema import BRepExtrema_DistShapeShape

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--protocol',type=Path,required=True)
p.add_argument('--run',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();protocol=json.loads(a.protocol.read_text());source=a.run/'design.json'
d=Design.model_validate_json(source.read_text());parts={p.id:p for p in d.parts};shapes={};rows=[]
for left,right in protocol['fixed_surface_gap_pairs']:
 row={'parts':[left,right]}
 if left not in parts or right not in parts:
  row.update(state='missing-part',gap_mm=None)
 else:
  for ident in (left,right):
   if ident not in shapes:shapes[ident]=build(parts[ident])
  distance=BRepExtrema_DistShapeShape(shapes[left],shapes[right]);distance.Perform()
  row.update(state='measured' if distance.IsDone() else 'failed',gap_mm=distance.Value() if distance.IsDone() else None)
 rows.append(row)
s=a.run/'perception/summary.json';visual=json.loads(s.read_text()) if s.exists() else {}
report={'run':a.run.name,'design_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'protocol_sha256':hashlib.sha256(a.protocol.read_bytes()).hexdigest(),
 'surface_gaps':rows,'engine_axis_issues':[x for x in layout_checks(d)['issues'] if x['code']=='AIRCRAFT_ENGINE_AXIS'],
 'selected_round':visual.get('selected_round'),'quality_status':visual.get('quality_status'),
 'model_calls':visual.get('model_calls'),'elapsed_s':visual.get('elapsed_s'),
 'scope':'Fixed ID pairs chosen before candidate outcomes; zero gap can include overlap. No silhouette, tangent continuity or physical certificate.'}
a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False));print(json.dumps(report,ensure_ascii=False))
