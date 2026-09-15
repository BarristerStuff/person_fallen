import json,hashlib,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent;V20=BASE/'20_person_fallen_v6_target_support_config';V13=BASE/'13_person_fallen_v4_pose_attributes'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(d,p):d[str(Path(p).resolve())]=sha(p)
def main():
 F=ROOT/'freeze/RECOVERY_FREEZE.json'
 if F.exists() or (ROOT/'freeze/RECOVERY_FREEZE.sha256').exists():raise RuntimeError('freeze exists')
 if (ROOT/'eval/pilot').exists() or (ROOT/'eval/regression').exists() or (ROOT/'eval/full').exists():raise RuntimeError('execution exists')
 # require preflight/test artifacts
 assert json.load(open(ROOT/'reports/ollama_preflight.json'))['status']=='PASS'
 assert json.load(open(ROOT/'reports/offline_test_summary.json'))['status']=='PASS'
 b={}
 # semantic candidate direct bindings
 for p in [V20/'prompt/target_support_attributes.txt',V20/'schema/target_attributes.json',V20/'policy/target_policy.py',V20/'definition/person_fallen_v4_operational_definition.md',V20/'tools/contracts.py',V20/'tools/metrics.py',V20/'tools/run_v6_eval.py',ROOT/'protocol/execution_plan.json',V20/'manifests/pilot156.json',V20/'manifests/regression1.json',ROOT/'manifests/full_dev_remaining.json',ROOT/'manifests/full_dev_combined.json',ROOT/'reports/source_audit.json',ROOT/'reports/offline_tests.txt',ROOT/'reports/offline_test_summary.json',ROOT/'reports/fake_e2e_report.json',ROOT/'reports/ollama_preflight.json',ROOT/'tools/recovery_runner.py']:
  bind(b,p)
 for p in [V20/'freeze/CANDIDATE_FREEZE.json',V20/'freeze/CANDIDATE_FREEZE.sha256',V20/'reports/final_report.json',V20/'reports/independent_audit_final.json',V20/'reports/source_audit.json']:
  bind(b,p)
 for r in json.load(open(V20/'manifests/pilot156.json'))+json.load(open(V20/'manifests/regression1.json'))+json.load(open(ROOT/'manifests/full_dev_remaining.json')):
  for k in ['image_path','prompt_path','full_view_path','crop_view_path']:bind(b,r[k])
 p={'status':'IMMUTABLE_RECOVERY_FREEZE','candidate':'V6-A0-TARGET-SUPPORT-CONFIG','execution_id':'PERSON_FALLEN_V6_A0_EXECUTION_RECOVERY_R1_20260910','model':{'endpoint':'http://192.168.20.62:11434','name':'qwen3.5:4b','digest':'2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd','ollama_version':'0.23.2','think':False,'stream':False,'temperature':0,'num_ctx':8192,'num_predict':768,'concurrency':1,'timeout_seconds':120,'automatic_retry':False,'resend_completion_unknown':False},'budget':{'pilot':156,'regression':1,'full_dev_remaining':280,'total':437,'val':0,'holdout':0,'detector':0},'gates':json.load(open(ROOT/'protocol/execution_plan.json'))['gates'],'bindings':dict(sorted(b.items())),'binding_count':len(b),'VAL_HOLDOUT':{'val_requests':0,'holdout_requests':0,'holdout_consumed':False},'OBJECT_LOCALIZATION_ACCURACY':'UNVERIFIED'}
 F.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n');(ROOT/'freeze/RECOVERY_FREEZE.sha256').write_text(sha(F)+'\n');F.chmod(0o444);(ROOT/'freeze/RECOVERY_FREEZE.sha256').chmod(0o444);print({'freeze':sha(F),'bindings':len(b)})
if __name__=='__main__':main()
