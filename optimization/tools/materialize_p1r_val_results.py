#!/usr/bin/env python3
"""Deterministically materialize P1R result files from the durable ledger and response files."""
from __future__ import annotations
import csv,hashlib,json,math,os,sqlite3,statistics
from collections import Counter
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P1R=ROOT/'04_p1r_freeze_binding_recovery';VAL=P1R/'val';MAN=P1R/'preflight/recovery_val_manifest.csv';FREEZE=P1R/'freeze/p1r_recovery_freeze.json';CFG=P1R/'config/p1r_config.json'
FIELDS=['request_id','media_id','split','event_label','sample_role','scenario_id','group_id','image_sha256','predicted_status','predicted_binary_alert','evidence','response_nonempty','thinking_present','http_ok','json_ok','schema_ok','canonical_ok','attempt_count','latency_seconds','done_reason','eval_count','is_correct','error_type']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def csvrows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def outcsv(p,rs,fields):
 t=p.with_suffix(p.suffix+'.tmp')
 with t.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rs);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def outjson(p,o):
 t=p.with_suffix(p.suffix+'.tmp')
 with t.open('w',encoding='utf-8') as f:json.dump(o,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def parse(outer):
 response=outer.get('response','');thinking=outer.get('thinking','');nonempty=isinstance(response,str) and bool(response.strip());think=isinstance(thinking,str) and bool(thinking.strip())
 if not nonempty:return 'protocol_failure','',False,False,False,think,outer.get('done_reason',''),outer.get('eval_count'),'response_empty'
 try:o=json.loads(response)
 except Exception as e:return 'protocol_failure','',True,False,False,think,outer.get('done_reason',''),outer.get('eval_count'),'response_json_parse_failure: '+str(e)
 if not isinstance(o,dict) or set(o)!={'person_fallen','evidence'} or o.get('person_fallen') not in {'positive','negative','uncertain'} or not isinstance(o.get('evidence'),str) or not o['evidence'].strip():return 'protocol_failure','',True,True,False,think,outer.get('done_reason',''),outer.get('eval_count'),'response_schema_failure'
 return o['person_fallen'],o['evidence'].strip(),True,True,True,think,outer.get('done_reason',''),outer.get('eval_count'),''
def pct(xs,q):
 xs=sorted(xs);i=(len(xs)-1)*q;a=math.floor(i);b=math.ceil(i);return xs[a] if a==b else xs[a]+(xs[b]-xs[a])*(i-a)
def metrics(rows):
 tp=fp=tn=fn=0
 for r in rows:
  if r['canonical_ok']!='true':continue
  alert=r['predicted_binary_alert']=='true';gt=r['event_label']
  if gt=='1' and alert:tp+=1
  elif gt=='1':fn+=1
  elif alert:fp+=1
  else:tn+=1
 ratio=lambda a,b:None if not b else a/b
 hard=[r for r in rows if r['sample_role']=='hard_negative' and r['canonical_ok']=='true'];ordinary=[r for r in rows if r['sample_role']=='negative' and r['canonical_ok']=='true']
 return {'TP':tp,'FP':fp,'TN':tn,'FN':fn,'precision':ratio(tp,tp+fp),'recall':ratio(tp,tp+fn),'f1':ratio(2*tp,2*tp+fp+fn),'accuracy':ratio(tp+tn,tp+tn+fp+fn),'fpr':ratio(fp,fp+tn),'specificity':ratio(tn,tn+fp),'ordinary_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in ordinary),len(ordinary)),'hard_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in hard),len(hard)),'positive_recall':ratio(tp,tp+fn),'model_uncertain_count':sum(r['predicted_status']=='uncertain' for r in rows),'model_uncertain_rate':ratio(sum(r['predicted_status']=='uncertain' for r in rows),len(rows))}
def main():
 manifest=csvrows(MAN);byid={r['media_id']:r for r in manifest};db=sqlite3.connect(VAL/'request_ledger.sqlite3');db.row_factory=sqlite3.Row;led=[dict(x) for x in db.execute('SELECT * FROM requests ORDER BY request_id')];meta={x['k']:x['v'] for x in db.execute('SELECT k,v FROM metadata')};db.close()
 states=Counter(x['state'] for x in led)
 if len(manifest)!=100 or len(led)!=100 or states!={'COMPLETED':100} or {x['media_id'] for x in led}!={x['media_id'] for x in manifest}:raise SystemExit('P1R_MATERIALIZE_BLOCKED_NONTERMINAL_OR_SET_MISMATCH')
 preds=[];raw=[];logs=[]
 for l in led:
  m=byid[l['media_id']];rp=VAL/'responses'/(l['request_id']+'.json')
  if not rp.is_file() or sha(rp)!=l['response_sha256']:raise SystemExit('P1R_MATERIALIZE_BLOCKED_RESPONSE_HASH_MISMATCH')
  outer=json.loads(rp.read_text());status,evidence,nonempty,jsonok,schemaok,think,done,evalc,etype=parse(outer);canonical=status in {'positive','negative','uncertain'};alert=status=='positive';gt=m['event_label'];correct='' if not canonical else str((gt=='1' and alert) or (gt=='0' and not alert)).lower()
  p={'request_id':l['request_id'],'media_id':m['media_id'],'split':m['split'],'event_label':gt,'sample_role':m['sample_role'],'scenario_id':m['scenario_id'],'group_id':m['group_id'],'image_sha256':m['image_sha256'],'predicted_status':status,'predicted_binary_alert':str(alert).lower() if canonical else '','evidence':evidence,'response_nonempty':str(nonempty).lower(),'thinking_present':str(think).lower(),'http_ok':'true','json_ok':str(jsonok).lower(),'schema_ok':str(schemaok).lower(),'canonical_ok':str(canonical).lower(),'attempt_count':l['attempt'],'latency_seconds':f"{l['latency_seconds']:.6f}",'done_reason':done or '','eval_count':evalc if evalc is not None else '','is_correct':correct,'error_type':etype};preds.append(p)
  raw.append({'request_id':l['request_id'],'media_id':m['media_id'],'outer_json':outer,'response':outer.get('response',''),'thinking':outer.get('thinking','')})
  logs.append({'request_id':l['request_id'],'media_id':m['media_id'],'split':m['split'],'image_sha256':m['image_sha256'],'state':l['state'],'started_at':l['started_at'],'completed_at':l['completed_at'],'attempt':l['attempt'],'http_status':l['http_status'],'latency_seconds':l['latency_seconds'],'response_sha256':l['response_sha256'],'error_type':l['error_type'],'config_sha256':l['config_sha256']})
 outcsv(VAL/'predictions.csv',preds,FIELDS)
 for name,subset in [('protocol_failures.csv',[r for r in preds if r['canonical_ok']!='true']),('false_positives.csv',[r for r in preds if r['event_label']=='0' and r['canonical_ok']=='true' and r['predicted_binary_alert']=='true']),('false_negatives.csv',[r for r in preds if r['event_label']=='1' and r['canonical_ok']=='true' and r['predicted_binary_alert']!='true']),('model_uncertain.csv',[r for r in preds if r['predicted_status']=='uncertain'])]:outcsv(VAL/name,subset,FIELDS)
 for name,items in [('raw_responses.jsonl',raw),('request_log.jsonl',logs)]:
  t=(VAL/name).with_suffix((VAL/name).suffix+'.tmp')
  with t.open('w',encoding='utf-8') as f:
   for x in items:f.write(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n')
   f.flush();os.fsync(f.fileno())
  os.replace(t,VAL/name)
 pro={'request_count':100,'http_success_rate':sum(r['http_ok']=='true' for r in preds)/100,'response_nonempty_rate':sum(r['response_nonempty']=='true' for r in preds)/100,'thinking_present_rate':sum(r['thinking_present']=='true' for r in preds)/100,'json_parse_success_rate':sum(r['json_ok']=='true' for r in preds)/100,'schema_success_rate':sum(r['schema_ok']=='true' for r in preds)/100,'canonical_prediction_success_rate':sum(r['canonical_ok']=='true' for r in preds)/100,'prediction_distribution':dict(Counter(r['predicted_status'] for r in preds))}
 lat=[float(r['latency_seconds']) for r in preds if r['canonical_ok']=='true'];warm=lat[1:];pro['latency_seconds']={'first_request':lat[0] if lat else None,'warm_mean':statistics.mean(warm) if warm else None,'p50':pct(warm,.5) if warm else None,'p95':pct(warm,.95) if warm else None,'max':max(warm) if warm else None}
 gate=all(pro[x]==1.0 for x in ['http_success_rate','response_nonempty_rate','json_parse_success_rate','schema_success_rate','canonical_prediction_success_rate']);freeze=json.loads(FREEZE.read_text());summary={'P1R_NAME':'P1R_FREEZE_BINDING_RECOVERY','run_id':meta['run_id'],'execution_status':'COMPLETE','ledger_states':dict(states),'planned_val_requests':100,'confirmed_completed_requests':100,'completion_unknown_count':0,'failed_confirmed_count':0,'holdout_requests':0,'holdout_consumed':False,'P1R_VAL_IS_PRISTINE':False,'prior_val_confirmed_exposure':10,'prior_val_possible_additional_exposure':1,'freeze_sha256':sha(FREEZE),'val_manifest_sha256':sha(MAN),'config_sha256':sha(CFG),'runner_sha256':freeze['file_hashes']['p1r_runner']['sha256'],'materializer_sha256':sha(Path(__file__)),'protocol':pro,'protocol_gate_pass':gate,'metrics':metrics(preds) if gate else None,'predictions_sha256':sha(VAL/'predictions.csv'),'raw_responses_sha256':sha(VAL/'raw_responses.jsonl'),'request_log_sha256':sha(VAL/'request_log.jsonl'),'ledger_sha256':sha(VAL/'request_ledger.sqlite3')}
 outjson(VAL/'summary.json',summary);(VAL/'summary.md').write_text('# P1R recovery VAL summary\n\n```json\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n```\n')
 print(json.dumps({'P1R_MATERIALIZE':'PASS','protocol_gate':gate,'summary':summary},ensure_ascii=False))
if __name__=='__main__':main()
