#!/usr/bin/env python3
"""Offline C0 SCREEN baseline from frozen P1A DEV predictions; zero requests."""
from __future__ import annotations
import csv,hashlib,json,math,os,statistics
from collections import Counter
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P2=ROOT/'05_p2_hard_negative_semantic_optimization';MAN=P2/'01_internal_split/p2_screen_manifest.csv';PRED=ROOT/'03_p1a_think_false_protocol/dev/predictions.csv';OUT=P2/'04_screening/C0_BASELINE';PROMPT=P2/'03_candidates/C0_BASELINE/C0_prompt.txt'
FIELDS=['request_id','media_id','split','event_label','sample_role','scenario_id','group_id','image_sha256','predicted_status','predicted_binary_alert','evidence','response_nonempty','thinking_present','http_ok','json_ok','schema_ok','canonical_ok','attempt_count','latency_seconds','done_reason','eval_count','is_correct','error_type']
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def quantile(xs,p):
 xs=sorted(xs);i=(len(xs)-1)*p;lo=math.floor(i);hi=math.ceil(i);return xs[lo] if lo==hi else xs[lo]+(xs[hi]-xs[lo])*(i-lo)
def atomic_text(path,text):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8') as f:f.write(text);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def ratio(a,b):return None if not b else a/b
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 with MAN.open(newline='',encoding='utf-8') as f:manifest={r['media_id']:r for r in csv.DictReader(f)}
 rows=[]
 with PRED.open(newline='',encoding='utf-8') as f:
  for r in csv.DictReader(f):
   if r['media_id'] in manifest:
    m=manifest[r['media_id']];row={k:r.get(k,'') for k in FIELDS};row.update({'split':'DEV','event_label':m['event_label'],'sample_role':m['sample_role'],'scenario_id':m['scenario_id'],'group_id':m['group_id'],'image_sha256':m['image_sha256']});rows.append(row)
 rows.sort(key=lambda r:r['media_id'])
 if len(rows)!=120 or {r['media_id'] for r in rows}!=set(manifest):raise SystemExit('P2_C0_SCREEN_ENTITY_MISMATCH')
 tmp=OUT/'predictions.csv.tmp'
 with tmp.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows);f.flush();os.fsync(f.fileno())
 os.replace(tmp,OUT/'predictions.csv')
 valid=[r for r in rows if r['event_label'] in {'0','1'}];tp=fp=tn=fn=0
 for r in valid:
  gt=r['event_label'];alert=r['predicted_status']=='positive'
  if gt=='1' and alert:tp+=1
  elif gt=='1':fn+=1
  elif alert:fp+=1
  else:tn+=1
 ordinary=[r for r in valid if r['sample_role']=='negative'];hard=[r for r in valid if r['sample_role']=='hard_negative'];unc=sum(r['predicted_status']=='uncertain' for r in valid);lat=[float(r['latency_seconds']) for r in rows]
 metrics={'determinate_count':len(valid),'TP':tp,'FP':fp,'TN':tn,'FN':fn,'precision':ratio(tp,tp+fp),'recall':ratio(tp,tp+fn),'f1':ratio(2*tp,2*tp+fp+fn),'accuracy':ratio(tp+tn,tp+tn+fp+fn),'ordinary_negative_fpr':ratio(sum(r['predicted_status']=='positive' for r in ordinary),len(ordinary)),'hard_negative_fpr':ratio(sum(r['predicted_status']=='positive' for r in hard),len(hard)),'positive_recall':ratio(tp,tp+fn),'model_uncertain_count':unc,'model_uncertain_rate':ratio(unc,len(valid)),'gt_uncertain_prediction_distribution':dict(Counter(r['predicted_status'] for r in rows if r['event_label']=='uncertain'))}
 protocol={'request_count':120,'source':'P1A_DEV_OFFLINE_SUBSET','new_model_requests':0,'http_success_rate':sum(r['http_ok']=='true' for r in rows)/120,'response_nonempty_rate':sum(r['response_nonempty']=='true' for r in rows)/120,'json_parse_success_rate':sum(r['json_ok']=='true' for r in rows)/120,'schema_success_rate':sum(r['schema_ok']=='true' for r in rows)/120,'canonical_prediction_success_rate':sum(r['canonical_ok']=='true' for r in rows)/120,'thinking_present_rate':sum(r['thinking_present']=='true' for r in rows)/120,'latency_seconds':{'subset_mean':statistics.mean(lat),'subset_p50':quantile(lat,.5),'subset_p95':quantile(lat,.95),'subset_max':max(lat)}}
 summary={'stage':'P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION','phase':'screen','candidate':'C0','source':'P1A_DEV_PREDICTIONS_OFFLINE_RECOMPUTE','new_model_requests':0,'manifest_sha256':sha(MAN),'prompt_sha256':sha(PROMPT),'source_predictions_sha256':sha(PRED),'predictions_sha256':sha(OUT/'predictions.csv'),'protocol_gate_pass':all(protocol[k]==1 for k in ['http_success_rate','response_nonempty_rate','json_parse_success_rate','schema_success_rate','canonical_prediction_success_rate']),'protocol':protocol,'metrics':metrics,'holdout_requests':0,'holdout_consumed':False}
 atomic_text(OUT/'summary.json',json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n');atomic_text(OUT/'summary.md','# P2 SCREEN C0 offline baseline\n\n```json\n'+json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n```\n');print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
