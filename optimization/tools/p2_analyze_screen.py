#!/usr/bin/env python3
"""Apply frozen SCREEN gates, paired comparison, and unique-winner rule."""
from __future__ import annotations
import csv,json,math,os
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P2=ROOT/'05_p2_hard_negative_semantic_optimization';OUT=P2/'04_screening';DECISION=OUT/'winner_decision.json';LATENCY_LIMIT=1.8520842
def load_json(path):return json.loads(path.read_text())
def load_csv(path):
 with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def atomic_json(path,obj):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def atomic_csv(path,fields,rows):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def exact_mcnemar(b,c):
 n=b+c
 if not n:return 1.0
 tail=sum(math.comb(n,k) for k in range(0,min(b,c)+1))/(2**n)
 return min(1.0,2*tail)
def main():
 if DECISION.exists():raise SystemExit('P2_WINNER_DECISION_ALREADY_EXISTS')
 paths={'C0':OUT/'C0_BASELINE','C1':OUT/'C1','C2':OUT/'C2','C3':OUT/'C3'};summaries={c:load_json(p/'summary.json') for c,p in paths.items()};preds={c:{r['media_id']:r for r in load_csv(p/'predictions.csv')} for c,p in paths.items()}
 if any(set(preds[c])!=set(preds['C0']) for c in ['C1','C2','C3']):raise SystemExit('P2_SCREEN_ENTITY_SET_MISMATCH')
 base=summaries['C0']['metrics'];comparison=[];paired=[];eligible=[];ineligible={}
 for candidate in ['C0','C1','C2','C3']:
  s=summaries[candidate];m=s['metrics'];p95=s['protocol']['latency_seconds'].get('p95',s['protocol']['latency_seconds'].get('subset_p95'));reasons=[]
  if candidate!='C0':
   if s['protocol_gate_pass'] is not True:reasons.append('protocol_gate_fail')
   if m['positive_recall']<0.95:reasons.append('positive_recall_below_0.95')
   if m['ordinary_negative_fpr']!=0:reasons.append('ordinary_negative_fpr_nonzero')
   if p95>LATENCY_LIMIT:reasons.append('p95_latency_above_1.8520842')
   improvement=base['hard_negative_fpr']-m['hard_negative_fpr']
   if not (m['hard_negative_fpr']<=0.05 or improvement>=0.05):reasons.append('hard_negative_improvement_insufficient')
   if reasons:ineligible[candidate]=reasons
   else:eligible.append(candidate)
  comparison.append({'candidate':candidate,'protocol_gate_pass':s['protocol_gate_pass'],'TP':m['TP'],'FP':m['FP'],'TN':m['TN'],'FN':m['FN'],'precision':m['precision'],'recall':m['recall'],'f1':m['f1'],'accuracy':m['accuracy'],'ordinary_negative_fpr':m['ordinary_negative_fpr'],'hard_negative_fpr':m['hard_negative_fpr'],'model_uncertain_rate':m['model_uncertain_rate'],'p50':s['protocol']['latency_seconds'].get('p50',s['protocol']['latency_seconds'].get('subset_p50')),'p95':p95,'hard_negative_fpr_delta_vs_C0':m['hard_negative_fpr']-base['hard_negative_fpr'],'precision_delta_vs_C0':m['precision']-base['precision'],'recall_delta_vs_C0':m['recall']-base['recall'],'eligible':candidate in eligible,'rejection_reasons':';'.join(ineligible.get(candidate,[]))})
  if candidate=='C0':continue
  counts={'baseline_FP_to_candidate_TN':0,'baseline_TN_to_candidate_FP':0,'baseline_TP_to_candidate_FN':0,'baseline_FN_to_candidate_TP':0,'baseline_correct_candidate_wrong':0,'baseline_wrong_candidate_correct':0}
  for media_id,b in preds['C0'].items():
   x=preds[candidate][media_id];gt=b['event_label'];ba=b['predicted_status']=='positive';xa=x['predicted_status']=='positive'
   if gt=='0' and ba and not xa:counts['baseline_FP_to_candidate_TN']+=1
   if gt=='0' and not ba and xa:counts['baseline_TN_to_candidate_FP']+=1
   if gt=='1' and ba and not xa:counts['baseline_TP_to_candidate_FN']+=1
   if gt=='1' and not ba and xa:counts['baseline_FN_to_candidate_TP']+=1
   if gt in {'0','1'}:
    bc=(gt=='1')==ba;xc=(gt=='1')==xa
    if bc and not xc:counts['baseline_correct_candidate_wrong']+=1
    if not bc and xc:counts['baseline_wrong_candidate_correct']+=1
  paired.append({'candidate':candidate,**counts,'mcnemar_exact_p':exact_mcnemar(counts['baseline_correct_candidate_wrong'],counts['baseline_wrong_candidate_correct'])})
 atomic_csv(OUT/'screening_comparison.csv',list(comparison[0]),comparison);atomic_csv(OUT/'paired_error_analysis.csv',list(paired[0]),paired)
 winner=None
 if eligible:
  winner=sorted(eligible,key=lambda c:(summaries[c]['metrics']['hard_negative_fpr'],-summaries[c]['metrics']['precision'],-summaries[c]['metrics']['f1'],summaries[c]['protocol']['latency_seconds']['p95']))[0]
 wm=summaries[winner]['metrics'] if winner else None;decision={'stage':'P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION','baseline':'C0','candidates':['C1','C2','C3'],'eligible_candidates':eligible,'ineligible_candidates':ineligible,'winner':winner or 'NONE','selection_rule':['minimum hard_negative_fpr','maximum precision','maximum f1','minimum p95 latency'],'latency_limit_seconds':LATENCY_LIMIT,'minimum_improvement_rule':'hard_negative_fpr<=0.05 OR absolute reduction>=0.05','baseline_screen_metrics':base,'winner_screen_metrics':wm,'absolute_hard_negative_fpr_reduction':base['hard_negative_fpr']-wm['hard_negative_fpr'] if winner else None,'precision_delta':wm['precision']-base['precision'] if winner else None,'recall_delta':wm['recall']-base['recall'] if winner else None,'f1_delta':wm['f1']-base['f1'] if winner else None,'latency_p95_delta':summaries[winner]['protocol']['latency_seconds']['p95']-summaries['C0']['protocol']['latency_seconds']['subset_p95'] if winner else None,'paired_comparison':{r['candidate']:r for r in paired},'screen_blind_before_candidate_freeze':True,'val_errors_used_for_prompt_design':False,'p2_val_requests_before_winner_freeze':0,'holdout_requests':0}
 atomic_json(DECISION,decision);print(json.dumps(decision,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
