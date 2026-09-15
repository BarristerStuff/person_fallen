"""Exclusive pre-inference freeze; no model call. Existing freeze/execution blocks."""
from contracts import *
from audit_cache import audit
import importlib.util

def freeze():
 if (ROOT/'freeze/EXECUTION_FREEZE.json').exists() or any((ROOT/'eval').iterdir()):raise ValueError('Existing freeze/execution; no overwrite')
 out,audit_report=audit()
 for phase,rr in out.items():
  if rr!=loads((ROOT/f'manifests/{phase}.json').read_bytes()):raise ValueError('Prepared candidate/source mismatch')
  validate_manifest(phase,rr)
 write_json(ROOT/'reports/final_cache_audit.json',audit_report)
 p=ROOT.parents[1].parent/'14_person_fallen_v4_operational_freeze/policy/deterministic_policy.py'
 spec=importlib.util.spec_from_file_location('primary_schema_source',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 schema={'type':'object','additionalProperties':False,'required':sorted(mod.EXPECTED_KEYS),'properties':{k:{'type':'string','enum':sorted(v)} for k,v in mod.ENUMS.items()}}
 schema['properties']['evidence']={'type':'string','minLength':1,'non_whitespace_required':True}
 write_json(ROOT/'schema/primary_contract_binding.json',{'source_policy_path':str(p),'source_policy_sha256':sha(p),'contract':schema,'note':'Derived exact 9-key contract for binding only, primary API remains historical format=json; no new primary request.'})
 test=loads((ROOT/'reports/offline_test_summary.json').read_bytes())
 if test['failed']!=0 or test['candidate_tests_passed']!=18 or test['preparation_tests_passed']!=13:raise ValueError('Offline tests not passed')
 plan=loads((ROOT/'protocol/execution_plan.json').read_bytes())
 bindings=dict(audit_report['bindings'])
 for folder in ['prompt','schema','policy','protocol','manifests','tools','tests']:
  for p in (ROOT/folder).rglob('*'):
   if p.is_file():bindings[str(p)]=sha(p)
 for name in ['cache_preflight.json','final_cache_audit.json','offline_tests.txt','offline_test_summary.json','ollama_initial_preflight.json']:
  p=ROOT/'reports'/name;bindings[str(p)]=sha(p)
 obj={'candidate':plan['candidate'],'status':'IMMUTABLE_EXECUTION_FREEZE','timestamp':utc(),'request_budget':plan['request_budget'],'bindings':bindings,'primary_cache_binding':audit_report['phases'],'primary_model_options':audit_report['model'],'primary_preprocess':audit_report['primary_preprocess'],'primary_detector':audit_report['primary_detector'],'secondary_model_options':plan['secondary_model'],'stage_order':plan['stage_order'],'gates':plan['gates'],'stop_rules':plan['stop_rules'],'primary_schema_sha256':sha(ROOT/'schema/primary_contract_binding.json'),'secondary_schema_sha256':sha(ROOT/'schema/secondary.json'),'secondary_prompt_sha256':sha(ROOT/'prompt/scene_review.txt'),'routing_policy_sha256':sha(ROOT/'policy/routing_contract.py'),'runner_sha256':sha(ROOT/'tools/run_secondary.py'),'metrics_sha256':sha(ROOT/'tools/metrics.py'),'offline_tests_sha256':sha(ROOT/'tests/test_execution.py'),'all_actual_full_scene_inputs':{phase:[{'item_id':r['item_id'],'path':r['full_view_path'],'sha256':r['full_view_sha256'],'secondary_required':r['secondary_required']} for r in rr] for phase,rr in out.items()},'VAL_AUTHORIZED':False,'HOLDOUT_AUTHORIZED':False,'ROBOT_CONTROL_AUTHORIZED':False}
 path=ROOT/'freeze/EXECUTION_FREEZE.json';write_json(path,obj);write_bytes(ROOT/'freeze/EXECUTION_FREEZE.sha256',(sha(path)+'\n').encode())
 # Do not chmod any historical/preparation file. Candidate-only frozen surfaces.
 for p in bindings:
  pp=Path(p)
  if pp.is_relative_to(ROOT):pp.chmod(0o444)
 path.chmod(0o444);(ROOT/'freeze/EXECUTION_FREEZE.sha256').chmod(0o444)
 print(json.dumps({'freeze_sha256':sha(path),'bound_files':len(bindings),'status':obj['status']}))
if __name__=='__main__':freeze()
