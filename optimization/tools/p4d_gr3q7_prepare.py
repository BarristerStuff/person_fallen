#!/usr/bin/env python3
"""Zero-provider-request Q7 quarantine, classifier regression, and plan freeze."""
from __future__ import annotations
import csv,hashlib,importlib.util,json,os,subprocess
from collections import Counter
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');G=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen';Q6=G/'06_execution/quota_campaign_window_03_gr3q6_authorized_20260831_01';Q7=G/'06_execution/quota_campaign_window_04_gr3q7_20260831_01';M=G/'03_fullregen_plan/full_regen_prompt_manifest.csv';A=G/'06_execution/quota_campaign_window_02_policy_adapter_20260830_01/01_adapter/render_prompt_manifest_v1.csv'
Q6F=Q6/'freeze/p4d_gr3q6_execution_terminal_freeze.json';E6=Q6/'freeze/p4d_gr3q6_execution_post_freeze_erratum.json';EX1='95df937db097e23f2e3939fbd132f3e9a24a20bff3d0d91eb174285a082d8d52';EX2='4719e6fa842ada2346596bb3316661926082e5a741c7217740d6143c3a13010b';UNKNOWN='PF_P4D_HN_MAINT_G006_V02'
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rd(p):
 with open(p,encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def wc(p,fields,rows):
 with open(p,'w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(rows)
def j(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def freeze_ok(p,expected):
 x=json.load(open(p));checks={a:h(a)==b for a,b in x['artifact_sha256'].items()};return h(p)==expected and Path(str(p)+'.sha256').read_text().split()[0]==expected and all(checks.values()),len(checks)
def main():
 if (Q7/'freeze/p4d_gr3q7_preparation_freeze.json').exists():raise RuntimeError('Q7 preparation already sealed')
 ok1,n1=freeze_ok(Q6F,EX1);ok2,n2=freeze_ok(E6,EX2)
 if not ok1 or not ok2:raise RuntimeError('BLOCKED_Q6_FREEZE_INTEGRITY')
 spec=importlib.util.spec_from_file_location('c',Q7/'provider_failure_classifier_v2.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 cases={'A_window01_content_refusal':(G/'06_execution/quota_campaign_window_01_authorized_20260830_05/04_raw_responses/P4D_GR3Q4E_WINDOW01_031_PF_P4D_POS_CURLED_G003_V03.json','CONTENT_POLICY_REFUSAL_CONFIRMED','STRUCTURED_EXPLICIT_REFUSAL'),'B_q5_quota':(G/'06_execution/quota_campaign_window_02_policy_adapter_20260830_01/04_raw_responses/PF_P4D_NEG_CHAIR_G003_V03.json','FAILED_CONFIRMED','HTTP429_USAGE_LIMIT_REACHED'),'C_q6_network_unknown':(Q6/'04_raw_responses/PF_P4D_HN_MAINT_G006_V02.json','COMPLETION_UNKNOWN','NETWORK_ERROR_COMPLETION_AMBIGUITY')}
 results={};
 for name,(p,state,reason) in cases.items():
  got=c.classify(json.load(open(p)));results[name]={'expected_state':state,'expected_reason':reason,'actual':got,'pass':got['state']==state and got['reason']==reason}
 if not all(x['pass'] for x in results.values()):raise RuntimeError('BLOCKED_FAILURE_CLASSIFIER_REGRESSION')
 manifest=rd(M);by={r['prompt_id']:r for r in manifest};success=rd(Q6/'06_partial_qa/current_verified_success.csv');success_ids={r['prompt_id'] for r in success};unknown_ids={UNKNOWN};safe_ids={r['prompt_id'] for r in manifest}-success_ids-unknown_ids
 assert len(success_ids)==151 and len(unknown_ids)==1 and len(safe_ids)==288 and not(success_ids&unknown_ids or success_ids&safe_ids or unknown_ids&safe_ids) and success_ids|unknown_ids|safe_ids==set(by)
 Q7.mkdir(exist_ok=True)
 for d in ('00_preflight','01_inventory','02_plan','03_ledger','04_raw_responses','05_checkpoints','06_partial_qa','07_generated_raw','08_final','freeze'):(Q7/d).mkdir(exist_ok=True)
 success_rows=[dict(by[p],state='VERIFIED_SUCCESS') for p in sorted(success_ids)];unknown_rows=[dict(by[p],state='COMPLETION_UNKNOWN_QUARANTINED',no_resend=True,group_state='PARTIAL_GROUP_WITH_COMPLETION_UNKNOWN') for p in sorted(unknown_ids)];safe_rows=[dict(by[p],state='SAFE_NOT_STARTED') for p in sorted(safe_ids)]
 wc(Q7/'01_inventory/verified_success.csv',list(success_rows[0]),success_rows);wc(Q7/'01_inventory/completion_unknown_quarantine.csv',list(unknown_rows[0]),unknown_rows);wc(Q7/'01_inventory/safe_executable_outstanding.csv',list(safe_rows[0]),safe_rows)
 # Q7 eligibility requires a complete 5/5 safe group and excludes all of G006.
 groups={}
 for p in safe_rows:groups.setdefault(p['group_id'],[]).append(p)
 eligible=[g for gid,g in groups.items() if len(g)==5 and gid!='PF_P4D_HN_MAINT_G006']
 current=Counter(r['taxonomy'] for r in success_rows);target=Counter(r['taxonomy'] for r in manifest)
 def score(g):return (target[g[0]['taxonomy']]-current[g[0]['taxonomy']])/target[g[0]['taxonomy']]
 positives=[g for g in eligible if g[0]['target_role']=='positive'];hns=[g for g in eligible if g[0]['target_role']=='hard_negative']
 possible=[]
 for a in positives:
  for b in positives:
   for d in positives:
    if len({a[0]['group_id'],b[0]['group_id'],d[0]['group_id']})<3 or len({a[0]['taxonomy'],b[0]['taxonomy'],d[0]['taxonomy']})<3:continue
    for hn in hns:
     chosen=[a,b,d,hn]
     if Counter(x[0]['planned_internal_split'] for x in chosen)==Counter({'NEW_DESIGN':2,'NEW_SCREEN':2}):possible.append(chosen)
 if not possible:raise RuntimeError('BLOCKED_Q7_PLAN_FEASIBILITY')
 chosen=max(possible,key=lambda gs:(sum(score(g) for g in gs),tuple(sorted(g[0]['group_id'] for g in gs))))
 ordered=sorted(chosen,key=lambda g:(g[0]['planned_internal_split'],g[0]['target_role']!='positive',-score(g),g[0]['group_id']))
 adapters={r['prompt_id']:r for r in rd(A)};plan=[]
 for order,g in enumerate([x for g in ordered for x in sorted(g,key=lambda r:r['variant_id'])],1):
  a=adapters[g['prompt_id']];plan.append({'q7_order':order,'prompt_id':g['prompt_id'],'group_id':g['group_id'],'variant_id':g['variant_id'],'role':g['target_role'],'taxonomy':g['taxonomy'],'planned_split':g['planned_internal_split'],'parent_state':'SAFE_NOT_STARTED','adapter_version':'CODEX_SAFE_STAGED_CV_V1','render_prompt_sha256':a['render_prompt_sha256'],'selection_reason':'Q7_COMPLETE_GROUP_NORMALIZED_DEFICIT_NETWORK_STABILITY'})
 assert len(plan)==20 and len({x['prompt_id'] for x in plan})==20 and Counter(x['role'] for x in plan)==Counter({'positive':15,'hard_negative':5}) and Counter(x['planned_split'] for x in plan)==Counter({'NEW_DESIGN':10,'NEW_SCREEN':10}) and not({x['prompt_id'] for x in plan}&success_ids or {x['prompt_id'] for x in plan}&unknown_ids) and not any(x['group_id']=='PF_P4D_HN_MAINT_G006' for x in plan)
 wc(Q7/'02_plan/q7_network_stability_balanced_20_plan.csv',list(plan[0]),plan)
 runtime=subprocess.run(['node','/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs','--json','--provider','codex','doctor'],capture_output=True,text=True,timeout=90);j(Q7/'00_preflight/provider_runtime.json',{'returncode':runtime.returncode,'payload':json.loads(runtime.stdout),'provider_requests':0})
 forensics={'unknown_prompt_id':UNKNOWN,'searched_roots':[str(Q6/'04_raw_responses'),str(Q6/'07_generated_raw'),str(Q6/'08_final'),'/tmp/gpt-image-2*','/tmp/gpt_image*','/home/yanbo/.cache'],'request_correlated_image_artifacts_found':0,'late_arriving_output_files_found':0,'recovery_result':'NO_EXISTING_IMAGE_COMPLETION_EVIDENCE','authoritative_state':'COMPLETION_UNKNOWN_QUARANTINED','no_resend':True};j(Q7/'00_preflight/completion_unknown_forensics.json',forensics)
 j(Q7/'00_preflight/q6_authority_audit.json',{'q6_original_freeze_sha256':EX1,'q6_original_freeze_verified':ok1,'q6_original_bound_artifacts':n1,'q6_erratum_seal_sha256':EX2,'q6_erratum_verified':ok2,'q6_erratum_bound_artifacts':n2,'corrected_counts':{'logical':10,'success':9,'policy_refusals':0,'confirmed_failures':0,'completion_unknown':1,'http200':9,'http429':0,'http401':0,'http403':0,'http5xx':0,'network_error':1,'retry':3,'physical':13}})
 j(Q7/'00_preflight/classifier_regression.json',{'classifier_sha256':h(Q7/'provider_failure_classifier_v2.py'),'cases':results,'pass_count':sum(x['pass'] for x in results.values()),'total':3})
 audit={'verified_success':len(success_ids),'completion_unknown':len(unknown_ids),'safe_executable_outstanding':len(safe_ids),'success_role':dict(Counter(r['target_role'] for r in success_rows)),'success_split':dict(Counter(r['planned_internal_split'] for r in success_rows)),'q7_plan_groups':[g[0]['group_id'] for g in ordered],'q7_plan_taxonomies':[g[0]['taxonomy'] for g in ordered],'q7_role':dict(Counter(r['role'] for r in plan)),'q7_split':dict(Counter(r['planned_split'] for r in plan))};j(Q7/'02_plan/q7_plan_audit.json',audit)
 auth={'authorized':False,'reason':'task_prompt_is_not_independent_Q7_paid_generation_authorization','provider_requests':0};j(Q7/'05_checkpoints/authorization_gate.json',auth)
 arts=[Q7/'provider_failure_classifier_v2.py',Q7/'00_preflight/q6_authority_audit.json',Q7/'00_preflight/completion_unknown_forensics.json',Q7/'00_preflight/classifier_regression.json',Q7/'00_preflight/provider_runtime.json',Q7/'01_inventory/verified_success.csv',Q7/'01_inventory/completion_unknown_quarantine.csv',Q7/'01_inventory/safe_executable_outstanding.csv',Q7/'02_plan/q7_network_stability_balanced_20_plan.csv',Q7/'02_plan/q7_plan_audit.json',Q7/'05_checkpoints/authorization_gate.json',Path(__file__)]
 fr={'status':'AWAITING_Q7_GENERATION_AUTHORIZATION','provider_requests':0,'parent_q6_original_freeze_sha256':EX1,'parent_q6_erratum_seal_sha256':EX2,'classifier_sha256':h(Q7/'provider_failure_classifier_v2.py'),'q7_plan_sha256':h(Q7/'02_plan/q7_network_stability_balanced_20_plan.csv'),'artifact_sha256':{str(p):h(p) for p in arts}};f=Q7/'freeze/p4d_gr3q7_preparation_freeze.json';j(f,fr);Path(str(f)+'.sha256').write_text(f'{h(f)}  {f.name}\n')
 print(json.dumps({'status':fr['status'],'provider_requests':0,'success':151,'unknown':1,'safe':288,'plan_rows':20,'classifier_pass':'3/3','plan_sha256':fr['q7_plan_sha256']}))
if __name__=='__main__':main()
