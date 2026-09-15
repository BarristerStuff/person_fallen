import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT.parent
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 files=[ROOT/'protocol/budget.py',ROOT/'protocol/execution_plan.json',ROOT/'tools/engine.py',ROOT/'tools/runner.py',ROOT/'tools/build_manifests.py',ROOT/'tools/fake_e2e.py',ROOT/'tests/test_engine.py']
 files += [ROOT/'manifests'/x for x in ('pilot156.json','regression1.json','full_remaining280.json','full_combined436.json')]
 files += [BASE/'20_person_fallen_v6_target_support_config'/x for x in ('prompt/target_support_attributes.txt','schema/target_attributes.json','policy/target_policy.py','definition/person_fallen_v4_operational_definition.md')]
 b={str(p):sha(p) for p in files}
 f={'status':'IMMUTABLE_EXECUTION_FREEZE','candidate':'V6-A0-TARGET-SUPPORT-CONFIG','execution_id':'PERSON_FALLEN_V6_A0_DIRECT_EVALUATION_20260914','model':{'endpoint':'http://192.168.20.62:11434','name':'qwen3.5:4b','digest':'2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd','ollama_version':'0.23.2','think':False,'stream':False,'temperature':0,'num_ctx':8192,'num_predict':768,'concurrency':1,'timeout_seconds':120,'automatic_retry':False,'resend_completion_unknown':False},'budget':{'pilot':156,'regression':1,'full_dev_remaining':280,'total':437,'val':0,'holdout':0,'detector':0},'stages':['pilot','regression','full_remaining','full_dev_combined'],'bindings':b,'val_requests':0,'holdout_requests':0}
 out=ROOT/'freeze/RECOVERY_FREEZE.json'; out.write_text(json.dumps(f,ensure_ascii=False,indent=2)+'\n'); (ROOT/'freeze/RECOVERY_FREEZE.sha256').write_text(sha(out)+'\n'); print(json.dumps({'sha256':sha(out),'bindings':len(b)}))
if __name__=='__main__': main()
