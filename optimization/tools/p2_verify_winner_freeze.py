#!/usr/bin/env python3
"""Read-only P2 winner-freeze verifier with separate attestation."""
from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P2=ROOT/'05_p2_hard_negative_semantic_optimization';D=P2/'05_winner_freeze';FREEZE=D/'p2_winner_freeze.json';ATTEST=D/'p2_winner_freeze_attestation.json'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def atomic(path,obj):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def main():
 before=sha(FREEZE);f=json.loads(FREEZE.read_text());checks={'prompt':(Path(f['prompt_path']),f['prompt_sha256']),'config':(Path(f['config_path']),f['config_sha256']),'runner':(Path(f['runner_path']),f['runner_sha256']),'materializer':(Path(f['materializer_path']),f['materializer_sha256']),'candidate_freeze':(Path(f['candidate_freeze_path']),f['candidate_freeze_sha256']),'internal_split':(P2/'01_internal_split/p2_internal_split.json',f['p2_internal_split_sha256']),'design_manifest':(P2/'01_internal_split/p2_design_manifest.csv',f['design_manifest_sha256']),'screen_manifest':(P2/'01_internal_split/p2_screen_manifest.csv',f['screen_manifest_sha256']),'screen_predictions':(Path(f['screen_predictions_path']),f['screen_predictions_sha256']),'screen_summary':(Path(f['screen_summary_path']),f['screen_summary_sha256']),'winner_decision':(Path(f['winner_decision_path']),f['winner_decision_sha256']),'val_manifest':(Path(f['val_manifest_path']),f['val_manifest_sha256']),'p1r_predictions':(Path(f['p1r_baseline_predictions_path']),f['p1r_baseline_predictions_sha256'])};errors=[]
 for name,(path,expected) in checks.items():
  if not path.is_file() or sha(path)!=expected:errors.append(name+'_hash_mismatch')
 if f.get('winner_candidate_id')!='C3' or f.get('p2_val_requests_before_freeze')!=0 or f.get('holdout_requests_before_freeze')!=0 or f.get('val_error_cases_used_for_prompt_design') is not False:errors.append('winner_governance_invalid')
 if sha(P2/'03_candidates/C3/C3_prompt.txt')!=f['prompt_sha256'] or sha(P2/'03_candidates/p2_request_config.json')!=f['config_sha256']:errors.append('runtime_source_copy_mismatch')
 after=sha(FREEZE)
 if before!=after:errors.append('freeze_changed_during_verification')
 att={'verification_result':'PASS' if not errors else 'FAIL','verified_at_utc':datetime.now(timezone.utc).isoformat(),'freeze_sha256':before,'freeze_unchanged_during_verification':before==after,'errors':errors,'checks':{name:{'path':str(path),'expected_sha256':expected,'actual_sha256':sha(path) if path.is_file() else None} for name,(path,expected) in checks.items()}}
 atomic(ATTEST,att);print(json.dumps(att,sort_keys=True))
 if errors:raise SystemExit('P2_WINNER_FREEZE_VERIFICATION=FAIL')
if __name__=='__main__':main()
