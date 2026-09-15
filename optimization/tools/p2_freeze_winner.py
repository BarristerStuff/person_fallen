#!/usr/bin/env python3
"""Create immutable P2 winner artifacts and freeze before any P2 VAL request."""
from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P2=ROOT/'05_p2_hard_negative_semantic_optimization';DEST=P2/'05_winner_freeze';DECISION=P2/'04_screening/winner_decision.json';SOURCE_PROMPT=P2/'03_candidates/C3/C3_prompt.txt';SOURCE_CONFIG=P2/'03_candidates/p2_request_config.json';FREEZE=DEST/'p2_winner_freeze.json'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def exclusive_copy(src,dst):
 data=src.read_bytes()
 with dst.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
def exclusive_json(path,obj):
 with path.open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def main():
 DEST.mkdir(parents=True,exist_ok=True)
 if FREEZE.exists():raise SystemExit('P2_WINNER_FREEZE_ALREADY_EXISTS')
 val_files=[str(p) for p in (P2/'06_val').rglob('*') if p.is_file()]
 if val_files:raise SystemExit('P2_WINNER_FREEZE_BLOCKED_VAL_ALREADY_TOUCHED')
 decision=json.loads(DECISION.read_text())
 if decision.get('winner')!='C3' or decision.get('eligible_candidates')!=['C3']:raise SystemExit('P2_WINNER_DECISION_INVALID')
 winner_prompt=DEST/'p2_winner_prompt.txt';winner_config=DEST/'p2_winner_config.json';exclusive_copy(SOURCE_PROMPT,winner_prompt);exclusive_copy(SOURCE_CONFIG,winner_config)
 screen_summary=P2/'04_screening/C3/summary.json';screen_predictions=P2/'04_screening/C3/predictions.csv';val_manifest=ROOT/'04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv';p1r_predictions=ROOT/'04_p1r_freeze_binding_recovery/val/predictions.csv'
 record={'stage':'P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION','created_at_utc':datetime.now(timezone.utc).isoformat(),'winner_candidate_id':'C3','prompt_path':str(winner_prompt),'prompt_sha256':sha(winner_prompt),'config_path':str(winner_config),'config_sha256':sha(winner_config),'runner_path':str(ROOT/'tools/p2_inference_runner.py'),'runner_sha256':sha(ROOT/'tools/p2_inference_runner.py'),'materializer_path':str(ROOT/'tools/p2_materialize_results.py'),'materializer_sha256':sha(ROOT/'tools/p2_materialize_results.py'),'model':'qwen3.5:4b','model_digest':'2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd','ollama_version':'0.23.2','preprocess':'letterbox_448x336_jpeg_q70','parser':'response_only','thinking_fallback':False,'candidate_freeze_path':str(P2/'03_candidates/candidate_freeze.json'),'candidate_freeze_sha256':sha(P2/'03_candidates/candidate_freeze.json'),'p2_internal_split_sha256':sha(P2/'01_internal_split/p2_internal_split.json'),'design_manifest_sha256':sha(P2/'01_internal_split/p2_design_manifest.csv'),'screen_manifest_sha256':sha(P2/'01_internal_split/p2_screen_manifest.csv'),'screen_predictions_path':str(screen_predictions),'screen_predictions_sha256':sha(screen_predictions),'screen_summary_path':str(screen_summary),'screen_summary_sha256':sha(screen_summary),'winner_decision_path':str(DECISION),'winner_decision_sha256':sha(DECISION),'screening_comparison_sha256':sha(P2/'04_screening/screening_comparison.csv'),'paired_error_analysis_sha256':sha(P2/'04_screening/paired_error_analysis.csv'),'winner_metrics':decision['winner_screen_metrics'],'baseline_metrics':decision['baseline_screen_metrics'],'winner_selection_rule':decision['selection_rule'],'absolute_hard_negative_fpr_reduction':decision['absolute_hard_negative_fpr_reduction'],'precision_delta':decision['precision_delta'],'recall_delta':decision['recall_delta'],'f1_delta':decision['f1_delta'],'val_manifest_path':str(val_manifest),'val_manifest_sha256':sha(val_manifest),'p1r_baseline_predictions_path':str(p1r_predictions),'p1r_baseline_predictions_sha256':sha(p1r_predictions),'p2_val_is_pristine':False,'p2_val_requests_before_freeze':0,'val_error_cases_used_for_prompt_design':False,'holdout_requests_before_freeze':0}
 exclusive_json(FREEZE,record);freeze_sha=sha(FREEZE)
 with (DEST/'p2_winner_freeze.sha256').open('x',encoding='utf-8') as f:f.write(f'{freeze_sha}  p2_winner_freeze.json\n');f.flush();os.fsync(f.fileno())
 print(json.dumps({'P2_WINNER_FREEZE_CREATED':True,'winner':'C3','freeze_sha256':freeze_sha,'p2_val_files_before_freeze':0},sort_keys=True))
if __name__=='__main__':main()
