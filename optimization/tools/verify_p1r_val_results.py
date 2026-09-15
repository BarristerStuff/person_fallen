#!/usr/bin/env python3
"""Independent post-run set and metric verifier for P1R recovery VAL."""
from __future__ import annotations
import csv,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P1R=ROOT/'04_p1r_freeze_binding_recovery';VAL=P1R/'val';MAN=P1R/'preflight/recovery_val_manifest.csv'
def load(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def metrics(rows):
 tp=fp=tn=fn=0
 for r in rows:
  alert=r['predicted_binary_alert']=='true';gt=r['event_label']
  if gt=='1' and alert:tp+=1
  elif gt=='1':fn+=1
  elif alert:fp+=1
  else:tn+=1
 ratio=lambda a,b:None if not b else a/b
 hard=[r for r in rows if r['sample_role']=='hard_negative'];ordinary=[r for r in rows if r['sample_role']=='negative']
 return {'TP':tp,'FP':fp,'TN':tn,'FN':fn,'precision':ratio(tp,tp+fp),'recall':ratio(tp,tp+fn),'f1':ratio(2*tp,2*tp+fp+fn),'accuracy':ratio(tp+tn,tp+tn+fp+fn),'fpr':ratio(fp,fp+tn),'specificity':ratio(tn,tn+fp),'ordinary_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in ordinary),len(ordinary)),'hard_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in hard),len(hard)),'positive_recall':ratio(tp,tp+fn),'model_uncertain_count':sum(r['predicted_status']=='uncertain' for r in rows),'model_uncertain_rate':ratio(sum(r['predicted_status']=='uncertain' for r in rows),len(rows))}
def main():
 m,p=load(MAN),load(VAL/'predictions.csv');raw=[json.loads(x) for x in (VAL/'raw_responses.jsonl').read_text().splitlines() if x.strip()];logs=[json.loads(x) for x in (VAL/'request_log.jsonl').read_text().splitlines() if x.strip()];db=sqlite3.connect(VAL/'request_ledger.sqlite3');ledger=[x[0] for x in db.execute("SELECT media_id FROM requests WHERE state='COMPLETED'")];db.close();ids={x['media_id'] for x in m};checks={'manifest_count':len(m),'prediction_count':len(p),'raw_count':len(raw),'log_count':len(logs),'ledger_completed_count':len(ledger),'manifest_unique':len(ids),'prediction_unique':len({x['media_id'] for x in p}),'raw_unique_requests':len({x['request_id'] for x in raw}),'log_unique_requests':len({x['request_id'] for x in logs}),'sets_match':ids=={x['media_id'] for x in p}=={x['media_id'] for x in raw}=={x['media_id'] for x in logs}==set(ledger),'holdout_rows':sum(x['split']=='HOLDOUT' for x in p),'canonical_all':all(x['canonical_ok']=='true' for x in p)}
 s=json.loads((VAL/'summary.json').read_text());re=metrics(p);match=re==s['metrics'];ok=checks=={'manifest_count':100,'prediction_count':100,'raw_count':100,'log_count':100,'ledger_completed_count':100,'manifest_unique':100,'prediction_unique':100,'raw_unique_requests':100,'log_unique_requests':100,'sets_match':True,'holdout_rows':0,'canonical_all':True} and match and s['protocol_gate_pass'] is True
 out={'P1R_RESULT_VERIFICATION':'PASS' if ok else 'FAIL','checks':checks,'recomputed_metrics':re,'summary_metrics':s['metrics'],'METRIC_RECOMPUTE_MATCH':match,'P1R_VALID_RECOVERY_BASELINE':ok}
 (P1R/'val/result_verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
