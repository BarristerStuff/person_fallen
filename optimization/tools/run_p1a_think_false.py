#!/usr/bin/env python3
"""Frozen P1A: validate only whether top-level think=false restores response JSON."""
from __future__ import annotations
import argparse,base64,csv,hashlib,json,math,shutil,statistics,sys,time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib import error,request
from PIL import Image

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization'); P1=ROOT/'03_p1a_think_false_protocol'; DATA=ROOT/'01_data'; FORMAL=Path('/home/yanbo/net_vlm_xunjian_dataset')
PROMPT=ROOT/'00_definition/p0_prompt.txt'; CONFIG=P1/'config/p1a_think_false_config.json'; RESAMPLE=getattr(getattr(Image,'Resampling',Image),'LANCZOS')
FIELDS=['request_id','media_id','split','event_label','sample_role','scenario_id','group_id','image_sha256','predicted_status','predicted_binary_alert','evidence','response_nonempty','thinking_present','http_ok','json_ok','schema_ok','canonical_ok','attempt_count','latency_seconds','done_reason','eval_count','is_correct','error_type','reused_canary_result']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def load(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def outcsv(p,rows,fields):
 with p.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n',extrasaction='ignore');w.writeheader();w.writerows(rows)
def q(xs,v):
 if not xs:return None
 xs=sorted(xs);i=(len(xs)-1)*v;a=math.floor(i);b=math.ceil(i);return xs[a] if a==b else xs[a]+(xs[b]-xs[a])*(i-a)
def process(src,dst):
 with Image.open(src) as im:im.verify()
 with Image.open(src) as im:
  im=im.convert('RGB');im.thumbnail((448,336),RESAMPLE);c=Image.new('RGB',(448,336),(128,128,128));c.paste(im,((448-im.width)//2,(336-im.height)//2));c.save(dst,'JPEG',quality=70,optimize=True)
def invoke(img,cfg,prompt):
 payload={'model':cfg['model'],'prompt':prompt,'images':[base64.b64encode(img.read_bytes()).decode()],'stream':False,'format':'json','think':False,'options':cfg['options']}
 started=datetime.now(timezone.utc).isoformat();t=time.time()
 for attempt in range(1,cfg['max_transport_retries']+2):
  try:
   req=request.Request(cfg['endpoint']+'/api/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
   with request.urlopen(req,timeout=cfg['timeout_seconds']) as r:raw=r.read().decode();code=r.status
   return {'payload':{k:v for k,v in payload.items() if k!='images'},'started_at_utc':started,'ended_at_utc':datetime.now(timezone.utc).isoformat(),'http_ok':True,'http_code':code,'outer_raw':raw,'attempt_count':attempt,'latency_seconds':time.time()-t,'first_attempt_success':attempt==1,'transport_error':''}
  except (error.URLError,error.HTTPError,TimeoutError) as exc:
   last={'payload':{k:v for k,v in payload.items() if k!='images'},'started_at_utc':started,'ended_at_utc':datetime.now(timezone.utc).isoformat(),'http_ok':False,'http_code':getattr(exc,'code',None),'outer_raw':'','attempt_count':attempt,'latency_seconds':time.time()-t,'first_attempt_success':False,'transport_error':type(exc).__name__+': '+str(exc)}
   if attempt<=cfg['max_transport_retries']:continue
   return last
def parse(r):
 if not r['http_ok']:return ('protocol_failure','',False,False,False,False,'',None,r['transport_error'],'')
 try:o=json.loads(r['outer_raw'])
 except Exception as e:return ('protocol_failure','',False,False,False,False,'',None,'outer_json_parse_failure: '+str(e),'')
 response=o.get('response','');thinking=o.get('thinking',''); nonempty=isinstance(response,str) and bool(response.strip()); thinking_present=isinstance(thinking,str) and bool(thinking.strip())
 if not nonempty:return ('protocol_failure','',False,False,False,thinking_present,o.get('done_reason',''),o.get('eval_count'),'response_empty','')
 try:obj=json.loads(response)
 except Exception as e:return ('protocol_failure','',True,False,False,thinking_present,o.get('done_reason',''),o.get('eval_count'),'response_json_parse_failure: '+str(e),'')
 if not isinstance(obj,dict) or set(obj)!={'person_fallen','evidence'} or obj.get('person_fallen') not in {'positive','negative','uncertain'} or not isinstance(obj.get('evidence'),str) or not obj['evidence'].strip():return ('protocol_failure','',True,True,False,thinking_present,o.get('done_reason',''),o.get('eval_count'),'response_schema_failure','')
 return (obj['person_fallen'],obj['evidence'].strip(),True,True,True,thinking_present,o.get('done_reason',''),o.get('eval_count'),'','')
def met(rows):
 valid=[r for r in rows if r['event_label'] in {'0','1'} and r['canonical_ok']=='true'];tp=fp=tn=fn=0
 for r in valid:
  alert=r['predicted_binary_alert']=='true';gt=r['event_label']
  if gt=='1' and alert:tp+=1
  elif gt=='1':fn+=1
  elif alert:fp+=1
  else:tn+=1
 ratio=lambda a,b:None if not b else a/b
 hard=[r for r in valid if r['sample_role']=='hard_negative'];ordinary=[r for r in valid if r['sample_role']=='negative']
 return {'determinate_count':len(valid),'TP':tp,'FP':fp,'TN':tn,'FN':fn,'precision':ratio(tp,tp+fp),'recall':ratio(tp,tp+fn),'f1':ratio(2*tp,2*tp+fp+fn),'accuracy':ratio(tp+tn,tp+tn+fp+fn),'fpr':ratio(fp,fp+tn),'specificity':ratio(tn,tn+fp),'ordinary_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in ordinary),len(ordinary)),'hard_negative_fpr':ratio(sum(r['predicted_binary_alert']=='true' for r in hard),len(hard)),'positive_recall':ratio(tp,tp+fn),'model_uncertain_count':sum(r['predicted_status']=='uncertain' for r in valid),'model_uncertain_rate':ratio(sum(r['predicted_status']=='uncertain' for r in valid),len(valid)),'gt_uncertain_prediction_distribution':dict(Counter(r['predicted_status'] for r in rows if r['event_label']=='uncertain'))}
def protocol(rows):
 n=len(rows);valid=[r for r in rows if r['canonical_ok']=='true'];lat=[float(r['latency_seconds']) for r in valid];warm=lat[1:]
 ratio=lambda a:None if not n else a/n
 return {'request_count':n,'http_success_rate':ratio(sum(r['http_ok']=='true' for r in rows)),'response_nonempty_rate':ratio(sum(r['response_nonempty']=='true' for r in rows)),'thinking_present_rate':ratio(sum(r['thinking_present']=='true' for r in rows)),'json_parse_success_rate':ratio(sum(r['json_ok']=='true' for r in rows)),'schema_success_rate':ratio(sum(r['schema_ok']=='true' for r in rows)),'canonical_prediction_success_rate':ratio(len(valid)),'first_attempt_success_rate':ratio(sum(r.get('first_attempt_success','false')=='true' for r in rows)),'latency_seconds':{'cold':lat[0] if lat else None,'warm_mean':statistics.mean(warm) if warm else None,'p50':q(warm,.5),'p95':q(warm,.95),'max':max(warm) if warm else None},'prediction_distribution':dict(Counter(r['predicted_status'] for r in rows))}
def gate(p):return all(p[k]==1.0 for k in ['http_success_rate','response_nonempty_rate','json_parse_success_rate','schema_success_rate','canonical_prediction_success_rate'])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['canary','dev','val']);a=ap.parse_args();cfg=json.loads(CONFIG.read_text());prompt=PROMPT.read_text();ph=sha(PROMPT);ch=sha(CONFIG);runner=sha(Path(__file__))
 if ph!='b457a2442b8c4cca66866ecd7fcaaa765524740f1019e7811a05ec8e2c8335f4':raise SystemExit('BLOCKED_PROMPT_HASH_MISMATCH')
 if sha(DATA/'frozen_splits.csv')!='16b95d59c25313a6a8e35e4d0056b5626a04d44edc0e017549e628b92f15f33a' or sha(DATA/'frozen_manifest.csv')!='771380b70099e2e2e641330a7d4f04860e2284725722bde3cd2da8988abfb2c6':raise SystemExit('BLOCKED_FREEZE_HASH_MISMATCH')
 allrows=load(DATA/'frozen_manifest.csv'); stage_dir=P1/a.stage; stage_dir.mkdir(exist_ok=True);proc=stage_dir/'processed_448x336';proc.mkdir(exist_ok=True)
 if a.stage=='canary':selected=load(P1/'canary/canary_manifest.csv')
 else:selected=[r for r in allrows if r['split']==a.stage.upper()]
 if any(r['split']=='HOLDOUT' for r in selected):raise SystemExit('INVALID_HOLDOUT_CONTAMINATION')
 reused={};raw_reused=[];log_reused=[]
 if a.stage=='dev':
  csum=json.loads((P1/'canary/summary.json').read_text())
  if not csum['protocol_gate_pass'] or csum['prompt_sha256']!=ph or csum['config_sha256']!=ch or csum['runner_sha256']!=runner:raise SystemExit('DEV_REUSE_INVARIANT_FAIL')
  for r in load(P1/'canary/predictions.csv'):reused[r['media_id']]=r
  raw_reused=[json.loads(x) for x in (P1/'canary/raw_responses.jsonl').read_text().splitlines()];log_reused=[json.loads(x) for x in (P1/'canary/request_log.jsonl').read_text().splitlines()]
 preds=[];raws=list(raw_reused);logs=list(log_reused)
 for idx,row in enumerate(selected,1):
  if row['media_id'] in reused:
   r=dict(reused[row['media_id']]);r['reused_canary_result']='true';preds.append(r);continue
  dst=proc/(row['media_id']+'.jpg');process(FORMAL/row['formal_relative_path'],dst);inv=invoke(dst,cfg,prompt);status,evidence,nonempty,jsonok,schemaok,thinking,done,evc,etype,_=parse(inv);canonical=status in {'positive','negative','uncertain'};alert=status=='positive';gt=row['event_label'];correct='' if gt=='uncertain' or not canonical else str((gt=='1' and alert) or (gt=='0' and not alert)).lower();rid=f'{a.stage}-{idx:04d}-{row["media_id"]}'
  p={'request_id':rid,'media_id':row['media_id'],'split':row['split'],'event_label':gt,'sample_role':row['sample_role'],'scenario_id':row['scenario_id'],'group_id':row['group_id'],'image_sha256':row['image_sha256'],'predicted_status':status,'predicted_binary_alert':str(alert).lower() if canonical else '','evidence':evidence,'response_nonempty':str(nonempty).lower(),'thinking_present':str(thinking).lower(),'http_ok':str(inv['http_ok']).lower(),'json_ok':str(jsonok).lower(),'schema_ok':str(schemaok).lower(),'canonical_ok':str(canonical).lower(),'attempt_count':inv['attempt_count'],'latency_seconds':f"{inv['latency_seconds']:.6f}",'done_reason':done or '','eval_count':evc if evc is not None else '','is_correct':correct,'error_type':etype,'reused_canary_result':'false','first_attempt_success':str(inv['first_attempt_success']).lower()};preds.append(p)
  logs.append({'request_id':rid,'media_id':row['media_id'],'split':row['split'],'image_sha256':row['image_sha256'],'payload_config':inv['payload'],'timestamp_start_utc':inv['started_at_utc'],'timestamp_end_utc':inv['ended_at_utc'],'attempt_count':inv['attempt_count'],'http_ok':inv['http_ok'],'http_code':inv['http_code'],'first_attempt_success':inv['first_attempt_success'],'done_reason':done,'eval_count':evc,'latency_seconds':inv['latency_seconds'],'error_type':etype})
  raws.append({'request_id':rid,'media_id':row['media_id'],'outer_json':json.loads(inv['outer_raw']) if inv['outer_raw'] else {},'response':json.loads(inv['outer_raw']).get('response','') if inv['outer_raw'] else '','thinking':json.loads(inv['outer_raw']).get('thinking','') if inv['outer_raw'] else ''})
  if idx%10==0:print(f'{a.stage.upper()}_P1A_PROGRESS={idx}/{len(selected)}',flush=True)
 for r in preds:r.setdefault('first_attempt_success','true' if r.get('reused_canary_result')=='true' else 'false')
 outcsv(stage_dir/f'{a.stage}_manifest.csv',selected,list(selected[0]));outcsv(stage_dir/'predictions.csv',preds,FIELDS)
 with (stage_dir/'raw_responses.jsonl').open('w') as f:
  for x in raws:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 with (stage_dir/'request_log.jsonl').open('w') as f:
  for x in logs:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 failures=[r for r in preds if r['canonical_ok']!='true'];outcsv(stage_dir/'protocol_failures.csv',failures,FIELDS)
 for n,rs in [('false_positives.csv',[r for r in preds if r['event_label']=='0' and r['canonical_ok']=='true' and r['predicted_binary_alert']=='true']),('false_negatives.csv',[r for r in preds if r['event_label']=='1' and r['canonical_ok']=='true' and r['predicted_binary_alert']!='true']),('model_uncertain.csv',[r for r in preds if r['predicted_status']=='uncertain'])]:outcsv(stage_dir/n,rs,FIELDS)
 pro=protocol(preds);summary={'stage':a.stage,'P1A_NAME':'P1A_THINK_FALSE_PROTOCOL','think_false_only':True,'prompt_sha256':ph,'config_sha256':ch,'runner_sha256':runner,'frozen_manifest_sha256':sha(DATA/'frozen_manifest.csv'),'frozen_splits_sha256':sha(DATA/'frozen_splits.csv'),'selected_count':len(selected),'holdout_requests':0,'reused_canary_results':len(reused) if a.stage=='dev' else 0,'duplicate_protocol_requests':0,'protocol':pro,'protocol_gate_pass':gate(pro),'metrics':met(preds) if gate(pro) else None,'predictions_sha256':sha(stage_dir/'predictions.csv'),'raw_responses_sha256':sha(stage_dir/'raw_responses.jsonl'),'request_log_sha256':sha(stage_dir/'request_log.jsonl')}
 (stage_dir/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n');(stage_dir/'summary.md').write_text('# '+a.stage.upper()+' P1A summary\n\n```json\n'+json.dumps(summary,indent=2,ensure_ascii=False)+'\n```\n')
 print(json.dumps({'stage':a.stage,'protocol_gate_pass':summary['protocol_gate_pass'],'requests':len(preds),'holdout_requests':0,'summary':summary},ensure_ascii=False))
if __name__=='__main__':main()
