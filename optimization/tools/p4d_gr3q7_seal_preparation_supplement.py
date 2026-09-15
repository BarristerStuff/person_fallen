#!/usr/bin/env python3
"""Seal the no-provider Q7 reports and final read-only dataset snapshot once."""
from __future__ import annotations
import hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');Q=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_04_gr3q7_20260831_01';F=Q/'freeze/p4d_gr3q7_preparation_freeze.json';OUT=Q/'freeze/p4d_gr3q7_preparation_supplement_freeze.json';V=Q/'05_checkpoints/preparation_supplement_verification.json'
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def j(p,x):
 t=Path(p).with_name(Path(p).name+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 with t.open('rb') as f:os.fsync(f.fileno())
 os.replace(t,p)
def main():
 if OUT.exists() or V.exists():raise RuntimeError('supplement already sealed')
 initial=json.load(open(F));checks={p:h(p)==x for p,x in initial['artifact_sha256'].items()}
 if h(F)!='9ac34d6335c48883845e1bcb8d254596623a13f9625d93a406570d80461cc8c5' or Path(str(F)+'.sha256').read_text().split()[0]!=h(F) or not all(checks.values()):raise RuntimeError('initial preparation integrity failure')
 r=subprocess.run(['python3','/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py','--json'],capture_output=True,text=True,timeout=240);x=json.loads(r.stdout);snap={'returncode':r.returncode,'validator':{k:x[k] for k in ('status','error_count','full_hash_check','warning_count','media_count','label_count','batch_count','split_count')},'p4d_active_references':0,'provider_requests':0};j(Q/'00_preflight/dataset_before_after.json',snap)
 if r.returncode or x['status']!='valid' or x['error_count']!=0 or not x['full_hash_check']:raise RuntimeError('dataset gate failure')
 arts=[F,Path(str(F)+'.sha256'),Q/'provider_failure_classifier_v2.py',Q/'00_preflight/dataset_before_after.json',Q/'00_preflight/q6_authority_audit.json',Q/'00_preflight/completion_unknown_forensics.json',Q/'00_preflight/classifier_regression.json',Q/'02_plan/q7_network_stability_balanced_20_plan.csv',Q/'02_plan/q7_plan_audit.json',Q/'05_checkpoints/authorization_gate.json',ROOT/'reports/102_p4d_gr3q6_failure_classifier_erratum.md',ROOT/'reports/103_p4d_gr3q7_completion_unknown_forensics.md',ROOT/'reports/104_p4d_gr3q7_failure_classifier_v2.md',ROOT/'reports/105_p4d_gr3q7_balanced_20_plan.md',ROOT/'reports/108_p4d_gr3q7_final.md',ROOT/'PERSON_FALLEN_V2.md',Path(__file__)]
 seal={'stage':'P4D_GR3Q7_NETWORK_STABILITY_RECOVERY','status':'AWAITING_Q7_GENERATION_AUTHORIZATION','provider_requests':0,'initial_freeze_sha256':h(F),'reports_106_107_absent_reason':'no_authorized_execution_or_partial_qa','artifact_sha256':{str(p):h(p) for p in arts}};j(OUT,seal);d=h(OUT);Path(str(OUT)+'.sha256').write_text(f'{d}  {OUT.name}\n')
 verify={'freeze_sha256':d,'sidecar_match':Path(str(OUT)+'.sha256').read_text().split()[0]==d,'bound_artifact_count':len(arts),'all_bound_artifacts_match':all(h(p)==x for p,x in seal['artifact_sha256'].items()),'provider_requests':0};j(V,verify);print(json.dumps(verify,sort_keys=True))
if __name__=='__main__':main()
