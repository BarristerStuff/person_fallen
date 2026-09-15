"""Main-agent-only exclusive execution freeze. No model request."""
import sys
from contracts import *

def freeze():
 if (ROOT/'freeze/EXECUTION_FREEZE.json').exists() or any((ROOT/'eval').iterdir()):raise ValueError('Existing freeze/execution blocks')
 audit=loads((ROOT/'reports/source_audit.json').read_bytes())
 if not audit['status'].startswith('PASS'):raise ValueError('Source audit not passed')
 bindings={**audit['bindings'],**audit['output_sha256']}
 for p,h in bindings.items():verify_sha(p,h)
 for phase,spec in PHASES.items():validate_manifest(phase,loads((ROOT/'manifests'/spec['manifest']).read_bytes()))
 # Main-agent independently checks set construction rather than accepting agent PASS.
 import csv
 base=ROOT.parent;d=base/'13_person_fallen_v4_pose_attributes/manifests'
 def csvrows(p):
  with p.open(newline='') as f:return list(csv.DictReader(f))
 diag=csvrows(d/'v4_diagnostic_110.csv');full=csvrows(d/'v4_full_dev_436.csv')
 pilot=loads((ROOT/'manifests/pilot115.json').read_bytes());reg=loads((ROOT/'manifests/regression1.json').read_bytes())
 expected=[r['item_id'] for r in diag]+[r['item_id'] for r in full if r['taxonomy']=='multi_person_one_lying']
 if len(set(expected))!=115 or [r['item_id'] for r in pilot]!=expected:raise ValueError('Diagnostic110+allmulti5 identity mismatch')
 fullmap={r['item_id']:r for r in full}
 for r in pilot:
  for k,v in fullmap[r['item_id']].items():
   if r[k]!=v:raise ValueError('Original source field modified: '+k)
 if sum(r['experiment_stratum']=='ground_lying' for r in pilot)!=60 or sum(r['taxonomy']=='floor_sitting' for r in pilot)!=55:raise ValueError('Wrong denominator')
 if len({r['group_id'] for r in pilot if r['taxonomy']=='multi_person_one_lying'})!=1:raise ValueError('Unexpected multi group count')
 if reg[0]['item_id']!='P4D_PLAN::PF_P4D_POS_CURLED_G003_V05' or reg[0]['operational_id']!='PFV4_SCREEN_0066':raise ValueError('Wrong regression')
 tests=loads((ROOT/'reports/offline_test_summary.json').read_bytes())
 if tests['failed']!=0 or tests['errors']!=0 or tests['skipped']!=0 or tests['passed']!=85:raise ValueError('Offline suite not passed')
 plan=loads((ROOT/'protocol/execution_plan.json').read_bytes())
 history=loads((ROOT/'reports/dependency_audit.json').read_bytes())
 for p,h in history['immutable_dependencies'].items():verify_sha(p,h);bindings[p]=h
 for folder in ['definition','prompt','schema','policy','protocol','manifests','tools','tests']:
  for p in (ROOT/folder).rglob('*'):
   if p.is_file():bindings[str(p)]=sha(p)
 for name in ['source_audit.json','offline_tests.txt','offline_test_summary.json','dependency_audit.json','handoff_at_preflight.md','ollama_initial_preflight.json']:
  p=ROOT/'reports'/name;bindings[str(p)]=sha(p)
 f={'candidate':CANDIDATE,'status':'IMMUTABLE_EXECUTION_FREEZE','timestamp':utc(),'bindings':bindings,'budget':plan['budget'],'stage_order':plan['stage_order'],'model':plan['model'],'pilot_gates':plan['pilot_gates'],'regression_gates':plan['regression_gates'],'stop_rules':plan['stop_rules'],'EVALUATION_MODE':'NEW_TARGET_ATTRIBUTES_ONLY','CACHED_PRIMARY_USED_FOR_FINAL_DECISION':False,'OBJECT_LOCALIZATION_ACCURACY':'UNVERIFIED','business_definition_sha256':sha(ROOT/'definition/person_fallen_v4_operational_definition.md'),'pilot115_manifest_sha256':sha(ROOT/'manifests/pilot115.json'),'known_regression1_manifest_sha256':sha(ROOT/'manifests/regression1.json'),'prompt_sha256':sha(ROOT/'prompt/target_attributes.txt'),'schema_sha256':sha(ROOT/'schema/target_attributes.json'),'person_policy_sha256':sha(ROOT/'policy/target_policy.py'),'scene_aggregation_sha256':sha(ROOT/'policy/target_policy.py'),'runner_sha256':sha(ROOT/'tools/run_target_eval.py'),'metrics_sha256':sha(ROOT/'tools/metrics.py'),'tests_sha256':{p.name:sha(p) for p in sorted((ROOT/'tests').glob('test_*.py'))},'input_bindings':[{'phase':r['phase'],'request_id':r['request_id'],'image_sha256':r['image_sha256'],'full_view_sha256':r['full_view_sha256'],'crop_view_sha256':r['crop_view_sha256'],'crop_attached':r['person_detected']=='true'} for r in pilot+reg]}
 p=ROOT/'freeze/EXECUTION_FREEZE.json';write_json(p,f);write_bytes(ROOT/'freeze/EXECUTION_FREEZE.sha256',(sha(p)+'\n').encode())
 for name in bindings:
  path=Path(name)
  if path.is_relative_to(ROOT):path.chmod(0o444)
 p.chmod(0o444);(ROOT/'freeze/EXECUTION_FREEZE.sha256').chmod(0o444)
 print(json.dumps({'status':f['status'],'freeze_sha256':sha(p),'bound_files':len(bindings),'budget':f['budget']}))
if __name__=='__main__':freeze()
