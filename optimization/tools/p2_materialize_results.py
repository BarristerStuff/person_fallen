#!/usr/bin/env python3
"""Deterministically materialize P2 protocol and metric artifacts from durable evidence."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,sqlite3,statistics
from collections import Counter
from pathlib import Path

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P2=ROOT/'05_p2_hard_negative_semantic_optimization';CFG=P2/'03_candidates/p2_request_config.json';RUNNER=ROOT/'tools/p2_inference_runner.py'
FIELDS=['request_id','media_id','split','event_label','sample_role','scenario_id','group_id','image_sha256','predicted_status','predicted_binary_alert','evidence','response_nonempty','thinking_present','http_ok','json_ok','schema_ok','canonical_ok','attempt_count','latency_seconds','done_reason','eval_count','is_correct','error_type']
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def prompt_path(candidate):return P2/'03_candidates'/('C0_BASELINE' if candidate=='C0' else candidate)/(candidate+'_prompt.txt')
def paths(phase,candidate):
 if phase=='canary':return P2/'03_candidates'/candidate/'canary',P2/'03_candidates/protocol_canary_manifest.csv'
 if phase=='screen':return P2/'04_screening'/candidate,P2/'01_internal_split/p2_screen_manifest.csv'
 if phase=='val':return P2/'06_val',ROOT/'04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv'
def load(path):
 with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def quantile(values,p):
 if not values:return None
 xs=sorted(values);i=(len(xs)-1)*p;lo=math.floor(i);hi=math.ceil(i);return xs[lo] if lo==hi else xs[lo]+(xs[hi]-xs[lo])*(i-lo)
def atomic_text(path,text):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',encoding='utf-8') as f:f.write(text);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def out_csv(path,rows,fields):
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def parse(wrapper,http_ok):
 outer=wrapper.get('outer_json',{});response=outer.get('response','');thinking=outer.get('thinking','');nonempty=isinstance(response,str) and bool(response.strip());thinking_present=isinstance(thinking,str) and bool(thinking.strip())
 if not http_ok:return 'protocol_failure','',False,False,False,thinking_present,'http_failure'
 if wrapper.get('outer_json_error'):return 'protocol_failure','',False,False,False,thinking_present,'outer_json_failure'
 if not nonempty:return 'protocol_failure','',False,False,False,thinking_present,'response_empty'
 try:obj=json.loads(response)
 except Exception as exc:return 'protocol_failure','',True,False,False,thinking_present,'response_json_failure: '+str(exc)
 schema=isinstance(obj,dict) and set(obj)=={'person_fallen','evidence'} and obj.get('person_fallen') in {'positive','negative','uncertain'} and isinstance(obj.get('evidence'),str) and bool(obj['evidence'].strip())
 if not schema:return 'protocol_failure','',True,True,False,thinking_present,'response_schema_failure'
 return obj['person_fallen'],obj['evidence'].strip(),True,True,True,thinking_present,''
def metrics(rows):
 valid=[r for r in rows if r['event_label'] in {'0','1'} and r['canonical_ok']=='true'];tp=fp=tn=fn=0
 for row in valid:
  gt=row['event_label'];alert=row['predicted_binary_alert']=='true'
  if gt=='1' and alert:tp+=1
  elif gt=='1':fn+=1
  elif alert:fp+=1
  else:tn+=1
 ratio=lambda a,b:None if not b else a/b;ordinary=[r for r in valid if r['sample_role']=='negative'];hard=[r for r in valid if r['sample_role']=='hard_negative'];uncertain=sum(r['predicted_status']=='uncertain' for r in valid)
 return {'determinate_count':len(valid),'TP':tp,'FP':fp,'TN':tn,'FN':fn,'precision':ratio(tp,tp+fp),'recall':ratio(tp,tp+fn),'f1':ratio(2*tp,2*tp+fp+fn),'accuracy':ratio(tp+tn,tp+tn+fp+fn),'fpr':ratio(fp,fp+tn),'specificity':ratio(tn,tn+fp),'ordinary_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in ordinary),len(ordinary)),'hard_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in hard),len(hard)),'positive_recall':ratio(tp,tp+fn),'model_uncertain_count':uncertain,'model_uncertain_rate':ratio(uncertain,len(valid)),'gt_uncertain_prediction_distribution':dict(Counter(r['predicted_status'] for r in rows if r['event_label']=='uncertain'))}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['canary','screen','val']);ap.add_argument('candidate',choices=['C0','C1','C2','C3']);args=ap.parse_args();run_dir,manifest_path=paths(args.phase,args.candidate);manifest=load(manifest_path);by_id={r['media_id']:r for r in manifest};db=sqlite3.connect(run_dir/'request_ledger.sqlite3');metadata=dict(db.execute('SELECT k,v FROM metadata'));ledger=db.execute('SELECT request_id,media_id,state,started_at,completed_at,attempt,http_status,latency_seconds,response_sha256,error_type FROM requests ORDER BY request_id').fetchall();states=dict(db.execute('SELECT state,count(*) FROM requests GROUP BY state'));db.close()
 if states.get('STARTED',0):raise SystemExit('P2_MATERIALIZE_INDETERMINATE_REQUEST')
 predictions=[];raws=[];logs=[]
 for request_id,media_id,state,started,completed,attempt,http_status,latency,response_sha,error_type in ledger:
  m=by_id[media_id];wrapper={};response_path=run_dir/'responses'/(request_id+'.json')
  if state=='COMPLETED':
   wrapper=json.loads(response_path.read_text());
   if sha(response_path)!=response_sha:raise SystemExit('P2_MATERIALIZE_RESPONSE_HASH_MISMATCH')
  status,evidence,nonempty,json_ok,schema_ok,thinking_present,parse_error=parse(wrapper,state=='COMPLETED' and http_status==200);canonical=status in {'positive','negative','uncertain'};alert=status=='positive';gt=m['event_label'];split=m.get('split') or m.get('original_split');is_correct='' if gt=='uncertain' or not canonical else str((gt=='1' and alert) or (gt=='0' and not alert)).lower();outer=wrapper.get('outer_json',{})
  predictions.append({'request_id':request_id,'media_id':media_id,'split':split,'event_label':gt,'sample_role':m['sample_role'],'scenario_id':m['scenario_id'],'group_id':m['group_id'],'image_sha256':m['image_sha256'],'predicted_status':status,'predicted_binary_alert':str(alert).lower() if canonical else '','evidence':evidence,'response_nonempty':str(nonempty).lower(),'thinking_present':str(thinking_present).lower(),'http_ok':str(state=='COMPLETED' and http_status==200).lower(),'json_ok':str(json_ok).lower(),'schema_ok':str(schema_ok).lower(),'canonical_ok':str(canonical).lower(),'attempt_count':attempt,'latency_seconds':f'{latency:.6f}' if latency is not None else '','done_reason':outer.get('done_reason',''),'eval_count':outer.get('eval_count',''),'is_correct':is_correct,'error_type':parse_error or error_type or ''})
  logs.append({'request_id':request_id,'media_id':media_id,'split':split,'state':state,'request_payload_config':wrapper.get('request_payload_without_image',{}),'timestamp_start_utc':started,'timestamp_end_utc':completed,'attempt':attempt,'http_code':http_status,'latency_seconds':latency,'response_sha256':response_sha,'image_sha256':m['image_sha256'],'error_type':parse_error or error_type or ''})
  raws.append({'request_id':request_id,'media_id':media_id,'outer_json':outer,'response':outer.get('response',''),'thinking':outer.get('thinking','')})
 out_csv(run_dir/'predictions.csv',predictions,FIELDS);atomic_text(run_dir/'request_log.jsonl',''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in logs));atomic_text(run_dir/'raw_responses.jsonl',''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in raws));out_csv(run_dir/'protocol_failures.csv',[r for r in predictions if r['canonical_ok']!='true'],FIELDS)
 n=len(predictions);valid=[r for r in predictions if r['canonical_ok']=='true'];latencies=[float(r['latency_seconds']) for r in valid];warm=latencies[1:];ratio=lambda count:count/n if n else None
 protocol={'request_count':n,'http_success_rate':ratio(sum(r['http_ok']=='true' for r in predictions)),'response_nonempty_rate':ratio(sum(r['response_nonempty']=='true' for r in predictions)),'thinking_present_rate':ratio(sum(r['thinking_present']=='true' for r in predictions)),'json_parse_success_rate':ratio(sum(r['json_ok']=='true' for r in predictions)),'schema_success_rate':ratio(sum(r['schema_ok']=='true' for r in predictions)),'canonical_prediction_success_rate':ratio(len(valid)),'latency_seconds':{'cold':latencies[0] if latencies else None,'warm_mean':statistics.mean(warm) if warm else None,'p50':quantile(warm,.5),'p95':quantile(warm,.95),'max':max(warm) if warm else None},'prediction_distribution':dict(Counter(r['predicted_status'] for r in predictions))}
 gate=all(protocol[key]==1.0 for key in ['http_success_rate','response_nonempty_rate','json_parse_success_rate','schema_success_rate','canonical_prediction_success_rate']);summary={'stage':'P2_HARD_NEGATIVE_SEMANTIC_OPTIMIZATION','phase':args.phase,'candidate':args.candidate,'execution_status':'COMPLETE' if sum(states.values())==n and set(states)<={'COMPLETED','FAILED_CONFIRMED'} else 'INCOMPLETE','ledger_states':states,'planned_requests':len(manifest),'holdout_requests':0,'holdout_consumed':False,'manifest_sha256':sha(manifest_path),'prompt_sha256':sha(prompt_path(args.candidate)),'config_sha256':sha(CFG),'runner_sha256':sha(RUNNER),'materializer_sha256':sha(Path(__file__)),'protocol':protocol,'protocol_gate_pass':gate,'metrics':metrics(predictions) if args.phase!='canary' and gate else None,'predictions_sha256':sha(run_dir/'predictions.csv'),'raw_responses_sha256':sha(run_dir/'raw_responses.jsonl'),'request_log_sha256':sha(run_dir/'request_log.jsonl')}
 atomic_text(run_dir/'summary.json',json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n');atomic_text(run_dir/'summary.md','# P2 '+args.phase.upper()+' '+args.candidate+' summary\n\n```json\n'+json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n```\n');print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
