#!/usr/bin/env python3
"""Create the immutable P2 candidate registry and freeze exactly once."""
from __future__ import annotations
import csv,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P2=ROOT/'05_p2_hard_negative_semantic_optimization';CANDS=P2/'03_candidates';FREEZE=CANDS/'candidate_freeze.json';REGISTRY=CANDS/'candidate_registry.csv'
RATIONALE={
 'C0':('baseline','unchanged P1A/P1R prompt; no new model request on SCREEN'),
 'C1':('sitting_on_floor;kneeling_or_half_kneeling;squatting_or_crouching;exercise_pushup_or_plank','explicit torso/pelvis lying boundary versus stable low supported posture'),
 'C2':('sitting_on_floor;kneeling_or_half_kneeling;squatting_or_crouching;exercise_pushup_or_plank','ordered visible negative-posture check followed by genuine lying-state test'),
 'C3':('sitting_on_floor;kneeling_or_half_kneeling;squatting_or_crouching;exercise_pushup_or_plank','support-surface, torso/pelvis, and active-limb evidence slots without schema change'),
}
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def prompt_path(candidate):return CANDS/('C0_BASELINE' if candidate=='C0' else candidate)/(candidate+'_prompt.txt')
def atomic(path,data):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def main():
 if FREEZE.exists() or REGISTRY.exists():raise SystemExit('P2_CANDIDATE_FREEZE_ALREADY_EXISTS')
 screen_files=[str(p) for p in (P2/'04_screening').rglob('*') if p.is_file()]
 if screen_files:raise SystemExit('P2_SCREEN_BLINDNESS_INVALID')
 summaries={}
 for candidate in ['C1','C2','C3']:
  path=CANDS/candidate/'canary/summary.json';summary=json.loads(path.read_text())
  if summary.get('protocol_gate_pass') is not True or summary.get('planned_requests')!=9 or summary.get('holdout_requests')!=0:raise SystemExit('P2_CANDIDATE_CANARY_FAIL_'+candidate)
  summaries[candidate]={'path':str(path),'sha256':sha(path),'protocol_gate_pass':True,'request_count':9}
 fields=['candidate_id','prompt_path','prompt_sha256','design_forensic_categories_targeted','design_rationale','canary_status','candidate_eligible_for_screen']
 rows=[]
 for candidate in ['C0','C1','C2','C3']:
  target,rationale=RATIONALE[candidate];rows.append({'candidate_id':candidate,'prompt_path':str(prompt_path(candidate)),'prompt_sha256':sha(prompt_path(candidate)),'design_forensic_categories_targeted':target,'design_rationale':rationale,'canary_status':'BASELINE_REUSE' if candidate=='C0' else 'PASS','candidate_eligible_for_screen':'false' if candidate=='C0' else 'true'})
 tmp=REGISTRY.with_suffix('.csv.tmp')
 with tmp.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows);f.flush();os.fsync(f.fileno())
 os.replace(tmp,REGISTRY)
 candidates={row['candidate_id']:{key:row[key] for key in ['prompt_path','prompt_sha256','design_forensic_categories_targeted','design_rationale','canary_status','candidate_eligible_for_screen']} for row in rows}
 record={'stage':'P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION','created_at_utc':datetime.now(timezone.utc).isoformat(),'candidate_ids':['C0','C1','C2','C3'],'candidates':candidates,'candidate_registry_path':str(REGISTRY),'candidate_registry_sha256':sha(REGISTRY),'request_config_path':str(CANDS/'p2_request_config.json'),'request_config_sha256':sha(CANDS/'p2_request_config.json'),'runner_path':str(ROOT/'tools/p2_inference_runner.py'),'runner_sha256':sha(ROOT/'tools/p2_inference_runner.py'),'materializer_path':str(ROOT/'tools/p2_materialize_results.py'),'materializer_sha256':sha(ROOT/'tools/p2_materialize_results.py'),'p2_internal_split_path':str(P2/'01_internal_split/p2_internal_split.json'),'p2_internal_split_sha256':sha(P2/'01_internal_split/p2_internal_split.json'),'design_manifest_sha256':sha(P2/'01_internal_split/p2_design_manifest.csv'),'screen_manifest_sha256':sha(P2/'01_internal_split/p2_screen_manifest.csv'),'protocol_canary_manifest_sha256':sha(CANDS/'protocol_canary_manifest.csv'),'canary_summaries':summaries,'model':'qwen3.5:4b','model_digest':'2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd','ollama_version':'0.23.2','preprocess':'letterbox_448x336_jpeg_q70','parser':'response_only','thinking_fallback':False,'screen_blind_before_candidate_freeze':True,'screen_artifact_files_before_freeze':0,'design_forensic_source':'DESIGN_ONLY','val_error_cases_used_for_prompt_design':False,'holdout_requests_before_freeze':0}
 atomic(FREEZE,record);freeze_sha=sha(FREEZE)
 side=CANDS/'candidate_freeze.sha256'
 with side.open('x',encoding='utf-8') as f:f.write(f'{freeze_sha}  candidate_freeze.json\n');f.flush();os.fsync(f.fileno())
 print(json.dumps({'CANDIDATE_FREEZE_CREATED':True,'freeze_sha256':freeze_sha,'screen_artifact_files_before_freeze':0},sort_keys=True))
if __name__=='__main__':main()
