#!/usr/bin/env python3
"""Read-only candidate-freeze verifier; writes only a separate attestation."""
from __future__ import annotations
import csv,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P2=ROOT/'05_p2_hard_negative_semantic_optimization';C=P2/'03_candidates';FREEZE=C/'candidate_freeze.json';ATTEST=C/'candidate_freeze_attestation.json'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def atomic(path,data):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def main():
 before=sha(FREEZE);f=json.loads(FREEZE.read_text());errors=[]
 checks={'candidate_registry':(Path(f['candidate_registry_path']),f['candidate_registry_sha256']),'request_config':(Path(f['request_config_path']),f['request_config_sha256']),'runner':(Path(f['runner_path']),f['runner_sha256']),'materializer':(Path(f['materializer_path']),f['materializer_sha256']),'internal_split':(Path(f['p2_internal_split_path']),f['p2_internal_split_sha256']),'design_manifest':(P2/'01_internal_split/p2_design_manifest.csv',f['design_manifest_sha256']),'screen_manifest':(P2/'01_internal_split/p2_screen_manifest.csv',f['screen_manifest_sha256']),'protocol_canary_manifest':(C/'protocol_canary_manifest.csv',f['protocol_canary_manifest_sha256'])}
 for name,(path,expected) in checks.items():
  if not path.is_file() or sha(path)!=expected:errors.append(name+'_hash_mismatch')
 for candidate,item in f['candidates'].items():
  path=Path(item['prompt_path'])
  if not path.is_file() or sha(path)!=item['prompt_sha256']:errors.append(candidate+'_prompt_hash_mismatch')
 for candidate,item in f['canary_summaries'].items():
  path=Path(item['path'])
  if not path.is_file() or sha(path)!=item['sha256']:errors.append(candidate+'_canary_summary_hash_mismatch')
 if f.get('screen_blind_before_candidate_freeze') is not True or f.get('screen_artifact_files_before_freeze')!=0 or f.get('val_error_cases_used_for_prompt_design') is not False:errors.append('blindness_attestation_invalid')
 after=sha(FREEZE)
 if before!=after:errors.append('freeze_changed_during_verification')
 att={'verification_result':'PASS' if not errors else 'FAIL','verified_at_utc':datetime.now(timezone.utc).isoformat(),'freeze_sha256':before,'freeze_unchanged_during_verification':before==after,'errors':errors,'checks':{name:{'path':str(path),'expected_sha256':expected,'actual_sha256':sha(path) if path.is_file() else None} for name,(path,expected) in checks.items()}}
 atomic(ATTEST,att);print(json.dumps(att,sort_keys=True))
 if errors:raise SystemExit('CANDIDATE_FREEZE_VERIFICATION=FAIL')
if __name__=='__main__':main()
