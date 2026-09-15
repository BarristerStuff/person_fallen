#!/usr/bin/env python3
"""Q6 zero-provider-request preparation and telemetry erratum."""
from __future__ import annotations
import csv,hashlib,json,sqlite3,subprocess
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');G=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen';Q5=G/'06_execution/quota_campaign_window_02_policy_adapter_20260830_01';Q6=G/'06_execution/quota_campaign_window_03_gr3q6_20260831_02';M=G/'03_fullregen_plan/full_regen_prompt_manifest.csv';F=Q5/'freeze/p4d_gr3q5_terminal_freeze.json';EXPECTED='3c219c9d75803cd5427862c0255ab557e92969085a864b116435aea85f8817f2'
def h(p):
 x=hashlib.sha256();x.update(Path(p).read_bytes());return x.hexdigest()
def j(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
def rd(p):
 with open(p,encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def wc(p,fs,xs):
 with open(p,'w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fs,lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(xs)
def main():
 if Q6.exists():raise RuntimeError('existing Q6 revision')
 fr=json.load(open(F));bad=[]
 for p,x in fr['artifact_sha256'].items():
  if h(p)!=x:bad.append(p)
 if h(F)!=EXPECTED or bad:raise RuntimeError('BLOCKED_PARENT_FREEZE_INTEGRITY')
 fail=json.load(open(Q5/'04_raw_responses/PF_P4D_NEG_CHAIR_G003_V03.json'));events=[]
 for line in fail['stderr_redacted'].splitlines():
  try:events.append(json.loads(line))
  except Exception:pass
 retry=[e for e in events if e.get('type')=='retry_scheduled'];starts=[e for e in events if e.get('type')=='request.started']
 telemetry={'q5_frozen_retry_counter':6,'q5_frozen_physical_lower_bound':17,'unique_native_retry_events':len({(e.get('data',{}).get('retry_number'),e.get('data',{}).get('status_code')) for e in retry}),'failed_logical_request_started_events':len(starts),'raw_evidence_physical_attempt_lower_bound':10+len(starts),'status_change':False,'stop_reason_change':False,'reset_at_utc':'2026-08-30T16:14:53+00:00','reset_at_local':'2026-08-31T00:14:53+08:00','current_utc':datetime.now(timezone.utc).isoformat(),'quota_reset_time_gate_pass':datetime.now(timezone.utc).timestamp()>=1788106493}
 rows=rd(M);legacy=rd(Q5/'00_preflight/current_verified_success_132.csv');success={r['prompt_id'] for r in legacy};c=sqlite3.connect(Q5/'03_ledger/gr3q5.sqlite3');success|={r[0] for r in c.execute("select prompt_id from slots where state='SUCCESS'")};unknown=c.execute("select count(*) from slots where state='COMPLETION_UNKNOWN'").fetchone()[0];c.close();assert len(success)==142 and unknown==0
 by={r['prompt_id']:r for r in rows};out=[r for r in rows if r['prompt_id'] not in success];assert len(out)==298
 # Adapter render prompts remain deterministic V1 provenance from Q5's manifest.
 ap={r['prompt_id']:r for r in rd(Q5/'01_adapter/render_prompt_manifest_v1.csv')}
 groups={}
 for r in out:groups.setdefault(r['group_id'],[]).append(r)
 partial=groups.pop('PF_P4D_NEG_CHAIR_G003');assert [r['variant_id'] for r in partial]==['V03','V04','V05']
 cur=Counter(by[x]['taxonomy'] for x in success);target=Counter(r['taxonomy'] for r in rows)
 def score(g):return max((target[x['taxonomy']]-cur[x['taxonomy']])/target[x['taxonomy']] for x in g)
 def pick(role,split,n):
  xs=[g for g in groups.values() if len(g)==5 and g[0]['target_role']==role and g[0]['planned_internal_split']==split];return sorted(xs,key=lambda g:(-score(g),g[0]['taxonomy'],g[0]['group_id']))[:n]
 chosen=[];seen=set()
 for role,split,n in (('hard_negative','NEW_DESIGN',1),('hard_negative','NEW_SCREEN',1),('positive','NEW_DESIGN',2),('positive','NEW_SCREEN',2)):
  candidates=pick(role,split,99)
  for g in candidates:
   if g[0]['taxonomy'] not in seen and len([x for x in chosen if x[0]['target_role']==role and x[0]['planned_internal_split']==split])<n:chosen.append(g);seen.add(g[0]['taxonomy'])
  if len([x for x in chosen if x[0]['target_role']==role and x[0]['planned_internal_split']==split])<n:
   for g in candidates:
    if g not in chosen and len([x for x in chosen if x[0]['target_role']==role and x[0]['planned_internal_split']==split])<n:chosen.append(g)
 assert len(chosen)==6
 plan=partial+[r for g in chosen for r in sorted(g,key=lambda x:x['variant_id'])]
 assert len(plan)==33 and Counter(r['target_role'] for r in plan)==Counter({'hard_negative':10,'positive':20,'ordinary_negative':3}) and Counter(r['planned_internal_split'] for r in plan)==Counter({'NEW_DESIGN':18,'NEW_SCREEN':15})
 Q6.mkdir();
 for d in ('00_preflight','01_inventory','02_plan','03_ledger','04_raw_responses','05_checkpoints','06_partial_qa','freeze'):(Q6/d).mkdir()
 inv=[]
 for p in sorted(success):
  r=by[p];inv.append({'prompt_id':p,'role':r['target_role'],'taxonomy':r['taxonomy'],'planned_split':r['planned_internal_split'],'adapter_stratum':'CODEX_SAFE_STAGED_CV_V1' if p in ap else 'LEGACY_NO_ADAPTER','profile_stratum':'HISTORICAL'})
 wc(Q6/'01_inventory/current_verified_success_142.csv',list(inv[0]),inv);wc(Q6/'01_inventory/outstanding_298.csv',['prompt_id','target_role','taxonomy','planned_internal_split','group_id','variant_id'],out)
 pp=[]
 for i,r in enumerate(plan,1):
  a=ap[r['prompt_id']];pp.append({'q6_order':i,'prompt_id':r['prompt_id'],'group_id':r['group_id'],'variant_id':r['variant_id'],'role':r['target_role'],'taxonomy':r['taxonomy'],'planned_split':r['planned_internal_split'],'parent_state':'Q5_HTTP429' if r['prompt_id'].endswith('_G003_V03') else 'OUTSTANDING','parent_request_id':'PF_P4D_NEG_CHAIR_G003_V03' if r['prompt_id'].endswith('_G003_V03') else '','adapter_version':'CODEX_SAFE_STAGED_CV_V1','render_prompt_sha256':a['render_prompt_sha256'],'selection_reason':'Q6_QUOTA_PROBE_PARTIAL_GROUP' if i==1 else 'Q6_PARTIAL_GROUP' if i<=3 else 'NORMALIZED_DEFICIT_GROUP_BALANCING'})
 wc(Q6/'02_plan/q6_balanced_window_33_plan.csv',list(pp[0]),pp)
 j(Q6/'00_preflight/q5_retry_telemetry_erratum.json',telemetry);j(Q6/'02_plan/q6_plan_audit.json',{'rows':33,'unique':33,'role':dict(Counter(x['role'] for x in pp)),'split':dict(Counter(x['planned_split'] for x in pp)),'taxonomy_groups':[g[0]['taxonomy'] for g in chosen],'semantic_frozen_prompt_changed':False,'provider_render_prompt_changed':True,'adapter_version':'CODEX_SAFE_STAGED_CV_V1'})
 runtime=subprocess.run(['node','/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs','--json','--provider','codex','doctor'],capture_output=True,text=True,check=False);j(Q6/'00_preflight/provider_runtime.json',{'returncode':runtime.returncode,'payload':json.loads(runtime.stdout) if runtime.stdout else {},'provider_requests':0})
 auth={'authorized':False,'reason':'no_explicit_Q6_generation_authorization_in_current_top_level_message','provider_requests':0};j(Q6/'05_checkpoints/authorization_gate.json',auth)
 freeze={'status':'AWAITING_Q6_GENERATION_AUTHORIZATION','parent_q5_freeze_sha256':EXPECTED,'telemetry':telemetry,'starting_success':142,'starting_outstanding':298,'q6_plan_sha256':h(Q6/'02_plan/q6_balanced_window_33_plan.csv'),'authorization':auth,'artifact_sha256':{str(p):h(p) for p in (F,Q6/'00_preflight/q5_retry_telemetry_erratum.json',Q6/'01_inventory/current_verified_success_142.csv',Q6/'01_inventory/outstanding_298.csv',Q6/'02_plan/q6_balanced_window_33_plan.csv',Q6/'02_plan/q6_plan_audit.json',Q6/'00_preflight/provider_runtime.json',Q6/'05_checkpoints/authorization_gate.json',Path(__file__))}};fp=Q6/'freeze/p4d_gr3q6_preparation_freeze.json';j(fp,freeze);Path(str(fp)+'.sha256').write_text(f'{h(fp)}  {fp.name}\n')
 print(json.dumps({'status':freeze['status'],'success':142,'outstanding':298,'plan_rows':33,'retry_events':telemetry['unique_native_retry_events'],'physical':telemetry['raw_evidence_physical_attempt_lower_bound'],'reset_gate':telemetry['quota_reset_time_gate_pass']}))
if __name__=='__main__':main()
