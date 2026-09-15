#!/usr/bin/env python3
"""Q9 frozen runner, generated from Q8's independently sealed runner shape.

The material execution code is statically snapshotted into the Q9 revision by
the inherited init flow; only the Q9 parent, plan, caps and deterministic
selection are changed here.
"""
from __future__ import annotations
import sys
from pathlib import Path

SRC=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization/tools/p4d_gr3q8_authorized_execution.py')
text=SRC.read_text(encoding='utf-8')
repl={
 "quota_campaign_window_04_gr3q7_authorized_20260831_01":"quota_campaign_window_05_gr3q8_authorized_20260831_01",
 "quota_campaign_window_05_gr3q8_authorized_20260831_01":"quota_campaign_window_06_gr3q9_authorized_20260831_01",
 "p4d_gr3q7_execution_terminal_freeze.json":"p4d_gr3q8_execution_terminal_freeze.json",
 "p4d_gr3q8_execution_terminal_freeze.json":"p4d_gr3q9_execution_terminal_freeze.json",
 "p4d_gr3q7_active_runner.lock":"p4d_gr3q9_active_runner.lock",
 "gr3q8_execution.sqlite3":"gr3q9_execution.sqlite3",
 "q8_balanced_stable_25_plan.csv":"q9_hard_negative_balanced_30_plan.csv",
 "q8_order":"q9_order",
 "P4D_GR3Q8":"P4D_GR3Q9",
 "p4d_gr3q8":"p4d_gr3q9",
 "E_Q7='9adc539e0b55a9207111b025bebdefcc4951760616b83f9680f91df28ef5aaf9'":"E_Q7='2235fff83e62b2daf05f736446ccc5819e599fd2c7112fdb788871ecc20d8477'",
 "MAX_LOGICAL=25;MAX_PHYSICAL=30;MAX_RETRIES=4;MAX_REFUSALS=3":"MAX_LOGICAL=30;MAX_PHYSICAL=36;MAX_RETRIES=4;MAX_REFUSALS=3",
 "(len(a),len(b),len(c))!=(171,1,268)":"(len(a),len(b),len(c))!=(196,1,243)",
 "'verified_success':171,'completion_unknown':1,'safe_outstanding':268":"'verified_success':196,'completion_unknown':1,'safe_outstanding':243",
 "'starting_verified_success':171,'starting_completion_unknown':1,'starting_safe_outstanding':268":"'starting_verified_success':196,'starting_completion_unknown':1,'starting_safe_outstanding':243",
 "'starting_verified_success':171,'starting_completion_unknown':1,'starting_safe_executable_outstanding':268":"'starting_verified_success':196,'starting_completion_unknown':1,'starting_safe_executable_outstanding':243",
 "Counter({'positive':15,'hard_negative':10})":"Counter({'hard_negative':25,'positive':5})",
 "len(plan)!=25":"len(plan)!=30",
 "'q8_plan_rows':25":"'q9_plan_rows':30",
 "'q8_plan_sha256'":"'q9_plan_sha256'",
 "'q8_groups'":"'q9_groups'",
 "'q8_role_distribution'":"'q9_role_distribution'",
 "'q8_split_distribution'":"'q9_split_distribution'",
 "'q8_taxonomies'":"'q9_taxonomies'",
}
for a,b in repl.items(): text=text.replace(a,b)
text=text.replace("len(plan)!=25", "len(plan)!=30")
text=text.replace("len({x['prompt_id'] for x in plan})!=25", "len({x['prompt_id'] for x in plan})!=30")
text=text.replace("role!=Counter({'positive':15,'hard_negative':10})", "role!=Counter({'hard_negative':25,'positive':5})")
text=text.replace("if len(plan)!=25 or len({x['prompt_id'] for x in plan})!=25 or role!=Counter({'positive':15,'hard_negative':10}) or split!=Counter({'NEW_DESIGN':15,'NEW_SCREEN':10}) or any('MAINT_G006' in x['prompt_id'] for x in plan):raise RuntimeError('BLOCKED_Q8_PLAN_INTEGRITY')", "if len(plan)!=30 or len({x['prompt_id'] for x in plan})!=30 or role!=Counter({'hard_negative':25,'positive':5}) or split!=Counter({'NEW_DESIGN':15,'NEW_SCREEN':15}) or any('MAINT_G006' in x['prompt_id'] for x in plan):raise RuntimeError('BLOCKED_Q9_PLAN_INTEGRITY')")
text=text.replace("if len(plan)!=30 or len({x['prompt_id'] for x in plan})!=30 or role!=Counter({'hard_negative':25,'positive':5}) or split!=Counter({'NEW_DESIGN':15,'NEW_SCREEN':10}) or any('MAINT_G006' in x['prompt_id'] for x in plan):raise RuntimeError('BLOCKED_Q8_PLAN_INTEGRITY')", "if len(plan)!=30 or len({x['prompt_id'] for x in plan})!=30 or role!=Counter({'hard_negative':25,'positive':5}) or split!=Counter({'NEW_DESIGN':15,'NEW_SCREEN':15}) or any('MAINT_G006' in x['prompt_id'] for x in plan):raise RuntimeError('BLOCKED_Q9_PLAN_INTEGRITY')")
# Q8's immutable regression remains in the Q7 preparation directory.
text=text.replace("reg=json.loads((Q7/'00_preflight/classifier_regression.json').read_text())", "reg=json.loads((GR3/'06_execution/quota_campaign_window_04_gr3q7_20260831_01/00_preflight/classifier_regression.json').read_text())")
ns={'__name__':'q9_template','__file__':str(SRC)}
ns={'__name__':'q9_template','__file__':str(Path(__file__))}
exec(compile(text,str(SRC),'exec'),ns)

# The replacement text is intentionally only a template.  Rebind parent paths
# explicitly so that repeated Q8/Q9 substrings cannot cascade into Q9 itself.
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
GR3=ROOT/'08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen'
PARENT=GR3/'06_execution/quota_campaign_window_05_gr3q8_authorized_20260831_01'
Q9EXEC=GR3/'06_execution/quota_campaign_window_06_gr3q9_authorized_20260831_02'
ns['Q7']=PARENT;ns['EXEC']=Q9EXEC;ns['DB']=Q9EXEC/'03_ledger/gr3q9_execution.sqlite3';ns['PLAN']=Q9EXEC/'02_plan/q9_hard_negative_balanced_30_plan.csv';ns['RAW']=Q9EXEC/'04_raw_responses';ns['RIMG']=Q9EXEC/'07_generated_raw';ns['FINAL']=Q9EXEC/'08_final';ns['QA']=Q9EXEC/'06_partial_qa';ns['CHECK']=Q9EXEC/'05_checkpoints';ns['PRE']=Q9EXEC/'00_preflight';ns['LOCK']=GR3/'06_execution/.p4d_gr3q9_active_runner.lock';ns['CLASSIFIER']=PARENT/'02_plan/provider_failure_classifier_v2.py';ns['PARSER']=PARENT/'02_plan/retry_event_parser_v2.py'
def verify_parent():
 f=PARENT/'freeze/p4d_gr3q8_execution_terminal_freeze.json';x=ns['json'].loads(f.read_text());checks={p:Path(p).is_file() and ns['sha'](Path(p))==h for p,h in x['artifact_sha256'].items()};o={'expected_sha256':'2235fff83e62b2daf05f736446ccc5819e599fd2c7112fdb788871ecc20d8477','actual_sha256':ns['sha'](f),'sidecar_match':f.with_name(f.name+'.sha256').read_text().split()[0]==ns['sha'](f),'bound_artifact_count':len(checks),'all_bound_artifacts_match':all(checks.values())}
 if o['actual_sha256']!=o['expected_sha256'] or not o['sidecar_match'] or not o['all_bound_artifacts_match'] or len(checks)!=95:raise RuntimeError('Q8 parent terminal integrity failure')
 return o
ns['verify_q7']=verify_parent
ns['MAX_LOGICAL']=30;ns['MAX_PHYSICAL']=36;ns['MAX_RETRIES']=4;ns['MAX_REFUSALS']=3

HN_TARGET={'ground_maintenance':40,'pushup_plank':50,'crawling_quadruped_support':40,'squat_crouch_deep_bend':30,'mixed_hard_negative':20}
Q9_GROUPS=['PF_P4D_POS_CURLED_G001','PF_P4D_HN_MAINT_G001','PF_P4D_HN_SQUAT_G001','PF_P4D_HN_CRAWL_G006','PF_P4D_HN_PLANK_G007','PF_P4D_HN_MIX_G004']
def q9_plan_rows(manifest,safe):
 m={x['prompt_id']:x for x in manifest}; sid={x['prompt_id'] for x in safe};out=[];order=1
 target={'curled_or_partially_occluded_lying':15,**HN_TARGET}
 verified={'curled_or_partially_occluded_lying':5,'ground_maintenance':1,'pushup_plank':5,'crawling_quadruped_support':5,'squat_crouch_deep_bend':5,'mixed_hard_negative':5}
 for gid in Q9_GROUPS:
  g=sorted([x for x in manifest if x['group_id']==gid],key=lambda x:x['variant_id'])
  if len(g)!=5 or any(x['prompt_id'] not in sid for x in g) or gid=='PF_P4D_HN_MAINT_G006':raise RuntimeError('Q9 selected group not complete safe '+gid)
  for x in g:
   tax=x['taxonomy'];reason='HN maximum normalized deficit distinct taxonomy under split feasibility' if x['target_role']=='hard_negative' else 'positive curled maximum normalized deficit under split feasibility'
   out.append({'q9_order':str(order),'prompt_id':x['prompt_id'],'group_id':gid,'variant_id':x['variant_id'],'role':x['target_role'],'taxonomy':tax,'planned_split':x['planned_internal_split'],'parent_state':'SAFE_EXECUTABLE_OUTSTANDING','adapter_version':ns['ADAPTER_VERSION'],'render_prompt_sha256':'','taxonomy_target':str(target[tax]),'taxonomy_verified_before_q9':str(verified[tax]),'normalized_deficit':f'{(target[tax]-verified[tax])/target[tax]:.6f}','selection_reason':reason});order+=1
 return out
ns['GROUPS']=Q9_GROUPS;ns['plan_rows']=q9_plan_rows
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('command',choices=['init','run']);a=p.parse_args();ns['init']() if a.command=='init' else ns['run']()
