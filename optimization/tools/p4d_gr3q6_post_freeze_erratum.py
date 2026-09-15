#!/usr/bin/env python3
"""Seal the Q6 raw-evidence classification correction without rewriting history."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
E=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen/06_execution/quota_campaign_window_03_gr3q6_authorized_20260831_01'
TF=E/'freeze/p4d_gr3q6_execution_terminal_freeze.json'
ERR=E/'05_checkpoints/post_freeze_classification_erratum.json'
FREEZE=E/'freeze/p4d_gr3q6_execution_post_freeze_erratum.json'
VERIFY=E/'05_checkpoints/post_freeze_erratum_verification.json'
EXPECTED='95df937db097e23f2e3939fbd132f3e9a24a20bff3d0d91eb174285a082d8d52'

def h(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def w(p:Path,x:object)->None:
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 with t.open('rb') as f:os.fsync(f.fileno())
 os.replace(t,p)
def main()->None:
 if ERR.exists() or FREEZE.exists() or VERIFY.exists():raise RuntimeError('immutable erratum already exists')
 if h(TF)!=EXPECTED or Path(str(TF)+'.sha256').read_text().split()[0]!=EXPECTED:raise RuntimeError('original execution terminal freeze mismatch')
 old=json.loads(TF.read_text());checks={p:h(Path(p))==x for p,x in old['artifact_sha256'].items()}
 if not all(checks.values()):raise RuntimeError('original terminal artifact mismatch')
 raw=E/'04_raw_responses/PF_P4D_HN_MAINT_G006_V02.json';r=json.loads(raw.read_text())
 if r['outer_json'].get('error',{}).get('code')!='network_error' or r['telemetry']!={'unique_native_retry_events':3,'request_started_events':4,'physical_attempt_lower_bound':4}:raise RuntimeError('raw evidence mismatch')
 err={'stage':'P4D_GR3Q6_BALANCED_QUOTA_RESET_RECOVERY','kind':'POST_FREEZE_CLASSIFICATION_ERRATUM','original_terminal_freeze_sha256':EXPECTED,'original_terminal_freeze_preserved':True,'raw_response_sha256':h(raw),'affected_prompt_id':r['prompt_id'],'original_frozen_state':'CONTENT_POLICY_REFUSAL_CONFIRMED','original_frozen_stop_reason':'NATIVE_RETRY_GUARD','raw_outer_error_code':'network_error','corrected_state':'COMPLETION_UNKNOWN','corrected_primary_stop_reason':'STOPPED_COMPLETION_UNKNOWN','simultaneous_guard_reached':'NATIVE_RETRY_GUARD','corrected_logical_invocations':10,'corrected_success':9,'corrected_policy_refusals':0,'corrected_other_failures':0,'corrected_completion_unknown':1,'corrected_unique_native_retry_events':3,'corrected_physical_attempt_lower_bound':13,'no_resend':True,'no_post_terminal_provider_request':True,'reason':'The original classifier matched the SSE metadata field name safety_identifier rather than explicit policy-refusal evidence.'}
 w(ERR,err)
 arts=[TF,Path(str(TF)+'.sha256'),E/'05_checkpoints/terminal_freeze_verification.json',raw,ERR,ROOT/'reports/98_p4d_gr3q6_execution.md',ROOT/'reports/99_p4d_gr3q6_partial_qa.md',ROOT/'reports/101_p4d_gr3q6_execution_final.md',ROOT/'PERSON_FALLEN_V2.md',Path(__file__)]
 seal={'stage':err['stage'],'kind':'POST_FREEZE_ERRATUM_SEAL','original_terminal_freeze_sha256':EXPECTED,'corrected_terminal_interpretation':{'status':'STOPPED_COMPLETION_UNKNOWN','completion_unknown':1,'policy_refusals':0,'success':9,'logical_invocations':10,'native_retry_guard_reached':True},'artifact_sha256':{str(p):h(p) for p in arts}}
 w(FREEZE,seal);d=h(FREEZE);Path(str(FREEZE)+'.sha256').write_text(f'{d}  {FREEZE.name}\n',encoding='utf-8')
 verify={'freeze_sha256':d,'sidecar_match':Path(str(FREEZE)+'.sha256').read_text().split()[0]==d,'bound_artifact_count':len(arts),'all_bound_artifacts_match':all(h(Path(p))==x for p,x in seal['artifact_sha256'].items()),'original_terminal_freeze_sha256':EXPECTED,'original_terminal_freeze_still_valid':all(checks.values())}
 w(VERIFY,verify);print(json.dumps(verify,sort_keys=True))
if __name__=='__main__':main()
